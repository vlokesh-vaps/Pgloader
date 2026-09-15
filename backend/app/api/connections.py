import time
from uuid import uuid4
from fastapi import APIRouter
from ..schemas.connection import ConnectionRequest, ConnectionTestResponse
from ..services.sqlserver_service import SqlServerService
from ..services.postgres_service import PostgresService

router = APIRouter(prefix="/connections")
connection_tokens: dict[str, ConnectionRequest] = {}
@router.post("/{role}/test", response_model=ConnectionTestResponse)
def test_connection(role: str, request: ConnectionRequest):
    started = time.perf_counter()
    if role == "source" and request.database_type == "sqlserver":
        result = SqlServerService().test_connection(request)
    elif role == "destination" and request.database_type == "postgresql":
        result = PostgresService().test_connection(request)
    else:
        return ConnectionTestResponse(success=False, database=request.database, latency_ms=round((time.perf_counter()-started)*1000))
    token = uuid4().hex
    connection_tokens[token] = request
    return ConnectionTestResponse(**result, connection_token=token, latency_ms=round((time.perf_counter()-started)*1000))
