import {dashboardSummary} from './domain.js';
export function businessDate(value=new Date()){const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Manila',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(value));return ['year','month','day'].map(type=>parts.find(p=>p.type===type).value).join('-');}
const shift=(date,days)=>{const d=new Date(date+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+days);return d.toISOString().slice(0,10);};
const issuedDay=value=>businessDate(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)?value:value+'Z');
const safe=value=>Number.isSafeInteger(value)&&value>=0;
export function yesterdayComparison({employees,records,events,removals=[],days=30,today=businessDate(),scoped=false}){
 const current=dashboardSummary(employees,records,[]),models=new Map(),rows=new Map(records.map(v=>[String(v.id),{employee:String(v.employeeApiId||v.employeeId),date:v.date}]));
 for(const employee of employees){const own=records.filter(r=>String(r.employeeApiId||r.employeeId)===String(employee.apiId||employee.id));models.set(String(employee.apiId||employee.id),{code:employee.id,department:employee.department,count:own.length,points:employee.totalPoints??own.reduce((s,r)=>s+r.points,0),strikes:employee.totalStrikes??own.filter(r=>r.strike).length});}
 let incomplete=false,averageUnknown=false;
 const todayEvents=events.filter(e=>businessDate(e.date)===today).sort((a,b)=>Date.parse(b.date)-Date.parse(a.date)||Number(b.id)-Number(a.id));
 function removeEmployee(id){models.delete(id);for(const [key,row] of rows)if(row.employee===id)rows.delete(key);}
 for(const e of todayEvents){const m=e.metadata||{},id=String(e.employeeApiId||e.targetId||''),action=e.action;
  if(action==='employee.updated'&&m.changes?.employee_code&&todayEvents.some(row=>row.action==='employees.bulk_created'))incomplete=true;
  if(scoped&&action==='employee.updated'&&Object.hasOwn(m.changes||{},'department')){incomplete=true;continue;}
  if(action==='employee.deleted'){
   if(scoped&&!Object.hasOwn(m,'department')){incomplete=true;continue;}
   if(scoped&&!employees.some(emp=>emp.department===m.department))continue;
   models.set(String(e.targetId||e.employeeApiId),{code:m.employee_code,department:m.department,count:safe(m.violation_count)?m.violation_count:null,points:safe(m.total_points)?m.total_points:m.violation_count===0?0:null,strikes:safe(m.total_strikes)?m.total_strikes:m.violation_count===0?0:null});
   if(Array.isArray(m.violation_records))for(const r of m.violation_records)rows.set(String(r.id),{employee:String(e.targetId||e.employeeApiId),date:issuedDay(String(r.issued_at))});else if(m.violation_count)averageUnknown=true;
  }else if(action==='employee.created')removeEmployee(String(e.targetId||e.employeeApiId));
  else if(action==='employees.bulk_created'){
   if(!Array.isArray(m.codes)){incomplete=true;continue;}
   for(const [key,employee] of models)if(m.codes.includes(employee.code))removeEmployee(key);
  }else if(action==='violation.assigned'||action==='violation.removed'){
   const employeeId=String(e.employeeApiId||''),employee=models.get(employeeId);if(!employee)continue;
   const direction=action==='violation.assigned'?-1:1;
   employee.count=employee.count===null?null:employee.count+direction;
   employee.points=employee.points===null||!safe(m.points)?null:employee.points+direction*m.points;
   employee.strikes=employee.strikes===null||typeof m.is_strike!=='boolean'?null:employee.strikes+direction*Number(m.is_strike);
   if(direction===-1)rows.delete(String(e.targetId));else{const removal=removals.find(r=>String(r.violationId)===String(e.targetId));if(removal?.originalIssuedAt)rows.set(String(e.targetId),{employee:employeeId,date:issuedDay(removal.originalIssuedAt)});else averageUnknown=true;}
  }else if(action==='violation.updated'&&m.changes?.issued_at)averageUnknown=true;
 }
 const values=[...models.values()],sum=key=>values.some(e=>e[key]===null||e[key]<0)?null:values.reduce((s,e)=>s+e[key],0);
 const baseline={employees:models.size,violations:sum('count'),points:sum('points'),watchlist:values.some(e=>e.strikes===null||e.strikes<0)?null:values.filter(e=>e.strikes>=2).length};
 const result={};for(const key of ['employees','violations','points','watchlist'])result[key]=incomplete||baseline[key]===null?null:(key==='watchlist'?current.watchlist.length:current[key])-baseline[key];
 const previous=shift(today,-1),from=shift(today,-days+1),previousFrom=shift(previous,-days+1);
 const currentCount=records.filter(r=>r.date>=from&&r.date<=today).length,previousCount=[...rows.values()].filter(r=>models.has(r.employee)&&r.date>=previousFrom&&r.date<=previous).length;
 result.dailyAverage=incomplete||averageUnknown?null:(currentCount-previousCount)/days;
 result.reason='The audit history does not contain enough information to reconstruct yesterday’s total.';
 return result;
}
export function renderYesterdayChange(value,icon,reason='',decimals=0){
 if(value===undefined)return '<div class="metric-change neutral"><span>Loading comparison…</span></div>';
 reason=String(reason).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
 if(value===null)return `<div class="metric-change neutral" title="${reason||'Yesterday’s data is unavailable.'}"><strong>—</strong><span>vs yesterday</span></div>`;
 const rounded=Number(value.toFixed(decimals)),label=(rounded>=0?'+':'')+rounded.toFixed(decimals);
 return `<div class="metric-change ${rounded>0?'increase':rounded<0?'decrease':'neutral'}">${icon(rounded<0?'arrow-down':'arrow-up',15)}<strong>${label}</strong><span>vs yesterday</span></div>`;
}
