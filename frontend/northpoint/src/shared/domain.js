// Shared rules for violation status and the weekly dashboard. No network calls.
export const VIOLATION_STATUSES = ['Active', 'Inactive'];

function retained(violation) {
  return violation.status !== 'Removed' && !violation.removed && !violation.removedAt;
}

export function normalizeViolationStatus(value) {
  return /^(inactive|resolved)$/i.test(String(value).trim()) ? 'Inactive' : 'Active';
}

export function violationStatusLabel(value) {
  return normalizeViolationStatus(value) === 'Active' ? 'Active — not yet resolved' : 'Inactive — resolved';
}

export function localDate(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function dateAtUTC(value) {
  return new Date(`${String(value).slice(0, 10)}T00:00:00Z`);
}

function shiftDate(value, days) {
  const date = dateAtUTC(value);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function startOfWeek(value = localDate()) {
  const day = dateAtUTC(value).getUTCDay();
  return shiftDate(value, -((day + 6) % 7));
}

export function weeklyTotals(violations, today = localDate(), weeks = 6) {
  const current = startOfWeek(today);
  return Array.from({ length: weeks }, (_, index) => {
    const start = shiftDate(current, (index - weeks + 1) * 7);
    const end = shiftDate(start, 6);
    const count = violations.filter(violation => {
      const date = String(violation.date).slice(0, 10);
      return retained(violation) && date >= start && date <= end && date <= today;
    }).length;
    return { start, end, count, current: start === current };
  });
}

export function recentViolationActivity(violations, today = localDate()) {
  const from = shiftDate(today, -13);
  return violations.filter(violation => {
    const date = String(violation.date).slice(0, 10);
    return retained(violation) && date >= from && date <= today;
  }).slice().sort((a, b) => b.date.localeCompare(a.date) || String(b.id).localeCompare(String(a.id))).slice(0, 5);
}

export function dashboardSummary(employees, violations, removals) {
  const numeric = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const employeeIds = new Set(employees.map(employee => employee.id));
  const records = violations.filter(violation => employeeIds.has(violation.employeeId) && retained(violation));
  const ranked = employees.map(employee => {
    const own = records.filter(violation => violation.employeeId === employee.id);
    return { ...employee, violations: own.length, points: employee.totalPoints ?? own.reduce((sum, v) => sum + numeric(v.points), 0), strikes: employee.totalStrikes ?? own.filter(v => v.strike).length };
  });
  const departments = [...new Set(employees.map(employee => employee.department || 'Unassigned'))].sort().map(department => {
    const members = ranked.filter(employee => (employee.department || 'Unassigned') === department);
    return {
      name: department,
      employees: members.length,
      violations: members.reduce((sum, employee) => sum + employee.violations, 0),
      points: members.reduce((sum, employee) => sum + employee.points, 0),
      strikes: members.reduce((sum, employee) => sum + employee.strikes, 0)
    };
  });
  return {
    employees: employees.length,
    violations: records.length,
    points: ranked.reduce((sum, employee) => sum + employee.points, 0),
    watchlist: ranked.filter(employee => employee.strikes >= 2),
    topOffenders: ranked.filter(employee => employee.violations > 0).sort((a, b) => b.points - a.points || b.strikes - a.strikes || a.name.localeCompare(b.name)).slice(0, 5),
    departments,
    recentRemovals: removals.filter(removal => employeeIds.has(removal.employeeId)).slice().sort((a, b) => b.date.localeCompare(a.date)).slice(0, 3)
  };
}
