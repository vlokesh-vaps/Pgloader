import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4
from ..schemas.migration import MigrationConfig, MigrationJob, MigrationStatus
from .pgloader_service import PgloaderService

logger = logging.getLogger(__name__)

class MigrationService:
    def __init__(self, pgloader: PgloaderService): self.pgloader, self.jobs, self.logs, self.tasks, self.configs = pgloader, {}, {}, {}, {}
    def create(self, config: MigrationConfig) -> MigrationJob:
        job_id = f"mig_{datetime.now(timezone.utc):%Y%m%d}_{uuid4().hex[:8]}"
        job = MigrationJob(id=job_id, status=MigrationStatus.QUEUED, source_type=config.source.database_type, source_database=config.source.database, destination_type=config.destination.database_type, destination_database=config.destination.database, selected_schema=config.schema_name, selected_tables=config.tables, migration_mode=config.mode, workers=config.workers, drop_tables=config.drop_tables)
        self.jobs[job_id] = job
        self.logs[job_id] = []
        self.configs[job_id] = config.model_copy(deep=True)
        task = asyncio.get_running_loop().create_task(self._run(job, config), name=f"migration-{job_id}")
        task.add_done_callback(lambda completed: self._task_finished(job_id, completed))
        self.tasks[job_id] = task
        return job

    def _task_finished(self, job_id: str, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Migration worker crashed unexpectedly for %s", job_id)
            job = self.jobs.get(job_id)
            if job and job.status not in {MigrationStatus.COMPLETED, MigrationStatus.FAILED, MigrationStatus.CANCELLED}:
                job.status = MigrationStatus.FAILED
                job.completed_at = datetime.now(timezone.utc)
                job.error_count += 1
                job.error = "Migration worker stopped unexpectedly."
                job.failure_reason = job.error
                self.log(job_id, "ERROR", job.error, "migration")
    async def _run(self, job: MigrationJob, config: MigrationConfig):
        job.status = MigrationStatus.STARTING; job.started_at = datetime.now(timezone.utc); self.log(job.id, "INFO", "Preflight validation passed", "PRECHECK"); self.log(job.id, "INFO", "Migration started", "STARTING")
        try:
            job.status = MigrationStatus.RUNNING
            async for entry in self.pgloader.run(config, job.id): self.log(job.id, entry["level"], entry["message"], entry["component"])
            job.status = MigrationStatus.COMPLETED; job.completed_at = datetime.now(timezone.utc); job.exit_code = 0; job.tables_processed = len(job.selected_tables); self.log(job.id, "INFO", "Migration completed successfully", "COMPLETED")
        except asyncio.CancelledError:
            job.status = MigrationStatus.CANCELLED; self.log(job.id, "WARNING", "Migration cancelled", "migration")
        except Exception as exc:
            job.status = MigrationStatus.FAILED; job.completed_at = datetime.now(timezone.utc); job.exit_code = getattr(exc, "exit_code", None); job.error_count += 1
            job.error = exc.message if hasattr(exc, "message") else "Migration failed while pgloader was running."
            job.failure_reason = job.error
            details = getattr(exc, "details", None)
            self.log(job.id, "ERROR", f"{job.error} ({details})" if details else job.error, "COMPLETED")
    def log(self, job_id: str, level: str, message: str, component: str): self.logs.setdefault(job_id, []).append({"timestamp": datetime.now(timezone.utc).isoformat(), "job_id": job_id, "level": level, "component": component, "message": message})
    def get(self, job_id: str) -> MigrationJob: return self.jobs[job_id]
    def list(self) -> list[MigrationJob]: return list(self.jobs.values())
    async def cancel(self, job_id: str):
        job = self.get(job_id)
        if job.status.value not in {"QUEUED", "STARTING", "RUNNING"}:
            return job
        await self.pgloader.cancel(job_id)
        task = self.tasks.get(job_id)
        if task and not task.done(): task.cancel()
        job.status = MigrationStatus.CANCELLED
        self.log(job_id, "WARNING", "Migration cancelled", "migration")
        return job

    def retry(self, job_id: str) -> MigrationJob:
        job = self.get(job_id)
        if job.status.value not in {"FAILED", "CANCELLED"}: raise ValueError("Only failed or cancelled migrations can be retried")
        return self.create(self.configs[job_id].model_copy(deep=True))
