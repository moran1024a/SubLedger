from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

_SENSITIVE_KEYS = re.compile(r"password|token|cookie|webhook|secret|authorization", re.IGNORECASE)


def _sanitize(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SENSITIVE_KEYS.search(str(key)) else _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


def _write(directory: str, scope: str, user_id: int | None, level: str, module: str, event: str, request_id: str | None, message: str, data: dict | None) -> None:
    now = datetime.now(timezone.utc)
    if scope == "system":
        target = Path(directory) / "system"
    else:
        if user_id is None:
            return
        target = Path(directory) / "users" / str(user_id)
    record = {
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "level": level,
        "module": module,
        "event": event,
        "request_id": request_id,
        "user_id": user_id,
        "result": "failure" if level in {"ERROR", "CRITICAL"} or (data and data.get("status", 0) >= 400) else "success",
        "message": message,
        "data": _sanitize(data or {}),
    }
    try:
        target.mkdir(parents=True, exist_ok=True)
        with (target / f"{now.date().isoformat()}.log").open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except (OSError, UnicodeError) as exc:
        # A committed operation must not look unsuccessful because its log disk failed.
        # Retain the sanitized event on stderr without exposing paths or exception text.
        record["log_write_error"] = type(exc).__name__
        try:
            print(json.dumps(record, ensure_ascii=True, separators=(",", ":")), file=sys.stderr)
        except (OSError, ValueError):
            pass


def write_system_log(settings, *, level: str, module: str, event: str, request_id: str | None, message: str, data: dict | None = None) -> None:
    _write(settings.logging.directory, "system", None, level, module, event, request_id, message, data)


def write_user_log(settings, *, user_id: int, level: str, module: str, event: str, request_id: str | None, message: str, data: dict | None = None) -> None:
    _write(settings.logging.directory, "user", user_id, level, module, event, request_id, message, data)


def _files(directory: str, scope: str, user_id: int | None = None) -> list[Path]:
    if scope == "system":
        root = Path(directory) / "system"
    else:
        if user_id is None:
            return []
        root = Path(directory) / "users" / str(user_id)
    if not root.exists():
        return []
    return sorted((path for path in root.glob("*.log") if path.is_file()), reverse=True)


def list_log_files(settings, scope: str, user_id: int | None = None) -> list[dict]:
    files = []
    for path in _files(settings.logging.directory, scope, user_id):
        stat = path.stat()
        files.append(
            {
                "date": path.stem,
                "filename": path.name,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc),
            }
        )
    return files


def log_file(settings, scope: str, filename: str, user_id: int | None = None) -> Path | None:
    if Path(filename).name != filename or not filename.endswith(".log"):
        return None
    path = next((item for item in _files(settings.logging.directory, scope, user_id) if item.name == filename), None)
    return path


def create_log_archive(settings, scope: str, user_id: int | None = None) -> Path:
    import tempfile

    files = _files(settings.logging.directory, scope, user_id)
    fd, archive_name = tempfile.mkstemp(prefix="subledger-logs-", suffix=".zip")
    os.close(fd)
    archive = Path(archive_name)
    with ZipFile(archive, "w", ZIP_DEFLATED) as zip_file:
        for path in files:
            zip_file.write(path, arcname=path.name)
    return archive


def cleanup_logs(settings) -> int:
    cutoff = datetime.now(timezone.utc).date().toordinal() - settings.logging.retention_days + 1
    removed = 0
    root = Path(settings.logging.directory)
    for path in root.glob("system/*.log"):
        removed += _remove_if_expired(path, cutoff)
    for path in root.glob("users/*/*.log"):
        removed += _remove_if_expired(path, cutoff)
    return removed


def _remove_if_expired(path: Path, cutoff: int) -> int:
    try:
        file_date = date.fromisoformat(path.stem)
    except ValueError:
        return 0
    if file_date.toordinal() < cutoff:
        path.unlink(missing_ok=True)
        return 1
    return 0
