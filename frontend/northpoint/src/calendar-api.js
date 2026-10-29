import {apiRequest} from './api-client.js';
import {calendarDate,calendarRange,calendarRows,calendarSummary} from './calendar-contract.js';

// Inject a parsed-JSON request function to use another transport in tests or integration.
// The shared apiRequest delegates to data-source.js (hosted API).
export function createCalendarService(request=apiRequest) {
  const monthState={key:'',status:'idle',data:null,error:''},dayState={key:'',status:'idle',data:null,error:''};
  const pending={month:null,day:null};let monthVersion=0,dayVersion=0;
  async function load(kind,key,path,query,normalize) {
    const state=kind==='month'?monthState:dayState,version=kind==='month'?++monthVersion:++dayVersion;
    pending[kind]?.abort();const controller=new AbortController();pending[kind]=controller;
    Object.assign(state,{key,status:'loading',data:null,error:''});
    try{const raw=await request(path,{method:'GET',query,signal:controller.signal});const data=normalize(raw);if(version!==(kind==='month'?monthVersion:dayVersion))return false;Object.assign(state,{status:'ready',data,error:''});}
    catch(error){if(version!==(kind==='month'?monthVersion:dayVersion))return false;Object.assign(state,{status:'error',data:null,error:error.message||'Calendar activity could not be loaded. Please try again.'});}
    finally{if(pending[kind]===controller)pending[kind]=null;}
    return true;
  }
  return {monthState,dayState,invalidate(){monthVersion++;dayVersion++;for(const kind of ['month','day']){pending[kind]?.abort();pending[kind]=null;}for(const state of [monthState,dayState])Object.assign(state,{key:'',status:'idle',data:null,error:''});},loadMonth(month){const range=calendarRange(month);return load('month',month,'/activity/calendar',range,raw=>calendarRows(raw,range));},loadDay(date){calendarDate(date);return load('day',date,'/activity/digest/'+date,{},raw=>calendarSummary(raw,date));}};
}
export const calendarService=createCalendarService();
