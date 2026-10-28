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

Create a user / device token:

```bash
docker compose -f docker-compose.yaml -f docker-compose.local.yaml exec auth \
  uv run --no-sync python -m auth.manage create-user james

docker compose -f docker-compose.yaml -f docker-compose.local.yaml exec auth \
  uv run --no-sync python -m auth.manage add-device phone1
```

## Run on production (VPS)

```bash
docker compose -f docker-compose.yaml up -d --build
```

Back up `auth/auth.db` before every deploy.

## Auth

- Browser → session cookie (7 days)
- Phone → device token (only works for `POST /app3/`)

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
```
