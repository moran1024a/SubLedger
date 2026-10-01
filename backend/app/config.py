from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field
from typing import get_type_hints

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    timezone: str
    session_expire_days: int


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    username: str
    password: str
    database: str
    charset: str
    pool_size: int
    max_overflow: int
    pool_recycle: int
    pool_timeout: int
    connect_timeout: int


@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool
    bill_check_hour: int
    bill_check_minute: int
    notification_interval_seconds: int
    log_cleanup_hour: int
    session_cleanup_hour: int = 2
    task_timeout_seconds: int = 900


@dataclass(frozen=True)
class LoggingConfig:
    directory: str
    retention_days: int
    level: str


@dataclass(frozen=True)
class SecurityConfig:
    secret_key_file: str
    cookie_secure: bool
    cookie_name: str
    smtp_allowed_hosts: tuple[str, ...] = ()
    smtp_allow_private_hosts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BootstrapAdminConfig:
    username: str
    password: str


@dataclass(frozen=True)
class NotificationConfig:
    dns_timeout_seconds: int = 5
    connect_timeout_seconds: int = 5
    send_timeout_seconds: int = 30


@dataclass(frozen=True)
class Settings:
    app: AppConfig
    database: DatabaseConfig
    scheduler: SchedulerConfig
    logging: LoggingConfig
    security: SecurityConfig
    bootstrap_admin: BootstrapAdminConfig
    config_path: Path
    notifications: NotificationConfig = field(default_factory=NotificationConfig)


def _require(data: dict, section: str, key: str):
    value = data.get(section, {}).get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ConfigError(f"[{section}].{key} is required")
    return value


def _smtp_hosts(data: dict, key: str) -> tuple[str, ...]:
    from app.services.outbound import normalize_host

    values = data.get("security", {}).get(key, [])
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise ConfigError(f"security.{key} must be an array of host names or IP addresses")
    try:
        return tuple(normalize_host(item) for item in values)
    except (ValueError, UnicodeError) as exc:
        raise ConfigError(f"security.{key} contains an invalid host") from exc


def _default_config_path() -> Path:
    candidates = (
        Path.cwd() / "config" / "config.toml",
        Path(__file__).resolve().parents[1] / "config" / "config.toml",
        Path("/app/config/config.toml"),
    )
    return next(
        (candidate for candidate in candidates if candidate.is_file()),
        candidates[0],
    )


def load_settings(path: str | Path | None = None) -> Settings:
    configured_path = os.getenv("SUBLEDGER_CONFIG")
    if path is not None:
        config_path = Path(path)
    elif configured_path:
        config_path = Path(configured_path)
    else:
        config_path = _default_config_path()
    try:
        with config_path.open("rb") as config_file:
            data = tomllib.load(config_file)
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file does not exist: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML configuration: {exc}") from exc

    expected = {
        "app": AppConfig,
        "database": DatabaseConfig,
        "scheduler": SchedulerConfig,
        "logging": LoggingConfig,
        "security": SecurityConfig,
        "bootstrap_admin": BootstrapAdminConfig,
        "notifications": NotificationConfig,
    }
    for section, cls in expected.items():
        values = data.get(section, {})
        if not isinstance(values, dict):
            raise ConfigError(f"[{section}] must be a table")
        for key, kind in get_type_hints(cls).items():
            if key in values and kind in (str, int, bool) and type(values[key]) is not kind:
                raise ConfigError(f"[{section}].{key} must be {kind.__name__}")
    for key in ("host", "port"):
        if key in data.get("app", {}):
            warnings.warn(f"app.{key} is deprecated and ignored; configure the ASGI server binding instead", UserWarning, stacklevel=2)
    app = AppConfig(
        host="0.0.0.0",
        port=8000,
        timezone=str(data.get("app", {}).get("timezone", "UTC")),
        session_expire_days=int(data.get("app", {}).get("session_expire_days", 7)),
    )
    database = DatabaseConfig(
        host=str(_require(data, "database", "host")),
        port=int(_require(data, "database", "port")),
        username=str(_require(data, "database", "username")),
        password=str(_require(data, "database", "password")),
        database=str(_require(data, "database", "database")),
        charset=str(data.get("database", {}).get("charset", "utf8mb4")),
        pool_size=int(data.get("database", {}).get("pool_size", 5)),
        max_overflow=int(data.get("database", {}).get("max_overflow", 5)),
        pool_recycle=int(data.get("database", {}).get("pool_recycle", 1800)),
        pool_timeout=int(data.get("database", {}).get("pool_timeout", 10)),
        connect_timeout=int(data.get("database", {}).get("connect_timeout", 10)),
    )
    scheduler = SchedulerConfig(
        enabled=bool(data.get("scheduler", {}).get("enabled", True)),
        bill_check_hour=int(data.get("scheduler", {}).get("bill_check_hour", 0)),
        bill_check_minute=int(data.get("scheduler", {}).get("bill_check_minute", 5)),
        notification_interval_seconds=int(
            data.get("scheduler", {}).get("notification_interval_seconds", 60)
        ),
        log_cleanup_hour=int(data.get("scheduler", {}).get("log_cleanup_hour", 1)),
        session_cleanup_hour=data.get("scheduler", {}).get("session_cleanup_hour", 2),
        task_timeout_seconds=data.get("scheduler", {}).get("task_timeout_seconds", 900),
    )
    logging = LoggingConfig(
        directory=str(data.get("logging", {}).get("directory", "/app/logs")),
        retention_days=int(data.get("logging", {}).get("retention_days", 4)),
        level=str(data.get("logging", {}).get("level", "INFO")).upper(),
    )
    security = SecurityConfig(
        secret_key_file=str(_require(data, "security", "secret_key_file")),
        cookie_secure=bool(data.get("security", {}).get("cookie_secure", False)),
        cookie_name=str(_require(data, "security", "cookie_name")),
        smtp_allowed_hosts=_smtp_hosts(data, "smtp_allowed_hosts"),
        smtp_allow_private_hosts=_smtp_hosts(data, "smtp_allow_private_hosts"),
    )
    bootstrap_admin = BootstrapAdminConfig(
        username=str(_require(data, "bootstrap_admin", "username")),
        password=str(_require(data, "bootstrap_admin", "password")),
    )
    settings = Settings(
        app=app,
        database=database,
        scheduler=scheduler,
        logging=logging,
        security=security,
        bootstrap_admin=bootstrap_admin,
        config_path=config_path,
        notifications=NotificationConfig(**{key: data.get("notifications", {}).get(key, default) for key, default in (("dns_timeout_seconds", 5), ("connect_timeout_seconds", 5), ("send_timeout_seconds", 30))}),
    )
    validate_settings(settings)
    return settings


