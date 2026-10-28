// Read-only: compare this additive payload with a target checkout.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const source=fileURLToPath(new URL('./',import.meta.url));
if(!process.argv[2])throw new Error('Pass the existing backend checkout directory.');
const checkout=path.resolve(process.argv[2]);
if(!fs.statSync(checkout).isDirectory())throw new Error('Target must be a directory.');
function list(folder) {return fs.readdirSync(folder,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?list(path.join(folder,entry.name)):[path.join(folder,entry.name)]);}
const paths=list(source).map(file=>'frontend/northpoint/'+path.relative(source,file).split(path.sep).join('/'));
const collisions=paths.filter(file=>fs.existsSync(path.join(checkout,file)));
console.log(JSON.stringify({target:checkout,proposedFiles:paths.length,scope:'frontend/northpoint/',existingPaths:collisions,result:collisions.length?'Review overlaps before copying':'All proposed files are new; no existing files overlap'},null,2));
if(collisions.length)process.exitCode=1;
