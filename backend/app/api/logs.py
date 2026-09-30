from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import FileResponse

from app.api.dependencies import get_current_user, require_admin
from app.errors import AppError
from app.models import User
from app.schemas import LogFileResponse
from app.services.logging import create_log_archive, list_log_files, log_file, write_user_log

router = APIRouter(tags=["logs"])


def _download(request: Request, scope: str, user_id: int | None, filename: str | None, background_tasks: BackgroundTasks):
    if filename:
        path = log_file(request.app.state.settings, scope, filename, user_id)
        if path is None:
            raise AppError("LOG_NOT_FOUND", "日志文件不存在", 404)
        return FileResponse(path, media_type="application/x-ndjson", filename=path.name)
    archive = create_log_archive(request.app.state.settings, scope, user_id)
    background_tasks.add_task(archive.unlink, missing_ok=True)
    return FileResponse(archive, media_type="application/zip", filename="subledger-logs.zip")


@router.get("/api/v1/me/logs", response_model=list[LogFileResponse])
def my_logs(request: Request, user: User = Depends(get_current_user)):
    return list_log_files(request.app.state.settings, "user", user.id)


@router.get("/api/v1/me/logs/download")
def download_my_logs(request: Request, background_tasks: BackgroundTasks, filename: str | None = None, user: User = Depends(get_current_user)):
    response = _download(request, "user", user.id, filename, background_tasks)
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="logs", event="logs_downloaded", request_id=request.state.request_id, message="用户日志已下载", data={"filename": filename})
    return response


@router.get("/api/v1/admin/users/{user_id}/logs", response_model=list[LogFileResponse])
def user_logs(user_id: int, request: Request, admin: User = Depends(require_admin)):
    return list_log_files(request.app.state.settings, "user", user_id)


@router.get("/api/v1/admin/users/{user_id}/logs/download")
def download_user_logs(user_id: int, request: Request, background_tasks: BackgroundTasks, filename: str | None = None, admin: User = Depends(require_admin)):
    response = _download(request, "user", user_id, filename, background_tasks)
    write_user_log(request.app.state.settings, user_id=admin.id, level="INFO", module="logs", event="user_logs_downloaded", request_id=request.state.request_id, message="用户日志已下载", data={"target_user_id": user_id, "filename": filename})
    return response


@router.get("/api/v1/admin/system-logs", response_model=list[LogFileResponse])
def system_logs(request: Request, admin: User = Depends(require_admin)):
    return list_log_files(request.app.state.settings, "system")


@router.get("/api/v1/admin/system-logs/download")
def download_system_logs(request: Request, background_tasks: BackgroundTasks, filename: str | None = None, admin: User = Depends(require_admin)):
    response = _download(request, "system", None, filename, background_tasks)
    write_user_log(request.app.state.settings, user_id=admin.id, level="INFO", module="logs", event="system_logs_downloaded", request_id=request.state.request_id, message="系统日志已下载", data={"filename": filename})
    return response
