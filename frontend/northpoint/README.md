# Northpoint frontend

## Compact lists

Dashboard keeps the totals, quick actions, trends and recent activity; Top Offenders and Department Rollup remain available in Reports & Analytics. Employees, Violations and Violation Types use compact rows and search with adjacent dropdown filters. Choosing a single-choice filter applies it immediately; date ranges use Apply dates. Use Enter or the magnifying-glass button to search, and Clear to reset the page's filters. On mobile, all three lists retain their table columns and scroll horizontally within the list, with a swipe hint above each table.

Employees display Total Demerit Points before Status. Violation rows omit employee codes and the case-code subline; case details remain accessible through View Case. A strike appears beside its points as `[Strike]`, without a separate strike column.

`[New!]` appears only in the employee directory for the first 24 elapsed hours after the backend's creation timestamp. app1's offset-less SQLite timestamps are interpreted as UTC. Because the summary API omits this timestamp, the frontend checks the existing employee-detail endpoint only for visible records that need it and keeps date metadata in memory. Failed checks do not invent a New label and offer Retry. Labels expire automatically on the visible page. No backend or server-configuration changes are required.

## Photos, camera and sign-in

Photo Library is part of the main sidebar at `/#photos`, with Photos and Activity Log tabs. The activity tab contains the month calendar and newest-first logs. Camera is in the same sidebar at `/#camera`; `/camera.html` redirects there. Upload Photo sends multipart form data to the existing `/app2/upload` endpoint. Lists, statistics, files and activity use the existing Photo API. No photo records are cached locally or fabricated on errors.

Camera uses the phone’s native capture/image picker. When the timestamp is enabled, it is burned into a JPEG before upload. A desktop opens an image picker rather than a live webcam stream. The original photo stays on the device. Unknown upload outcomes are not automatically retried; refresh and review recent photos/activity before explicitly allowing another upload.

The signed-in account comes from the existing read-only `/auth/me` endpoint. It uses the HTTP-only session cookie and returns the user ID, username and profile names; Northpoint displays `full_name`, using available first/last names or the username when profile names are missing. Successful responses are marked no-store, and missing/expired sessions return 401. Settings shows the signed-in name as read-only. Existing Nginx `/auth/` routing supports both session checks and logout; no backend change is needed for the frontend Sign Out button.

To sign out, open the profile button at the top right and choose **Sign Out**. Northpoint navigates to the existing `/auth/logout` endpoint, which deletes the current session, clears its cookie, and redirects to sign-in. The action waits for any active save to finish. Pages restored through Back are reloaded through Nginx so a logged-out session cannot keep using a restored dashboard.

## Yesterday comparisons

Dashboard Employees, Total Violations, Total Points and Watchlist show signed numeric changes against the prior day’s closing totals. Reports Daily Average compares the selected rolling window with the same-length window ending yesterday. Manila time defines day boundaries. No percentage or prior-period label is used. Photo Total Photos and Storage Used have no comparison indicators.

Comparisons reverse today’s recorded HR audit events. New hard-delete events include aggregate and violation snapshots so totals can be reconstructed later. Old hard-deletion logs without these snapshots, missing history, and department transfers without prior department details show `— vs yesterday` rather than fabricated changes. Hover the indicator for the reason. Restart `app1` after updating `queries.py`; no schema migration is required.

Northpoint uses the backend API for employees, violations, rulebook, dashboard, reports, History and Calendar. The existing desktop/phone design remains unchanged. Records are never stored in the browser or queued offline, and failed requests never fall back to sample data.

## One API configuration

By default **frontend/northpoint/config.js** uses the same server address as the page:

```javascript
const BASE_URL = '';
```

This makes both `http://localhost:8081/` and a tunnel address use their own `/app1/`, `/app2/`, and `/auth/` endpoints. Keep config.js beside index.html when copying or deploying the frontend. You may set an absolute API URL for a special deployment, but the browser needs an appropriate same-origin authentication and CORS setup. Save and reload after any configuration edit; no rebuild is needed. The older frontend/js/script.js configuration does not control Northpoint.

For a phone, localhost refers to the phone. Open the tunnel address or `http://YOUR-PC-LAN-IP:8081/` from the phone and sign in there; the API follows that address automatically. Use HTTPS when camera access requires a secure connection.

## Run with the local backend

Start Docker Desktop. In the **repository root**, run:

```powershell
docker compose -f docker-compose.yaml -f docker-compose.local.yaml up -d --build
```

