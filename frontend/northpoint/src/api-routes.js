// Allowed routes from the supplied references, plus the existing Calendar contract.
const routes=[
 ['GET',/^\/employees$/],['POST',/^\/employees$/,true],
 ['GET',/^\/employees\/\d+$/],['PATCH',/^\/employees\/\d+$/,true],['DELETE',/^\/employees\/\d+$/,true],
 ['POST',/^\/employees\/\d+\/(?:deactivate|reactivate)$/,true],
 ['GET',/^\/employees\/\d+\/violations$/],['POST',/^\/employees\/\d+\/violations$/,true],['POST',/^\/employees\/\d+\/violations\/clear$/],
 ['GET',/^\/violations\/recent$/],['GET',/^\/violations\/\d+$/],['PATCH',/^\/violations\/\d+$/,true],['POST',/^\/violations\/\d+\/remove$/],
 ['GET',/^\/violation-removals(?:\/\d+)?$/],['GET',/^\/activity\/(?:timeline|calendar|digest\/\d{4}-\d{2}-\d{2})$/],
 ['GET',/^\/violation-types(?:\/all|\/\d+)?$/],['POST',/^\/violation-types$/,true],['PATCH',/^\/violation-types\/\d+$/,true],['DELETE',/^\/violation-types\/\d+$/,true],['POST',/^\/violation-types\/\d+\/(?:activate|deactivate)$/,true]
];
export function apiRoute(path,method){const row=routes.find(([verb,pattern])=>verb===method&&pattern.test(path));if(!row)throw new Error('This action is not defined in the API contract.');return {actor:row[2]===true};}
export function validateActor(value){const actor=typeof value==='string'?value.trim():'';if(!actor)throw new Error('Set your display name in Settings before saving.');if(/[^\x20-\x7e\u00a0-\u00ff]/.test(actor))throw new Error('Your display name cannot be sent in X-Actor. Update it in Settings before saving.');return actor;}
