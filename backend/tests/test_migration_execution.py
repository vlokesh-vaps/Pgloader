import asyncio
from pathlib import Path

from app.core.config import Settings
from app.schemas.migration import MigrationConfig, MigrationStatus
from app.services.migration_service import MigrationService
from app.services.pgloader_service import PgloaderService


def migration_config() -> MigrationConfig:
    return MigrationConfig.model_validate({
        "source": {"database_type": "sqlserver", "host": "source", "port": 1433, "database": "source_db", "username": "source_user", "password": "source_password"},
        "destination": {"database_type": "postgresql", "host": "destination", "port": 5432, "database": "destination_db", "username": "destination_user", "password": "destination_password"},
        "schema": "dbo",
        "tables": ["users"],
    })


def test_background_migration_runs_pgloader_and_captures_output(tmp_path: Path):
    async def run():
        service = MigrationService(PgloaderService(Settings(pgloader_path="/bin/echo", migration_work_dir=tmp_path)))
        job = service.create(migration_config())
        await service.tasks[job.id]
        return job, service.logs[job.id]

    job, logs = asyncio.run(run())

    assert job.status == MigrationStatus.COMPLETED
    assert job.exit_code == 0
    messages = [entry["message"] for entry in logs]
    assert any("Launching pgloader executable" in message for message in messages)
    assert any("pgloader started" in message for message in messages)
    assert any("pgloader exited with code 0" in message for message in messages)
    assert "Migration completed successfully" in messages


def test_background_migration_records_pgloader_failure_and_exit_code(tmp_path: Path):
    async def run():
        service = MigrationService(PgloaderService(Settings(pgloader_path="/bin/sh", migration_work_dir=tmp_path)))
        job = service.create(migration_config())
        await service.tasks[job.id]
        return job, service.logs[job.id]

    job, logs = asyncio.run(run())

    assert job.status == MigrationStatus.FAILED
    assert job.exit_code != 0
    assert any(entry["level"] == "ERROR" for entry in logs)
    assert any("Exit code:" in entry["message"] for entry in logs)
