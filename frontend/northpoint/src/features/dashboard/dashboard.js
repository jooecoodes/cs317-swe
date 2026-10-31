import { dashboardSummary, weeklyTotals, localDate, recentViolationActivity } from '../../shared/domain.js';

function shortDate(date) {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

function weeklyChart(weeks, esc) {
  const cap = Math.max(4, Math.ceil(Math.max(...weeks.map(week => week.count)) / 4) * 4);
  const summary = weeks.map(week => `${shortDate(week.start)} to ${shortDate(week.end)}: ${week.count} violations`).join('; ');
  let svg = `<svg class="weekly-trend-chart" viewBox="0 0 660 275" role="img" aria-label="Weekly violations, Monday to Sunday"><title>${esc(summary)}</title>`;
  for (let index = 0; index <= 4; index++) {
    const y = 204 - index * 42;
    svg += `<line x1="44" y1="${y}" x2="644" y2="${y}" class="chart-grid"/><text x="23" y="${y + 5}" text-anchor="middle">${index * cap / 4}</text>`;
  }
  weeks.forEach((week, index) => {
    const x = 62 + index * 99;
    const height = week.count / cap * 168;
    const color = week.current ? '#527ca9' : '#c4d6e9';
    svg += `<g tabindex="0" aria-label="${esc(shortDate(week.start))} to ${esc(shortDate(week.end))}: ${week.count} violations${week.current ? ', current week' : ''}"><title>${esc(shortDate(week.start))}–${esc(shortDate(week.end))}: ${week.count} violations</title><rect x="${x}" y="${204 - height}" width="48" height="${height}" rx="4" fill="${color}"/><text x="${x + 24}" y="${192 - height}" text-anchor="middle" class="bar-number">${week.count}</text><text x="${x + 24}" y="234" text-anchor="middle">${esc(shortDate(week.start))}</text><text x="${x + 24}" y="255" text-anchor="middle" class="week-end">– ${esc(shortDate(week.end))}</text></g>`;
  });
  const maximum=Math.max(1,...weeks.map(week=>week.count));
  const phone=`<div class="phone-weekly-chart" role="list" aria-label="Weekly violation totals">${weeks.map(week=>`<div class="phone-week" role="listitem"><div class="phone-week-heading"><span>${esc(shortDate(week.start))} – ${esc(shortDate(week.end))}${week.current?'<span class="phone-current-week">Current week</span>':''}</span><strong>${week.count}<span class="sr-only"> violations</span></strong></div><div class="phone-week-track" aria-hidden="true"><span style="width:${week.count/maximum*100}%;background:${week.current?'#527ca9':'#aec6df'}"></span></div></div>`).join('')}</div>`;
  return svg + '</svg>' + phone;
}

export function renderDashboard(ctx) {
  const { store, esc, icon, person, formatDate, badge, visibleEmployees, visibleViolations } = ctx;
  const employees = visibleEmployees();
  const violations = visibleViolations();
  const summary = dashboardSummary(employees, violations, store.removals);
  const weeks = weeklyTotals(violations, localDate());
  const recentActivity = (ctx.recentActivity || recentViolationActivity(violations)).filter(record => store.settings.role !== 'Supervisor' || employees.some(employee => employee.apiId === record.employeeApiId));
  const daysAgo = date => {
    const days = Math.round((Date.parse(localDate()) - Date.parse(String(date).slice(0, 10))) / 86400000);
    return days === 0 ? 'Today' : days === 1 ? 'Yesterday' : `${days} days ago`;
  };
  const cards = [
    ['Employees', summary.employees, 'users', '', 'Employee records', 'employees'],
    ['Total Violations', summary.violations, 'shield', 'rose', 'Retained violation records', 'violations'],
    ['Total Points', summary.points, 'clipboard', 'amber', 'Recorded demerit points', 'points'],
    ['Watchlist', summary.watchlist.length, 'alert', 'purple', 'Employees with 2 or more strikes', 'watchlist']
  ];
  const directoryReady=ctx.employeeDirectory?.status==='ready';
  const quickActions=[
    {label:'Issue Violation',icon:'shield',action:'record',disabled:!['HR','Supervisor'].includes(store.settings.role)||!directoryReady,hint:'Load employees before issuing a violation.'},
    {label:'Add Employee',icon:'users',action:'add-employee',disabled:store.settings.role!=='HR'||!directoryReady,hint:store.settings.role!=='HR'?'Available in the HR workspace view.':'Load employees before adding an employee.'},
    {label:'Timestamp Camera',icon:'camera',action:'navigate',page:'camera',disabled:false}
  ];
  return `<div class="dashboard-simple">
    <section class="metrics-grid" aria-label="Workplace overview"><h2 class="dashboard-summary-heading">Workplace overview</h2>${cards.map(card => `<article class="metric-card"><div class="metric-top"><span class="metric-title">${card[0]}</span><span class="metric-icon ${card[3]}">${icon(card[2], 20)}</span></div><div class="metric-number">${card[1]}</div>${ctx.renderYesterdayChange?ctx.renderYesterdayChange(ctx.comparison?.[card[5]==='employees'?'employees':card[5]==='violations'?'violations':card[5]],icon,ctx.comparison?.reason):''}<div class="metric-bottom">${card[4]}</div><button class="metric-card-link" data-action="dashboard-card" data-target="${card[5]}" aria-label="View ${card[0].toLowerCase()}"></button></article>`).join('')}</section>
    <section class="dashboard-quick-actions" aria-labelledby="dashboard-quick-title"><h2 id="dashboard-quick-title">What would you like to do?</h2><div class="dashboard-action-grid">${quickActions.map(item=>`<button class="dashboard-action-tile" data-action="${item.action}" ${item.page?'data-page="'+item.page+'"':''} ${item.disabled?'disabled title="'+item.hint+'"':''}><span class="dashboard-action-icon">${icon(item.icon,25)}</span><span>${item.label}</span></button>`).join('')}</div></section>
    <div class="dashboard-main-row">
      <section class="panel weekly-panel"><div class="panel-header"><div><h2>Violation Trends</h2><p>Weekly totals · Monday to Sunday</p></div><span class="period-label">Last 6 weeks</span></div><div class="weekly-chart-body">${weeklyChart(weeks, esc)}</div><div class="weekly-chart-footer"><span><i class="legend-dot light"></i> Weekly violations</span><span><i class="legend-dot"></i> Current week (last bar)</span></div></section>
      <section class="panel dashboard-activity-panel"><div class="panel-header"><div><h2>Recent Activity</h2><p>Last 14 days · Latest 5 violations</p></div></div>${ctx.recentState || (recentActivity.length ? `<div class="dashboard-activity-list">${recentActivity.map(violation => {
        const employee = employees.find(employee => employee.apiId ? employee.apiId === violation.employeeApiId : employee.id === violation.employeeId) || violation.employee;
        const initials = employee.name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('');
        return `<button class="dashboard-activity-item" data-action="case-details" data-id="${esc(violation.id)}"><span class="avatar" aria-hidden="true">${esc(initials)}</span><span class="dashboard-activity-content"><span class="dashboard-activity-title"><strong>${esc(employee.name)}</strong>${violation.strike ? '<span class="pill danger">Strike</span>' : ''}</span><span class="dashboard-activity-detail">${esc(violation.typeName)} · +${violation.points} pts</span></span><span class="dashboard-activity-time">${daysAgo(violation.date)}</span></button>`;
      }).join('')}</div>` : `<div class="empty-state">${icon('clock', 28)}<h3>No recent violations</h3><p>Violations issued in the last 14 days will appear here.</p></div>`)}<div class="panel-link-footer"><button class="button ghost" data-action="navigate" data-page="history">View History ${icon('arrow', 17)}</button></div></section>
    </div>
    <p class="dashboard-totals-note">Totals cover the returned employee directory and its retained violations. Removed records are excluded.</p>
  </div>`;
}
