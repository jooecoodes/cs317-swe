import {canOpen,currentRole} from '../../../shared/permissions.js';
import {recordChoice,recordToolbar} from '../../shared/record-ui.js';
import {displayActor} from '../../auth/session.js';
import {photoActivityService} from './photo-activity.js';
import {renderPhotoActivity,handlePhotoActivityAction} from './photo-activity-view.js';
import {businessDate} from '../reports/yesterday.js';
import {photoData,loadPhotos,photoRequest,normalizePhoto} from './photo-service.js';
import {loadingSkeleton} from '../../shared/loading.js';
const photoState={get items(){return photoData.items;},tab:'photos',filters:{search:'',owner:'',tag:'',order:'newest',timeframe:'all'},view:'grid',page:1};
export function clearPhotoDraft(){}
function photoAuthorLink(owner,esc){return `<button type="button" class="text-button np-photo-author" data-action="photo-author" data-author="${esc(owner)}" aria-label="View photos by ${esc(displayActor(owner))}">${esc(displayActor(owner))}</button>`;}

const photoBytes=value=>value>=1048576?(value/1048576).toFixed(1)+' MB':Math.max(1,Math.round(value/1024))+' KB';
function photoDateTime(value){
 const date=new Date(value);
 if(!Number.isFinite(date.getTime()))return 'Time unavailable';
 return new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Manila',year:'numeric',month:'long',day:'numeric',hour:'numeric',minute:'2-digit',hour12:true}).format(date).replace(' at ', ', ');
}
export function photoSourceBadge(p){
 const source=p.mobileMetadata?.source;
 const kind=source==='camera'?'camera':source==='gallery'?'gallery':'unknown';
 const label=kind==='camera'?'Photo Upload':kind==='gallery'?'Gallery Upload':'Source not recorded';
 return `<span class="np-photo-source np-photo-source--${kind}">${label}</span>`;
}
function parsePhotoMs(value){
 if(!value||typeof value!=='string')return NaN;
 return Date.parse(/(?:Z|[+-]\d\d:\d\d)$/.test(value)?value:value+'+08:00');
}
function photoUploadedMs(p){const ms=parsePhotoMs(p.mobileMetadata?.uploaded_at);return Number.isFinite(ms)?ms:p.created;}
export function photoExifWarningBadge(p,esc){
 const m=p.mobileMetadata;
 if(m?.source!=='gallery')return '';
 const style='display:inline-flex;align-items:center;gap:4px;margin-top:6px;margin-bottom:4px;padding:4px 9px;border-radius:999px;background:#fff4db;border:1px solid #d99b26;color:#7a4d00;font-size:0.8rem;font-weight:600;line-height:1.35;';
 const exifRaw=p.exifTakenAt||m.exif_taken_at||null;
 const exifMs=parsePhotoMs(exifRaw);
 if(!Number.isFinite(exifMs))return `<span class="np-photo-warning" style="${style}">⚠️ Original time unverified (No EXIF)</span>`;
 const refMs=parsePhotoMs(m.selected_at||m.uploaded_at);
 const compareMs=Number.isFinite(refMs)?refMs:p.created;
 if(Number.isFinite(compareMs)&&compareMs-exifMs>30*60*1000)return `<span class="np-photo-warning" style="${style}">⚠️ Taken earlier: ${esc(photoDateTime(exifMs))}</span>`;
 return '';
}
export function photoOfflineSyncBadge(p,esc){
 const m=p.mobileMetadata;
 if(m?.source!=='camera')return '';
 const selectedMs=parsePhotoMs(m.selected_at),uploadedMs=parsePhotoMs(m.uploaded_at);
 if(!Number.isFinite(selectedMs)||!Number.isFinite(uploadedMs)||uploadedMs-selectedMs<15*60*1000)return '';
 const style='display:inline-flex;align-items:center;gap:4px;margin-top:6px;margin-bottom:4px;padding:4px 9px;border-radius:999px;background:#edf3fa;border:1px solid #b8c9dd;color:#234e7d;font-size:0.8rem;font-weight:600;line-height:1.35;white-space:normal;';
 return `<span class="np-photo-offline-sync" style="${style}">Taken ${esc(photoDateTime(selectedMs))} \u00b7 Synced offline</span>`;
}
function photoDescription(p){
 const m=p.mobileMetadata;
 if(!m)return p.description||'No description added.';
 return `${m.source==='camera'?'Camera photo selected':m.source==='gallery'?'Gallery photo selected':'Photo selected'}: ${photoDateTime(m.selected_at)} (Philippine time)`;
}
function photoRefreshBar(esc){return `<div class="np-photo-refresh" aria-busy="${photoData.refreshing}"><button class="button secondary" data-action="photo-refresh" ${photoData.refreshing?'disabled':''}>${photoData.refreshing?'<span class="np-refresh-spinner" aria-hidden="true"></span>Refreshing…':'Refresh Photos'}</button><span role="status" aria-live="polite" class="np-pull-status">${photoData.refreshing?'Checking for new photos…':photoData.error?'Refresh failed. Your previous photos are still shown.':photoData.lastUpdated?'Updated '+esc(photoDateTime(photoData.lastUpdated))+' (Philippine time). Pull down or scroll up at the top to refresh.':'Pull down or scroll up at the top to refresh.'}</span></div>`;}
function photoTabs(){return `<div class="report-tabs-container"><div class="tabs report-tabs" role="tablist" aria-label="Photo Library sections">${[['photos','Photos'],['activity','Activity Log']].map(([id,label])=>`<button class="tab ${photoState.tab===id?'active':''}" role="tab" aria-selected="${photoState.tab===id}" data-action="photo-tab" data-tab="${id}">${label}</button>`).join('')}</div></div>`;}
function photoRows(showLocation){const f=photoState.filters;return photoState.items.filter(p=>(!f.search||`${p.name} ${p.owner} ${showLocation?p.description:''} ${p.tags.join(' ')}`.toLowerCase().includes(f.search.toLowerCase()))&&(!f.owner||p.owner===f.owner)&&(!f.tag||p.tags.some(t=>t.toLowerCase()===f.tag.toLowerCase()))).sort((a,b)=>f.order==='oldest'?photoUploadedMs(a)-photoUploadedMs(b):f.order==='name'?a.name.localeCompare(b.name):f.order==='size'?b.size-a.size:photoUploadedMs(b)-photoUploadedMs(a));}
export function renderPhotoLibrary({icon,esc,formatDate}){
 const showLocation=canOpen('tracking');
 const uploadNotice=currentRole()==='supervisor'?' <div class="callout workspace-access-notice" role="status"><p><strong>Submit proof photo</strong><br>Browser uploads are currently unavailable. Contact your administrator for help submitting proof.</p></div>':'';
 const tabs=(canOpen('history')?photoTabs():'')+uploadNotice;
 if(canOpen('history')&&photoState.tab==='activity')return tabs+renderPhotoActivity({icon,esc,formatDate});
 if(photoData.status!=='ready')return tabs+(photoData.status==='error'?`<section class="panel"><div class="empty-state" role="alert"><h3>Couldn’t load photos</h3><p>${esc(photoData.error)}</p><button class="button primary" data-action="photo-retry">Try Again</button></div></section>`:loadingSkeleton('employees','photo library'));
 const f=photoState.filters,rows=photoRows(showLocation),pages=Math.max(1,Math.ceil(rows.length/8));photoState.page=Math.min(photoState.page,pages);const start=(photoState.page-1)*8,shown=rows.slice(start,start+8),size=photoState.items.reduce((total,p)=>total+p.size,0);
 const choices=(name,label,values,current)=>recordChoice(name,label,values,current||'',esc,icon);
 const owners=[...new Set((photoData.stats.employee_counts||[]).map(p=>p.owner).filter(Boolean))].sort(),tags=[...new Set(['Photo Upload','Gallery Upload',...photoState.items.flatMap(p=>p.tags)])];
 const controls=choices('timeframe','Upload period',[['today','Uploads today'],['week','Uploads this week'],['all','All uploads']],f.timeframe||'all')+choices('owner','Owner',[['','All owners'],...owners.map(name=>[name,displayActor(name)])],f.owner)+choices('tag','Tag',[['','All tags'],...tags.map(tag=>[tag,tag])],f.tag)+choices('order','Order by',[['newest','Most recent first'],['oldest','Least recent first'],['name','Photo name'],['size','Largest file first']],f.order);
 const toolbar=recordToolbar('photo-filters','photos',f.search,showLocation?'Search title, employee name, description, or tags':'Search title, employee name, or tags',controls,esc,icon,{queryName:'search',clearAction:'photo-clear',clearLabel:'Clear Filters',label:'Photo library'});
 const card=p=>`<article class="np-photo-card"><button class="np-photo-image" data-action="photo-details" data-id="${p.id}" aria-label="View ${esc(p.name)}"><img src="${p.url}" alt="${esc(p.name)}"></button><div class="np-photo-card-body">${photoSourceBadge(p)}<button class="text-button" data-action="photo-details" data-id="${p.id}">${esc(p.name)}</button><p class="np-photo-meta"><span>By: ${photoAuthorLink(p.owner,esc)}</span><time datetime="${new Date(photoUploadedMs(p)).toISOString()}" title="Uploaded (Philippine time)">${esc(photoDateTime(photoUploadedMs(p)))}</time>${showLocation?`<span class="np-photo-place"><strong>Place:</strong> ${esc(p.locationName||'Place name unavailable')}</span>`:''}<span class="np-photo-meta-size">${photoBytes(p.size)}</span>${photoExifWarningBadge(p,esc)}</p><div class="np-photo-tags">${p.tags.filter(t=>!['Photo Upload','Gallery Upload'].includes(t)).slice(0,3).map(t=>`<span>${esc(t)}</span>`).join('')}</div></div></article>`;
 const metrics=[['Total photos',photoData.stats.total_photos,'image'],['Storage used',(photoData.stats.total_bytes/1048576).toFixed(1)+' MB','archive'],['Added today',photoData.stats.uploads_today,'calendar']];
 return tabs+`<div class="photo-library"><section class="np-photo-metrics" aria-label="Photo summary">${metrics.map(([label,value,ico])=>`<div><span class="np-photo-metric-icon">${icon(ico,23)}</span><div><p>${label}</p><strong>${value}</strong></div></div>`).join('')}</section>${toolbar}${photoRefreshBar(esc)}${photoData.error?`<p class="form-error show" role="alert">${esc(photoData.error)}</p>`:''}<section class="panel np-photo-results" aria-labelledby="photos-heading"><div class="panel-header"><div class="np-photo-panel-title"><h2 id="photos-heading">Employee photos</h2><span class="count-label">${rows.length} ${rows.length===1?'photo':'photos'} · ${rows.filter(p=>businessDate(photoUploadedMs(p))===(photoData.stats.business_date||businessDate())).length} uploads today</span></div><div class="np-photo-views" aria-label="Photo view"><button class="icon-button ${photoState.view==='grid'?'selected':''}" data-action="photo-view" data-view="grid" aria-label="Grid view" aria-pressed="${photoState.view==='grid'}">${icon('dashboard',17)}</button><button class="icon-button ${photoState.view==='list'?'selected':''}" data-action="photo-view" data-view="list" aria-label="List view" aria-pressed="${photoState.view==='list'}">${icon('list',19)}</button></div></div>${shown.length?(photoState.view==='grid'?`<div class="np-photo-grid">${shown.map(card).join('')}</div>`:`<div class="np-photo-table" tabindex="0" role="region" aria-label="Photo list, scroll horizontally"><table><thead><tr><th>Photo name</th><th>Owner</th><th>Uploaded (PHT)</th><th>File size</th><th>Action</th></tr></thead><tbody>${shown.map(p=>`<tr><td><div><img src="${p.url}" alt=""><strong>${esc(p.name)}</strong>${photoSourceBadge(p)}</div></td><td>${photoAuthorLink(p.owner,esc)}</td><td>${esc(photoDateTime(photoUploadedMs(p)))}${showLocation?`<p class="np-photo-place"><strong>Place:</strong> ${esc(p.locationName||'Place name unavailable')}</p>`:''}</td><td>${photoBytes(p.size)}</td><td><button class="button ghost small" data-action="photo-details" data-id="${p.id}">View Photo</button></td></tr>`).join('')}</tbody></table></div>`):`<div class="np-photo-empty"><span>${icon('image',32)}</span><h3>${photoState.items.length?'No matching photos':'A clearer view of your workplace'}</h3><p>${photoState.items.length?'Try a different search or clear your filters.':'Photos uploaded by your team will appear here.'}</p>${photoState.items.length?`<button class="button secondary" data-action="photo-clear">${icon('refresh',17)} Clear Filters</button>`:'<p>Employees send photos using the Northpoint Android app.</p>'}</div>`}<div class="np-photo-pagination"><span>${rows.length?`${start+1}–${Math.min(start+8,rows.length)} of ${rows.length} photos`:'No photos to display'}</span><div><button class="button secondary small" data-action="photo-page" data-step="-1" ${photoState.page===1?'disabled':''}>${icon('chevron-left',14)} Previous</button><button class="button secondary small" data-action="photo-page" data-step="1" ${photoState.page===pages?'disabled':''}>Next ${icon('chevron-right',14)}</button></div></div></section></div>`;
}
export async function handlePhotoAction(action,el,c){const {icon,esc,openModal,closeModal,render,formatDate}=c;
 if(action.startsWith('photo-activity-')||action==='photo-history'){await handlePhotoActivityAction(action,el,c);return;}
 switch(action){
 case 'photo-tab':photoState.tab=el.dataset.tab;c.render();if(photoState.tab==='activity')await photoActivityService.load({},true);break;
 case 'photo-author':{
 const owner=el.dataset.author;if(!owner)return;
 closeModal();photoState.tab='photos';photoState.page=1;
 photoState.filters={search:'',owner,tag:'',order:'newest',timeframe:'all'};
 await loadPhotos(true,'all');render();
 requestAnimationFrame(()=>document.querySelector('#photos-heading')?.scrollIntoView({block:'start'}));
 break;
 }
 case 'photo-refresh':photoState.page=1;await loadPhotos(true);render();requestAnimationFrame(()=>document.querySelector('#photos-heading')?.scrollIntoView({behavior:'smooth',block:'start'}));break;
 case 'photo-retry':await loadPhotos(true);break;
 case 'photo-clear':clearTimeout(photoSearchTimer);photoState.filters={search:'',owner:'',tag:'',order:'newest',timeframe:'all'};photoState.page=1;await loadPhotos(true,'all');render();break;
 case 'photo-view':photoState.view=el.dataset.view;render();break;
 case 'photo-page':photoState.page+=Number(el.dataset.step);render();requestAnimationFrame(()=>document.querySelector('#photos-heading')?.scrollIntoView({behavior:'smooth',block:'start'}));break;
 case 'photo-details':{const showLocation=canOpen('tracking');let p;try{p=normalizePhoto(await photoRequest('/photos/'+encodeURIComponent(el.dataset.id)));}catch(error){openModal('Photo unavailable',`<p role="alert">${esc(error.message||'This photo could not be loaded. It may have been deleted.')}</p>`,'<button class="button secondary" data-action="close-modal">Close</button>');return;}openModal('Photo Details',`<img class="np-photo-detail" src="${p.url}" alt="${esc(p.name)}"><h3 class="np-photo-detail-title">${esc(p.name)}</h3>${photoSourceBadge(p)}<p class="np-photo-detail-description">By: ${photoAuthorLink(p.owner,esc)}</p>${showLocation?`<p class="np-photo-detail-description">${esc(photoDescription(p))}</p>`:''}<p class="np-photo-detail-description"><strong>Photo time (PHT):</strong> ${esc(photoDateTime(p.created))}</p>${p.mobileMetadata?.uploaded_at?`<p class="np-photo-detail-description"><strong>Uploaded (PHT):</strong> ${esc(photoDateTime(p.mobileMetadata.uploaded_at))}</p>`:''}${showLocation?`<p class="np-photo-detail-description np-photo-place"><strong>Place:</strong> ${esc(p.locationName||'Place name unavailable')}</p>${locationSnapshot(p,esc)}`:''}${photoExifWarningBadge(p,esc)}<dl class="np-photo-detail-meta"><div><dt>File size</dt><dd>${photoBytes(p.size)}</dd></div><div><dt>Tags</dt><dd>${esc(p.tags.join(', ')||'No tags')}</dd></div></dl>`,`${showLocation?`<a class="button secondary" href="${p.url.replace(/\/file$/,'/download')}" download>Download</a>`:''}${canOpen('history')?`<button class="button secondary" data-action="photo-history" data-id="${p.id}">View History</button>`:''}<button class="button secondary" data-action="close-modal">Close</button>`);if(showLocation)mountPhotoLocationMap(p);break;}

 }
}
export async function handlePhotoSubmit(form,values,c){
 if(form.id==='photo-activity-filters'){await photoActivityService.load({q:values.q||'',actor:values.actor||'',action:values.action||'',page:1});return;}
 if(form.id==='photo-filters'){const timeframe=values.timeframe||'all',changed=timeframe!==(photoState.filters.timeframe||'all');photoState.filters={...photoState.filters,...values,timeframe};photoState.page=1;if(changed)await loadPhotos(true,timeframe);c.render();return;}
}

