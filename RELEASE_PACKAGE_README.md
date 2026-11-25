# FactoryLink Japan — release candidate package

This archive contains the complete FactoryLink source tree plus the Render and
production-readiness fixes recorded in `RELEASE_REVIEW_2026-11-05.md`.

## What is deliberately not included

- Real `.env` files or service credentials.
- Python `.venv`, frontend `node_modules`, build output, caches or compiled files.
- Local database dumps, uploaded documents, and backup archives.

Use `.env.example` for a fresh local evaluation and `.env.production.example`
only as a production configuration reference. Do not reuse local/demo passwords
or copy real credentials into source control.

## Test in an isolated local Compose project (Windows PowerShell)

1. Extract this archive into a new folder. Do not overwrite the folder currently
   running your FactoryLink database.
2. In the extracted `FactoryLink` folder, run:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

3. Set `APP_PORT=8081` in `.env` if your existing application already uses
   port 8080. Keep strong local-only passwords and a local-only JWT secret.
4. Start this candidate under a separate Compose project name so it creates
   separate, isolated development volumes:

   ```powershell
   docker compose -p factorylink-release-candidate up --build -d
   docker compose -p factorylink-release-candidate ps
   ```

5. Open `http://localhost:8081` (or the port you configured). This isolated
   candidate starts with its own local database; it does not reuse or migrate
   your currently running FactoryLink database.

Do not run `docker compose down -v` against your existing project. It deletes
Compose-managed data volumes. To stop this isolated candidate without deleting
its data, use:

```powershell
docker compose -p factorylink-release-candidate stop
```

## Render setup order

Read `DEPLOYMENT.md` before provisioning. Create two Blueprints from the same
repository, using these paths in this exact order:

1. `render-database.yaml` — creates managed PostgreSQL.
2. Save its initial `factorylink_owner` Internal Database URL securely; create
   a new default managed credential named `factorylink_app` in Render.
3. `render.yaml` — creates the application services and references the existing
   database. Supply the saved owner URL and the required SMTP, S3, CORS and
   frontend URL settings when prompted.

Review plan costs and service regions in Render before approving deployment.
Render currently has no Japan region; obtain customer approval for the
Singapore processing location before storing real Japanese factory data.

## Release status

This is a hardened release candidate, **not a production approval or compliance
certification**. Real SMTP, S3, ClamAV, Render, provider-side backup/restore,
monitoring/alerts, Japanese customer privacy review, and factory acceptance
still require deployment and verification with customer-owned services.
