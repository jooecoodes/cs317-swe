// Decorative shapes only: no made-up records or totals while API data is pending.
export function loadingSkeleton(layout = 'rows', label = 'records') {
  const safeLabel = String(label).replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  const line = (width = 'medium') => `<span class="skeleton-line ${width}"></span>`;
  const rows = (count = 5) => `<div class="skeleton-rows">${Array.from({length:count}, () => `<div class="skeleton-row"><span class="skeleton-avatar"></span><div>${line('long')}${line('short')}</div>${line('short')}</div>`).join('')}</div>`;
  const panel = content => `<div class="skeleton-panel"><div class="skeleton-heading">${line('medium')}</div>${content}</div>`;
  const metrics = count => `<div class="skeleton-metrics" style="--skeleton-columns:${count}">${Array.from({length:count}, () => `<div class="skeleton-metric">${line('medium')}${line('number')}${line('long')}</div>`).join('')}</div>`;
  const chart = panel('<div class="skeleton-chart"><span></span><span></span><span></span><span></span><span></span><span></span><span></span></div>');
  const filters = `<div class="skeleton-filter">${Array.from({length:4}, () => `<div>${line('short')}<span class="skeleton-input"></span></div>`).join('')}</div>`;
  const tabs = `<div class="skeleton-tabs">${Array.from({length:5}, () => line('short')).join('')}</div>`;
  let content;
  if (layout === 'dashboard') content = metrics(4) + chart + `<div class="skeleton-columns">${panel(rows(4))}${panel(rows(4))}</div>` + panel(rows(3));
  else if (layout === 'reports') content = tabs + metrics(3) + chart + `<div class="skeleton-circles">${Array.from({length:3}, () => panel('<div class="skeleton-ring"></div>')).join('')}</div>`;
  else if (layout === 'profile') content = panel(rows(1) + metrics(4)) + panel(filters) + panel(rows());
  else if (layout === 'form') content = `<div class="skeleton-form">${Array.from({length:4}, () => `<div>${line('medium')}<span class="skeleton-input"></span></div>`).join('')}</div>`;
  else if (['employees','violations','types'].includes(layout)) content = filters + panel(rows(6));
  else content = rows();
  return `<div class="loading-skeleton skeleton-${layout}" role="status" aria-live="polite" aria-busy="true"><span class="sr-only">Loading ${safeLabel}…</span><div aria-hidden="true">${content}</div></div>`;
}
