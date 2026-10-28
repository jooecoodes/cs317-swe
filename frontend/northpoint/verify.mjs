import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=fileURLToPath(new URL('./',import.meta.url));
function list(folder){return fs.readdirSync(folder,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?list(path.join(folder,entry.name)):[path.join(folder,entry.name)]);}
const files=list(root),code=files.filter(file=>/\.(?:js|mjs)$/.test(file));
for(const file of code){const result=spawnSync(process.execPath,['--check',file],{encoding:'utf8',windowsHide:true});if(result.status!==0)throw new Error(result.stderr||'Syntax check failed: '+file);}
const sources=files.filter(file=>file.includes(path.sep+'src'+path.sep)&&file.endsWith('.js')).map(file=>fs.readFileSync(file,'utf8')).join('\n');
if(/\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|indexedDB|localStorage|sessionStorage)\b/.test(sources))throw new Error('The UI preview must not include network transport or browser persistence.');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
if(!html.includes("connect-src 'none'"))throw new Error('The standalone preview must block network connections.');
if(/(?:src|href)=["']https?:\/\//i.test(html))throw new Error('The preview must bundle its assets.');
if(!html.includes('Fictional records'))throw new Error('The preview needs its visible fiction notice.');
console.log(`Checked ${code.length} JavaScript files; no network/storage code; standalone assets and preview notice verified.`);
