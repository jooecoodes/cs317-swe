import {canUseMobileAccess} from '../../../shared/permissions.js';
import {dataSource} from '../../state/data-source.js';

export function mobileAccessPanel(employee, esc) {
 return `<section class="panel mobile-access" data-employee-id="${esc(employee.apiId)}"><div class="panel-header"><div><h2>Mobile App Access</h2><p>Create the sign-in details for ${esc(employee.name)}.</p></div></div><div class="panel-body"><div class="mobile-access-content"><p>Check whether this employee already has a mobile account.</p><button type="button" class="button primary" data-mobile-action="load">Open Mobile App Access</button></div><p class="mobile-access-message" role="status" aria-live="polite"></p></div></section>`;
}
const escape = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function request(id, method='GET', body, suffix='') {
 return dataSource.request({service:'session',path:`/employees/${id}/mobile-access${suffix}`,method,body});
}

async function load(section) {
 const data=await request(section.dataset.employeeId), account=data.account;
 const content=section.querySelector('.mobile-access-content');
 content.innerHTML=account ? `<p><strong>${escape(account.username)}</strong> — ${account.disabled?'Access disabled':'Account ready'}</p><p>This account is linked to ${escape(data.full_name)}.</p><form data-mobile-form="reset"><label>New password (at least 10 characters)<input name="password" type="password" autocomplete="new-password" minlength="10" maxlength="128" required></label><label class="mobile-show"><input type="checkbox" data-mobile-show> Show password</label><button class="button secondary" type="submit">Reset Password</button></form><button class="button secondary" type="button" data-mobile-action="${account.disabled?'enable':'disable'}">${account.disabled?'Enable':'Disable'} Mobile Access</button>` : `<p>No mobile account yet. Enter sign-in details, then create the account.</p><form data-mobile-form="create"><label>Username<input name="username" autocomplete="off" autocapitalize="none" minlength="3" maxlength="50" pattern="[A-Za-z0-9][A-Za-z0-9._\\-]{2,49}" required></label><p>Use 3–50 letters, numbers, dots, underscores or hyphens.</p><label>Password (at least 10 characters)<input name="password" type="password" autocomplete="new-password" minlength="10" maxlength="128" required></label><label class="mobile-show"><input type="checkbox" data-mobile-show> Show password</label><p>Give these details to the employee securely. Saved passwords cannot be displayed later.</p><button class="button primary" type="submit">Create Mobile Account</button><details><summary>Already has an older tracker account?</summary><p>Enter its username above and a new password. This links an unlinked account and signs out its existing phones.</p><button class="button secondary" type="submit" name="link" value="yes">Link Existing Account</button></details></form>`;
 content.insertAdjacentHTML('beforeend','<button class="button secondary" type="button" data-mobile-action="load">Refresh Access</button>');
}
async function run(section, action) {
 if(section.dataset.busy)return;
 section.dataset.busy='true';
 const message=section.querySelector('.mobile-access-message');
 message.textContent='Please wait…';
 section.querySelectorAll('button').forEach(b=>b.disabled=true);
 try {await action(message);} catch(error){message.textContent=error.message;message.setAttribute('role','alert');}
 finally {delete section.dataset.busy;section.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
document.addEventListener('change', event=>{
 if(canUseMobileAccess()&&event.target.matches('.mobile-access [data-mobile-show]'))event.target.closest('form').querySelector('[name=password]').type=event.target.checked?'text':'password';
});
document.addEventListener('click', event=>{
 const button=event.target.closest('[data-mobile-action]');if(!button)return;
 const section=button.closest('.mobile-access'), action=button.dataset.mobileAction;
 if(!canUseMobileAccess()||!section||!['load','disable','enable'].includes(action))return;
 void run(section,async message=>{
  if(action==='load'){await load(section);message.textContent='Mobile access information is up to date.';return;}
  if(action==='disable'&&!confirm('Disable this employee’s mobile access and sign out their phones?')){message.textContent='No changes made.';return;}
  const result=await request(section.dataset.employeeId,'PATCH',{disabled:action==='disable'});
  await load(section);message.textContent=result.message;
 });
});
document.addEventListener('submit', event=>{
 const form=event.target.closest('form[data-mobile-form]');if(!form)return;
 event.preventDefault();event.stopImmediatePropagation();
 const section=form.closest('.mobile-access');if(!canUseMobileAccess()||!section)return;
 const values=new FormData(form), linking=event.submitter?.name==='link';
 void run(section,async message=>{
  const create=form.dataset.mobileForm==='create';
  const result=await request(section.dataset.employeeId,create?'POST':'PATCH',create?{username:values.get('username').trim(),password:values.get('password')}:{password:values.get('password')},linking?'/link':'');
  // Erase the password promptly even if the follow-up status request fails.
  form.reset();await load(section);message.textContent=result.message;
 });
},true);
