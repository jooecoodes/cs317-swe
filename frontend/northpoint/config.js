// Change only this URL to point Northpoint at another API server, then reload.
// Keep this file beside index.html. No rebuild is needed after changing it.
(() => {
  const BASE_URL = 'https://mushiness-parsnip-refining.ngrok-free.dev/app1/';

  const url = new URL(BASE_URL);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || /[\s;'"<>]/.test(url.href)) {
    throw new Error('Northpoint BASE_URL must be an HTTP(S) API address without credentials, a query or a fragment.');
  }
  url.pathname = url.pathname.replace(/\/+$/, '') + '/';
  globalThis.NORTHPOINT_CONFIG = Object.freeze({BASE_URL: url.href});

  // The connection policy follows the same URL, so changing servers needs one edit.
  if (typeof document !== 'undefined') {
    const meta = document.createElement('meta');
    meta.httpEquiv = 'Content-Security-Policy';
    meta.content = `default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: ${new URL('/app2/photos/',url).href}; font-src 'self' data:; connect-src 'self' ${url.href} ${new URL('/app2/',url).href} ${new URL('/auth/me',url).href}; object-src 'none'; base-uri 'none'; form-action 'none'`;
    document.head.appendChild(meta);
  }
})();
