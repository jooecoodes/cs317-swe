import {apiRequest} from '../../api/api-client.js';

const creationDates=new Map();
let newLabelTimer;
export function employeeCreationTime(value){
 if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T/.test(value))return NaN;
 // app1 stores UTC; SQLite may return its timestamp without an offset.
 return Date.parse(/(?:Z|[+-]\d\d:\d\d)$/i.test(value)?value:value+'Z');
}
export function isNewEmployee(employee,now=Date.now()){
 const value=employee.createdAt||creationDates.get(employee.apiId)?.value;
 const age=now-employeeCreationTime(value);return age>=0&&age<86400000;
}
export function employeeDateErrors(employees){return employees.some(e=>creationDates.get(e.apiId)?.status==='error');}
export function retryEmployeeDates(){for(const [key,value] of creationDates)if(value.status==='error')creationDates.delete(key);}
export function ensureEmployeeDates(employees,onChange){
 clearTimeout(newLabelTimer);
 const now=Date.now(),expires=employees.filter(e=>isNewEmployee(e,now)).map(e=>employeeCreationTime(e.createdAt||creationDates.get(e.apiId)?.value)+86400000);
 if(expires.length){newLabelTimer=setTimeout(onChange,Math.min(...expires)-now+5);newLabelTimer.unref?.();}
 const pending=employees.filter(e=>e.apiId&&!e.createdAt&&!creationDates.has(e.apiId)).map(async employee=>{
  creationDates.set(employee.apiId,{status:'loading'});
  try{
   const raw=await apiRequest('/employees/'+encodeURIComponent(employee.apiId));
   if(String(raw?.id)!==employee.apiId||raw.created_at!=null&&!Number.isFinite(employeeCreationTime(raw.created_at)))throw Error('Invalid employee creation date');
   creationDates.set(employee.apiId,{status:'ready',value:raw.created_at||null});
  }catch{creationDates.set(employee.apiId,{status:'error'});}
 });
 if(pending.length)void Promise.all(pending).then(onChange);
}
