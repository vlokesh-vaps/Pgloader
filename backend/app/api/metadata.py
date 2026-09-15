from fastapi import APIRouter, Header, HTTPException, Query
from .connections import connection_tokens
from ..services.sqlserver_service import SqlServerService
router = APIRouter(prefix="/source")
@router.get("/schemas")
def schemas(x_connection_token: str | None = Header(default=None)):
    config = connection_tokens.get(x_connection_token or "")
    if not config: raise HTTPException(401, "A successful source connection test is required")
    return {"schemas": SqlServerService().schemas(config)}
@router.get("/tables")
def tables(schema: str = Query(..., min_length=1), x_connection_token: str | None = Header(default=None)):
    config = connection_tokens.get(x_connection_token or "")
    if not config: raise HTTPException(401, "A successful source connection test is required")
    return {"schema": schema, "tables": SqlServerService().tables(config, schema)}
