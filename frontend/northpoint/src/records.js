import { sortEmployeeRecords } from './insight-data.js';
import { loadingSkeleton } from './loading.js';

const unique = values => [...new Set(values.filter(Boolean))].sort();
function options(values, current, all, esc) {
  return `<option value="">${esc(all)}</option>${values.map(value => `<option value="${esc(value)}" ${value === current ? 'selected' : ''}>${esc(value)}</option>`).join('')}`;
}
function empty(icon) { return `<div class="empty-state">${icon('search', 30)}<h3>No records found</h3><p>Try adjusting your search or clearing the filters.</p></div>`; }

export function employeeLoadState(directory, icon, esc) {
  if (directory.status === 'error') return `<div class="empty-state" role="alert">${icon('alert', 30)}<h3>Couldn’t load employees</h3><p>${esc(directory.error)}</p><button class="button primary" data-action="retry-employees" style="margin-top:18px">${icon('refresh', 17)} Try again</button></div>`;
  return loadingSkeleton('rows', 'employees');
}

export function renderEmployees(ctx) {
  const { esc, icon, badge, employeeSummary, visibleEmployees, person, pagination } = ctx;
  const f = ctx.getFilters('employees');
  const directory = ctx.employeeDirectory;
  const pending = directory && directory.status !== 'ready';
  const all = visibleEmployees();
  let employees = all.filter(employee => {
    const summary = employeeSummary(employee.id);
    return (!f.query || `${employee.name} ${employee.id}`.toLowerCase().includes(f.query.toLowerCase())) && (!f.department || employee.department === f.department) &&
      (!f.status || employee.status === f.status) && (!f.strikes || (f.strikes === 'watchlist' ? summary.strikes >= 2 : f.strikes === 'any' ? summary.total > 0 : summary.total === 0));
  });
  employees = sortEmployeeRecords(employees, employeeSummary, f.order);
  const total = employees.length;
  const page = Math.min(ctx.page, Math.max(1, Math.ceil(total / 8)));
  ctx.setPage(page);
  employees = employees.slice((page - 1) * 8, page * 8);
  const orderOptions = [['newest', 'Most recent first'], ['oldest', 'Least recent first'], ['points', 'Demerit points: high to low'], ['points-low', 'Demerit points: low to high'], ['strikes', 'Most strikes first'], ['name', 'Name: A to Z'], ['name-desc', 'Name: Z to A']];
  const desktop = `<div class="desktop-records table-wrap"><table><thead><tr><th>Employee</th><th>Department / Position</th><th>Status</th><th>Demerit Points</th><th>Strikes</th><th>Actions</th></tr></thead><tbody>${employees.map(employee => {
    const summary = employeeSummary(employee.id);
    return `<tr><td>${person(employee)}</td><td>${esc(employee.department || 'Unassigned')}<div class="person-id">${esc(employee.position || 'Not provided')}</div></td><td>${badge(employee.status)}</td><td><strong>${summary.points}</strong></td><td>${summary.strikes ? badge(`${summary.strikes} ${summary.strikes === 1 ? 'Strike' : 'Strikes'}`) : '<span class="muted">0 Strikes</span>'}</td><td><button class="button ghost small" data-action="profile" data-id="${esc(employee.profileId || employee.id)}">View Profile ${icon('chevron-right', 15)}</button></td></tr>`;
  }).join('')}</tbody></table></div>`;
  const phone = `<div class="mobile-record-list" aria-label="Employee records">${employees.map(employee => {
    const summary = employeeSummary(employee.id);
    return `<details class="record-disclosure"><summary><span class="record-summary"><strong>${esc(employee.name)}</strong><span class="record-code">${esc(employee.id)}</span><span class="record-category">${esc(employee.department || 'Unassigned')}</span></span><span class="record-chevron" aria-hidden="true">${icon('chevron-down', 21)}</span></summary><div class="record-expanded"><dl><div><dt>Status</dt><dd>${badge(employee.status)}</dd></div><div><dt>Demerit Points</dt><dd>${summary.points}</dd></div><div><dt>Strikes</dt><dd>${summary.strikes}</dd></div></dl><button class="button secondary full" data-action="profile" data-id="${esc(employee.profileId || employee.id)}">View Profile ${icon('chevron-right', 17)}</button></div></details>`;
  }).join('')}</div>`;
  return `${ctx.store.settings.role === 'Supervisor' ? `<div class="callout">${icon('info')}<p>You are viewing employees in <strong>${esc(ctx.store.settings.department)}</strong>, your assigned department.</p></div>` : ''}
    <form id="employee-filters" class="filters">
      <div class="field span-2"><label for="employee-query">Find an employee</label><input id="employee-query" name="query" placeholder="Search by name or employee ID" value="${esc(f.query || '')}"></div>
      <div class="field"><label for="employee-department">Department</label><select id="employee-department" name="department">${options(unique(all.map(employee => employee.department)), f.department, 'All departments', esc)}</select></div>
      <div class="field"><label for="employee-status">Employment status</label><select id="employee-status" name="status">${options(['Active', 'Inactive'], f.status, 'All statuses', esc)}</select></div>
      <div class="field"><label for="employee-strikes">Violation history</label><select id="employee-strikes" name="strikes"><option value="">All employees</option>${[['watchlist', '2 or more strikes'], ['any', 'With violations'], ['clean', 'No violations']].map(([value, name]) => `<option value="${value}" ${!ctx.store.recordsReady && ['any','clean'].includes(value) ? 'disabled title="Violation history is still loading or unavailable"' : ''} ${f.strikes === value ? 'selected' : ''}>${name}</option>`).join('')}</select></div>
      <div class="filter-actions" style="grid-column:span 2"><button class="button ghost" type="button" data-action="clear-filters" data-page="employees">Clear Filters</button><button class="button primary" type="submit">${icon('search', 17)} Search</button></div>
    </form><section class="panel employee-directory" aria-busy="${pending && directory.status !== 'error' ? 'true' : 'false'}"><div class="panel-header"><h2>Employee directory <span class="count-label">${pending ? directory.status === 'error' ? 'Unavailable' : 'Loading…' : total + ' employees'}</span></h2><div class="directory-order field"><label for="employee-order">Order by</label><select id="employee-order" ${pending ? 'disabled' : ''}>${orderOptions.map(([value, name]) => `<option value="${value}" ${(f.order || 'newest') === value ? 'selected' : ''}>${name}</option>`).join('')}</select></div></div>${pending ? employeeLoadState(directory,icon,esc) : employees.length ? desktop + phone : directory && !all.length ? '<div class="empty-state"><h3>No employees returned</h3><p>The employee API returned an empty list.</p></div>' : empty(icon)}${pending ? '' : pagination(total, page, 8, 'employees')}</section>`;
}

