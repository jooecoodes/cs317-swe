import '../../config.js';
import {apiRoute,validateActor} from './api-routes.js';
export const API_BASE_URL=globalThis.NORTHPOINT_CONFIG.BASE_URL.replace(/\/+$/,'');
function failure(message,extra={}){return Object.assign(new Error(message),{handled:true,uncertain:false,...extra});}
function serverMessage(raw,status){
 if(typeof raw?.detail==='string')return raw.detail;
 if(Array.isArray(raw?.detail))return raw.detail.map(item=>`${(item.loc||[]).filter(part=>part!=='body').join(' · ')}: ${item.msg||'Invalid value'}`).join('; ');
 return ({400:'The server could not accept these details.',401:'You are not signed in, or your session has expired. Open Northpoint on the API server and sign in again.',403:'The API denied access to this action.',404:'This record no longer exists. Refresh the list.',409:'This change conflicts with an existing record. Review the details.',422:'Review the highlighted field details.',429:'Too many requests. Please wait a moment and try again.'})[status]||`The API returned HTTP ${status}. Please try again.`;
}
export function createHostedApiProvider({fetchImpl=(...args)=>globalThis.fetch(...args),timeoutMs=15000}={}){
 return {mode:'api',async request({path,method='GET',query={},body,actor,signal,service='hr'}={}){
  const rule=apiRoute(path,method,service),write=method!=='GET';
  const headers={Accept:'application/json'};
  if(rule.actor)headers['X-Actor']=validateActor(actor);
  const multipart=typeof FormData!=='undefined'&&body instanceof FormData;
  if(body!==undefined&&!multipart)headers['Content-Type']='application/json';
  const base=service==='hr'?API_BASE_URL:new URL(service==='photos'?'/app2':'/auth',API_BASE_URL).href;
  const url=new URL(base+path);
  for(const [key,value] of Object.entries(query))if(value!==undefined&&value!==null){if(!['string','number','boolean'].includes(typeof value))throw failure('Invalid API query.');url.searchParams.set(key,String(value));}
  if(signal?.aborted)throw failure('Request cancelled.',{name:'AbortError',code:'cancelled'});
  const controller=new AbortController();let timedOut=false,dispatched=false;
  const cancel=()=>controller.abort();signal?.addEventListener('abort',cancel,{once:true});
  const timer=setTimeout(()=>{timedOut=true;controller.abort();},timeoutMs);
  try{
   const options={method,headers,credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal};if(body!==undefined)options.body=multipart?body:JSON.stringify(body);
   dispatched=true;const response=await fetchImpl(url.href,options);
   let raw=null;
   if(response.status!==204){
    const json=/\bapplication\/(?:[\w.-]+\+)?json\b/i.test(response.headers.get('content-type')||'');
    if(json){try{raw=await response.json();}catch{throw failure('The server returned unreadable JSON. Refresh to check the latest records.',{status:response.status,uncertain:write&&(response.ok||response.status>=500),accepted:write&&response.ok});}}
    else if(response.ok)throw failure('The server returned a page instead of API data. Check config.js and sign in on the API server.',{status:response.status,uncertain:write,accepted:write});
   }
   if(!response.ok)throw failure(serverMessage(raw,response.status),{status:response.status,code:response.status===409?'conflict':'api-error',backendError:raw?.error,uncertain:write&&response.status>=500});
   if(raw===null&&response.status!==204)throw failure('The API returned an empty response instead of record data.',{status:response.status,uncertain:write,accepted:write});
   return raw;
  }catch(error){
   if(error.handled)throw error;
   throw failure(timedOut?'The API took too long to respond. Please try again.':controller.signal.aborted?'Request cancelled.':'Could not reach the API. Check config.js and that the server is running. Open Northpoint on the same server and sign in; other origins also need backend CORS support.',{code:timedOut?'timeout':controller.signal.aborted?'cancelled':'network',name:controller.signal.aborted&&!timedOut?'AbortError':'Error',uncertain:write&&dispatched});
  }finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel);}
 }};
}
