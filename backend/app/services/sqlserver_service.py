import logging
from ..core.exceptions import ConnectionTestError
from ..schemas.connection import ConnectionRequest

logger = logging.getLogger(__name__)

class SqlServerService:
    def _connect(self, config: ConnectionRequest):
        import pyodbc
        return pyodbc.connect(self._connection_string(config), timeout=config.timeout_seconds)

    @staticmethod
    def _connection_string(config: ConnectionRequest) -> str:
        driver = "ODBC Driver 18 for SQL Server"
        return ";".join([
            f"DRIVER={{{driver}}}",
            f"SERVER={config.host},{config.port}",
            f"DATABASE={config.database}",
            f"UID={config.username}",
            f"PWD={config.password}",
            f"Encrypt={'yes' if config.encrypt else 'no'}",
            "TrustServerCertificate=yes",
        ])

    def test_connection(self, config: ConnectionRequest) -> dict:
        try:
            import pyodbc
            connection = self._connect(config)
            with connection:
                version = connection.execute("SELECT CAST(SERVERPROPERTY('ProductVersion') AS varchar(64))").fetchone()[0]
            return {"success": True, "server_version": str(version), "database": config.database}
        except Exception as exc:
            reason = str(exc).lower()
            logger.warning("SQL Server connection test failed: %s", type(exc).__name__)
            if "login failed" in reason or "authentication" in reason:
                details = "SQL Server rejected the username or password. Verify SQL authentication is enabled."
            elif "certificate" in reason or "ssl" in reason or "encrypt" in reason:
                details = "The encrypted connection could not be verified. Check the SQL Server certificate or encryption settings."
            elif "08001" in reason or "timeout" in reason or "server" in reason:
                details = "The backend could not reach SQL Server. Check the host, TCP port 1433, firewall, and SQL Server TCP/IP settings."
            else:
                details = "The SQL Server driver rejected the connection. Check the ODBC driver and connection settings."
            raise ConnectionTestError("SOURCE_CONNECTION_FAILED", "Unable to connect to the SQL Server.", details, retryable=True) from exc

    def schemas(self, config: ConnectionRequest) -> list[str]:
        try:
            with self._connect(config) as connection:
                rows = connection.execute("SELECT name FROM sys.schemas WHERE name NOT IN ('sys', 'INFORMATION_SCHEMA') ORDER BY name").fetchall()
            return [str(row[0]) for row in rows]
        except Exception as exc:
            raise ConnectionTestError("SOURCE_SCHEMA_LOAD_FAILED", "Unable to load SQL Server schemas.", "Verify the source user has metadata read permission.", retryable=True) from exc

    def tables(self, config: ConnectionRequest, schema: str) -> list[dict]:
        try:
            with self._connect(config) as connection:
                rows = connection.execute("SELECT t.name, SUM(p.rows), CAST(SUM(a.total_pages) * 8.0 / 1024 AS decimal(18,2)) FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id LEFT JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1) LEFT JOIN sys.allocation_units a ON a.container_id=p.partition_id WHERE s.name=? GROUP BY t.name ORDER BY t.name", schema).fetchall()
            return [{"name": str(row[0]), "estimated_rows": int(row[1] or 0), "size_mb": float(row[2] or 0)} for row in rows]
        except Exception as exc:
            raise ConnectionTestError("SOURCE_TABLE_LOAD_FAILED", "Unable to load tables from the selected schema.", "Verify the schema exists and the source user has metadata read permission.", retryable=True) from exc
