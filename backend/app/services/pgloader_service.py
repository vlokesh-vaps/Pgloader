import asyncio
import logging
import os
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import quote
from ..core.config import Settings
from ..core.exceptions import PgloaderExecutionError
from ..schemas.migration import MigrationConfig

logger = logging.getLogger(__name__)

class PgloaderConfigBuilder:
    @staticmethod
    def _connection_url(scheme: str, username: str, password: str, host: str, port: int, database: str, *, sslmode: str | None = None) -> str:
        """Build a pgloader URI with credentials safely escaped as URI components."""
        credentials = f"{quote(username, safe='')}:{quote(password, safe='')}"
        query = f"?sslmode={quote(sslmode, safe='')}" if sslmode else ""
        return f"{scheme}://{credentials}@{host}:{port}/{quote(database, safe='')}{query}"

    @staticmethod
    def build(config: MigrationConfig) -> str:
        s, d = config.source, config.destination
        source = PgloaderConfigBuilder._connection_url("mssql", s.username, s.password, s.host, s.port, s.database)
        target = PgloaderConfigBuilder._connection_url("postgresql", d.username, d.password, d.host, d.port, d.database, sslmode="require")

        def pgloader_string(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        lines = ["LOAD DATABASE", f"FROM {source}", f"INTO {target}", "", "WITH"]
        options = [f"workers = {config.workers}"]
        if config.mode.value == "schema_only": options.append("schema only")
        if config.mode.value == "data_only": options.append("data only")
        if config.drop_tables: options.insert(0, "include drop")
        lines.extend(f"    {item}" + ("," if i < len(options) - 1 else "") for i, item in enumerate(options))
        table_patterns = ", ".join(pgloader_string(table) for table in config.tables)
        lines.append("")
        lines.append(f"INCLUDING ONLY TABLE NAMES LIKE {table_patterns} IN SCHEMA {pgloader_string(config.schema_name)};")
        return "\n".join(lines)

async def read_lines(stream, level: str, queue: asyncio.Queue, redactions: tuple[str, ...] = ()) -> None:
    while line := await stream.readline():
        message = line.decode(errors="replace").strip()
        for secret in redactions:
            message = message.replace(secret, "[REDACTED]").replace(quote(secret, safe=""), "[REDACTED]")
        await queue.put({"level": level, "component": "pgloader", "message": message})
    await queue.put(None)

class PgloaderService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.processes: dict[str, asyncio.subprocess.Process] = {}

    async def cancel(self, job_id: str) -> None:
        process = self.processes.get(job_id)
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def version(self) -> str:
        process = await asyncio.create_subprocess_exec(self.settings.pgloader_path, "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await process.communicate()
        if process.returncode != 0: raise PgloaderExecutionError("PGLOADER_NOT_FOUND", "pgloader is not available on the server.", retryable=False)
        return stdout.decode().strip()

    async def run(self, config: MigrationConfig, job_id: str) -> AsyncIterator[dict]:
        work_dir = Path(self.settings.migration_work_dir) / job_id
        work_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        load_file = work_dir / "migration.load"
        try:
            load_file.write_text(PgloaderConfigBuilder.build(config), encoding="utf-8")
            os.chmod(load_file, 0o600)
            environment = os.environ.copy()
            # pgloader's MSSQL connector uses FreeTDS, which reads the SQL Server
            # port from TDSPORT rather than reliably honoring a URL port.
            environment["TDSPORT"] = str(config.source.port)
            yield {"level": "INFO", "component": "pgloader", "message": f"Launching pgloader executable: {self.settings.pgloader_path}"}
            try:
                process = await asyncio.create_subprocess_exec(self.settings.pgloader_path, str(load_file), env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            except OSError as exc:
                logger.exception("Unable to launch pgloader for migration %s", job_id)
                raise PgloaderExecutionError("PGLOADER_START_FAILED", "Unable to start pgloader.", f"{type(exc).__name__}: {exc}", retryable=False) from exc
            self.processes[job_id] = process
            logger.info("Started pgloader for migration %s with pid %s", job_id, process.pid)
            yield {"level": "INFO", "component": "pgloader", "message": f"pgloader started (pid {process.pid})"}
            queue: asyncio.Queue = asyncio.Queue()
            redactions = (config.source.password, config.destination.password)
            stdout_task = asyncio.create_task(read_lines(process.stdout, "INFO", queue, redactions))
            stderr_task = asyncio.create_task(read_lines(process.stderr, "ERROR", queue, redactions))
            streams_closed = 0
            while streams_closed < 2:
                entry = await queue.get()
                if entry is None:
                    streams_closed += 1
                else:
                    yield entry
            await asyncio.gather(stdout_task, stderr_task)
            exit_code = await process.wait()
            logger.info("pgloader exited for migration %s with code %s", job_id, exit_code)
            yield {"level": "INFO", "component": "pgloader", "message": f"pgloader exited with code {exit_code}"}
            if exit_code != 0:
                error = PgloaderExecutionError("PGLOADER_FAILED", "pgloader could not complete the migration.", f"Exit code: {exit_code}", retryable=True)
                error.exit_code = exit_code
                raise error
        finally:
            self.processes.pop(job_id, None)
            try: load_file.unlink(missing_ok=True); work_dir.rmdir()
            except OSError: logger.warning("Unable to clean migration work directory", extra={"job_id": job_id})
