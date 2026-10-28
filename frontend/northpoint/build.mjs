// Rebuild the offline HTML from the modular app. No packages or network needed.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const project = fileURLToPath(new URL('./', import.meta.url));
const source = path.join(project, 'src');
const read = name => fs.readFileSync(path.join(source, name), 'utf8');
const withoutExports = content => content.replace(/^import .*?;\s*$/gm, '').replace(/\bexport\s+(?=(?:async\s+)?(?:function|const|let)\b)/g, '');
const favicon = 'data:image/png;base64,' + fs.readFileSync(path.join(source,'assets/company-logo.png')).toString('base64');
let styles = read('styles.css');
for (const name of ['dm-sans-latin-ext.woff2', 'dm-sans-latin.woff2']) {
  const encoded = fs.readFileSync(path.join(source, 'assets/fonts', name)).toString('base64');
  styles = styles.replaceAll(`./assets/fonts/${name}`, `data:font/woff2;base64,${encoded}`);
}
let script = `const {validCalendarDate,calendarMonthBounds,shiftCalendarMonth,calendarCells,calendarActionLabel,previewCalendarRows,previewDailyDigest,validateDailyDigest}=(()=>{
${withoutExports(read('calendar-data.js'))}
return {validCalendarDate,calendarMonthBounds,shiftCalendarMonth,calendarCells,calendarActionLabel,previewCalendarRows,previewDailyDigest,validateDailyDigest};})();
`;
script += `const {previewFixtures}=(()=>{
${withoutExports(read('preview-fixtures.js'))}
return {previewFixtures};})();
`;
script += `const {createPreviewProvider}=(()=>{
${withoutExports(read('preview-provider.js'))}
return {createPreviewProvider};})();
`;
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
script += `const {renderEmployees,renderViolations,employeeLoadState}=(()=>{\n${withoutExports(read('records.js'))}\nreturn {renderEmployees,renderViolations,employeeLoadState};})();\n`;
script += `const {renderReports,renderHistory}=(()=>{\n${withoutExports(read('insights.js'))}\nreturn {renderReports,renderHistory};})();\n`;
script += `const {renderSecondary,handleSecondary}=(()=>{\n${withoutExports(read('secondary.js'))}\nreturn {renderSecondary,handleSecondary};})();\n`;
script += `const {renderDashboard}=(()=>{\n${withoutExports(read('dashboard.js'))}\nreturn {renderDashboard};})();\n`;
script += `const {enhancePhoneLayout,syncPhoneFilters}=(()=>{\n${withoutExports(read('phone.js'))}\nreturn {enhancePhoneLayout,syncPhoneFilters};})();\n`;
script += `const {bindEmployeePicker}=(()=>{\n${withoutExports(read('employee-picker.js'))}\nreturn {bindEmployeePicker};})();\n`;
script += `const {createCalendarLoader,renderHistoryCalendar,renderCalendarDigest,handleCalendarAction,handleCalendarKeydown}=(()=>{\n${withoutExports(read('calendar.js'))}\nreturn {createCalendarLoader,renderHistoryCalendar,renderCalendarDigest,handleCalendarAction,handleCalendarKeydown};})();\n`;
script += read('app.js').replace(/^import .*?;\s*$/gm, '').replaceAll('./favicon.svg', favicon).replaceAll('./assets/company-logo.png', favicon);
script = script.replace(/<\/script/gi, '<\\/script');
const policy = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";
const html = read('index.html')
  .replace('<meta charset="utf-8">', `<meta charset="utf-8">\n  <meta http-equiv="Content-Security-Policy" content="${policy}">\n  <!-- DM Sans is bundled under the SIL Open Font License. See src/assets/fonts/OFL.txt. -->`)
  .replace('<link rel="icon" type="image/png" href="./assets/company-logo.png">', `<link rel="icon" type="image/png" href="${favicon}">`)
  .replace('<link rel="stylesheet" href="./styles.css">', `<style>\n${styles}\n</style>`)
  .replace('<script type="module" src="./app.js"></script>', `<script>\n${script}\n</script>`)
  .replace('</body>', `<script type="text/plain" id="dm-sans-font-license">\n${read('assets/fonts/OFL.txt').replace(/<\/script/gi, '<\\/script')}\n</script>\n</body>`);
if (/@import\s|(?:src|href)=["']https?:\/\//i.test(html)) throw new Error('The offline HTML must not depend on remote assets.');
fs.writeFileSync(path.join(project, 'index.html'), html);
if (process.argv[2]) fs.writeFileSync(path.resolve(process.argv[2]), html);
console.log('Standalone website rebuilt: index.html (static UI preview; network connections blocked)');
