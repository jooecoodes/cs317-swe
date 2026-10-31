// Rebuild the bundled HTML. Runtime API settings stay in the adjacent config.js.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const project = fileURLToPath(new URL('./', import.meta.url));
const source = path.join(project, 'src');
const read = name => fs.readFileSync(path.join(source, name), 'utf8');
const withoutExports = content => content.replace(/^import .*?;\s*$/gm, '').replace(/\bexport\s+(?=(?:async\s+)?(?:function|const|let)\b)/g, '');
const favicon = 'data:image/png;base64,' + fs.readFileSync(path.join(source,'assets/company-logo.png')).toString('base64');
let styles = read('styles.css')+'\n'+read('photos.css')+'\n'+read('compact-records.css');
for (const name of ['dm-sans-latin-ext.woff2', 'dm-sans-latin.woff2']) {
  const encoded = fs.readFileSync(path.join(source, 'assets/fonts', name)).toString('base64');
  styles = styles.replaceAll(`./assets/fonts/${name}`, `data:font/woff2;base64,${encoded}`);
}
let script = `const {calendarDate,calendarRange,calendarRows,calendarSummary}=(()=>{
${withoutExports(read('calendar-contract.js'))}
return {calendarDate,calendarRange,calendarRows,calendarSummary};})();\n`;
script += `const {validCalendarDate,calendarMonthBounds,shiftCalendarMonth,calendarCells,calendarActionLabel,previewCalendarRows,previewDailyDigest,validateDailyDigest}=(()=>{
${withoutExports(read('calendar-data.js'))}
return {validCalendarDate,calendarMonthBounds,shiftCalendarMonth,calendarCells,calendarActionLabel,previewCalendarRows,previewDailyDigest,validateDailyDigest};})();
`;
script += `const {apiRoute,validateActor}=(()=>{
${withoutExports(read('api-routes.js'))}
return {apiRoute,validateActor};})();\n`;
script += `const {API_BASE_URL,createHostedApiProvider}=(()=>{
${withoutExports(read('hosted-api.js'))}
return {API_BASE_URL,createHostedApiProvider};})();\n`;
script += `const {dataSource,sourceLabel,sourceNotice}=(()=>{
${withoutExports(read('data-source.js'))}
return {dataSource,sourceLabel,sourceNotice};})();
`;
script += `const {VIOLATION_STATUSES,normalizeViolationStatus,violationStatusLabel,localDate,startOfWeek,weeklyTotals,dashboardSummary,recentViolationActivity}=(()=>{\n${withoutExports(read('domain.js'))}\nreturn {VIOLATION_STATUSES,normalizeViolationStatus,violationStatusLabel,localDate,startOfWeek,weeklyTotals,dashboardSummary,recentViolationActivity};})();\n`;
script += `const {loadingSkeleton}=(()=>{\n${withoutExports(read('loading.js'))}\nreturn {loadingSkeleton};})();\n`;
script += `const {apiId,apiActor,apiRequest,paginatedApi}=(()=>{\n${withoutExports(read('api-client.js'))}\nreturn {apiId,apiActor,apiRequest,paginatedApi};})();\n`;
script += `const {normalizeApiEmployee,employeeDirectory,loadEmployeeDirectory,suspendEmployeeDirectory,apiEmployeeSummary,nextApiEmployeeCode,employeeCodeKey,fetchEmployeeDirectorySnapshot,employeeCreatePayload,employeeMatchesCreation,createApiEmployee}=(()=>{\n${withoutExports(read('employee-api.js'))}\nreturn {normalizeApiEmployee,employeeDirectory,loadEmployeeDirectory,suspendEmployeeDirectory,apiEmployeeSummary,nextApiEmployeeCode,employeeCodeKey,fetchEmployeeDirectorySnapshot,employeeCreatePayload,employeeMatchesCreation,createApiEmployee};})();\n`;
script += `const {store,saveStore,employeeSummary,visibleEmployees,visibleViolations}=(()=>{\n${withoutExports(read('data.js'))}\nreturn {store,saveStore,employeeSummary,visibleEmployees,visibleViolations};})();\n`;
script += `const {resources,watchBackend,refreshEmployees,refreshWorkspace,ensurePageData,loadRecords,loadTypes,loadActiveTypes,loadRecent,loadTimeline,loadRemovals,normalizeViolation,normalizeType}=(()=>{\n${withoutExports(read('backend.js'))}\nreturn {resources,watchBackend,refreshEmployees,refreshWorkspace,ensurePageData,loadRecords,loadTypes,loadActiveTypes,loadRecent,loadTimeline,loadRemovals,normalizeViolation,normalizeType};})();\n`;
script += `const {employeeProfile,fetchEmployeeProfile,loadEmployeeProfile,invalidateEmployeeProfile,employeeUpdatePayload,employeeMatchesUpdate,patchEmployee,changeEmployeeState}=(()=>{\n${withoutExports(read('employee-details.js'))}\nreturn {employeeProfile,fetchEmployeeProfile,loadEmployeeProfile,invalidateEmployeeProfile,employeeUpdatePayload,employeeMatchesUpdate,patchEmployee,changeEmployeeState};})();\n`;
script += `const {submitApiEmployeeForm,employeeCreateInFlight,pendingEmployeeCreation}=(()=>{\n${withoutExports(read('employee-create.js'))}\nreturn {submitApiEmployeeForm,employeeCreateInFlight,pendingEmployeeCreation};})();\n`;
script += `const {mutationInFlight,pendingMutation,runMutation,checkPendingMutation,saveType,changeType,issueViolation,updateViolation,deleteViolation}=(()=>{\n${withoutExports(read('mutations.js'))}\nreturn {mutationInFlight,pendingMutation,runMutation,checkPendingMutation,saveType,changeType,issueViolation,updateViolation,deleteViolation};})();\n`;
script += `const {sortEmployeeRecords,analyticsData,historyEvents}=(()=>{\n${withoutExports(read('insight-data.js'))}\nreturn {sortEmployeeRecords,analyticsData,historyEvents};})();\n`;
script += `const {recordChoice,recordDateFilter,recordToolbar,handleRecordFilterToggle,closeRecordFilters}=(()=>{\n${withoutExports(read('record-ui.js'))}\nreturn {recordChoice,recordDateFilter,recordToolbar,handleRecordFilterToggle,closeRecordFilters};})();\n`;
script += `const {employeeCreationTime,isNewEmployee,employeeDateErrors,retryEmployeeDates,ensureEmployeeDates}=(()=>{\n${withoutExports(read('employee-new.js'))}\nreturn {employeeCreationTime,isNewEmployee,employeeDateErrors,retryEmployeeDates,ensureEmployeeDates};})();\n`;
script += `const {renderEmployees,renderViolations,renderTypesList,employeeLoadState}=(()=>{\n${withoutExports(read('records.js'))}\nreturn {renderEmployees,renderViolations,renderTypesList,employeeLoadState};})();\n`;
script += `const {renderReports,renderHistory}=(()=>{\n${withoutExports(read('insights.js'))}\nreturn {renderReports,renderHistory};})();\n`;
script += `const {renderSecondary,handleSecondary}=(()=>{\n${withoutExports(read('secondary.js'))}\nreturn {renderSecondary,handleSecondary};})();\n`;
script += `const {renderDashboard}=(()=>{\n${withoutExports(read('dashboard.js'))}\nreturn {renderDashboard};})();\n`;
script += `const {enhancePhoneLayout,syncPhoneFilters}=(()=>{\n${withoutExports(read('phone.js'))}\nreturn {enhancePhoneLayout,syncPhoneFilters};})();\n`;
script += `const {bindEmployeePicker}=(()=>{\n${withoutExports(read('employee-picker.js'))}\nreturn {bindEmployeePicker};})();\n`;
script += `const {createCalendarService,calendarService}=(()=>{\n${withoutExports(read('calendar-api.js'))}\nreturn {createCalendarService,calendarService};})();\n`;
script += `const {invalidateHistoryCalendar,createCalendarLoader,renderHistoryCalendar,renderCalendarDigest,handleCalendarAction,handleCalendarKeydown}=(()=>{\n${withoutExports(read('calendar.js'))}\nreturn {invalidateHistoryCalendar,createCalendarLoader,renderHistoryCalendar,renderCalendarDigest,handleCalendarAction,handleCalendarKeydown};})();\n`;
script += `const {sessionState,loadSession,signOut,displayActor}=(()=>{\n${withoutExports(read('session.js'))}\nreturn {sessionState,loadSession,signOut,displayActor};})();\n`;
script += `const {businessDate,yesterdayComparison,renderYesterdayChange}=(()=>{\n${withoutExports(read('yesterday.js'))}\nreturn {businessDate,yesterdayComparison,renderYesterdayChange};})();\n`;
script += `const {photoData,photoUpload,watchPhotos,notifyPhotos,photoFileUrl,photoRequest,loadPhotos,uploadPhoto,allowPhotoRetry}=(()=>{\n${withoutExports(read('photo-service.js'))}\nreturn {photoData,photoUpload,watchPhotos,notifyPhotos,photoFileUrl,photoRequest,loadPhotos,uploadPhoto,allowPhotoRetry};})();\n`;
script += `const {createPhotoActivity,photoActivityService,fetchPhotoHistory,fetchPhotoBatch}=(()=>{\n${withoutExports(read('photo-activity.js'))}\nreturn {createPhotoActivity,photoActivityService,fetchPhotoHistory,fetchPhotoBatch};})();\n`;
script += `const {renderPhotoActivity,handlePhotoActivityAction}=(()=>{\n${withoutExports(read('photo-activity-view.js'))}\nreturn {renderPhotoActivity,handlePhotoActivityAction};})();\n`;
script += `const {renderPhotoCamera,stampedPhoto,handleCameraAction,handleCameraChange}=(()=>{\n${withoutExports(read('photo-camera.js'))}\nreturn {renderPhotoCamera,stampedPhoto,handleCameraAction,handleCameraChange};})();\n`;
script += `const {renderPhotoLibrary,handlePhotoAction,handlePhotoSubmit,handlePhotoChange,clearPhotoDraft}=(()=>{\n${withoutExports(read('photo-library.js'))}\nreturn {renderPhotoLibrary,handlePhotoAction,handlePhotoSubmit,handlePhotoChange,clearPhotoDraft};})();\n`;
script += read('app.js').replace(/^import .*?;\s*$/gm, '').replaceAll('./favicon.svg', favicon).replaceAll('./assets/company-logo.png', favicon);
script = script.replace(/<\/script/gi, '<\\/script');
const html = read('index.html')
  .replace('<meta charset="utf-8">', `<meta charset="utf-8">\n  <script src="./config.js"></script>\n  <!-- DM Sans is bundled under the SIL Open Font License. See src/assets/fonts/OFL.txt. -->`)
  .replace('<link rel="icon" type="image/png" href="./assets/company-logo.png">', `<link rel="icon" type="image/png" href="${favicon}">`)
  .replace(/^[ \t]*<link rel="stylesheet" href="\.\/(?:photos|compact-records)\.css">\r?\n/gm, '')
  .replace('<link rel="stylesheet" href="./styles.css">', `<style>\n${styles}\n</style>`)
  .replace('<script type="module" src="./app.js"></script>', `<script>\n${script}\n</script>`)
  .replace('</body>', `<script type="text/plain" id="dm-sans-font-license">\n${read('assets/fonts/OFL.txt').replace(/<\/script/gi, '<\\/script')}\n</script>\n</body>`);
if (/@import\s|(?:src|href)=["']https?:\/\//i.test(html)) throw new Error('The frontend must not depend on remote assets.');
fs.writeFileSync(path.join(project, 'index.html'), html);
if (process.argv[2]) {
  const output = path.resolve(process.argv[2]);
  fs.writeFileSync(output, html);
  const config = path.join(path.dirname(output), 'config.js');
  if (config !== path.join(project, 'config.js')) fs.copyFileSync(path.join(project, 'config.js'), config);
}
console.log('Northpoint rebuilt: API settings load from config.js');

// Compatibility entrypoint: Camera now lives inside the main Northpoint shell.
fs.writeFileSync(path.join(project,'camera.html'),'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="0;url=./index.html#camera"><title>Camera · Northpoint</title></head><body><a href="./index.html#camera">Open Camera in Northpoint</a></body></html>');
