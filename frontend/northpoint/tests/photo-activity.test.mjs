import test from 'node:test';
import assert from 'node:assert/strict';
import {createPhotoActivity,photoActivityService,fetchPhotoHistory,fetchPhotoBatch} from '../src/photo-activity.js';
import {renderPhotoActivity,handlePhotoActivityAction} from '../src/photo-activity-view.js';
import {photoData,loadPhotos} from '../src/photo-service.js';
import {dataSource} from '../src/data-source.js';
import {createHostedApiProvider} from '../src/hosted-api.js';
const event={id:1,actor:'Test Actor',action:'upload',photo_id:5,photo_display_name:'Site',created_at:'2026-10-30T10:00:00'};
const digest={from_date:'2026-10-01',to_date:'2026-10-31',total:1,summary:'One upload this month.',days:[{date:'2026-10-30',total:1,summary:'Test Actor uploaded a photo.'}]};
const digestFor=query=>({...digest,from_date:query.from_date,to_date:query.to_date,days:digest.days.filter(day=>day.date>=query.from_date&&day.date<=query.to_date)});
const actors={actors:[{actor:'Test Actor',total:1,actions:{upload:1},last_seen:event.created_at}]};
const response=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const esc=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const ctx={esc,icon:()=>'',formatDate:String};
function requestFor(calls,total=17){return async(path,options)=>{
 calls.push({path,...options});
 if(path==='/activity/digest')return digestFor(options.query);
 if(path==='/activity/actors')return actors;
 const offset=options.query.offset;return {items:Array.from({length:Math.max(0,Math.min(8,total-offset))},(_,i)=>({...event,id:offset+i+1})),total,offset,limit:8};
};}
test('activity uses bounded server pages and matching date/search/actor/action filters',async()=>{
 const calls=[],service=createPhotoActivity(requestFor(calls));
 await service.load({month:'2026-10',day:'2026-10-30',page:2,q:'site',actor:'Test Actor',action:'upload'});
 assert.equal(service.state.status,'ready');assert.equal(service.state.items.length,8);assert.equal(service.state.total,17);
 assert.deepEqual(calls[0].query,{q:'site',actor:'Test Actor',action:'upload',limit:8,offset:8,from_date:'2026-10-30',to_date:'2026-10-30'});
 assert.deepEqual(calls[1].query,{q:'site',actor:'Test Actor',action:'upload',from_date:'2026-10-01',to_date:'2026-10-31',include_items:false});
 assert.equal(calls.length,3);assert.equal(service.state.digest.summary,digest.summary);assert.deepEqual(service.state.actors,actors.actors);
 await service.load({month:'2026-02',day:'',page:1,q:'',actor:'',action:''});
 assert.equal(calls[4].query.to_date,'2026-02-28');assert.equal(calls[3].query.from_date,undefined);
});
test('rapid filter changes abort older reads and ignore their late responses',async()=>{
 let finish;const calls=[];
 const service=createPhotoActivity(async(path,options)=>{
  calls.push({path,...options});
  if(path==='/activity'&&options.query.q==='old')return await new Promise(resolve=>finish=()=>resolve({items:[event],total:1,offset:0,limit:8}));
  if(path==='/activity')return {items:[],total:0,offset:0,limit:8};
  return path==='/activity/digest'?{...digestFor(options.query),total:0,days:[]}:actors;
 });
 const old=service.load({q:'old'});await service.load({q:'new'});assert.equal(calls[0].signal.aborted,true);finish();await old;
 assert.equal(service.state.q,'new');assert.equal(service.state.total,0);assert.deepEqual(service.state.items,[]);
});
test('API failures and malformed summaries clear old data and support retry',async()=>{
 let fail=false,malformed=false;const base=requestFor([],1),service=createPhotoActivity(async(path,options)=>{
  if(fail)throw Error('Session expired');if(malformed&&path==='/activity/digest')return {summary:'invalid'};return base(path,options);
 });
 await service.load();fail=true;await service.load({actor:'Test Actor'});
 assert.equal(service.state.status,'error');assert.match(service.state.error,/Session expired/);assert.deepEqual(service.state.items,[]);assert.equal(service.state.digest,null);
 fail=false;malformed=true;await service.load({},true);assert.match(service.state.error,/invalid activity summary/);
 malformed=false;await service.load();assert.equal(service.state.status,'ready');assert.equal(service.state.actor,'Test Actor');
});
test('a deleted last page is clamped by fetching the remaining server page',async()=>{
 const calls=[],service=createPhotoActivity(requestFor(calls,1));await service.load({page:3});
 assert.equal(service.state.page,1);assert.equal(service.state.items.length,1);assert.deepEqual(calls.filter(x=>x.path==='/activity').map(x=>x.query.offset),[16,0]);
});
test('pagination reuses summary and actor reads, while an explicit refresh reloads them',async()=>{
 const calls=[],service=createPhotoActivity(requestFor(calls));await service.load();await service.load({page:2});
 assert.equal(calls.filter(x=>x.path==='/activity').length,2);assert.equal(calls.filter(x=>x.path==='/activity/digest').length,1);assert.equal(calls.filter(x=>x.path==='/activity/actors').length,1);
 await service.load({},true);assert.equal(calls.filter(x=>x.path==='/activity/digest').length,2);assert.equal(calls.filter(x=>x.path==='/activity/actors').length,2);
});
test('photo library initial load never downloads the activity history',async()=>{
 const calls=[];Object.assign(dataSource,{async request({path}){calls.push(path);if(path==='/stats')return {total_photos:0,total_bytes:0};if(path==='/photos')return {items:[],total:0,offset:0,limit:200};throw Error('Unexpected history download');}});
 await loadPhotos(true);assert.equal(photoData.status,'ready');assert.deepEqual(calls.sort(),['/photos','/stats']);
});
test('history and read-only batch helpers send schema-defined URLs, pagination and body',async()=>{
 const calls=[];Object.assign(dataSource,createHostedApiProvider({fetchImpl:async(url,options)=>{
  calls.push({url:new URL(url),options});
  return response(options.method==='POST'?{found:[{id:5,display_name:'Site'}],missing:[9]}:{photo_id:5,photo_display_name:'Site',photo_exists:false,total:10,items:[event]});
 }}));
 const history=await fetchPhotoHistory(5,2);assert.equal(history.photo_exists,false);assert.equal(calls[0].url.pathname,'/app2/photos/5/history');assert.equal(calls[0].url.searchParams.get('offset'),'8');assert.equal(calls[0].url.searchParams.get('limit'),'8');
 const batch=await fetchPhotoBatch([5,9],'Test Actor');assert.deepEqual(batch.missing,[9]);assert.equal(calls[1].url.pathname,'/app2/photos/batch');assert.deepEqual(JSON.parse(calls[1].options.body),{ids:[5,9]});assert.equal(calls[1].options.headers['X-Actor'],'Test Actor');
 await assert.rejects(fetchPhotoBatch([],'Test Actor'));await assert.rejects(fetchPhotoBatch(Array(201).fill(1),'Test Actor'));await assert.rejects(fetchPhotoHistory('../bad'));
 assert.equal(calls.length,2);
});
test('activity renders backend totals, calendar summaries and escaped content',()=>{
 Object.assign(photoActivityService.state,{status:'ready',month:'2026-10',day:'2026-10-30',page:1,q:'<search>',actor:'',action:'',total:17,items:[{...event,actor:'<actor>',photo_display_name:'<photo>'}],actors:actors.actors,digest:{...digest,summary:'<summary>'}});
 const html=renderPhotoActivity(ctx);assert.match(html,/17 events/);assert.match(html,/Page 1 of 3/);assert.match(html,/&lt;summary>/);assert.match(html,/&lt;actor>/);assert.ok(!html.includes('<actor>'));assert.match(html,/Test Actor uploaded a photo/);assert.match(html,/photo-history/);assert.match(html,/photo-activity-filters/);
 Object.assign(photoActivityService.state,{status:'error',error:'Backend unavailable',items:[],digest:null,actors:[]});assert.match(renderPhotoActivity(ctx),/Backend unavailable/);assert.match(renderPhotoActivity(ctx),/Try Again/);
});
test('actual activity actions request backend filters and history/gallery dialogs handle deleted photos',async()=>{
 const calls=[];Object.assign(dataSource,{async request({path,query,body}){
  calls.push({path,query,body});if(path==='/activity')return {items:[event],total:1,offset:0,limit:8};if(path==='/activity/digest')return digestFor(query);if(path==='/activity/actors')return actors;
  if(path.endsWith('/history'))return {photo_id:5,photo_display_name:'Deleted <photo>',photo_exists:false,total:1,items:[event]};
  if(path==='/photos/batch')return {found:[],missing:[5]};throw Error('Unexpected route '+path);
 }});
 await handlePhotoActivityAction('photo-activity-day',{dataset:{date:'2026-10-30'}},ctx);
 assert.equal(calls[0].query.from_date,'2026-10-30');assert.equal(photoActivityService.state.status,'ready');
 const original=globalThis.document,node={innerHTML:''};globalThis.document={querySelector:()=>node};
 try{const modal={...ctx,store:{settings:{name:'Test Actor'}},openModal(){node.innerHTML='Loading';}};
  await handlePhotoActivityAction('photo-history',{dataset:{id:'5'}},modal);assert.match(node.innerHTML,/has been deleted/);assert.match(node.innerHTML,/Deleted &lt;photo>/);
  await handlePhotoActivityAction('photo-activity-gallery',{dataset:{}},modal);assert.match(node.innerHTML,/1 photo\(s\) are no longer available/);
 }finally{globalThis.document=original;}
});
