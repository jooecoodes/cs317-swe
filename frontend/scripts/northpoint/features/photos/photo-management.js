import {photoData,photoUpload,photoRequest,readPhoto,photoDownloadUrl,loadPhotos} from './photo-service.js';
import {photoActivityService} from './photo-activity.js';
import {displayActor} from '../../auth/session.js';
import {businessDate} from '../reports/yesterday.js';

export const photoManagement={selected:new Set(),pending:null};
let detailVersion=0;
const bytes=size=>size>=1048576?(size/1048576).toFixed(1)+' MB':Math.max(1,Math.round(size/1024))+' KB';
function currentDialog(body,version){return detailVersion===version&&body?.isConnected&&document.querySelector('#modal')?.open;}
function errorMessage(message){const node=document.querySelector('#photo-error');if(node){node.textContent=message;node.hidden=false;}}
function footer(photo,c){return `<a class="button secondary" href="${c.esc(photoDownloadUrl(photo.id))}" download>Download</a><button class="button primary" data-action="photo-edit" data-id="${photo.id}">Edit details</button><button class="button secondary" data-action="photo-rename" data-id="${photo.id}">Rename</button><button class="button secondary" data-action="photo-history" data-id="${photo.id}">View History</button><button class="button danger-outline" data-action="photo-delete-confirm" data-id="${photo.id}">Delete Photo</button><button class="button secondary" data-action="close-modal">Close</button>`;}
function showDetails(photo,c){
 c.openModal('Photo Details',`<div class="np-photo-viewer"><p role="status">Loading photo…</p><img src="${c.esc(photo.url)}" alt="${c.esc(photo.name)}" hidden><div class="np-photo-viewer-error" role="alert" hidden><p>This image cannot be previewed in this browser. Download the original to view it.</p></div></div><h3>${c.esc(photo.name)}</h3><p class="np-photo-description">${c.esc(photo.description||'No description added.')}</p><dl class="np-photo-detail-meta"><div><dt>Uploaded by</dt><dd>${c.esc(displayActor(photo.owner))}</dd></div><div><dt>Added</dt><dd>${c.formatDate(businessDate(photo.created))}</dd></div><div><dt>File size</dt><dd>${bytes(photo.size)}</dd></div><div><dt>Tags</dt><dd>${c.esc(photo.tags.join(', ')||'No tags')}</dd></div><div><dt>Original file</dt><dd>${c.esc(photo.originalFilename||'Not provided')}</dd></div>${photo.width&&photo.height?`<div><dt>Dimensions</dt><dd>${photo.width} × ${photo.height}</dd></div>`:''}</dl>`,footer(photo,c));
 const viewer=document.querySelector('.np-photo-viewer'),image=viewer.querySelector('img'),status=viewer.querySelector('[role=status]'),error=viewer.querySelector('[role=alert]');viewer.closest('dialog').classList.add('photo-viewer-dialog','photo-management-dialog');
 const loaded=()=>{status.hidden=true;image.hidden=false;error.hidden=true;},failed=()=>{status.hidden=true;image.hidden=true;error.hidden=false;};image.addEventListener('load',loaded,{once:true});image.addEventListener('error',failed,{once:true});if(image.complete)(image.naturalWidth?loaded:failed)();
}
async function openPhoto(id,mode,c){
 const version=++detailVersion;c.openModal('Photo Details','<p role="status">Loading photo details…</p>','<button class="button secondary" data-action="close-modal">Cancel</button>');const body=document.querySelector('#modal .modal-content');
 try{const photo=await readPhoto(id);if(!currentDialog(body,version))return;
  if(mode==='details'){showDetails(photo,c);return;}
  if(mode==='delete'){
   c.openModal('Delete Photo?',`<p>Permanently delete <strong>${c.esc(photo.name)}</strong>?</p><p class="form-intro">The photo file will be deleted. Its activity history will remain available.</p><form id="photo-delete-form" data-id="${photo.id}"><label class="confirm-check"><input type="checkbox" name="confirmed" required>I understand that this permanently removes the photo.</label><p id="photo-error" class="form-error show" hidden role="alert"></p></form>`,`<button class="button secondary" data-action="close-modal">Cancel</button><button type="submit" form="photo-delete-form" class="button danger">Delete Photo</button>`);return;
  }
  const rename=mode==='rename';
  c.openModal(rename?'Rename Photo':'Edit Photo Details',`<form id="${rename?'photo-rename-form':'photo-edit-form'}" data-id="${photo.id}"><p id="photo-error" class="form-error show" role="alert" hidden></p><div class="field"><label for="photo-edit-name">Photo name</label><input id="photo-edit-name" name="name" maxlength="255" required value="${c.esc(photo.name)}"></div>${rename?'<label class="confirm-check"><input type="checkbox" name="renameFile">Also rename the stored image file.</label>':`<div class="field"><label for="photo-edit-description">Description <span class="muted">(optional)</span></label><textarea id="photo-edit-description" name="description" maxlength="2000">${c.esc(photo.description)}</textarea></div><div class="field"><label for="photo-edit-tags">Tags <span class="muted">(optional)</span></label><input id="photo-edit-tags" name="tags" value="${c.esc(photo.storedTags.join(', '))}" placeholder="Separate tags with commas"></div>`}</form>`,`<button class="button secondary" data-action="photo-details" data-id="${photo.id}">Cancel</button><button class="button primary" type="submit" form="${rename?'photo-rename-form':'photo-edit-form'}">${rename?'Rename Photo':'Save changes'}</button>`);
  document.querySelector(rename?'#photo-rename-form':'#photo-edit-form').photoOriginal=photo;
 }catch(error){if(currentDialog(body,version))body.innerHTML=`<p role="alert">${c.esc(error.message)}</p><button class="button secondary" data-action="photo-${mode==='details'?'details':mode==='delete'?'delete-confirm':mode}" data-id="${c.esc(id)}">Try Again</button>`;}
}
async function removed(ids,actor){
 // Batch reads are limited to 200 IDs by the backend.
 for(let start=0;start<ids.length;start+=200){const data=await photoRequest('/photos/batch',{method:'POST',body:{ids:ids.slice(start,start+200).map(Number)},actor});if(!Array.isArray(data.found)||!Array.isArray(data.missing))throw Error('Could not verify photo deletion.');if(data.found.length)return false;}
 return true;
}
async function runWrite(task,c,checkOnly=false){
 if(photoUpload.busy)return;
 if(photoUpload.uncertain){errorMessage('Check the previous upload in the library before making another change.');return;}
 if(photoManagement.pending&&!checkOnly){errorMessage('Check the previous photo change before saving again.');return;}
 const modal=document.querySelector('#modal'),controls=[...modal.querySelectorAll('button,input,textarea')].map(node=>({node,disabled:node.disabled}));let complete=false;
 photoUpload.busy=true;modal.setAttribute('aria-busy','true');controls.forEach(({node})=>node.disabled=true);
 try{
  if(!checkOnly){try{await task.execute();photoManagement.pending=task;}catch(error){if(!error.uncertain)throw error;photoManagement.pending=task;}}
  const verified=await task.verify();if(verified){complete=true;photoManagement.pending=null;}else if(checkOnly){photoManagement.pending=null;errorMessage('The completed change was not found. Review the current photos before trying again.');}else{photoManagement.pending=task;errorMessage('This change is not confirmed yet. Check save status before another attempt.');}
  if(complete){for(const id of task.deletedIds||[])photoManagement.selected.delete(String(id));await loadPhotos(true);await photoActivityService.load({},true);}
 }catch(error){if(checkOnly||photoManagement.pending||error.uncertain)photoManagement.pending=task;errorMessage(error.message||'Could not save the photo change.');}
 finally{photoUpload.busy=false;modal.setAttribute('aria-busy','false');controls.forEach(({node,disabled})=>node.disabled=disabled);}
 if(complete){c.closeModal();c.render();c.toast(task.message+(photoData.status==='error'?' Refresh the library to load the updated list.':''));if(task.after)await task.after();}
 else if(photoManagement.pending){const foot=modal.querySelector('.modal-footer');if(foot)foot.innerHTML='<button class="button secondary" data-action="close-modal">Close</button><button class="button primary" data-action="photo-check-change">Check save status</button>';c.render();}
 else if(checkOnly){const foot=modal.querySelector('.modal-footer');if(foot)foot.innerHTML='<button class="button secondary" data-action="photo-review-change">Review library</button>';c.render();}
}
export async function handlePhotoManagementAction(action,el,c){
 const modes={'photo-details':'details','photo-edit':'edit','photo-rename':'rename','photo-delete-confirm':'delete'};
 if(modes[action]){await openPhoto(el.dataset.id,modes[action],c);return true;}
 if(action==='photo-check-change'){if(photoManagement.pending){if(!document.querySelector('#modal')?.open)c.openModal('Check Photo Change','<p id="photo-error" class="form-error show" role="alert" hidden></p><p>Checking the saved photo details…</p>','<button class="button secondary" data-action="close-modal">Close</button>');await runWrite(photoManagement.pending,c,true);}return true;}
 if(action==='photo-review-change'){await loadPhotos(true);c.closeModal();c.render();return true;}
 if(action==='photo-selection-clear'){photoManagement.selected.clear();c.render();return true;}
 if(action==='photo-bulk-delete'){
  const ids=[...photoManagement.selected].filter(id=>photoData.items.some(photo=>photo.id===id));if(!ids.length)return true;
  c.openModal('Delete selected photos?',`<p>Delete <strong>${ids.length} selected ${ids.length===1?'photo':'photos'}</strong> and their image files?</p><p class="form-intro">This cannot be undone. Activity history is retained.</p><form id="photo-bulk-delete-form"><p id="photo-error" class="form-error show" role="alert" hidden></p><label class="confirm-check"><input type="checkbox" name="confirmed" required>I understand that these photos will be permanently deleted.</label></form>`,`<button class="button secondary" data-action="close-modal">Cancel</button><button class="button danger" type="submit" form="photo-bulk-delete-form">Delete ${ids.length} photos</button>`);document.querySelector('#photo-bulk-delete-form').photoIds=ids;return true;
 }
 return false;
}
export async function handlePhotoManagementSubmit(form,values,c){
 if(!['photo-edit-form','photo-rename-form','photo-delete-form','photo-bulk-delete-form'].includes(form.id))return false;
 const id=form.dataset.id,actor=c.store.settings.name,original=form.photoOriginal;
 try{
  if(form.id==='photo-delete-form'||form.id==='photo-bulk-delete-form'){
   if(!values.confirmed)return true;const ids=form.id==='photo-delete-form'?[id]:form.photoIds;if(!ids?.length)throw Error('Select the photos again before deleting.');
   await runWrite({execute:()=>form.id==='photo-delete-form'?photoRequest('/photos/'+id,{method:'DELETE',actor}):photoRequest('/photos/bulk-delete',{method:'POST',body:{ids:ids.map(Number)},actor}),verify:()=>removed(ids,actor),deletedIds:ids,message:ids.length===1?'Photo deleted.':ids.length+' photos deleted.'},c);return true;
  }
  if(!original)throw Error('Reload the photo before saving.');const name=String(values.name||'').trim();if(!name||name.length>255)throw Error('Enter a photo name of 255 characters or fewer.');
  if(form.id==='photo-rename-form'){
   const renameFile=values.renameFile==='on';await runWrite({execute:()=>photoRequest('/photos/'+id+'/rename',{method:'POST',actor,body:{display_name:name,rename_file:renameFile}}),verify:async()=>{const saved=await readPhoto(id);return saved.displayName===name&&(!renameFile||saved.filename!==original.filename);},message:'Photo renamed.',after:()=>c.showPhotoDetails(id)},c);return true;
  }
  const description=String(values.description||'').trim(),tags=[...new Set(String(values.tags||'').split(',').map(tag=>tag.trim()).filter(Boolean))],body={};
  if(description.length>2000)throw Error('Keep the description within 2,000 characters.');
  if(name!==original.name)body.display_name=name;if(description!==original.description)body.description=description;if(JSON.stringify(tags)!==JSON.stringify(original.storedTags))body.tags=tags;
  if(!Object.keys(body).length){c.toast('No photo details have changed.','info');return true;}
  await runWrite({execute:()=>photoRequest('/photos/'+id,{method:'PATCH',actor,body}),verify:async()=>{const saved=await readPhoto(id);return saved.displayName===(body.display_name??original.displayName)&&saved.description===description&&JSON.stringify(saved.storedTags)===JSON.stringify(tags);},message:'Photo details saved.',after:()=>c.showPhotoDetails(id)},c);
 }catch(error){errorMessage(error.message);}
 return true;
}
