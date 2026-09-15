# Migration Workflow

This document describes the complete SQL Server to PostgreSQL migration workflow used by Pgloader Dashboard.

## Project details

### Project name

Pgloader Migration Dashboard

### Project purpose

Pgloader Migration Dashboard is an internal migration management tool for moving selected data from SQL Server to PostgreSQL with pgloader v3. It provides a controlled interface around pgloader so database engineers can configure, validate, monitor, and review migrations without running manual commands directly on the server.

### Intended users

- Database administrators
- Data engineers
- Platform engineers
- Application engineers responsible for database migrations

### Main problem solved

Manual database migrations are difficult to track and easy to run incorrectly. This project centralizes the migration workflow and adds connection checks, table selection, preflight validation, safety warnings, background execution, live logs, cancellation, and migration history.

### Technology stack

| Area | Technology | Responsibility |
|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS | User interface and migration wizard |
| Forms | React Hook Form, Zod | Form state and client-side validation |
| Server state | TanStack Query | API requests, loading, caching, and errors |
| Backend | Python 3.11+, FastAPI, Pydantic | API, validation, orchestration, and error handling |
| SQL Server | pyodbc and Microsoft ODBC Driver | Connection tests and metadata access |
| PostgreSQL | psycopg | Connection tests and metadata access |
| Migration engine | pgloader v3 | Actual SQL Server to PostgreSQL migration |
| Runtime updates | Server-Sent Events | Live migration logs and status updates |
| Deployment | Docker and Docker Compose | Optional service packaging |

### Core design principles

1. The frontend never connects directly to a database.
2. The frontend never executes migration commands.
3. The backend validates every migration request.
4. pgloader performs the actual data migration.
5. Passwords are never logged, persisted in browser storage, or returned in responses.
6. A migration cannot execute before preflight checks pass.
7. Destructive operations require explicit confirmation.
8. Failed and cancelled migrations remain in history.
9. Retry creates a new migration job instead of overwriting the old one.
10. Progress is shown only when it is supported by reliable migration data.

### Main project modules

```text
frontend/
  Dashboard       Empty state, metrics, and migration entry point
  New Migration   Guided migration configuration wizard
  Connection UI   SQL Server and PostgreSQL connection forms
  Table Selector  Schema and selected-table configuration
  Safety Tracker  Preflight status and destructive-operation warnings
  API Client      Real and explicit mock API modes

backend/
  API Routers     Health, connections, metadata, and migrations
  Schemas         Typed Pydantic request and response models
  Connection Services  pyodbc and psycopg connection adapters
  Validation      Server-side migration configuration checks
  Safety          Preflight checks before execution
  Pgloader Service Secure config generation and process execution
  Job Service     Background job status, cancellation, and logs
  Audit/History   Migration records and important user actions
```

### Expected result

The completed workflow lets an authorized user move selected SQL Server tables into PostgreSQL through a clear sequence:

```text
Connect → Test → Select → Validate → Review → Start → Monitor → Review result
```

The tool should make unsafe or incomplete migrations difficult to start and make every migration outcome traceable.

## Workflow overview

```text
Dashboard
   ↓
New Migration
   ↓
SQL Server connection
   ↓
PostgreSQL connection
   ↓
Schema and table selection
   ↓
Migration options
   ↓
Preflight safety checks
   ↓
Migration review
   ↓
Explicit confirmation
   ↓
Queued background job
   ↓
pgloader execution
   ↓
Live logs and status
   ↓
Completed / Failed / Cancelled
   ↓
History and audit record
```

## 1. Create a migration

The user selects **New migration** from the dashboard. The frontend creates a local form state only. No migration is created and no database is contacted at this point.

## 2. Test the source connection

The user enters:

- SQL Server host
- Port
- Database
- Username
- Password

The frontend sends the form to:

```text
POST /api/connections/source/test
```

FastAPI validates the request and calls the SQL Server connection service. The service uses `pyodbc` and the installed Microsoft ODBC Driver. Passwords remain in request memory and are never returned or logged.

The UI displays one of:

- Connection successful
- Authentication failed
- SQL Server unreachable
- TLS/certificate problem
- Driver or configuration problem

The workflow cannot continue until the required source fields are valid and the source connection has been tested successfully.

## 3. Test the destination connection

The user enters the PostgreSQL connection details. The frontend sends them to:

```text
POST /api/connections/destination/test
```

FastAPI calls the PostgreSQL service, which uses `psycopg`. The UI shows the connection result without exposing credentials.

