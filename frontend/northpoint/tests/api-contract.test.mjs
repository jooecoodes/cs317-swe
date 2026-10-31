import test from 'node:test';
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {checkApiSchemas} from '../tooling/check-openapi.mjs';
const schema=name=>JSON.parse(fs.readFileSync(new URL(`./contracts/${name}-openapi.json`,import.meta.url),'utf8').replace(/^\uFEFF/,''));
test('adapter operations and photo filters match generated backend OpenAPI',()=>{
 assert.equal(checkApiSchemas(schema('app1'),schema('app2')),38);
});
test('contract audit detects an unsupported backend route or renamed query field',()=>{
 const photos=schema('app2');delete photos.paths['/photos/batch'];
 assert.throws(()=>checkApiSchemas(schema('app1'),photos),/absent from generated/);
 const changed=schema('app2');changed.paths['/activity'].get.parameters=changed.paths['/activity'].get.parameters.filter(p=>p.name!=='actor');
 assert.throws(()=>checkApiSchemas(schema('app1'),changed),/query parameter actor/);
});
