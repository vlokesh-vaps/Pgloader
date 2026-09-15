# Pgloader Migration Dashboard

An internal web application for safely managing SQL Server to PostgreSQL migrations with [pgloader v3](https://pgloader.readthedocs.io/). The dashboard provides the workflow around pgloader: database connection testing, schema and table selection, migration configuration, safety checks, job tracking, logs, cancellation, and history.

The application does not reimplement database migration logic. The backend validates a migration request, creates a temporary pgloader configuration, runs the installed `pgloader` binary in a background task, captures its output, and reports the result to the frontend.

## What this project provides

- A React, TypeScript, Vite, and Tailwind dashboard.
- A FastAPI backend with typed Pydantic request and response models.
- Real SQL Server connection testing through `pyodbc`.
- Real PostgreSQL connection testing through `psycopg`.
- Server-side pgloader configuration generation.
- Shell-free pgloader execution with `asyncio.create_subprocess_exec`.
- Migration statuses: `QUEUED`, `STARTING`, `RUNNING`, `COMPLETED`, `FAILED`, and `CANCELLED`.
- Preflight and safety-check workflow before execution.
- Structured migration logs and an SSE event endpoint.
- Explicit confirmation for destructive `DROP TABLES` operations.
- Mock mode for frontend development without database access.

## Architecture

```text
React + TypeScript frontend
             |
             | REST API and SSE logs
             v
FastAPI backend
   |         |          |
   |         |          +-- Job and migration services
   |         +------------- Connection and metadata services
   +----------------------- Safety and validation services
             |
             v
        pgloader v3
        /          \
 SQL Server    PostgreSQL
```

The frontend never connects directly to either database and never stores database passwords. The backend is the only database and process boundary.

## Repository structure

```text
frontend/                  React application
  src/App.tsx              Migration dashboard and wizard
  src/services/api/        REST client and mock/real API switch
  src/schemas/             Zod form validation
  src/types/               TypeScript API types

backend/                   FastAPI application
  app/api/                 HTTP routers
  app/schemas/             Pydantic models
  app/services/            Connection and migration services
  app/core/                Settings, errors, and logging
  tests/                   Backend tests

docs/                      Architecture, setup, API, security, and flow docs
docker-compose.yml         Optional frontend/backend containers
.env.example               Configuration template
```

## Requirements

- Python 3.11 or newer.
- Node.js 20 or newer and npm.
- pgloader v3 installed and available on `PATH`, or configured with `PGLOADER_PATH`.
- Microsoft ODBC Driver 18 for SQL Server.
- FreeTDS/ODBC configuration appropriate for the target SQL Server.
- Network access from the backend host to both databases.

Verify pgloader and the SQL Server driver:

```bash
pgloader --version
python -c "import pyodbc; print(pyodbc.drivers())"
```

## Configuration

Create a local environment file:

```bash
cp .env.example .env
```

Important settings:

```env
APP_ENV=development
LOG_LEVEL=INFO
PGLOADER_PATH=pgloader
MIGRATION_WORK_DIR=./.pgloader-jobs
MAX_WORKERS=8
SOURCE_CONNECTION_TIMEOUT=30
TARGET_CONNECTION_TIMEOUT=30
MIGRATION_TIMEOUT=3600
CORS_ORIGINS=http://localhost:5173,http://172.16.10.187:5173
VITE_API_MODE=real
VITE_API_URL=http://localhost:8009/api
```

Never commit `.env` or place database credentials in frontend source code.

## Run locally

Install backend dependencies:

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Install frontend dependencies once:

```bash
npm install --prefix frontend
```

Start both services from the repository root with one command:

```bash
npm run dev
```

The services use:

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8009
API:      http://localhost:8009/api
```

To expose the app on a LAN IP:

```bash
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8009 --reload
cd frontend
VITE_API_MODE=real VITE_API_URL=http://172.16.10.187:8009/api npm run dev -- --host 0.0.0.0
```

Then open `http://172.16.10.187:5173` from an allowed device.

## Migration workflow

The full migration process is documented separately in [docs/workflow.md](docs/workflow.md). It covers connection testing, schema/table selection, preflight gates, review, background execution, live logs, cancellation, completion, failure, retry, and audit ownership.

## API endpoints

```text
GET  /api/health
POST /api/connections/source/test
POST /api/connections/destination/test
GET  /api/source/schemas
GET  /api/source/tables?schema=<schema>
POST /api/migrations/preflight
POST /api/migrations
GET  /api/migrations
GET  /api/migrations/{job_id}
POST /api/migrations/{job_id}/cancel
POST /api/migrations/{job_id}/retry
GET  /api/migrations/{job_id}/logs
GET  /api/migrations/{job_id}/events
```

Connection-test responses never include passwords or full connection strings.

## Mock mode

Mock mode is only for frontend development:

```bash
cd frontend
VITE_API_MODE=mock npm run dev
```

Real mode is the default. In real mode, connection tests call the FastAPI backend and use the actual database drivers. Mock mode does not perform a migration.

## Verification

```bash
cd frontend
npm run build

cd ../backend
PYTHONPATH=. pytest
```

Python source can be syntax-checked without installed dependencies:

```bash
python -m compileall -q backend/app
```

## Security model

- Passwords are accepted only by backend request models and are not logged.
- Credentials are not stored in browser local storage.
- Temporary pgloader files are created server-side with restrictive permissions and removed after execution.
- User input is validated before configuration generation.
- pgloader is launched without `shell=True` and without `os.system`.
- Destructive operations require explicit confirmation.
- Failed migrations remain in history rather than being overwritten.

Before production deployment, add authentication and authorization, durable database-backed job storage, a persistent worker queue, encrypted secret storage, rate limiting, and durable audit records.

## Current implementation notes

The first runnable version keeps jobs and logs in process memory so the complete workflow can be developed locally. For production with multiple backend workers, replace this repository with SQLAlchemy persistence and a durable worker/event system. The service boundaries are already separated for that migration.

See also:

- [docs/architecture.md](docs/architecture.md)
- [docs/setup.md](docs/setup.md)
- [docs/api.md](docs/api.md)
- [docs/security.md](docs/security.md)
- [docs/migration-flow.md](docs/migration-flow.md)