function locationSnapshot(photo,esc) {
 const m=photo.mobileMetadata;if(!validPhotoLocation(m))return '';
 const lat=m.latitude.toFixed(6),lon=m.longitude.toFixed(6),url=`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=16/${lat}/${lon}`;
 return `<section class="np-location-snapshot" aria-label="Photo location map"><h3>Location when photo was selected</h3><p>Nearby streets and places</p><div class="np-photo-location-map" tabindex="0" aria-label="Map with a recorded location pin and a 80 metre surrounding radius"></div><p class="np-photo-map-status" role="status">Loading street map…</p><details class="np-map-details"><summary>Map Details &amp; Accuracy</summary><div><p>Use + and − to zoom. Drag the map to explore nearby streets.</p><p><strong>Blue circle: 50 m surrounding area</strong><br>This circle shows nearby context, not GPS accuracy.</p><p><strong>Coordinates:</strong> ${esc(lat)}, ${esc(lon)}<br><strong>GPS accuracy:</strong> ±${esc(Math.round(m.accuracy_m))} metres</p><p>Street and place names appear where available on the map. The pin marks the recorded coordinates; a nearby label is not a verified address.</p><p>For gallery photos, this is where the employee selected the image, not necessarily where it was taken.</p></div></details><a href="${url}" target="_blank" rel="noopener noreferrer">Open larger map</a></section>`;
}
function validPhotoLocation(m) {
 return !!m&&Number.isFinite(m.latitude)&&Number.isFinite(m.longitude)&&Math.abs(m.latitude)<=90&&Math.abs(m.longitude)<=180;
}
let disposePhotoLocationMap=()=>{};
function mountPhotoLocationMap(photo) {
 disposePhotoLocationMap();
 const root=document.querySelector('.np-photo-location-map');
 if(!root||!validPhotoLocation(photo.mobileMetadata))return;
 const status=root.parentElement.querySelector('.np-photo-map-status'),L=window.L;
 if(!L){status.textContent='Map unavailable. Use Open larger map below.';return;}
 const m=photo.mobileMetadata,point=[m.latitude,m.longitude];
 let map,resizeObserver,observer,frame,timer,disposed=false;
 const cleanup=()=>{if(disposed)return;disposed=true;clearTimeout(timer);cancelAnimationFrame(frame);resizeObserver?.disconnect();observer?.disconnect();map?.remove();};
 disposePhotoLocationMap=cleanup;
 try {
  map=L.map(root,{scrollWheelZoom:false,zoomControl:true}).setView(point,16);
  map.attributionControl.setPrefix(false);
  if (globalThis.NORTHPOINT_CONFIG?.READ_ONLY_PREVIEW) status.textContent='Sample coordinates · Street map disabled in development preview.';
  else {
   const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>'});
   let tileFailed=false;
   tiles.on('tileerror',()=>{tileFailed=true;status.textContent='Some map tiles could not load. Check your internet connection or open the larger map.';});
   tiles.on('tileload',()=>{clearTimeout(timer);if(!tileFailed)status.textContent='';});
   timer=setTimeout(()=>{status.textContent='Street map is taking longer to load. Coordinates are still available below.';},12000);
   tiles.addTo(map);
  }
  const circle=L.circle(point,{radius:50,color:'#285587',weight:2,fillColor:'#3189ce',fillOpacity:0.16}).addTo(map);
  const marker=L.marker(point,{title:'Recorded photo location',alt:'Recorded photo location',icon:L.divIcon({className:'np-photo-map-pin',html:'<span></span>',iconSize:[32,42],iconAnchor:[16,42]})}).addTo(map);
  marker.bindTooltip('Recorded photo location');
  const fit=()=>{if(disposed||!root.isConnected)return;map.invalidateSize({pan:false});map.fitBounds(circle.getBounds(),{padding:[30,30],maxZoom:17,animate:false});};
  frame=requestAnimationFrame(fit);
  if(typeof ResizeObserver!=='undefined'){resizeObserver=new ResizeObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(fit);});resizeObserver.observe(root);}
  observer=new MutationObserver(()=>{if(!root.isConnected)cleanup();});
  observer.observe(document.body,{childList:true,subtree:true});
 } catch {cleanup();status.textContent='Map unavailable. Your saved coordinates are below. Use Open larger map.';}
}

