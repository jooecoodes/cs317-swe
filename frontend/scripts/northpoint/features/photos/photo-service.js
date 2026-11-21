import {dataSource} from '../../state/data-source.js';
import {API_BASE_URL} from '../../api/hosted-api.js';
export const photoData={status:'idle',items:[],activity:[],stats:null,error:'',timeframe:'all',refreshing:false,lastUpdated:null};
export const photoUpload={busy:false,uncertain:false,error:'',reviewed:false};
let photoListener=()=>{},photoLoad,photoLoadKey,photoGeneration=0;
export function watchPhotos(fn){photoListener=fn;}
export function notifyPhotos(){photoListener();}
export function photoFileUrl(id){if(!/^\d+$/.test(String(id)))throw Error('Invalid photo ID.');return new URL(`/app2/photos/${id}/file`,API_BASE_URL).href;}
export function photoRequest(path,options={}){return dataSource.request({service:'photos',path,...options});}
// Derive source tags from original metadata, including photos uploaded before this UI update.
export function photoTags(raw){
 const source=raw.mobile_metadata?.source,label=source==='camera'?'Photo Upload':source==='gallery'?'Gallery Upload':null;
 const tags=raw.tags.map(String);
 if(!label)return tags; // Never guess the origin of older photos without source metadata.
 return [label,...tags.filter(t=>!['mobile upload','camera photo','photo upload','gallery upload'].includes(t.trim().toLowerCase()))];
}
export function normalizePhoto(raw){if(!Number.isSafeInteger(raw?.id)||raw.id<1||typeof raw.owner!=='string'||typeof raw.timestamp!=='string'||Number.isNaN(Date.parse(raw.timestamp))||!Array.isArray(raw.tags))throw Error('The photo service returned an invalid photo.');return {mobileMetadata:raw.mobile_metadata||null,exifTakenAt:raw.mobile_metadata?.exif_taken_at||null,id:String(raw.id),name:raw.title||'Untitled Photo',locationName:raw.location_name||'',description:raw.description||'',tags:photoTags(raw),owner:raw.owner,size:raw.size_bytes||0,created:Date.parse(/(?:Z|[+-]\d\d:\d\d)$/.test(raw.timestamp)?raw.timestamp:raw.timestamp+'+08:00'),url:photoFileUrl(raw.id)};}
async function pages(path,limit=200,query={}){const items=[],ids=new Set();let offset=0,expected=null;for(let page=0;page<2000;page++){const raw=await photoRequest(path,{query:{...query,limit,offset}});if(!Array.isArray(raw?.items)||!Number.isSafeInteger(raw.total)||raw.total<0||raw.offset!==offset||expected!==null&&raw.total!==expected)throw Error('The photo list changed or returned incomplete data. Refresh to retry.');expected=raw.total;for(const item of raw.items){if(!Number.isSafeInteger(item.id)||ids.has(item.id))throw Error('The photo service returned repeated records.');ids.add(item.id);items.push(item);}if(items.length===expected)return items;if(!raw.items.length||items.length>expected)throw Error('The photo service returned an incomplete list.');offset+=raw.items.length;}throw Error('The photo list is too large to load.');}
export function loadPhotos(force=false,timeframe=photoData.timeframe){
 if(!['today','week','all'].includes(timeframe))return Promise.reject(Error('Choose a valid upload period.'));
 if(photoLoad&&photoLoadKey===timeframe)return photoLoad;
 if(!force&&photoData.status==='ready'&&photoData.timeframe===timeframe)return Promise.resolve();
 const generation=++photoGeneration,keep=photoData.status==='ready'&&photoData.timeframe===timeframe;
 photoData.timeframe=timeframe;photoData.refreshing=true;photoData.error='';
 if(!keep)photoData.status='loading';
 photoLoadKey=timeframe;
 // Start requests on a microtask so listeners cannot start a duplicate load.
 photoLoad=Promise.resolve().then(async()=>{
  try{
   const stats=await photoRequest('/stats',{query:{include_employees:true}});
   if(!Number.isSafeInteger(stats.total_photos)||typeof stats.total_bytes!=='number'||!Array.isArray(stats.employee_counts)||!Number.isSafeInteger(stats.uploads_today)||stats.employee_counts.some(row=>typeof row.owner!=='string'||!Number.isSafeInteger(row.uploads_today)||row.uploads_today<0||!Number.isSafeInteger(row.total_uploads)||row.total_uploads<row.uploads_today)||!/^\d{4}-\d{2}-\d{2}$/.test(stats.business_date))throw Error('Photo summary needs the updated backend. Restart the photo service and refresh.');
   const items=await pages('/photos',200,{timeframe,on_date:stats.business_date});
   if(generation!==photoGeneration)return;
   Object.assign(photoData,{status:'ready',items:items.map(normalizePhoto),activity:[],stats,error:'',lastUpdated:Date.now()});
   if(photoUpload.uncertain)photoUpload.reviewed=true;
  }catch(error){
   if(generation!==photoGeneration)return;
   if(keep)photoData.error=error.message;
   else Object.assign(photoData,{status:'error',items:[],activity:[],stats:null,error:error.message});
  }finally{
   if(generation===photoGeneration){photoLoad=null;photoLoadKey=null;photoData.refreshing=false;photoListener();}
  }
 });
 photoListener();return photoLoad;
}
export async function uploadPhoto(){throw Error('Only employees can upload photos through the Northpoint Android app.');}
export function allowPhotoRetry(){if(!photoUpload.reviewed||photoData.status!=='ready')throw Error('Refresh the library and check the recent uploads first.');photoUpload.uncertain=false;photoUpload.error='';photoUpload.reviewed=false;}

export function photoDownloadUrl(id){photoFileUrl(id);return new URL('/app2/photos/'+id+'/download',API_BASE_URL).href;}
export async function readPhoto(id){photoFileUrl(id);return normalizePhoto(await photoRequest('/photos/'+id));}
