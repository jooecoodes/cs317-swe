import { apiRequest, apiId, apiActor } from '../api/api-client.js';
let busy = false;
let pending = null;
export function mutationInFlight() { return busy; }
export function pendingMutation() { return pending; }
export function clearPendingMutation() { pending = null; }

export function typePayload(values) {
  const name = String(values.name || '').trim(), description = String(values.description || '').trim(), points = Number(values.points);
  if (!name || !description) throw new Error('Please enter a name and description.');
  if (name.length > 100 || description.length > 1000) throw new Error('The name or description is too long. Please shorten it.');
  if (!Number.isInteger(points) || points < 0 || points > 100) throw new Error('Enter a whole number of points from 0 to 100.');
  return { name, description, default_points: points, is_strike: values.strike === 'on' };
}
export async function saveType(id, values, actor) { return apiRequest(`/violation-types${id ? '/' + apiId(id) : ''}`, { method: id ? 'PATCH' : 'POST', body: typePayload(values), actor }); }
export async function changeType(id, mode, actor) { return apiRequest(`/violation-types/${apiId(id)}${mode === 'delete' ? '' : '/' + mode}`, { method: mode === 'delete' ? 'DELETE' : 'POST', actor }); }
export async function issueViolation(employeeApiId, values, actor) {
  const issuer = String(values.recordedBy || '').trim();
  if (!issuer) throw new Error('Choose who issued this violation. Your signed-in name is used automatically.');
  return apiRequest(`/employees/${apiId(employeeApiId)}/violations`, { method: 'POST', actor, body: { violation_type_id: Number(apiId(values.typeId)), notes: String(values.description || '').trim(), issued_by: issuer } });
}
export async function updateViolation(id, values, actor) {
  const issuer = String(values.recordedBy || '').trim();
  if (!issuer) throw new Error('Choose who issued this violation.');
  return apiRequest(`/violations/${apiId(id)}`, { method: 'PATCH', actor, body: { notes: String(values.description || '').trim(), issued_by: issuer } });
}
export async function deleteViolation(id, reason, removedBy) {
  reason = String(reason || '').trim(); removedBy = String(removedBy || '').trim();
  reason = reason || 'No reason provided.';
  if (reason.length > 1000) throw new Error('Keep the removal reason within 1,000 characters.');
  if (!removedBy) throw new Error('Sign in before removing a record.');
  // Removal attribution is in the body. The reference explicitly excludes X-Actor.
  return apiRequest(`/violations/${apiId(id)}/remove`, { method: 'POST', body: { removed_by: removedBy, reason } });
}

// A single write per explicit confirmation. Lost replies are resolved by GET only.
export async function runMutation(task, ctx) {
  if (busy) return;

  if (pending) { ctx.showPending(); return; }
  apiActor(ctx.actor);
  await run(task, ctx, false);
}
export async function checkPendingMutation(ctx) { if (!busy && pending) await run(pending.task, ctx, true); }
async function run(task, ctx, checkOnly) {
  busy = true;
  const controls = [...ctx.dialog.querySelectorAll('button,input,select,textarea')].map(control => ({ control, disabled: control.disabled }));
  const button = ctx.dialog.querySelector('.modal-footer .primary,.modal-footer .danger');
  const oldLabel = button?.innerHTML;
  controls.forEach(({ control }) => control.disabled = true);
  if (button) button.textContent = checkOnly ? 'Checking save…' : 'Saving…';
  ctx.dialog.setAttribute('aria-busy', 'true');
  let complete = false, message = task.message;
  try {
    if (checkOnly) {
      const result = await task.reconcile();
      if (result === true) { pending = null; complete = true; }
      else if (result === false) { pending = null; ctx.error('No completed change was found. Review the current records before trying again.'); }
      else ctx.error('The save is still unconfirmed. Check again before making another change.');
    } else {
      try { await task.execute(); complete = true; }
      catch (error) {
        if (!error.uncertain) throw error;
        pending = { task, error: error.message };
        try {
          const result = await task.reconcile();
          if (result === true) { pending = null; complete = true; message = 'The change was found on the server.'; }
          // An absent new record may still be processing; do not re-POST automatically.
          else ctx.error('The connection was interrupted and the save is unconfirmed. Use Check save status before another attempt.');
        } catch { ctx.error('Could not confirm whether the change was saved. Check save status when the connection returns.'); }
      }
    }
    if (complete) {
      try { const refreshMessage = await ctx.refresh(); if (refreshMessage) message += ' ' + refreshMessage; }
      catch { message += ' Some lists could not refresh. Use Try again to reload them.'; }
    }
  } catch (error) { ctx.error(error.message || 'This change could not be saved. Your entries have been kept.'); }
  finally {
    busy = false; ctx.dialog.setAttribute('aria-busy', 'false');
    controls.forEach(({ control, disabled }) => control.disabled = disabled);
    if (button) button.innerHTML = oldLabel;
  }
  if (pending) ctx.showPending();
  if (complete) { ctx.close(); ctx.render(); ctx.toast(message); }
}
