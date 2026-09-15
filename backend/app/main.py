from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .core.config import get_settings
from .core.exceptions import AppError
from .core.logging import configure_logging
from .api import health, connections, metadata, migrations
settings = get_settings(); configure_logging(settings.log_level)
app = FastAPI(title="Pgloader Migration Dashboard", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()], allow_origin_regex=r"https?://[^/]+" if settings.app_env == "development" else None, allow_methods=["*"], allow_headers=["*"])
@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError): return JSONResponse(status_code=400, content={"success": False, "error": {"code": exc.code, "message": exc.message, "details": exc.details, "retryable": exc.retryable}})
app.include_router(health.router, prefix="/api"); app.include_router(connections.router, prefix="/api"); app.include_router(metadata.router, prefix="/api"); app.include_router(migrations.router, prefix="/api")
