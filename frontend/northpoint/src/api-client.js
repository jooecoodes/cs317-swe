import { dataSource } from './data-source.js';
const routes = [
  ['GET', /^\/employees$/], ['POST', /^\/employees$/],
  ['GET', /^\/employees\/\d+$/], ['PATCH', /^\/employees\/\d+$/], ['DELETE', /^\/employees\/\d+$/], ['POST', /^\/employees\/\d+\/(?:deactivate|reactivate)$/],
  ['GET', /^\/employees\/\d+\/violations$/], ['POST', /^\/employees\/\d+\/violations$/], ['POST', /^\/employees\/\d+\/violations\/clear$/],
  ['GET', /^\/violations\/recent$/], ['GET', /^\/violations\/\d+$/], ['PATCH', /^\/violations\/\d+$/], ['POST', /^\/violations\/\d+\/remove$/],
  ['GET', /^\/violation-removals(?:\/\d+)?$/], ['GET', /^\/activity\/(?:timeline|calendar|digest\/\d{4}-\d{2}-\d{2})$/],
  ['GET', /^\/violation-types(?:\/all|\/\d+)?$/], ['POST', /^\/violation-types$/], ['PATCH', /^\/violation-types\/\d+$/], ['DELETE', /^\/violation-types\/\d+$/], ['POST', /^\/violation-types\/\d+\/(?:activate|deactivate)$/]
];
export function apiId(value) {
  const id = String(value ?? '');
  if (!/^\d+$/.test(id) || !Number.isSafeInteger(Number(id)) || Number(id) < 1) throw new Error('The record has no valid backend ID. Refresh the list.');
  return id;
}
export function apiActor(value) {
  const actor = typeof value === 'string' ? value.trim() : '';
  if (!actor) throw new Error('Set your display name in Settings before saving.');
  if (/[^\x20-\x7e\u00a0-\u00ff]/.test(actor)) throw new Error('Your display name cannot be sent in X-Actor. Update it in Settings before saving.');
  return actor;
}

export async function apiRequest(path,{method='GET',query,body,actor,signal}={}) {
  if(!routes.some(([verb,route])=>method===verb&&route.test(path)))throw new Error('This action is not defined in the API contract.');
  if(signal?.aborted)throw new DOMException('Request cancelled.','AbortError');
  return dataSource.request({path,method,query:query||{},body,actor,signal});
}
export async function paginatedApi(path, { array = false, query = {}, ...options } = {}) {
  const items = [], seen = new Set();
  let offset = 0, expected = null;
  const limit = 50;
  for (let page = 0; page < 2000; page++) {
    const data = await apiRequest(path, { ...options, query: { ...query, limit, offset } });
    const chunk = array ? data : data?.items;
    if (!Array.isArray(chunk)) throw new Error('The API returned an unexpected list format. Please retry.');
    if (!array) {
      if (!Number.isInteger(data.total) || data.total < 0 || !Number.isInteger(data.limit) || data.limit < 1 || data.offset !== offset || expected !== null && expected !== data.total) throw new Error('The list changed or returned incomplete pagination. Please refresh.');
      expected = data.total;
    }
    for (const item of chunk) { const id = apiId(item?.id); if (seen.has(id)) throw new Error('The API returned repeated pages. Please refresh to get a complete list.'); seen.add(id); items.push(item); }
    if (array ? chunk.length < limit : items.length === expected) return items;
    if (!chunk.length || expected !== null && items.length > expected) throw new Error('The API returned an incomplete list. Please refresh.');
    offset += chunk.length;
  }
  throw new Error('The list could not be loaded completely. Narrow the request or try again.');
}
