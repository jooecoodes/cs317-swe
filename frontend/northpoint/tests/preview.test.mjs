import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createPreviewProvider} from '../src/preview-provider.js';
import {previewFixtures} from '../src/preview-fixtures.js';
import {apiRequest,paginatedApi} from '../src/api-client.js';
import {fetchApiEmployees,createApiEmployee,employeeDirectory} from '../src/employee-api.js';
import {fetchEmployeeProfile,patchEmployee,changeEmployeeState} from '../src/employee-details.js';
import {saveType,changeType,issueViolation,updateViolation,deleteViolation} from '../src/mutations.js';
import {refreshWorkspace,resources,normalizeViolation,normalizeRemoval,normalizeType,normalizeActivity} from '../src/backend.js';
import {store} from '../src/data.js';
import {API_BASE_URL} from '../src/hosted-api.js';
import {dataSource} from '../src/data-source.js';
Object.assign(dataSource,createPreviewProvider());

test('preview reads have the backend contract and internally consistent totals',async()=>{
  const source=createPreviewProvider({delayMs:0});
  const result=await source.request({path:'/employees',query:{include_inactive:true,limit:8}});
  assert.equal(result.total,12);assert.equal(result.items.length,8);assert.equal(result.offset,0);
  const second=await source.request({path:'/employees',query:{include_inactive:true,offset:8,limit:8}});
  assert.equal(second.items.length,4);assert.equal(new Set([...result.items,...second.items].map(row=>row.id)).size,12);
  for(const employee of previewFixtures.employees){const rows=previewFixtures.violations.filter(row=>row.employee_id===employee.id);assert.equal(employee.total_points,rows.reduce((total,row)=>total+row.points,0));assert.equal(employee.total_strikes,rows.filter(row=>row.is_strike).length);}
  const active=await source.request({path:'/employees'});assert.equal(active.total,10);
});

test('all record-changing UI actions are blocked without altering fictional records',async()=>{
  const before=JSON.stringify(previewFixtures);
  const payload={employee_code:'PREVIEW-NEW',first_name:'New',last_name:'Example',department:null,position:null};
  const actions=[
    ()=>createApiEmployee(payload,'Preview User'),()=>patchEmployee(101,{first_name:'Changed'},'Preview User'),
    ...['deactivate','reactivate','delete'].map(action=>()=>changeEmployeeState(101,action,'Preview User')),
    ()=>saveType(null,{name:'Example',description:'Example description',points:2,strike:'on'},'Preview User'),
    ()=>saveType(1,{name:'Example',description:'Example description',points:2},'Preview User'),
    ...['activate','deactivate','delete'].map(action=>()=>changeType(1,action,'Preview User')),
    ()=>issueViolation(101,{typeId:'1',description:'Example',recordedBy:'Preview User'},'Preview User'),
    ()=>updateViolation(1001,{description:'Example',recordedBy:'Preview User'},'Preview User'),
    ()=>deleteViolation(1001,'Example removal reason','Preview User')
  ];
  for(const action of actions)await assert.rejects(action,error=>error.code==='preview-only'&&error.uncertain===false&&/UI-only preview/.test(error.message));
  assert.equal(JSON.stringify(previewFixtures),before);
});

test('preview responses are independent copies; unknown records never fabricate data',async()=>{
  const source=createPreviewProvider({delayMs:0});
  const row=await source.request({path:'/employees/101'});row.full_name='Changed';row.violation_records.length=0;
  const fresh=await source.request({path:'/employees/101'});assert.equal(fresh.full_name,'Alex Example');assert.equal(fresh.violation_records.length,3);
  await assert.rejects(source.request({path:'/employees/999999'}),error=>error.status===404);
  await assert.rejects(source.request({path:'/missing'}),error=>error.status===404);
});

