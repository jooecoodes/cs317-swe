import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createHostedApiProvider,API_BASE_URL} from '../src/hosted-api.js';
import {dataSource} from '../src/data-source.js';
import {loadSession,sessionState,signOut} from '../src/session.js';
import {store} from '../src/data.js';
import {loadPhotos,photoData,uploadPhoto,photoUpload,allowPhotoRetry} from '../src/photo-service.js';
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const photo={id:5,owner:'Account Tester',display_name:'Test Image',tags:['site'],size_bytes:10,timestamp:'2026-10-30T10:00:00',url:'/photos/5/file'};
test('sign-out navigates to the backend endpoint that clears the session cookie',()=>{
 const original=globalThis.location,redirects=[];globalThis.location={replace:url=>redirects.push(url)};
 try{signOut();assert.deepEqual(redirects,[new URL('/auth/logout',API_BASE_URL).href]);}
 finally{if(original===undefined)delete globalThis.location;else globalThis.location=original;}
});
test('session and photo requests share the configured server and browser sign-in cookie',async()=>{
 const calls=[],source=createHostedApiProvider({fetchImpl:async(url,options)=>{calls.push({url,options});return json({username:'Account Tester'});}});
 await source.request({service:'session',path:'/me'});assert.equal(calls[0].url,new URL('/auth/me',API_BASE_URL).href);assert.equal(calls[0].options.credentials,'same-origin');
 const form=new FormData();form.append('file',new Blob(['image'],{type:'image/png'}),'test.png');await source.request({service:'photos',path:'/upload',method:'POST',body:form,actor:'Account Tester'});
 assert.equal(calls[1].url,new URL('/app2/upload',API_BASE_URL).href);assert.equal(calls[1].options.body,form);assert.equal(calls[1].options.headers['Content-Type'],undefined);assert.equal(calls[1].options.headers['X-Actor'],'Account Tester');
 await assert.rejects(source.request({service:'photos',path:'//external.invalid/upload',method:'POST',actor:'Account Tester'}),/contract/);
});
test('the account username is loaded automatically and removed on expired sessions',async()=>{
 Object.assign(dataSource,createHostedApiProvider({fetchImpl:async()=>json({username:'Account Tester'})}));await loadSession();assert.equal(store.settings.name,'Account Tester');assert.equal(sessionState.status,'ready');
 Object.assign(dataSource,createHostedApiProvider({fetchImpl:async()=>json({detail:'Session expired'},401)}));await loadSession();assert.equal(store.settings.name,'');assert.equal(sessionState.status,'error');
});
test('an expired same-origin session opens sign-in; network failures do not redirect',async()=>{
 const original=globalThis.location,redirects=[];
 const origin=new URL(API_BASE_URL).origin;
 globalThis.location={origin,protocol:new URL(origin).protocol,pathname:'/',search:'',hash:'#employees',replace:url=>redirects.push(url)};
 try{
  Object.assign(dataSource,createHostedApiProvider({fetchImpl:async()=>json({detail:'Not signed in'},401)}));await loadSession();
  assert.equal(redirects.length,1);const login=new URL(redirects[0]);assert.equal(login.origin,origin);assert.equal(login.pathname,'/auth/login');assert.equal(login.searchParams.get('next'),'/#employees');
  redirects.length=0;Object.assign(dataSource,createHostedApiProvider({fetchImpl:async()=>{throw Error('offline');}}));await loadSession();assert.equal(redirects.length,0);assert.equal(sessionState.status,'error');
  globalThis.location.origin='https://other.example';Object.assign(dataSource,createHostedApiProvider({fetchImpl:async()=>json({detail:'Not signed in'},401)}));await loadSession();assert.equal(redirects.length,0);
 }finally{if(original===undefined)delete globalThis.location;else globalThis.location=original;}
});
test('photo list/stats/activity errors clear data and uploads never silently retry',async()=>{
 const calls=[];Object.assign(dataSource,createHostedApiProvider({fetchImpl:async(url,options)=>{const path=new URL(url).pathname;calls.push({path,options});if(path==='/app2/stats')return json({total_photos:1,total_bytes:10});if(path==='/app2/photos')return json({items:[photo],total:1,offset:0,limit:200});if(path==='/app2/activity')return json({items:[],total:0,offset:0,limit:500});if(path==='/app2/upload')throw new TypeError('lost reply');throw Error('Unexpected endpoint');}}));
 await loadPhotos(true);assert.equal(photoData.status,'ready');assert.equal(photoData.items[0].id,'5');assert.equal(photoData.items[0].url,new URL('/app2/photos/5/file',API_BASE_URL).href);
 const file=new File(['image'],'test.png',{type:'image/png'});await assert.rejects(uploadPhoto(file,{},'Account Tester'),e=>e.uncertain);assert.equal(photoUpload.uncertain,true);await assert.rejects(uploadPhoto(file,{},'Account Tester'),/not been confirmed/);assert.equal(calls.filter(c=>c.path==='/app2/upload').length,1);await loadPhotos(true);allowPhotoRetry();assert.equal(photoUpload.uncertain,false);
 Object.assign(dataSource,createHostedApiProvider({fetchImpl:async()=>json({detail:'Photo service unavailable'},500)}));await loadPhotos(true);assert.equal(photoData.status,'error');assert.deepEqual(photoData.items,[]);assert.deepEqual(photoData.activity,[]);
});
test('a confirmed upload is sent once, preserves multipart metadata and refreshes real list data',async()=>{
 let finish,posts=0;
 Object.assign(dataSource,createHostedApiProvider({fetchImpl:async(url,options)=>{const path=new URL(url).pathname;if(options.method==='POST'){posts++;assert.equal(options.body.get('display_name'),'Inspection');assert.equal(options.body.get('tags'),'site, team');assert.equal(options.headers['Content-Type'],undefined);return new Promise(resolve=>finish=()=>resolve(json(photo,201)));}if(path.endsWith('/stats'))return json({total_photos:1,total_bytes:10});return json({items:path.endsWith('/photos')?[photo]:[],total:path.endsWith('/photos')?1:0,offset:0,limit:200});}}));
 const file=new File(['image'],'test.png',{type:'image/png'}),pending=uploadPhoto(file,{display_name:'Inspection',tags:'site, team'},'Account Tester');
 await assert.rejects(uploadPhoto(file,{},'Account Tester'),/already in progress/);finish();const result=await pending;
 assert.equal(posts,1);assert.equal(result.id,'5');assert.equal(photoData.items[0].owner,'Account Tester');assert.equal(photoData.status,'ready');assert.equal(photoUpload.busy,false);
});
test('camera timestamp preparation draws the Manila timestamp and returns a JPEG for upload',async()=>{
 const draws=[],canvas={width:0,height:0,getContext:()=>({fillRect(){},drawImage(...args){draws.push(['image',...args]);},measureText:()=>({width:400}),fillText:text=>draws.push(['timestamp',text])}),toBlob:fn=>fn(new Blob(['encoded-jpeg'],{type:'image/jpeg'}))};
 const context={document:{createElement:()=>canvas},window:{addEventListener(){}},createImageBitmap:async()=>({width:4800,height:3600,close(){}}),File,Blob,Date};
 const source=fs.readFileSync(new URL('../src/photo-camera.js',import.meta.url),'utf8').replace(/^import .*;\s*$/gm,'').replace(/\bexport\s+/g,'');
 vm.runInNewContext(source+'\nglobalThis.prepare=stampedPhoto;',context);
 const file=await context.prepare(new File(['raw'],'camera.png',{type:'image/png'}),new Date('2026-10-30T00:00:00Z'));
 assert.equal(canvas.width,2400);assert.equal(canvas.height,1800);assert.equal(file.name,'camera-timestamp.jpg');assert.equal(file.type,'image/jpeg');assert.ok(file.size>0);assert.match(draws.find(row=>row[0]==='timestamp')[1],/Oct 30, 2026.*8:00 AM/);
});
