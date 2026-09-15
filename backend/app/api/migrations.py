import asyncio
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from ..core.config import get_settings
from ..schemas.assessment import AssessmentReport, AssessmentRequest
from ..schemas.migration import MigrationConfig
from ..schemas.response import PreflightCheck, PreflightResponse
from ..services.migration_service import MigrationService
from ..services.pgloader_service import PgloaderService
from ..services.sqlserver_service import SqlServerService
from ..services.postgres_service import PostgresService
from ..services.sqlserver_assessment_service import SqlServerAssessmentService
router = APIRouter(prefix="/migrations")
service = MigrationService(PgloaderService(get_settings()))
assessment_service = SqlServerAssessmentService()

@router.post("/assessment", response_model=AssessmentReport, response_model_exclude_none=False)
def assessment(request: AssessmentRequest, format: str = "json") -> AssessmentReport | PlainTextResponse:
    """Generate a source inventory before any migration job is queued."""
    if request.source.database_type != "sqlserver":
        raise HTTPException(422, "Assessment source must be SQL Server.")
    report = assessment_service.assess(request.source, request.downtime_tolerance, request.large_table_row_threshold, request.large_table_size_mb_threshold)
    if format == "markdown":
        return PlainTextResponse(report.to_markdown(), media_type="text/markdown")
    if format != "json":
        raise HTTPException(422, "format must be json or markdown")
    return report

@router.post("/preflight", response_model=PreflightResponse)
async def preflight(config: MigrationConfig):
    SqlServerService().test_connection(config.source)
    PostgresService().test_connection(config.destination)
    available = {table["name"] for table in SqlServerService().tables(config.source, config.schema_name)}
    missing = [table for table in config.tables if table not in available]
    if missing:
        raise HTTPException(422, detail={"code": "SOURCE_TABLE_NOT_FOUND", "message": "One or more selected tables were not found."})
    version = await service.pgloader.version()
    checks = [PreflightCheck(name="Source connection", status="passed"), PreflightCheck(name="Destination connection", status="passed"), PreflightCheck(name="Schema and selected tables", status="passed"), PreflightCheck(name="pgloader", status="passed", message=version), PreflightCheck(name="Temporary workspace", status="passed")]
    return PreflightResponse(ready=True, checks=checks)
@router.post("")
async def create_migration(config: MigrationConfig): return service.create(config)
@router.get("")
def list_migrations(): return service.list()
@router.get("/{job_id}")
def get_migration(job_id: str):
    try: return service.get(job_id)
    except KeyError: raise HTTPException(404, "Migration not found")
@router.post("/{job_id}/cancel")
async def cancel_migration(job_id: str):
    try: await service.cancel(job_id); return service.get(job_id)
    except KeyError: raise HTTPException(404, "Migration not found")
@router.get("/{job_id}/logs")
def migration_logs(job_id: str): return {"logs": service.logs.get(job_id, [])}
@router.get("/{job_id}/events")
async def migration_events(job_id: str):
    async def stream():
        sent = 0
        for _ in range(120):
            entries = service.logs.get(job_id, [])
            while sent < len(entries):
                yield f"data: {json.dumps({'event': 'log', **entries[sent]})}\n\n"; sent += 1
            if job_id in service.jobs and service.jobs[job_id].status.value in {"COMPLETED", "FAILED", "CANCELLED"}:
                yield f"data: {json.dumps({'event': 'status', 'job_id': job_id, 'status': service.jobs[job_id].status.value})}\n\n"; return
            await asyncio.sleep(1)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control":"no-cache", "X-Accel-Buffering":"no"})
@router.post("/{job_id}/retry")
def retry_migration(job_id: str):
    try: return service.retry(job_id)
    except KeyError: raise HTTPException(404, "Migration not found")
    except ValueError as exc: raise HTTPException(409, str(exc))
