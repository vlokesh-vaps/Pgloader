from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    pgloader_path: str = "pgloader"
    database_url: str = "sqlite:///./pgloader-dashboard.db"
    migration_work_dir: Path = Path("./.pgloader-jobs")
    max_workers: int = 8
    source_connection_timeout: int = 30
    target_connection_timeout: int = 30
    migration_timeout: int = 3600
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://172.16.10.187:5173"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    settings = Settings(); settings.migration_work_dir.mkdir(parents=True, exist_ok=True); return settings
