// View state only. Nothing is saved to browser storage or a database.
const defaults={organization:'Northpoint',textSize:'standard',name:''};
export const store={employees:[],violations:[],types:[],removals:[],activities:[],settings:{...defaults}};
export function saveStore() { /* Preferences apply to this open tab only. */ }
export function visibleEmployees() {
  return store.employees.slice();
}
export function visibleViolations() {
  const ids = new Set(visibleEmployees().map(employee => employee.id));
  return store.violations.filter(record => ids.has(record.employeeId));
}
export function employeeSummary(id) {
  const employee = store.employees.find(employee => employee.id === id);
  const violations = store.violations.filter(record => record.employeeId === id);
  const points = employee?.totalPoints ?? null, strikes = employee?.totalStrikes ?? null;
  return { violations, total: store.recordsReady ? violations.length : null, points, strikes, status: strikes >= 2 ? 'Needs attention' : points > 0 || strikes > 0 ? 'For monitoring' : store.recordsReady && !violations.length ? 'Good standing' : 'Not provided' };
}
