# relay backend_py

Python/FastAPI reimplementation of the relay backend. It is intentionally isolated from
the existing `backend` directory and uses SQLite from the Python standard library
instead of Redis/PostgreSQL.

## Run

```powershell
cd D:\relay\backend_py
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8081 --reload
```

Point the frontend at it with:

```powershell
$env:VITE_API_BASE_URL='http://127.0.0.1:8081/api'
```

## Local config

By default the app stores data in `backend_py/relay_py.db`.

It can import local upstream credentials at startup:

- `RELAY_PY_CHAT_PROFILES`, default `D:\freeclaude\chat_profiles.json`
- `RELAY_PY_CODEX_PROFILES`, default `D:\freeclaude\codex_profiles.json`

Those files are read at runtime only. Tokens are not copied into this repository.

Useful environment variables:

- `RELAY_PY_DB`: SQLite path
- `RELAY_PY_JWT_SECRET`: HMAC secret for login tokens
- `RELAY_PY_ALLOW_DEV_VERIFY_CODE`: when `1`, `/auth/register-code` returns `debugCode`
- `RELAY_PY_CORS_ORIGINS`: comma-separated origins, default `*`

## Synchronous billing/logging

This version does not use FastAPI background tasks. Proxy logging and balance deduction
happen inline after the upstream response body has been yielded to the client. For normal
JSON responses this is effectively immediate; for streams it runs when the stream finishes.

## Sync Supabase/Postgres and SQLite

Install dependencies first:

```powershell
cd D:\relay
pip install -r backend_py\requirements.txt
```

Set the Supabase database connection string from Dashboard -> Connect -> Transaction pooler
or Direct connection:

```powershell
$env:SUPABASE_DB_URL='postgresql://postgres.xxx:password@host:6543/postgres?sslmode=require'
```

Preview the sync without writing:

```powershell
python backend_py\migrate_postgres_to_sqlite.py --dry-run
python backend_py\migrate_sqlite_to_postgres.py --dry-run
```

Run the real sync from Supabase/Postgres to SQLite:

```powershell
python backend_py\migrate_postgres_to_sqlite.py
```

Run the real sync from SQLite back to Supabase/Postgres:

```powershell
python backend_py\migrate_sqlite_to_postgres.py
```

Both scripts skip `verification_codes` by default because register codes are temporary.
Existing rows with the same primary key are compared column by column: unchanged rows are
skipped, changed rows are updated, missing rows are inserted, and target rows missing from
the source are deleted. Use `--tables users,api_keys` to sync only selected tables.

The Postgres-to-SQLite script can create missing SQLite tables and columns with simple
SQLite types. The SQLite-to-Postgres script syncs tables that already exist in Postgres
and resets Postgres serial/identity sequences after inserting explicit ids.
