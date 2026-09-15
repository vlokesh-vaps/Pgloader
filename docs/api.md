# API

All endpoints are under `/api`:

`GET /health`, `POST /connections/{source|destination}/test`, `GET /source/schemas`, `GET /source/tables?schema=dbo`, `POST /migrations/assessment`, `POST /migrations/preflight`, `POST /migrations`, `GET /migrations`, `GET /migrations/{job_id}`, `POST /migrations/{job_id}/cancel`, `POST /migrations/{job_id}/retry`, and `GET /migrations/{job_id}/logs`.

`POST /migrations/assessment` inventories the SQL Server source before a migration job is queued. Pass `?format=markdown` for a readable Markdown report; the default response is the versioned JSON report. The request must include `source` and a caller-supplied `downtime_tolerance`.

Validation errors follow FastAPI's standard 422 response. Domain errors use `{success:false,error:{code,message,details,retryable}}`.
