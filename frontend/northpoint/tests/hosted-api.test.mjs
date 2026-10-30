import test from 'node:test';
import assert from 'node:assert/strict';
import {createHostedApiProvider,API_BASE_URL} from '../src/hosted-api.js';
import {dataSource} from '../src/data-source.js';
import {apiRequest,paginatedApi} from '../src/api-client.js';
import {fetchApiEmployees,createApiEmployee,employeeDirectory,loadEmployeeDirectory} from '../src/employee-api.js';
import {fetchEmployeeProfile,patchEmployee,changeEmployeeState,employeeUpdatePayload} from '../src/employee-details.js';
import {saveType,changeType,issueViolation,updateViolation,deleteViolation,runMutation,pendingMutation,checkPendingMutation,clearPendingMutation} from '../src/mutations.js';
import {submitApiEmployeeForm} from '../src/employee-create.js';
import {analyticsData} from '../src/insight-data.js';
import {refreshWorkspace,resources} from '../src/backend.js';
import {store} from '../src/data.js';
const actor='Integration Tester';
const employee={id:901,employee_code:'TEST-901',first_name:'Adapter',last_name:'Test',full_name:'Adapter Test',department:null,position:null,status:'active',total_points:6,total_strikes:2,created_at:'2026-10-28T08:00:00',updated_at:'2026-10-28T08:00:00'};
const type={id:902,name:'Test Rule',description:'Test description',default_points:3,is_strike:true,is_active:true};
const violation={id:903,employee_id:901,violation_type_id:902,points:3,is_strike:true,notes:'Test notes',issued_by:actor,issued_at:'2026-10-28T08:00:00',created_at:null,violation_type:{...type},violation_type_name:type.name};
const removal={id:904,violation_record_id:903,employee_id:901,employee_code:employee.employee_code,employee_full_name:employee.full_name,violation_type_id:902,violation_type_name:type.name,points:3,is_strike:true,reason:'Test resolved incident',removed_by:actor,removed_at:'2026-10-28T09:00:00',original_notes:'Test notes'};
const json=(data,status=200)=>new Response(status===204?null:JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
function install(responder){const calls=[];Object.assign(dataSource,createHostedApiProvider({fetchImpl:async(url,options)=>{const u=new URL(url),call={path:u.pathname.replace('/app1',''),query:Object.fromEntries(u.searchParams),method:options.method,headers:options.headers,body:options.body===undefined?undefined:JSON.parse(options.body)};assert.equal(u.origin,new URL(API_BASE_URL).origin);assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');assert.equal(options.redirect,'error');calls.push(call);return responder(call,calls.length);}}));return calls;}
const page=items=>({items,total:items.length,limit:50,offset:0});
test('every referenced route targets the configured API with the correct actor requirement',async()=>{
 const source=createHostedApiProvider({fetchImpl:async(url,options)=>{assert.ok(url.startsWith(API_BASE_URL+'/'));return json({ok:true});}});
 const writes=[['/employees','POST',true],['/employees/1','PATCH',true],['/employees/1','DELETE',true],['/employees/1/deactivate','POST',true],['/employees/1/reactivate','POST',true],['/employees/1/violations','POST',true],['/violations/1','PATCH',true],['/violations/1/remove','POST',false],['/violation-types','POST',true],['/violation-types/1','PATCH',true],['/violation-types/1','DELETE',true],['/violation-types/1/activate','POST',true],['/violation-types/1/deactivate','POST',true]];
 for(const [path,method,needsActor] of writes){let sent=false;const client=createHostedApiProvider({fetchImpl:async(_url,options)=>{sent=true;assert.equal(options.headers['X-Actor'],needsActor?actor:undefined);assert.equal(options.body,undefined);return json(null,204);}});await client.request({path,method,actor});assert.ok(sent);if(needsActor)await assert.rejects(client.request({path,method}),/sign in/i);}
 for(const path of ['/employees','/employees/1','/employees/1/violations','/violations/recent','/violations/1','/violation-removals','/violation-removals/1','/violation-types','/violation-types/all','/violation-types/1','/activity/timeline','/activity/calendar','/activity/digest/2026-10-28'])await source.request({path});
 await assert.rejects(source.request({path:'//external.test/steal'}),/API contract/);await assert.rejects(source.request({path:'/analytics/invented'}),/API contract/);
});
test('employee create/profile/PATCH/state/delete payloads follow the supplied contract',async()=>{
 const calls=install(call=>{if(call.method==='DELETE')return json(null,204);return json({...employee,...call.body,status:call.path.endsWith('/deactivate')?'inactive':'active',violation_records:[violation]});});
 const created=await createApiEmployee({employee_code:employee.employee_code,first_name:'Adapter',last_name:'Test',department:null,position:null},actor);assert.equal(created.apiId,'901');assert.deepEqual(Object.keys(calls[0].body).sort(),['department','employee_code','first_name','last_name','position']);
 const profile=await fetchEmployeeProfile('901');assert.equal(profile.violations[0].createdAt,null);assert.equal(profile.violations[0].issuedAt,'2026-10-28T08:00:00Z');assert.equal(profile.violations[0].status,null);
 const payload=employeeUpdatePayload({department:'Operations',position:''},{department:'',position:'Driver'});assert.deepEqual(payload,{department:'Operations',position:null});await patchEmployee('901',payload,actor);assert.deepEqual(calls.at(-1).body,payload);
 assert.equal((await changeEmployeeState('901','deactivate',actor)).status,'Inactive');assert.equal((await changeEmployeeState('901','reactivate',actor)).status,'Active');await changeEmployeeState('901','delete',actor);assert.equal(calls.at(-1).body,undefined);
});
test('rulebook lifecycle sends only editable fields, and violations snapshot points from the response',async()=>{
 const calls=install(call=>call.method==='DELETE'?json(null,204):json(call.path.includes('violation-types')?type:call.path.endsWith('/remove')?removal:violation));
 const values={name:type.name,description:type.description,points:'3',strike:'on'};await saveType(null,values,actor);assert.deepEqual(calls.at(-1).body,{name:type.name,description:type.description,default_points:3,is_strike:true});
 await saveType(902,values,actor);assert.equal(calls.at(-1).method,'PATCH');for(const action of ['deactivate','activate','delete']){await changeType(902,action,actor);assert.equal(calls.at(-1).body,undefined);}
 const assigned=await issueViolation(901,{typeId:'902',description:' Test notes ',recordedBy:actor,date:'2026-10-28',points:999,strike:false},actor);assert.equal(assigned.points,3);assert.equal(assigned.is_strike,true);assert.deepEqual(calls.at(-1).body,{violation_type_id:902,notes:'Test notes',issued_by:actor});
 await updateViolation(903,{description:'Updated notes',recordedBy:actor},actor);assert.deepEqual(calls.at(-1).body,{notes:'Updated notes',issued_by:actor});
 await deleteViolation(903,removal.reason,actor);assert.deepEqual(calls.at(-1).body,{removed_by:actor,reason:removal.reason});assert.equal(calls.at(-1).headers['X-Actor'],undefined);
});
test('an accepted PATCH that ignores an optional-field clear is never reported as a verified update',async()=>{
 const calls=install(()=>json({...employee,department:'Unchanged department'}));await assert.rejects(patchEmployee('901',{department:null},actor),e=>e.uncertain&&e.accepted);assert.deepEqual(calls[0].body,{department:null});assert.equal(calls.length,1);
});
test('pagination loads every page and refuses duplicate IDs or incomplete totals',async()=>{
 const rows=Array.from({length:51},(_,i)=>({...employee,id:i+1,employee_code:'TEST-'+(i+1)}));const calls=install(call=>json({items:rows.slice(Number(call.query.offset),Number(call.query.offset)+50),total:51,limit:50,offset:Number(call.query.offset)}));
 assert.equal((await fetchApiEmployees()).total,51);assert.equal(calls.length,2);assert.equal(calls[0].query.include_inactive,'true');assert.equal(calls[1].query.offset,'50');
 install(call=>json({items:Array(50).fill(employee),total:51,limit:50,offset:Number(call.query.offset)}));await assert.rejects(fetchApiEmployees(),/repeated pages/);
 install(()=>json({items:[],total:1,limit:50,offset:0}));await assert.rejects(fetchApiEmployees(),/incomplete list/);
});
test('live-shaped resources calculate watchlist, clean employees and reports without synthetic cases',async()=>{
 install(call=>{switch(call.path){case '/employees':return json(page([employee,{...employee,id:905,employee_code:'TEST-905',full_name:'Clean Employee',total_points:0,total_strikes:0}]));case '/employees/901/violations':return json([violation,{...violation,id:906}]);case '/employees/905/violations':return json([]);case '/violation-types/all':return json([type]);case '/violation-removals':return json(page([removal]));case '/activity/timeline':return json(page([{id:907,occurred_at:'2026-10-28T09:00:00',actor,action:'employee.deleted',target_type:'employee',target_id:999,employee_id:null,summary:'Deleted former employee',metadata_json:{}}]));case '/violations/recent':return json([{...violation,employee:{id:901,employee_code:employee.employee_code,full_name:employee.full_name}}]);default:throw Error('Unexpected read '+call.path);}});
 await refreshWorkspace();assert.equal(employeeDirectory.status,'ready');for(const key of ['records','types','removals','timeline','recent'])assert.equal(resources[key].status,'ready',resources[key].error);
 const report=analyticsData(store.employees,store.violations,store.types);assert.equal(report.watchlist[0].totalStrikes,2);assert.equal(report.cleanEmployees.length,1);assert.equal(resources.timeline.items[0].action,'employee.deleted');assert.equal(resources.removals.items[0].violationId,'903');
 Object.assign(dataSource,createHostedApiProvider({fetchImpl:async()=>{throw new TypeError('offline');}}));await refreshWorkspace();assert.equal(employeeDirectory.status,'error');assert.deepEqual(store.employees,[]);assert.deepEqual(store.violations,[]);
});
test('HTTP errors preserve backend details, never invent a duplicate, and keep writes certain or uncertain correctly',async()=>{
 for(const status of [400,401,403,404,409,422,429,500,502]){const source=createHostedApiProvider({fetchImpl:async()=>json({detail:status===422?[{loc:['body','first_name'],msg:'Field required'}]:'Backend message',error:'BackendError'},status)});await assert.rejects(source.request({path:'/employees',method:'POST',actor,body:{}}),e=>e.status===status&&e.uncertain===(status>=500)&&(status===422?e.message==='first_name: Field required':e.message==='Backend message'));}
 const source=createHostedApiProvider({fetchImpl:async()=>json({detail:'Referenced type cannot be deleted',error:'ViolationTypeInUse'},409)});await assert.rejects(source.request({path:'/violation-types/902',method:'DELETE',actor}),e=>e.code==='conflict'&&e.backendError==='ViolationTypeInUse'&&e.message==='Referenced type cannot be deleted');
});
test('network, timeout, invalid JSON and successful-but-invalid employee writes require verification without automatic retries',async()=>{
 let calls=0;const source=createHostedApiProvider({fetchImpl:async()=>{calls++;throw new TypeError('offline');}});await assert.rejects(source.request({path:'/employees',method:'POST',actor}),e=>e.uncertain&&e.code==='network');assert.equal(calls,1);
 const timeout=createHostedApiProvider({timeoutMs:10,fetchImpl:(_url,{signal})=>new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError'))))});await assert.rejects(timeout.request({path:'/employees',method:'POST',actor}),e=>e.uncertain&&e.code==='timeout');
 const cancelled=new AbortController();cancelled.abort();await assert.rejects(source.request({path:'/employees',signal:cancelled.signal}),e=>!e.uncertain&&e.name==='AbortError');assert.equal(calls,1);
 await assert.rejects(createHostedApiProvider({fetchImpl:async()=>new Response('{',{headers:{'Content-Type':'application/json'}})}).request({path:'/employees',method:'POST',actor}),e=>e.uncertain&&e.accepted);
 install(()=>json({unexpected:true},201));await assert.rejects(createApiEmployee({employee_code:'TEST-NEW',first_name:'New',last_name:'Employee'},actor),e=>e.uncertain&&e.accepted);
 await assert.rejects(createHostedApiProvider({fetchImpl:async()=>new Response('<html>login</html>')}).request({path:'/employees'}),/instead of API data/);
});
function mutationContext(){const controls=[{disabled:false}],errors=[];return {actor,dialog:{querySelectorAll:()=>controls,querySelector:()=>null,setAttribute(){}},error:message=>errors.push(message),showPending(){},refresh:async()=>{},close(){},render(){},toast(){},controls,errors};}
test('double submissions lock controls; ambiguous writes reconcile by GET and never replay POST',async()=>{
 clearPendingMutation();const ctx=mutationContext();let writes=0,reads=0,finish;const task={execute:()=>{writes++;return new Promise(resolve=>finish=resolve);},reconcile:async()=>{reads++;return true;}};
 const pending=runMutation(task,ctx);assert.equal(ctx.controls[0].disabled,true);await runMutation(task,ctx);assert.equal(writes,1);finish();await pending;assert.equal(ctx.controls[0].disabled,false);
 const uncertain={execute:async()=>{writes++;throw Object.assign(Error('lost reply'),{uncertain:true});},reconcile:async()=>{reads++;return null;}};await runMutation(uncertain,ctx);assert.ok(pendingMutation());await runMutation(uncertain,ctx);assert.equal(writes,2);pendingMutation().task.reconcile=async()=>{reads++;return true;};await checkPendingMutation(ctx);assert.equal(writes,2);assert.equal(pendingMutation(),null);assert.equal(reads,2);
});
test('Add Employee checks all codes, confirms success by GET, and preserves a lost-response draft until GET recovery',async()=>{
 const payload={employee_code:'TEST-NEW',first_name:'New',last_name:'Employee',department:null,position:null},created={...employee,id:999,...payload,full_name:'New Employee'};let saved=false,failVerification=false,posts=0;
 install(call=>{if(call.method==='POST'){posts++;saved=true;failVerification=true;throw new TypeError('lost response');}if(failVerification)throw new TypeError('offline verification');return json(page(saved?[created]:[]));});
 const errors=[],form={dataset:{},elements:{},querySelector:()=>null,querySelectorAll:()=>[],setAttribute(){}},ctx={actor,dialog:{querySelectorAll:()=>[],querySelector:()=>null},refresh:async()=>loadEmployeeDirectory(),formError:(_form,message)=>errors.push(message),closeModal(){},resetFilters(){},render(){},toast(){}};
 const values={employee_code:payload.employee_code,firstName:payload.first_name,lastName:payload.last_name,department:'',position:''};await submitApiEmployeeForm(form,values,ctx);assert.equal(posts,1);assert.match(errors.at(-1),/not be verified/);assert.equal(employeeDirectory.status,'error');failVerification=false;await submitApiEmployeeForm(form,values,ctx);assert.equal(posts,1);assert.equal(employeeDirectory.items[0].id,payload.employee_code);
});
