# Northpoint frontend

## Photos, camera and sign-in

Photo Library is part of the main sidebar at `/#photos`, with Photos and Activity Log tabs. The activity tab contains the month calendar and newest-first logs. Camera is in the same sidebar at `/#camera`; `/camera.html` redirects there. Upload Photo sends multipart form data to the existing `/app2/upload` endpoint. Lists, statistics, files and activity use the existing Photo API. No photo records are cached locally or fabricated on errors.

Camera uses the phone’s native capture/image picker. When the timestamp is enabled, it is burned into a JPEG before upload. A desktop opens an image picker rather than a live webcam stream. The original photo stays on the device. Unknown upload outcomes are not automatically retried; refresh and review recent photos/activity before explicitly allowing another upload.

The signed-in username comes from the new read-only `/auth/me` endpoint. It uses the existing HTTP-only session cookie, returns only `{username}`, is never cached, and returns 401 for missing/expired sessions. Settings shows this username as read-only. Existing Nginx `/auth/` routing already supports it. Restart `auth` after updating that backend file.

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

Your signed-in username is used automatically for changes. Existing documented X-Actor and removal payload behavior is retained; Nginx also forwards the authenticated username. Workspace role choices are view filters, not account permissions. Users & Roles remains Coming Soon. Loading, success, conflict, access and lost-response handling remain in place; unconfirmed saves are checked by GET before another write is allowed.

## Development checks

Node 24+ is needed only for development; it is not required to open the Docker-served website:

```powershell
node build.mjs
node verify.mjs
node --test
```

The generated page bundles its styles, fonts and logo and loads config.js separately. Uploaded photo files are served by the photo API. Tests verify configuration changes without rebuilding, request paths, session-cookie mode, existing adapters, UI handlers and error behavior. Write tests use controlled responses or an isolated HTTP test server, never company records.

`node serve.mjs` is an optional static preview server. It serves index.html and config.js; use the Docker URL for authenticated API access. `node tooling/check-live.mjs` is an optional GET-only backend check; if run outside the browser it has no sign-in cookie and will report authentication failures on the protected local stack.

## Additional checks

Run `node --test` for frontend regression, photo API and yesterday-comparison tests. Run `uv run python frontend/northpoint/tests/auth-session.py` from the repository root to test anonymous, invalid, valid and expired sessions using a temporary database. Tests do not upload photos or modify company records.

## Photo Activity and generated API contracts

Photo Activity now fetches eight events per page from `/app2/activity`. Search, team member, action, and selected-date filters are sent to the server. “All dates” removes the feed's date restriction; the adjacent calendar always summarizes the displayed month using `/app2/activity/digest?include_items=false`. Calendar shading uses the returned daily totals and the text below it uses the server's summary. No full activity-history download occurs when opening the photo library.

The “Changed by” options come from `/app2/activity/actors`. Clicking a photo name in Activity or “View History” in Photo Details opens its paginated `/app2/photos/{id}/history`, including retained history for deleted photos. “Photos on this page” uses the read-only `POST /app2/photos/batch` with `{ "ids": [...] }`; it shows only photos linked to that event page and explicitly reports missing/deleted photos. It does not upload or modify records.

Activity requests cancel and ignore superseded reads. Errors clear the results and show a retry button. Page navigation reuses the latest successful monthly summary and actor options in memory; reopening Activity, retrying, or saving a photo from Activity refreshes them. Nothing is persisted in browser storage.

Generated schemas from the merged backend are saved in `tests/contracts/app1-openapi.json` and `tests/contracts/app2-openapi.json`. Run this from the Northpoint directory:

```powershell
node tooling/check-openapi.mjs
```

It checks 38 supported adapter operations, photo-filter parameter names, the batch request body, and required response fields. The same audit runs with `node --test`. These snapshots describe API contracts, not database contents. Refresh them after backend changes by running the following from the repository root after restarting any changed service:

```powershell
foreach ($service in 'app1','app2') {
  $schema = docker compose -f docker-compose.yaml -f docker-compose.local.yaml exec -T nginx wget -qO- "http://${service}:8000/openapi.json"
  if ($LASTEXITCODE -ne 0) { throw "Could not export $service schema" }
  $schema | Set-Content -Encoding utf8 "frontend/northpoint/tests/contracts/$service-openapi.json"
}
```

The public URL adds the service prefix: schema `/activity/actors` in app2 becomes `/app2/activity/actors`. The existing `config.js` remains the server configuration. The browser must use the same server as the signed-in session.
