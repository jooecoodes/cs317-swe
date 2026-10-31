import {dataSource} from './data-source.js';
import {store} from './data.js';
import {API_BASE_URL} from './hosted-api.js';
export const sessionState={status:'idle',username:'',error:''};
let sessionPromise;
export function loadSession(){
 if(sessionPromise)return sessionPromise;
 sessionState.status='loading';sessionState.error='';
 sessionPromise=(async()=>{try{const raw=await dataSource.request({service:'session',path:'/me'});if(typeof raw?.username!=='string'||!raw.username.trim())throw Error('The sign-in service returned no username.');Object.assign(sessionState,{status:'ready',username:raw.username,error:''});store.settings.name=raw.username;}catch(error){Object.assign(sessionState,{status:'error',username:'',error:error.message||'Could not read your sign-in session.'});store.settings.name='';const page=globalThis.location;if(error.status===401&&page&&/^https?:$/.test(page.protocol)&&page.origin===new URL(API_BASE_URL).origin){const login=new URL('/auth/login',page.origin);login.searchParams.set('next',page.pathname+page.search+page.hash);page.replace(login.href);}}finally{sessionPromise=null;}})();return sessionPromise;
}
