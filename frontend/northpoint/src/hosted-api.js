import {apiRoute,validateActor} from './api-routes.js';
export const API_BASE_URL='https://cs317.duckdns.org/app1';
function failure(message,extra={}){return Object.assign(new Error(message),{handled:true,uncertain:false,...extra});}
function serverMessage(raw,status){
 if(typeof raw?.detail==='string')return raw.detail;
 if(Array.isArray(raw?.detail))return raw.detail.map(item=>`${(item.loc||[]).filter(part=>part!=='body').join(' · ')}: ${item.msg||'Invalid value'}`).join('; ');
 return ({400:'The server could not accept these details.',401:'The hosted API requires authentication. Ask the backend team for the deployed access setup.',403:'The hosted API denied access to this action.',404:'This record no longer exists. Refresh the list.',409:'This change conflicts with an existing record. Review the details.',422:'Review the highlighted field details.',429:'Too many requests. Please wait a moment and try again.'})[status]||`The hosted API returned HTTP ${status}. Please try again.`;
}
export function createHostedApiProvider({fetchImpl=(...args)=>globalThis.fetch(...args),timeoutMs=15000}={}){
 return {mode:'api',async request({path,method='GET',query={},body,actor,signal}={}){
  const rule=apiRoute(path,method),write=method!=='GET';
  const headers={Accept:'application/json'};
  if(rule.actor)headers['X-Actor']=validateActor(actor);
  if(body!==undefined)headers['Content-Type']='application/json';
  const url=new URL(API_BASE_URL+path);
  for(const [key,value] of Object.entries(query))if(value!==undefined&&value!==null){if(!['string','number','boolean'].includes(typeof value))throw failure('Invalid API query.');url.searchParams.set(key,String(value));}
  if(signal?.aborted)throw failure('Request cancelled.',{name:'AbortError',code:'cancelled'});
  const controller=new AbortController();let timedOut=false,dispatched=false;
  const cancel=()=>controller.abort();signal?.addEventListener('abort',cancel,{once:true});
  const timer=setTimeout(()=>{timedOut=true;controller.abort();},timeoutMs);
  try{
   const options={method,headers,credentials:'omit',cache:'no-store',redirect:'error',signal:controller.signal};if(body!==undefined)options.body=JSON.stringify(body);
   dispatched=true;const response=await fetchImpl(url.href,options);
   let raw=null;
   if(response.status!==204){
    const json=/\bapplication\/(?:[\w.-]+\+)?json\b/i.test(response.headers.get('content-type')||'');
    if(json){try{raw=await response.json();}catch{throw failure('The server returned unreadable JSON. Refresh to check the latest records.',{status:response.status,uncertain:write&&(response.ok||response.status>=500),accepted:write&&response.ok});}}
    else if(response.ok)throw failure('The hosted server returned a page instead of API data. Check the API address and deployed access setup.',{status:response.status,uncertain:write,accepted:write});
   }
   if(!response.ok)throw failure(serverMessage(raw,response.status),{status:response.status,code:response.status===409?'conflict':'api-error',backendError:raw?.error,uncertain:write&&response.status>=500});
   if(raw===null&&response.status!==204)throw failure('The API returned an empty response instead of record data.',{status:response.status,uncertain:write,accepted:write});
   return raw;
  }catch(error){
   if(error.handled)throw error;
   throw failure(timedOut?'The hosted API took too long to respond. Please try again.':controller.signal.aborted?'Request cancelled.':'Could not reach the hosted API. Check your internet connection. If the API opens separately, ask the backend team to check CORS for this frontend and its write headers.',{code:timedOut?'timeout':controller.signal.aborted?'cancelled':'network',name:controller.signal.aborted&&!timedOut?'AbortError':'Error',uncertain:write&&dispatched});
  }finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel);}
 }};
}
