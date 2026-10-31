import {photoRequest,notifyPhotos} from './photo-service.js';
import {businessDate} from './yesterday.js';

function activityRows(rows){
 if(!Array.isArray(rows)||rows.some(e=>!e||!Number.isSafeInteger(e.id)||e.id<1||e.photo_id!=null&&(!Number.isSafeInteger(e.photo_id)||e.photo_id<1)||e.photo_display_name!=null&&typeof e.photo_display_name!=='string'||typeof e.actor!=='string'||typeof e.action!=='string'||typeof e.created_at!=='string'||Number.isNaN(Date.parse(e.created_at))))throw Error('The photo service returned invalid activity.');
 return rows;
}
export function createPhotoActivity(request=photoRequest,notify=()=>{}){
 const state={status:'idle',error:'',items:[],total:0,digest:null,actors:[],month:businessDate().slice(0,7),day:'',page:1,q:'',actor:'',action:''};
 let controller,version=0,digestCache=null,actorCache=null;
 async function load(changes={},force=false){
  Object.assign(state,changes);controller?.abort();controller=new AbortController();const signal=controller.signal,ticket=++version;
  Object.assign(state,{status:'loading',error:'',items:[],total:0,digest:null,actors:[]});notify();
  try{
   const [year,month]=state.month.split('-').map(Number),from=state.month+'-01',to=state.month+'-'+new Date(year,month,0).getDate();
   const filters={q:state.q||undefined,actor:state.actor||undefined,action:state.action||undefined};
   const feed={...filters,limit:8,offset:(state.page-1)*8,from_date:state.day||undefined,to_date:state.day||undefined};
   const digestQuery={...filters,from_date:from,to_date:to,include_items:false},key=JSON.stringify(digestQuery);
   const [page,digest,actors]=await Promise.all([
    request('/activity',{query:feed,signal}),
    !force&&digestCache?.key===key?digestCache.value:request('/activity/digest',{query:digestQuery,signal}),
    !force&&actorCache?actorCache:request('/activity/actors',{signal})
   ]);
   if(ticket!==version)return;
   activityRows(page.items);
   if(!Number.isSafeInteger(page.total)||page.total<0||page.offset!==feed.offset||page.limit!==8||page.items.length>8)throw Error('The photo service returned an invalid activity page.');
   if(typeof digest?.summary!=='string'||!Number.isSafeInteger(digest.total)||digest.total<0||digest.from_date!==from||digest.to_date!==to||!Array.isArray(digest.days)||digest.days.some(d=>!d||typeof d.date!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(d.date)||d.date<from||d.date>to||!Number.isSafeInteger(d.total)||d.total<0||typeof d.summary!=='string'))throw Error('The photo service returned an invalid activity summary.');
   if(!Array.isArray(actors.actors)||actors.actors.some(a=>typeof a.actor!=='string'||!Number.isSafeInteger(a.total)))throw Error('The photo service returned invalid actor statistics.');
   digestCache={key,value:digest};actorCache=actors;
   const last=Math.max(1,Math.ceil(page.total/8));if(state.page>last)return await load({page:last});
   Object.assign(state,{status:'ready',items:page.items,total:page.total,digest,actors:actors.actors});
  }catch(error){if(ticket!==version)return;digestCache=null;actorCache=null;Object.assign(state,{status:'error',error:error.message||'Could not load photo activity.',items:[],total:0,digest:null,actors:[]});}
  finally{if(ticket===version)notify();}
 }
 return {state,load};
}
export const photoActivityService=createPhotoActivity(photoRequest,notifyPhotos);
export async function fetchPhotoHistory(id,page=1){
 if(!/^\d+$/.test(String(id))||!Number.isInteger(page)||page<1)throw Error('Invalid photo history request.');
 const result=await photoRequest(`/photos/${id}/history`,{query:{limit:8,offset:(page-1)*8}});
 activityRows(result.items);if(result.photo_id!==Number(id)||!Number.isSafeInteger(result.total)||result.total<0||typeof result.photo_exists!=='boolean')throw Error('The photo service returned invalid photo history.');return result;
}
export async function fetchPhotoBatch(ids,actor){
 if(!Array.isArray(ids)||ids.length<1||ids.length>200||ids.some(id=>!Number.isSafeInteger(id)||id<1))throw Error('Choose between 1 and 200 photo IDs.');
 const result=await photoRequest('/photos/batch',{method:'POST',body:{ids},actor});
 if(!Array.isArray(result.found)||!Array.isArray(result.missing))throw Error('The photo service returned an invalid photo batch.');
 const returned=[...result.found.map(p=>p.id),...result.missing],expected=[...new Set(ids)];
 if(new Set(returned).size!==returned.length||returned.length!==expected.length||returned.some(id=>!expected.includes(id)))throw Error('The photo batch did not match the requested photos.');return result;
}
