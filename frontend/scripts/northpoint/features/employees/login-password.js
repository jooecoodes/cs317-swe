import { mayManage } from '../../../shared/permissions.js';
import { loginPasswordError, requestLoginPassword } from './login-password-api.js';

function refreshButton(label = 'Refresh Password Settings') {
  return '<button class="button secondary" type="button" data-login-action="load">' + label + '</button>';
}

export function loginPasswordPanel(employee, esc) {
  if (!mayManage()) return '';
  return `<section class="panel mobile-access login-password" data-employee-id="${esc(employee.apiId)}">
    <div class="panel-header"><div><h2>Website Login Password</h2><p>Change the password ${esc(employee.name)} uses to sign in to Northpoint.</p></div></div>
    <div class="panel-body"><div class="login-password-content">
      <p>Only HR can change website login passwords. Tracker app passwords are managed under Mobile App Access.</p>
      <button type="button" class="button primary" data-login-action="load">Open Password Settings</button>
    </div><p class="mobile-access-message login-password-message" role="status" aria-live="polite"></p></div>
  </section>`;
}

const passwordField = `<label>New password (10–128 characters)
  <input name="password" type="password" autocomplete="new-password" minlength="10" maxlength="128" required>
</label><label class="mobile-show"><input type="checkbox" data-login-show> Show password</label>`;

function renderStatus(content, status, esc) {
  content.innerHTML = `<p>Username: <strong>${esc(status.username)}</strong> — ${status.disabled ? 'Login disabled' : 'Login enabled'}</p>
    <form data-login-form="change">
      ${passwordField}
      <p>Changing the password signs out this employee’s existing browser sessions.</p>
      <button class="button primary" type="submit">Change Password</button>
    </form>${refreshButton()}`;
}

function actionAvailable(action, status) {
  if (action === 'load') return true;
  return action === 'change' && Boolean(status?.username);
}

export function bindLoginPassword(root, getProfileEmployee, esc, ui = {}) {
  const statuses = new WeakMap();
  const busy = new WeakSet();

  function showResult(ok, message, username) {
    if (typeof ui.openModal !== 'function') return;
    const details = username
      ? `<p class="muted">Username: <strong>${esc(username)}</strong></p>`
      : '';
    ui.openModal(
      ok ? 'Updated successfully' : 'Update failed',
      `<p>${esc(message)}</p>${details}`,
      `<button class="button ${ok ? 'primary' : 'secondary'}" data-action="close-modal">${ok ? 'Done' : 'Close'}</button>`,
    );
  }

  function getEmployee(section) {
    const employee = getProfileEmployee();
    if (!section || !root.contains(section) || !mayManage() || !employee) return null;
    return String(employee.apiId) === section.dataset.employeeId ? employee : null;
  }

  function announce(section, text, error = false) {
    const message = section.querySelector('.login-password-message');
    message.setAttribute('role', error ? 'alert' : 'status');
    message.textContent = text;
  }

  async function run(section, action, form) {
    const employee = getEmployee(section);
    const status = statuses.get(section);
    if (!employee || busy.has(section) || !actionAvailable(action, status)) return;

    const values = form ? Object.fromEntries(new FormData(form)) : undefined;
    const content = section.querySelector('.login-password-content');
    const buttons = [...section.querySelectorAll('button')].filter(button => !button.disabled);
    busy.add(section);
    content.setAttribute('aria-busy', 'true');
    buttons.forEach(button => { button.disabled = true; });
    announce(section, action === 'load' ? 'Loading password settings…' : 'Changing password…');

    async function load() {
      const latest = await requestLoginPassword(employee, 'load');
      if (!getEmployee(section)) return;
      statuses.set(section, latest);
      renderStatus(content, latest, esc);
    }

    try {
      if (action === 'load') {
        await load();
        announce(section, 'Password settings are up to date.');
        return;
      }

      const result = await requestLoginPassword(employee, action, values);
      const message = typeof result?.message === 'string' ? result.message : 'Password changed.';
      const username = status?.username;
      form?.reset();
      showResult(true, message, username);
      if (!getEmployee(section)) return;
      statuses.delete(section);
      content.innerHTML = refreshButton();
      try {
        await load();
        announce(section, message);
      } catch (error) {
        announce(section, message + ' Could not refresh the account. ' + loginPasswordError(error), true);
      }
    } catch (error) {
      const message = loginPasswordError(error);
      if (action === 'load' || error.uncertain || error.accepted ||
          [401, 403, 404].includes(error.status)) {
        form?.reset();
        statuses.delete(section);
        content.innerHTML = refreshButton('Try again');
      }
      announce(section, message, true);
      if (action !== 'load') showResult(false, message, status?.username);
    } finally {
      busy.delete(section);
      content.removeAttribute('aria-busy');
      buttons.forEach(button => { button.disabled = false; });
    }
  }

  root.addEventListener('click', event => {
    const button = event.target.closest('[data-login-action]');
    if (button) void run(button.closest('.login-password'), button.dataset.loginAction);
  });
  root.addEventListener('submit', event => {
    const form = event.target.closest('form[data-login-form]');
    if (!form) return;
    event.preventDefault();
    if (!form.reportValidity()) return;
    void run(form.closest('.login-password'), form.dataset.loginForm, form);
  });
  root.addEventListener('change', event => {
    const checkbox = event.target;
    if (!checkbox.matches('[data-login-show]') || !getEmployee(checkbox.closest('.login-password'))) return;
    const password = checkbox.form?.elements.namedItem('password');
    if (password) password.type = checkbox.checked ? 'text' : 'password';
  });

  return {
    load() {
      const section = root.querySelector('.login-password');
      if (section) void run(section, 'load');
    },
  };
}
