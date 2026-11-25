import { apiId } from '../../api/api-client.js';
import { API_BASE_URL } from '../../api/hosted-api.js';
import { dataSource } from '../../state/data-source.js';
import { mayManage } from '../../../shared/permissions.js';

const operations = {
  load: { method: 'GET', suffix: '/login-account' },
  change: { method: 'PATCH', suffix: '/password' },
};

function failure(status, message) {
  return Object.assign(new Error(message), { status });
}

export async function requestLoginPassword(employee, action, values = {}) {
  if (!mayManage()) {
    throw failure(403, 'Only HR can change website login passwords.');
  }
  if (globalThis.location && globalThis.location.origin !== new URL(API_BASE_URL).origin) {
    throw failure(403, 'Open Northpoint on the same server as the sign-in service to change login passwords.');
  }
  if (!Object.hasOwn(operations, action)) throw new Error('Unknown password action.');

  const operation = operations[action];
  const id = apiId(employee.apiId);
  let body;
  if (action === 'change') {
    const password = typeof values.password === 'string' ? values.password : '';
    const length = [...password].length;
    if (length < 10 || length > 128) {
      throw failure(422, 'Enter a password between 10 and 128 characters.');
    }
    body = { password };
  }

  const result = await dataSource.request({
    service: 'session',
    path: '/employees/' + id + operation.suffix,
    method: operation.method,
    body,
  });
  if (action === 'change') return result;

  if (typeof result?.username !== 'string' || !result.username.trim() ||
      ![false, true, 0, 1].includes(result.disabled)) {
    throw new Error('The server returned unexpected login account information. Refresh and try again.');
  }
  return { username: result.username, disabled: Boolean(result.disabled) };
}

export function loginPasswordError(error) {
  if (error.status === 401) return 'Your session has expired. Sign in again to change login passwords.';
  if (error.status === 404) return 'This employee does not have a website login account.';
  if (error.accepted) return 'The server accepted the change. Refresh to check the account.';
  if (error.uncertain) return 'The server could not confirm the change. Refresh before trying again.';
  return error.message || 'Login password settings are temporarily unavailable. Try again.';
}
