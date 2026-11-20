import {roleLabels} from '../../scripts/shared/permissions.js';
import {previewCalendarRows, previewCalendarSummary} from '../../scripts/northpoint/features/history/calendar-contract.js';

const mobileAccessTesting = process.argv.includes('--mobile-access-testing');
const mobileAccounts = new Map();
const cookie = 'northpoint_rbac_preview';
const roles = Object.keys(roleLabels);
const now = new Date();
const issuedAt = now.toISOString();
const businessDate = new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Manila'}).format(now);
const category = {id:1, name:'Workplace Conduct', description:'', is_active:true};
const rule = {id:1, violation_type_id:1, name:'Missed safety briefing', description:'', is_active:true,
  penalties:[{offense_number:1,description:'Written warning'},{offense_number:2,description:'One-day suspension'}]};
const employee = {id:101, employee_code:'DEMO-101', first_name:'Alex', last_name:'Sample', full_name:'Alex Sample',
  department:'Operations', position:'Team member', status:'active', active_violation_count:1, total_offenses:2, created_at:issuedAt};
const other = {...employee,id:102,employee_code:'DEMO-102',first_name:'Morgan',full_name:'Morgan Sample',
  department:'Administration',status:'inactive',active_violation_count:0,total_offenses:0};
const employees = [employee, other];
const issuer = 'Preview Supervisor';
const record = {id:201, employee_id:employee.id, subsection_id:rule.id, subsection:rule, offense_number:2,
  penalty_description:rule.penalties[1].description, issued_at:issuedAt, created_at:issuedAt, issued_by:issuer, notes:'Fictional incident for development preview.'};
const removedIssue = new Date(now.getTime() - 86400000).toISOString();
const removal = {id:301, violation_record_id:200, employee_id:employee.id, employee_code:employee.employee_code,
  employee_full_name:employee.full_name, subsection_id:rule.id, subsection_name:rule.name, violation_type_name:category.name,
  offense_number:1, penalty_description:rule.penalties[0].description, reason:'Sample correction', removed_by:'Preview HR',
  removed_at:issuedAt, original_issued_at:removedIssue, original_issued_by:issuer, original_notes:''};
const history = [{violation_record_id:record.id,subsection_id:rule.id,subsection_name:rule.name,violation_type_name:category.name,
  offense_number:record.offense_number,penalty_description:record.penalty_description,issued_at:issuedAt,issued_by:issuer,
  notes:record.notes,status:'active'},{...removal,status:'removed',issued_at:removedIssue,issued_by:issuer,removal_reason:removal.reason}];
const event = {id:401, occurred_at:issuedAt, event_date:businessDate, actor:issuer, action:'violation.assigned',
  target_type:'violation', target_id:record.id, employee_id:employee.id, summary:'Recorded a sample safety briefing violation.'};
const point = [8.4803,124.6498];
const device = {device_id:'demo-device', tracker:'Sample device', status:'online', lat:point[0], lon:point[1], accuracy_m:15, last_seen_seconds_ago:4};
const photo = {id:501, title:'Sample proof photo', owner:issuer, timestamp:issuedAt, tags:['Safety'], size_bytes:324,
  location_name:'Sample location', mobile_metadata:{source:'camera',selected_at:issuedAt,latitude:point[0],longitude:point[1]}};
const photoImage = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400" role="img" aria-label="Fictional preview photo"><rect width="640" height="400" fill="#e5edf7"/><path fill="#90aac4" d="M0 350 180 170 285 270 435 90 640 350Z"/><text x="320" y="380" text-anchor="middle" font-family="sans-serif" font-size="24" fill="#26445f">Sample proof photo</text></svg>';

const settings = `globalThis.NORTHPOINT_CONFIG = Object.freeze({BASE_URL:new URL('/app1/', location.origin).href, READ_ONLY_PREVIEW:true, MOBILE_ACCESS_TESTING:${mobileAccessTesting}});`;
const previewHeaders = {
  'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'",
  'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'
};
const previewMessage = 'Development preview is read-only. No changes were saved.';

