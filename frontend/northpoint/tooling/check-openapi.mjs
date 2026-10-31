// Generated snapshots are refreshed from the running services; no database access.
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {apiRoute} from '../src/api-routes.js';

const hrPaths=['/employees','/employees/1','/employees/1/deactivate','/employees/1/reactivate','/employees/1/violations','/employees/1/violations/clear','/violations/recent','/violations/1','/violations/1/remove','/violation-removals','/violation-removals/1','/activity/timeline','/activity/calendar','/activity/digest/2026-10-30','/violation-types','/violation-types/all','/violation-types/1','/violation-types/1/activate','/violation-types/1/deactivate'];
const photoPaths=['/photos','/photos/1','/photos/1/history','/photos/batch','/stats','/activity','/activity/digest','/activity/actors','/upload'];
function operation(schema,path,method){
 const template=Object.keys(schema.paths).find(pattern=>new RegExp('^'+pattern.replace(/\{[^}]+\}/g,'[^/]+')+'$').test(path)&&schema.paths[pattern][method.toLowerCase()]);
 return template&&schema.paths[template][method.toLowerCase()];
}
export function checkApiSchemas(hr,photos){
 let checked=0;
 for(const [schema,paths,service] of [[hr,hrPaths,'hr'],[photos,photoPaths,'photos']])for(const path of paths)for(const method of ['GET','POST','PATCH','DELETE']){
  try{apiRoute(path,method,service);}catch{continue;}
  assert.ok(operation(schema,path,method),`${service} ${method} ${path} is absent from generated OpenAPI`);checked++;
 }
 for(const [path,parameters] of [
  ['/activity',['q','actor','action','from_date','to_date','limit','offset']],
  ['/activity/digest',['q','actor','action','from_date','to_date','include_items']],
  ['/activity/actors',['from_date','to_date','q']],
  ['/photos/1/history',['limit','offset']]
 ]){
  const op=operation(photos,path,'GET'),query=op.parameters.filter(p=>p.in==='query').map(p=>p.name);
  for(const name of parameters)assert.ok(query.includes(name),`${path} does not support query parameter ${name}`);
 }
 const body=photos.paths['/photos/batch'].post.requestBody.content['application/json'].schema;
 const batch=photos.components.schemas[body.$ref.split('/').at(-1)];
 assert.ok(batch.required.includes('ids'));assert.equal(batch.properties.ids.maxItems,200);
 for(const [name,fields] of Object.entries({ActivityListResponse:['total','limit','offset','items'],DigestResponse:['from_date','to_date','total','summary','days'],PhotoHistoryResponse:['photo_id','photo_exists','total','items'],PhotoBatchResponse:['found','missing'],ActorListResponse:['actors']})){
  for(const field of fields)assert.ok(photos.components.schemas[name].required.includes(field),`${name}.${field} must be required`);
 }
 return checked;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const paths=process.argv.slice(2);
 const read=(name,index)=>JSON.parse(fs.readFileSync(paths[index]||new URL(`../tests/contracts/${name}-openapi.json`,import.meta.url),'utf8').replace(/^\uFEFF/,''));
 console.log(`Verified ${checkApiSchemas(read('app1',0),read('app2',1))} adapter operations and photo query/response contracts against generated OpenAPI.`);
}
