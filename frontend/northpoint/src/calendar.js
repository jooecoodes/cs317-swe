import {apiRequest} from './api-client.js';
import {createCalendarService,calendarService} from './calendar-api.js';
import {calendarSummary} from './calendar-contract.js';
import {loadingSkeleton} from './loading.js';
import {calendarMonthBounds,shiftCalendarMonth,calendarCells,calendarActionLabel,validCalendarDate} from './calendar-data.js';

export function createCalendarLoader(request=apiRequest) {
  const service=createCalendarService(request),source=service.monthState;
  const state={get month(){return source.key;},get status(){return source.status;},get rows(){return source.data||[];},get error(){return source.error;}};
  return {state,load:month=>service.loadMonth(month),invalidate:()=>service.invalidate()};
}
const monthLoader=createCalendarLoader();
let digestVersion=0,openDigest=null;
export function invalidateHistoryCalendar(){monthLoader.invalidate();calendarService.invalidate();digestVersion++;openDigest=null;}
const utcToday=()=>new Date().toISOString().slice(0,10);
const longDate=date=>new Date(date+'T12:00:00Z').toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric',timeZone:'UTC'});
const shortDate=date=>new Date(date+'T12:00:00Z').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'});
function refreshCalendar(ctx){const id=document.activeElement?.id;ctx.render();if(id?.startsWith('calendar-'))document.getElementById(id)?.focus({preventScroll:true});}

export function renderHistoryCalendar(ctx) {
  const {esc,icon}=ctx,f=ctx.getFilters('history');let month=f.month||utcToday().slice(0,7);
  try{calendarMonthBounds(month);}catch{month=utcToday().slice(0,7);}
  const state=monthLoader.state;
  if(state.month!==month||state.status==='idle')void monthLoader.load(month).then(changed=>{if(changed&&ctx.getFilters('history').tab==='calendar')refreshCalendar(ctx);});
  const title=new Date(month+'-01T12:00:00Z').toLocaleDateString('en-US',{month:'long',year:'numeric',timeZone:'UTC'}),ready=state.status==='ready';
  const data=ready?calendarCells(month,state.rows):null;
  const content=state.status==='error'?`<div class="empty-state" role="alert"><h3>Couldn’t load calendar</h3><p>${esc(state.error)}</p><button class="button primary" data-action="sec-calendar-retry">${icon('refresh',17)} Try again</button></div>`:!ready?`<div class="calendar-loading" role="status" aria-label="Loading calendar"><div class="calendar-weekdays" aria-hidden="true">${['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(day=>`<span>${day}</span>`).join('')}</div><div class="calendar-grid" aria-hidden="true">${Array.from({length:35},()=>'<span class="calendar-placeholder"></span>').join('')}</div><span class="sr-only">Loading calendar activity…</span></div>`:
    `<div class="calendar-weekdays" aria-hidden="true">${['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(day=>`<span>${day}</span>`).join('')}</div><div class="calendar-grid" role="group" aria-labelledby="calendar-month-title" aria-describedby="calendar-help">${data.cells.map(cell=>cell?`<button id="calendar-day-${cell.date}" class="calendar-day${cell.today?' is-today':''}${cell.total?' has-activity':''}" data-action="sec-calendar-day" data-date="${cell.date}" style="--day-strength:${cell.strength}" aria-label="${esc(longDate(cell.date))}: ${cell.total} ${cell.total===1?'change':'changes'}${cell.today?', today':''}"${cell.today?' aria-current="date"':''}><span class="calendar-day-number">${cell.day}</span>${cell.today?'<span class="calendar-today-dot" aria-hidden="true"></span>':''}</button>`:'<span class="calendar-blank" aria-hidden="true"></span>').join('')}</div>`;
  return `<section id="history-log-panel" class="panel history-calendar" role="tabpanel" aria-labelledby="history-tab-calendar" aria-busy="${state.status==='loading'}"><div class="calendar-toolbar"><div class="calendar-month-controls"><button id="calendar-previous" class="icon-button" data-action="sec-calendar-month" data-step="-1" aria-label="Previous month">${icon('chevron-left',20)}</button><h2 id="calendar-month-title" aria-live="polite">${esc(title)}</h2><button id="calendar-next" class="icon-button" data-action="sec-calendar-month" data-step="1" aria-label="Next month">${icon('chevron-right',20)}</button><button id="calendar-today" class="button secondary small" data-action="sec-calendar-today">Today</button></div><p id="calendar-help">Choose a day to see its activity.</p></div><div class="calendar-body">${content}</div><div class="calendar-footer"><p role="status">${data?`${data.total} ${data.total===1?'change':'changes'} across ${data.activeDays} ${data.activeDays===1?'day':'days'} this month.`:'Activity by day'}</p><div class="calendar-legend" aria-label="Darker blue means more changes"><span>Fewer</span>${[0,.1,.22,.36,.48].map(strength=>`<i aria-hidden="true" style="--day-strength:${strength}"></i>`).join('')}<span>More changes</span></div><small>Dates and times use UTC.</small></div></section>`;
}

