// Responsive presentation helpers; records and actions use the existing UI.
const PHONE_QUERY='(max-width:900px)';
let previousPhoneMode=null;

function positionDashboardActions(phone){
  const quick=document.querySelector('.dashboard-quick-actions'),metrics=document.querySelector('.dashboard-simple>.metrics-grid');
  if(!quick?.parentElement||quick.parentElement!==metrics?.parentElement)return;
  if(phone)metrics.before(quick);else metrics.after(quick);
}

export function enhancePhoneLayout({icon}) {
  const phone=matchMedia(PHONE_QUERY).matches;
  positionDashboardActions(phone);
  document.querySelectorAll('main table').forEach(table=>{
    if(table.dataset.phoneLayout==='table'||table.closest('.desktop-records'))return;
    table.classList.add('phone-table');
    table.setAttribute('role','table');
    const headers=[...table.querySelectorAll('thead th')].map(header=>header.textContent.replace(/\s+/g,' ').trim());
    table.querySelectorAll('thead,tbody').forEach(group=>group.setAttribute('role','rowgroup'));
    table.querySelectorAll('thead tr').forEach(row=>row.setAttribute('role','row'));
    table.querySelectorAll('thead th').forEach(header=>header.setAttribute('role','columnheader'));
    table.querySelectorAll('tbody tr').forEach(row=>{
      row.setAttribute('role','row');
      [...row.cells].forEach((cell,index)=>{
        cell.dataset.label=headers[index]||'';
        cell.setAttribute('role',cell.tagName==='TH'?'rowheader':'cell');
        if(index===0)cell.classList.add('phone-primary-cell');
        if(/^(action|actions|manage)$/i.test(headers[index]||''))cell.classList.add('phone-actions');
        const value=document.createElement('div');
        value.className='phone-cell-value';
        value.append(...cell.childNodes);
        cell.append(value);
      });
    });
  });
  document.querySelectorAll('#employee-filters,#violation-filters,#type-filters,#secondary-filter').forEach(form=>{
    if(form.closest('.phone-filters'))return;
    const count=[...form.elements].filter(field=>field.name&&!['button','submit','reset'].includes(field.type)&&!(field.name==='order'&&['desc','newest'].includes(field.value))&&(field.type==='checkbox'?field.checked:Boolean(field.value))).length;
    const disclosure=document.createElement('details');
    disclosure.className='phone-filters';
    disclosure.open=!phone;
    const summary=document.createElement('summary');
    summary.innerHTML=`${icon('filter',20)}<span>Search &amp; filters${count?` <span class="filter-count">${count} applied</span>`:''}</span><span class="filter-chevron">${icon('chevron-down',19)}</span>`;
    form.before(disclosure);
    disclosure.append(summary,form);
  });
  previousPhoneMode=phone;
}

export function syncPhoneFilters() {
  const phone=matchMedia(PHONE_QUERY).matches;
  positionDashboardActions(phone);
  if(phone!==previousPhoneMode){
    document.querySelectorAll('.phone-filters').forEach(details=>details.open=!phone);
    previousPhoneMode=phone;
  }
}
