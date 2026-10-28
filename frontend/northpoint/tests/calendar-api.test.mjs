import test from 'node:test';
import assert from 'node:assert/strict';
import {createCalendarService} from '../src/calendar-api.js';
import {calendarDate,calendarRange,calendarRows,calendarSummary,previewCalendarSummary} from '../src/calendar-contract.js';
import {renderCalendarDigest} from '../src/calendar.js';
import {calendarCells} from '../src/calendar-data.js';
import {createPreviewProvider} from '../src/preview-provider.js';

const date='2026-10-27';
const event={id:1,event_date:date,occurred_at:date+'T12:00:00Z',actor:'RJ45',action:'employee.created',target_type:'employee',summary:'Employee added'};
const row={date,total:1,employees:1,violations:0,violation_types:0,removals:0};
const digest=()=>({...previewCalendarSummary([event],date),highlights:['Backend highlight']});
test('monthly request uses inclusive ISO bounds and backend response counts',async()=>{
  const calls=[],service=createCalendarService(async(path,options)=>{calls.push({path,...options});return [row];});
  const pending=service.loadMonth('2026-10');assert.equal(service.monthState.status,'loading');assert.equal(service.monthState.data,null);await pending;
  assert.equal(calls[0].path,'/activity/calendar');assert.equal(calls[0].method,'GET');assert.deepEqual(calls[0].query,{start:'2026-10-01',end:'2026-10-31'});
  assert.equal(service.monthState.status,'ready');const cells=calendarCells('2026-10',service.monthState.data).cells.filter(Boolean);assert.equal(cells[26].total,1);assert.equal(cells[0].total,0);
  assert.deepEqual(calendarRange('2024-02'),{start:'2024-02-01',end:'2024-02-29'});assert.equal(calendarRange('2026-12').end,'2026-12-31');
});
test('daily digest uses server highlights and actor objects without changing names',async()=>{
  const service=createCalendarService(async(path,options)=>{assert.equal(path,'/activity/digest/'+date);assert.equal(options.method,'GET');return digest();});
  await service.loadDay(date);assert.equal(service.dayState.status,'ready');assert.deepEqual(service.dayState.data.actors,[{name:'RJ45',count:1}]);
  const html=renderCalendarDigest(service.dayState.data,{esc:String,icon:()=>''});assert.match(html,/Backend highlight/);assert.match(html,/RJ45/);assert.ok(!html.includes('[object Object]'));
});
test('failed requests clear previous results, expose an error, and allow retry',async()=>{
  let fail=false;const service=createCalendarService(async()=>{if(fail)throw Error('Sign in required');return [row];});
  await service.loadMonth('2026-10');fail=true;await service.loadMonth('2026-10');assert.equal(service.monthState.status,'error');assert.equal(service.monthState.data,null);assert.equal(service.monthState.error,'Sign in required');
  fail=false;await service.loadMonth('2026-10');assert.equal(service.monthState.status,'ready');
  const failed=createCalendarService(async()=>{throw Error('Unavailable');});await failed.loadDay(date);assert.equal(failed.dayState.status,'error');assert.equal(failed.dayState.data,null);
});
test('malformed responses and non-ISO dates never become a fake empty calendar',async()=>{
  assert.throws(()=>calendarDate('10-1-2026'),/YYYY-MM-DD/);assert.throws(()=>calendarDate('2026-02-30'),/valid/);
  const range=calendarRange('2026-10');for(const raw of [{items:[row]},[{...row,total:-1}],[row,row],[{...row,date:'2026-11-01'}]])assert.throws(()=>calendarRows(raw,range));
  assert.throws(()=>calendarSummary({...digest(),total:2},date));assert.throws(()=>calendarSummary({...digest(),by_actor:{RJ45:1}},date));
  const service=createCalendarService(async()=>({items:[]}));assert.throws(()=>service.loadDay('10-1-2026'));assert.throws(()=>service.loadMonth('2026-13'));await service.loadMonth('2026-10');assert.equal(service.monthState.status,'error');
});
test('rapid month and day changes abort old reads and ignore stale responses',async()=>{
  const calls=[],service=createCalendarService((path,options)=>new Promise(resolve=>calls.push({path,options,resolve})));
  const old=service.loadMonth('2026-10'),next=service.loadMonth('2026-11');assert.ok(calls[0].options.signal.aborted);
  calls[1].resolve([]);await next;calls[0].resolve([row]);assert.equal(await old,false);assert.equal(service.monthState.key,'2026-11');assert.deepEqual(service.monthState.data,[]);
  const first=service.loadDay(date),second=service.loadDay('2026-10-28');assert.ok(calls[2].options.signal.aborted);
  calls[3].resolve(previewCalendarSummary([],'2026-10-28'));await second;calls[2].resolve(digest());assert.equal(await first,false);assert.equal(service.dayState.key,'2026-10-28');assert.equal(service.dayState.data.total,0);
});
test('preview supplies the same raw calendar/digest contracts and explicit empty/error states',async()=>{
  const source=createPreviewProvider({delayMs:0}),range=calendarRange(new Date().toISOString().slice(0,7));
  const rows=calendarRows(await source.request({path:'/activity/calendar',query:range}),range);assert.ok(rows.length>0);
  const raw=await source.request({path:'/activity/digest/'+rows[0].date});assert.equal(calendarSummary(raw,rows[0].date).total,rows[0].total);
  const empty=createPreviewProvider({delayMs:0,scenario:'empty'});assert.deepEqual(await empty.request({path:'/activity/calendar',query:range}),[]);assert.equal(calendarSummary(await empty.request({path:'/activity/digest/'+date}),date).total,0);
  const error=createPreviewProvider({delayMs:0,scenario:'error'});await assert.rejects(error.request({path:'/activity/calendar',query:range}),/Preview error/);
});