export function renderViolations(ctx) {
  const { store, esc, icon, person, badge, formatDate, violationBadge, violationStatusOptions, pagination } = ctx;
  const f = ctx.getFilters('violations');
  let records = ctx.visibleViolations().filter(record => {
    const employee = store.employees.find(employee => employee.id === record.employeeId);
    return (!f.query || `${employee?.name} ${record.id} ${record.employeeId}`.toLowerCase().includes(f.query.toLowerCase())) && (!f.department || employee?.department === f.department) &&
      (!f.type || record.typeId === f.type) && (!f.from || record.date >= f.from) && (!f.to || record.date <= f.to) && (!f.strike || record.strike);
  }).sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id));
  const total = records.length;
  const page = Math.min(ctx.page, Math.max(1, Math.ceil(total / 8)));
  ctx.setPage(page);
  records = records.slice((page - 1) * 8, page * 8);
  const desktop = `<div class="desktop-records table-wrap"><table><thead><tr><th>Employee</th><th>Violation / Case number</th><th>Demerit Points</th><th>Strike</th><th>Incident date</th><th>Recorded by</th><th>Action</th></tr></thead><tbody>${records.map(record => `<tr><td>${person(store.employees.find(employee => employee.id === record.employeeId))}</td><td>${esc(record.typeName)}<div class="person-id">${esc(record.id)}</div></td><td>${record.points}</td><td>${record.strike ? badge('Strike Violation') : 'No'}</td><td>${formatDate(record.date)}</td><td>${esc(record.recordedBy)}</td><td><button class="button ghost small" data-action="case-details" data-id="${esc(record.id)}">View Case ${icon('chevron-right', 14)}</button></td></tr>`).join('')}</tbody></table></div>`;
  const phone = `<div class="mobile-record-list" aria-label="Violation records">${records.map(record => {
    const employee = store.employees.find(employee => employee.id === record.employeeId);
    return `<details class="record-disclosure"><summary><span class="record-summary"><strong>${esc(employee.name)}</strong><span class="record-code">${esc(employee.id)}</span><span class="record-category">${esc(record.typeName)}</span></span><span class="record-chevron" aria-hidden="true">${icon('chevron-down', 21)}</span></summary><div class="record-expanded"><dl><div><dt>Case number</dt><dd>${esc(record.id)}</dd></div><div><dt>Demerit Points</dt><dd>${record.points}</dd></div><div><dt>Strike</dt><dd>${record.strike ? 'Yes' : 'No'}</dd></div><div><dt>Incident Date</dt><dd>${formatDate(record.date)}</dd></div><div><dt>Recorded by</dt><dd>${esc(record.recordedBy)}</dd></div></dl><button class="button secondary full" data-action="case-details" data-id="${esc(record.id)}">View Case ${icon('chevron-right', 17)}</button></div></details>`;
  }).join('')}</div>`;
  return `<form id="violation-filters" class="filters">
      <div class="field"><label for="violation-query">Employee or case number</label><input id="violation-query" name="query" value="${esc(f.query || '')}" placeholder="Search name or case number"></div>
      <div class="field"><label for="violation-department">Department</label><select id="violation-department" name="department">${options(unique(ctx.visibleEmployees().map(employee => employee.department)), f.department, 'All departments', esc)}</select></div>
      <div class="field"><label for="violation-type-filter">Violation type</label><select id="violation-type-filter" name="type"><option value="">All violation types</option>${store.types.map(type => `<option value="${esc(type.id)}" ${f.type === type.id ? 'selected' : ''}>${esc(type.name)}</option>`).join('')}</select></div>
      <div class="field"><label for="violation-from">From date</label><input id="violation-from" type="date" name="from" value="${esc(f.from || '')}"></div><div class="field"><label for="violation-to">To date</label><input id="violation-to" type="date" name="to" value="${esc(f.to || '')}"></div>
      <div class="check-field"><input id="strike-only" type="checkbox" name="strike" ${f.strike ? 'checked' : ''}><label for="strike-only">Strike violations only</label></div>
      <div class="filter-actions" style="grid-column:auto"><button class="button ghost" type="button" data-action="clear-filters" data-page="violations">Clear Filters</button><button class="button primary" type="submit">${icon('search', 17)} Search</button></div><p id="filter-error" class="form-error span-full" role="alert"></p>
    </form><section class="panel violation-directory"><div class="panel-header"><h2>Violation records <span class="count-label">${total} records</span></h2><span class="muted">Most recent first</span></div>${records.length ? desktop + phone : empty(icon)}${pagination(total, page, 8, 'violations')}</section>`;
}
