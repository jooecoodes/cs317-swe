import {previewFixtures} from './preview-fixtures.js';
import {previewCalendarRows,previewDailyDigest} from './calendar-data.js';
const previewWriteMessage='This is a UI-only preview. Record changes are disabled. Connect the backend adapter to enable saving; your form entries have been kept.';
function failure(message,status=400,code='preview-request') {return Object.assign(new Error(message),{status,code,uncertain:false});}
function cancelled(){return new DOMException('Request cancelled.','AbortError');}
function pause(ms,signal) {
  return new Promise((resolve,reject)=>{
    if(signal?.aborted){reject(cancelled());return;}
    const abort=()=>{clearTimeout(timer);reject(cancelled());};
    const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve();},ms);
    signal?.addEventListener('abort',abort,{once:true});
  });
}
function page(items,query) {
  const limit=Math.max(1,Math.min(200,Number(query.limit)||50)),offset=Math.max(0,Number(query.offset)||0);
  return {items:items.slice(offset,offset+limit),total:items.length,limit,offset};
}
const clone=value=>JSON.parse(JSON.stringify(value));
function required(items,id){const row=items.find(item=>item.id===Number(id));if(!row)throw failure('This preview record is not available.',404);return row;}
export function createPreviewProvider({scenario='normal',delayMs=140}={}) {
  if(!['normal','empty','error'].includes(scenario))throw new Error('Unknown preview scenario.');
  return {mode:'preview',async request({path,method='GET',query={},signal}={}) {
    // No POST/PATCH/DELETE changes, in-memory writes, queues, or persistence.
    if(method!=='GET')throw failure(previewWriteMessage,501,'preview-only');
    await pause(delayMs,signal);
    if(scenario==='error')throw failure('Preview error state: records could not be loaded. Use Try again to reload the preview.',503,'preview-error');
    const fixtures=scenario==='empty'?{employees:[],violations:[],types:[],removals:[],activities:[]}:previewFixtures;
    const {employees,violations,types,removals,activities}=fixtures;
    let match,result;
    if(path==='/employees') {
      const list=employees.filter(row=>query.include_inactive===true||query.include_inactive==='true'||row.status==='active');
      result=page(list.map(({id,employee_code,full_name,department,position,status,total_points,total_strikes})=>({id,employee_code,full_name,department,position,status,total_points,total_strikes})),query);
    } else if((match=path.match(/^\/employees\/(\d+)\/violations$/))) {
      required(employees,match[1]);result=page(violations.filter(row=>row.employee_id===Number(match[1])),query).items;
    } else if((match=path.match(/^\/employees\/(\d+)$/))) {
      const row=required(employees,match[1]);result={...row,violation_records:violations.filter(record=>record.employee_id===row.id)};
    } else if(path==='/violation-types') {
      result=types.filter(row=>row.is_active).map(({id,name,default_points,is_strike})=>({id,name,default_points,is_strike}));
    } else if(path==='/violation-types/all')result=query.include_inactive===false?types.filter(row=>row.is_active):types;
    else if((match=path.match(/^\/violation-types\/(\d+)$/)))result=required(types,match[1]);
    else if(path==='/violations/recent') {
      const cutoff=Date.now()-(Number(query.days)||30)*86400000;
      result=violations.filter(row=>Date.parse(row.issued_at)>=cutoff&&(!query.only_strikes||query.only_strikes==='false'||row.is_strike)).sort((a,b)=>Date.parse(b.issued_at)-Date.parse(a.issued_at))
        .slice(0,Number(query.limit)||50).map(row=>{const employee=required(employees,row.employee_id);return {...row,employee:{id:employee.id,employee_code:employee.employee_code,full_name:employee.full_name}};});
    } else if((match=path.match(/^\/violations\/(\d+)$/)))result=required(violations,match[1]);
    else if(path==='/violation-removals')result=page(removals.slice().sort((a,b)=>Date.parse(b.removed_at)-Date.parse(a.removed_at)),query);
    else if((match=path.match(/^\/violation-removals\/(\d+)$/)))result=required(removals,match[1]);
    else if(path==='/activity/timeline')result=page(activities,query);
    else if(path==='/activity/calendar')result=previewCalendarRows(activities,query.start,query.end);
    else if((match=path.match(/^\/activity\/digest\/(\d{4}-\d{2}-\d{2})$/)))result=previewDailyDigest(activities,match[1]);
    else throw failure('This read route is not part of the UI preview.',404);
    return clone(result);
  }};
}
