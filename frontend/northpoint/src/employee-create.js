import { employeeDirectory, createApiEmployee, employeeCreatePayload, employeeMatchesCreation, employeeCodeKey, fetchEmployeeDirectorySnapshot } from './employee-api.js';

let saving = false;
let unconfirmed = null;
export function employeeCreateInFlight() { return saving; }
export function pendingEmployeeCreation() { return unconfirmed; }

export async function submitApiEmployeeForm(form, values, ctx) {
  if (saving || form.dataset.saving === 'true') return;
  let payload, actor;
  try {

    payload = unconfirmed?.payload || employeeCreatePayload({ employee_code:values.employee_code, first_name:values.firstName, last_name:values.lastName, department:values.department, position:values.position });
    actor = unconfirmed?.actor || ctx.actor;
  } catch (error) { ctx.formError(form,error.message); return; }
  const controls = [...ctx.dialog.querySelectorAll('button,input,select,textarea')].map(control => ({ control, disabled:control.disabled }));
  const submit = ctx.dialog.querySelector('[type="submit"][form="employee-form"]');
  const label = unconfirmed ? 'Add Employee' : submit?.innerHTML;
  saving = true; form.dataset.saving = 'true'; form.setAttribute('aria-busy','true');
  controls.forEach(({control}) => control.disabled = true);
  if (submit) submit.textContent = unconfirmed ? 'Checking save…' : 'Saving…';
  const errorBox = form.querySelector('.form-error');
  if (errorBox) { errorBox.textContent = ''; errorBox.classList.remove('show'); }
  let completed = false, message = '';
  async function checkUnconfirmed() {
    await ctx.refresh();
    if (employeeDirectory.status !== 'ready') {
      ctx.formError(form,'The save could not be verified with the backend. No employee has been added to the list locally. Reconnect and choose “Check save status”; your entries have been kept.');
      return;
    }
    const existing = employeeDirectory.items.find(employee => employeeCodeKey(employee.id) === employeeCodeKey(payload.employee_code));
    if (existing && employeeMatchesCreation(existing,payload) && (!unconfirmed?.apiId || existing.apiId===unconfirmed.apiId)) {
      completed = true; message = 'The employee is on the server. The list has been refreshed.'; unconfirmed = null;
    } else if (existing) {
      unconfirmed = null;
      ctx.formError(form,'This employee code belongs to a different employee. Enter another code before saving again. Your other entries have been kept.');
    } else if (unconfirmed?.accepted) {
      ctx.formError(form,'The server accepted the request, but the employee is not visible in the list yet. Choose “Check save status” again; this will not send another POST.');
    } else {
      unconfirmed = null;
      ctx.formError(form,'No saved employee was found with this code. Your entries have been kept. You can try Add Employee again.');
    }
  }

  try {
    if (unconfirmed) await checkUnconfirmed();
    else {
      if (submit) submit.textContent = 'Checking employee code…';
      const directory = await fetchEmployeeDirectorySnapshot();
      const existing = directory.items.find(employee => employeeCodeKey(employee.id) === employeeCodeKey(payload.employee_code));
      if (existing) {
        throw Object.assign(new Error(`Employee code ${payload.employee_code} is already used by an ${existing.status.toLowerCase()} employee. Enter another code. Your other entries have been kept.`), { code:'duplicate' });
      }
      if (submit) submit.textContent = 'Saving…';

      const created = await createApiEmployee(payload,actor);
      // Only a fresh backend GET may populate the list. A POST reply is never
      // inserted locally when the verification request fails or goes offline.
      unconfirmed = {payload,actor,accepted:true,apiId:created.apiId};
      await checkUnconfirmed();
      if(completed)message='Employee added successfully.';
    }
  } catch (error) {
    if (error.uncertain) {
      unconfirmed = { payload, actor, accepted:Boolean(error.accepted) };
      await checkUnconfirmed();
    } else if (error.code === 'conflict') {
      try {
        const directory = await fetchEmployeeDirectorySnapshot();
        const existing = directory.items.find(employee => employeeCodeKey(employee.id) === employeeCodeKey(payload.employee_code));
        ctx.formError(form,existing ? `Employee code ${payload.employee_code} is already used by an ${existing.status.toLowerCase()} employee. Enter another code. Your other entries have been kept.` : `${error.message} The latest employee list contains no matching code; your entries have been kept.`);
      } catch { ctx.formError(form,`${error.message} The employee list could not be checked again. Your entries have been kept.`); }
    } else ctx.formError(form,error.message || 'The employee could not be saved. Your entries have been kept.');
  } finally {
    saving = false; form.dataset.saving = 'false'; form.setAttribute('aria-busy','false');
    controls.forEach(({control,disabled}) => control.disabled = disabled);
    form.querySelectorAll('input,select,textarea').forEach(control => control.disabled = Boolean(unconfirmed) || control.name === 'newDepartment' && form.elements.department?.value !== '__other_department__');
    if (submit) {
      submit.innerHTML = unconfirmed ? 'Check save status' : label;
      submit.disabled = false;
    }
  }
  if (completed) {
    ctx.closeModal(); ctx.resetFilters(); ctx.render(); ctx.toast(message,'check-circle');
  }
}
