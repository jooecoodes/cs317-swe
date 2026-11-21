import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { dataSource } from '../scripts/shared/api.js';
import { setIdentity } from '../scripts/shared/permissions.js';
import { apiRoute } from '../scripts/northpoint/api/api-routes.js';
import { mobileAccessPanel } from '../scripts/northpoint/features/employees/mobile-access.js';
import { mobileAccessError, requestMobileAccess } from '../scripts/northpoint/features/employees/mobile-access-api.js';

const supervisor = { apiId: '42', employeeType: 'supervisor', status: 'Active', name: 'Test Supervisor' };
const path = '/employees/42/mobile-access';
const password = 'track-test-1234';
const fields = { username: 'test.tracker', password };
const backendStatus = {
  employee_id: 42, employee_code: 'EMP-42', employee_type: 'supervisor',
  full_name: 'Test Supervisor', status: 'active', eligible: true, account: null,
};
const originalFetch = globalThis.fetch;
const originalLocation = Object.getOwnPropertyDescriptor(globalThis, 'location');

afterEach(() => {
  setIdentity(null);
  globalThis.fetch = originalFetch;
  if (originalLocation) Object.defineProperty(globalThis, 'location', originalLocation);
  else delete globalThis.location;
});

function intercept(handler) {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    const call = { url: new URL(url), ...options };
    calls.push(call);
    return handler(call);
  };
  return calls;
}

test('only HR sees the panel and only on Supervisor profiles', () => {
  for (const role of ['', 'hr', 'supervisor', 'c_manager', 'employee']) {
    setIdentity(role && { role });
    for (const employeeType of ['hr', 'supervisor', 'c_manager', 'employee', undefined]) {
      const panel = mobileAccessPanel({ ...supervisor, employeeType }, String);
      assert.equal(panel.includes('Mobile App Access'), role === 'hr' && employeeType === 'supervisor');
    }
  }
});

test('non-HR calls are denied by both the feature and the shared API client before fetching', async () => {
  const calls = intercept(() => { throw Error('Fetch was not expected'); });
  for (const role of ['', 'supervisor', 'c_manager', 'employee']) {
    setIdentity(role && { role });
    for (const action of ['load', 'create', 'link', 'reset', 'enable', 'disable']) {
      await assert.rejects(requestMobileAccess(supervisor, action, fields), { status: 403 });
    }
    for (const [method, route] of [['GET', path], ['POST', path], ['POST', path + '/link'], ['PATCH', path]]) {
      await assert.rejects(dataSource.request({ service: 'session', method, path: route }), { status: 403 });
    }
  }
  assert.equal(calls.length, 0);
});

test('HR cannot use the feature for ineligible employees or issue or enable access for inactive Supervisors', async () => {
  setIdentity({ role: 'hr' });
  const calls = intercept(() => { throw Error('Fetch was not expected'); });
  for (const employeeType of ['hr', 'c_manager', 'employee', undefined]) {
    for (const action of ['load', 'create', 'link', 'reset', 'enable', 'disable']) {
      await assert.rejects(requestMobileAccess({ ...supervisor, employeeType }, action, fields), { status: 403 });
    }
  }
  for (const action of ['create', 'link', 'enable']) {
    await assert.rejects(requestMobileAccess({ ...supervisor, status: 'Inactive' }, action, fields), { status: 403 });
  }
  for (const invalid of [{ username: 'bad name', password }, { ...fields, password: 'too short' }]) {
    await assert.rejects(requestMobileAccess(supervisor, 'create', invalid), { status: 422 });
  }
  assert.equal(calls.length, 0);
});

