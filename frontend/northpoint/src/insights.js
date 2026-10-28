import { analyticsData, historyEvents } from './insight-data.js';
import { renderHistoryCalendar } from './calendar.js';

const reportTabs = [['activity', 'Activity'], ['offenders', 'Top Offenders'], ['watchlist', 'Watchlist'], ['departments', 'Departments'], ['rulebook', 'Rulebook Usage'], ['clean', 'Clean Employees']];
const colors = ['#527ca9', '#5b9788', '#c19549', '#8a7baa', '#b86d78', '#528f9f', '#777c85'];
function empty(title, detail = 'There are no matching records in this view.') { return `<div class="empty-state"><h3>${title}</h3><p>${detail}</p></div>`; }
function profileName(employee, esc) { return `<button class="text-button report-person" data-action="profile" data-id="${esc(employee.profileId || employee.id)}">${esc(employee.name)}</button>`; }
function tablePanel(title, description, headers, rows, ctx, wide = false) {
  return `<section class="panel report-table-panel"><div class="panel-header"><div><h2>${title}</h2><p>${description}</p><span class="horizontal-scroll-hint">Swipe left or right to see all columns</span></div></div>${rows.length ? `<div class="table-wrap report-table-scroll ${wide ? 'wide' : ''}" role="region" tabindex="0" aria-label="${title} table"><table data-phone-layout="table"><thead><tr>${headers.map(header => `<th scope="col">${header}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : empty('No records to display')}</section>`;
}
function percentagePanel(title, items, esc, {unit = 'violation', includeZero = false, description = ''} = {}) {
  const values = items.filter(item => includeZero || item.value > 0);
  const total = values.reduce((sum, item) => sum + item.value, 0);
  let cursor = 0;
  const slices = values.map((item, index) => {
    const start = cursor; cursor += item.value / total * 100;
    return `${colors[index % colors.length]} ${start}% ${cursor}%`;
  });
  const label = values.map(item => `${item.label}: ${item.value}, ${(item.value / total * 100).toFixed(1)} percent`).join('; ');
  return `<section class="panel percentage-panel"><div class="panel-header"><div><h2>${title}</h2>${description?`<p>${esc(description)}</p>`:''}</div></div>${total ? `<div class="percentage-body"><div class="percentage-ring" role="img" aria-label="${esc(label)}" style="background:conic-gradient(${slices.join(',')})"><div><strong>${total}</strong><span>${unit}s</span></div></div><ul class="percentage-legend">${values.map((item, index) => `<li><span class="percentage-swatch" aria-hidden="true" style="background:${colors[index % colors.length]}"></span><span class="percentage-label">${esc(item.label)}<small>${item.value} ${unit}${item.value===1?'':'s'}</small></span><strong>${(item.value / total * 100).toFixed(1)}%</strong></li>`).join('')}</ul></div>` : empty(unit==='employee'?'No employees returned':'No violations in this period')}</section>`;
}
function dailyChart(data, esc, formatDate) {
  const max = Math.max(4, Math.ceil(Math.max(0, ...data.daily.map(day => day.count)) / 4) * 4);
  const width = 900, left = 40, plot = 836, base = 186;
  const step = plot / data.days;
  const description = `${data.events} violations from ${formatDate(data.from)} to ${formatDate(data.today)}. ${data.daily.map(day => `${day.date}: ${day.count}`).join('; ')}`;
  let svg = `<svg class="report-daily-chart" viewBox="0 0 ${width} 238" role="img" aria-label="${esc(description)}"><title>Daily violation activity</title>`;
  for (let index = 0; index <= 4; index++) {
    const y = base - index * 39;
    svg += `<line x1="${left}" x2="880" y1="${y}" y2="${y}" class="chart-grid"/><text x="23" y="${y + 5}" text-anchor="middle">${Math.round(max * index / 4)}</text>`;
  }
  data.daily.forEach((day, index) => {
    const h = day.count / max * 156;
    svg += `<g><title>${esc(formatDate(day.date))}: ${day.count} violations</title><rect x="${left + index * step + step * .18}" y="${base - h}" width="${Math.max(2, step * .64)}" height="${h || 2}" rx="2" fill="${day.count ? '#527ca9' : '#e2eaf4'}"/>${day.count && data.days <= 30 ? `<text class="daily-bar-value" x="${left + index * step + step / 2}" y="${base - h - 7}" text-anchor="middle">${day.count}</text>` : ''}</g>`;
  });
  const short = date => new Date(`${date}T12:00:00Z`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
  for (const index of [...new Set([0, Math.floor((data.days - 1) / 2), data.days - 1])]) svg += `<text x="${left + index * step + step / 2}" y="219" text-anchor="${index === 0 ? 'start' : index === data.days - 1 ? 'end' : 'middle'}">${esc(short(data.daily[index].date))}</text>`;
  return `<section class="panel daily-activity-panel"><div class="panel-header"><div><h2>Daily Activity</h2><p>${formatDate(data.from)} – ${formatDate(data.today)}</p><span class="horizontal-scroll-hint">Swipe to explore the chart</span></div></div><div class="daily-chart-scroll" tabindex="0" role="region" aria-label="Daily violation chart">${svg}</svg></div></section>`;
}

export function renderReports(ctx) {
  const { esc, store, visibleEmployees, visibleViolations, formatDate } = ctx;
  const f = ctx.getFilters('reports');
  const tab = reportTabs.some(([id]) => id === f.tab) ? f.tab : 'activity';
  const data = analyticsData(visibleEmployees(), visibleViolations(), store.types, f.days);
  let content = '';
  if (tab === 'activity') {
    content = `<div class="report-period-row"><p>Activity in the selected period</p><div class="field"><label for="report-period">Time period</label><select id="report-period">${[7, 30, 90].map(days => `<option value="${days}" ${data.days === days ? 'selected' : ''}>Last ${days} days</option>`).join('')}</select></div></div>
      <div class="activity-metrics">${[['Events', data.events, `Last ${data.days} days`], ['Points', data.points, 'Demerit points issued'], ['Daily Average', data.dailyAverage.toFixed(2), 'Violations per day']].map(([label, value, detail]) => `<article class="metric-card"><span class="metric-title">${label}</span><strong class="metric-number">${value}</strong><span class="metric-bottom">${detail}</span></article>`).join('')}</div>
      ${dailyChart(data, esc, formatDate)}<div class="percentage-grid">${percentagePanel('Violations by Department', data.byDepartment, esc)}${percentagePanel('Most Common Violations', data.byType, esc)}${percentagePanel('Employee Status', data.employeeStatus, esc, {unit:'employee',includeZero:true,description:'Active and inactive employees · Current directory'})}</div>`;
  } else if (tab === 'offenders') {
    content = tablePanel('Top Offenders', 'All recorded violations · Highest points first', ['Name', 'Points'], data.topOffenders.map(employee => [profileName(employee, esc), `<strong>${employee.points}</strong>`]), ctx);
  } else if (tab === 'watchlist') {
    content = `<section class="panel"><div class="panel-header"><div><h2>Watchlist</h2><p>Employees with 2 or more strikes · All recorded violations</p></div></div>${data.watchlist.length ? `<div class="report-name-list">${data.watchlist.map(employee => `<button class="name-entry" data-action="profile" data-id="${esc(employee.profileId || employee.id)}">${esc(employee.name)}</button>`).join('')}</div>` : empty('No employees on the watchlist')}</section>`;
  } else if (tab === 'departments') {
    content = tablePanel('Department Rollup', 'All recorded violations · Totals by department', ['Department', 'Employees', 'Violations', 'Points', 'Strikes'], data.departments.map(department => [esc(department.name), department.employees, department.violations, `<strong>${department.points}</strong>`, department.strikes]), ctx, true);
  } else if (tab === 'rulebook') {
    content = tablePanel('Rulebook Usage', 'All recorded violations · Default points reflect the current rulebook', ['Violation', 'Default Points', 'Strike', 'Issued', 'Total Points'], data.usage.map(type => [esc(type.name), type.points ?? '—', type.strike ? 'Yes' : 'No', type.issued, `<strong>${type.totalPoints}</strong>`]), ctx, true);
  } else {
    content = tablePanel('Clean Employees', 'Employees with 0 recorded violations across their full history', ['Name', 'Department'], data.cleanEmployees.map(employee => [profileName(employee, esc), esc(employee.department || 'Unassigned')]), ctx);
  }
  return `<div class="report-tabs-container"><div class="tabs report-tabs" role="tablist" aria-label="Report sections">${reportTabs.map(([id, label]) => `<button id="report-tab-${id}" class="tab ${tab === id ? 'active' : ''}" role="tab" aria-selected="${tab === id}" aria-controls="report-panel" tabindex="${tab === id ? 0 : -1}" data-action="sec-report-tab" data-tab="${id}">${label}</button>`).join('')}</div><p class="report-tabs-hint">Swipe to see all report tabs</p></div><div id="report-panel" role="tabpanel" aria-labelledby="report-tab-${tab}">${content}</div><p class="report-scope-note">Reports cover the returned employee directory and its retained violations. Removed records are excluded. Employee Status counts all active and inactive employees in this view, regardless of the activity period.</p>`;
}

export function renderHistory(ctx) {
  const {esc,icon,formatDate}=ctx;
  const f=ctx.getFilters('history'), tab=['removals','calendar'].includes(f.tab)?f.tab:'activity', isRemoval=tab==='removals';
  const tabs=`<div class="report-tabs-container history-tabs-container"><div class="tabs report-tabs history-tabs" role="tablist" aria-label="History sections">${[['activity','Activity Logs'],['removals','Removal Logs'],['calendar','Calendar']].map(([id,label])=>`<button id="history-tab-${id}" class="tab ${tab===id?'active':''}" role="tab" aria-selected="${tab===id}" aria-controls="history-log-panel" tabindex="${tab===id?0:-1}" data-action="sec-history-tab" data-tab="${id}">${label}</button>`).join('')}</div></div>`;
  if(tab==='calendar')return tabs+renderHistoryCalendar(ctx);
  const resource=ctx.resources[isRemoval?'removals':'timeline'];
  const all=historyEvents(ctx.store,ctx.visibleEmployees(),ctx.visibleViolations(),{tab});
  const events=historyEvents(ctx.store,ctx.visibleEmployees(),ctx.visibleViolations(),{...f,tab});
  const current=Math.min(Math.max(1,Number.parseInt(f.page,10)||1),Math.max(1,Math.ceil(events.length/6)));
  const rows=events.slice((current-1)*6,current*6);
  const labels={employee:'Employee changes',violation:'Violation changes',violation_type:'Violation type changes'};
  const categories=[...new Map(all.map(event=>[event.category,isRemoval?event.typeName:labels[event.category]||String(event.category).replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase())])).entries()].sort((a,b)=>a[1].localeCompare(b[1]));
  const timestamp=value=>`<time datetime="${esc(value)}">${formatDate(value)}<span class="history-cell-secondary">${esc(new Date(value).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',second:'2-digit'}))}</span></time>`;
  const employeeCell=event=>`${event.profileId?`<button class="text-button report-person" data-action="profile" data-id="${esc(event.profileId)}">${esc(event.employeeName)}</button>`:`<strong>${esc(event.employeeName||event.targetLabel||'Not provided')}</strong>`}${event.employeeId?`<span class="history-cell-secondary">${esc(event.employeeId)}</span>`:''}${!isRemoval&&event.targetLabel&&event.employeeName?`<span class="history-cell-secondary">${esc(event.targetLabel)}</span>`:''}`;
  const changeDetails=event=>{
    const changes=event.metadata?.changes;
    if(!changes||typeof changes!=='object'||Array.isArray(changes))return '';
    return `<span class="history-cell-secondary history-change-details">${Object.entries(changes).map(([key,value])=>esc(key.replaceAll('_',' '))+': '+esc(typeof value==='string'?value:JSON.stringify(value))).join(' · ')}</span>`;
  };
  const headers=isRemoval?['Removed at','Employee','Violation / Case','Points','Strike','Removed by','Reason for removal']:['Date & Time','Action','Employee / Record','Changed by','Details'];
  const tableRows=rows.map(event=>isRemoval?[
    timestamp(event.date),employeeCell(event),`<strong>${esc(event.typeName)}</strong><span class="history-cell-secondary">Case #${esc(event.violationId)}</span>`,event.points,event.strike?'Yes':'No',esc(event.actor||'Not provided'),esc(event.notes||'Not provided')
  ]:[timestamp(event.date),`<strong>${esc(event.title)}</strong>`,employeeCell(event),esc(event.actor||'Not provided'),esc(event.detail||'No summary provided')+changeDetails(event)+(event.notes&&!event.detail?.includes(event.notes)?`<span class="history-cell-secondary">Reason: ${esc(event.notes)}</span>`:'')]);
  const title=isRemoval?'Removal Logs':'Activity Logs';
  const content=resource.status!=='ready'?ctx.resourceState(resource,isRemoval?'removal logs':'activity logs'):rows.length?`<div class="table-wrap history-table-scroll" role="region" tabindex="0" aria-labelledby="history-table-title" aria-describedby="history-scroll-hint"><table class="history-table ${isRemoval?'history-removal-table':'history-activity-table'}" data-phone-layout="table"><caption class="sr-only">${title} · Newest first</caption><thead><tr>${headers.map(header=>`<th scope="col">${header}</th>`).join('')}</tr></thead><tbody>${tableRows.map(cells=>`<tr>${cells.map(cell=>`<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:empty(isRemoval?'No violation removals found':'No activity found','Try another category or a wider date range.');
  return `${tabs}
    <section class="panel"><form id="secondary-filter" class="filters history-filters" data-filter-page="history">
      <div class="field"><label for="history-search">Search ${isRemoval?'removals':'activity'}</label><input id="history-search" name="query" placeholder="Name, employee code, or details" value="${esc(f.query||'')}"></div>
      <div class="field"><label for="history-category">${isRemoval?'Violation type':'Category'}</label><select id="history-category" name="category"><option value="">${isRemoval?'All violation types':'All changes'}</option>${categories.map(([id,label])=>`<option value="${esc(id)}" ${f.category===id?'selected':''}>${esc(label)}</option>`).join('')}</select></div>
      <div class="field"><label for="history-from">From date</label><input id="history-from" type="date" name="from" value="${esc(f.from||'')}"></div><div class="field"><label for="history-to">To date</label><input id="history-to" type="date" name="to" value="${esc(f.to||'')}"></div>
      <div class="filter-actions"><button type="button" class="button ghost" data-action="sec-filter-clear" data-page="history">Clear Filters</button><button type="submit" class="button primary">${icon('search',17)} Search</button></div><p id="secondary-filter-error" class="form-error" role="alert" hidden></p>
    </form></section>
    <section id="history-log-panel" class="panel history-panel" role="tabpanel" aria-labelledby="history-tab-${tab}" aria-busy="${resource.status==='loading'||resource.status==='idle'}"><div class="panel-header"><div><h2 id="history-table-title">${title} <span class="count-label">${resource.status==='ready'?events.length+' records':resource.status==='error'?'Unavailable':'Loading…'}</span></h2><p>${isRemoval?'Employee violation removals only':'All recorded changes'}</p><span id="history-scroll-hint" class="history-scroll-hint">Swipe left or right to see all columns</span></div><span class="muted">Newest first</span></div>${content}${resource.status==='ready'?ctx.pagination(events.length,current,6,'history'):''}</section>`;
}
