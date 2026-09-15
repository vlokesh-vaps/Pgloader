from app.schemas.connection import ConnectionRequest
from app.services.sqlserver_service import SqlServerService


def test_sqlserver_connection_string_uses_encryption_and_trusted_certificate():
    config = ConnectionRequest(
        database_type="sqlserver",
        host="sql.example.test",
        port=1433,
        database="source_db",
        username="source_user",
        password="source_password",
    )

    connection_string = SqlServerService._connection_string(config)

    assert "Encrypt=yes" in connection_string
    assert "TrustServerCertificate=yes" in connection_string
    assert "TrustServerCertificate=no" not in connection_string


def test_sqlserver_connection_string_does_not_change_credentials():
    config = ConnectionRequest(
        database_type="sqlserver",
        host="sql.example.test",
        port=1433,
        database="source_db",
        username="source_user",
        password="p;ass word",
    )

    connection_string = SqlServerService._connection_string(config)

    assert "UID=source_user" in connection_string
    assert "PWD=p;ass word" in connection_string
