import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import http from 'node:http';
import {once} from 'node:events';

const read=name=>fs.readFileSync(new URL('../'+name,import.meta.url),'utf8');
const config=read('config.js'),html=read('index.html');
const configuredBase=config.match(/const BASE_URL = '([^']+)'/)[1];
const withBase=url=>config.replace(configuredBase,url);
// Run the API transport from the actual build, without starting the UI.
const bundled=html.match(/<script>\n([\s\S]*?)\n<\/script>/)[1];
const transport=bundled.slice(0,bundled.indexOf('const {dataSource,sourceLabel,sourceNotice}='));

function setup(source=config,fetchImpl=async()=>new Response('{"items":[]}',{headers:{'Content-Type':'application/json'}})){
 const policies=[];
 const context={URL,AbortController,setTimeout,clearTimeout,fetch:fetchImpl,document:{createElement:()=>({}),head:{appendChild:meta=>policies.push(meta)}}};
 vm.runInNewContext(source,context);
 vm.runInNewContext(transport+'\nglobalThis.client=createHostedApiProvider();',context);
 return {context,policies};
}

test('runtime config targets the selected server and sets its connection policy',async()=>{
 const calls=[],{context,policies}=setup(config,async(url,options)=>{calls.push({url,options});return new Response('{"items":[]}',{headers:{'Content-Type':'application/json'}});});
 await context.client.request({path:'/employees',query:{limit:50,offset:0}});
 assert.equal(context.NORTHPOINT_CONFIG.BASE_URL,new URL(configuredBase).href.replace(/\/+$/,'')+'/');
 assert.equal(calls[0].url,context.NORTHPOINT_CONFIG.BASE_URL+'employees?limit=50&offset=0');
 assert.equal(calls[0].options.credentials,'same-origin');
 assert.equal(policies[0].httpEquiv,'Content-Security-Policy');
 assert.ok(policies[0].content.includes("connect-src 'self' "+context.NORTHPOINT_CONFIG.BASE_URL+' '));
 assert.ok(!html.includes('cs317.duckdns.org'));assert.ok(!html.includes('http://localhost:8081/app1'));
});

test('editing config alone changes existing bundled requests and CSP without rebuilding',async()=>{
 const changed=withBase('https://api.example.test/hr///'),calls=[];
 const {context,policies}=setup(changed,async(url,options)=>{calls.push({url,options});return new Response('{}',{headers:{'Content-Type':'application/json'}});});
 await context.client.request({path:'/activity/calendar',query:{start:'2026-10-01',end:'2026-10-31'}});
 await context.client.request({path:'/employees/5',method:'PATCH',actor:'Config Test',body:{first_name:'Updated'}});
 assert.equal(calls[0].url,'https://api.example.test/hr/activity/calendar?start=2026-10-01&end=2026-10-31');
 assert.equal(calls[1].url,'https://api.example.test/hr/employees/5');
 assert.equal(calls[1].options.headers['X-Actor'],'Config Test');
 assert.deepEqual(JSON.parse(calls[1].options.body),{first_name:'Updated'});
 assert.ok(policies[0].content.includes("connect-src 'self' https://api.example.test/hr/ "));
 assert.equal(read('index.html'),html,'The build was not rewritten.');
});

test('invalid API addresses are rejected rather than silently falling back to another server',()=>{
 for(const url of ['file:///tmp/app1','ftp://example.test/app1','https://user:password@example.test/app1','https://example.test/app1?debug=1','https://example.test/app1#debug',"https://example.test/app1/;connect-src *"]){
  assert.throws(()=>setup(withBase(url)));
 }
});

test('local HTTP transport sends real HTTP requests to configured paths without changing payloads',async t=>{
 const received=[];
 const server=http.createServer(async(req,res)=>{
  let body='';for await(const chunk of req)body+=chunk;
  received.push({url:req.url,method:req.method,actor:req.headers['x-actor'],body:body?JSON.parse(body):null});
  res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({ok:true}));
 });
 server.listen(0,'127.0.0.1');await once(server,'listening');
 t.after(()=>new Promise(resolve=>{server.close(resolve);server.closeAllConnections();}));
 const origin=`http://127.0.0.1:${server.address().port}`;
 const {context}=setup(withBase(origin+'/app1/'),fetch);
 await context.client.request({path:'/employees',query:{limit:50,offset:0}});
 await context.client.request({path:'/employees/5',method:'PATCH',actor:'Config Test',body:{department:'Operations'}});
 assert.deepEqual(received,[{url:'/app1/employees?limit=50&offset=0',method:'GET',actor:undefined,body:null},{url:'/app1/employees/5',method:'PATCH',actor:'Config Test',body:{department:'Operations'}}]);
});
