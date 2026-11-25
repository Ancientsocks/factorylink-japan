# FactoryLink local setup troubleshooting

This guide is for the local Docker Compose package. Use fictional demo data only.

## 1. Docker Engine is unavailable

Open Docker Desktop and wait for **Engine running**. In a new PowerShell window, check:

```powershell
docker version
docker info
```

Both commands must show Server information. FactoryLink uses Linux containers; switch Docker Desktop to Linux containers if it is configured for Windows containers.

## 2. Backend image fails while installing Python requirements

The migration, API, worker and scheduler services share `backend/Dockerfile`. Build output from the old TTY progress mode may hide the pip resolver's real error. RC24 uses plain Compose progress and longer pip network retries/timeouts. To see the exact failing dependency:

```powershell
docker compose --progress plain build --no-cache migrate
```

Look immediately above `exit code: 1` for `ERROR:`, `No matching distribution found`, `ResolutionImpossible`, `CERTIFICATE_VERIFY_FAILED` or a network/DNS error.

If your network uses an approved internal PyPI mirror, set `PIP_INDEX_URL` in `.env` to that mirror URL and rebuild. Do not disable TLS certificate verification or use an untrusted package index. A first build requires internet access to download Python wheels and container images.

## 3. Start again after a successful build

```powershell
docker compose --progress plain up --build -d
docker compose ps
docker compose logs --tail=100 db db-bootstrap migrate redis clamav backend worker scheduler frontend
```

Open `http://localhost:8080`. ClamAV downloads and loads signature databases on first start; allow additional startup time and allocate approximately 4 GiB RAM or more to Docker Desktop.

## 4. Frontend build failure

The frontend container downloads the exact direct dependency versions listed in `frontend/package.json`. Check registry/network output using:

```powershell
docker compose --progress plain build --no-cache frontend
```

For a local frontend build outside Docker:

```powershell
cd frontend
npm install --no-audit --no-fund
npm run build
```

## 5. Reset only when you intend to delete local demo data

`docker compose down` stops services but keeps named volumes. The following command deletes the database, Redis persistence, uploaded documents and ClamAV signatures:

```powershell
docker compose down -v
```

Do not run it if you need to keep local data.
