import {businessDate} from './yesterday.js';
import { dashboardSummary, localDate } from './domain.js';

export function sortEmployeeRecords(employees, summary, order = 'newest') {
  const created = employee => Date.parse(employee.createdAt || '') || Number(employee.apiId ?? String(employee.id).match(/(\d+)$/)?.[1] ?? 0);
  const name = (a, b) => a.name.localeCompare(b.name);
  const compare = {
    newest: (a, b) => created(b) - created(a) || name(a, b),
    oldest: (a, b) => created(a) - created(b) || name(a, b),
    points: (a, b) => summary(b.id).points - summary(a.id).points || name(a, b),
    'points-low': (a, b) => summary(a.id).points - summary(b.id).points || name(a, b),
    strikes: (a, b) => summary(b.id).strikes - summary(a.id).strikes || name(a, b),
    name,
    'name-desc': (a, b) => name(b, a)
  };
  return employees.slice().sort(compare[order] || compare.newest);
}

export function analyticsData(employees, violations, types, days = 30, today = businessDate()) {
  days = [7, 30, 90].includes(Number(days)) ? Number(days) : 30;
  const summary = dashboardSummary(employees, violations, []);
  const ids = new Set(employees.map(employee => employee.id));
  const records = violations.filter(record => ids.has(record.employeeId) && record.status !== 'Removed' && !record.removed && !record.removedAt);
  const ranked = employees.map(employee => {
    const own = records.filter(record => record.employeeId === employee.id);
    return { ...employee, total: own.length, points: employee.totalPoints ?? own.reduce((sum, record) => sum + Number(record.points || 0), 0), strikes: employee.totalStrikes ?? own.filter(record => record.strike).length };
  });
  const start = new Date(`${today}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - days + 1);
  const from = start.toISOString().slice(0, 10);
  const period = records.filter(record => String(record.date).slice(0, 10) >= from && String(record.date).slice(0, 10) <= today);
  const daily = Array.from({ length: days }, (_, index) => {
    const date = new Date(start); date.setUTCDate(date.getUTCDate() + index);
    const value = date.toISOString().slice(0, 10);
    return { date: value, count: period.filter(record => String(record.date).slice(0, 10) === value).length };
  });
  const byDepartment = [...new Set(employees.map(employee => employee.department || 'Unassigned'))].map(department => ({
    label: department,
    value: period.filter(record => (employees.find(employee => employee.id === record.employeeId)?.department || 'Unassigned') === department).length
  })).filter(item => item.value).sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
  const typeNames = [...new Set(period.map(record => record.typeName))];
  const byType = typeNames.map(label => ({ label, value: period.filter(record => record.typeName === label).length })).sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
  const employeeStatus = ['Active', 'Inactive'].map(label => ({ label, value: employees.filter(employee => employee.status === label).length }));
  const ruleTypes = [...types];
  for (const record of records) if (!ruleTypes.some(type => type.id === record.typeId)) ruleTypes.push({ id: record.typeId, name: record.typeName, points: null, strike: record.strike });
  const usage = ruleTypes.map(type => {
    const issued = records.filter(record => record.typeId === type.id);
    return { ...type, issued: issued.length, totalPoints: issued.reduce((sum, record) => sum + Number(record.points || 0), 0) };
  }).sort((a, b) => b.issued - a.issued || a.name.localeCompare(b.name));
  return {
    days, from, today, events: period.length, points: period.reduce((sum, record) => sum + Number(record.points || 0), 0),
    dailyAverage: period.length / days, daily, byDepartment, byType, employeeStatus,
    topOffenders: ranked.filter(employee => employee.total).sort((a, b) => b.points - a.points || a.name.localeCompare(b.name)),
    watchlist: ranked.filter(employee => employee.strikes >= 2).sort((a, b) => a.name.localeCompare(b.name)),
    cleanEmployees: ranked.filter(employee => employee.total === 0).sort((a, b) => a.name.localeCompare(b.name)),
    departments: summary.departments, usage
  };
}

export function historyEvents(store, employees, violations, filters = {}) {
  const removals = filters.tab === 'removals';
  const friendly = value => String(value || '').replaceAll('_',' ').replaceAll('.',' ').replace(/\b\w/g,letter=>letter.toUpperCase());
  const names = { 'employee.created':'Employee added', 'employee.updated':'Employee updated', 'employee.deleted':'Employee deleted', 'employee.removed':'Employee removed', 'employee.deactivated':'Employee deactivated', 'employee.activated':'Employee activated', 'violation.assigned':'Violation issued', 'violation.created':'Violation added', 'violation.updated':'Violation updated', 'violation.removed':'Violation removed', 'violations.cleared':'Violations cleared', 'violation_type.created':'Violation type added', 'violation_type.updated':'Violation type updated', 'violation_type.activated':'Violation type activated', 'violation_type.deactivated':'Violation type deactivated', 'violation_type.deleted':'Violation type deleted' };
  const targetNames = { employee:'Employee', violation:'Violation', violation_type:'Violation type' };
  const string = value => typeof value === 'string' ? value : '';
  const events = removals ? store.removals.map(removal=>{
    const employee=employees.find(item=>item.apiId===removal.employeeApiId);
    return {...removal,id:'removal-'+removal.id,sortId:Number(removal.id),category:removal.typeId,title:'Violation removed',actor:removal.removedBy,profileId:employee?.profileId||'',detail:removal.typeName,notes:removal.reason};
  }) : store.activities.map(activity=>{
    const metadata=activity.metadata||{};
    const type=activity.targetType||activity.action.split('.')[0]||'other';
    const employeeApiId=activity.employeeApiId||(type==='employee'?activity.targetId:null);
    const snapshotCode=string(metadata.employee_code);
    const candidate=employees.find(item=>item.apiId===employeeApiId);
    const relatedEmployee=candidate&&(!snapshotCode||snapshotCode===candidate.id)?candidate:null;
    const targetLabel=(targetNames[type]||friendly(type))+(activity.targetId!=null?' #'+activity.targetId:'');
    // Every timeline action survives, even unknown future actions or deleted employees.
    return {...activity,id:'activity-'+activity.id,sortId:Number(activity.id),category:type,title:names[activity.action]||friendly(activity.action),targetLabel,
      employeeName:string(metadata.employee_full_name)||string(metadata.full_name)||relatedEmployee?.name||'',
      employeeId:snapshotCode||relatedEmployee?.id||'',profileId:relatedEmployee?.profileId||(activity.action==='employee.deactivated'&&employeeApiId&&!candidate?'api/'+employeeApiId:''),
      notes:string(metadata.reason),metadata};
  });
  return events.filter(event=>(!filters.category||event.category===filters.category)&&(!filters.from||event.date.slice(0,10)>=filters.from)&&(!filters.to||event.date.slice(0,10)<=filters.to)&&
    (!filters.query||[event.employeeName,event.employeeId,event.title,event.detail,event.notes,event.actor,event.targetLabel,event.violationId,JSON.stringify(event.metadata||{})].join(' ').toLowerCase().includes(filters.query.toLowerCase())))
    .sort((a,b)=>(Date.parse(b.date)-Date.parse(a.date))||(b.sortId-a.sortId));
}
