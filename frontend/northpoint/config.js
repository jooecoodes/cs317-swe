// Leave blank to use the server hosting this page. Set an absolute URL only
// when explicitly configuring another server. Reload after editing this file.

(() => {
  const BASE_URL = '';

  const origin = globalThis.location?.origin || (typeof document === 'undefined' ? 'http://localhost:8081' : '');
  if (!BASE_URL && !/^https?:\/\//.test(origin)) {
    throw new Error('Open Northpoint through the signed-in HTTP server, not directly from a file.');
  }
  const url = new URL(BASE_URL || new URL('/app1/', origin).href);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || /[\s;'"<>]/.test(url.href)) {
    throw new Error('Northpoint BASE_URL must be an HTTP(S) API address without credentials, a query or a fragment.');
  }
  url.pathname = url.pathname.replace(/\/+$/, '') + '/';
  globalThis.NORTHPOINT_CONFIG = Object.freeze({BASE_URL: url.href});


  if (typeof document !== 'undefined') {
    const meta = document.createElement('meta');
    meta.httpEquiv = 'Content-Security-Policy';
    meta.content = `default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: ${new URL('/app2/photos/',url).href}; font-src 'self' data:; connect-src 'self' ${url.href} ${new URL('/app2/',url).href} ${new URL('/auth/me',url).href}; object-src 'none'; base-uri 'none'; form-action 'none'`;
    document.head.appendChild(meta);
  }
})();
