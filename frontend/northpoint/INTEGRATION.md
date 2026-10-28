# Connect the backend later

The presentation is isolated from data transport. Every record read or attempted record write passes through `src/api-client.js` into `src/data-source.js`. The default source is the explicitly labeled, read-only `createPreviewProvider()` in `src/preview-provider.js`. It is never a failed-request fallback.

## One integration boundary

Replace the source configured in `src/data-source.js` with an adapter exposing:

```js
export const dataSource = {
  mode: 'api',
  async request({ path, method = 'GET', query = {}, body, actor, signal }) {
    // Implement transport here using the team's authenticated API client.
    // Return parsed response JSON, or null for a successful HTTP 204.
    // Throw on HTTP errors, failed authentication, cancellation or bad replies.
    // Do not return preview fixtures when a request fails.
  }
};
```

The snippet defines the interface, not a working API implementation. Transport, login and backend changes are intentionally absent from this UI-only package. The backend developer can delegate to their shared client without rewriting the views. If importing another adapter module, add its exported bindings to build.mjs before bundling. Rebuild index.html after integration; editing src alone does not change the standalone page.

The current standalone page has `connect-src 'none'` to enforce a network-free preview. During real integration, change the build policy to the agreed API origin or `'self'` for same-origin requests. Do not broadly allow all destinations. The existing backend proxy requires a login session; simply changing a URL is insufficient. Prefer the agreed same-origin `/app1` deployment and authenticated requests. Opening a file or using a separate local origin has cookie/CORS implications that must be handled in the integration PR.

## Existing view contracts

| UI | Routes used by the views | Required response |
|---|---|---|
| Employee directory | GET /employees?include_inactive=true&limit=50&offset=0 | `{items,total,limit,offset}` of EmployeeSummary |
| Employee profile/edit | GET /employees/{id}; PATCH /employees/{id} | EmployeeDetail with `violation_records`; EmployeeRead after PATCH |
| Add employee | POST /employees | EmployeeRead; input is employee_code, first_name, last_name, department, position |
| Employee status/delete | POST /employees/{id}/deactivate or /reactivate; DELETE /employees/{id} | EmployeeRead or HTTP 204 |
| Employee violations | GET /employees/{id}/violations?limit=50&offset=0 | Bare ViolationRecordRead array |
| Issue violation | POST /employees/{id}/violations | ViolationRecordRead; input is violation_type_id, notes, issued_by |
| Case details/edit | GET /violations/{id}; PATCH /violations/{id} | ViolationRecordRead; update input is notes, issued_by |
| Recent activity | GET /violations/recent?days=14&only_strikes=false&limit=5 | Bare array including nested employee |
| Rulebook | GET /violation-types; GET /violation-types/all?include_inactive=true; GET /violation-types/{id} | Bare arrays or one type |
| Rulebook changes | POST /violation-types; PATCH /violation-types/{id}; POST /violation-types/{id}/activate or /deactivate; DELETE /violation-types/{id} | Type object or HTTP 204 |
| Remove violation | POST /violations/{id}/remove | Removal object; input is removed_by and reason |
| History | GET /activity/timeline; GET /violation-removals | `{items,total,limit,offset}` |

`src/employee-api.js` converts employee_code/full_name/total_points/total_strikes into view models. `src/backend.js` converts rulebook, violation, activity and removal responses. `src/employee-details.js` and `src/mutations.js` prepare write payloads. Keep authoritative record IDs and the distinction between numeric API IDs and employee codes. Employee summaries do not contain created_at; newest-first currently falls back to numeric ID. Reports are calculated from loaded records and exclude removed violations; dedicated backend analytics endpoints can replace those calculations in a later change.

## Decisions for the integration PR

- Let the authenticated server determine permissions and audit identity. HR/Supervisor choices here are visual previews, not authorization. The existing proxy overwrites X-Actor, while removal attribution is in removed_by. Agree on their relationship with the signed-in user.
- The inspected backend ignores null department/position values in PATCH. The current UI produces null when clearing an optional field. Agree on clearing semantics before enabling saves; otherwise the UI's verification correctly rejects a mismatched reply.
- The issue date is displayed as today; the current payload lets the backend assign issued_at. Points and strike are snapshots assigned from the chosen violation type.
- For failed writes with unknown outcome, throw an error carrying `{uncertain:true}` so the existing UI checks the record with GET before allowing another attempt. For known failures, include a user-readable message and optional status. Do not automatically retry a POST. Successful employee creation is displayed only after a fresh directory read confirms it.
- All employee histories are currently loaded to support company-wide reports. Consider the existing analytics endpoints or a paginated global list when the directory grows.
- Keep UI preview fixtures out of the live adapter and test authenticated desktop/phone behavior, duplicate codes, optional-field clearing, errors and lost responses before release.

To review empty/error/loading states without a backend, set `createPreviewProvider({scenario:'empty'})`, `createPreviewProvider({scenario:'error'})`, or a longer `delayMs` in data-source.js and rebuild. Restore the normal configuration before submitting the UI preview PR.
