// Allowed routes from the supplied references, plus the existing Calendar contract.
const routes=[
 ['GET',/^\/employees\/\d+\/violation-history$/],
 ['GET',/^\/employees\/\d+\/(?:offense-summary|totals)$/],
 ['GET',/^\/analytics\/(?:top-offenders|departments|subsections|activity|watchlist|clean-employees)$/],
 ['GET',/^\/violation-types\/\d+\/subsections$/],['POST',/^\/violation-types\/\d+\/subsections$/,true],
 ['GET',/^\/subsections\/\d+$/],['PATCH',/^\/subsections\/\d+$/,true],['DELETE',/^\/subsections\/\d+$/,true],
 ['POST',/^\/subsections\/\d+\/(?:activate|deactivate)$/,true],['PUT',/^\/subsections\/\d+\/penalties$/,true],
 ['GET',/^\/employees$/],['POST',/^\/employees$/,true],
 ['GET',/^\/employees\/\d+$/],['PATCH',/^\/employees\/\d+$/,true],['DELETE',/^\/employees\/\d+$/,true],
 ['POST',/^\/employees\/\d+\/(?:deactivate|reactivate)$/,true],
 ['GET',/^\/employees\/\d+\/violations$/],['POST',/^\/employees\/\d+\/violations$/,true],['POST',/^\/employees\/\d+\/violations\/clear$/,true],
 ['GET',/^\/violations\/recent$/],['GET',/^\/violations\/\d+$/],['PATCH',/^\/violations\/\d+$/,true],['POST',/^\/violations\/\d+\/remove$/,true],
 ['GET',/^\/violation-removals(?:\/\d+)?$/],['GET',/^\/activity\/(?:timeline|calendar|digest\/\d{4}-\d{2}-\d{2})$/],
 ['GET',/^\/violation-types(?:\/all|\/\d+)?$/],['POST',/^\/violation-types$/,true],['PATCH',/^\/violation-types\/\d+$/,true],['DELETE',/^\/violation-types\/\d+$/,true],['POST',/^\/violation-types\/\d+\/(?:activate|deactivate)$/,true]
];
export function isMobileAccessRoute(path, method) {
  if (method === 'POST' && /^\/employees\/[1-9]\d*\/mobile-access\/link$/.test(path)) return true;
  return ['GET', 'POST', 'PATCH'].includes(method) && /^\/employees\/[1-9]\d*\/mobile-access$/.test(path);
}

export function isLoginPasswordRoute(path, method) {
  return (method === 'GET' && /^\/employees\/[1-9]\d*\/login-account$/.test(path)) ||
    (method === 'PATCH' && /^\/employees\/[1-9]\d*\/password$/.test(path));
}

export function apiRoute(path,method,service='hr'){
 if (service === 'session') {
  if ((path === '/me' && method === 'GET') || isMobileAccessRoute(path, method) ||
      isLoginPasswordRoute(path, method)) return {actor: false};
  throw new Error('Unknown session endpoint.');
 }
 if(service==='tracking'){if(method==='GET'&&/^\/(?:devices|(?:live|route)\/[^/?#\s]+)$/.test(path))return {actor:false};throw new Error('This action is not defined in the tracking API contract.');}
 if(service==='photos'){
  const allowed=method==='GET'&&/^\/(?:photos(?:\/\d+(?:\/(?:history|download))?)?|stats|activity(?:\/(?:digest|actors|authors))?)$/.test(path)||method==='POST'&&(['/upload','/photos/batch','/photos/bulk-delete'].includes(path)||/^\/photos\/\d+\/rename$/.test(path))||['PATCH','DELETE'].includes(method)&&/^\/photos\/\d+$/.test(path);
  if(allowed)return {actor:method!=='GET'};
  throw new Error('This action is not defined in the photo API contract.');
 }
 if(service!=='hr')throw new Error('Unknown API service.');
 const row=routes.find(([verb,pattern])=>verb===method&&pattern.test(path));if(!row)throw new Error('This action is not defined in the API contract.');return {actor:row[2]===true};
}
export function validateActor(value){const actor=typeof value==='string'?value.trim():'';if(!actor)throw new Error('Sign in before saving changes.');if(/[\r\n\x00]/.test(actor))throw new Error('Your signed-in name contains invalid header characters. Contact your administrator.');return actor.normalize('NFKD').replace(/[^\x20-\x7e]/g,'').trim()||'unknown';}
