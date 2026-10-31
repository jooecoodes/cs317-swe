![tests](https://github.com/jooecoodes/cs317-swe/actions/workflows/tests.yml/badge.svg)

## Services

| Service | Role | Path |
|---------|------|------|
| caddy | TLS termination | 80, 443 |
| nginx | Routing + auth gate | internal |
| auth | Login, sessions, device tokens | `/auth/*` |
| app1 | Violation tracker | `/app1/*` |
| app2 | Performance tracker | `/app2/*` |
| app3 | GPS ingest + map | `/app3/*` |
| frontend | Static UI | `/` |

## Run locally

```bash
docker compose -f docker-compose.yaml -f docker-compose.local.yaml up -d --build
```

Open http://localhost:8081

## Accounts & devices

All account management goes through `auth.manage`, run inside the `auth` container:

```bash
# create / update a browser user (session-cookie login)
docker compose -f docker-compose.yaml -f docker-compose.local.yaml exec auth \
  uv run --no-sync python -m auth.manage create-user james

# create / update a tracker account (used by the Android app)
docker compose -f docker-compose.yaml -f docker-compose.local.yaml exec auth \
  uv run --no-sync python -m auth.manage create-tracker phone1

# disable a tracker and log out all its phones
docker compose -f docker-compose.yaml -f docker-compose.local.yaml exec auth \
  uv run --no-sync python -m auth.manage disable-tracker phone1

# issue a device token for a tracker (shown once — copy it now)
docker compose -f docker-compose.yaml -f docker-compose.local.yaml exec auth \
  uv run --no-sync python -m auth.manage add-device phone1

# revoke a device token
docker compose -f docker-compose.yaml -f docker-compose.local.yaml exec auth \
  uv run --no-sync python -m auth.manage revoke-device phone1

# list users, trackers, and devices
docker compose -f docker-compose.yaml -f docker-compose.local.yaml exec auth \
  uv run --no-sync python -m auth.manage list
```

## Run on production (VPS)

```bash
docker compose -f docker-compose.yaml up -d --build
```

Back up `auth/auth.db` before every deploy.

## Auth

- Browser → session cookie (7 days)
- Phone → device token (only works for `POST /app3/`)
- nginx forwards every request to auth/verify before it reaches an app. That endpoint must return 2xx (allow), 401 (deny → redirect to login), or 403 (deny). Anything else — including a 500 — is surfaced to the client as a 500.

## Android

Repo: [cs317-swe-tracker](https://github.com/cs317-swe-tracker)

- Server URL: `https://cs317.duckdns.org/app3/`
- Device Token: from `add-device`

## Useful commands

```bash
# logs
docker compose -f docker-compose.yaml -f docker-compose.local.yaml logs -f nginx auth app1

# restart one service
docker compose -f docker-compose.yaml -f docker-compose.local.yaml restart app1

# reset auth data
rm auth/auth.db
```

## API schemas (OpenAPI)

Every FastAPI service publishes its schema at `/openapi.json`. The services aren't exposed to the host — only nginx can reach them — so pull the schema through the nginx container and write it to the host:

```bash
docker compose exec nginx wget -qO- http://app1:8000/openapi.json > app1_openapi.json
docker compose exec nginx wget -qO- http://app2:8000/openapi.json > app2_openapi.json
docker compose exec nginx wget -qO- http://app3:8000/openapi.json > app3_openapi.json
```

Rule:
```bash
public URL = /<appN> + path in appN_openapi.json
```

| Spec file[cite: 1] | Path in the spec[cite: 1] | Real URL through nginx[cite: 1] |
| :--- | :--- | :--- |
| `app1_openapi.json` | `/employees` | `/app1/employees` |
| `app2_openapi.json` | `/photos/5/file` | `/app2/photos/5/file` |
| `app3_openapi.json` | `/live/{dev}` | `/app3/live/{dev}` |
| `app3_openapi.json` | `/` (the upload) | `/app3/` (keep the trailing slash) |
