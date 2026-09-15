from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest

from app.core.exceptions import AssessmentError
from app.schemas.assessment import AssessmentRequest, ForeignKeyInventory, TableInventory
from app.services.sqlserver_assessment_service import SqlServerAssessmentService


class FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class FakeConnection:
    def __init__(self, responder: Callable[..., list[tuple[Any, ...]]]) -> None:
        self.responder = responder

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        return None

    def execute(self, query: str, *parameters: Any) -> FakeCursor:
        return FakeCursor(self.responder(query, *parameters))


def source_request() -> AssessmentRequest:
    return AssessmentRequest.model_validate({
        "source": {"database_type": "sqlserver", "host": "sql", "port": 1433, "database": "inventory", "username": "reader", "password": "secret"},
        "downtime_tolerance": "4 hours",
    })


def responder(query: str, *parameters: Any) -> list[tuple[Any, ...]]:
    if "SERVERPROPERTY" in query:
        return [("16.0.1000.6", "Developer Edition")]
    if "sys.database_files" in query:
        return [("inventory", 128.5)]
    if "dm_db_partition_stats" in query:
        return [("dbo", "orders", 2_000_000, 2048.0), ("dbo", "customers", 50, 2.0)]
    if "sys.triggers" in query:
        return [("dbo", "trg_orders", "TABLE_TRIGGER")]
    if "msdb.dbo.sysjobs" in query:
        return [(None, "Nightly ETL", "SQL_AGENT_JOB")]
    if "sys.identity_columns" in query:
        return [("dbo", "orders", "id", "1", "1")]
    if "sys.sequences" in query:
        return [("dbo", "order_sequence", "bigint", "1", "1")]
    if "DATABASEPROPERTYEX" in query:
        return [("DATABASE", None, None, None, "SQL_Latin1_General_CP1_CI_AS", 0), ("COLUMN", "dbo", "orders", "code", "Latin1_General_100_CS_AS", 1)]
    if "sys.foreign_keys" in query:
        return [("FK_orders_customers", "dbo", "orders", "dbo", "customers")]
    if "c.max_length" in query:
        return [("dbo", "orders", "payload", "varbinary")]
    if "typ.name IN" in query:
        return [("dbo", "orders", "customer_id", "uniqueidentifier")]
    if "o.type IN" in query:
        label = str(parameters[0])
        return [("dbo", f"sample_{label.lower()}", label)]
    raise AssertionError(f"Unhandled query: {query}")


def test_each_inventory_query_and_report_sections() -> None:
    service = SqlServerAssessmentService()
    fake_connection = FakeConnection(responder)
    with patch.object(service.sqlserver, "_connect", return_value=fake_connection):
        report = service.assess(source_request().source, "4 hours")

    assert report.server.data is not None
    assert report.server.data.edition == "Developer Edition"
    assert report.database_size.data is not None
    assert report.tables.data is not None and report.tables.data[0].row_count == 2_000_000
    assert report.row_counts_baseline.data == report.tables.data
    assert report.views.data and report.stored_procedures.data and report.functions.data
    assert report.triggers.data and report.sql_agent_jobs.data and report.synonyms.data
    assert report.identity_columns.data and report.sequences.data
    assert report.flagged_columns.data and report.lob_columns.data
    assert report.collations.data and any(item.case_sensitive for item in report.collations.data)
    assert report.foreign_keys.data and report.safe_migration_order.data
    assert report.safe_migration_order.data.table_keys == ["dbo.customers", "dbo.orders"]
    assert report.large_tables.data and report.large_tables.data[0].table_name == "orders"
    assert "# SQL Server Compatibility Assessment" in report.to_markdown()


def test_unavailable_inventory_section_is_explicit() -> None:
    service = SqlServerAssessmentService()

    def fail(_: Any) -> Any:
        raise AssessmentError("DENIED", "metadata unavailable", "Permission denied on metadata view.")

    with patch.object(service.sqlserver, "_connect", side_effect=fail):
        report = service.assess(source_request().source, "unknown")

    assert report.server.available is False
    assert report.server.data is None
    assert report.server.error == "Permission denied on metadata view."


def test_cyclic_foreign_keys_are_reported() -> None:
    service = SqlServerAssessmentService()
    result = service.build_migration_order(
        [
            TableInventory(schema_name="dbo", table_name="a", row_count=1, size_mb=1),
            TableInventory(schema_name="dbo", table_name="b", row_count=1, size_mb=1),
        ],
        [
            ForeignKeyInventory(constraint_name="fk_a_b", schema_name="dbo", table_name="a", referenced_schema_name="dbo", referenced_table_name="b"),
            ForeignKeyInventory(constraint_name="fk_b_a", schema_name="dbo", table_name="b", referenced_schema_name="dbo", referenced_table_name="a"),
        ],
    )
    assert result.has_cycle is True
    assert result.cycle_tables == ["dbo.a", "dbo.b"]