Open **http://localhost:8081/**. The existing backend sign-in page appears when there is no valid local session; after signing in, Northpoint opens at `/`. A valid existing session goes straight to the dashboard. API requests use the same-origin session cookie; an expired session redirects to sign-in, while connection errors stay visible for retry. Opening index.html directly or using a separate preview port does not provide this same-origin login session.

If you need an account, the backend's existing account command is:

```powershell
docker compose -f docker-compose.yaml -f docker-compose.local.yaml exec auth uv run --no-sync python -m auth.manage create-user YOUR_USERNAME
```

If the stack is already running, apply the frontend mount by recreating only Nginx:

```powershell
docker compose -f docker-compose.yaml -f docker-compose.local.yaml up -d --no-deps --force-recreate nginx
```

The temporary change is in **docker-compose.local.yaml**: `./frontend/northpoint:/usr/share/nginx/html:ro`. It replaces the base file's frontend mount only for local runs. The main docker-compose.yaml and nginx/nginx.conf remain unchanged; `/app1/`, `/app2/`, `/app3/` and `/auth/` keep their existing routes and authentication. Remove that local volume override and recreate Nginx to restore the original frontend. A deployment serving these routes on the same origin needs no config.js URL change.

Your signed-in full name is used automatically for changes. Existing documented X-Actor and removal payload behavior is retained; Nginx also forwards the authenticated name. Workspace role choices are view filters, not account permissions. Users & Roles remains Coming Soon. Loading, success, conflict, access and lost-response handling remain in place; unconfirmed saves are checked by GET before another write is allowed.

## Development checks

Node 24+ is needed only for development; it is not required to open the Docker-served website:

```powershell
node build.mjs
node verify.mjs
```

The generated page bundles its styles, fonts and logo and loads config.js separately. Uploaded photo files are served by the photo API.

`node serve.mjs` is an optional static preview server. It serves index.html and config.js; use the Docker URL for authenticated API access.

## Photo Activity and API routes

Photo Activity now fetches eight events per page from `/app2/activity`. Search, team member, action, and selected-date filters are sent to the server. “All dates” removes the feed's date restriction; the adjacent calendar always summarizes the displayed month using `/app2/activity/digest?include_items=false`. Calendar shading uses the returned daily totals and the text below it uses the server's summary. No full activity-history download occurs when opening the photo library.

The “Changed by” options come from `/app2/activity/actors`. Clicking a photo name in Activity or “View History” in Photo Details opens its paginated `/app2/photos/{id}/history`, including retained history for deleted photos. “Photos on this page” uses the read-only `POST /app2/photos/batch` with `{ "ids": [...] }`; it shows only photos linked to that event page and explicitly reports missing/deleted photos. It does not upload or modify records.

Activity requests cancel and ignore superseded reads. Errors clear the results and show a retry button. Page navigation reuses the latest successful monthly summary and actor options in memory; reopening Activity, retrying, or saving a photo from Activity refreshes them. Nothing is persisted in browser storage.

The public URL adds the service prefix: schema `/activity/actors` in app2 becomes `/app2/activity/actors`. The existing `config.js` remains the server configuration. The browser must use the same server as the signed-in session.

Photo Activity → Photos on this page: select a thumbnail or photo name to open the enlarged viewer. Back to photos restores the same gallery. Image loading failures show a retry option. The viewer adapts to desktop and phone screens.

The account name comes from `/auth/me`: `full_name`, then available first/last names, then username for older accounts without profile names. New issued-by and removal payloads use this name. Historical names for other accounts stay as returned by the backend; `/auth/me` only identifies the current account.

## Source folders

Edit source files in `src/`, then run `node build.mjs` to refresh the root `index.html`. Keep server configuration in the existing root `config.js`.

- `app.js` and `index.html`: application entry point and page template.
- `api/`: shared API transport, allowed routes and request helpers.
- `auth/`: signed-in account and session handling.
- `state/`: shared application data, backend loading and mutations.
- `features/dashboard/`: dashboard view.
- `features/employees/`: employee requests, forms, picker and New labels.
- `features/records/`: employee, violation and violation-type list views.
- `features/history/`: calendar, daily summaries and history API contracts.
- `features/reports/`: reports, analytics and yesterday comparisons.
- `features/photos/`: photo library, activity, viewer, camera and API handling.
- `features/settings/`: settings, help and secondary page routing.
- `shared/`: reusable domain helpers, loading states, filters and mobile behavior.
- `styles/`: shared, photo and compact-table styles.
- `assets/`: company logo and bundled fonts.
- `preview/`: retained preview helpers, excluded from the live website build.

File imports and `build.mjs` use these folder paths; moving a file again requires updating its imports and build entry.
