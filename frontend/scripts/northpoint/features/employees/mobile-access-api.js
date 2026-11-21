import { apiId } from '../../api/api-client.js';
import { API_BASE_URL } from '../../api/hosted-api.js';
import { dataSource } from '../../state/data-source.js';
import { mayManageMobileAccess } from '../../../shared/permissions.js';

const operations = {
  load: { method: 'GET' },
  create: { method: 'POST', needsActive: true, needsUsername: true },
  link: { method: 'POST', suffix: '/link', needsActive: true, needsUsername: true },
  reset: { method: 'PATCH' },
  enable: { method: 'PATCH', needsActive: true },
  disable: { method: 'PATCH' },
};

function failure(status, message) {
  return Object.assign(new Error(message), { status });
}

function requestBody(action, values, operation) {
  if (action === 'load') return undefined;
  if (action === 'disable' || action === 'enable') return { disabled: action === 'disable' };

  const password = typeof values.password === 'string' ? values.password : '';
  const length = [...password].length;
  if (length < 10 || length > 128) {
    throw failure(422, 'Enter a password between 10 and 128 characters.');
  }
  if (!operation.needsUsername) return { password };

  const username = typeof values.username === 'string' ? values.username.trim() : '';
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{2,49}$/.test(username)) {
    throw failure(422, 'Enter a username of 3–50 letters, numbers, dots, underscores or hyphens. Start with a letter or number.');
  }
  return { username, password };
}

export async function requestMobileAccess(employee, action, values = {}) {
  if (!mayManageMobileAccess(employee)) {
    throw failure(403, 'Only HR can manage mobile access for Supervisor employees.');
  }
  if (globalThis.location && globalThis.location.origin !== new URL(API_BASE_URL).origin) {
    throw failure(403, 'Open Northpoint on the same server as the sign-in service to manage mobile access.');
  }
  if (!Object.hasOwn(operations, action)) throw new Error('Unknown mobile access action.');

  const operation = operations[action];
  if (operation.needsActive && employee.status !== 'Active') {
    throw failure(403, 'Reactivate this employee before setting up or enabling mobile access.');
  }
  const id = apiId(employee.apiId);
  const body = requestBody(action, values, operation);
  const result = await dataSource.request({
    service: 'session',
    path: '/employees/' + id + '/mobile-access' + (operation.suffix || ''),
    method: operation.method,
    body,
  });
  if (action !== 'load') return result;

  const account = result?.account;
  if (String(result?.employee_id) !== id || typeof result.eligible !== 'boolean' ||
      !['active', 'inactive'].includes(result.status) ||
      (account !== null && (typeof account?.username !== 'string' ||
        ![false, true, 0, 1].includes(account.disabled)))) {
    throw new Error('The server returned unexpected mobile access information. Refresh access and try again.');
  }
  return {
    eligible: result.eligible && result.employee_type === 'supervisor',
    active: result.status === 'active',
    account: account && { username: account.username, disabled: Boolean(account.disabled) },
  };
}

export function mobileAccessError(error) {
  if (error.status === 401) return 'Your session has expired. Sign in again to manage mobile access.';
  if (error.accepted) return 'The server accepted the change. Refresh access to check the account.';
  if (error.uncertain) return 'The server could not confirm the change. Refresh access before trying again.';
  return error.message || 'Mobile access is temporarily unavailable. Try again.';
}

