import { renderReports, renderHistory } from '../reports/insights.js';
import { handleCalendarAction } from '../history/calendar.js';
/* Connected views. Preferences apply only to the current tab. */

const statuses = ['Active', 'Inactive'];
const uniq = values => [...new Set(values.filter(Boolean))].sort();

function options(values, current, esc, first = 'All') {
  return `<option value="">${esc(first)}</option>${values.map(value => `<option value="${esc(value)}"${value === current ? ' selected' : ''}>${esc(value)}</option>`).join('')}`;
}

function field(label, content) { return `<label class="field"><span>${label}</span>${content}</label>`; }
function empty(message, detail = 'Try a wider date range or clear the filters.') {
  return `<div class="empty-state"><h3>${message}</h3><p class="muted">${detail}</p></div>`;
}

function settings(ctx) {
  const s = ctx.store.settings;
  const { esc, icon } = ctx;
  return `<div class="two-column" style="align-items:start"><section class="panel"><div class="panel-header"><div><h2>Your Preferences</h2><p class="muted">Make this workspace comfortable for you</p></div></div><form id="secondary-settings-form" class="panel-body" style="display:grid;gap:22px">
      <div class="field"><span>Signed-in name</span><strong>${esc(ctx.sessionState?.fullName||s.name||'Sign in required')}</strong>${ctx.sessionState?.status==='error'?`<p class="muted">${esc(ctx.sessionState.error)}</p><button class="button secondary" type="button" data-action="session-retry">Retry Sign-in Check</button>`:''}</div>
      ${field('Text size', `<select name="textSize"><option value="standard"${s.textSize !== 'larger' ? ' selected' : ''}>Standard — comfortable reading</option><option value="larger"${s.textSize === 'larger' ? ' selected' : ''}>Larger — extra reading comfort</option></select>`)}
      <p class="muted" style="margin:0">Larger text increases the size of navigation, forms, and body text throughout the workspace.</p>
      <div class="settings-actions"><button type="submit" class="button primary">${icon('check')} Save Changes</button><button type="button" class="button danger" data-action="sign-out">Sign out</button></div>
    </form></section><div>
      <section class="panel settings-rule-restore"><div class="panel-header"><h2>Company Violation Categories</h2></div><div class="panel-body"><p>Restore missing company categories, specific violations, and penalty schedules. Existing entries, penalties, and inactive settings are kept.</p><p class="muted">Categories are shared by all accounts. Your custom violation types stay alongside the company rules.</p><button type="button" class="button primary" data-action="restore-company-rules">Restore Violation Categories</button></div></section>
      <section class="panel"><div class="panel-header"><h2>About This Workspace</h2></div><div class="panel-body"><p><strong>Northpoint</strong><br>Violation Management System</p><p class="muted">A dedicated space for employee records, disciplinary cases, and clear reporting.</p><div class="callout" style="margin-top:20px"><div><strong>About this build</strong><p>Employee records, violations and history are connected to the hosted backend. Your signed-in full name is used automatically. Preferences reset when you reload.</p></div></div></div></section>
    </div></div>`;
}