test('empty, error, loading and cancellation states can be reviewed independently',async()=>{
  const empty=createPreviewProvider({scenario:'empty',delayMs:0});assert.deepEqual((await empty.request({path:'/employees'})).items,[]);
  const error=createPreviewProvider({scenario:'error',delayMs:0});await assert.rejects(error.request({path:'/employees'}),/Preview error state/);
  const source=createPreviewProvider({delayMs:50}),controller=new AbortController();let completed=false;
  const pending=source.request({path:'/employees',signal:controller.signal}).then(()=>{completed=true;});assert.equal(completed,false);controller.abort();await assert.rejects(pending,error=>error.name==='AbortError');
});

test('view adapters load every resource from the provider without network access',async()=>{
  const fetchBefore=globalThis.fetch;globalThis.fetch=()=>{throw new Error('Unexpected network request');};
  try{
    await refreshWorkspace();assert.equal(store.employees.length,12);assert.equal(store.violations.length,19);
    for(const name of ['records','types','removals','timeline','recent'])assert.equal(resources[name].status,'ready',name);
    const directory=await fetchApiEmployees();assert.equal(directory.total,12);
    const profile=await fetchEmployeeProfile(101);assert.equal(profile.employee.name,'Alex Example');assert.equal(profile.violations.length,3);
    assert.equal((await paginatedApi('/employees',{query:{include_inactive:true}})).length,12);
    for(const item of previewFixtures.types)normalizeType(item);
    for(const item of previewFixtures.removals)normalizeRemoval(item);
    for(const item of previewFixtures.activities)normalizeActivity(item);
    for(const item of previewFixtures.violations)normalizeViolation(item,employeeDirectory.items);
    await assert.rejects(apiRequest('/not-in-contract'),/API contract/);
  }finally{globalThis.fetch=fetchBefore;}
});

