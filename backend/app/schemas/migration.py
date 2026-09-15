from datetime import datetime
from enum import StrEnum
from typing import Annotated
from pydantic import BaseModel, Field, model_validator
from .connection import ConnectionRequest

class MigrationStatus(StrEnum):
    QUEUED = "QUEUED"; PRECHECK = "PRECHECK"; STARTING = "STARTING"; RUNNING = "RUNNING"; COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELLED = "CANCELLED"

class MigrationMode(StrEnum):
    SCHEMA_DATA = "schema_and_data"; SCHEMA_ONLY = "schema_only"; DATA_ONLY = "data_only"

class MigrationConfig(BaseModel):
    source: ConnectionRequest
    destination: ConnectionRequest
    schema_name: Annotated[str, Field(alias="schema", min_length=1, max_length=255)]
    tables: list[str] = Field(min_length=1, max_length=500)
    mode: MigrationMode = MigrationMode.SCHEMA_DATA
    workers: int = Field(default=4, ge=1, le=32)
    drop_tables: bool = False
    confirmation: bool = False

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def require_confirmation_for_destructive(self):
        if self.drop_tables and not self.confirmation: raise ValueError("Explicit confirmation is required when drop_tables is enabled")
        return self

class MigrationJob(BaseModel):
    id: str
    status: MigrationStatus
    source_type: str
    source_database: str
    destination_type: str
    destination_database: str
    selected_schema: str
    selected_tables: list[str]
    migration_mode: MigrationMode
    workers: int
    drop_tables: bool
    started_at: datetime | None = None
    completed_at: datetime | None = None
    rows_processed: int = 0
    tables_processed: int = 0
    tables_failed: int = 0
    error_count: int = 0
    error: str | None = None
    exit_code: int | None = None
    failure_reason: str | None = None
