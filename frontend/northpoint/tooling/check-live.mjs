// Read-only smoke check. No POST/PATCH/DELETE and no employee data written to disk.
import assert from 'node:assert/strict';
import {refreshWorkspace,resources,loadActiveTypes} from '../src/backend.js';
import {employeeDirectory} from '../src/employee-api.js';
import {fetchEmployeeProfile} from '../src/employee-details.js';
import {apiRequest} from '../src/api-client.js';
import {createCalendarService} from '../src/calendar-api.js';
import {API_BASE_URL} from '../src/hosted-api.js';
await refreshWorkspace();await loadActiveTypes(true);
assert.equal(employeeDirectory.status,'ready',employeeDirectory.error);
for(const [name,resource] of Object.entries(resources))assert.equal(resource.status,'ready',name+': '+resource.error);
if(employeeDirectory.items.length){const employee=employeeDirectory.items[0],profile=await fetchEmployeeProfile(employee.apiId);assert.equal(profile.employee.apiId,employee.apiId);}
if(resources.types.items.length){const type=await apiRequest('/violation-types/'+resources.types.items[0].id);assert.equal(typeof type.is_active,'boolean');}
if(resources.records.items.length){const record=await apiRequest('/violations/'+resources.records.items[0].id);assert.equal(String(record.id),resources.records.items[0].id);}
if(resources.removals.items.length){const removal=await apiRequest('/violation-removals/'+resources.removals.items[0].id);assert.equal(String(removal.id),resources.removals.items[0].id);}
const calendar=createCalendarService(),today=new Date().toISOString().slice(0,10);
await calendar.loadMonth(today.slice(0,7));assert.equal(calendar.monthState.status,'ready',calendar.monthState.error);
const active=calendar.monthState.data.filter(row=>row.total>0).at(-1),date=active?.date||today;
await calendar.loadDay(date);assert.equal(calendar.dayState.status,'ready',calendar.dayState.error);if(active)assert.equal(calendar.dayState.data.total,active.total);
const preflight=await fetch(API_BASE_URL+'/employees/1',{method:'OPTIONS',headers:{Origin:'http://localhost:4173','Access-Control-Request-Method':'PATCH','Access-Control-Request-Headers':'content-type,x-actor'},signal:AbortSignal.timeout(15000)});
assert.ok(preflight.ok);assert.match(preflight.headers.get('access-control-allow-headers')||'',/x-actor/i);assert.match(preflight.headers.get('access-control-allow-methods')||'',/PATCH/);
console.log(JSON.stringify({employees:employeeDirectory.total,resources:Object.fromEntries(Object.entries(resources).map(([name,r])=>[name,r.items.length])),calendar:'ready',digestEvents:calendar.dayState.data.total,corsPreflight:preflight.status,writesSent:0},null,2));
