import {sourceLabel,sourceNotice} from './data-source.js';
import {handleCalendarKeydown} from './calendar.js';
import { employeeProfile, fetchEmployeeProfile, loadEmployeeProfile, invalidateEmployeeProfile, employeeUpdatePayload, employeeMatchesUpdate, patchEmployee, changeEmployeeState } from './employee-details.js';
import { apiRequest, apiId } from './api-client.js';
import { resources, watchBackend, refreshEmployees, refreshWorkspace, ensurePageData, loadRecords, loadTypes, loadActiveTypes, loadRecent, loadTimeline, loadRemovals, normalizeViolation, normalizeType } from './backend.js';
import { mutationInFlight, pendingMutation, runMutation, checkPendingMutation, saveType, changeType, issueViolation, updateViolation, deleteViolation } from './mutations.js';
import { submitApiEmployeeForm, employeeCreateInFlight, pendingEmployeeCreation } from './employee-create.js';
import { employeeDirectory, nextApiEmployeeCode, fetchEmployeeDirectorySnapshot } from './employee-api.js';
import { loadingSkeleton } from './loading.js';
import { renderEmployees, renderViolations, employeeLoadState } from './records.js';
import { bindEmployeePicker } from './employee-picker.js';
import { enhancePhoneLayout, syncPhoneFilters } from './phone.js';
import { localDate, startOfWeek, normalizeViolationStatus, VIOLATION_STATUSES, violationStatusLabel } from './domain.js';
import { renderDashboard } from './dashboard.js';
import { store, saveStore, employeeSummary, visibleEmployees, visibleViolations } from './data.js';
import { renderSecondary, handleSecondary } from './secondary.js';