export function renderCalendarDigest(data,ctx,page=1) {
  data=data.by_action?calendarSummary(data,data.date):data;
  const {esc,icon}=ctx,pages=Math.max(1,Math.ceil(data.total/6));page=Math.max(1,Math.min(pages,page));const rows=data.events.slice((page-1)*6,page*6);
  const groups=(items,actions=false)=>`<ul>${items.map(item=>`<li><span>${esc(actions?calendarActionLabel(item.name):item.name)}</span><strong>${item.count}</strong></li>`).join('')}</ul>`;
  return `<p class="digest-date">${esc(longDate(data.date))}</p><div class="digest-metrics">${[['Total events',data.total],['People',data.actors.length],['Action types',data.actions.length]].map(([label,count])=>`<div><span>${label}</span><strong>${count}</strong></div>`).join('')}</div>${!data.total?'<div class="empty-state"><h3>No activity on this day</h3><p>Choose another date to review its changes.</p></div>':`<section class="digest-highlights"><h3>Highlights</h3><ul>${(data.highlights||data.actions.map(item=>calendarActionLabel(item.name)+': '+item.count+' changes.')).map(text=>`<li>${esc(text)}</li>`).join('')}</ul></section><div class="digest-breakdown"><section><h3>By action</h3>${groups(data.actions,true)}</section><section><h3>By person</h3>${groups(data.actors)}</section></div><section class="digest-events"><h3>All changes <span class="count-label">${data.total}</span></h3><p class="muted">Newest first · UTC</p><ol>${rows.map(event=>`<li><span class="digest-event-icon" aria-hidden="true">${icon('history',17)}</span><div><p>${esc(event.detail||calendarActionLabel(event.action))}</p><span>${esc(event.actor||'Not provided')} · ${esc(calendarActionLabel(event.action))}</span></div><time datetime="${esc(event.date)}">${esc(new Date(event.date).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',timeZone:'UTC'}))}</time></li>`).join('')}</ol>${pages>1?`<nav class="digest-pagination" aria-label="Daily activity pages"><span>${(page-1)*6+1}–${Math.min(page*6,data.total)} of ${data.total} changes</span><div><button class="icon-button" data-action="sec-calendar-events" data-date="${data.date}" data-page="${page-1}" aria-label="Previous changes" ${page===1?'disabled':''}>${icon('chevron-left',19)}</button><span>Page ${page} of ${pages}</span><button class="icon-button" data-action="sec-calendar-events" data-date="${data.date}" data-page="${page+1}" aria-label="Next changes" ${page===pages?'disabled':''}>${icon('chevron-right',19)}</button></div></nav>`:''}</section>`}`;
}
function showDigestContent(date,html,ctx){ctx.openModal('Daily Summary · '+shortDate(date),html,'<button class="button secondary" data-action="close-modal">Close</button>');const dialog=document.querySelector('#modal');dialog.dataset.calendarDate=date;dialog.classList.add('calendar-digest-dialog');}
async function loadDigest(date,ctx) {
  if(!validCalendarDate(date))return;
  const sequence=++digestVersion;openDigest=null;
  showDigestContent(date,loadingSkeleton('rows','daily summary'),ctx);
  const changed=await calendarService.loadDay(date),dialog=document.querySelector('#modal');
  if(!changed||sequence!==digestVersion||!dialog.open||dialog.dataset.calendarDate!==date)return;
  const state=calendarService.dayState;
  if(state.status==='ready'){openDigest=state.data;showDigestContent(date,renderCalendarDigest(openDigest,ctx),ctx);}
  else showDigestContent(date,`<div class="empty-state" role="alert"><h3>Couldn’t load daily summary</h3><p>${ctx.esc(state.error||'Please try again.')}</p><button class="button primary" data-action="sec-calendar-day" data-date="${date}">Try again</button></div>`,ctx);
}
export async function handleCalendarAction(action,el,ctx) {
  if(action==='sec-calendar-month'||action==='sec-calendar-today'){
    const current=ctx.getFilters('history').month||utcToday().slice(0,7),month=action==='sec-calendar-today'?utcToday().slice(0,7):shiftCalendarMonth(current,Number(el.dataset.step));
    ctx.setFilters('history',{...ctx.getFilters('history'),tab:'calendar',month});ctx.render();document.getElementById(el.id)?.focus({preventScroll:true});return true;
  }
  if(action==='sec-calendar-retry'){const month=ctx.getFilters('history').month||utcToday().slice(0,7);const promise=monthLoader.load(month);ctx.render();await promise;refreshCalendar(ctx);return true;}
  if(action==='sec-calendar-day'){await loadDigest(el.dataset.date,ctx);return true;}
  if(action==='sec-calendar-events'&&openDigest){showDigestContent(openDigest.date,renderCalendarDigest(openDigest,ctx,Number(el.dataset.page)),ctx);document.querySelector('.digest-events')?.scrollIntoView({block:'nearest'});return true;}
  return false;
}
export function handleCalendarKeydown(event,ctx) {
  const day=event.target.closest?.('[data-action="sec-calendar-day"]');
  if(!day||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(event.key))return false;
  event.preventDefault();const date=new Date(day.dataset.date+'T12:00:00Z');
  if(event.key==='Home')date.setUTCDate(1);
  else if(event.key==='End')date.setUTCMonth(date.getUTCMonth()+1,0);
  else if(event.key==='PageUp'||event.key==='PageDown'){const targetMonth=shiftCalendarMonth(day.dataset.date.slice(0,7),event.key==='PageUp'?-1:1),bounds=calendarMonthBounds(targetMonth);date.setTime(Date.parse(`${targetMonth}-${String(Math.min(date.getUTCDate(),bounds.days)).padStart(2,'0')}T12:00:00Z`));}
  else date.setUTCDate(date.getUTCDate()+({ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[event.key]));
  const next=date.toISOString().slice(0,10),month=next.slice(0,7);
  if(month!==day.dataset.date.slice(0,7)){ctx.setFilters('history',{...ctx.getFilters('history'),tab:'calendar',month});const pending=monthLoader.load(month);ctx.render();void pending.then(changed=>{if(changed){refreshCalendar(ctx);document.getElementById('calendar-day-'+next)?.focus({preventScroll:true});}});}
  else document.getElementById('calendar-day-'+next)?.focus();
  return true;
}
