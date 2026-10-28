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

test('built standalone works offline, renders all views and never persists or saves records',async t=>{
  const html=fs.readFileSync(new URL('../index.html',import.meta.url),'utf8');
  assert.ok(html.includes("connect-src 'none'"));
  const script=html.match(/<script>\n([\s\S]*?)\n<\/script>/)[1];
  const events={},nodes=new Map();let networkCalls=0,storageCalls=0;
  function element(selector){if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:'',open:false,isConnected:true,dataset:{},elements:{},checked:true,disabled:false,addEventListener(){},setAttribute(){},focus(){},scrollIntoView(){},getClientRects:()=>[],classList:{toggle(){},contains:()=>false,remove(){},add(){}},querySelector:element,querySelectorAll:()=>[],showModal(){this.open=true;},close(){this.open=false;}});return nodes.get(selector);}
  class Form{constructor(id,values){this.id=id;this.dataset={};this.values=values;this.elements=Object.fromEntries(Object.entries(values).map(([name,value])=>[name,{name,value,disabled:false}]));}querySelector=element;querySelectorAll(){return [];}setAttribute(){}reportValidity(){return true;}}
  const context={document:{querySelector:element,querySelectorAll:()=>[],getElementById:id=>element('#'+id),addEventListener:(name,fn)=>events[name]=fn,body:element('body'),documentElement:{dataset:{}},hidden:false},window:{addEventListener(){},scrollTo(){}},navigator:{onLine:false},location:{hash:'#dashboard'},fetch(){networkCalls++;throw Error('Network forbidden');},URL,DOMException,AbortController,queueMicrotask,HTMLFormElement:Form,FormData:class{constructor(form){return Object.entries(form.values);}},matchMedia:()=>({matches:false}),setTimeout,clearTimeout,setInterval(){},console};
  for(const key of ['localStorage','sessionStorage','indexedDB'])Object.defineProperty(context,key,{get(){storageCalls++;throw Error('Persistence forbidden');}});
  vm.runInNewContext(script+'\nglobalThis.fixture={store,resources,employeeDirectory,route,filters,render,employeeForm,employeeProfile,saveStore};',context);
  const ui=context.fixture,body=()=>element('#app').innerHTML,wait=()=>new Promise(resolve=>setTimeout(resolve,450));await wait();await wait();
  await t.test('dashboard has preview branding and actual example totals while offline',()=>{assert.equal(ui.store.employees.length,12);assert.equal(ui.store.violations.length,19);assert.ok(body().includes('Fictional records'));assert.ok(body().includes('Recent Activity'));assert.ok(body().includes('Department Rollup'));assert.ok(!body().includes('Live backend data'));});
  await t.test('every main navigation view renders without a backend',async()=>{
    for(const [hash,title] of [['employees','Employee directory'],['violations','Violation records'],['types','Violation categories'],['history','Activity Logs'],['reports','Daily Activity'],['users','Coming Soon'],['settings','Your Preferences'],['help','How Can We Help?']]){context.location.hash='#'+hash;ui.route();await wait();assert.ok(body().includes(title),hash);}
  });
  await t.test('profile and add/edit employee forms render from the same adapter',async()=>{
    context.location.hash='#employee/api/101';ui.route();await wait();assert.ok(body().includes('Alex Example'));assert.equal(ui.employeeProfile.status,'ready');
    await ui.employeeForm();assert.ok(element('#modal').innerHTML.includes('First name'));assert.ok(element('#modal').innerHTML.includes('No department assigned'));
    await ui.employeeForm('api/101');assert.ok(element('#modal').innerHTML.includes('Alex'));assert.ok(element('#modal').innerHTML.includes('Save Changes'));
  });
  await t.test('employee form submission keeps the draft and does not invent a saved record',async()=>{
    const form=new Form('employee-form',{employee_code:'PREVIEW-DRAFT',firstName:'Unsaved',lastName:'Example',department:'',position:''});
    await events.submit({target:form,preventDefault(){}});assert.equal(ui.store.employees.length,12);assert.equal(form.elements.firstName.value,'Unsaved');assert.equal(ui.store.employees.some(employee=>employee.id==='PREVIEW-DRAFT'),false);assert.match(element('.form-error').textContent,/UI-only preview/);
  });
  await t.test('all reports and both history tabs remain available',()=>{
    context.location.hash='#reports';ui.route();for(const tab of ['activity','offenders','watchlist','departments','rulebook','clean']){ui.filters.reports={tab};ui.render();assert.ok(body().includes('id="report-panel"'),'report panel '+tab);assert.doesNotMatch(body(),/>\s*NaN\s*<|(?:height|width|value)="NaN"/,'finite report values '+tab);}
    context.location.hash='#history';ui.route();for(const tab of ['activity','removals']){ui.filters.history={tab};ui.render();assert.ok(body().includes(tab==='activity'?'Activity Logs':'Removal Logs'));assert.ok(body().includes('history-table-scroll'));}
  });
  await t.test('record data and preferences never reach browser storage or the network',()=>{ui.saveStore();assert.equal(networkCalls,0);assert.equal(storageCalls,0);});
});
