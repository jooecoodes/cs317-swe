const staff = ['dashboard', 'employees', 'violations', 'profile'];
const monitoring = ['history', 'reports'];
const pages = {
  hr: [...staff, ...monitoring, 'types', 'rulebook', 'ruleEditor', 'photos', 'tracking', 'settings', 'help'],
  supervisor: [...staff, 'photos'],
  c_manager: [...staff, ...monitoring],
  employee: ['mine']
};

export const roleLabels = Object.freeze({
  hr: 'HR', supervisor: 'Supervisor', c_manager: 'Chief Manager', employee: 'Concerned Employee'
});

export function normalizeRole(value) {
  const name = typeof value === 'string' ? value.trim().toLowerCase().replace(/[\s-]+/g, '_') : '';
  if (name === 'chief_manager') return 'c_manager';
  if (name === 'concerned_employee') return 'employee';
  return Object.hasOwn(roleLabels, name) ? name : '';
}

let identity = null;
export function setIdentity(verifiedSession) {
  identity = verifiedSession ? Object.freeze({...verifiedSession}) : null;
}
export function currentRole() { return identity?.role || ''; }
export function ownEmployeeId() { return identity?.employeeId || ''; }
export function canOpen(page, role = currentRole()) {
  return Object.hasOwn(pages, role) && pages[role].includes(page);
}
export function workspacePage(hash) {
  if (hash.startsWith('employee/')) return 'profile';
  if (hash === 'profile') return '';
  if (hash === 'camera') return 'photos';
  if (hash === 'removals') return 'history';
  if (hash === 'rulebook' || hash === 'ruleEditor') return 'types';
  if (/^category\/\d+(?:\/rule\/(?:\d+|new))?$/.test(hash)) return hash.includes('/rule/') ? 'ruleEditor' : 'rulebook';
  return hash;
}
export function landingPage(role = currentRole()) { return role === 'employee' ? 'mine' : 'dashboard'; }
export function mayRecord() { return ['hr', 'supervisor'].includes(currentRole()); }
export function mayManage() { return currentRole() === 'hr'; }

export function canUseMobileAccess() {
  return mayManage() || (Boolean(currentRole()) && globalThis.NORTHPOINT_CONFIG?.MOBILE_ACCESS_TESTING === true);
}

export function isMobileAccessRequest({service, method = 'GET', path}) {
  return service === 'session' && (
    (/^\/employees\/\d+\/mobile-access$/.test(path) && ['GET','POST','PATCH'].includes(method)) ||
    (/^\/employees\/\d+\/mobile-access\/link$/.test(path) && method === 'POST')
  );
}

// Companion to the existing method/path contract. The server must enforce its own policy.
export function allowsRequest({service = 'hr', method = 'GET', path}) {
  if (service === 'session') {
    if (path === '/me') return method === 'GET';
    return canUseMobileAccess() && isMobileAccessRequest({service, method, path});
  }
  if (!currentRole()) return false;
  if (service === 'tracking') return canOpen('tracking') && method === 'GET';
  if (service === 'photos') {
    if (!canOpen('photos')) return false;
    if (path.endsWith('/download')) return method === 'GET' && canOpen('tracking');
    if (method === 'GET' && (path.startsWith('/activity') || path.endsWith('/history'))) return canOpen('history');
    if (method === 'GET') return true;
    if (method === 'POST' && path === '/photos/batch') return canOpen('history');
    return mayManage() && (
      (['PATCH','DELETE'].includes(method) && /^\/photos\/\d+$/.test(path)) ||
      (method === 'POST' && (path === '/photos/bulk-delete' || /^\/photos\/\d+\/rename$/.test(path)))
    );
  }
  if (service !== 'hr') return false;
  if (currentRole() === 'employee') {
    return Boolean(ownEmployeeId()) && method === 'GET' && path === '/employees/' + ownEmployeeId() + '/violation-history';
  }
  if (method === 'GET') {
    if (path.startsWith('/activity/')) return canOpen('history');
    if (path.startsWith('/violation-removals')) return canOpen('history');
    if (path.startsWith('/analytics/')) return canOpen('reports');
    // Directory, profile and rule metadata are supporting reads for the staff views.
    return canOpen('violations') && /^\/(?:employees|violation-types|subsections|violations)(?:\/|$)/.test(path);
  }
  if (method === 'POST' && /^\/employees\/\d+\/violations$/.test(path)) return mayRecord();
  if (!mayManage()) return false;
  if (/^\/(?:violation-types|subsections)(?:\/|$)/.test(path)) return true;
  return (method === 'POST' && (path === '/employees' ||
    /^\/employees\/\d+\/(?:deactivate|reactivate)$/.test(path) ||
    /^\/violations\/\d+\/remove$/.test(path))) ||
    (method === 'PATCH' && /^\/(?:employees|violations)\/\d+$/.test(path)) ||
    (method === 'DELETE' && /^\/employees\/\d+$/.test(path));
}

