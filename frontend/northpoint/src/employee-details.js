import { apiRequest, apiId } from './api-client.js';
import { normalizeApiEmployee } from './employee-api.js';
import { normalizeViolation } from './backend.js';

export const employeeProfile = { status:'idle', apiId:'', employee:null, violations:[], error:'' };
let profileSequence=0, profileController=null;
export async function fetchEmployeeProfile(id, options={}) {
  id=apiId(id);
  const raw=await apiRequest('/employees/'+id,options);
  const employee=normalizeApiEmployee(raw);
  if(employee.apiId!==id||!employee.firstName||!employee.lastName||!Array.isArray(raw.violation_records)) throw new Error('The API returned an incomplete employee profile. Please try again.');
  const seen=new Set();
  const violations=raw.violation_records.map(record=>{
    if(String(record.employee_id)!==id||seen.has(String(record.id)))throw new Error('The profile returned inconsistent violation history. Please try again.');
    seen.add(String(record.id));return normalizeViolation(record,[employee]);
  }).sort((a,b)=>b.issuedAt.localeCompare(a.issuedAt)||Number(b.id)-Number(a.id));
  return {employee,violations};
}
export async function loadEmployeeProfile(id,onChange=()=>{}) {
  id=apiId(id);const sequence=++profileSequence;
  profileController?.abort();const controller=new AbortController();profileController=controller;
  Object.assign(employeeProfile,{status:'loading',apiId:id,employee:null,violations:[],error:''});onChange();
  try{const result=await fetchEmployeeProfile(id,{signal:controller.signal});if(sequence===profileSequence)Object.assign(employeeProfile,{status:'ready',...result,error:''});}
  catch(error){if(sequence===profileSequence)Object.assign(employeeProfile,{status:'error',employee:null,violations:[],error:error.message||'The employee profile could not be loaded.'});}
  finally{if(sequence===profileSequence){profileController=null;onChange();}}
}
export function invalidateEmployeeProfile(){profileSequence++;profileController?.abort();profileController=null;Object.assign(employeeProfile,{status:'idle',apiId:'',employee:null,violations:[],error:''});}

export function employeeUpdatePayload(values,original) {
  const result={};
  for(const [input,key,label,required] of [['firstName','first_name','First name',true],['lastName','last_name','Last name',true],['department','department','Department',false],['position','position','Position',false]]) {
    if(!Object.hasOwn(values,input))continue;
    const value=String(values[input]??'').trim();
    if(required&&!value)throw new Error(label+' is required.');
    if(value.length>100)throw new Error(label+' must be 100 characters or fewer.');
    const before=original[input]||'';
    if(value!==before)result[key]=required?value:value||null;
  }
  return result;
}
export function employeeMatchesUpdate(employee,payload) {
  const names={first_name:'firstName',last_name:'lastName',department:'department',position:'position'};
  return Object.entries(payload).every(([key,value])=>(employee[names[key]]||'')===(value||''));
}
function unverified(){return Object.assign(new Error('The server accepted the request, but its employee reply could not be verified. Check save status before another attempt.'),{uncertain:true,accepted:true});}
export async function patchEmployee(id,payload,actor) {
  id=apiId(id);
  if(!Object.keys(payload).length)throw new Error('No employee details have changed.');
  if(Object.keys(payload).some(key=>!['first_name','last_name','department','position'].includes(key)))throw new Error('This employee field cannot be edited here.');
  const raw=await apiRequest('/employees/'+id,{method:'PATCH',body:payload,actor});
  try{const employee=normalizeApiEmployee(raw);if(employee.apiId!==id||!employeeMatchesUpdate(employee,payload))throw new Error();return employee;}catch{throw unverified();}
}
export async function changeEmployeeState(id,action,actor) {
  id=apiId(id);if(!['deactivate','reactivate','delete'].includes(action))throw new Error('This employee action is unavailable.');
  const raw=await apiRequest('/employees/'+id+(action==='delete'?'':'/'+action),{method:action==='delete'?'DELETE':'POST',actor});
  if(action==='delete')return;
  try{const employee=normalizeApiEmployee(raw);if(employee.apiId!==id||employee.status!==(action==='deactivate'?'Inactive':'Active'))throw new Error();return employee;}catch{throw unverified();}
}
