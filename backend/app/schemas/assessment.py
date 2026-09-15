from datetime import datetime
from typing import Any, Callable, Generic, TypeVar

from pydantic import BaseModel, Field

from .connection import ConnectionRequest


T = TypeVar("T")


class AssessmentRequest(BaseModel):
    """Input for an assessment; downtime tolerance must be supplied by the caller."""

    source: ConnectionRequest
    downtime_tolerance: str = Field(min_length=1, max_length=255)
    large_table_row_threshold: int = Field(default=1_000_000, ge=1)
    large_table_size_mb_threshold: float = Field(default=1_024.0, ge=0)


class AssessmentSection(BaseModel, Generic[T]):
    """One independently queried assessment section and its availability."""

    available: bool
    data: T | None = None
    error: str | None = None


class ServerInfo(BaseModel):
    product_version: str
    edition: str


class DatabaseSize(BaseModel):
    database_name: str
    size_mb: float


class TableInventory(BaseModel):
    schema_name: str
    table_name: str
    row_count: int
    size_mb: float


class ObjectInventory(BaseModel):
    schema_name: str | None = None
    object_name: str
    object_type: str


class IdentityColumn(BaseModel):
    schema_name: str
    table_name: str
    column_name: str
    seed_value: str
    increment_value: str


class SequenceInventory(BaseModel):
    schema_name: str
    sequence_name: str
    data_type: str
    start_value: str
    increment_value: str


class FlaggedColumn(BaseModel):
    schema_name: str
    table_name: str
    column_name: str
    sql_server_type: str
    postgres_mapping_required: bool = True


class CollationInventory(BaseModel):
    scope: str
    schema_name: str | None = None
    table_name: str | None = None
    column_name: str | None = None
    collation_name: str
    case_sensitive: bool


class ForeignKeyInventory(BaseModel):
    constraint_name: str
    schema_name: str
    table_name: str
    referenced_schema_name: str
    referenced_table_name: str


class MigrationOrder(BaseModel):
    table_keys: list[str]
    has_cycle: bool
    cycle_tables: list[str] = Field(default_factory=list)


class LargeTable(BaseModel):
    schema_name: str
    table_name: str
    row_count: int
    size_mb: float
    large_by_rows: bool
    large_by_size: bool


