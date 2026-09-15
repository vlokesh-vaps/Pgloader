from app.schemas.migration import MigrationConfig
from app.services.pgloader_service import PgloaderConfigBuilder
from urllib.parse import unquote, urlsplit


def test_postgresql_destination_requires_ssl_and_preserves_special_characters():
    password = "p@ss:w/rd#x?y%z&a"
    config = MigrationConfig.model_validate({
        "source": {
            "database_type": "sqlserver",
            "host": "source",
            "port": 1433,
            "database": "source_db",
            "username": "source_user",
            "password": "source_password",
        },
        "destination": {
            "database_type": "postgresql",
            "host": "ivrm.postgres.database.azure.com",
            "port": 5432,
            "database": "IVRM_NEW_ARCH",
            "username": "VapsPSQL",
            "password": password,
        },
        "schema": "dbo",
        "tables": ["users"],
    })

    load_file = PgloaderConfigBuilder.build(config)
    target = next(line.removeprefix("INTO ") for line in load_file.splitlines() if line.startswith("INTO "))
    parsed = urlsplit(target)

    assert parsed.scheme == "postgresql"
    assert parsed.hostname == "ivrm.postgres.database.azure.com"
    assert parsed.port == 5432
    assert parsed.path == "/IVRM_NEW_ARCH"
    assert parsed.query == "sslmode=require"
    assert parsed.username == "VapsPSQL"
    assert unquote(parsed.password) == password
    assert "%40" in target and "%23" in target and "%25" in target and "%3A" in target and "%2F" in target and "%3F" in target
    assert password not in load_file
