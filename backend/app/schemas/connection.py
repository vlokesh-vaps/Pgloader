from typing import Literal
from pydantic import BaseModel, Field

class ConnectionRequest(BaseModel):
    database_type: Literal["sqlserver", "postgresql"]
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)
    encrypt: bool = True
    ssl_mode: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)

class ConnectionTestResponse(BaseModel):
    success: bool
    server_version: str | None = None
    database: str | None = None
    latency_ms: int | None = None
    connection_token: str | None = None
