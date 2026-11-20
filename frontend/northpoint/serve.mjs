// Optional local static server. Authenticated deployments serve frontend/ through Nginx.
import http from 'node:http';
import {readFile} from 'node:fs/promises';

const preview = (process.argv.includes('--rbac-preview') || process.argv.includes('--mobile-access-testing')) ? await import('./dev/rbac-preview.mjs') : null;
const port = Number(process.env.PORT ?? (preview ? 4175 : 4173));
const host = preview ? '127.0.0.1' : process.env.HOST || '127.0.0.1';
const root = new URL('../', import.meta.url);
const contentTypes = {
  html:'text/html; charset=utf-8', js:'text/javascript; charset=utf-8',
  css:'text/css; charset=utf-8', png:'image/png', jpg:'image/jpeg', woff2:'font/woff2'
};
const role = /^(hr|supervisor|c_manager|employee)(?:\/|\/index\.html)?$/;
const entry = /^(?:index\.html|northpoint\/(?:index|login|camera)\.html|northpoint\/src\/index\.html)$/;
const asset = /^(?:css|scripts)\/(?:[a-z0-9_-]+\/)*[a-z0-9_.-]+\.(?:js|css|png|jpg|woff2)$/i;

const server = http.createServer(async (request, response) => {
  if (preview && request.headers.host !== '127.0.0.1:' + server.address().port) {
    response.writeHead(403).end('Open the preview using its local 127.0.0.1 address.');
    return;
  }
  const url = new URL(request.url, 'http://localhost');
  const current = preview?.previewRole(request);
  if (await preview?.handlePreviewRequest(request, response, url, current)) return;

  let file = url.pathname.slice(1) || 'index.html';
  const workspace = file.match(role)?.[1];
  if (workspace) {
    const index = workspace + '/index.html';
    if (file !== index) {
      response.writeHead(302, {Location:'/' + index + url.search}).end();
      return;
    }
  } else if (['northpoint','northpoint/','login.html','camera.html'].includes(file)) {
    file = file.startsWith('northpoint') ? 'northpoint/index.html' : 'northpoint/' + file;
  }

  if (!['GET', 'HEAD'].includes(request.method) || (!workspace && !entry.test(file) && !asset.test(file))) {
    response.writeHead(404).end('Not found');
    return;
  }
  try {
    let data = await readFile(new URL(file, root));
    if (preview && workspace) data = preview.previewPage(file, data.toString('utf8'), current);
    response.writeHead(200, {'Content-Type':contentTypes[file.split('.').at(-1)], 'Cache-Control':'no-store'});
    response.end(request.method === 'HEAD' ? undefined : data);
  } catch {
    response.writeHead(404).end('Not found');
  }
});

server.listen(port, host, () => {
  const url = 'http://' + host + ':' + server.address().port + '/';
  console.log(preview ? 'Development-only RBAC preview at ' + url : 'Static preview at ' + url + ' — use the backend server for authenticated workspaces.');
});
