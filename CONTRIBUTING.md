# Contributing

## Development principles

- Keep the backend a modular monolith unless a documented operational requirement justifies a service boundary.
- Put business rules in testable backend functions; never rely on frontend validation alone.
- Scope every tenant-owned query by the authenticated organisation and test negative access cases.
- Use database migrations for schema changes.
- Keep timestamps in UTC; use `Asia/Tokyo` for the default Japanese display timezone.
- Keep interface strings in `frontend/src/i18n.ts`; do not add user-facing text directly to components where a translation key is appropriate.
- Never commit `.env`, credentials, real customer information or uploaded documents.

## Branches and commits

Use short feature branches and conventional commit prefixes, e.g. `feat: add supplier delivery receipt`, `fix: scope attachment download by supplier`, `test: cover reservation rollback`.

## Checks

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app migrations tests
cd ../frontend
npm install --no-audit --no-fund
npm run build
```

For integrated changes, also run `docker compose up --build`, exercise the supplier-to-receipt-to-production-to-quality workflow, and record observed results in `PROJECT_STATUS.md`.