def validate_settings(settings: Settings) -> None:
    if not 1 <= settings.app.port <= 65535:
        raise ConfigError("app.port must be between 1 and 65535")
    try:
        ZoneInfo(settings.app.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError("app.timezone is invalid") from exc
    if settings.app.session_expire_days <= 0:
        raise ConfigError("app.session_expire_days must be greater than zero")
    if not 1 <= settings.database.port <= 65535:
        raise ConfigError("database.port must be between 1 and 65535")
    if settings.database.pool_size < 1 or settings.database.max_overflow < 0:
        raise ConfigError("database pool settings are invalid")
    if settings.logging.level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("logging.level is invalid")
    if min(settings.database.pool_recycle, settings.database.pool_timeout, settings.database.connect_timeout) <= 0:
        raise ConfigError("database timeouts must be greater than zero")
    if settings.logging.retention_days <= 0:
        raise ConfigError("logging.retention_days must be greater than zero")
    if settings.scheduler.notification_interval_seconds < 10:
        raise ConfigError("scheduler.notification_interval_seconds must be at least 10")
    if not 0 <= settings.scheduler.bill_check_hour <= 23:
        raise ConfigError("scheduler.bill_check_hour must be between 0 and 23")
    if not 0 <= settings.scheduler.bill_check_minute <= 59:
        raise ConfigError("scheduler.bill_check_minute must be between 0 and 59")
    if not 0 <= settings.scheduler.log_cleanup_hour <= 23:
        raise ConfigError("scheduler.log_cleanup_hour must be between 0 and 23")
    if not 0 <= settings.scheduler.session_cleanup_hour <= 23:
        raise ConfigError("scheduler.session_cleanup_hour must be between 0 and 23")
    if settings.scheduler.task_timeout_seconds < 60:
        raise ConfigError("scheduler.task_timeout_seconds must be at least 60")
    notice = settings.notifications
    if not 1 <= notice.dns_timeout_seconds <= 30 or not 1 <= notice.connect_timeout_seconds <= notice.send_timeout_seconds <= 120:
        raise ConfigError("notification timeouts are invalid (DNS 1-30, connect <= send <= 120 seconds)")
    if not settings.security.cookie_name.strip():
        raise ConfigError("security.cookie_name must not be empty")
    if not settings.bootstrap_admin.username.strip() or not settings.bootstrap_admin.password:
        raise ConfigError("bootstrap admin credentials must not be empty")
