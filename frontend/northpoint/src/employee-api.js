import {apiRequest,paginatedApi} from './api-client.js';
// API-shaped view models. The configured data source currently supplies fiction.
export const employeeDirectory={status:'idle',items:[],total:0,error:''};
let requestSequence=0,currentController=null;
function nonnegative(value, field) {
  if ((typeof value !== 'number' && typeof value !== 'string') || value === '' || !Number.isFinite(Number(value)) || Number(value) < 0) throw new Error(`The employee API returned an invalid ${field}. Please retry.`);
  return Number(value);
}
function requiredText(value, field) {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`The employee API returned a missing ${field}. Please retry.`);
  return value.trim();
}
export function normalizeApiEmployee(item) {
  if (!item || typeof item !== 'object' || !['number', 'string'].includes(typeof item.id) || !String(item.id).trim()) throw new Error('The employee API returned an invalid employee ID. Please retry.');
  if (typeof item.id === 'number' && (!Number.isSafeInteger(item.id) || item.id < 0)) throw new Error('The employee API returned an invalid employee ID. Please retry.');
  const code = requiredText(item.employee_code, 'employee code');
  const status = String(item.status || '').trim().toLowerCase();
  if (!['active', 'inactive'].includes(status)) throw new Error('The employee API returned an unknown employee status. Please retry.');
  for (const key of ['department', 'position']) if (item[key] != null && typeof item[key] !== 'string') throw new Error(`The employee API returned an invalid ${key}. Please retry.`);
  for (const key of ['first_name','last_name']) if (item[key] != null && typeof item[key] !== 'string') throw new Error(`The employee API returned an invalid ${key}. Please retry.`);
  const totalStrikes = nonnegative(item.total_strikes, 'strike total');
  if (!Number.isInteger(totalStrikes)) throw new Error('The employee API returned an invalid strike total. Please retry.');
  return {
    id: code, apiId: String(item.id), profileId: `api/${encodeURIComponent(String(item.id))}`, source: 'api',
    name: requiredText(item.full_name, 'employee name'), department: item.department?.trim() || '', position: item.position?.trim() || '',
    status: status === 'active' ? 'Active' : 'Inactive', totalPoints: nonnegative(item.total_points, 'points total'), totalStrikes,
    ...(typeof item.first_name==='string'?{firstName:item.first_name.trim()}:{}), ...(typeof item.last_name==='string'?{lastName:item.last_name.trim()}:{}),
    ...(item.created_at ? { createdAt: item.created_at } : {})
  };
}


export async function fetchApiEmployees({signal}={}) {
  const raw=await paginatedApi('/employees',{query:{include_inactive:true},signal});
  return {items:raw.map(normalizeApiEmployee),total:raw.length};
}
export async function loadEmployeeDirectory(onChange = () => {}, { timeoutMs = 15000 } = {}) {
  const sequence = ++requestSequence;
  currentController?.abort();
  const controller = new AbortController();
  currentController = controller;
  Object.assign(employeeDirectory, { status: 'loading', items: [], total: 0, error: '' });
  onChange();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const result = await fetchApiEmployees({ signal: controller.signal });
    if (sequence !== requestSequence) return;
    Object.assign(employeeDirectory, { status: 'ready', ...result, error: '' });
  } catch (error) {
    if (sequence !== requestSequence) return;
    Object.assign(employeeDirectory, { status: 'error', items: [], total: 0, error: timedOut ? 'The employee API took too long to respond. Please try again.' : error.message || 'Employees could not be loaded. Please try again.' });
  } finally {
    clearTimeout(timer);
    if (sequence === requestSequence) { currentController = null; onChange(); }
  }
}


export function suspendEmployeeDirectory(){requestSequence++;currentController?.abort();currentController=null;Object.assign(employeeDirectory,{status:'idle',items:[],total:0,error:''});}
export function apiEmployeeSummary(employee) {
  const points = employee?.totalPoints ?? 0;
  const strikes = employee?.totalStrikes ?? 0;
  return { points, strikes, total: null, violations: [], status: strikes >= 2 ? 'Needs attention' : points > 0 || strikes > 0 ? 'For monitoring' : 'Not available' };
}

function createError(message, code = 'validation', extra = {}) {
  return Object.assign(new Error(message), { code, uncertain: false, ...extra });
}

export function employeeCodeKey(code) { return String(code || '').trim().toLowerCase(); }
const generatedCodes = new Set();
export function nextApiEmployeeCode(employees = employeeDirectory.items, random = Math.random) {
  const used = new Set(employees.map(employee => employeeCodeKey(employee.id)));
  const start = Math.floor(Math.max(0, Math.min(.999999999, random())) * 900000);
  for (let attempt = 0; attempt < 900000; attempt++) {
    const code = `EMP-${100000 + (start + attempt) % 900000}`;
    const key = employeeCodeKey(code);
    if (!used.has(key) && !generatedCodes.has(key)) { generatedCodes.add(key); return code; }
  }
  throw createError('An unused employee code could not be assigned. Please enter a different code.');
}

export async function fetchEmployeeDirectorySnapshot({ timeoutMs = 15000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try { return await fetchApiEmployees({ signal: controller.signal }); }
  catch (error) {
    if (controller.signal.aborted) throw createError('The employee code check timed out. Please try again.', 'lookup');
    throw error;
  } finally { clearTimeout(timer); }
}

export function employeeCreatePayload(values) {
  const fields = {};
  for (const [key, label, max] of [['employee_code','Employee code',50],['first_name','First name',100],['last_name','Last name',100]]) {
    const value = typeof values[key] === 'string' ? values[key].trim() : '';
    if (!value) throw createError(`${label} is required.`, 'validation', { field: key });
    if (value.length > max) throw createError(`${label} must be ${max} characters or fewer.`, 'validation', { field: key });
    fields[key] = value;
  }
  for (const key of ['department','position']) {
    const value = values[key] == null ? '' : String(values[key]).trim();
    if (value.length > 100) throw createError(`${key === 'department' ? 'Department' : 'Position'} must be 100 characters or fewer.`, 'validation', { field: key });
    fields[key] = value || null;
  }
  return fields;
}

export function employeeMatchesCreation(employee, payload) {
  return employeeCodeKey(employee.id) === employeeCodeKey(payload.employee_code) && employee.name === `${payload.first_name} ${payload.last_name}` && (employee.department || '') === (payload.department || '') && (employee.position || '') === (payload.position || '');
}


export async function createApiEmployee(values,actor) {
  const payload=employeeCreatePayload(values);
  return normalizeApiEmployee(await apiRequest('/employees',{method:'POST',body:payload,actor}));
}