function help(ctx){
 const {icon,esc}=ctx;
 const steps=[
  ['Find an Employee','Open Employees, search for a name or employee ID, then select View Profile.'],
  ['Issue a Violation','On the employee’s profile, choose Record violation to open the form.'],
  ['Select a Violation','Choose a category and specific violation. Review the offense number, company-rule conditions, and penalty. Add optional incident details.'],
  ['Record','Review the summary, tick the confirmation checkbox, then confirm the record.']
 ];
 const questions=[
  ['What is an offense number?','An employee has a separate offense sequence for each specific violation. The backend counts active and removed records when assigning the next offense.'],
  ['How is the penalty selected?','Each specific violation has penalty tiers. The backend uses its offense number to select and store the penalty. Review alternatives and conditions in the company rules before recording. Existing records retain their penalty snapshot.'],
  ['What is Watchlist?','Watchlist shows employees who reached offense 3 or later on any specific violation, including removed records. Open Reports & Analytics, then select Watchlist to view them. Select a name to open the employee’s profile.'],
  ['Accidentally removed a user?','If an employee was deactivated, filter Employees by Inactive, open their profile, choose Edit Employee, then Reactivate. A permanently deleted employee cannot be restored through this website. Contact your administrator for assistance.'],
  ['Can I make the text larger?','Open Settings, choose Larger under Text size and select Save Changes. This preference applies to the current tab and resets on reload.'],
  ['How do I sign out?','Select your account name or avatar at the top right, then choose Sign out. You can also use the red Sign out button in Settings.']
 ];
 return `<section class="panel help-start"><div class="panel-header"><div><h2>How Can We Help?</h2><p class="muted">Record a violation in four simple steps.</p></div></div><div class="panel-body"><ol class="help-steps">${steps.map(([title,text],i)=>`<li><span class="help-number" aria-hidden="true">${String(i+1).padStart(2,'0')}</span><div><h3>${esc(title)}</h3><p>${esc(text)}</p></div></li>`).join('')}</ol><div class="help-section-action"><button class="button secondary" data-action="sec-help-nav" data-page="employees">${icon('users',17)} Go to Employees</button></div></div></section>
 <section class="panel help-photo-guide"><div class="panel-header"><div><h2>How to use Photo Library?</h2><p class="muted">Photos uploaded from the Tracker app appear in Northpoint’s Photo Library.</p></div></div><div class="panel-body"><ol class="help-photo-list"><li><strong>Upload from the Tracker app</strong><p>In the Tracker app, take or select a photo and upload it. After it uploads, the photo appears in the Photo Library on this website.</p></li><li><strong>Find and view photos</strong><p>Admins can use search and filters to find photos. Select a thumbnail or title to open the photo and see its details.</p></li><li><strong>Review activity</strong><p>Admins can open the Activity Log to see photo activity and filter it by user, action, or date. Photos on this page shows the related photos; select one to enlarge it. View History shows its recorded changes.</p></li></ol><div class="help-section-action"><button class="button secondary" data-action="sec-help-nav" data-page="photos">${icon('image',17)} Open Photo Library</button></div></div></section>
 <section class="panel help-questions"><div class="panel-header"><h2>Common Questions</h2></div><div class="panel-body">${questions.map(([title,text],i)=>`<details ${i===0?'open':''}><summary><strong>${esc(title)}</strong></summary><p>${esc(text)}</p></details>`).join('')}</div></section>`;
}

export function renderSecondary(page, ctx) {
  const views = { reports:renderReports, history:renderHistory, settings, help };
  return views[page] ? views[page](ctx) : '';
}

export function handleSecondary(action, el, ctx) {
  const { esc } = ctx;
  if(action.startsWith('sec-calendar-'))return handleCalendarAction(action,el,ctx);
  if (action === 'sec-filter-apply') {
    const form = document.getElementById('secondary-filter');
    const values = Object.fromEntries(new FormData(form));
    const error = document.getElementById('secondary-filter-error');
    if (values.from && values.to && values.from > values.to) {
      error.textContent = 'The end date must be on or after the start date.';
      error.hidden = false;
      error.classList.add('show');
      form.elements.to.focus();
      return true;
    }
    ctx.setFilters(el.dataset.page, { ...ctx.getFilters(el.dataset.page), ...values, page: 1 });
    ctx.render();
    return true;
  }
  if (action === 'sec-filter-clear') {
    const page = el.dataset.page;
    ctx.setFilters(page, page==='history'?{tab:ctx.getFilters(page).tab||'activity'}:{});
    ctx.render();
    return true;
  }
  if (action === 'sec-report-tab' || action === 'sec-history-tab') {
    const history=action==='sec-history-tab';
    ctx.setFilters(history?'history':'reports',history?{tab:el.dataset.tab,page:1,month:ctx.getFilters('history').month}:{...ctx.getFilters('reports'),tab:el.dataset.tab});
    ctx.render();
    const tab=document.getElementById((history?'history-tab-':'report-tab-')+el.dataset.tab);
    tab?.focus({preventScroll:true});
    tab?.scrollIntoView({block:'nearest',inline:'nearest'});
    return true;
  }
  if (action === 'sec-print') { window.print(); return true; }
  if (action === 'sec-help-nav') { ctx.navigate(el.dataset.page); return true; }
  if (action === 'sec-settings-save') {
    const form = document.getElementById('secondary-settings-form');
    if (!form.reportValidity()) return true;
    const values = Object.fromEntries(new FormData(form));
    Object.assign(ctx.store.settings, {textSize:values.textSize==='larger'?'larger':'standard'});
    ctx.saveStore();
    document.documentElement.dataset.textSize = values.textSize;
    document.body.classList.toggle('larger-text', values.textSize === 'larger');
    ctx.render();
    ctx.toast('Preferences applied to this tab.');
    return true;
  }
  if (action === 'sec-modal-cancel') { ctx.closeModal(); return true; }
  return false;
}
