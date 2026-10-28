// Fictional examples only. No employee data was copied from a real API/database.
// Relative dates keep the weekly chart useful whenever this UI is reviewed.
function dateBefore(days,hour=9) {
  const value=new Date();value.setDate(value.getDate()-days);value.setHours(hour,0,0,0);
  return value.toISOString();
}
const types=[
  {id:1,name:'Tardiness',description:'Arriving after the scheduled start of a shift.',default_points:2,is_strike:false,is_active:true},
  {id:2,name:'Safety procedure',description:'Not following an established workplace safety procedure.',default_points:5,is_strike:true,is_active:true},
  {id:3,name:'Unexcused absence',description:'An absence without the required notice or approval.',default_points:3,is_strike:true,is_active:true},
  {id:4,name:'Incomplete documentation',description:'Required work documentation was not completed.',default_points:1,is_strike:false,is_active:true},
  {id:5,name:'Archived category',description:'An inactive example retained for the rulebook preview.',default_points:1,is_strike:false,is_active:false}
];
const people=[
  ['Alex','Example','Operations','Coordinator'],['Mina','Sample','Administration','Assistant'],
  ['Riley','Example','Engineering','Technician'],['Sam','Sample','Operations','Associate'],
  ['Taylor','Example','Customer Support','Representative'],['Jamie','Sample','Administration','Clerk'],
  ['Morgan','Example','Engineering','Analyst'],['Casey','Sample','Customer Support','Coordinator'],
  ['Robin','Example','Operations','Associate'],['Drew','Sample','Engineering','Technician'],
  ['Avery','Example','Administration','Assistant'],['Jordan','Sample',null,null]
];
const employees=people.map(([first,last,department,position],index)=>({
  id:101+index,employee_code:`PREVIEW-${101+index}`,first_name:first,last_name:last,full_name:`${first} ${last}`,
  department,position,status:index>=10?'inactive':'active',total_points:0,total_strikes:0,
  created_at:dateBefore(60-index),updated_at:dateBefore(2)
}));
const violations=Array.from({length:19},(_,index)=>{
  const employee=index<3?employees[0]:employees[1+(index-3)%7];
  const type=index<3?types[1]:types[index%4];
  const issued=dateBefore(index<10?index:7+(index-10)*3);
  employee.total_points+=type.default_points;employee.total_strikes+=Number(type.is_strike);
  return {id:1001+index,employee_id:employee.id,violation_type_id:type.id,points:type.default_points,is_strike:type.is_strike,
    notes:'Fictional incident details for reviewing this interface.',issued_by:'Preview User',issued_at:issued,created_at:issued,
    violation_type:{id:type.id,name:type.name,default_points:type.default_points,is_strike:type.is_strike},violation_type_name:type.name};
});
const removals=[0,1].map((index)=>({id:301+index,violation_record_id:901+index,violation_type_id:1,violation_type_name:'Tardiness',points:2,is_strike:false,
  original_notes:'Fictional record used to preview the removal log.',employee_id:employees[index].id,employee_code:employees[index].employee_code,
  employee_full_name:employees[index].full_name,original_issued_by:'Preview User',original_issued_at:dateBefore(8+index),
  removed_by:'Preview User',reason:'Example record removed after reviewing a corrected attendance entry.',removed_at:dateBefore(index+1,14)}));
const activities=[
  ...employees.map((employee,index)=>({occurred_at:employee.created_at,actor:'Preview User',action:'employee.created',target_type:'employee',target_id:employee.id,employee_id:employee.id,
    summary:`Added ${employee.employee_code} (${employee.full_name})`,metadata_json:{employee_code:employee.employee_code,full_name:employee.full_name}})),
  ...violations.map(record=>{const employee=employees.find(employee=>employee.id===record.employee_id);return {occurred_at:record.issued_at,actor:'Preview User',action:'violation.assigned',target_type:'violation',target_id:record.id,employee_id:employee.id,
    summary:`Issued '${record.violation_type_name}' to ${employee.full_name}`,metadata_json:{employee_code:employee.employee_code,employee_full_name:employee.full_name,points:record.points,is_strike:record.is_strike}};}),
  ...removals.map(removal=>({occurred_at:removal.removed_at,actor:removal.removed_by,action:'violation.removed',target_type:'violation',target_id:removal.violation_record_id,employee_id:removal.employee_id,
    summary:`Removed '${removal.violation_type_name}' from ${removal.employee_full_name}`,metadata_json:{employee_code:removal.employee_code,employee_full_name:removal.employee_full_name,reason:removal.reason}})),
  {occurred_at:dateBefore(0,10),actor:'Preview User',action:'employee.updated',target_type:'employee',target_id:102,employee_id:102,summary:'Updated PREVIEW-102: position',metadata_json:{changes:{position:'Assistant'}}},
  {occurred_at:dateBefore(1,10),actor:'Preview User',action:'employee.deactivated',target_type:'employee',target_id:111,employee_id:111,summary:'Deactivated PREVIEW-111 (Avery Example)',metadata_json:{new_status:'inactive'}},
  {occurred_at:dateBefore(2,10),actor:'Preview User',action:'violation_type.updated',target_type:'violation_type',target_id:1,employee_id:null,summary:'Updated Tardiness description',metadata_json:{changes:{description:types[0].description}}}
].sort((a,b)=>Date.parse(b.occurred_at)-Date.parse(a.occurred_at)).map((event,index,rows)=>({...event,id:500+rows.length-index,event_date:event.occurred_at.slice(0,10)}));
export const previewFixtures={employees,violations,types,removals,activities};