The workflow cannot continue until the destination connection has been tested successfully.

## 4. Discover schemas and tables

After the source connection succeeds, the backend retrieves available source schemas and tables. The user enters or selects a schema, searches the returned table list, and selects the exact tables to migrate.

Only selected tables are included in the migration configuration. The system must never silently migrate all tables.

The configuration is rejected if:

- No schema is selected.
- No tables are selected.
- A selected table no longer exists.

## 5. Configure migration options

The user selects:

- Schema and data
- Schema only
- Data only
- Worker count
- Whether destination tables should be dropped

Worker count is validated by both Zod in the frontend and Pydantic in the backend. The backend remains authoritative.

If dropping destination tables is enabled, the user must type:

```text
DROP TABLES
```

The operation is not allowed without this explicit confirmation.

## 6. Run preflight checks

The frontend sends the complete validated configuration to:

```text
POST /api/migrations/preflight
```

The backend checks:

- Source connection
- Destination connection
- Schema availability
- Selected tables
- Destination permissions
- pgloader availability and version
- Temporary workspace
- System readiness
- Migration configuration

Each check returns a status:

```text
PASSED
WARNING
FAILED
SKIPPED
```

Critical failures prevent execution. Warnings are shown to the user and require review.

## 7. Review the migration

The review screen shows:

- Source database
- Destination database
- Selected schema
- Selected tables
- Migration mode
- Worker count
- Drop-table setting
- Safety tracker result

The user must explicitly choose **Confirm and start migration**. The review data is submitted again to the backend and validated server-side.

## 8. Create the background job

The backend creates a unique job ID and immediately returns:

```json
{
  "id": "mig_20260905_abc12345",
  "status": "QUEUED"
}
```

The HTTP request does not wait for pgloader to finish.

## 9. Generate the pgloader configuration

`PgloaderConfigBuilder` creates a temporary `.load` file on the backend. The file contains the validated source, destination, options, and selected tables.

Security controls:

- The file is created only on the server.
- The job directory has restrictive permissions.
- The load file has restrictive permissions.
- The file is never returned to the browser.
- The file is removed after the job finishes.

## 10. Execute pgloader

The migration service invokes the installed binary through a subprocess argument list. It does not use `os.system`, raw shell strings, or `shell=True`.

Status changes are:

```text
QUEUED → STARTING → RUNNING
```

The terminal status is one of:

```text
COMPLETED
FAILED
CANCELLED
```

## 11. Stream logs and status

The backend captures pgloader output as structured log entries. The frontend can read historical logs from:

```text
GET /api/migrations/{job_id}/logs
```

Live events are exposed through:

```text
GET /api/migrations/{job_id}/events
```

The event stream reports log entries and terminal status changes. The frontend should reconnect if the stream is interrupted.

The UI must not show fabricated percentage progress. When pgloader does not provide reliable progress, display completed tables, processed rows, current logs, and elapsed time instead.

## 12. Cancellation

Cancellation is available while the job is queued, starting, or running.

```text
POST /api/migrations/{job_id}/cancel
```

The backend marks cancellation, terminates the worker process, preserves logs, and records `CANCELLED`. A cancellation must never silently disappear or leave the job marked as running.

## 13. Completion or failure

On completion, the UI shows:

- Final status
- Tables selected
- Tables completed
- Failed tables
- Rows processed
- Error count
- Start time
- Completion time
- Duration

On failure, the UI shows a safe explanation, error code, retryability, and a link to technical logs. Stack traces, passwords, and complete connection strings are never shown to normal users.

## 14. History and retry

Every job remains in migration history, including failures and cancellations. A retry creates a new job ID and does not overwrite the previous record.

Important actions should be recorded in the audit trail:

- Connection tested
- Schema loaded
- Tables selected
- Options changed
- Preflight executed
- Migration started
- Migration cancelled
- Migration completed
- Migration failed
- Retry created

## Workflow ownership

| Stage | Frontend | Backend | pgloader |
|---|---|---|---|
| Form entry | Yes | Validates | No |
| Connection test request | Yes | Yes | No |
| Database connection | No | Yes | No |
| Schema discovery | Displays | Queries | No |
| Table selection | Yes | Validates | No |
| Preflight | Displays | Performs | Version check |
| Configuration | Collects options | Builds secure file | No |
| Migration execution | Displays status | Orchestrates process | Performs migration |
| Logs | Displays | Captures and streams | Produces output |
| History | Displays | Persists | No |
