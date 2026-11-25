# Architecture

This document explains how the backend is put together. Start with [README.md](README.md) for a short overview and [SETUP.md](SETUP.md) for commands.

## Request flow

```text
Browser / Android app
        |
        v
Caddy (443, production)          TLS termination; one vhost: cs317.duckdns.org
        |
        v
nginx:80                         routing + auth_request gate
   |     |      |       |
   |     |      |       +-- /app3/*  -> app3:8000   (adds X-Device)
   |     |      +---------- /app2/*  -> app2:8000   (adds X-Actor)
   |     +----------------- /app1/*  -> app1:8000   (adds X-Actor)
   +----------------------- /auth/*  -> auth:8000   (public login/device login)
                            /        -> static frontend (role dashboard)

Every protected location first calls internal location /_auth,
which proxies to auth:8000/verify with Cookie, Authorization,
X-Original-Method, and X-Original-URI.
```

The backends all listen on container port `8000` and are not published to the host. nginx strips the `/appN/` prefix before proxying, so a path in an OpenAPI document maps to `/appN` + that path.

| Public location | Upstream | Identity injected | On 401 |
|---|---|---|---|
| `/` | role dashboard | `X-Role` from auth | redirect to `/auth/login?next=...` |
| `/app1/` | `app1:8000/` | `X-Actor`, `X-Role`, `X-Employee-Id` from auth | 401 returned |
| `/app2/` | `app2:8000/` | `X-Actor` from `X-User` | redirect to login |
| `/app3/` | `app3:8000/` | `X-Device` from auth response | 401 returned |
| `/auth/login`, `/auth/device-login`, `/auth/` | `auth:8000` | none | publicly proxied; app enforces its own auth |
| `/auth/verify` | blocked | none | 404 from nginx |

The Nginx configuration is [nginx/nginx.conf](nginx/nginx.conf); production routing is in [Caddyfile](Caddyfile).

## Authentication

