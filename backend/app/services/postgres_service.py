from ..core.exceptions import ConnectionTestError
from ..schemas.connection import ConnectionRequest

class PostgresService:
    def test_connection(self, config: ConnectionRequest) -> dict:
        try:
            import psycopg
            with psycopg.connect(host=config.host, port=config.port, dbname=config.database, user=config.username, password=config.password, connect_timeout=config.timeout_seconds, sslmode=config.ssl_mode or "prefer") as connection:
                version = connection.execute("SELECT version()").fetchone()[0]
            return {"success": True, "server_version": str(version), "database": config.database}
        except Exception as exc:
            raise ConnectionTestError("DESTINATION_CONNECTION_FAILED", "Unable to connect to PostgreSQL.", "Check host, port, credentials, SSL mode, and firewall access.", retryable=True) from exc
