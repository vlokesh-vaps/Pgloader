import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, TypeVar

from ..core.exceptions import AssessmentError
from ..schemas.assessment import (
    AssessmentReport,
    AssessmentSection,
    CollationInventory,
    DatabaseSize,
    FlaggedColumn,
    ForeignKeyInventory,
    IdentityColumn,
    LargeTable,
    MigrationOrder,
    ObjectInventory,
    SequenceInventory,
    ServerInfo,
    TableInventory,
)
from ..schemas.connection import ConnectionRequest
from .sqlserver_service import SqlServerService

logger = logging.getLogger(__name__)
T = TypeVar("T")


class SqlServerAssessmentService:
    """Build a compatibility inventory using the existing SQL Server adapter."""

    def __init__(self, sqlserver: SqlServerService | None = None) -> None:
        self.sqlserver = sqlserver or SqlServerService()

    def assess(
        self,
        config: ConnectionRequest,
        downtime_tolerance: str,
        large_table_row_threshold: int = 1_000_000,
        large_table_size_mb_threshold: float = 1_024.0,
    ) -> AssessmentReport:
        """Run every assessment query and return a report with explicit section errors."""
        tables = self._section("tables", lambda: self.list_tables(config))
        table_data = tables.data or []
        foreign_keys = self._section("foreign keys", lambda: self.list_foreign_keys(config))
        foreign_key_data = foreign_keys.data or []
        return AssessmentReport(
            generated_at=datetime.now(timezone.utc),
            database_name=config.database,
            downtime_tolerance=downtime_tolerance,
            large_table_row_threshold=large_table_row_threshold,
            large_table_size_mb_threshold=large_table_size_mb_threshold,
            server=self._section("server", lambda: self.get_server_info(config)),
            database_size=self._section("database size", lambda: self.get_database_size(config)),
            tables=tables,
            row_counts_baseline=AssessmentSection[ list[TableInventory] ](available=tables.available, data=table_data if tables.available else None, error=tables.error),
            views=self._section("views", lambda: self.list_objects(config, "V", "VIEW")),
            stored_procedures=self._section("stored procedures", lambda: self.list_objects(config, "P", "SQL_STORED_PROCEDURE")),
            functions=self._section("functions", lambda: self.list_objects(config, "FN,IF,TF,FS,FT", "FUNCTION")),
            triggers=self._section("triggers", lambda: self.list_triggers(config)),
            sql_agent_jobs=self._section("SQL Agent jobs", lambda: self.list_sql_agent_jobs(config)),
            synonyms=self._section("synonyms", lambda: self.list_objects(config, "SN", "SYNONYM")),
            identity_columns=self._section("identity columns", lambda: self.list_identity_columns(config)),
            sequences=self._section("sequences", lambda: self.list_sequences(config)),
            flagged_columns=self._section("flagged columns", lambda: self.list_flagged_columns(config)),
            collations=self._section("collations", lambda: self.list_collations(config)),
            foreign_keys=foreign_keys,
            safe_migration_order=AssessmentSection(available=tables.available and foreign_keys.available, data=self.build_migration_order(table_data, foreign_key_data) if tables.available and foreign_keys.available else None, error="Tables or foreign keys section unavailable; safe order was not computed." if not (tables.available and foreign_keys.available) else None),
            large_tables=self._section("large tables", lambda: self.find_large_tables(table_data, large_table_row_threshold, large_table_size_mb_threshold)),
            lob_columns=self._section("LOB columns", lambda: self.list_lob_columns(config)),
        )

    def _section(self, name: str, query: Callable[[], T]) -> AssessmentSection[T]:
        """Execute one inventory function and preserve permission/query failures in the report."""
        try:
            return AssessmentSection(available=True, data=query())
        except AssessmentError as exc:
            logger.warning("SQL Server assessment section unavailable: %s", name)
            return AssessmentSection(available=False, error=exc.details or exc.message)
        except Exception as exc:
            logger.exception("Unexpected SQL Server assessment failure: %s", name)
            return AssessmentSection(available=False, error=f"{type(exc).__name__}: {exc}")

    def _fetchall(self, config: ConnectionRequest, query: str, *parameters: Any) -> list[Any]:
        """Execute a read-only SQL Server metadata query through the shared connector."""
        try:
            with self.sqlserver._connect(config) as connection:
                return list(connection.execute(query, *parameters).fetchall())
        except AssessmentError:
            raise
        except Exception as exc:
            raise AssessmentError("SQLSERVER_ASSESSMENT_QUERY_FAILED", "Unable to query SQL Server metadata.", "Verify source metadata permissions and inspect the section-level assessment error.", retryable=True) from exc

    def get_server_info(self, config: ConnectionRequest) -> ServerInfo:
        """Query SQL Server product version and edition from SERVERPROPERTY."""
        rows = self._fetchall(config, "SELECT CAST(SERVERPROPERTY('ProductVersion') AS varchar(64)), CAST(SERVERPROPERTY('Edition') AS nvarchar(256))")
        return ServerInfo(product_version=str(rows[0][0]), edition=str(rows[0][1]))

    def get_database_size(self, config: ConnectionRequest) -> DatabaseSize:
        """Query the total allocated size of the selected database."""
        rows = self._fetchall(config, "SELECT DB_NAME(), CAST(SUM(size) * 8.0 / 1024 AS decimal(18,2)) FROM sys.database_files")
        return DatabaseSize(database_name=str(rows[0][0]), size_mb=float(rows[0][1] or 0))

    def list_tables(self, config: ConnectionRequest) -> list[TableInventory]:
        """Query exact row-count baselines and allocated table sizes."""
        rows = self._fetchall(config, """
            SELECT s.name, t.name, SUM(CASE WHEN ps.index_id IN (0,1) THEN ps.row_count ELSE 0 END),
                   CAST(SUM(ps.used_page_count) * 8.0 / 1024 AS decimal(18,2))
            FROM sys.tables t
            JOIN sys.schemas s ON s.schema_id=t.schema_id
            LEFT JOIN sys.dm_db_partition_stats ps ON ps.object_id=t.object_id
            GROUP BY s.name, t.name ORDER BY s.name, t.name
        """)
        return [TableInventory(schema_name=str(r[0]), table_name=str(r[1]), row_count=int(r[2] or 0), size_mb=float(r[3] or 0)) for r in rows]

    def list_objects(self, config: ConnectionRequest, object_types: str, label: str) -> list[ObjectInventory]:
        """Query named database objects for one object category."""
        types = tuple(object_types.split(","))
        placeholders = ",".join("?" for _ in types)
        rows = self._fetchall(config, f"SELECT s.name, o.name, ? FROM sys.objects o LEFT JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE o.type IN ({placeholders}) ORDER BY s.name, o.name", label, *types)
        return [ObjectInventory(schema_name=str(r[0]) if r[0] is not None else None, object_name=str(r[1]), object_type=str(r[2])) for r in rows]

    def list_triggers(self, config: ConnectionRequest) -> list[ObjectInventory]:
        """Query database and table triggers, including their parent schema/table when available."""
        rows = self._fetchall(config, """
            SELECT s.name, tr.name, CASE WHEN tr.parent_class = 0 THEN 'DATABASE_TRIGGER' ELSE 'TABLE_TRIGGER' END
            FROM sys.triggers tr
            LEFT JOIN sys.tables t ON t.object_id=tr.parent_id
            LEFT JOIN sys.schemas s ON s.schema_id=t.schema_id
            ORDER BY s.name, tr.name
        """)
        return [ObjectInventory(schema_name=str(r[0]) if r[0] is not None else None, object_name=str(r[1]), object_type=str(r[2])) for r in rows]

    def list_sql_agent_jobs(self, config: ConnectionRequest) -> list[ObjectInventory]:
        """Query SQL Agent jobs from msdb; permissions may make this section unavailable."""
        rows = self._fetchall(config, "SELECT CAST(NULL AS nvarchar(128)), name, 'SQL_AGENT_JOB' FROM msdb.dbo.sysjobs ORDER BY name")
        return [ObjectInventory(object_name=str(r[1]), object_type=str(r[2])) for r in rows]

    def list_identity_columns(self, config: ConnectionRequest) -> list[IdentityColumn]:
        """Query identity columns, seeds, and increments from sys.identity_columns."""
        rows = self._fetchall(config, """
            SELECT s.name, t.name, c.name, CONVERT(nvarchar(128), ic.seed_value), CONVERT(nvarchar(128), ic.increment_value)
            FROM sys.identity_columns ic
            JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
            JOIN sys.tables t ON t.object_id=ic.object_id JOIN sys.schemas s ON s.schema_id=t.schema_id
            ORDER BY s.name, t.name, c.name
        """)
        return [IdentityColumn(schema_name=str(r[0]), table_name=str(r[1]), column_name=str(r[2]), seed_value=str(r[3]), increment_value=str(r[4])) for r in rows]

    def list_sequences(self, config: ConnectionRequest) -> list[SequenceInventory]:
        """Query database sequences and their start/increment metadata."""
        rows = self._fetchall(config, "SELECT s.name, seq.name, typ.name, CONVERT(nvarchar(128), seq.start_value), CONVERT(nvarchar(128), seq.increment) FROM sys.sequences seq JOIN sys.schemas s ON s.schema_id=seq.schema_id JOIN sys.types typ ON typ.user_type_id=seq.user_type_id ORDER BY s.name, seq.name")
        return [SequenceInventory(schema_name=str(r[0]), sequence_name=str(r[1]), data_type=str(r[2]), start_value=str(r[3]), increment_value=str(r[4])) for r in rows]

    def list_flagged_columns(self, config: ConnectionRequest) -> list[FlaggedColumn]:
        """Query table columns whose SQL Server types need explicit PostgreSQL mapping."""
        types = ("uniqueidentifier", "datetimeoffset", "money", "smallmoney", "bit", "xml", "varbinary", "geography", "geometry")
        placeholders = ",".join("?" for _ in types)
        rows = self._fetchall(config, f"SELECT s.name, t.name, c.name, typ.name FROM sys.columns c JOIN sys.tables t ON t.object_id=c.object_id JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.types typ ON typ.user_type_id=c.user_type_id WHERE typ.name IN ({placeholders}) ORDER BY s.name, t.name, c.column_id", *types)
        return [FlaggedColumn(schema_name=str(r[0]), table_name=str(r[1]), column_name=str(r[2]), sql_server_type=str(r[3])) for r in rows]

    def list_lob_columns(self, config: ConnectionRequest) -> list[FlaggedColumn]:
        """Query table columns using SQL Server large-object types."""
        types = ("varchar", "nvarchar", "varbinary", "text", "ntext", "image", "xml")
        placeholders = ",".join("?" for _ in types)
        rows = self._fetchall(config, f"SELECT s.name, t.name, c.name, typ.name FROM sys.columns c JOIN sys.tables t ON t.object_id=c.object_id JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.types typ ON typ.user_type_id=c.user_type_id WHERE (typ.name IN ({placeholders}) AND c.max_length = -1) OR typ.name IN ('text','ntext','image','xml') ORDER BY s.name, t.name, c.column_id", *types)
        return [FlaggedColumn(schema_name=str(r[0]), table_name=str(r[1]), column_name=str(r[2]), sql_server_type=str(r[3])) for r in rows]

    def list_collations(self, config: ConnectionRequest) -> list[CollationInventory]:
        """Query database and column collations and flag names containing the case-sensitive marker."""
        rows = self._fetchall(config, """
            SELECT 'DATABASE', NULL, NULL, NULL, CAST(DATABASEPROPERTYEX(DB_NAME(), 'Collation') AS nvarchar(128)),
                   CASE WHEN CHARINDEX('_CS', CAST(DATABASEPROPERTYEX(DB_NAME(), 'Collation') AS nvarchar(128))) > 0 THEN 1 ELSE 0 END
            UNION ALL
            SELECT 'COLUMN', s.name, t.name, c.name, c.collation_name,
                   CASE WHEN CHARINDEX('_CS', c.collation_name) > 0 THEN 1 ELSE 0 END
            FROM sys.columns c JOIN sys.tables t ON t.object_id=c.object_id JOIN sys.schemas s ON s.schema_id=t.schema_id
            WHERE c.collation_name IS NOT NULL ORDER BY 2, 3, 4
        """)
        return [CollationInventory(scope=str(r[0]), schema_name=str(r[1]) if r[1] is not None else None, table_name=str(r[2]) if r[2] is not None else None, column_name=str(r[3]) if r[3] is not None else None, collation_name=str(r[4]), case_sensitive=bool(r[5])) for r in rows]

    def list_foreign_keys(self, config: ConnectionRequest) -> list[ForeignKeyInventory]:
        """Query foreign-key edges used to calculate dependency-safe table order."""
        rows = self._fetchall(config, """
            SELECT fk.name, sch.name, tab.name, rsch.name, rtab.name
            FROM sys.foreign_keys fk JOIN sys.tables tab ON tab.object_id=fk.parent_object_id
            JOIN sys.schemas sch ON sch.schema_id=tab.schema_id JOIN sys.tables rtab ON rtab.object_id=fk.referenced_object_id
            JOIN sys.schemas rsch ON rsch.schema_id=rtab.schema_id ORDER BY sch.name, tab.name, fk.name
        """)
        return [ForeignKeyInventory(constraint_name=str(r[0]), schema_name=str(r[1]), table_name=str(r[2]), referenced_schema_name=str(r[3]), referenced_table_name=str(r[4])) for r in rows]

    @staticmethod
    def build_migration_order(tables: list[TableInventory], foreign_keys: list[ForeignKeyInventory]) -> MigrationOrder:
        """Topologically sort tables so referenced tables precede dependent tables."""
        keys = {f"{table.schema_name}.{table.table_name}" for table in tables}
        dependencies: dict[str, set[str]] = {key: set() for key in keys}
        dependents: dict[str, set[str]] = defaultdict(set)
        for foreign_key in foreign_keys:
            child = f"{foreign_key.schema_name}.{foreign_key.table_name}"
            parent = f"{foreign_key.referenced_schema_name}.{foreign_key.referenced_table_name}"
            if child in dependencies and parent in dependencies and child != parent:
                dependencies[child].add(parent)
                dependents[parent].add(child)
        ready = sorted(key for key, deps in dependencies.items() if not deps)
        order: list[str] = []
        while ready:
            current = ready.pop(0)
            order.append(current)
            for dependent in sorted(dependents[current]):
                dependencies[dependent].discard(current)
                if not dependencies[dependent] and dependent not in order and dependent not in ready:
                    ready.append(dependent)
            ready.sort()
        cycle_tables = sorted(key for key, deps in dependencies.items() if deps)
        return MigrationOrder(table_keys=order, has_cycle=bool(cycle_tables), cycle_tables=cycle_tables)

    @staticmethod
    def find_large_tables(tables: list[TableInventory], row_threshold: int, size_threshold_mb: float) -> list[LargeTable]:
        """Select large tables using caller-provided row and size thresholds."""
        return [LargeTable(schema_name=t.schema_name, table_name=t.table_name, row_count=t.row_count, size_mb=t.size_mb, large_by_rows=t.row_count >= row_threshold, large_by_size=t.size_mb >= size_threshold_mb) for t in tables if t.row_count >= row_threshold or t.size_mb >= size_threshold_mb]
