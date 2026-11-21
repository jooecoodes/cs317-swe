import { mayManageMobileAccess } from '../../../shared/permissions.js';
import { mobileAccessError, requestMobileAccess } from './mobile-access-api.js';

function refreshButton(label = 'Refresh Access') {
  return '<button class="button secondary" type="button" data-mobile-action="load">' + label + '</button>';
}

export function mobileAccessPanel(employee, esc) {
  if (!mayManageMobileAccess(employee)) return '';
  return `<section class="panel mobile-access" data-employee-id="${esc(employee.apiId)}">
    <div class="panel-header"><div><h2>Mobile App Access</h2><p>Manage tracker sign-in for ${esc(employee.name)}.</p></div></div>
    <div class="panel-body"><div class="mobile-access-content">
      <p>Check whether this employee already has a mobile account.</p>
      <button type="button" class="button primary" data-mobile-action="load">Open Mobile App Access</button>
    </div><p class="mobile-access-message" role="status" aria-live="polite"></p></div>
  </section>`;
}

const passwordField = `<label>New password (10–128 characters)
  <input name="password" type="password" autocomplete="new-password" minlength="10" maxlength="128" required>
</label><label class="mobile-show"><input type="checkbox" data-mobile-show> Show password</label>`;

function renderStatus(content, status, esc) {
  const { eligible, active, account } = status;
  if (!eligible) {
    content.innerHTML = '<p>Only Supervisor employees are eligible for mobile access.</p>' + refreshButton();
    return;
  }
  const inactiveNotice = active ? '' : '<p>Reactivate this employee to set up or enable mobile access.</p>';
  if (!account) {
    content.innerHTML = '<p>No mobile account yet.</p>' + inactiveNotice + (active ? `
      <form data-mobile-form="create">
        <label>Username<input name="username" autocomplete="off" autocapitalize="none" spellcheck="false"
          minlength="3" maxlength="50" pattern="[A-Za-z0-9][A-Za-z0-9._\\-]{2,49}" required></label>
        <p>Use 3–50 letters, numbers, dots, underscores or hyphens.</p>
        ${passwordField}
        <p>Give these details to the employee securely. Saved passwords cannot be displayed later.</p>
        <button class="button primary" type="submit">Create Mobile Account</button>
        <details><summary>Already has an older tracker account?</summary>
          <p>Enter its username and a new password. Linking signs out its existing phones.</p>
          <button class="button secondary" type="submit" value="link">Link Existing Account</button>
        </details>
      </form>` : '') + refreshButton();
    return;
  }
  const toggle = account.disabled ? 'enable' : 'disable';
  content.innerHTML = `<p><strong>${esc(account.username)}</strong> — ${account.disabled ? 'Access disabled' : 'Account enabled'}</p>
    ${inactiveNotice}<form data-mobile-form="reset">
      ${passwordField}<button class="button secondary" type="submit">Reset Password</button>
    </form>${!account.disabled || active ? `<button class="button secondary" type="button" data-mobile-action="${toggle}">${account.disabled ? 'Enable' : 'Disable'} Mobile Access</button>` : ''}${refreshButton()}`;
}

function actionAvailable(action, status) {
  if (action === 'load') return true;
  if (!status?.eligible) return false;
  if (action === 'create' || action === 'link') return status.active && !status.account;
  if (action === 'reset') return Boolean(status.account);
  if (action === 'enable') return status.active && status.account?.disabled === true;
  return action === 'disable' && status.account?.disabled === false;
}

export function bindMobileAccess(root, getProfileEmployee, esc) {
  const statuses = new WeakMap();
  const busy = new WeakSet();

  function getEmployee(section) {
    const employee = getProfileEmployee();
    if (section && root.contains(section) && mayManageMobileAccess(employee) &&
        String(employee.apiId) === section.dataset.employeeId) return employee;
    return null;
  }

  function announce(section, text, error = false) {
    const message = section.querySelector('.mobile-access-message');
    message.setAttribute('role', error ? 'alert' : 'status');
    message.textContent = text;
  }

  async function run(section, action, form) {
    const employee = getEmployee(section);
    const status = statuses.get(section);
    if (!employee || busy.has(section) || !actionAvailable(action, status)) return;

    if (action === 'disable' && !window.confirm('Disable this employee’s mobile access and sign out their phones?')) return;
    const values = form ? Object.fromEntries(new FormData(form)) : undefined;
    // Use the status returned by the account API for actions on inactive employees.
    const target = action === 'load' ? employee : { ...employee, status: status.active ? 'Active' : 'Inactive' };
    const content = section.querySelector('.mobile-access-content');
    const buttons = [...section.querySelectorAll('button')].filter(button => !button.disabled);
    busy.add(section);
    content.setAttribute('aria-busy', 'true');
    buttons.forEach(button => { button.disabled = true; });
    announce(section, action === 'load' ? 'Loading mobile access…' : 'Saving mobile access…');

    async function load() {
      const latest = await requestMobileAccess(employee, 'load');
      if (!getEmployee(section)) return;
      statuses.set(section, latest);
      renderStatus(content, latest, esc);
    }

    try {
      if (action === 'load') {
        await load();
        announce(section, 'Mobile access information is up to date.');
        return;
      }

      const result = await requestMobileAccess(target, action, values);
      const message = typeof result?.message === 'string' ? result.message : 'Mobile access saved.';
      form?.reset();
      if (!getEmployee(section)) return;
      statuses.delete(section);
      content.innerHTML = refreshButton();
      try {
        await load();
        announce(section, message);
      } catch (error) {
        announce(section, message + ' Could not refresh the account. ' + mobileAccessError(error), true);
      }
    } catch (error) {
      if (action === 'load' || error.uncertain || error.accepted ||
          [401, 403, 409].includes(error.status) || (error.status === 404 && action !== 'link')) {
        form?.reset();
        statuses.delete(section);
        content.innerHTML = refreshButton('Try again');
      }
      announce(section, mobileAccessError(error), true);
    } finally {
      busy.delete(section);
      content.removeAttribute('aria-busy');
      buttons.forEach(button => { button.disabled = false; });
    }
  }

  root.addEventListener('click', event => {
    const button = event.target.closest('[data-mobile-action]');
    if (button) void run(button.closest('.mobile-access'), button.dataset.mobileAction);
  });
  root.addEventListener('submit', event => {
    const form = event.target.closest('form[data-mobile-form]');
    if (!form) return;
    event.preventDefault();
    const action = event.submitter?.value === 'link' && form.dataset.mobileForm === 'create'
      ? 'link' : form.dataset.mobileForm;
    if (!['create', 'link', 'reset'].includes(action) || !form.reportValidity()) return;
    void run(form.closest('.mobile-access'), action, form);
  });
  root.addEventListener('change', event => {
    const checkbox = event.target;
    if (!checkbox.matches('[data-mobile-show]') || !getEmployee(checkbox.closest('.mobile-access'))) return;
    const password = checkbox.form?.elements.namedItem('password');
    if (password) password.type = checkbox.checked ? 'text' : 'password';
  });
}

