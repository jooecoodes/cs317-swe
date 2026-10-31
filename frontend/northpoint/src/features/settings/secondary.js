import { renderReports, renderHistory } from '../reports/insights.js';
import { handleCalendarAction } from '../history/calendar.js';
/* Connected views. Preferences apply only to the current tab. */

const statuses = ['Active', 'Inactive'];
const roles = ['HR', 'Supervisor'];
const uniq = values => [...new Set(values.filter(Boolean))].sort();

function options(values, current, esc, first = 'All') {
  return `<option value="">${esc(first)}</option>${values.map(value => `<option value="${esc(value)}"${value === current ? ' selected' : ''}>${esc(value)}</option>`).join('')}`;
}

function field(label, content) { return `<label class="field"><span>${label}</span>${content}</label>`; }
function empty(message, detail = 'Try a wider date range or clear the filters.') {
  return `<div class="empty-state"><h3>${message}</h3><p class="muted">${detail}</p></div>`;
}

function users(ctx) {
  return `<section class="panel"><div class="empty-state">${ctx.icon('clock',36)}<h2>Coming Soon</h2><p>Users &amp; Roles will be available in a future update.</p></div></section>`;
}

function settings(ctx) {
  const s = ctx.store.settings;
  const { esc, icon } = ctx;
  return `<div class="two-column" style="align-items:start"><section class="panel"><div class="panel-header"><div><h2>Your Preferences</h2><p class="muted">Make this workspace comfortable for you</p></div></div><form id="secondary-settings-form" class="panel-body" style="display:grid;gap:22px">
      <div class="field"><span>Signed-in name</span><strong>${esc(ctx.sessionState?.fullName||s.name||'Sign in required')}</strong>${ctx.sessionState?.status==='error'?`<p class="muted">${esc(ctx.sessionState.error)}</p><button class="button secondary" type="button" data-action="session-retry">Retry Sign-in Check</button>`:''}</div>
      ${field('Text size', `<select name="textSize"><option value="standard"${s.textSize !== 'larger' ? ' selected' : ''}>Standard — comfortable reading</option><option value="larger"${s.textSize === 'larger' ? ' selected' : ''}>Larger — extra reading comfort</option></select>`)}
      <p class="muted" style="margin:0">Larger text increases the size of navigation, forms, and body text throughout the workspace.</p>
      <div style="padding-top:10px;border-top:1px solid #e8edf3"><h3 style="margin:0 0 16px">Workspace view</h3><p class="muted">Choose a department view for this tab. These filters do not change account permissions.</p></div>
      ${field('Workspace view', `<select name="role">${roles.map(role => `<option${role === s.role ? ' selected' : ''}>${role}</option>`).join('')}</select>`)}
      ${field('Assigned department', `<select name="department"><option value="">Select a department</option>${uniq(ctx.store.employees.map(e => e.department)).map(department => `<option${department === s.department ? ' selected' : ''}>${esc(department)}</option>`).join('')}</select>`)}
      <div><button type="submit" class="button primary">${icon('check')} Save Changes</button></div>
    </form></section><div>
      <section class="panel"><div class="panel-header"><h2>About This Workspace</h2></div><div class="panel-body"><p><strong>Northpoint</strong><br>Violation Management System</p><p class="muted">A dedicated space for employee records, disciplinary cases, and clear reporting.</p><div class="callout" style="margin-top:20px"><div><strong>About this build</strong><p>Employee records, violations and history are connected to the hosted backend. Your signed-in full name is used automatically. Preferences reset when you reload.</p></div></div></div></section>
      ${s.role === 'HR' ? `<section class="panel"><div class="panel-header"><h2>Refresh Data</h2></div><div class="panel-body"><p class="muted">Reload employees, violations, rulebook and history from the hosted backend.</p><button class="button secondary" data-action="refresh-data">Refresh Data</button></div></section>` : ''}
    </div></div>`;
}

function help(ctx) {
  const { icon } = ctx;
  return `<section class="panel"><div class="panel-header"><div><h2>How Can We Help?</h2><p class="muted">A short guide to your daily HR tasks</p></div></div><div class="panel-body"><div class="two-column">
    <article><span class="help-number">01</span><h3>Find an employee</h3><p>Open Employees, enter a name or employee ID, and select Search. Use department, employment status, or strike filters to narrow your results.</p><button class="button secondary" data-action="sec-help-nav" data-page="employees">${icon('users')} Go to Employees</button></article>
    <article><span class="help-number">02</span><h3>Record a violation</h3><p>Choose Record New Violation. Select the employee and violation type, enter the incident details, then review the summary before confirming.</p><button class="button secondary" data-action="sec-help-nav" data-page="violations">${icon('file-text')} Go to Violations</button></article>
    <article><span class="help-number">03</span><h3>Review an employee’s history</h3><p>Select View Profile beside an employee. Their profile brings together employee details, demerit points, strikes, and previous violations.</p><button class="button secondary" data-action="sec-help-nav" data-page="history">${icon('clock')} View History</button></article>
    <article><span class="help-number">04</span><h3>Prepare a report</h3><p>Open Reports &amp; Analytics and select a tab. Activity shows a choice of periods; the other tabs show totals across the full recorded history.</p><button class="button secondary" data-action="sec-help-nav" data-page="reports">${icon('download')} Go to Reports</button></article>
  </div></div></section>
  <section class="panel"><div class="panel-header"><h2>Common Questions</h2></div><div class="panel-body">
    <details open><summary><strong>What is a demerit point?</strong></summary><p>Demerit points are the penalty value assigned to a violation type. An employee’s total adds the points from their recorded violations. Removed records are excluded.</p></details>
    <details><summary><strong>What is a strike?</strong></summary><p>A strike marks a violation that counts toward disciplinary follow-up. Employees with two or more strikes appear in the repeat-offender watchlist. Your organization’s policies determine the appropriate action.</p></details>
    <details><summary><strong>Can I make the text larger?</strong></summary><p>Yes. Open Settings, choose Larger under Text size, and select Save Changes. Your preference applies to this tab and resets on reload.</p></details>
    <details><summary><strong>Why can I only see one department?</strong></summary><p>The Supervisor workspace view filters to the assigned department. The HR view includes all departments. Change your view in Settings.</p></details>
    <details><summary><strong>Is this connected to the company’s employee system?</strong></summary><p>Yes. Records are read from and saved to the hosted backend. If the connection fails, you will see an error. No record changes are saved locally.</p></details>
  </div></section>
  <div class="callout">${icon('info')}<div><strong>Keyboard-friendly by design</strong><p>Use Tab to move between controls and Enter or Space to select a button. Press Escape to close a dialog. Every field has a visible label.</p></div></div>`;
}

export function renderSecondary(page, ctx) {
  const views = { reports:renderReports, history:renderHistory, users, settings, help };
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
    if(!roles.includes(values.role)){ctx.toast('Choose HR or Supervisor.');return true;}
    Object.assign(ctx.store.settings, {textSize:values.textSize==='larger'?'larger':'standard',role:values.role,department:values.department||''});
    ctx.saveStore();
    document.documentElement.dataset.textSize = values.textSize;
    document.body.classList.toggle('larger-text', values.textSize === 'larger');
    ctx.render();
    ctx.toast('Preferences applied to this tab.');
    return true;
  }
  if (action === 'sec-user-add' || action === 'sec-user-save') { ctx.toast('Users & Roles: Coming Soon.','info'); return true; }
  if (action === 'sec-modal-cancel') { ctx.closeModal(); return true; }
  return false;
}
