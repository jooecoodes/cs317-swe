import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import './config.js';
const root=fileURLToPath(new URL('./',import.meta.url));
function list(folder){return fs.readdirSync(folder,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?list(path.join(folder,entry.name)):[path.join(folder,entry.name)]);}
const files=list(root),code=files.filter(file=>/\.(?:js|mjs)$/.test(file));
for(const file of code){const result=spawnSync(process.execPath,['--check',file],{encoding:'utf8',windowsHide:true});if(result.status!==0)throw new Error(result.stderr||'Syntax check failed: '+file);}
const sources=files.filter(file=>file.includes(path.sep+'src'+path.sep)&&file.endsWith('.js')).map(file=>fs.readFileSync(file,'utf8')).join('\n');
if(/\b(?:indexedDB|localStorage|sessionStorage)\b/.test(sources))throw new Error('Employee records must not be saved to browser storage.');
for(const file of files.filter(file=>file.includes(path.sep+'src'+path.sep)&&file.endsWith('.js')&&!file.endsWith(path.sep+'hosted-api.js'))){if(/\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\b/.test(fs.readFileSync(file,'utf8')))throw new Error('Network requests must go through hosted-api.js.');}
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
if(!html.includes('<script src="./config.js"></script>')||html.indexOf('<script src="./config.js"></script>')>html.indexOf('<script>'))throw new Error('Runtime configuration must load before the application.');
const config=fs.readFileSync(path.join(root,'config.js'),'utf8');
if(!config.includes("connect-src 'self' ${url.href} " ))throw new Error('The connection policy must follow the runtime API URL.');
if(html.includes('cs317.duckdns.org')||html.includes('http://localhost:8081/app1'))throw new Error('The generated page must not hard-code an API server. Edit config.js instead.');
if(html.includes('const previewFixtures')||html.includes('createPreviewProvider()'))throw new Error('The hosted employee build must not contain mock records or a fallback provider.');
if(/(?:src|href)=["']https?:\/\//i.test(html))throw new Error('The preview must bundle its assets.');
if(!html.includes("sourceLabel='v.FE-1.0'"))throw new Error('The frontend version label is missing.');
if(html.includes('UI preview · Fictional records · Record changes are disabled.')||html.includes('People. Clarity. Accountability.'))throw new Error('Removed branding text remains in the build.');
console.log(`Checked ${code.length} JavaScript files; runtime API configuration (${globalThis.NORTHPOINT_CONFIG.BASE_URL}), no mock records/browser persistence, bundled assets and version label verified.`);
