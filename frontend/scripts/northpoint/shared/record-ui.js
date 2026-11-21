export function recordChoice(name,label,choices,current,esc,icon){
 const selected=choices.find(choice=>choice[0]===current)||choices[0];
 return `<details class="record-filter"><summary><span>${esc(selected[1])}</span>${icon('chevron-down',14)}</summary><div class="record-filter-popup"><div class="record-filter-heading"><strong>${esc(label)}</strong><button type="button" class="icon-button" data-action="close-record-filter" aria-label="Close ${esc(label)} filter">${icon('close',16)}</button></div><div class="record-filter-options">${choices.map(([value,text,disabled])=>`<label class="record-filter-option"><span>${esc(text)}</span><input type="radio" name="${name}" value="${esc(value)}" ${value===selected[0]?'checked':''} ${disabled?'disabled':''}></label>`).join('')}</div></div></details>`;
}
export function recordDateFilter(f,esc,icon,{label="Incident date",prefix="violation"}={}){
 return `<details class="record-filter"><summary><span>${f.from||f.to?'Date range applied':esc(label)}</span>${icon('chevron-down',14)}</summary><div class="record-filter-popup"><div class="record-filter-heading"><strong>${esc(label)}</strong><button class="icon-button" type="button" data-action="close-record-filter" aria-label="Close date filter">${icon('close',16)}</button></div><div class="record-date-fields"><div class="field"><label for="${prefix}-from">From date</label><input id="${prefix}-from" type="date" name="from" value="${esc(f.from||'')}"></div><div class="field"><label for="${prefix}-to">To date</label><input id="${prefix}-to" type="date" name="to" value="${esc(f.to||'')}"></div><button class="button secondary" type="submit">Apply dates</button></div></div></details>`;
}
export function recordToolbar(id,page,query,placeholder,controls,esc,icon,{queryName="query",clearAction="clear-filters",label="",attributes="",errorId="",clearLabel="Clear",primaryAction=""}={}){
 const directory=['employees','violations','types'].includes(page);
 const clear=directory?`<button class="icon-button record-clear-icon" type="button" data-action="${clearAction}" data-page="${page}" aria-label="Clear filters" title="Clear filters">${icon('refresh',18)}</button>`:'';
 const last=controls.lastIndexOf('<details class="record-filter"');
 const filters=directory?(last>=0?controls.slice(0,last)+'<div class="record-filter-reset-pair">'+controls.slice(last)+clear+'</div>':controls+clear):controls;
 return `<form id="${id}" class="record-toolbar ${directory?'record-toolbar-directory':''}" ${attributes} aria-label="${label|| (page==='types'?'Violation type':page==='employees'?'Employee':'Violation')} search and filters"><div class="record-search"><label class="sr-only" for="${page}-query">${esc(placeholder)}</label><button class="record-search-submit" type="submit" aria-label="Search ${label?label.toLowerCase():page==='types'?'violation types':page}">${icon('search',17)}</button><input id="${page}-query" name="${queryName}" type="search" value="${esc(query||'')}" placeholder="${esc(placeholder)}" autocomplete="off"></div><div class="record-filter-controls">${filters}</div><div class="record-toolbar-actions">${directory||primaryAction?primaryAction:`<button class="button ghost small" type="button" data-action="${clearAction}" data-page="${page}">${esc(clearLabel)}</button>`}</div>${errorId||page==='violations'?`<p id="${errorId||'filter-error'}" class="form-error" role="alert" hidden></p>`:''}</form>`;
}
export function handleRecordFilterToggle(event){
 const details=event.target;if(!details.matches?.('.record-filter')||!details.open)return;
 document.querySelectorAll('.record-filter[open]').forEach(other=>{if(other!==details)other.open=false;});
 const popup=details.querySelector('.record-filter-popup');popup.style.transform='';
 const rect=popup.getBoundingClientRect(),width=globalThis.innerWidth;
 const shift=rect.right>width-16?width-16-rect.right:rect.left<16?16-rect.left:0;
 if(shift)popup.style.transform=`translateX(${shift}px)`;
}
export function closeRecordFilters(target){
 document.querySelectorAll('.record-filter[open]').forEach(details=>{if(!details.contains(target))details.open=false;});
}
