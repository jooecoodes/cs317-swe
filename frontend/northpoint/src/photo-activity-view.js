import {displayActor} from './session.js';
import {photoActivityService,fetchPhotoHistory,fetchPhotoBatch} from './photo-activity.js';
import {photoFileUrl} from './photo-service.js';
import {loadingSkeleton} from './loading.js';

export function renderPhotoActivity({icon,esc,formatDate}){
 const a=photoActivityService.state,[y,m]=a.month.split('-').map(Number),month=new Date(y,m-1,1),count=new Date(y,m,0).getDate();
 const days=a.digest?.days||[],peak=Math.max(1,...days.map(d=>d.total));
 let cells='<span></span>'.repeat(month.getDay());
 for(let i=1;i<=count;i++){
  const date=a.month+'-'+String(i).padStart(2,'0'),day=days.find(d=>d.date===date);
  cells+=`<button class="np-photo-day ${date===a.day?'selected':''} ${day?.total?'has-activity':''}" ${day?.total?`style="background:rgba(82,124,169,${.12+.45*day.total/peak})"`:''} data-action="photo-activity-day" data-date="${date}" aria-label="${date}${a.status==='ready'?', '+(day?.total||0)+' events':''}" aria-pressed="${date===a.day}">${i}</button>`;
 }
 const pages=Math.max(1,Math.ceil(a.total/8)),selected=days.find(d=>d.date===a.day);
 const options=[...new Set([a.actor,...a.actors.map(x=>x.actor)].filter(Boolean))];
 const filters=`<section class="panel np-photo-filters"><form id="photo-activity-filters"><div class="np-photo-filter-fields"><div class="field"><label for="photo-activity-search">Search activity</label><input type="search" id="photo-activity-search" name="q" value="${esc(a.q)}" placeholder="Photo name or details"></div><div class="field"><label for="photo-activity-actor">Changed by</label><select id="photo-activity-actor" name="actor"><option value="">All team members</option>${options.map(name=>`<option value="${esc(name)}" ${name===a.actor?'selected':''}>${esc(displayActor(name))}</option>`).join('')}</select></div><div class="field"><label for="photo-activity-action">Action</label><select id="photo-activity-action" name="action">${[['','All actions'],['upload','Uploads'],['edit','Edits'],['rename','Renames'],['delete','Deletions']].map(([value,label])=>`<option value="${value}" ${value===a.action?'selected':''}>${label}</option>`).join('')}</select></div></div><div class="np-photo-filter-bottom"><span></span><div><button type="button" class="button ghost" data-action="photo-activity-clear">Clear Filters</button><button type="submit" class="button secondary">${icon('search',16)} Search</button></div></div></form></section>`;
 let content;
 if(a.status==='error')content=`<div class="empty-state" role="alert"><h3>Couldn’t load photo activity</h3><p>${esc(a.error)}</p><button class="button primary" data-action="photo-activity-retry">Try Again</button></div>`;
 else if(a.status!=='ready')content=loadingSkeleton('employees','photo activity');
 else content=`${a.day?`<div class="callout"><p>${esc(selected?.summary||'No activity for this date and these filters.')}</p></div>`:''}${a.items.length?`<div class="np-photo-table" tabindex="0" role="region" aria-label="Photo activity, scroll horizontally"><table><thead><tr><th>Date & Time</th><th>Action</th><th>Photo</th><th>Changed by</th></tr></thead><tbody>${a.items.map(e=>`<tr><td>${formatDate(e.created_at)}<span class="history-cell-secondary">${esc(e.created_at.slice(11,16))}</span></td><td>${esc(({upload:'Photo uploaded',edit:'Details edited',rename:'Photo renamed',delete:'Photo deleted'})[e.action]||e.action)}</td><td>${e.photo_id?`<button class="text-button" data-action="photo-history" data-id="${e.photo_id}">${esc(e.photo_display_name||'Photo #'+e.photo_id)}</button>`:esc(e.photo_display_name||'Photo unavailable')}</td><td>${esc(displayActor(e.actor))}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty-state"><h3>No photo activity</h3><p>No events match these filters.</p></div>'}`;
 return filters+`<div class="np-photo-activity-layout"><section class="panel"><div class="panel-header"><button class="icon-button" data-action="photo-activity-month" data-step="-1" aria-label="Previous month">${icon('chevron-left',16)}</button><h2>${month.toLocaleDateString('en-US',{month:'long',year:'numeric'})}</h2><button class="icon-button" data-action="photo-activity-month" data-step="1" aria-label="Next month">${icon('chevron-right',16)}</button></div><div class="np-photo-calendar"><div class="np-photo-week">${['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(d=>`<span>${d}</span>`).join('')}</div><div class="np-photo-days">${cells}</div></div><div class="panel-footer"><button class="button ghost" data-action="photo-activity-day" data-date="">All dates</button></div>${a.status==='ready'?`<div class="callout"><p>${esc(a.digest.summary)}</p></div>`:''}</section><section class="panel"><div class="panel-header"><div><h2>Photo Activity Log</h2><p>${a.day?formatDate(a.day):'All dates'} · Newest first</p></div>${a.status==='ready'?`<span class="count-label">${a.total} events</span>`:''}</div>${content}<div class="np-photo-pagination"><span>${a.status==='ready'?'Page '+a.page+' of '+pages:''}</span><div><button class="button secondary small" data-action="photo-activity-gallery" ${a.status!=='ready'||!a.items.some(e=>e.photo_id)?'disabled':''}>Photos on this page</button><button class="button secondary small" data-action="photo-activity-page" data-step="-1" ${a.status!=='ready'||a.page===1?'disabled':''}>Previous</button><button class="button secondary small" data-action="photo-activity-page" data-step="1" ${a.status!=='ready'||a.page>=pages?'disabled':''}>Next</button></div></div></section></div>`;
}

let photoModalVersion=0,activityGallery=null;
function activityGalleryHtml(data,c){
 return `<div class="np-photo-grid">${data.found.map(p=>{const name=p.display_name||p.original_filename||'Photo';return `<article class="np-photo-card"><button class="np-photo-image" data-action="photo-activity-view" data-id="${p.id}" aria-label="View ${c.esc(name)}"><img src="${photoFileUrl(p.id)}" alt="${c.esc(name)}"></button><div class="np-photo-card-body"><button class="text-button" data-action="photo-activity-view" data-id="${p.id}">${c.esc(name)}</button><button class="text-button" data-action="photo-history" data-id="${p.id}">View History</button></div></article>`;}).join('')}</div>${data.missing.length?`<p>${data.missing.length} photo(s) are no longer available.</p>`:''}`;
}
function showActivityPhoto(id,c){
 const photo=activityGallery?.found.find(p=>String(p.id)===String(id));
 if(!photo){c.openModal('Photo unavailable','<p role="alert">Reload Photos on this page to view this photo.</p>','<button class="button secondary" data-action="close-modal">Close</button>');return;}
 const name=photo.display_name||photo.original_filename||'Photo';
 c.openModal(c.esc(name),`<div class="np-photo-viewer"><p class="muted" role="status">Loading photo…</p><img src="${photoFileUrl(photo.id)}" alt="${c.esc(name)}" hidden><div class="np-photo-viewer-error" role="alert" hidden><p>Couldn’t load this photo. It may have been removed or your sign-in session may have expired.</p><button class="button secondary" data-action="photo-activity-view" data-id="${photo.id}">Try Again</button></div></div>`,'<button class="button secondary" data-action="photo-activity-gallery-back">Back to photos</button><button class="button secondary" data-action="close-modal">Close</button>');
 const viewer=document.querySelector('.np-photo-viewer'),image=viewer.querySelector('img'),status=viewer.querySelector('[role="status"]'),error=viewer.querySelector('[role="alert"]');
 viewer.closest('dialog').classList.add('photo-viewer-dialog');
 const loaded=()=>{status.hidden=true;image.hidden=false;error.hidden=true;};
 const failed=()=>{status.hidden=true;image.hidden=true;error.hidden=false;};
 image.addEventListener('load',loaded,{once:true});image.addEventListener('error',failed,{once:true});
 if(image.complete)(image.naturalWidth?loaded:failed)();
}
export async function handlePhotoActivityAction(action,el,c){
 const a=photoActivityService.state;
 switch(action){
 case 'photo-activity-view':photoModalVersion++;showActivityPhoto(el.dataset.id,c);return;
 case 'photo-activity-gallery-back':photoModalVersion++;if(activityGallery)c.openModal('Photos on this page',activityGalleryHtml(activityGallery,c),'<button class="button secondary" data-action="close-modal">Close</button>');return;
 case 'photo-activity-day':await photoActivityService.load({day:el.dataset.date||'',page:1});return;
 case 'photo-activity-month':{const [y,m]=a.month.split('-').map(Number);await photoActivityService.load({month:new Date(Date.UTC(y,m-1+Number(el.dataset.step),1)).toISOString().slice(0,7),day:'',page:1});return;}
 case 'photo-activity-page':await photoActivityService.load({page:Math.max(1,a.page+Number(el.dataset.step))});return;
 case 'photo-activity-retry':await photoActivityService.load({},true);return;
 case 'photo-activity-clear':await photoActivityService.load({q:'',actor:'',action:'',day:'',page:1});return;
 }
 const version=++photoModalVersion,history=action==='photo-history',id=el.dataset.id,page=Number(el.dataset.page)||1;
 c.openModal(history?'Photo History':'Photos on this page','<div id="photo-activity-modal" aria-live="polite">Loading…</div>','<button class="button secondary" data-action="close-modal">Close</button>');
 const target=()=>version===photoModalVersion&&document.querySelector('#photo-activity-modal');
 try{
  let html;
  if(history){
   const data=await fetchPhotoHistory(id,page);
   html=`<h3>${c.esc(data.photo_display_name||'Photo #'+id)}</h3>${data.photo_exists?'':'<p class="muted">This photo has been deleted. Its history is retained.</p>'}<div class="np-photo-table" tabindex="0" role="region" aria-label="Photo history, scroll horizontally"><table><thead><tr><th>Date & Time</th><th>Action</th><th>Changed by</th></tr></thead><tbody>${data.items.map(e=>`<tr><td>${c.esc(e.created_at)}</td><td>${c.esc(e.action)}</td><td>${c.esc(displayActor(e.actor))}</td></tr>`).join('')}</tbody></table></div>${data.total?'':'<p>No history recorded.</p>'}<div class="np-photo-pagination"><span>Page ${page} of ${Math.max(1,Math.ceil(data.total/8))}</span><div><button class="button secondary" data-action="photo-history" data-id="${id}" data-page="${page-1}" ${page<=1?'disabled':''}>Previous</button><button class="button secondary" data-action="photo-history" data-id="${id}" data-page="${page+1}" ${page*8>=data.total?'disabled':''}>Next</button></div></div>`;
  }else{
   const ids=[...new Set(a.items.map(e=>e.photo_id).filter(id=>Number.isSafeInteger(id)&&id>0))],data=await fetchPhotoBatch(ids,c.store.settings.name);
   if(version===photoModalVersion)activityGallery=data;
   html=activityGalleryHtml(data,c);
  }
  const body=target();if(body)body.innerHTML=html;
 }catch(error){const body=target();if(body)body.innerHTML=`<p role="alert">${c.esc(error.message)}</p><button class="button secondary" data-action="${history?'photo-history':'photo-activity-gallery'}" ${history?`data-id="${id}" data-page="${page}"`:''}>Try Again</button>`;}
}
