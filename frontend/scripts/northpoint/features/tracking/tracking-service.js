import {dataSource} from '../../state/data-source.js';
const validLocation=(lat,lon)=>Number.isFinite(lat)&&Math.abs(lat)<=90&&Number.isFinite(lon)&&Math.abs(lon)<=180;
export async function readTrackingDevices(signal){
 const raw=await dataSource.request({service:'tracking',path:'/devices',query:{include_offline:true},signal});
 if(!raw||!Array.isArray(raw.devices)||!Number.isSafeInteger(raw.count)||raw.count!==raw.devices.length)throw Error('The tracking service returned an invalid device list.');
 const ids=new Set();
 for(const d of raw.devices){
  if(typeof d.device_id!=='string'||!d.device_id.trim()||ids.has(d.device_id)||d.tracker!=null&&typeof d.tracker!=='string'||d.employee_name!=null&&typeof d.employee_name!=='string'||!['online','disconnected'].includes(d.status)||!validLocation(d.lat,d.lon)||!Number.isSafeInteger(d.last_seen_seconds_ago)||d.last_seen_seconds_ago<0||d.accuracy_m!=null&&(!Number.isFinite(d.accuracy_m)||d.accuracy_m<0))throw Error('The tracking service returned invalid device details.');
  ids.add(d.device_id);
 }
 return raw.devices;
}
function devicePath(kind,id){if(typeof id!=='string'||!id.trim()||['.','..'].includes(id)||id.length>200)throw Error('Enter a valid device ID.');return '/'+kind+'/'+encodeURIComponent(id);}
export async function readTrackingLocation(id,signal){
 const raw=await dataSource.request({service:'tracking',path:devicePath('live',id),signal});
 if(!raw||!['online','disconnected','not_connected'].includes(raw.status)||raw.status!=='not_connected'&&!validLocation(raw.lat,raw.lon))throw Error('The tracking service returned an invalid location.');
 return raw;
}
export async function readTrackingRoute(id,signal){
 const raw=await dataSource.request({service:'tracking',path:devicePath('route',id),signal});
 if(!raw||!Array.isArray(raw.segments)||raw.segments.some(segment=>!Array.isArray(segment)||segment.some(p=>!Array.isArray(p)||p.length!==2||!validLocation(p[0],p[1]))))throw Error('The tracking service returned an invalid route.');
 return raw.segments.filter(segment=>segment.length);
}
