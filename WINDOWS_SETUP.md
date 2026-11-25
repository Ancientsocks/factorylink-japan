# FactoryLink — Windows Local Setup

This guide starts the local evaluation stack on Windows 10/11. Use fictional sample data only.

## 1. Install prerequisites

1. Install Docker Desktop for Windows and enable the WSL 2 backend when prompted.
2. Start Docker Desktop and wait for **Engine running**.
3. Confirm Docker is using **Linux containers**.
4. Allocate about 4 GiB RAM or more to Docker Desktop so ClamAV has room to load its signature database.
5. Ensure the computer can reach the container registry and the configured Python/npm package indexes on the first build.

Python 3.12 and Node.js 22 are needed only for running backend/frontend development tools outside their containers. The normal application startup uses Docker Compose.

## 2. Extract and configure

1. Extract `FactoryLink-Japan-Complete-Release.zip` into a normal writable folder such as `C:\\Projects\\FactoryLink`.
2. Open PowerShell in the extracted `FactoryLink` directory.
3. Confirm the files `.env.example` and `docker-compose.yml` are present.
4. Run `Copy-Item .env.example .env` only if `.env` does not already exist. The startup script creates it automatically when missing.
5. For local evaluation, the default `.env` values are suitable for localhost only. Never expose this configuration to the Internet.

If your network requires an approved Python package mirror, edit `PIP_INDEX_URL` in `.env` to the mirror's HTTPS simple-index URL. Do not disable TLS verification and do not put private credentials inside the URL.

## 3. Start the complete stack

```powershell
.\\scripts\\start.ps1
```

The script checks that Docker Engine is reachable, builds the backend and frontend, starts PostgreSQL, Redis, ClamAV, API, background worker, scheduler and frontend, then waits for API readiness.

Open:

- Application: <http://localhost:8080>
- Swagger API documentation: <http://localhost:8080/docs>
- OpenAPI schema: <http://localhost:8080/openapi.json>
- Readiness probe: <http://localhost:8080/health/ready>

If `APP_PORT` is changed in `.env`, use that port instead of `8080`.

## 4. Local demo login

All accounts and records are fictional. This password is for **local development only**. Production demo seeding is disabled; never reuse this password for a real account.

| Role | Email |
|---|---|
| Factory administrator | `admin@factorylink.jp` |
| Production manager | `production@factorylink.jp` |
| Warehouse manager | `warehouse@factorylink.jp` |
| Quality inspector | `quality@factorylink.jp` |
| Maintenance manager | `maintenance@factorylink.jp` |
| Operator | `operator@factorylink.jp` |
| Supplier user | `supplier@osaka-parts.jp` |
| Separate-tenant administrator | `admin@tokyo-industrial.jp` |

## 5. Inspect and stop

```powershell
docker compose ps
docker compose logs --tail=100 db db-bootstrap migrate redis clamav backend worker scheduler frontend
docker compose down
```

`docker compose down` stops containers but preserves database, upload, Redis and ClamAV volumes.

**Destructive reset:** `docker compose down -v` deletes all named volumes, including the PostgreSQL database and uploaded documents. Export anything needed before running it.

## 6. Common startup failures

- Docker pipe/daemon error: open Docker Desktop, wait for Engine running, then run `docker info`.
- Python requirements build error: run `docker compose --progress plain build --no-cache migrate` and inspect the first pip error above `exit code: 1`. See `TROUBLESHOOTING.md`.
- Frontend npm failure: run `docker compose --progress plain build --no-cache frontend` to see the npm error.
- Port already in use: set an unused `APP_PORT` in `.env`, then rerun the start script.
- ClamAV not ready: allow time for initial signature download and check `docker compose logs --tail=100 clamav`.