test('account operations use the authenticated session client and exact backend contract', async () => {
  setIdentity({ role: 'hr' });
  const calls = intercept(({ method }) => {
    if (method === 'GET') {
      return Response.json({ ...backendStatus, account: { username: fields.username, disabled: 0 } });
    }
    return Response.json({ message: 'Saved' }, { status: calls.length === 2 ? 201 : 200 });
  });
  assert.deepEqual(await requestMobileAccess(supervisor, 'load'), {
    eligible: true, active: true, account: { username: fields.username, disabled: false },
  });
  await requestMobileAccess(supervisor, 'create', fields);
  await requestMobileAccess(supervisor, 'link', fields);
  await requestMobileAccess({ ...supervisor, status: 'Inactive' }, 'reset', fields);
  await requestMobileAccess({ ...supervisor, status: 'Inactive' }, 'disable');
  await requestMobileAccess(supervisor, 'enable');
  const expected = [
    ['GET', path, undefined], ['POST', path, fields], ['POST', path + '/link', fields],
    ['PATCH', path, { password }], ['PATCH', path, { disabled: true }], ['PATCH', path, { disabled: false }],
  ];
  assert.equal(calls.length, expected.length);
  for (const [i, [method, route, body]] of expected.entries()) {
    const call = calls[i];
    assert.equal(call.url.pathname, '/auth' + route);
    assert.equal(call.method, method);
    assert.equal(call.credentials, 'same-origin');
    assert.equal(call.redirect, 'error');
    assert.equal(call.headers['X-Actor'], undefined);
    assert.equal(call.headers['X-Requested-With'], method === 'GET' ? undefined : 'Northpoint');
    assert.equal(call.headers['Content-Type'], method === 'GET' ? undefined : 'application/json');
    assert.deepEqual(call.body === undefined ? undefined : JSON.parse(call.body), body);
  }
});

test('session route contract keeps /me and rejects unsupported mobile paths and methods', async () => {
  const calls = intercept(() => Response.json({ username: 'test' }));
  assert.equal((await dataSource.request({ service: 'session', path: '/me' })).username, 'test');
  setIdentity({ role: 'hr' });
  for (const [method, route] of [
    ['GET', path + '/link'], ['PATCH', path + '/link'], ['DELETE', path], ['POST', '/me'],
    ['GET', '/employees/0/mobile-access'], ['GET', path + '/other'],
  ]) {
    assert.throws(() => apiRoute(route, method, 'session'));
    await assert.rejects(dataSource.request({ service: 'session', method, path: route }), { status: 403 });
  }
  assert.equal(calls.length, 1);
});

test('server eligibility and identity are checked before displaying management controls', async () => {
  setIdentity({ role: 'hr' });
  intercept(() => Response.json({ ...backendStatus, eligible: false, employee_type: 'employee' }));
  assert.equal((await requestMobileAccess(supervisor, 'load')).eligible, false);
  intercept(() => Response.json({ ...backendStatus, employee_id: 43 }));
  await assert.rejects(requestMobileAccess(supervisor, 'load'), /unexpected mobile access information/);
});

test('account-management errors preserve backend detail and do not retry a write', async () => {
  setIdentity({ role: 'hr' });
  const cases = [
    [400, 'Bad request', /Bad request/],
    [401, 'Sign-in required', /Sign in again/],
    [403, 'HR only', /HR only/],
    [404, 'Tracker username does not exist', /Tracker username does not exist/],
    [409, 'Tracker already linked', /Tracker already linked/],
    [422, [{ loc: ['body', 'password'], msg: 'Invalid length' }], /password.*Invalid length/],
    [500, 'Internal Server Error', /could not confirm.*Refresh access/],
    [503, 'Employee database unavailable', /could not confirm.*Refresh access/],
  ];
  for (const [status, detail, message] of cases) {
    const calls = intercept(() => Response.json({ detail }, { status }));
    await assert.rejects(requestMobileAccess(supervisor, 'link', fields), error => {
      assert.equal(error.status, status);
      assert.match(mobileAccessError(error), message);
      return true;
    });
    assert.equal(calls.length, 1);
  }
  intercept(() => Response.json({ detail: 'Employee database unavailable' }, { status: 503 }));
  await assert.rejects(requestMobileAccess(supervisor, 'load'), /Employee database unavailable/);
});

test('tracker credentials are not sent to a different origin', async () => {
  setIdentity({ role: 'hr' });
  Object.defineProperty(globalThis, 'location', { value: { origin: 'https://another.example' }, configurable: true });
  const calls = intercept(() => { throw Error('Fetch was not expected'); });
  await assert.rejects(requestMobileAccess(supervisor, 'create', fields), /same server/);
  assert.equal(calls.length, 0);
});