// Refresh gestures are scoped to Photo Library and never run in a modal or map.
let photoPull=null,photoWheelAmount=0,photoWheelAt=0,photoGestureAt=0;
function photoGestureSurface(target){
 const library=target?.closest?.('.photo-library');
 if(!library||target.closest('button:not(.np-photo-image),a,input,select,textarea,summary,details,.leaflet-container')||document.querySelector('#modal.open,dialog[open]'))return null;
 let scroller=library.parentElement;
 while(scroller&&scroller!==document.body){const css=getComputedStyle(scroller);if(/auto|scroll/.test(css.overflowY)&&scroller.scrollHeight>scroller.clientHeight)break;scroller=scroller.parentElement;}
 return {library,scroller:scroller&&scroller!==document.body?scroller:document.scrollingElement};
}
function photoCanPull(surface){return surface&&surface.library.isConnected&&surface.scroller.scrollTop<=1&&!photoData.refreshing&&photoData.status==='ready'&&Date.now()-photoGestureAt>1500;}
function photoPullText(library,text){const node=library.querySelector('.np-pull-status');if(node)node.textContent=text;}
function photoGestureRefresh(){photoGestureAt=Date.now();photoWheelAmount=0;void loadPhotos(true);}
document.addEventListener('touchstart',event=>{
 const surface=photoGestureSurface(event.target);
 photoPull=event.touches.length===1&&photoCanPull(surface)?{...surface,x:event.touches[0].clientX,y:event.touches[0].clientY,distance:0}:null;
},{passive:true});
document.addEventListener('touchmove',event=>{
 if(!photoPull)return;
 if(event.touches.length!==1||!photoCanPull(photoPull)){photoPull=null;return;}
 const dy=event.touches[0].clientY-photoPull.y,dx=Math.abs(event.touches[0].clientX-photoPull.x);
 if(dy<=0||dx>Math.abs(dy)){photoPull.distance=0;return;}
 photoPull.distance=dy;
 if(event.cancelable)event.preventDefault();
 photoPullText(photoPull.library,dy>=80?'Release to refresh photos':'Pull a little further to refresh');
},{passive:false});
document.addEventListener('touchend',()=>{const pull=photoPull;photoPull=null;if(pull&&pull.distance>=80&&photoCanPull(pull))photoGestureRefresh();else if(pull)photoPullText(pull.library,'Pull down or scroll up at the top to refresh.');},{passive:true});
document.addEventListener('touchcancel',()=>{if(photoPull)photoPullText(photoPull.library,'Pull down or scroll up at the top to refresh.');photoPull=null;},{passive:true});
document.addEventListener('wheel',event=>{
 const surface=photoGestureSurface(event.target);
 if(event.ctrlKey||event.deltaY>=0||!photoCanPull(surface)){photoWheelAmount=0;return;}
 const now=Date.now();if(now-photoWheelAt>500)photoWheelAmount=0;photoWheelAt=now;
 photoWheelAmount+=Math.min(100,Math.abs(event.deltaY)*(event.deltaMode===1?16:event.deltaMode===2?100:1));
 if(photoWheelAmount>=160)photoGestureRefresh();
},{passive:true});

let photoSearchTimer;
document.addEventListener('input',event=>{
 if(event.target.id!=='photos-query')return;
 clearTimeout(photoSearchTimer);
 const input=event.target;
 photoSearchTimer=setTimeout(()=>{
  if(!input.isConnected)return;
  const focused=document.activeElement===input,start=input.selectionStart,end=input.selectionEnd;
  input.form.requestSubmit();
  const next=document.getElementById('photos-query');
  if(focused&&next){next.focus({preventScroll:true});if(start!==null&&end!==null)next.setSelectionRange(start,end);}
 },250);
});