test('built frontend uses the real transport to render supplied API responses without persistence',async t=>{
  const html=fs.readFileSync(new URL('../index.html',import.meta.url),'utf8');
  assert.ok(html.includes('<script src="./config.js"></script>'));assert.ok(!html.includes('const previewFixtures'));
  const script=html.match(/<script>\n([\s\S]*?)\n<\/script>/)[1];
  const events={},nodes=new Map();let networkCalls=0,storageCalls=0;
  function element(selector){if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:'',open:false,isConnected:true,dataset:{},elements:{},checked:true,disabled:false,addEventListener(){},setAttribute(){},focus(){},scrollIntoView(){},getClientRects:()=>[],classList:{toggle(){},contains:()=>false,remove(){},add(){}},querySelector:element,querySelectorAll:()=>[],showModal(){this.open=true;},close(){this.open=false;}});return nodes.get(selector);}
  class Form{constructor(id,values){this.id=id;this.dataset={};this.values=values;this.elements=Object.fromEntries(Object.entries(values).map(([name,value])=>[name,{name,value,disabled:false}]));}querySelector=element;querySelectorAll(){return [];}setAttribute(){}reportValidity(){return true;}}
  const fixtureHttpSource=createPreviewProvider();
  const context={document:{createElement:()=>({}),head:{appendChild(){}},querySelector:element,querySelectorAll:()=>[],getElementById:id=>element('#'+id),addEventListener:(name,fn)=>events[name]=fn,body:element('body'),documentElement:{dataset:{}},hidden:false},window:{addEventListener(){},scrollTo(){}},navigator:{onLine:false},location:{hash:'#dashboard'},async fetch(url,options){networkCalls++;const parsed=new URL(url);assert.equal(parsed.origin,new URL(API_BASE_URL).origin);assert.equal(options.credentials,'same-origin');if(parsed.pathname==='/auth/me')return new Response(JSON.stringify({username:'Signed In Tester'}),{headers:{'Content-Type':'application/json'}});if(parsed.pathname==='/app2/photos'||parsed.pathname==='/app2/activity')return new Response(JSON.stringify({items:[],total:0,limit:Number(parsed.searchParams.get('limit')),offset:0}),{headers:{'Content-Type':'application/json'}});if(parsed.pathname==='/app2/stats')return new Response(JSON.stringify({total_photos:0,total_bytes:0}),{headers:{'Content-Type':'application/json'}});assert.ok(parsed.pathname.startsWith('/app1/'));try{const data=await fixtureHttpSource.request({path:parsed.pathname.replace('/app1',''),method:options.method,query:Object.fromEntries(parsed.searchParams),signal:options.signal});return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});}catch(error){return new Response(JSON.stringify({detail:error.message}),{status:error.code==='preview-only'?403:error.status||500,headers:{'Content-Type':'application/json'}});}},URL,DOMException,AbortController,queueMicrotask,HTMLFormElement:Form,FormData:class{constructor(form){return Object.entries(form.values);}},matchMedia:()=>({matches:false}),setTimeout,clearTimeout,setInterval(){},console};
  for(const key of ['localStorage','sessionStorage','indexedDB'])Object.defineProperty(context,key,{get(){storageCalls++;throw Error('Persistence forbidden');}});
  vm.runInNewContext(fs.readFileSync(new URL('../config.js',import.meta.url),'utf8'),context);
  vm.runInNewContext(script+'\nglobalThis.fixture={store,resources,employeeDirectory,route,filters,render,employeeForm,employeeProfile,saveStore};',context);
  const ui=context.fixture,body=()=>element('#app').innerHTML,wait=()=>new Promise(resolve=>setTimeout(resolve,450));await wait();await wait();
  await t.test('dashboard has the requested version label and simplified footer',()=>{assert.equal(ui.store.employees.length,12);assert.equal(ui.store.violations.length,19);assert.ok(body().includes('v.FE-1.0'));assert.ok(!body().includes('Fictional records'));assert.ok(!body().includes('UI preview'));assert.ok(!body().includes('People. Clarity. Accountability.'));assert.match(body(),/<footer class="page-footer"><span>[\s\S]*?Northpoint<\/span><\/footer>/);assert.ok(body().includes('Recent Activity'));assert.ok(body().includes('Department Rollup'));assert.ok(!body().includes('Live backend data'));});
  await t.test('dashboard shortcuts expose the existing violation, employee and camera actions',async()=>{
    assert.ok(body().includes('What would you like to do?'));assert.ok(body().includes('Issue Violation'));assert.ok(body().includes('Add Employee'));assert.ok(body().includes('Timestamp Camera'));
    const click=dataset=>events.click({target:{closest:()=>({dataset})}});
    await click({action:'record'});assert.ok(element('#modal').innerHTML.includes('Record New Violation'));
    await click({action:'add-employee'});assert.ok(element('#modal').innerHTML.includes('Add Employee'));
    await click({action:'navigate',page:'camera'});ui.route();assert.ok(body().includes('Timestamp Camera'));
    context.location.hash='#dashboard';ui.route();
  });
  await t.test('every main navigation view renders without a backend',async()=>{
    for(const [hash,title] of [['employees','Employee directory'],['violations','Violation records'],['types','Violation categories'],['photos','Employee photos'],['camera','Your photo will appear here'],['history','Activity Logs'],['reports','Daily Activity'],['users','Coming Soon'],['settings','Your Preferences'],['help','How Can We Help?']]){context.location.hash='#'+hash;ui.route();await wait();assert.ok(body().includes(title),hash);if(hash==='settings'){assert.ok(body().includes('Signed In Tester'));assert.ok(!body().includes('Your display name'));}}
  });
  await t.test('Photo Library uploads require an image and activity stays inside its tabs',async()=>{
    const before=networkCalls;context.location.hash='#photos';ui.route();assert.match(body(),/data-action="navigate" data-page="photos"/);assert.ok(body().includes('Violation Management'));assert.ok(body().includes('Employee photos'));assert.equal(ui.store.settings.name,'Signed In Tester');assert.ok(!body().includes('vs yesterday'));
    await events.click({target:{closest:()=>({dataset:{action:'photo-add'}})}});assert.ok(element('#modal').innerHTML.includes('Upload Photo'));assert.ok(element('#modal').innerHTML.includes('photo-upload-form'));
    const form=new Form('photo-upload-form',{name:'Unsaved image',description:'',tags:''});await events.submit({target:form,preventDefault(){}});assert.equal(element('#photo-error').textContent,'Choose a photo first.');assert.equal(networkCalls,before);
  });
  await t.test('profile and add/edit employee forms render from the same adapter',async()=>{
    context.location.hash='#employee/api/101';ui.route();await wait();assert.ok(body().includes('Alex Example'));assert.equal(ui.employeeProfile.status,'ready');
    await ui.employeeForm();assert.ok(element('#modal').innerHTML.includes('First name'));assert.ok(element('#modal').innerHTML.includes('No department assigned'));
    await ui.employeeForm('api/101');assert.ok(element('#modal').innerHTML.includes('Alex'));assert.ok(element('#modal').innerHTML.includes('Save Changes'));
  });
  await t.test('employee form submission keeps the draft and does not invent a saved record',async()=>{
    ui.store.settings.name='UI Test Actor';const form=new Form('employee-form',{employee_code:'PREVIEW-DRAFT',firstName:'Unsaved',lastName:'Example',department:'',position:''});
    await events.submit({target:form,preventDefault(){}});assert.equal(ui.store.employees.length,12);assert.equal(form.elements.firstName.value,'Unsaved');assert.equal(ui.store.employees.some(employee=>employee.id==='PREVIEW-DRAFT'),false);assert.match(element('.form-error').textContent,/UI-only preview/);
  });
  await t.test('all reports and both history tabs remain available',()=>{
    context.location.hash='#reports';ui.route();for(const tab of ['activity','offenders','watchlist','departments','rulebook','clean']){ui.filters.reports={tab};ui.render();assert.ok(body().includes('id="report-panel"'),'report panel '+tab);assert.doesNotMatch(body(),/>\s*NaN\s*<|(?:height|width|value)="NaN"/,'finite report values '+tab);}
    context.location.hash='#history';ui.route();for(const tab of ['activity','removals']){ui.filters.history={tab};ui.render();assert.ok(body().includes(tab==='activity'?'Activity Logs':'Removal Logs'));assert.ok(body().includes('history-table-scroll'));}
  });
  await t.test('record data and preferences never reach browser storage',()=>{ui.saveStore();assert.ok(networkCalls>0);assert.equal(storageCalls,0);});
  await t.test('Calendar tab opens a daily summary through the actual bundled event handlers',async()=>{
    context.location.hash='#history';ui.route();ui.filters.history={tab:'calendar'};ui.render();assert.ok(body().includes('Loading calendar activity'));
    await wait();assert.ok(body().includes('calendar-grid'));assert.ok(body().includes('More changes'));
    const dateButtons=[...body().matchAll(/<button[^>]+class="calendar-day[^>]*>([\s\S]*?)<\/button>/g)];assert.ok(dateButtons.length>=28);
    for(const [,content] of dateButtons)assert.match(content.replace(/<[^>]*>/g,''),/^\d{1,2}$/);
    assert.ok(!body().includes('class="calendar-day-count"'));
    const date=new Date().toISOString().slice(0,10),day={dataset:{action:'sec-calendar-day',date},id:'calendar-day-'+date};
    await events.click({target:{closest:()=>day}});assert.ok(element('#modal').innerHTML.includes('Daily Summary'));assert.ok(element('#modal').innerHTML.includes('By person'));assert.ok(!element('#modal').innerHTML.includes('[object Object]'));
    const next={dataset:{action:'sec-calendar-month',step:'1'},id:'calendar-next'};await events.click({target:{closest:()=>next}});await wait();assert.notEqual(ui.filters.history.month,date.slice(0,7));
    const today={dataset:{action:'sec-calendar-today'},id:'calendar-today'};await events.click({target:{closest:()=>today}});await wait();assert.equal(ui.filters.history.month,date.slice(0,7));assert.ok(networkCalls>0);assert.equal(storageCalls,0);
  });
});
