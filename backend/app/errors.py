from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "request_id": _request_id(request)},
    )


def validation_field_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    errors = []
    for item in exc.errors():
        location = list(item.get("loc", ()))
        if location and location[0] in {"body", "path", "query"}:
            location = location[1:]
        errors.append(
            {
                "field": ".".join(str(part) for part in location),
                "message": str(item.get("msg", "请求参数格式错误")),
            }
        )
    return errors


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "INVALID_REQUEST",
            "message": "请求参数格式错误",
            "request_id": _request_id(request),
            "errors": validation_field_errors(exc),
        },
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "服务内部错误", "request_id": _request_id(request)},
    )
