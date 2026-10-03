from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from app.api import auth, bills, logs, notification_records, notifications, plans, runtime, statistics, users
from app.bootstrap import ensure_bootstrap_admin
from app.config import ConfigError, load_settings
from app.database import Database
from app.errors import AppError, app_error_handler, unexpected_error_handler, validation_error_handler
from app.middleware import RequestContextMiddleware
from app.scheduler import Scheduler
from app.security import LoginFailureLimiter, load_or_create_fernet_key
from app.services.logging import write_system_log
from app.services.notification_verification import NotificationVerification


def create_app(settings=None) -> FastAPI:
    settings = settings or load_settings()
    database = Database(settings)
    fernet = load_or_create_fernet_key(settings.security.secret_key_file)
    scheduler = Scheduler(settings, database, fernet)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.wait_for_connection()
        database.run_migrations()
        with database.session() as db:
            ensure_bootstrap_admin(db, settings)
        scheduler.start()
        write_system_log(settings, level="INFO", module="system", event="application_started", request_id=None, message="应用启动成功")
        try:
            yield
        finally:
            scheduler.shutdown()
            database.dispose()
            write_system_log(settings, level="INFO", module="system", event="application_stopped", request_id=None, message="应用已停止")

    app = FastAPI(title="SubLedger", version="0.1.8", lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database
    app.state.fernet = fernet
    app.state.scheduler = scheduler
    app.state.login_limiter = LoginFailureLimiter()
    app.state.notification_verification = NotificationVerification()
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(plans.router)
    app.include_router(bills.router)
    app.include_router(statistics.router)
    app.include_router(notifications.router)
    app.include_router(logs.router)
    app.include_router(runtime.router)
    app.include_router(notification_records.router)

    @app.get("/health")
    def health(request: Request):
        db_ok = request.app.state.database.check_connection()
        scheduler_obj = request.app.state.scheduler
        scheduler_status = scheduler_obj.snapshot()["status"]
        scheduler_ok = scheduler_status != "error"
        status = "ok" if db_ok and scheduler_ok else "degraded"
        return JSONResponse(
            status_code=200 if status == "ok" else 503,
            content={
                "status": status,
                "application": "ok",
                "database": "ok" if db_ok else "error",
                "scheduler": scheduler_status,
            },
        )

    static_dir = Path(os.getenv("SUBLEDGER_STATIC_DIR", "/app/static"))
    index_file = static_dir / "index.html"
    reserved_prefixes = ("/api/", "/health/", "/docs/", "/redoc/", "/openapi.json/")
    reserved_exact = ("/api", "/health", "/docs", "/redoc", "/openapi.json", "/assets")

    @app.get("/{path:path}", include_in_schema=False)
    @app.head("/{path:path}", include_in_schema=False)
    def frontend_fallback(path: str, request: Request):
        requested = "/" + path
        candidate = (static_dir / path).resolve()
        is_static_file = (
            static_dir.exists()
            and candidate.is_file()
            and static_dir.resolve() in candidate.parents
        )
        if requested.startswith("/assets/"):
            if not is_static_file:
                return JSONResponse(status_code=404, content={"detail": "Not Found"})
            response = FileResponse(candidate)
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response
        if requested in reserved_exact or requested.startswith(reserved_prefixes):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        if is_static_file:
            response = FileResponse(candidate)
            response.headers["Cache-Control"] = "no-cache"
            return response
        accepts_html = "text/html" in request.headers.get("accept", "")
        if (
            request.method in {"GET", "HEAD"}
            and accepts_html
            and "." not in Path(path).name
            and index_file.is_file()
        ):
            response = FileResponse(index_file)
            response.headers["Cache-Control"] = "no-cache"
            return response
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    return app


try:
    app = create_app()
except ConfigError:
    app = None