class AssessmentReport(BaseModel):
    """Versioned SQL Server inventory and PostgreSQL compatibility report."""

    report_version: str = "1.0"
    generated_at: datetime
    database_name: str
    downtime_tolerance: str
    large_table_row_threshold: int
    large_table_size_mb_threshold: float
    server: AssessmentSection[ServerInfo]
    database_size: AssessmentSection[DatabaseSize]
    tables: AssessmentSection[list[TableInventory]]
    row_counts_baseline: AssessmentSection[list[TableInventory]]
    views: AssessmentSection[list[ObjectInventory]]
    stored_procedures: AssessmentSection[list[ObjectInventory]]
    functions: AssessmentSection[list[ObjectInventory]]
    triggers: AssessmentSection[list[ObjectInventory]]
    sql_agent_jobs: AssessmentSection[list[ObjectInventory]]
    synonyms: AssessmentSection[list[ObjectInventory]]
    identity_columns: AssessmentSection[list[IdentityColumn]]
    sequences: AssessmentSection[list[SequenceInventory]]
    flagged_columns: AssessmentSection[list[FlaggedColumn]]
    collations: AssessmentSection[list[CollationInventory]]
    foreign_keys: AssessmentSection[list[ForeignKeyInventory]]
    safe_migration_order: AssessmentSection[MigrationOrder]
    large_tables: AssessmentSection[list[LargeTable]]
    lob_columns: AssessmentSection[list[FlaggedColumn]]

    def to_markdown(self) -> str:
        """Render this report as a readable Markdown summary without credentials."""
        lines = [
            f"# SQL Server Compatibility Assessment",
            "",
            f"- Report version: `{self.report_version}`",
            f"- Generated at: `{self.generated_at.isoformat()}`",
            f"- Database: `{self.database_name}`",
            f"- Application downtime tolerance: {self.downtime_tolerance}",
            "",
        ]
        self._markdown_section(lines, "SQL Server", self.server, self._format_server)
        self._markdown_section(lines, "Database size", self.database_size, self._format_database_size)
        self._markdown_section(lines, "Tables and row-count baseline", self.tables, self._format_tables)
        for title, section in (
            ("Views", self.views),
            ("Stored procedures", self.stored_procedures),
            ("Functions", self.functions),
            ("Triggers", self.triggers),
            ("SQL Agent jobs", self.sql_agent_jobs),
            ("Synonyms", self.synonyms),
        ):
            self._markdown_section(lines, title, section, self._format_objects)
        self._markdown_section(lines, "Identity columns", self.identity_columns, self._format_identity)
        self._markdown_section(lines, "Sequences", self.sequences, self._format_sequences)
        self._markdown_section(lines, "Columns requiring explicit PostgreSQL mapping", self.flagged_columns, self._format_flagged)
        self._markdown_section(lines, "Collations", self.collations, self._format_collations)
        self._markdown_section(lines, "Foreign keys", self.foreign_keys, self._format_foreign_keys)
        self._markdown_section(lines, "Safe migration order", self.safe_migration_order, self._format_order)
        self._markdown_section(lines, "Large tables", self.large_tables, self._format_large_tables)
        self._markdown_section(lines, "LOB columns", self.lob_columns, self._format_flagged)
        return "\n".join(lines)

    @staticmethod
    def _markdown_section(lines: list[str], title: str, section: AssessmentSection[T], formatter: Callable[[Any], str]) -> None:
        lines.extend([f"## {title}", ""])
        if not section.available:
            lines.extend([f"Unavailable: {section.error}", ""])
            return
        formatted = formatter(section.data)
        lines.extend([formatted or "None found.", ""])

    @staticmethod
    def _format_server(data: ServerInfo | None) -> str:
        return f"- Version: `{data.product_version}`\n- Edition: `{data.edition}`" if data else ""

    @staticmethod
    def _format_database_size(data: DatabaseSize | None) -> str:
        return f"- `{data.database_name}`: {data.size_mb:.2f} MB" if data else ""

    @staticmethod
    def _format_tables(data: list[TableInventory] | None) -> str:
        return "\n".join(f"- `{item.schema_name}.{item.table_name}`: {item.row_count} rows, {item.size_mb:.2f} MB" for item in data or [])

    @staticmethod
    def _format_objects(data: list[ObjectInventory] | None) -> str:
        return "\n".join(f"- `{item.schema_name + '.' if item.schema_name else ''}{item.object_name}`" for item in data or [])

    @staticmethod
    def _format_identity(data: list[IdentityColumn] | None) -> str:
        return "\n".join(f"- `{item.schema_name}.{item.table_name}.{item.column_name}` seed `{item.seed_value}`, increment `{item.increment_value}`" for item in data or [])

    @staticmethod
    def _format_sequences(data: list[SequenceInventory] | None) -> str:
        return "\n".join(f"- `{item.schema_name}.{item.sequence_name}` type `{item.data_type}`, start `{item.start_value}`, increment `{item.increment_value}`" for item in data or [])

    @staticmethod
    def _format_flagged(data: list[FlaggedColumn] | None) -> str:
        return "\n".join(f"- `{item.schema_name}.{item.table_name}.{item.column_name}`: `{item.sql_server_type}`" for item in data or [])

    @staticmethod
    def _format_collations(data: list[CollationInventory] | None) -> str:
        return "\n".join(f"- {item.scope}: `{item.collation_name}` (case-sensitive: `{item.case_sensitive}`)" for item in data or [])

    @staticmethod
    def _format_foreign_keys(data: list[ForeignKeyInventory] | None) -> str:
        return "\n".join(f"- `{item.schema_name}.{item.table_name}` → `{item.referenced_schema_name}.{item.referenced_table_name}` ({item.constraint_name})" for item in data or [])

    @staticmethod
    def _format_order(data: MigrationOrder | None) -> str:
        if not data:
            return ""
        result = f"- Order: {' → '.join(data.table_keys) or 'None'}\n- Cycle detected: `{data.has_cycle}`"
        return result + (f"\n- Cycle tables: {', '.join(data.cycle_tables)}" if data.cycle_tables else "")

    @staticmethod
    def _format_large_tables(data: list[LargeTable] | None) -> str:
        return "\n".join(f"- `{item.schema_name}.{item.table_name}`: {item.row_count} rows, {item.size_mb:.2f} MB" for item in data or [])
