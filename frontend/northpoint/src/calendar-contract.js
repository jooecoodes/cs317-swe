// Public backend response contracts. This file has no transport or UI dependencies.
export function calendarDate(value) {
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))throw new Error('Use a calendar date in YYYY-MM-DD format.');
  const date=new Date(value+'T12:00:00Z');if(Number.isNaN(date.getTime())||date.toISOString().slice(0,10)!==value)throw new Error('Choose a valid calendar date.');return value;
}
export function calendarRange(month) {
  const start=calendarDate(month+'-01'),last=new Date(start+'T12:00:00Z');last.setUTCMonth(last.getUTCMonth()+1,0);return {start,end:last.toISOString().slice(0,10)};
}
const count=value=>Number.isSafeInteger(value)&&value>=0;
export function calendarRows(raw,{start,end}) {
  if(!Array.isArray(raw))throw new Error('The calendar API returned an unexpected list.');const seen=new Set();
  return raw.map(row=>{const date=calendarDate(row?.date);if(date<start||date>end||seen.has(date)||['total','employees','violations','violation_types','removals'].some(key=>!count(row[key])))throw new Error('The calendar API returned invalid daily totals.');seen.add(date);return {...row};});
}
export function calendarSummary(raw,date) {
  if(raw?.date!==date||!count(raw.total)||!Array.isArray(raw.events)||raw.total!==raw.events.length||!raw.by_action||typeof raw.by_action!=='object'||Array.isArray(raw.by_action)||!Array.isArray(raw.by_actor)||!Array.isArray(raw.highlights))throw new Error('The daily summary API returned an unexpected response.');
  if(Object.values(raw.by_action).some(value=>!count(value))||Object.values(raw.by_action).reduce((sum,value)=>sum+value,0)!==raw.total||raw.by_actor.some(row=>typeof row?.actor!=='string'||!count(row.count))||raw.by_actor.reduce((sum,row)=>sum+row.count,0)!==raw.total||raw.highlights.some(value=>typeof value!=='string'))throw new Error('The daily summary API returned inconsistent totals.');
  const ids=new Set(),events=raw.events.map(event=>{if(!Number.isSafeInteger(event.id)||event.id<1||ids.has(event.id)||event.event_date!==date||typeof event.occurred_at!=='string'||Number.isNaN(Date.parse(event.occurred_at))||typeof event.actor!=='string'||typeof event.action!=='string'||typeof event.summary!=='string')throw new Error('The daily summary API returned invalid events.');ids.add(event.id);return {id:event.id,date:/(?:Z|[+-]\d{2}:?\d{2})$/i.test(event.occurred_at)?event.occurred_at:event.occurred_at+'Z',actor:event.actor,action:event.action,detail:event.summary};}).sort((a,b)=>Date.parse(b.date)-Date.parse(a.date)||b.id-a.id);
  return {date,total:raw.total,events,actions:Object.entries(raw.by_action).map(([name,count])=>({name,count})),actors:raw.by_actor.map(({actor,count})=>({name:actor||'Not provided',count})),highlights:raw.highlights};
}
export function previewCalendarRows(events,{start,end}) {
  calendarDate(start);calendarDate(end);if(start>end)throw new Error('The end date must be on or after the start date.');const rows=new Map();
  for(const event of events){const date=event.event_date;if(date<start||date>end)continue;if(!rows.has(date))rows.set(date,{date,total:0,employees:0,violations:0,violation_types:0,removals:0});const row=rows.get(date);row.total++;if(event.target_type==='employee')row.employees++;if(event.target_type==='violation')row.violations++;if(event.target_type==='violation_type')row.violation_types++;if(event.action==='violation.removed')row.removals++;}
  return [...rows.values()].sort((a,b)=>a.date.localeCompare(b.date));
}
export function previewCalendarSummary(events,date) {
  calendarDate(date);const rows=events.filter(event=>event.event_date===date),actions=Object.create(null),actors=new Map();
  for(const event of rows){actions[event.action]=(actions[event.action]||0)+1;actors.set(event.actor,(actors.get(event.actor)||0)+1);}
  return {date,total:rows.length,by_action:actions,by_actor:[...actors].map(([actor,count])=>({actor,count})),highlights:Object.entries(actions).map(([action,count])=>`${action.replaceAll('.',' ').replaceAll('_',' ')}: ${count} ${count===1?'change':'changes'}.`),events:rows};
}
