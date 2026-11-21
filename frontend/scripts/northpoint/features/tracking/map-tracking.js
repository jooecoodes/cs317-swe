import {readTrackingDevices,readTrackingLocation,readTrackingRoute} from './tracking-service.js';
import {recordChoice,recordToolbar} from '../../shared/record-ui.js';
import {loadingSkeleton} from '../../shared/loading.js';
const tracking={devices:[],status:'idle',error:'',query:'',availability:'all',updated:0,selected:'',location:null,locationStatus:'idle',locationError:'',segments:[],routeStatus:'idle',routeError:'',routeUpdated:0,follow:true};
let active=false,epoch=0,selection=0,timer,devicesController,detailController,map,tiles,pin,line,circle,context,refreshing,view=null,firstDeviceFocus=false;
const age=n=>n<60?n+'s ago':n<3600?Math.floor(n/60)+'m ago':n<86400?Math.floor(n/3600)+'h ago':Math.floor(n/86400)+'d ago';
const selectedRow=()=>tracking.devices.find(d=>d.device_id===tracking.selected);
function statusLabel(value){return value==='online'?'Online':value==='disconnected'?'Offline':'Not connected';}
function devicesHtml(c){
 if(tracking.status==='idle'||tracking.status==='loading')return loadingSkeleton('form','tracking devices');
 if(tracking.status==='error')return `<div class="tracking-empty" role="alert"><strong>Couldn’t load devices</strong><p>${c.esc(tracking.error)}</p><button class="button secondary" data-action="tracking-refresh">Try again</button></div>`;
 const q=tracking.query.toLowerCase(),rows=tracking.devices.filter(d=>(!q||[d.device_id,d.tracker||''].join(' ').toLowerCase().includes(q))&&(tracking.availability==='all'||tracking.availability===d.status));
 if(!rows.length)return `<div class="tracking-empty">${c.icon('map-pin',30)}<strong>${tracking.devices.length?'No matching devices':'No devices reporting yet'}</strong><p>${tracking.devices.length?'Try another search or clear the filters.':'Start tracking in the phone app to see its location here.'}</p>${tracking.query?`<button class="button secondary" data-action="tracking-lookup">Look up this device ID</button>`:''}</div>`;
 return rows.map(d=>`<button class="tracking-device ${d.device_id===tracking.selected?'selected':''}" data-action="tracking-select" data-id="${c.esc(d.device_id)}" aria-pressed="${d.device_id===tracking.selected}"><span class="tracking-device-top"><strong>${c.esc(d.tracker||d.device_id)}</strong><span class="tracking-status ${d.status==='online'?'online':'offline'}">${statusLabel(d.status)}</span></span>${d.tracker?`<span class="tracking-device-id">${c.esc(d.device_id)}</span>`:''}<span class="tracking-device-meta">Last report ${age(d.last_seen_seconds_ago)}${d.accuracy_m!=null?' · ±'+Math.round(d.accuracy_m)+' m':''}</span></button>`).join('');
}
function selectionHtml(c){
 if(!tracking.selected)return `<div class="tracking-selection-empty">${c.icon('map-pin',20)}<p>Select a device to view its location and today’s route.</p></div>`;
 const d=selectedRow(),loading=tracking.locationStatus==='loading',live=tracking.location,hasLocation=live&&live.status!=='not_connected';
 return `<div class="tracking-selected-title"><div><span class="tracking-eyebrow">Selected device</span><h3>${c.esc(d?.tracker||tracking.selected)}</h3>${d?.tracker?`<p>${c.esc(tracking.selected)}</p>`:''}</div><span class="tracking-status ${live?.status==='online'?'online':'offline'}">${loading?'Loading…':tracking.locationStatus==='error'?'Unavailable':statusLabel(live?.status)}</span></div>${tracking.locationError?`<p class="tracking-inline-error" role="alert">${c.esc(tracking.locationError)}</p>`:''}<dl class="tracking-details"><div><dt>Last report</dt><dd>${d?age(d.last_seen_seconds_ago):'Not available'}</dd></div><div><dt>GPS accuracy</dt><dd>${d?.accuracy_m!=null?'±'+Math.round(d.accuracy_m)+' m':'Not available'}</dd></div><div><dt>${live?.status==='disconnected'?'Last reported location':'Coordinates'}</dt><dd>${hasLocation?live.lat.toFixed(5)+', '+live.lon.toFixed(5):'Not available'}</dd></div><div><dt>Today’s route</dt><dd>${tracking.routeStatus==='loading'?'Loading…':tracking.routeStatus==='error'?'Unavailable':tracking.routeStatus==='ready'?tracking.segments.reduce((n,s)=>n+s.length,0)+' points':'Not loaded'}</dd></div></dl>${live?.status==='not_connected'?'<p class="tracking-note">This device has not reported a live location. Any available route is shown for today.</p>':''}${tracking.routeError?`<p class="tracking-inline-error" role="alert">${c.esc(tracking.routeError)}</p>`:''}`;
}
export function renderMapTracking(c){
 const controls=recordChoice('availability','Device status',[['all','All devices'],['online','Online only'],['disconnected','Offline only']],tracking.availability,c.esc,c.icon);
 return `<div class="tracking-page">${recordToolbar('tracking-filters','tracking',tracking.query,'Search tracker name or device ID',controls,c.esc,c.icon,{label:'Map tracking',primaryAction:`<button class="button ghost small" type="button" data-action="tracking-refresh" aria-label="Refresh map tracking" title="Refresh map tracking">${c.icon('refresh',18)}</button>`})}<div class="tracking-summary"><span><span class="tracking-dot online"></span><strong id="tracking-online">—</strong> online</span><span><span class="tracking-dot offline"></span><strong id="tracking-offline">—</strong> offline</span><span id="tracking-updated">Getting device data…</span></div><div class="tracking-layout"><section class="panel tracking-devices-panel" aria-labelledby="tracking-devices-heading"><div class="panel-header"><h2 id="tracking-devices-heading">Devices</h2><span class="count-label" id="tracking-count">—</span></div><div id="tracking-devices" class="tracking-devices" aria-live="polite">${devicesHtml(c)}</div><p class="tracking-list-note">Select a device to see it on the map.</p></section><section class="panel tracking-map-panel" aria-labelledby="tracking-map-heading"><div class="panel-header"><div><h2 id="tracking-map-heading">Live map</h2><p id="tracking-map-status">Select a device to begin</p></div><button class="button secondary small" data-action="tracking-fit" disabled>${c.icon('locate',16)} Fit route</button></div><div class="tracking-map-wrap"><div id="tracking-map" class="tracking-map" role="region" aria-label="Device locations and today’s route"></div><p id="tracking-tile-error" class="tracking-tile-error" role="alert" hidden>Map tiles couldn’t load. Check your internet connection. <button class="text-button" data-action="tracking-tiles">Retry map</button></p></div><div class="tracking-map-options"><span><span class="tracking-route-key"></span> Today’s route · Asia/Manila</span><label><input type="checkbox" id="tracking-follow" ${tracking.follow?'checked':''}> Keep device centered</label></div><div id="tracking-selected" class="tracking-selected" aria-live="polite">${selectionHtml(c)}</div></section></div><p class="tracking-footnote">Device locations update every 5 seconds while this page is open. An online device has reported within the last 15 seconds.</p></div>`;
}
function paint(){
 if(!active||!context||!document.querySelector('#tracking-map'))return;
 const focused=document.activeElement?.closest?.('.tracking-device')?.dataset.id;
 document.querySelector('#tracking-devices').innerHTML=devicesHtml(context);
 if(focused)[...document.querySelectorAll('.tracking-device')].find(el=>el.dataset.id===focused)?.focus({preventScroll:true});
 document.querySelector('#tracking-count').textContent=tracking.status==='ready'?String(tracking.devices.length):'—';
 document.querySelector('#tracking-online').textContent=tracking.status==='ready'?String(tracking.devices.filter(d=>d.status==='online').length):'—';
 document.querySelector('#tracking-offline').textContent=tracking.status==='ready'?String(tracking.devices.filter(d=>d.status==='disconnected').length):'—';
 document.querySelector('#tracking-updated').textContent=tracking.status==='error'?'Device data unavailable':tracking.updated?'Updated '+new Date(tracking.updated).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',second:'2-digit',timeZone:'Asia/Manila'}):'Getting device data…';
 document.querySelector('#tracking-selected').innerHTML=selectionHtml(context);
 document.querySelector('#tracking-map-status').textContent=!tracking.selected?'Select a device to begin':tracking.locationStatus==='error'?'Location unavailable':tracking.locationStatus==='loading'?'Getting the latest location…':tracking.location?.status==='online'?'Live location · Updates every 5 seconds':tracking.location?.status==='disconnected'?'Offline · Showing the last reported location':'No live location reported';
 document.querySelector('[data-action="tracking-fit"]').disabled=!tracking.segments.length&&!pin;
}
function updateLayers(){
 if(!map)return;
 const L=window.L,live=tracking.location,d=selectedRow();
 line.setLatLngs(tracking.segments);
 if(live&&live.status!=='not_connected'&&tracking.locationStatus==='ready'){
  const point=[live.lat,live.lon],online=live.status==='online';
  if(!pin){pin=L.marker(point,{icon:L.divIcon({className:'tracking-pin',html:'<span></span>',iconSize:[24,24],iconAnchor:[12,12]})}).addTo(map);}
  pin.setLatLng(point);pin.getElement()?.classList.toggle('offline',!online);
  const label=document.createElement('span');label.textContent=(d?.tracker||tracking.selected)+' · '+statusLabel(live.status);pin.bindTooltip(label);
  if(d?.accuracy_m!=null){if(!circle)circle=L.circle(point,{radius:d.accuracy_m,color:'#527ca9',weight:1,fillOpacity:.08}).addTo(map);circle.setLatLng(point).setRadius(d.accuracy_m);}else if(circle){circle.remove();circle=null;}
  if(tracking.follow||firstDeviceFocus){map.setView(point,firstDeviceFocus?16:map.getZoom(),{animate:false});firstDeviceFocus=false;}
 }else{pin?.remove();circle?.remove();pin=null;circle=null;}
}
async function loadDevices(token){
 devicesController?.abort();devicesController=new AbortController();
 try{const rows=await readTrackingDevices(devicesController.signal);if(!active||token!==epoch)return;Object.assign(tracking,{devices:rows,status:'ready',error:'',updated:Date.now()});}
 catch(error){if(!active||token!==epoch||error.name==='AbortError')return;Object.assign(tracking,{devices:[],status:'error',error:error.message,updated:0});}
 if(active&&token===epoch){paint();updateLayers();}
}
async function loadSelected(token,force=false){
 if(!tracking.selected)return;
 const id=tracking.selected,ticket=++selection;detailController?.abort();detailController=new AbortController();const signal=detailController.signal;
 const routeDue=force||tracking.routeStatus==='idle'||Date.now()-tracking.routeUpdated>=15000;
 const replies=await Promise.allSettled([readTrackingLocation(id,signal),routeDue?readTrackingRoute(id,signal):Promise.resolve(null)]);
 if(!active||token!==epoch||ticket!==selection||id!==tracking.selected)return;
 const [position,route]=replies;
 if(position.status==='fulfilled')Object.assign(tracking,{location:position.value,locationStatus:'ready',locationError:''});
 else Object.assign(tracking,{location:null,locationStatus:'error',locationError:position.reason.message});
 if(routeDue){tracking.routeUpdated=Date.now();if(route.status==='fulfilled')Object.assign(tracking,{segments:route.value,routeStatus:'ready',routeError:''});else Object.assign(tracking,{segments:[],routeStatus:'error',routeError:route.reason.message});}
 paint();updateLayers();
}
async function refreshTracking(force=false){
 if(!active||refreshing)return refreshing;
 const token=epoch;
 const job=Promise.allSettled([loadDevices(token),loadSelected(token,force)]);refreshing=job;
 try{await job;}finally{if(refreshing===job)refreshing=null;}
}
function schedule(){clearTimeout(timer);if(!active||document.hidden)return;timer=setTimeout(async()=>{await refreshTracking();schedule();},5000);}
function visibility(){clearTimeout(timer);if(document.hidden){devicesController?.abort();detailController?.abort();selection++;}else if(active){void refreshTracking().finally(schedule);}}
export function stopMapTracking(){
 active=false;epoch++;selection++;clearTimeout(timer);devicesController?.abort();detailController?.abort();refreshing=null;document.removeEventListener('visibilitychange',visibility);
 if(map){view={center:map.getCenter(),zoom:map.getZoom()};map.remove();}map=null;tiles=null;pin=null;line=null;circle=null;context=null;
}
export function mountMapTracking(c){
 if(active&&map?.getContainer()===document.querySelector('#tracking-map'))return;
 stopMapTracking();context=c;active=true;const token=epoch;
 const root=document.querySelector('#tracking-map');if(!root)return;
 if(!window.L){root.innerHTML='<div class="tracking-empty" role="alert"><strong>Couldn’t open the map</strong><p>Reload Northpoint and try again.</p></div>';return;}
 const L=window.L;map=L.map(root,{scrollWheelZoom:false}).setView(view?.center||[8.4803,124.6498],view?.zoom||13);map.attributionControl.setPrefix(false);
 if (!globalThis.NORTHPOINT_CONFIG?.READ_ONLY_PREVIEW) {
  const attribution=document.createElement('a');attribution.setAttribute('href','https://www.openstreetmap.org/copyright');attribution.setAttribute('target','_blank');attribution.setAttribute('rel','noopener noreferrer');attribution.textContent='OpenStreetMap contributors';
  tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© '+attribution.outerHTML}).addTo(map);
  tiles.on('tileerror',()=>{if(active&&token===epoch)document.querySelector('#tracking-tile-error').hidden=false;});
 }
 line=L.polyline([],{color:'#285587',weight:4,opacity:.85}).addTo(map);
 tracking.status='loading';tracking.devices=[];tracking.updated=0;
 if(tracking.selected){tracking.locationStatus='loading';tracking.location=null;tracking.routeStatus='loading';tracking.segments=[];tracking.routeUpdated=0;}
 paint();document.addEventListener('visibilitychange',visibility);void refreshTracking(true).finally(schedule);
}
export function handleTrackingAction(action,el,c){
 switch(action){
 case 'tracking-refresh':void refreshTracking(true);return;
 case 'tracking-select':case 'tracking-lookup':{
  const id=(action==='tracking-select'?el.dataset.id:tracking.query).trim();if(!id||id.length>200||['.','..'].includes(id)){c.toast('Enter a valid device ID.','alert');return;}
  Object.assign(tracking,{selected:id,location:null,locationStatus:'loading',locationError:'',segments:[],routeStatus:'loading',routeError:'',routeUpdated:0});firstDeviceFocus=true;paint();updateLayers();void loadSelected(epoch,true);return;
 }

 case 'tracking-fit':{const points=tracking.segments.flat();if(points.length)map?.fitBounds(points,{padding:[28,28],maxZoom:17});else if(pin)map?.setView(pin.getLatLng(),16);return;}
 case 'tracking-tiles':document.querySelector('#tracking-tile-error').hidden=true;tiles?.redraw();return;
 }
}
export function handleTrackingSubmit(values,c){tracking.query=String(values.query||'').trim();tracking.availability=['online','disconnected'].includes(values.availability)?values.availability:'all';c.render();}
export function handleTrackingChange(event){if(event.target.id!=='tracking-follow')return false;tracking.follow=event.target.checked;updateLayers();return true;}