const app = document.querySelector('#app');
const dialog = document.querySelector('#modal');
let displayedWeek = startOfWeek(localDate());
const filters = {};
let savedSnapshot = JSON.stringify(store.settings);
let page = 'dashboard';
let profileId = '';
let employeePage = 1;
let violationPage = 1;
let draft = null;
let modalOrigin = null;
let modalVersion = 0;
let checkingDraft = false;
let editingEmployee = null;
const pageInfo = {
  dashboard: ['Dashboard', 'A clear view of employee violations and disciplinary activity.', 'Overview'],
  employees: ['Employees', 'Find employee records and follow their disciplinary history.', 'Employee management'],
  violations: ['Violations', 'Find, record, and review employee violations.', 'Employee management'],
  types: ['Violation Types', 'Keep a clear, consistent guide to workplace violations.', 'Employee management'],
  profile: ['Employee Profile', 'Employee information and disciplinary history in one place.', 'Employee management'],
  history: ['History', 'All recorded changes and employee violation removals in one place.', 'Monitoring'],
  reports: ['Reports & Analytics', 'Turn disciplinary records into a clearer picture of your workplace.', 'Reports'],
  users: ['Users & Roles', 'User and role management will be available in a future update.', 'Administration'],
  settings: ['Settings', 'Make your workspace comfortable and easy to use.', 'Administration'],
  help: ['Help & Guidance', 'A little guidance for your everyday HR tasks.', 'Support']
};
const paths = {
  dashboard:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  users:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M16 3a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-3.87 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  user:'M20 21v-2a7 7 0 0 0-14 0v2 M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  shield:'M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11 M9 12l2 2 4-4',
  alert:'m10.3 3.9-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3.1l-8-14a2 2 0 0 0-3.4 0 M12 9v4 M12 17h.01',
  file:'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M8 13h8 M8 17h5',
  clipboard:'M9 5H6a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3 M9 2h6v5H9z M8 12h8 M8 16h6',
  history:'M3 11a9 9 0 1 1 2.7 7 M3 4v7h7 M12 7v5l3 2',
  archive:'M3 3h18v4H3z M5 7v14h14V7 M10 11h4 M9 16l6-6 M9 10l6 6',
  chart:'M3 3v18h18 M7 14l4-5 4 3 6-7',
  settings:'M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  help:'M12 17h.01 M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  search:'m21 21-4.3-4.3 M18 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0',
  bell:'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9 M10 21h4',
  'chevron-right':'m9 5 7 7-7 7',
  'chevron-left':'m15 5-7 7 7 7',
  'chevron-down':'m6 9 6 6 6-6',
  plus:'M12 5v14 M5 12h14',
  download:'M21 15v5H3v-5 M12 3v12 M7 10l5 5 5-5',
  calendar:'M8 2v4 M16 2v4 M3 10h18 M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2',
  sun:'M12 2v2 M12 20v2 M2 12h2 M20 12h2 M4.93 4.93l1.42 1.42 M17.65 17.65l1.42 1.42 M4.93 19.07l1.42-1.42 M17.65 6.35l1.42-1.42 M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0',
  clock:'M12 8v4l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  check:'m5 12 4 4L19 6',
  'check-circle':'m8 12 3 3 5-6 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  info:'M12 11v6 M12 7h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  arrow:'M5 12h14 m-6-6 6 6-6 6',
  'arrow-up':'M7 17 17 7 M7 7h10v10',
  'arrow-down':'M7 7l10 10 M7 17h10V7',
  close:'M6 6l12 12 M6 18 18 6',
  edit:'m16 3 5 5 M4 15 16 3a3.5 3.5 0 0 1 5 5L9 20l-6 1z',
  trash:'M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7',
  mail:'M3 5h18v14H3z m0 1 9 7 9-7',
  building:'M4 22V2h12v20 M16 8h4v14 M8 6h4 M8 10h4 M8 14h4 M8 18h4',
  printer:'M6 9V2h12v7 M6 18H3V9h18v9h-3 M6 14h12v8H6z M17 11h.01',
  menu:'M3 6h18 M3 12h18 M3 18h18',
  eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7 M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  lock:'M6 11h12v11H6z M8 11V6a4 4 0 0 1 8 0v5',
  filter:'M3 4h18l-7 8v7l-4 2v-9z',
  refresh:'M20 4v6h-6 M4 20v-6h6 M5 8a8 8 0 0 1 13-4l2 6 M4 14l2 6a8 8 0 0 0 13-4'
};
paths['file-text']=paths.file;
function icon(name,size=20){return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]||paths.file}"/></svg>`;}
function esc(value=''){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function formatDate(iso){if(!iso)return '—';const d=new Date(String(iso).slice(0,10)+'T12:00:00');return Number.isNaN(+d)?'—':d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});}
function badge(text){const t=String(text);const cl=/resolved|active$|good standing/i.test(t)&&!/^Inactive/.test(t)?'success':/pending|monitor|1 Strike/i.test(t)?'warning':/review/i.test(t)?'review':/strike|attention/i.test(t)?'danger':'neutral';const ic=cl==='success'?'check-circle':cl==='warning'?'clock':cl==='danger'?'alert':cl==='review'?'eye':'info';return `<span class="pill ${cl}">${icon(ic,12)}${esc(t)}</span>`;}
function violationStatusOptions(current='',includeAll=false){return (includeAll?'<option value="">All statuses</option>':'')+VIOLATION_STATUSES.map(status=>`<option value="${status}" ${status===current?'selected':''}>${includeAll?status:violationStatusLabel(status)}</option>`).join('');}
function violationBadge(value){if(!value)return `<span class="pill neutral" title="The API does not supply case resolution status">${icon('info',14)}Not provided</span>`;const status=normalizeViolationStatus(value);return `<span class="pill ${status==='Active'?'warning':'success'}" title="${violationStatusLabel(status)}">${icon(status==='Active'?'clock':'check-circle',14)}${status}</span>`;}
function initials(name){return name.split(/\s+/).filter(Boolean).slice(0,2).map(n=>n[0]).join('');}
function avatar(e){const colors=['','sage','rose','lavender'];return `<span class="avatar ${colors[Number(e.id?.replace(/\D/g,''))%4]||''}">${esc(initials(e.name))}</span>`;}
function person(e){const content=`${avatar(e)}<span><span class="person-name">${esc(e.name)}</span><span class="person-id" style="display:block">${esc(e.id)}</span></span>`;return e.source==='api'&&!e.profileId?`<span class="person-button">${content}</span>`:`<button class="person-button" data-action="profile" data-id="${esc(e.profileId || e.id)}">${content}</button>`;}
function opt(values,current='',all='All'){return `<option value="">${esc(all)}</option>${values.map(v=>`<option value="${esc(v)}" ${v===current?'selected':''}>${esc(v)}</option>`).join('')}`;}
function unique(values){return [...new Set(values)].filter(Boolean).sort();}
function empty(title='No records found',desc='Try adjusting your search or clearing the filters.'){return `<div class="empty-state">${icon('search',32)}<h3>${title}</h3><p>${desc}</p></div>`;}
function canRecord(){return ['HR','Supervisor'].includes(store.settings.role);}
function canManage(){return store.settings.role==='HR';}
function restoreSnapshot(){Object.assign(store.settings,JSON.parse(savedSnapshot));}
function commitStore(){try{const previous=JSON.parse(savedSnapshot);saveStore();if(previous.role!==store.settings.role||previous.department!==store.settings.department){Object.keys(filters).forEach(k=>delete filters[k]);employeePage=1;violationPage=1;}savedSnapshot=JSON.stringify(store.settings);}catch(error){restoreSnapshot();throw error;}}
function ctx(){return {store,resources,resourceState,icon,esc,formatDate,badge,violationBadge,violationStatusOptions,person,employeeSummary,visibleEmployees,visibleViolations,navigate,toast,saveStore:commitStore,openModal,closeModal,downloadCSV,render,pagination,getFilters:p=>filters[p]||{},setFilters:(p,f)=>{filters[p]=f;},barChart};}
function persist(message){try{commitStore();if(message)toast(message);return true;}catch(e){toast(e.message||'Unable to save changes in this browser.','alert');return false;}}
function toast(message,type='check-circle'){const r=document.querySelector('#toast-region');r.innerHTML=`<div class="toast">${icon(type,22)}<span>${esc(message)}</span><button class="icon-button" data-action="dismiss-toast" aria-label="Dismiss notification">${icon('close',16)}</button></div>`;clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>r.innerHTML='',6500);}
function openModal(title,html,footer=''){modalVersion++;delete dialog.dataset.calendarDate;dialog.classList.remove('calendar-digest-dialog');if(!dialog.open)modalOrigin=document.activeElement;dialog.innerHTML=`<div class="modal-header"><h2 id="modal-title">${title}</h2><button class="icon-button" data-action="close-modal" aria-label="Close dialog">${icon('close')}</button></div><div class="modal-content">${html}</div>${footer?`<div class="modal-footer">${footer}</div>`:''}`;if(!dialog.open)dialog.showModal();}
function closeModal(){if(employeeCreateInFlight()||mutationInFlight()||checkingDraft)return;modalVersion++;dialog.close();if(modalOrigin?.isConnected)modalOrigin.focus();}
function downloadCSV(filename,rows){const safe=rows.map(row=>row.map(value=>{let s=String(value??'');if(/^[=+@\-\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}).join(',')).join('\r\n');const url=URL.createObjectURL(new Blob(['\uFEFF'+safe],{type:'text/csv;charset=utf-8;'}));const a=document.createElement('a');a.href=url;a.download=filename.endsWith('.csv')?filename:filename+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Your report has been downloaded.');}

function navItem(id,label,ic,count=''){return `<button class="nav-item ${page===id||(page==='profile'&&id==='employees')?'active':''}" data-action="navigate" data-page="${id}" ${page===id?'aria-current="page"':''}>${icon(ic)}<span>${label}</span>${count?`<span class="nav-count">${count}</span>`:''}</button>`;}
function connectionNotice(){return sourceNotice?`<div class="callout preview-notice" role="status"><p>${esc(sourceNotice)}</p></div>`:'';}
function shell(content){const info=pageInfo[page];const activeCount=store.recordsReady?visibleViolations().filter(v=>v.status==='Active').length:0;const roleLabel={'HR':'HR administrator','Supervisor':'Department supervisor'}[store.settings.role]||'HR administrator';return `<button class="mobile-overlay" data-action="toggle-nav" aria-label="Close navigation"></button><aside class="sidebar" aria-label="Main navigation"><a class="brand" href="#dashboard" aria-label="Northpoint home"><img src="./assets/company-logo.png" alt="Company logo"><div><div class="brand-name">Northpoint</div><div class="brand-subtitle">Violation Management</div></div></a><button class="button secondary phone-menu-close" data-action="toggle-nav">${icon('close',18)} Close menu</button><nav class="navigation"><div class="nav-label">Workspace</div>${navItem('dashboard','Dashboard','dashboard')}<div class="nav-label">Employee management</div>${navItem('employees','Employees','users')}${navItem('violations','Violations','shield',activeCount)}${canManage()?navItem('types','Violation Types','clipboard'):''}<div class="nav-label">Monitoring</div>${navItem('history','History','history')}<div class="nav-label">Insights</div>${navItem('reports','Reports & Analytics','chart')}<div class="nav-label">Administration</div>${canManage()?navItem('users','Users & Roles','user'):''}${navItem('settings','Settings','settings')}</nav><div class="sidebar-bottom"><div class="help-card"><div class="help-top">${icon('help',18)} A little help, if you need it</div><p>Simple guidance for everyday tasks.</p><button data-action="navigate" data-page="help">View the quick guide ${icon('arrow',15)}</button></div><div class="sidebar-note">${icon('lock',12)} ${esc(sourceLabel)}</div></div></aside><div class="workspace"><header class="topbar"><button class="icon-button mobile-toggle" data-action="toggle-nav" aria-label="Open navigation" aria-expanded="false">${icon('menu')}<span>Menu</span></button><div class="breadcrumb"><span>Workspace</span>${icon('chevron-right',13)}<strong>${info[0]}</strong></div><div class="topbar-right"><form id="global-search" class="top-search"><label class="sr-only" for="global-query">Search employees or records</label>${icon('search',17)}<input id="global-query" name="query" placeholder="Search employees or records…" autocomplete="off"><span class="key-hint">Ctrl K</span></form><button class="icon-button" data-action="navigate" data-page="help" aria-label="Help and guidance">${icon('help',21)}</button><span class="top-divider"></span><button class="account-button" data-action="account" aria-label="Your profile and workspace view"><span class="avatar sage">${esc(initials(store.settings.name || '?'))}</span><span class="account-details"><span class="account-name">${esc(store.settings.name || 'Set your name')}</span><span class="account-role" style="display:block">${roleLabel}</span></span>${icon('chevron-down',14)}</button></div></header><main id="main" class="main" tabindex="-1"><div class="page-heading"><div><div class="eyebrow">${info[2]}</div><h1>${info[0]}</h1><p class="page-description">${info[1]}</p></div><div class="heading-actions">${headingActions()}</div></div>${connectionNotice()}${content}<footer class="page-footer"><span>${icon('shield',13)} Northpoint</span></footer></main></div>`;}
function headingActions(){
    const recordDisabled=employeeDirectory.status!=='ready'?'disabled title="Load employees before recording a violation"':'';
    if(page==='dashboard'||page==='violations')return canRecord()?`<button class="button primary" data-action="record" ${recordDisabled}>${icon('plus',18)} ${page==='dashboard'?'Record violation':'Record New Violation'}</button>`:'';
    if(page==='employees'&&canManage())return `<button class="button primary" data-action="add-employee" ${employeeDirectory.status!=='ready'&&!pendingEmployeeCreation()?'disabled':''}>${icon('plus',18)} Add Employee</button>`;
    if(page==='types'&&canManage())return `<button class="button primary" data-action="add-type" ${resources.types.status!=='ready'?'disabled':''}>${icon('plus',18)} Add Violation Type</button>`;
    if(page==='profile')return `<button class="button secondary" data-action="navigate" data-page="employees">${icon('chevron-left',17)} All employees</button>${canRecord()?`<button class="button primary" data-action="record" data-employee="${esc(profileId)}" ${employeeProfile.status!=='ready'||employeeProfile.employee?.status!=='Active'?'disabled title="Only active employees can receive a violation"':recordDisabled}>${icon('plus',17)} Record violation</button>`:''}`;
    return '';
  }

function barChart(items){const max=Math.max(1,...items.map(x=>x.value));return `<div class="bar-chart">${items.map(i=>`<div class="bar-chart-row" title="${esc(i.label)}: ${i.value}"><span>${esc(i.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${i.value/max*100}%"></div></div><strong>${i.value}</strong></div>`).join('')}</div>`;}
function resourceState(resource,label='records',layout='rows'){
    if(resource.status==='ready')return '';
    const failed=resource.status==='error';
    if(!failed)return loadingSkeleton(layout==='rows'&&/details|employee form|violation type$/.test(label)?'form':layout,label);
    return `<div class="empty-state" role="${failed?'alert':'status'}" aria-live="polite">${icon(failed?'alert':'refresh',30)}<h3>${failed?'Couldn’t load '+esc(label):'Loading '+esc(label)+'…'}</h3><p>${failed?esc(resource.error):'Preparing the workspace preview.'}</p>${failed?`<button class="button primary" data-action="refresh-data" style="margin-top:18px">${icon('refresh',17)} Try again</button>`:''}</div>`;
  }
  function dataGate(names){
    if(names.includes('employees')&&employeeDirectory.status!=='ready')return employeeDirectory.status==='error'?'<section class="panel">'+employeeLoadState(employeeDirectory,icon,esc)+'</section>':loadingSkeleton(page,'employee data');
    const labels={records:'violation records',types:'violation types',timeline:'activity history',removals:'removal history'};
    const name=names.find(name=>name!=='employees'&&resources[name].status!=='ready');
    return name?resources[name].status==='error'?'<section class="panel">'+resourceState(resources[name],labels[name])+'</section>':loadingSkeleton(page,labels[name]):'';
  }
  function dashboard(){return dataGate(['employees','records'])||renderDashboard({...ctx(),recentActivity:resources.recent.items,recentState:resourceState(resources.recent,'recent activity')});}

function isLiveEmployeeProfile(){return page==='profile'&&profileId.startsWith('api/');}
function liveEmployeeRecords(){return visibleEmployees();}
  function liveEmployeeSummary(id){return employeeSummary(id);}
  async function refreshApiEmployees(){await refreshEmployees();ensurePageData(page);}
  function employeeList(){return renderEmployees({...ctx(),employeeDirectory,visibleEmployees,employeeSummary,page:employeePage,setPage:value=>employeePage=value})+(employeeDirectory.status==='ready'&&resources.records.status==='error'?`<div class="callout warning" role="alert">${icon('alert')}<p>${esc(resources.records.error)} Violation history filters are unavailable. <button class="text-button" data-action="refresh-data">Try again</button></p></div>`:'');}

function pagination(total, current, size, target) {
  const pages = Math.max(1, Math.ceil(total / size));
  const shown = [...new Set([1, ...Array.from({ length: 5 }, (_, index) => current + index - 2), pages])].filter(number => number > 0 && number <= pages).sort((a, b) => a - b);
  return `<div class="table-footer"><span>${total ? `${(current - 1) * size + 1}–${Math.min(total, current * size)}` : '0'} of ${total} ${target === 'employees' ? 'employees' : 'records'}</span><nav class="pagination" aria-label="${target === 'employees' ? 'Employee' : target === 'history' ? 'History' : 'Violation'} pages"><button data-action="paginate" data-page="${target}" data-number="${current - 1}" ${current === 1 ? 'disabled' : ''} aria-label="Previous page">${icon('chevron-left', 15)}</button><span class="pagination-pages">${shown.map((number, index) => `${index && number > shown[index - 1] + 1 ? '<span aria-hidden="true">…</span>' : ''}<button data-action="paginate" data-page="${target}" data-number="${number}" class="${number === current ? 'active' : ''}" aria-label="Page ${number}" ${number === current ? 'aria-current="page"' : ''}>${number}</button>`).join('')}</span><span class="pagination-summary" aria-live="polite">Page ${current} of ${pages}</span><button data-action="paginate" data-page="${target}" data-number="${current + 1}" ${current >= pages ? 'disabled' : ''} aria-label="Next page">${icon('chevron-right', 15)}</button></nav></div>`;
}
function violationsList(){return dataGate(['employees','records','types'])||renderViolations({...ctx(),page:violationPage,setPage:value=>violationPage=value});}
function typesList(){const gate=dataGate(['types']);if(gate)return gate;const f=filters.types||{};const ts=store.types.filter(t=>(!f.query||`${t.name} ${t.description}`.toLowerCase().includes(f.query.toLowerCase()))&&(!f.status||(f.status==='active'?t.active:!t.active)));return `<form id="type-filters" class="filters" style="grid-template-columns:2fr 1fr auto"><div class="field"><label for="type-query">Find a violation type</label><input id="type-query" name="query" value="${esc(f.query||'')}" placeholder="Search by name or description"></div><div class="field"><label for="type-status">Status</label><select id="type-status" name="status"><option value="">All statuses</option><option value="active" ${f.status==='active'?'selected':''}>Active</option><option value="inactive" ${f.status==='inactive'?'selected':''}>Inactive</option></select></div><div class="filter-actions" style="grid-column:auto"><button class="button ghost" type="button" data-action="clear-filters" data-page="types">Clear Filters</button><button type="submit" class="button primary">${icon('search',17)} Search</button></div></form><section class="panel"><div class="panel-header"><h2>Violation categories <span class="count-label">${ts.length} categories</span></h2></div>${ts.length?`<div class="table-wrap"><table><thead><tr><th>Violation Name / Description</th><th>Demerit Points</th><th>Strike Violation</th><th>Status</th><th>Manage</th></tr></thead><tbody>${ts.map(t=>`<tr><td style="max-width:350px"><strong>${esc(t.name)}</strong><div class="muted" style="font-size:13px;margin-top:5px">${esc(t.description)}</div></td><td>${t.points} points</td><td>${t.strike?badge('Strike Violation'):'No'}</td><td>${badge(t.active?'Active':'Inactive')}</td><td><div class="row-actions"><button class="button secondary small" data-action="edit-type" data-id="${esc(t.id)}">${icon('edit',14)} Edit</button><button class="button ghost small" data-action="toggle-type" data-id="${esc(t.id)}">${t.active?'Deactivate':'Reactivate'}</button>${!store.violations.some(v=>v.typeId===t.id)?`<button class="icon-button" data-action="delete-type" data-id="${esc(t.id)}" aria-label="Delete ${esc(t.name)}">${icon('trash',16)}</button>`:''}</div></td></tr>`).join('')}</tbody></table></div>`:empty()}</section>`;}
function profileApiId(){
  if(profileId.startsWith('api/')){try{return apiId(profileId.slice(4));}catch{return '';}}
  return store.employees.find(employee=>employee.id===profileId)?.apiId||'';
}
async function ensureCurrentProfile(force=false){
  if(page!=='profile')return;
  const id=profileApiId();if(!id)return;
  if(force||employeeProfile.apiId!==id||employeeProfile.status==='idle')await loadEmployeeProfile(id,()=>{if(page==='profile')render();});
}
function profile(){
  const id=profileApiId();
  if(!id){if(!profileId.startsWith('api/')&&employeeDirectory.status!=='ready')return '<section class="panel">'+employeeLoadState(employeeDirectory,icon,esc)+'</section>';return empty('Employee not available','Choose an employee from the directory.');}
  if(employeeProfile.apiId!==id||employeeProfile.status!=='ready')return resourceState(employeeProfile.apiId===id?employeeProfile:{status:'loading'},'employee profile','profile').replace('data-action="refresh-data"','data-action="retry-profile"');
  const e=employeeProfile.employee;
  if(store.settings.role==='Supervisor'&&e.department!==store.settings.department)return empty('Employee not available','This employee is outside your assigned department view.');
  const vs=employeeProfile.violations, f=filters.profile||{}, strikes=e.totalStrikes, points=e.totalPoints;
  const standing=strikes>=2?'Needs attention':vs.length||points>0||strikes>0?'For monitoring':'Good standing';
  const current=Math.min(Math.max(1,Number(f.page)||1),Math.max(1,Math.ceil(vs.length/6))), shown=vs.slice((current-1)*6,current*6);
  return `<section class="panel" style="margin-bottom:23px"><div class="profile-top">${avatar(e)}<div class="profile-info"><h2>${esc(e.name)}</h2><div class="profile-meta"><span>${esc(e.id)}</span><span>${esc(e.department||'Unassigned')}</span><span>${esc(e.position||'Not provided')}</span>${badge(e.status)}</div></div>${canManage()?`<button class="button secondary" data-action="edit-employee" data-id="${esc(e.apiId)}">${icon('edit',16)} Edit Employee</button>`:''}</div><div class="profile-stats"><div class="profile-stat"><span>Total Violations</span><strong>${vs.length}</strong></div><div class="profile-stat"><span>Demerit Points</span><strong>${points}</strong></div><div class="profile-stat"><span>Strikes</span><strong>${strikes}</strong></div><div class="profile-stat"><span>Disciplinary Status</span><strong class="text">${badge(standing)}</strong></div></div></section>${strikes>=2?`<div class="callout warning">${icon('alert')}<p><strong>Repeated offenses need a closer look.</strong> ${esc(e.name)} has ${strikes} recorded strikes. Review the history and employee explanation before deciding on further action.</p></div>`:''}
  <section class="panel" style="margin-bottom:23px"><div class="panel-header"><h2>Employee information</h2></div><div class="panel-body"><dl class="detail-grid"><div><dt>Employee ID</dt><dd>${esc(e.id)}</dd></div><div><dt>Department</dt><dd>${esc(e.department||'Unassigned')}</dd></div><div><dt>Position</dt><dd>${esc(e.position||'Not provided')}</dd></div><div><dt>Employment Status</dt><dd>${badge(e.status)}</dd></div></dl></div></section>
  <section class="panel"><div class="panel-header"><div><h2>Violation history</h2><p>${vs.length} records · Most recent first</p></div></div>${shown.length?`<div class="table-wrap"><table><thead><tr><th>Violation / Description</th><th>Incident date</th><th>Demerit Points</th><th>Strike</th><th>Recorded by</th><th>Action</th></tr></thead><tbody>${shown.map(v=>`<tr><td style="max-width:330px"><strong>${esc(v.typeName)}</strong><p class="muted" style="font-size:13px;margin-top:6px">${esc(v.description)}</p></td><td>${formatDate(v.date)}</td><td>${v.points}</td><td>${v.strike?badge('Strike Violation'):'No'}</td><td>${esc(v.recordedBy)}</td><td><button class="button ghost small" data-action="case-details" data-id="${esc(v.id)}">View Case</button></td></tr>`).join('')}</tbody></table></div>`:empty('No violations on record','There are no records in this view.')}${pagination(vs.length,current,6,'profile')}</section>`;
}

function render(){if(!canManage()&&['types','users'].includes(page))page='dashboard';document.body.classList.toggle('larger-text',store.settings.textSize==='larger');document.documentElement.dataset.textSize=store.settings.textSize;let html=page==='dashboard'?dashboard():page==='employees'?employeeList():page==='violations'?violationsList():page==='types'?typesList():page==='profile'?profile():page==='reports'?(dataGate(['employees','records',...(filters.reports?.tab==='rulebook'?['types']:[])])||renderSecondary(page,ctx())):page==='history'?renderSecondary(page,ctx()):renderSecondary(page,ctx());if(page==='dashboard')displayedWeek=startOfWeek(localDate());app.innerHTML=shell(html);enhancePhoneLayout({icon});syncNavigation();document.title=`${pageInfo[page][0]} · Northpoint`;}
function navigate(target,id=''){document.body.classList.remove('nav-open');const hash=target==='profile'?`employee/${id}`:target;if(location.hash.slice(1)===hash){route();}else location.hash=hash;}
function route(){let hash=location.hash.slice(1)||'dashboard';if(hash==='removals'){filters.history={tab:'removals'};location.hash='history';return;}if(hash.startsWith('employee/')){profileId=decodeURIComponent(hash.slice(9));page='profile';}else page=pageInfo[hash]?hash:'dashboard';render();window.scrollTo({top:0,behavior:'instant'});document.querySelector('#main')?.focus({preventScroll:true});if(employeeDirectory.status==='idle')void refreshApiEmployees();ensurePageData(page);void ensureCurrentProfile();}

function formError(form,message){const el=form.querySelector('.form-error');if(el){el.textContent=message;el.classList.add('show');el.hidden=false;el.scrollIntoView({block:'nearest'});}}
async function employeeForm(id) {
  if(!canManage())return;
  if(pendingMutation()){showPending();return;}
  if(pendingEmployeeCreation()&&id){toast('Check the previous employee save first.','info');return;}
  const pending=!id?pendingEmployeeCreation():null;
  let e={}, departments=unique(store.employees.map(employee=>employee.department));editingEmployee=null;
  if(id){
    id=id.startsWith('api/')?id.slice(4):store.employees.find(employee=>employee.id===id)?.apiId||id;
    openModal('Edit Employee',resourceState({status:'loading'},'employee details'),'<button class="button secondary" data-action="close-modal">Cancel</button>');
    const version=modalVersion;
    try{e=(await fetchEmployeeProfile(id)).employee;}catch(error){if(dialog.open&&version===modalVersion)dialog.querySelector('.modal-content').innerHTML=resourceState({status:'error',error:error.message},'employee details').replace('data-action="refresh-data"',`data-action="edit-employee" data-id="${esc(id)}"`);return;}
    if(!dialog.open||version!==modalVersion)return;editingEmployee={...e};
  }else{
    if(employeeDirectory.status!=='ready'&&!pending){toast('Load the employee list before adding an employee.','info');return;}
    if(pending)e={id:pending.payload.employee_code,firstName:pending.payload.first_name,lastName:pending.payload.last_name,department:pending.payload.department,position:pending.payload.position};
    else {
      openModal('Add Employee',resourceState({status:'loading'},'employee form','form'),'<button class="button secondary" data-action="close-modal">Cancel</button>');
      const version=modalVersion;
      try {
        const directory=await fetchEmployeeDirectorySnapshot();
        if(!dialog.open||version!==modalVersion)return;
        e.id=nextApiEmployeeCode(directory.items);
        departments=unique(directory.items.map(employee=>employee.department));
      } catch(error) {
        if(dialog.open&&version===modalVersion)dialog.querySelector('.modal-content').innerHTML=resourceState({status:'error',error:error.message},'employee code availability').replace('data-action="refresh-data"','data-action="add-employee"');
        return;
      }
    }
  }
  if(e.department&&!departments.includes(e.department))departments.push(e.department);
  openModal(id?'Edit Employee':'Add Employee',`<form id="employee-form" data-id="${esc(id||'')}" data-source="api"><p class="form-error" role="alert"></p><div class="form-grid ${id?'':'employee-create-grid'}">
    <div class="field employee-first-name"><label for="emp-first-name">First name (required)</label><input id="emp-first-name" name="firstName" required maxlength="100" autocomplete="given-name" value="${esc(e.firstName||'')}"></div>
    <div class="field employee-code"><label for="emp-code">Employee code</label><input id="emp-code" name="employee_code" required maxlength="50" value="${esc(e.id)}" ${id?'readonly aria-readonly="true"':'autocomplete="off" spellcheck="false"'} aria-describedby="emp-code-help"><small id="emp-code-help">${id?'Employee code stays the same.':'Sample code for this form preview. You can change it.'}</small></div>
    <div class="field"><label for="emp-last-name">Last name (required)</label><input id="emp-last-name" name="lastName" required maxlength="100" autocomplete="family-name" value="${esc(e.lastName||'')}"></div>
    <div class="field"><label for="emp-department">Department <span class="muted">(optional)</span></label>${id?`<input id="emp-department" name="department" list="employee-departments" maxlength="100" value="${esc(e.department||'')}"><datalist id="employee-departments">${departments.map(department=>`<option value="${esc(department)}"></option>`).join('')}</datalist>`:`<select id="emp-department" name="department"><option value="">No department assigned</option>${departments.map(department=>`<option value="${esc(department)}" ${department===e.department?'selected':''}>${esc(department)}</option>`).join('')}<option value="__other_department__">Add another department…</option></select>`}</div>
    ${id?'':'<div class="field span-full" id="employee-new-department-field" hidden><label for="emp-new-department">New department name</label><input id="emp-new-department" name="newDepartment" maxlength="100" disabled></div>'}
    <div class="field span-full"><label for="emp-position">Position <span class="muted">(optional)</span></label><input id="emp-position" name="position" maxlength="100" value="${esc(e.position||'')}"></div>
    </div>${!id?'<p class="form-intro" style="margin:20px 0 0">New employees are automatically active.</p>':''}</form>
    ${id?`<div style="margin-top:22px;padding-top:18px;border-top:1px solid #e1e7ef"><p class="form-intro" style="margin-bottom:12px">Employment status: ${badge(e.status)}</p><div class="row-actions" style="flex-wrap:wrap;gap:10px"><button class="button secondary" data-action="employee-state" data-id="${esc(e.apiId)}" data-mode="${e.status==='Active'?'deactivate':'reactivate'}">${e.status==='Active'?'Deactivate':'Reactivate'} Employee</button><button class="button danger-outline" data-action="employee-state" data-id="${esc(e.apiId)}" data-mode="delete">Permanently Delete</button></div></div>`:''}`,`<button class="button secondary" data-action="close-modal">Cancel</button><button class="button primary" type="submit" form="employee-form">${icon('check',17)} ${id?'Save Changes':pending?'Check save status':'Add Employee'}</button>`);
  if(pending){dialog.querySelectorAll('#employee-form input,#employee-form select,#employee-form textarea').forEach(control=>control.disabled=true);formError(dialog.querySelector('#employee-form'),'A previous save has not been confirmed. Choose “Check save status” to check the server without sending another POST.');}
}
function confirmEmployeeState(id,mode){
  if(!canManage()||!editingEmployee||editingEmployee.apiId!==id||!['deactivate','reactivate','delete'].includes(mode))return;
  const e=editingEmployee,deleting=mode==='delete',label=deleting?'Permanently Delete':mode==='deactivate'?'Deactivate':'Reactivate';
  openModal(label+' Employee',`<div class="callout ${deleting?'warning':''}">${icon(deleting?'alert':'info')}<p>${deleting?`Permanently delete <strong>${esc(e.name)}</strong> (${esc(e.id)}) and all their violation records? This cannot be undone and bypasses the violation removal audit trail.`:mode==='deactivate'?`Deactivate <strong>${esc(e.name)}</strong>? Their status becomes Inactive and their violation history stays on the backend.`:`Reactivate <strong>${esc(e.name)}</strong>? Their status becomes Active again.`}</p></div><form id="employee-state-form" data-id="${esc(id)}" data-mode="${mode}"><p class="form-error" role="alert"></p>${deleting?`<div class="field"><label for="employee-delete-code">Type ${esc(e.id)} to confirm</label><input id="employee-delete-code" name="code" required autocomplete="off"></div><label class="confirm-check" style="margin-top:18px"><input type="checkbox" name="confirmed" required>I understand that the employee and their violation records will be permanently deleted.</label>`:''}</form>`,`<button class="button secondary" data-action="edit-employee" data-id="${esc(id)}">Cancel</button><button class="button ${deleting?'danger':'primary'}" type="submit" form="employee-state-form">${label} Employee</button>`);
}

async function typeForm(id) {
  if (!canManage()) return;
  if(pendingMutation()){showPending();return;}
  let t = store.types.find(type => type.id === id) || {};
  if(id){openModal('Edit Violation Type',resourceState({status:'loading'},'violation type'),'<button class="button secondary" data-action="close-modal">Close</button>');const version=modalVersion;try{t=normalizeType(await apiRequest('/violation-types/'+apiId(id)));}catch(error){if(dialog.open&&version===modalVersion)dialog.querySelector('.modal-content').innerHTML=resourceState({status:'error',error:error.message},'violation type').replace('data-action="refresh-data"',`data-action="edit-type" data-id="${esc(id)}"`);return;}if(!dialog.open||version!==modalVersion)return;}
  openModal(id ? 'Edit Violation Type' : 'Add Violation Type', `<p class="form-intro">Use a clear name and description so staff can record violations consistently.</p><form id="type-form" data-id="${esc(id || '')}"><p class="form-error" role="alert"></p><div class="form-grid">
    <div class="field span-full"><label for="type-name">Violation name (required)</label><input id="type-name" name="name" value="${esc(t.name || '')}" required maxlength="100"></div>
    <div class="field span-full"><label for="type-description">Description (required)</label><textarea id="type-description" name="description" required maxlength="1000">${esc(t.description || '')}</textarea></div>
    <div class="field span-full"><label for="type-points">Demerit Points</label><input id="type-points" name="points" type="number" inputmode="numeric" required min="0" max="100" step="1" value="${t.points ?? 0}"></div>
    <div class="check-field span-full"><input type="checkbox" id="type-strike" name="strike" ${t.strike ? 'checked' : ''}><label for="type-strike">This is a Strike Violation</label></div>
    </div>${!id ? '<p class="form-intro" style="margin:20px 0 0">New violation types are automatically active.</p>' : ''}</form>`, `<button class="button secondary" data-action="close-modal">Cancel</button><button class="button primary" type="submit" form="type-form">${id ? 'Save Changes' : 'Add Violation Type'}</button>`);
}
async function recordForm(employeeId = '', keep = false) {
  if (!canRecord()) return;
  if(pendingMutation()){showPending();return;}
  if(!store.settings.name.trim()){toast('Set your display name in Settings before recording a violation.','info');navigate('settings');return;}
  if(employeeDirectory.status!=='ready'){toast('Load the employee list first.','info');return;}
  if(resources.activeTypes.status!=='ready'){openModal('Record New Violation',resourceState(resources.activeTypes,'active violation types'),`<button class="button secondary" data-action="close-modal">Close</button>`);const version=modalVersion;await loadActiveTypes(true);if(!dialog.open||version!==modalVersion)return;if(resources.activeTypes.status!=='ready'){dialog.querySelector('.modal-content').innerHTML=resourceState(resources.activeTypes,'active violation types').replace('data-action="refresh-data"','data-action="record"');return;}}
  employeeId=store.employees.find(employee=>employee.profileId===employeeId)?.id||employeeId;
  const d = keep && draft ? draft : { employeeId, typeId: '', date: localDate(), description: '', recordedBy: store.settings.name };
  const employees = visibleEmployees().filter(employee => employee.status === 'Active');
  const issuers = issuerNames();
  openModal('Record New Violation', `<div class="modal-stepper"><span class="step-circle">1</span><span class="current">Enter details</span><span class="step-line"></span><span class="step-circle">2</span><span>Review & confirm</span></div><form id="record-form"><p class="form-error" role="alert"></p><div class="form-grid">
    <div class="field span-full employee-picker"><label for="record-employee">Employee (required)</label><input id="record-employee" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="employee-suggestions" aria-describedby="employee-picker-status" autocomplete="off" autocapitalize="words" spellcheck="false" required placeholder="Type an employee name or code"><input id="record-employee-id" type="hidden" name="employeeId"><div id="employee-suggestions" class="employee-suggestions" role="listbox" aria-label="Employee suggestions" hidden></div><small id="employee-picker-status" role="status" aria-live="polite">Type a name or employee code, then tap a suggestion.</small></div>
    <div class="field span-full"><label for="record-type">Violation type (required)</label><select id="record-type" name="typeId" required><option value="">Select a violation type</option>${resources.activeTypes.items.map(type => `<option value="${esc(type.id)}" ${type.id === d.typeId ? 'selected' : ''}>${esc(type.name)}</option>`).join('')}</select></div>
    <div class="field"><label for="record-issuer">Issued by</label><select id="record-issuer" name="recordedBy" required>${issuers.map(name => `<option value="${esc(name)}" ${name === d.recordedBy ? 'selected' : ''}>${esc(name)}${name === store.settings.name ? ' (you)' : ''}</option>`).join('')}</select></div>
    <div class="field"><label for="record-date">Issued at</label><input id="record-date" name="date" type="date" required readonly aria-readonly="true" value="${localDate()}"><small>Today is shown for this form preview.</small></div>
    <div class="field span-full"><label for="record-description">Notes / Incident details <span class="muted">(optional)</span></label><textarea id="record-description" name="description" maxlength="2000" placeholder="Add any details that may help with the review.">${esc(d.description)}</textarea></div>
    </div></form>`, `<button class="button secondary" data-action="close-modal">Cancel</button><button class="button primary" type="submit" form="record-form">Review & Submit ${icon('arrow', 16)}</button>`);
  bindEmployeePicker(dialog, employees, d.employeeId, esc);
}
function recordReview() {
  const e = store.employees.find(employee => employee.id === draft.employeeId);
  const t = resources.activeTypes.items.find(type => type.id === draft.typeId);
  openModal('Review Violation', `<div class="modal-stepper"><span class="step-circle">${icon('check', 13)}</span><span>Enter details</span><span class="step-line"></span><span class="step-circle">2</span><span class="current">Review & confirm</span></div><p class="form-error" role="alert"></p><p class="form-intro">Please check these details before adding this record to the employee’s history.</p><div class="review-summary"><dl>
    <dt>Employee</dt><dd>${esc(e.name)}<small class="muted" style="display:block">${esc(e.id)}</small></dd>
    <dt>Violation</dt><dd>${esc(t.name)}</dd><dt>Demerit Points</dt><dd>${draft.points} points <small class="muted">from violation type</small></dd><dt>Strike Violation</dt><dd>${draft.strike ? 'Yes' : 'No'}</dd>
    <dt>Issued by</dt><dd>${esc(draft.recordedBy)}</dd><dt>Issued at</dt><dd>${formatDate(draft.date)}</dd>
    <dt>Notes / Incident details</dt><dd class="review-description">${esc(draft.description || 'No notes provided.')}</dd>
    </dl></div><label class="confirm-check"><input id="confirm-record" type="checkbox">I have reviewed the details and confirm that this violation should be recorded.</label>`, `<button class="button secondary" data-action="record-back">${icon('chevron-left', 16)} Back to details</button><button class="button primary" data-action="confirm-record" disabled>${icon('check', 17)} Confirm & Record</button>`);
}
async function caseDetails(id){
    const recent=resources.recent.items.find(record=>record.id===id);
    if(!visibleViolations().some(record=>record.id===id)&&!employeeProfile.violations.some(record=>record.id===id)&&!(store.settings.role!=='Supervisor'&&recent)){toast('This case is not available in the selected view.','alert');return;}
    openModal('Violation Details',resourceState({status:'loading'},'case details'),`<button class="button secondary" data-action="close-modal">Close</button>`);
    const version=modalVersion;
    let v;try{v=normalizeViolation(await apiRequest('/violations/'+apiId(id)),[...store.employees,...(employeeProfile.employee?[employeeProfile.employee]:[]),...(recent?.employee?[recent.employee]:[])]);}catch(error){if(dialog.open&&modalVersion===version)dialog.querySelector('.modal-content').innerHTML=resourceState({status:'error',error:error.message},'case details').replace('data-action="refresh-data"',`data-action="case-details" data-id="${esc(id)}"`);return;}
    if(!dialog.open||modalVersion!==version)return;
    const e=store.employees.find(employee=>employee.apiId===v.employeeApiId)||v.employee;if(!e)return;
    const readonly=!canRecord();
    openModal('Violation Details',`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:22px">${person(e)}</div><div class="review-summary"><dl><dt>Case number</dt><dd>${esc(v.id)}</dd><dt>Violation type</dt><dd>${esc(v.typeName)}</dd><dt>Incident date</dt><dd>${formatDate(v.date)}</dd><dt>Demerit Points</dt><dd>${v.points}</dd><dt>Strike Violation</dt><dd>${v.strike?'Yes':'No'}</dd><dt id="case-issuer-label">Issued by</dt><dd>${readonly?esc(v.recordedBy):`<select id="case-issuer" name="recordedBy" form="case-form" aria-labelledby="case-issuer-label" required>${!v.recordedBy?'<option value="" selected>Choose an issuer</option>':''}${unique([v.recordedBy,...issuerNames()]).map(name=>`<option value="${esc(name)}" ${name===v.recordedBy?'selected':''}>${esc(name)}</option>`).join('')}</select>`}</dd><dt id="case-notes-label">Incident details</dt><dd class="review-description">${readonly?esc(v.description||'No notes provided.'):`<textarea id="case-notes" name="description" form="case-form" aria-labelledby="case-notes-label" maxlength="2000">${esc(v.description)}</textarea>`}</dd></dl></div>
    <form id="case-form" data-id="${esc(id)}"><p class="form-error" role="alert"></p></form>
    ${canManage()?`<div style="margin-top:25px;padding-top:17px;border-top:1px solid #e1e7ef;display:flex;justify-content:space-between;align-items:center;gap:12px"><small class="muted">Incorrect record? A reason for removal is required.</small><button class="button danger-outline small" data-action="remove-violation" data-id="${esc(id)}">${icon('trash',14)} Remove record</button></div>`:''}`,`<button class="button secondary" data-action="close-modal">Close</button>${readonly?'':'<button class="button primary" type="submit" form="case-form">Save Changes</button>'}`);
  }

function removeViolation(id){if(!canManage())return;const v=visibleViolations().find(v=>v.id===id)||employeeProfile.violations.find(v=>v.id===id)||(store.settings.role!=='Supervisor'?resources.recent.items.find(v=>v.id===id):null);if(!v)return;const e=store.employees.find(e=>e.apiId===v.employeeApiId)||v.employee;openModal('Remove Violation Record',`<div class="callout warning">${icon('alert')}<p>This will remove <strong>${esc(v.typeName)}</strong> from ${esc(e.name)}’s active history and adjust their points and strikes. The reason and original record will remain in the removal history.</p></div><form id="remove-form" data-id="${esc(id)}"><p class="form-error" role="alert"></p><div class="field"><label for="remove-reason">Reason for removal (required)</label><textarea id="remove-reason" name="reason" required minlength="10" maxlength="1000" placeholder="Explain why this record should be removed."></textarea><small>Minimum 10 characters. This explanation will appear in the audit trail.</small></div><label class="confirm-check" style="margin-top:20px"><input type="checkbox" required name="confirmed">I understand this record will be removed from the employee’s active history.</label></form>`,`<button class="button secondary" data-action="case-details" data-id="${esc(id)}">Keep record</button><button class="button danger" type="submit" form="remove-form">Remove Violation</button>`);}
function confirmType(id,mode){if(!canManage())return;const t=store.types.find(t=>t.id===id);if(!t)return;const deleting=mode==='delete';openModal(deleting?'Delete Violation Type':`${t.active?'Deactivate':'Reactivate'} Violation Type`, `<p style="margin-bottom:18px">${deleting?'Delete':t.active?'Deactivate':'Reactivate'} <strong>${esc(t.name)}</strong>?</p><p class="muted" style="font-size:14px">${deleting?'This category will be deleted from the backend. Types referenced by records cannot be deleted.':t.active?'Staff will no longer be able to select this category for new violations. Existing records will keep their details.':'Staff will be able to select this category for new violations again.'}</p>`,`<button class="button secondary" data-action="close-modal">Cancel</button><button class="button ${deleting?'danger':'primary'}" data-action="confirm-type" data-id="${esc(id)}" data-mode="${mode}">${deleting?'Delete Type':t.active?'Deactivate':'Reactivate'}</button>`);}

document.addEventListener('click',async event=>{const el=event.target.closest('[data-action]');if(!el)return;const action=el.dataset.action;const id=el.dataset.id;try{if(action.startsWith('sec-')){await handleSecondary(action,el,ctx());return;}switch(action){
case 'navigate':if(dialog.open)closeModal();navigate(el.dataset.page);break;
case 'profile':if(dialog.open)closeModal();navigate('profile',id);break;
case 'toggle-nav':document.body.classList.toggle('nav-open');syncNavigation();if(document.body.classList.contains('nav-open'))document.querySelector('.nav-item.active')?.focus();else document.querySelector('.mobile-toggle')?.focus();break;
case 'close-modal':closeModal();break;
case 'dismiss-toast':document.querySelector('#toast-region').innerHTML='';break;
case 'retry-employees':case 'refresh-data':await refreshWorkspace();ensurePageData(page);break;
case 'check-mutation':await checkPendingMutation(mutationContext());break;
case 'add-employee':await employeeForm();break;
case 'edit-employee':await employeeForm(id);break;
case 'employee-state':confirmEmployeeState(id,el.dataset.mode);break;
case 'retry-profile':await ensureCurrentProfile(true);break;
case 'add-type':await typeForm();break;
case 'edit-type':await typeForm(id);break;
case 'toggle-type':confirmType(id,'toggle');break;
case 'delete-type':confirmType(id,'delete');break;
case 'confirm-type':{const t=store.types.find(type=>type.id===id);if(!canManage()||!t)return;const mode=el.dataset.mode==='delete'?'delete':t.active?'deactivate':'activate';await mutate({message:'Violation type updated successfully.',execute:()=>changeType(id,mode,store.settings.name),reconcile:async()=>{try{const current=normalizeType(await apiRequest('/violation-types/'+apiId(id)));return mode==='delete'?false:current.active===(mode==='activate');}catch(error){if(mode==='delete'&&error.status===404)return true;throw error;}}});break;}
case 'record':draft=null;await recordForm(el.dataset.employee||'');break;
case 'record-back':await recordForm('',true);break;
case 'confirm-record':{
  if(checkingDraft||mutationInFlight()||!canRecord()||!draft||!document.querySelector('#confirm-record')?.checked)return;
  checkingDraft=true;
  const confirmButton=dialog.querySelector('[data-action="confirm-record"]');if(confirmButton)confirmButton.disabled=true;
  try{const employee=visibleEmployees().find(employee=>employee.id===draft.employeeId);if(!employee)return;const current=normalizeType(await apiRequest('/violation-types/'+apiId(draft.typeId)));if(!current.active){formError(dialog,'This violation type is now inactive. Choose another type.');return;}if(current.points!==draft.points||current.strike!==draft.strike){Object.assign(draft,{points:current.points,strike:current.strike});const type=resources.activeTypes.items.find(type=>type.id===current.id);if(type)Object.assign(type,current);recordReview();toast('The violation type changed. Review the updated points and strike before confirming.','info');return;}const input={...draft},before=new Set(store.violations.map(record=>record.id));checkingDraft=false;await mutate({message:'Violation recorded successfully.',execute:()=>issueViolation(employee.apiId,input,store.settings.name),reconcile:async()=>{const rows=await apiRequest('/employees/'+apiId(employee.apiId)+'/violations',{query:{limit:50,offset:0}});if(!Array.isArray(rows))throw Error('Could not read the employee history.');return rows.some(row=>!before.has(String(row.id))&&String(row.violation_type_id)===input.typeId&&(row.notes||'')===input.description&&row.issued_by===input.recordedBy)?true:null;}});}
  catch(error){formError(dialog,error.message||'The violation could not be saved.');}
  finally{checkingDraft=false;if(confirmButton?.isConnected)confirmButton.disabled=!document.querySelector('#confirm-record')?.checked;}
  break;
}

case 'case-details':await caseDetails(id);break;
case 'remove-violation':removeViolation(id);break;
case 'clear-filters':filters[el.dataset.page]={};employeePage=1;violationPage=1;render();break;
case 'paginate':if(el.dataset.page==='employees')employeePage=Number(el.dataset.number);else if(el.dataset.page==='profile')filters.profile={page:Number(el.dataset.number)};else if(el.dataset.page==='history')filters.history={...filters.history,page:Number(el.dataset.number)};else violationPage=Number(el.dataset.number);render();(document.querySelector('.mobile-record-list')?.getClientRects().length?document.querySelector('.mobile-record-list'):document.querySelector('.history-panel')||document.querySelector('.table-wrap'))?.scrollIntoView({block:'start',behavior:'smooth'});break;

case 'watchlist':filters.employees={strikes:'watchlist'};employeePage=1;navigate('employees');break;
case 'dashboard-card':{const target=el.dataset.target;if(target==='watchlist'){filters.employees={strikes:'watchlist'};employeePage=1;navigate('employees');}else if(target==='points'){filters.reports={};navigate('reports');}else if(target==='employees'){filters.employees={};employeePage=1;navigate('employees');}else{filters.violations={};violationPage=1;navigate('violations');}break;}
case 'account':openModal('Your Profile',`<div class="callout">${icon('info')}<p>This is a fictional preview user. Role selection previews the interface on this tab; sign-in and permissions belong to the backend integration.</p></div><div class="profile-top" style="padding:0 0 24px">${avatar({name:store.settings.name,id:'EMP-000'})}<div><h2>${esc(store.settings.name || 'Set your name in Settings')}</h2><p class="muted">${esc(store.settings.role)} · Northpoint</p></div></div><form id="role-form"><div class="field"><label for="demo-role">View workspace as</label><select id="demo-role" name="role">${['HR','Supervisor'].map(r=>`<option ${store.settings.role===r?'selected':''}>${r}</option>`).join('')}</select></div><div class="field" style="margin-top:18px"><label for="demo-dept">Supervisor’s assigned department</label><select id="demo-dept" name="department">${unique(store.employees.map(e=>e.department)).map(d=>`<option ${store.settings.department===d?'selected':''}>${esc(d)}</option>`).join('')}</select></div></form>`,`<button class="button secondary" data-action="close-modal">Cancel</button><button class="button primary" type="submit" form="role-form">Switch View</button>`);break;
case 'export-employees':downloadCSV('NorthPoint-Employees', [['Employee ID','Name','Department','Position','Employment Status','Demerit Points','Strikes'],...visibleEmployees().map(e=>{const s=employeeSummary(e.id);return [e.id,e.name,e.department,e.position,e.status,s.points,s.strikes];})]);break;
case 'export-violations':downloadCSV('NorthPoint-Violations',[['Case number','Employee ID','Employee','Violation','Incident date','Demerit Points','Strike','Recorded by','Status'],...visibleViolations().map(v=>[v.id,v.employeeId,store.employees.find(e=>e.id===v.employeeId)?.name,v.typeName,v.date,v.points,v.strike?'Yes':'No',v.recordedBy,v.status])]);break;

}}catch(error){toast(error.message||'Unable to complete that action. Please try again.','alert');}});

document.addEventListener('submit',async event=>{const form=event.target;if(!(form instanceof HTMLFormElement))return;event.preventDefault();try{const values=Object.fromEntries(new FormData(form));switch(form.id){
case 'global-search':{if(employeeDirectory.status!=='ready'||resources.records.status!=='ready'){toast('Live data is still loading or unavailable. Refresh before searching.','alert');return;}const q=(values.query||'').trim().toLowerCase();if(!q)return;const es=visibleEmployees().filter(e=>`${e.name} ${e.id} ${e.department}`.toLowerCase().includes(q));const vs=visibleViolations().filter(v=>`${v.id} ${v.typeName} ${store.employees.find(e=>e.id===v.employeeId)?.name}`.toLowerCase().includes(q)).slice(0,8);openModal('Search Results',`<p class="muted" style="font-size:14px;margin-bottom:20px">Results for “${esc(values.query.trim())}”</p>${es.length?`<h3>Employees</h3>${es.map(e=>`<div class="watchlist-row">${person(e)}<span class="muted" style="font-size:13px">${esc(e.department)}</span></div>`).join('')}`:''}${vs.length?`<h3 style="margin-top:25px">Violation records</h3>${vs.map(v=>`<button class="button ghost full" data-action="case-details" data-id="${esc(v.id)}" style="justify-content:space-between;text-align:left;white-space:normal">${esc(v.typeName)}<span class="muted">${esc(v.id)}</span>${icon('chevron-right',14)}</button>`).join('')}`:''}${!es.length&&!vs.length?empty('No matching records','Try an employee name, ID, or violation type.'):''}`,`<button class="button secondary" data-action="close-modal">Close</button>`);break;}
case 'employee-filters':filters.employees={...filters.employees,...values};employeePage=1;render();break;
case 'violation-filters':if(values.from&&values.to&&values.from>values.to){formError(form,'The end date must be on or after the start date.');return;}filters.violations={...values,strike:values.strike==='on'};violationPage=1;render();break;
case 'type-filters':filters.types=values;render();break;
case 'employee-form': {
  if(!form.dataset.id&&values.department==='__other_department__'){values.department=(values.newDepartment||'').trim();if(!values.department){formError(form,'Enter the new department name or choose No department assigned.');return;}}
  if(!canManage())return;
  const id=form.dataset.id;
  if(id){
    if(!editingEmployee||editingEmployee.apiId!==id){formError(form,'Reload this employee before saving.');return;}
    const payload=employeeUpdatePayload(values,editingEmployee);
    if(!Object.keys(payload).length){toast('No employee details have changed.','info');return;}
    await mutate({message:'Employee updated successfully.',execute:async()=>{await patchEmployee(id,payload,store.settings.name);invalidateEmployeeProfile();},reconcile:async()=>employeeMatchesUpdate((await fetchEmployeeProfile(id)).employee,payload)},form);
  }else await submitApiEmployeeForm(form,values,{dialog,actor:store.settings.name,refresh:refreshApiEmployees,formError,closeModal,render,toast,resetFilters:()=>{filters.employees={};employeePage=1;store.employees=employeeDirectory.items;void Promise.all([loadRecords(true),loadRecent(true),loadTimeline(true),loadRemovals(true)]);}});
  break;
}
case 'employee-state-form':{
  if(!canManage())return;const id=form.dataset.id,mode=form.dataset.mode;
  if(!editingEmployee||editingEmployee.apiId!==id)return;
  if(mode==='delete'&&(values.code!==editingEmployee.id||!values.confirmed)){formError(form,'Type the employee code exactly and confirm permanent deletion.');return;}
  await mutate({message:mode==='delete'?'Employee permanently deleted.':mode==='deactivate'?'Employee deactivated.':'Employee reactivated.',execute:async()=>{await changeEmployeeState(id,mode,store.settings.name);invalidateEmployeeProfile();if(mode==='delete'){filters.employees={};employeePage=1;navigate('employees');}},reconcile:async()=>{try{const result=await fetchEmployeeProfile(id);return mode==='delete'?false:result.employee.status===(mode==='deactivate'?'Inactive':'Active');}catch(error){if(mode==='delete'&&error.status===404){invalidateEmployeeProfile();navigate('employees');return true;}throw error;}}},form);break;
}
case 'type-form': {
  if(!canManage())return;
  const id=form.dataset.id;
  await mutate({message:'Violation type saved successfully.',execute:()=>saveType(id,values,store.settings.name),reconcile:async()=>{await loadTypes(true);if(resources.types.status!=='ready')throw Error(resources.types.error);const target=resources.types.items.find(type=>id?type.id===id:type.name===values.name.trim());return target&&target.name===values.name.trim()&&target.description===values.description.trim()&&target.points===Number(values.points)&&target.strike===(values.strike==='on')?true:null;}},form);
  break;
}
case 'record-form': {
  if (!canRecord()) return;
  const employee = visibleEmployees().find(employee => employee.id === values.employeeId && employee.status === 'Active');
  const type = resources.activeTypes.items.find(type => type.id === values.typeId && type.active);
  const issuers = issuerNames();
  if (!employee) { formError(form, 'Choose an employee from the suggestions.'); return; }
  if (!type) { formError(form, 'Choose an active violation type.'); return; }
  if (!issuers.includes(values.recordedBy)) { formError(form, 'Choose who issued this violation.'); return; }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(values.date) || Number.isNaN(Date.parse(values.date)) || values.date > localDate()) { formError(form, 'Choose a valid issue date on or before today.'); return; }
  draft = { employeeId: employee.id, typeId: type.id, date: values.date, description: (values.description || '').trim(), recordedBy: values.recordedBy, status: null, points: Number(type.points), strike: Boolean(type.strike) };
  recordReview();
  break;
}
case 'case-form':{if(!canRecord())return;const id=form.dataset.id;await mutate({message:'Violation details updated successfully.',execute:()=>updateViolation(id,values,store.settings.name),reconcile:async()=>{const record=await apiRequest('/violations/'+apiId(id));return (record.notes||'')===(values.description||'').trim()&&record.issued_by===values.recordedBy;}},form);break;}
case 'remove-form':{if(!canManage()||!values.confirmed)return;const id=form.dataset.id;await mutate({message:'Violation removed. The reason is saved in History.',execute:()=>deleteViolation(id,values.reason,store.settings.name),reconcile:async()=>{await loadRemovals(true);if(resources.removals.status!=='ready')throw Error(resources.removals.error);return resources.removals.items.some(removal=>removal.violationId===id&&removal.reason===values.reason.trim())?true:null;}},form);break;}
case 'role-form':if(!['HR','Supervisor'].includes(values.role))return;store.settings.role=values.role;store.settings.department=values.department;if(persist(`Workspace switched to the ${values.role} view.`)){closeModal();navigate('dashboard');}break;
case 'secondary-filter':await handleSecondary('sec-filter-apply',{dataset:{page:form.dataset.filterPage}},ctx());break;
case 'secondary-settings-form':await handleSecondary('sec-settings-save',{dataset:{}},ctx());break;
case 'secondary-user-form':await handleSecondary('sec-user-save',{dataset:{}},ctx());break;
default:if(form.id.startsWith('sec-')){const button=form.querySelector('[data-action]')||dialog.querySelector('.modal-footer [data-action^="sec-"]');if(button)await handleSecondary(button.dataset.action,button,ctx());}
}}catch(error){formError(form,error.message||'Unable to save changes. Please review the fields.');toast(error.message||'Unable to save changes.','alert');}});
document.addEventListener('change',event=>{const el=event.target;if(el.id==='emp-department'&&document.querySelector('#employee-new-department-field')){const other=el.value==='__other_department__';const field=document.querySelector('#employee-new-department-field');const input=document.querySelector('#emp-new-department');field.hidden=!other;input.disabled=!other;input.required=other;if(other)input.focus();}if(el.id==='employee-order'){filters.employees={...filters.employees,order:el.value};employeePage=1;render();document.querySelector('#employee-order')?.focus({preventScroll:true});}if(el.id==='report-period'){filters.reports={...filters.reports,days:Number(el.value)};render();document.querySelector('#report-period')?.focus({preventScroll:true});}if(el.id==='confirm-record')dialog.querySelector('[data-action="confirm-record"]').disabled=!el.checked;});
document.addEventListener('keydown',event=>{if(handleCalendarKeydown(event,ctx()))return;const reportTab=event.target.closest?.('[data-action="sec-report-tab"],[data-action="sec-history-tab"]');if(reportTab&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const action=reportTab.dataset.action;const tabs=[...document.querySelectorAll('[data-action="'+action+'"]')];const index=tabs.indexOf(reportTab);const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;handleSecondary(action,tabs[next],ctx());return;}if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();document.querySelector('#global-query')?.focus();}if(event.key==='Escape'){document.body.classList.remove('nav-open');syncNavigation();}});
dialog.addEventListener('cancel',event=>{if(employeeCreateInFlight()||mutationInFlight()||checkingDraft)event.preventDefault();});
dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeModal();}});
function syncNavigation(){const sidebar=document.querySelector('.sidebar');const open=document.body.classList.contains('nav-open');if(sidebar){sidebar.inert=matchMedia('(max-width:900px)').matches&&!open;sidebar.setAttribute('aria-hidden',String(sidebar.inert));}const workspace=document.querySelector('.workspace');if(workspace)workspace.inert=matchMedia('(max-width:900px)').matches&&open;document.querySelector('.mobile-toggle')?.setAttribute('aria-expanded',String(open));}
window.addEventListener('resize',()=>{syncNavigation();syncPhoneFilters();});
function refreshWeeklyDashboard(){if(page==='dashboard'&&!dialog.open&&startOfWeek(localDate())!==displayedWeek)void refreshWorkspace();}
window.addEventListener('focus',refreshWeeklyDashboard);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshWeeklyDashboard();});
setInterval(refreshWeeklyDashboard,60000);
window.addEventListener('hashchange',route);
document.querySelector('.skip-link').addEventListener('click',event=>{event.preventDefault();document.querySelector('#main')?.focus();});
function issuerNames(){return unique([store.settings.name,...store.violations.map(record=>record.recordedBy),...store.activities.map(event=>event.actor)]);}
function showPending(){openModal('Check Save Status',`<p class="form-error show" role="alert">${esc(pendingMutation()?.error||'The save has not been confirmed.')}</p><div class="callout warning">${icon('info')}<p>A previous change has not been confirmed. Check the backend before making another change. This check will not send another save request.</p></div>`,`<button class="button secondary" data-action="close-modal">Close</button><button class="button primary" data-action="check-mutation">Check save status</button>`);}
function mutationContext(form){return {dialog,actor:store.settings.name,error:message=>{if(pendingMutation())pendingMutation().error=message;formError(form||dialog,message);},showPending,refresh:async()=>{await refreshWorkspace();await loadActiveTypes(true);await ensureCurrentProfile(true);return employeeDirectory.status!=='ready'||['records','types','timeline','removals'].some(name=>resources[name].status==='error')||page==='profile'&&employeeProfile.status!=='ready'?'Some lists could not refresh. Use Try again to reload them.':'';},close:closeModal,render,toast};}
async function mutate(task,form){if(employeeCreateInFlight())return;if(pendingEmployeeCreation()){employeeForm();return;}await runMutation(task,mutationContext(form));}
let updateQueued=false;
watchBackend(()=>{if(updateQueued)return;updateQueued=true;queueMicrotask(()=>{updateQueued=false;ensurePageData(page);void ensureCurrentProfile();render();});});
route();