const commonActions = new Set(['sign-out','toggle-nav','close-modal','dismiss-toast','close-record-filter']);
const staffActions = new Set(['profile','case-details','retry-profile','profile-record-tab','retry-profile-history','retry-employees','retry-employee-labels','refresh-data']);
const recordActions = new Set(['record','record-back','confirm-record','check-mutation']);
const managementActions = new Set(['add-employee','edit-employee','add-type','edit-type','toggle-type','delete-type','confirm-type','remove-violation','restore-company-rules']);
const photoActions = new Set(['photo-author','photo-clear','photo-details','photo-page','photo-refresh','photo-retry','photo-view']);

const photoManagementActions = new Set(['photo-edit','photo-rename','photo-delete-confirm','photo-bulk-delete','photo-selection-clear','photo-check-change','photo-review-change']);
const photoManagementForms = new Set(['photo-edit-form','photo-rename-form','photo-delete-form','photo-bulk-delete-form']);

export function allowsAction(action, data, page) {
  if (!canOpen(page)) return false;
  if (commonActions.has(action)) return true;
  if (action === 'navigate' || action === 'sec-help-nav') return canOpen(data.page);
  if (action === 'paginate') return page === data.page && ['employees','violations','profile','mine','history'].includes(page);
  if (action === 'clear-filters') return page === data.page && ['employees','violations','types'].includes(page);
  if (action === 'retry-own-history') return page === 'mine';
  if (staffActions.has(action)) return canOpen('profile');
  if (recordActions.has(action)) return mayRecord();
  if (managementActions.has(action)) return mayManage();
  if (action === 'employee-state') return mayManage() && ['deactivate','reactivate','delete'].includes(data.mode);
  if (action.startsWith('rulebook-')) return canOpen('types');
  if (action.startsWith('tracking-')) return page === 'tracking';
  if (photoManagementActions.has(action)) return page === 'photos' && mayManage();
  if (photoActions.has(action)) return page === 'photos';
  if (action === 'photo-tab') return page === 'photos' && (data.tab === 'photos' || data.tab === 'activity' && canOpen('history'));
  if (action === 'photo-history' || action.startsWith('photo-activity-')) return page === 'photos' && canOpen('history');
  if (action === 'watchlist') return canOpen('reports') && page === 'dashboard';
  if (action === 'dashboard-trend') return page === 'dashboard';
  if (action === 'dashboard-card') return page === 'dashboard' && (['employees','violations'].includes(data.target) || ['offenses','watchlist'].includes(data.target) && canOpen('reports'));
  if (action.startsWith('sec-calendar-') || action === 'sec-history-tab') return page === 'history';
  if (action === 'sec-report-tab' || action === 'sec-print') return page === 'reports';
  if (action === 'sec-filter-apply' || action === 'sec-filter-clear') return ['history','reports'].includes(page) && data.page === page;
  return false;
}

export function allowsForm(form, page) {
  if (!canOpen(page)) return false;
  if (form.id === 'global-search') return canOpen('employees');
  if (form.id === 'employee-filters') return page === 'employees';
  if (form.id === 'violation-filters') return page === 'violations';
  if (form.id === 'type-filters') return page === 'types';
  if (form.id === 'tracking-filters') return page === 'tracking';
  if (form.id === 'report-filters') return page === 'reports';
  if (form.id === 'secondary-filter') return ['history','reports'].includes(page) && form.dataset.filterPage === page;
  if (form.id === 'secondary-settings-form' || form.id === 'restore-company-rules-form') return page === 'settings';
  if (photoManagementForms.has(form.id)) return page === 'photos' && mayManage();
  if (form.id === 'photo-filters') return page === 'photos';
  if (form.id === 'photo-activity-filters') return page === 'photos' && canOpen('history');
  if (form.id === 'record-form') return mayRecord();
  if (form.id === 'employee-state-form') return mayManage() && ['deactivate','reactivate','delete'].includes(form.dataset.mode);
  return mayManage() && ['employee-form','type-form','rule-editor-form','remove-form','case-form'].includes(form.id);
}