Two credential types are accepted by `/auth/verify` ([auth/main.py](auth/main.py#L179)):

| Credential | Created by | Sent as | Becomes | Used for |
|---|---|---|---|---|
| Browser session (7 days) | `POST /auth/login` | `auth_session` cookie | `X-Actor` = full name, `X-Username`, `X-Role` | role dashboard, app1/app2 reads and writes |
| Device token (7 days, sliding) | `POST /auth/device-login` | `Authorization: Bearer ...` | `X-Device` = `tracker:device_id` | GPS ingest and employee mobile photo flows |

Device tokens are limited to these original requests:

- `POST /app3/`
- `POST /app2/mobile-upload`
- `PATCH /app2/mobile-photos/{id}/title`

A session cookie is ignored for those device-only requests, so a browser session cannot POST GPS data with an empty `X-Device`.

For mobile photos, [auth/mobile_access.py](auth/mobile_access.py#L51) resolves the bearer token to a tracker, requires that tracker to be linked to an **active employee whose type is Supervisor**, and returns the employee id/code/name to app2. Only HR can call the `/auth/employees/{id}/mobile-access` endpoints, and only a Supervisor employee is eligible for a tracker account. Legacy `add-device` tokens are not tracker-linked and remain GPS-only.

Only HR can change passwords for either account type. Website login accounts use
`GET /auth/employees/{id}/login-account` and
`PATCH /auth/employees/{id}/password` ([auth/passwords.py](auth/passwords.py));
a login password change also signs out that employee's browser sessions. Tracker
passwords are reset through the existing HR-only mobile-access endpoints, which
revoke the tracker's phones.

`X-Actor` is required by app1 writes and by app2 mutation endpoints; reads are generally public behind the nginx gate. app3 uses `X-Device`, not `X-Actor`.

Browser users have one role: `c_manager`, `employee`, `hr`, or `supervisor`. Creating an
employee from the HR workspace is the normal account-creation path: app1 stores an
`employee_type` (the auth role), creates the linked auth user through
[auth/accounts.py](auth/accounts.py), and records `users.employee_id`. Employee edits,
deactivation, reactivation and deletion keep that login account in sync. The auth CLI
remains available for administrative recovery and legacy accounts.

On successful login, and when an authenticated browser opens `/`, nginx sends the user
to `/<role>/index.html`. The auth service also rejects requests for another role's
folder with `403`, so the frontend folders are not just cosmetic redirects.

`/auth/verify` enforces the app1 part of the role matrix. HR can manage employees and
rulebook data; Supervisors can read records and issue violations; Chief Managers have
read access; a Concerned Employee may only read
`/app1/employees/{own_id}/violation-history`. app1 repeats the ownership and HR checks
when it receives `X-Role` and `X-Employee-Id` from nginx.

## Services and data

| Service | Public prefix | Responsibility | State |
|---|---|---|---|
| `auth` | `/auth/` | sessions, device tokens, nginx `auth_request` gate, employee↔tracker links | `data/auth/auth.db` |
| `app1` | `/app1/` | violation tracker: employees, rulebook, violations, removals, analytics | `data/app1/app.db` |
| `app2` | `/app2/` | photo library: mobile uploads, files, metadata, activity, stats | `data/app2/photos.db`, `data/app2/uploads/` |
| `app3` | `/app3/` | GPS ingest, live device state, routes, map | `data/app3/tracking.db` (live state is in memory) |
| `nginx` | internal / `:8081` locally | reverse proxy, auth gate, static frontend | none |
| `caddy` | `80`/`443` | TLS termination in production | `caddy_data` volume |
| frontend | `/` | Northpoint single-page UI, served by nginx | static files in `frontend/northpoint/` |

See [docker-compose.yaml](docker-compose.yaml) and [docker-compose.local.yaml](docker-compose.local.yaml) for the exact environment variables and mounts.

## app1 — violation tracker

The rulebook is hierarchical ([models.py](models.py#L100)):

```text
ViolationType (category, active/inactive)
  └── ViolationSubsection (specific violation, active/inactive)
        └── Penalty(offense_number, description)
```

Issuing a violation snapshots the subsection and penalty text onto the `ViolationRecord`, so later rulebook edits do not rewrite history. The next offense number is `active records + removals + 1` for that employee/subsection. If no tier matches, the nearest lower tier is used; if none exists, assignment is rejected. Inactive rulebook entries also block assignment.

`ViolationRemoval` is an audit snapshot: removals keep the offense in repeat-offense counts and total offenses but take it out of the active list. All writes record `ActivityEvent` rows with the actor from `X-Actor`.

Main route groups:

- `/employees` — create/bulk update, search, filter, deactivate/reactivate, by-code lookup, totals, violation history. Each employee carries an `employee_type` of `hr`, `supervisor`, `c_manager`, or `employee`.
- `/violation-types` — categories
- `/violation-types/{id}/subsections` — specific violations and their penalty tiers
- `/employees/{id}/violations` — issue/list, clear all, remove one, offense summary
- `/activity/timeline`, `/activity/calendar`, `/activity/digest/{day}` — audit views
- `/analytics/top-offenders`, `/departments`, `/subsections`, `/watchlist`, `/clean-employees` — dashboards

Employee list filters: `search`, `department`, `position`, `include_inactive`, `min_active_violations`, `min_total_offenses`. Violation queries also support offense-number, date, subsection, and status filters. Current APIs use offense counts; the older points/strikes serializers remain only for the legacy showcase.

## app2 — photo library

Browser uploads are disabled: `POST /app2/upload` always returns 403. Photos enter the system from the Android app through `POST /app2/mobile-upload`.

```text
multipart/form-data
  file:      JPG, PNG, or WebP (extension + magic bytes checked, <= 15 MB)
  metadata:  JSON string
  title:     optional (max 120 chars)
```

The metadata JSON requires `upload_id` (UUID), `latitude`, `longitude`, `accuracy_m` (≤ 25), timezone-aware `location_at` and `selected_at` (within 120 seconds of each other, at most 5 minutes in the future), and `source` (`camera` or `gallery`). Optional `expected_tracker_id`, `expected_employee_id`, and `expected_employee_code` guard against a stale account. Extra fields are rejected.

Uploads are idempotent by `tracker_id:upload_id`: a duplicate returns the existing photo. Each record stores the selected time in Manila time, GPS coordinates, accuracy, and a 250 m context radius in its description and metadata. Success is `201` with a `PhotoOut` body.

HR-facing endpoints cover the rest of the library:

- `GET /photos`, `GET /photos/{id}`, `/file`, `/download` — browse and retrieve
- `PATCH /photos/{id}`, `POST /photos/{id}/rename`, `DELETE /photos/{id}`, `POST /photos/bulk-delete` — edit and remove
- `GET /photos/{id}/history`, `GET /activity`, `GET /activity/digest` — audit views
- `GET /activity/authors`, `GET /activity/actors`, `POST /photos/batch`, `GET /stats` — reporting
- `PATCH /mobile-photos/{id}/title` — employee title edit with a monotonic `revision`; stale or conflicting edits are rejected

## app3 — GPS tracking

The phone sends batches to `POST /app3/`:

```json
{
  "id": "phone1:phone-1",
  "points": [
    {"lat": 14.5995, "lon": 120.9842, "ts": 1700000000, "acc": 10}
  ]
}
```

`X-Device` from the device token is bound to the `id` for tracker-linked accounts. Ingest filters jitter using accuracy, speed, time gaps, movement confirmation, median smoothing, and segment breaks, then deduplicates by `(device_id, ts)`. Daily cleanup runs at Manila midnight.

Live state is in memory: a ping newer than 15 seconds counts as online. Routes:

- `GET /map` — map page
- `POST /` — ingest batch
- `GET /live/{dev}`, `GET /devices?include_offline=true` — current state
- `GET /route/{dev}` — today's persisted segments

## Frontend

`frontend/northpoint/` is the maintained UI. Its `config.js` defaults to same-origin API calls, so `BASE_URL = ''` makes `/app1/`, `/app2/`, and `/auth/` follow whichever host served the page. Build and verify it with:

```bash
cd frontend/northpoint
node build.mjs
node verify.mjs
```

Locally, the legacy showcase page is available at `/showcase.html`; the production root serves only `frontend/northpoint/`. [COMPANY_RULES.md](COMPANY_RULES.md) is the source data for the rulebook importer, not generated documentation.