function page() {
  const links = roles.map(role => `<a class="button secondary" href="/_preview/role/${role}">${roleLabels[role]}</a>`).join('');
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Northpoint role preview</title><link rel="stylesheet" href="/css/northpoint.css"><link rel="stylesheet" href="/_preview/style.css">
    <main class="session-gate"><section class="panel panel-body"><h1>Northpoint role preview</h1>
    <p>Development only. Choose a role to explore with fictional records. ${mobileAccessTesting?'Only sample mobile account changes are enabled.':'Changes are disabled.'}</p>
    <nav class="preview-roles" aria-label="Preview roles">${links}</nav></section></main></html>`;
}

export function previewPage(path, html, role) {
  if (!/^(?:hr|supervisor|c_manager|employee)\/index\.html$/.test(path)) return html;
  const label = role ? ' · ' + roleLabels[role] : '';
  return html.replace('</head>', '<link rel="stylesheet" href="/_preview/style.css"></head>')
    .replace('<body>', `<body><aside class="preview-banner" aria-label="Development preview">
      <p><strong>Development preview${label}</strong><span> · Sample data · ${mobileAccessTesting?'Mobile access testing':'Read-only'}</span></p>
      <a href="/_preview/">Switch role</a></aside>`);
}

export function previewRole(request) {
  const role = request.headers.cookie?.split(';').find(part => part.trim().startsWith(cookie + '='))?.split('=')[1];
  return roles.includes(role) ? role : '';
}

export async function handlePreviewRequest(request, response, url, role) {
  const path = url.pathname;
  const send = (status, type, content, extra = {}) => {
    response.writeHead(status, {...previewHeaders,'Content-Type':type,...extra})
      .end(request.method === 'HEAD' ? undefined : content);
    return true;
  };
  const json = (data, status = 200) => send(status, 'application/json', JSON.stringify(data));
  const text = (data, type) => send(200, type + '; charset=utf-8', data);
  const redirect = (location, session = '') => send(303, 'text/plain', '', {Location:location,...(session ? {'Set-Cookie':session} : {})});
  const mobile = path.match(/^\/auth\/employees\/(\d+)\/mobile-access(\/link)?$/);
  if (mobile && (mobileAccessTesting || request.method === 'GET')) {
    if (!role) return json({detail:'Choose a preview role.'},401);
    if (!mobileAccessTesting && role !== 'hr') return json({detail:'HR access required.'},403);
    const person = employees.find(item => String(item.id) === mobile[1]);
    if (!person) return json({detail:'Unknown sample employee.'},404);
    const result = await sampleMobileAccess(request, person, Boolean(mobile[2]));
    return json(result.body,result.status);
  }
  if (!['GET','HEAD'].includes(request.method)) return json({detail:previewMessage}, 403);
  for (const [name,value] of Object.entries(previewHeaders)) response.setHeader(name, value);

  if (['/','/_preview','/_preview/','/auth/login'].includes(path)) return text(page(), 'text/html');
  if (path === '/auth/logout') return redirect('/_preview/', `${cookie}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0`);
  const selection = path.match(/^\/_preview\/role\/(\w+)$/)?.[1];
  if (roles.includes(selection) && request.method === 'GET') {
    return redirect('/northpoint/', `${cookie}=${selection}; Path=/; HttpOnly; SameSite=Strict`);
  }
  if (path === '/_preview/style.css') return text(previewStyles,'text/css');
  if (['/scripts/config.js'].includes(path)) return text(settings,'text/javascript');
  if (path === '/auth/me') {
    return role ? json({username:'preview_'+role, full_name:'Preview '+roleLabels[role], role,
      ...(role === 'employee' ? {employee_id:employee.id} : {})}) : json({detail:'Choose a preview role.'},401);
  }
  if (!/^\/app[123]\//.test(path)) return false;
  if (!role) return json({detail:'Choose a preview role.'},401);

  const {searchParams:query} = url;
  const list = (items, array = false) => {
    const limit = Number(query.get('limit')) || 50, offset = Number(query.get('offset')) || 0;
    const shown = items.slice(offset, offset+limit);
    return array ? shown : {items:shown,total:items.length,limit,offset};
  };
  let data;
  try {
    data = readSample(path, role, query, list);
  } catch {
    return json({detail:'Invalid preview request.'},400);
  }
  if (data === photoImage) return text(data, 'image/svg+xml');
  return data === undefined ? json({detail:'This record is unavailable in the preview.'},404) : json(data);
}

async function sampleMobileAccess(request, person, linking) {
  const result = (status, detail) => ({status,body:{detail}});
  if (request.method === 'GET' && !linking) {
    return {status:200,body:{full_name:person.full_name,account:mobileAccounts.get(person.id) ?? null}};
  }
  if (request.headers['x-requested-with'] !== 'Northpoint') return result(403,'Open the test panel to make changes.');
  if (!(request.method === 'POST' || (request.method === 'PATCH' && !linking))) return result(405,'Method unavailable.');
  let body;
  try {
    const chunks = [];
    let size = 0;
    for await (const chunk of request.iterator({destroyOnReturn:false})) {
      size += chunk.length;
      if (size > 2048) {
        request.resume();
        return result(413,'Test request is too large.');
      }
      chunks.push(chunk);
    }
    body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (!body || typeof body !== 'object' || Array.isArray(body)) throw Error();
  } catch {
    return result(422,'Enter valid test account details.');
  }
  const account = mobileAccounts.get(person.id);
  const validPassword = typeof body.password === 'string' && body.password.length >= 10 && body.password.length <= 128;
  if (request.method === 'POST') {
    if (person.status !== 'active') return result(403,'This sample employee is inactive.');
    if (account || [...mobileAccounts.values()].some(item => item.username === body.username)) return result(409,'Sample account already exists.');
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{2,49}$/.test(body.username ?? '') || !validPassword) return result(422,'Enter a test username and password.');
    if (linking && body.username !== 'legacy-tracker') return result(404,'Use legacy-tracker to test account linking.');
    mobileAccounts.set(person.id,{username:body.username,disabled:false});
    return {status:linking ? 200 : 201,body:{message:linking?'Sample account linked.':'Sample account created.'}};
  }
  if (!account) return result(404,'Create a sample account first.');
  if (body.disabled === false && person.status !== 'active') return result(403,'This sample employee is inactive.');
  if (typeof body.disabled === 'boolean') account.disabled = body.disabled;
  else if (!validPassword) return result(422,'Enter a valid test password.');
  return {status:200,body:{message:'Sample mobile access updated.'}};
}

function readSample(path, role, query, list) {
  const mine = `/app1/employees/${employee.id}/violation-history`;
  if (role === 'employee') return path === mine ? list(history) : undefined;
  const monitoring = role === 'hr' || role === 'c_manager';
  if (path === '/app1/employees') return list(employees);
  if (path === '/app1/violations/recent') return [record];
  if (path === `/app1/violations/${record.id}`) return record;
  if (path === '/app1/violation-types' || path === '/app1/violation-types/all') return [category];
  if (path === '/app1/violation-types/1') return category;
  if (path === '/app1/violation-types/1/subsections') return [rule];
  if (path === '/app1/subsections/1') return rule;
  const profile = path.match(/^\/app1\/employees\/(\d+)(?:\/(.*))?$/);
  if (profile) {
    const row = employees.find(person => person.id === Number(profile[1]));
    if (!row) return;
    const active = row === employee ? [record] : [];
    switch (profile[2]) {
      case undefined: return {...row, violation_records:active};
      case 'totals': return row;
      case 'violations': return list(active,true);
      case 'violation-history': return list(row === employee ? history : []);
      case 'offense-summary': return row === employee ? [{subsection_id:rule.id,active_offenses:1,removed_offenses:1}] : [];
    }
  }
  if (monitoring) {
    if (path === '/app1/violation-removals') return list([removal]);
    if (path === '/app1/activity/timeline') return list([event]);
    if (path === '/app1/activity/calendar') return previewCalendarRows([event],{start:query.get('start'),end:query.get('end')});
    const day = path.match(/^\/app1\/activity\/digest\/(\d{4}-\d{2}-\d{2})$/)?.[1];
    if (day && !Number.isNaN(Date.parse(day))) return previewCalendarSummary([event],day);
  }
  if (role === 'hr' || role === 'supervisor') {
    const proof = role === 'hr' ? photo : {...photo, location_name:null, mobile_metadata:{source:'camera',selected_at:issuedAt}};
    if (path === '/app2/photos') return list([proof]);
    if (path === '/app2/photos/501') return proof;
    if (path === '/app2/photos/501/file' || role === 'hr' && path === '/app2/photos/501/download') return photoImage;
    if (path === '/app2/stats') return {business_date:businessDate,total_photos:1,total_bytes:photo.size_bytes,uploads_today:1,
      employee_counts:[{owner:issuer,total_uploads:1,uploads_today:1}]};
  }
  if (role === 'hr') {
    if (path === '/app2/activity') return list([]);
    if (path === '/app2/activity/authors') return {actors:[]};
    if (path === '/app2/activity/digest') return {summary:'No sample photo activity.',total:0,days:[],
      from_date:query.get('from_date'),to_date:query.get('to_date')};
    if (path === '/app2/photos/501/history') return {...list([]), photo_id:photo.id, photo_exists:true};
    if (path === '/app3/devices') return {count:1,devices:[device]};
    if (path === '/app3/live/demo-device') return device;
    if (path === '/app3/route/demo-device') return {segments:[[point,[8.4825,124.6519]]]};
  }
}

const previewStyles = `
  .preview-roles { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 185px), 1fr)); gap: 12px; margin-top: 22px; }
  .preview-banner { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 4px 14px;
    padding: 8px 18px; margin-left: var(--sidebar); background: #fff6dd; color: #653c00; border-bottom: 1px solid #ead5a0; }
  .preview-banner a { display: inline-flex; align-items: center; min-height: 44px; text-decoration: underline; font-weight: 650; }
  @media (max-width: 900px) { .preview-banner { margin-left: 0; } }
`;
