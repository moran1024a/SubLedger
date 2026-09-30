from __future__ import annotations

import secrets
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.logging import write_system_log


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or secrets.token_hex(16)
        request.state.request_id = request_id
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            write_system_log(
                request.app.state.settings,
                level="ERROR",
                module="http",
                event="request_failed",
                request_id=request_id,
                message="HTTP request failed",
                data={"method": request.method, "path": request.url.path},
            )
            raise
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        write_system_log(
            request.app.state.settings,
            level="INFO",
            module="http",
            event="request_completed",
            request_id=request_id,
            message="HTTP request completed",
            data={"method": request.method, "path": request.url.path, "status": response.status_code, "duration_ms": duration_ms},
        )
        return response
