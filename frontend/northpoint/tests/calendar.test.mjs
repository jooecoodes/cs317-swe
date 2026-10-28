import test from 'node:test';
import assert from 'node:assert/strict';
import {calendarMonthBounds,shiftCalendarMonth,calendarCells,previewCalendarRows,previewDailyDigest,validateDailyDigest,validCalendarDate} from '../src/calendar-data.js';
import {createCalendarLoader,renderCalendarDigest} from '../src/calendar.js';
import {createPreviewProvider} from '../src/preview-provider.js';
import {previewFixtures} from '../src/preview-fixtures.js';

test('month layout handles leap days, Sunday starts, six weeks and year boundaries',()=>{
  assert.equal(calendarMonthBounds('2024-02').days,29);assert.equal(calendarMonthBounds('2026-02').days,28);
  assert.equal(calendarMonthBounds('2026-11').offset,0);assert.equal(calendarCells('2026-08').cells.length,42);
  assert.equal(shiftCalendarMonth('2026-12',1),'2027-01');assert.equal(shiftCalendarMonth('2026-01',-1),'2025-12');
  assert.equal(validCalendarDate('2026-02-29'),false);assert.equal(validCalendarDate('2024-02-29'),true);
  assert.throws(()=>calendarMonthBounds('2026-13'),/valid calendar month/);
});

test('daily shading increases with activity and missing days stay selectable with zero counts',()=>{
  const data=calendarCells('2026-10',[{date:'2026-10-01',total:3},{date:'2026-10-02',total:62}],'2026-10-03');
  const days=data.cells.filter(Boolean);assert.equal(days.length,31);assert.equal(data.total,65);assert.equal(data.activeDays,2);
  assert.ok(days[0].strength>0&&days[0].strength<days[1].strength);assert.ok(days[1].strength<=.48);
  assert.equal(days[2].strength,0);assert.equal(days[2].total,0);assert.equal(days[2].today,true);
  assert.throws(()=>calendarCells('2026-10',[{date:'2026-10-01',total:-1}]),/invalid daily totals/);
  assert.throws(()=>calendarCells('2026-10',[{date:'2026-11-01',total:1}]),/invalid daily totals/);
  assert.throws(()=>calendarCells('2026-10',[{date:'2026-10-01',total:1},{date:'2026-10-01',total:1}]),/invalid daily totals/);
});

test('calendar and digest preview routes follow the actual backend shapes and UTC dates',async()=>{
  const provider=createPreviewProvider({delayMs:0}),date=previewFixtures.activities[0].event_date,bounds=calendarMonthBounds(date.slice(0,7));
  const rows=await provider.request({path:'/activity/calendar',query:{start:bounds.start,end:bounds.end}});
  assert.deepEqual(rows,previewCalendarRows(previewFixtures.activities,bounds.start,bounds.end));
  const digest=await provider.request({path:'/activity/digest/'+date});validateDailyDigest(digest,date);
  assert.equal(rows.find(row=>row.date===date).total,digest.total);
  assert.ok(digest.by_actor.every(row=>typeof row.actor==='string'&&typeof row.count==='number'));
  const synthetic={...previewFixtures.activities[0],event_date:'2026-10-01',occurred_at:'2026-10-01T23:59:59Z'};
  assert.equal(previewDailyDigest([synthetic],'2026-10-02').total,0);assert.equal(previewDailyDigest([synthetic],'2026-10-01').total,1);
});

test('empty month and empty daily summary are valid states',async()=>{
  const provider=createPreviewProvider({scenario:'empty',delayMs:0});
  const rows=await provider.request({path:'/activity/calendar',query:{start:'2026-10-01',end:'2026-10-31'}});assert.deepEqual(rows,[]);
  const digest=await provider.request({path:'/activity/digest/2026-10-01'});validateDailyDigest(digest,digest.date);assert.equal(digest.total,0);
  assert.equal(calendarCells('2026-10',rows).maximum,0);
  assert.match(renderCalendarDigest(digest,{esc:String,icon:()=>''}),/No activity on this day/);
});

test('stale month replies cannot overwrite a newly selected month',async()=>{
  const pending=[];const loader=createCalendarLoader((_path,options)=>new Promise(resolve=>pending.push({options,resolve})));
  const old=loader.load('2026-10');assert.equal(loader.state.status,'loading');const next=loader.load('2026-11');assert.equal(pending[0].options.signal.aborted,true);
  pending[1].resolve([{date:'2026-11-01',total:2,employees:2,violations:0,violation_types:0,removals:0}]);assert.equal(await next,true);
  pending[0].resolve([{date:'2026-10-01',total:99,employees:99,violations:0,violation_types:0,removals:0}]);assert.equal(await old,false);
  assert.equal(loader.state.month,'2026-11');assert.equal(loader.state.rows[0].total,2);
});

test('month errors clear counts and retry reloads without fabricated activity',async()=>{
  let fail=true;const loader=createCalendarLoader(async()=>{if(fail)throw Error('Calendar unavailable');return [];});
  await loader.load('2026-10');assert.equal(loader.state.status,'error');assert.deepEqual(loader.state.rows,[]);assert.match(loader.state.error,/unavailable/);
  fail=false;await loader.load('2026-10');assert.equal(loader.state.status,'ready');assert.deepEqual(loader.state.rows,[]);
});

test('daily summary escapes content, renders actor names and paginates events at six',()=>{
  const events=Array.from({length:8},(_,index)=>({...previewFixtures.activities[0],id:900+index,event_date:'2026-10-27',occurred_at:`2026-10-27T10:${String(index).padStart(2,'0')}:00Z`,actor:'<img src=x onerror=alert(1)>',summary:'<script>unsafe()</script>'}));
  const digest=previewDailyDigest(events,'2026-10-27');validateDailyDigest(digest,digest.date);
  const esc=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const first=renderCalendarDigest(digest,{esc,icon:()=>''});assert.doesNotMatch(first,/<script>|<img src=x|\[object Object\]/);assert.match(first,/&lt;script&gt;/);
  assert.equal((first.match(/<ol>([\s\S]*?)<\/ol>/)[1].match(/<li>/g)||[]).length,6);assert.match(first,/1–6 of 8 changes/);
  const last=renderCalendarDigest(digest,{esc,icon:()=>''},2);assert.match(last,/7–8 of 8 changes/);assert.equal((last.match(/<ol>([\s\S]*?)<\/ol>/)[1].match(/<li>/g)||[]).length,2);
  assert.throws(()=>validateDailyDigest({...digest,total:9},digest.date),/could not be read/);
});
