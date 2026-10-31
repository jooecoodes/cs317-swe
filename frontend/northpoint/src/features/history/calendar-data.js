// Calendar dates follow the backend's UTC event_date, independently of device time.
export function validCalendarDate(value) {
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const date=new Date(value+'T12:00:00Z');
  return !Number.isNaN(date.getTime())&&date.toISOString().slice(0,10)===value;
}
export function calendarMonthBounds(month) {
  if(typeof month!=='string'||!/^\d{4}-\d{2}$/.test(month)||!validCalendarDate(month+'-01'))throw new Error('Choose a valid calendar month.');
  const start=month+'-01',last=new Date(start+'T12:00:00Z');last.setUTCMonth(last.getUTCMonth()+1,0);
  return {start,end:last.toISOString().slice(0,10),days:last.getUTCDate(),offset:new Date(start+'T12:00:00Z').getUTCDay()};
}
export function shiftCalendarMonth(month,amount) {
  const {start}=calendarMonthBounds(month),date=new Date(start+'T12:00:00Z');date.setUTCMonth(date.getUTCMonth()+amount);
  const result=date.toISOString().slice(0,7);calendarMonthBounds(result);return result;
}
export function calendarCells(month,rows=[],today=new Date().toISOString().slice(0,10)) {
  const {start,end,days,offset}=calendarMonthBounds(month),counts=new Map();
  if(!Array.isArray(rows))throw new Error('The calendar returned an unexpected list. Please try again.');
  for(const row of rows){if(!validCalendarDate(row?.date)||row.date<start||row.date>end||!Number.isSafeInteger(row.total)||row.total<0||counts.has(row.date))throw new Error('The calendar returned invalid daily totals. Please try again.');counts.set(row.date,row.total);}
  const maximum=Math.max(0,...counts.values()),cells=Array(offset).fill(null);
  for(let day=1;day<=days;day++){
    const date=month+'-'+String(day).padStart(2,'0'),total=counts.get(date)||0;
    cells.push({day,date,total,today:date===today,strength:total?Number((.08+.4*Math.log1p(total)/Math.log1p(maximum)).toFixed(3)):0});
  }
  while(cells.length%7)cells.push(null);
  return {cells,maximum,total:[...counts.values()].reduce((sum,value)=>sum+value,0),activeDays:[...counts.values()].filter(Boolean).length};
}
export function calendarActionLabel(value) {
  const labels={'employee.created':'Employee added','employees.bulk_created':'Employees imported','employee.updated':'Employee updated','employee.deleted':'Employee deleted','employee.activated':'Employee reactivated','employee.deactivated':'Employee deactivated','violation.assigned':'Violation issued','violation.updated':'Violation updated','violation.removed':'Violation removed','violation_type.created':'Violation type added','violation_type.updated':'Violation type updated','violation_type.activated':'Violation type activated','violation_type.deactivated':'Violation type deactivated','violation_type.deleted':'Violation type deleted'};
  return labels[value]||String(value||'Other change').replaceAll('_',' ').replaceAll('.',' ').replace(/\b\w/g,letter=>letter.toUpperCase());
}
export function previewCalendarRows(events,start,end) {
  if(!validCalendarDate(start)||!validCalendarDate(end)||start>end)throw new Error('Choose a valid date range.');
  const days=new Map();
  for(const event of events){const date=event.event_date;if(date<start||date>end)continue;
    if(!days.has(date))days.set(date,{date,total:0,employees:0,violations:0,violation_types:0,removals:0});
    const row=days.get(date);row.total++;if(event.target_type==='employee')row.employees++;if(event.target_type==='violation')row.violations++;if(event.target_type==='violation_type')row.violation_types++;if(event.action==='violation.removed')row.removals++;
  }
  return [...days.values()].sort((a,b)=>a.date.localeCompare(b.date));
}
export function previewDailyDigest(events,date) {
  if(!validCalendarDate(date))throw new Error('Choose a valid calendar date.');
  const selected=events.filter(event=>event.event_date===date).slice().sort((a,b)=>Date.parse(a.occurred_at)-Date.parse(b.occurred_at)||a.id-b.id),by_action=Object.create(null),actors=new Map();
  for(const event of selected){by_action[event.action]=(by_action[event.action]||0)+1;actors.set(event.actor,(actors.get(event.actor)||0)+1);}
  return {date,total:selected.length,by_action,by_actor:[...actors].map(([actor,count])=>({actor,count})).sort((a,b)=>b.count-a.count||a.actor.localeCompare(b.actor)),
    highlights:selected.length?Object.entries(by_action).map(([action,count])=>`${calendarActionLabel(action)}: ${count} ${count===1?'change':'changes'}.`):['No activity recorded on this day.'],events:selected};
}
export function validateDailyDigest(raw,date) {
  const validCount=value=>Number.isSafeInteger(value)&&value>=0;
  if(raw?.date!==date||!validCount(raw.total)||!raw.by_action||Array.isArray(raw.by_action)||typeof raw.by_action!=='object'||!Array.isArray(raw.by_actor)||!Array.isArray(raw.highlights)||!Array.isArray(raw.events)||raw.events.length!==raw.total)throw new Error('The daily summary could not be read. Please try again.');
  if(Object.values(raw.by_action).some(value=>!validCount(value))||Object.values(raw.by_action).reduce((sum,value)=>sum+value,0)!==raw.total||raw.by_actor.some(row=>typeof row?.actor!=='string'||!validCount(row.count))||raw.by_actor.reduce((sum,row)=>sum+row.count,0)!==raw.total||raw.highlights.some(text=>typeof text!=='string'))throw new Error('The daily summary returned inconsistent totals. Please try again.');
  const ids=new Set();for(const event of raw.events){if(event.event_date!==date||typeof event.summary!=='string'||typeof event.actor!=='string'||typeof event.action!=='string'||typeof event.occurred_at!=='string'||Number.isNaN(Date.parse(event.occurred_at))||ids.has(event.id))throw new Error('The daily summary returned invalid events. Please try again.');ids.add(event.id);}
  return raw;
}
