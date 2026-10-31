import {dataSource} from '../state/data-source.js';
import {store} from '../state/data.js';
import {API_BASE_URL} from '../api/hosted-api.js';
export const sessionState={status:'idle',username:'',fullName:'',firstName:'',lastName:'',error:''};
let sessionPromise;
export function signOut(){
 // This endpoint returns a redirect and clears an HttpOnly cookie, so use
 // browser navigation instead of the JSON API transport.
 globalThis.location.replace(new URL('/auth/logout',API_BASE_URL).href);
}
export function loadSession(){
 if(sessionPromise)return sessionPromise;
 sessionState.status='loading';sessionState.error='';
 sessionPromise=(async()=>{try{const raw=await dataSource.request({service:'session',path:'/me'});if(typeof raw?.username!=='string'||!raw.username.trim())throw Error('The sign-in service returned no username.');const firstName=typeof raw.first_name==='string'?raw.first_name.trim():'',lastName=typeof raw.last_name==='string'?raw.last_name.trim():'';const fullName=(typeof raw.full_name==='string'?raw.full_name.trim():'')||[firstName,lastName].filter(Boolean).join(' ')||raw.username.trim();Object.assign(sessionState,{status:'ready',username:raw.username.trim(),fullName,firstName,lastName,error:''});store.settings.name=fullName;}catch(error){Object.assign(sessionState,{status:'error',username:'',fullName:'',firstName:'',lastName:'',error:error.message||'Could not read your sign-in session.'});store.settings.name='';const page=globalThis.location;if(error.status===401&&page&&/^https?:$/.test(page.protocol)&&page.origin===new URL(API_BASE_URL).origin){const login=new URL('/auth/login',page.origin);login.searchParams.set('next',page.pathname+page.search+page.hash);page.replace(login.href);}}finally{sessionPromise=null;}})();return sessionPromise;
}

// Only the signed-in account can be resolved by /auth/me; preserve other backend names.
export function displayActor(value){return sessionState.status==='ready'&&value===sessionState.username?sessionState.fullName:value;}
