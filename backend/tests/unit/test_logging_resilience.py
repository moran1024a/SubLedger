import json
from datetime import datetime
from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import users
from app.api.dependencies import get_current_user, get_db
from app.middleware import RequestContextMiddleware
from app.models import Base, User
from app.services import logging


def unavailable_log_settings(tmp_path):
    blocked = tmp_path / "logs"
    blocked.write_text("A file cannot be used as a log directory.")
    return SimpleNamespace(logging=SimpleNamespace(directory=str(blocked)))


def test_unwritable_log_directory_falls_back_to_sanitized_stderr(tmp_path, capsys):
    settings = unavailable_log_settings(tmp_path)
    logging.write_user_log(
        settings, user_id=1, level="INFO", module="users", event="profile_updated",
        request_id="request-1", message="资料已更新",
        data={"smtp_password": "do-not-expose", "nested": {"token": "private"}},
    )

    output = capsys.readouterr().err
    record = json.loads(output)
    assert record["event"] == "profile_updated"
    assert record["request_id"] == "request-1"
    assert record["log_write_error"] in {"NotADirectoryError", "FileExistsError"}
    assert record["data"] == {
        "smtp_password": "[REDACTED]", "nested": {"token": "[REDACTED]"},
    }
    assert "do-not-expose" not in output and "private" not in output
    assert str(tmp_path) not in output


def test_stderr_failure_does_not_fail_business_logging(tmp_path, monkeypatch):
    class BrokenStream:
        def write(self, value):
            raise OSError("stderr unavailable")

    monkeypatch.setattr(logging.sys, "stderr", BrokenStream())
    logging.write_system_log(
        unavailable_log_settings(tmp_path), level="INFO", module="test", event="completed",
        request_id="request-2", message="done",
    )


def test_committed_profile_update_succeeds_when_both_logs_fail(tmp_path, capsys):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(User(
            id=1, username="original", password_hash="unused", role="user", is_active=True,
            timezone="UTC", currency_code="CNY", created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        ))
        db.commit()

    app = FastAPI()
    app.state.settings = unavailable_log_settings(tmp_path)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(users.router)

    def override_db():
        with factory() as db:
            yield db

    def override_user(db=Depends(get_db)):
        return db.get(User, 1)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.patch("/api/v1/me/profile", json={"username": "updated"})
        assert response.status_code == 200, response.text
        assert response.json()["username"] == "updated"
        assert response.headers["X-Request-ID"]
        with factory() as db:
            assert db.get(User, 1).username == "updated"
        events = [json.loads(line)["event"] for line in capsys.readouterr().err.splitlines()]
        assert "profile_updated" in events and "request_completed" in events
    finally:
        engine.dispose()
