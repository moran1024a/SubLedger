import io
import socket
import ssl
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import notifications as notifications_api
from app.api.dependencies import get_current_user, get_db
from app.config import ConfigError, load_settings
from app.errors import AppError, app_error_handler
from app.models import Base, NotificationSetting, User
from app.services import notifications, outbound

WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/test-token"


def address(ip, port=465):
    if ":" in ip:
        return (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, port, 0, 0))
    return (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))


@pytest.mark.parametrize("url", [
    "http://open.feishu.cn/open-apis/bot/v2/hook/token",
    "https://localhost/open-apis/bot/v2/hook/token",
    "https://127.0.0.1/open-apis/bot/v2/hook/token",
    "https://[::1]/open-apis/bot/v2/hook/token",
    "https://open.feishu.cn.evil.test/open-apis/bot/v2/hook/token",
    "https://open.feishu.cn@evil.test/open-apis/bot/v2/hook/token",
    "https://username@open.feishu.cn/open-apis/bot/v2/hook/token",
    "https://open.feishu.cn:8443/open-apis/bot/v2/hook/token",
    "https://open.feishu.cn/open-apis/bot/v2/hook/token?redirect=http://localhost",
    "https://open.feishu.cn/open-apis/bot/v2/hook/token?",
    "https://open.feishu.cn/open-apis/bot/v2/hook/token#fragment",
    "https://open.feishu.cn/open-apis/bot/v2/hook/token/../../other",
    "https://open.feishu.cn/open-apis/bot/v2/hook/%2e%2e",
    "https://open.feishu.cn\n/open-apis/bot/v2/hook/token",
    "https://open.feishu.cn/api/other",
])
def test_feishu_rejects_untrusted_webhooks(url):
    with pytest.raises(ValueError):
        outbound.validate_feishu_webhook(url)


@pytest.mark.parametrize("host", ["open.feishu.cn", "open.larksuite.com"])
@pytest.mark.parametrize("port", ["", ":443"])
def test_feishu_allows_official_webhooks(host, port):
    assert outbound.validate_feishu_webhook(
        f"https://{host}{port}/open-apis/bot/v2/hook/test-token"
    ) == (host, "/open-apis/bot/v2/hook/test-token")


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254",
    "0.0.0.0", "224.0.0.1", "100.64.0.1", "::1", "fc00::1", "fe80::1",
    "::", "ff02::1", "fec0::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1",
])
def test_smtp_rejects_nonpublic_dns_and_mixed_answers(monkeypatch, ip):
    for answers in ([address(ip)], [address("8.8.8.8"), address(ip)]):
        monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *args, **kwargs: answers)
        with pytest.raises(ValueError, match="prohibited"):
            outbound.resolve_smtp_target("smtp.example.com", 465)
        with pytest.raises(ValueError, match="prohibited"):
            outbound.resolve_addresses("open.feishu.cn", 443)


@pytest.mark.parametrize("ip", ["8.8.8.8", "2606:4700:4700::1111"])
def test_smtp_allows_public_targets(monkeypatch, ip):
    answers = [address(ip)]
    monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *args, **kwargs: answers)
    assert outbound.resolve_smtp_target("SMTP.EXAMPLE.COM.", 465) == (
        "smtp.example.com", answers,
    )


def test_smtp_precise_host_allowlist_and_private_exception(monkeypatch):
    answers = [address("10.0.0.8")]
    monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *args, **kwargs: answers)
    security = SimpleNamespace(
        smtp_allowed_hosts=("smtp.internal",), smtp_allow_private_hosts=("smtp.internal",),
    )
    assert outbound.resolve_smtp_target("smtp.internal", 465, security)[1] == answers
    with pytest.raises(ValueError, match="allowlist"):
        outbound.resolve_smtp_target("child.smtp.internal", 465, security)
    with pytest.raises(ValueError, match="prohibited"):
        outbound.resolve_smtp_target(
            "smtp.internal", 465,
            SimpleNamespace(smtp_allowed_hosts=("smtp.internal",), smtp_allow_private_hosts=()),
        )
    assert outbound.resolve_smtp_target(
        "smtp.internal", 465, SimpleNamespace(smtp_allow_private_hosts=("smtp.internal",)),
    )[1] == answers


class FakeSocket:
    def __init__(self, response=b""):
        self.response = io.BytesIO(response)
        self.connected = None
        self.sent = []
        self.closed = False

    def do_handshake(self):
        pass

    def settimeout(self, value):
        self.timeout = value

    def setsockopt(self, *args):
        pass

    def connect(self, address):
        self.connected = address

    def sendall(self, data):
        self.sent.append(data)

    def makefile(self, *args):
        return self.response

    def close(self):
        self.closed = True


class FakeContext:
    verify_mode = ssl.CERT_REQUIRED
    check_hostname = True

    def __init__(self):
        self.hosts = []

    def wrap_socket(self, sock, *, server_hostname, **kwargs):
        self.hosts.append(server_hostname)
        return sock


def test_feishu_pins_checked_ip_preserves_tls_host_and_ignores_proxies(monkeypatch):
    calls = []

    def resolve(*args, **kwargs):
        calls.append(args)
        return [address("8.8.8.8", 443)] if len(calls) == 1 else [address("127.0.0.1", 443)]

    payload = b'{"code":0}'
    sock = FakeSocket(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n" + payload)
    context = FakeContext()
    monkeypatch.setattr(outbound.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(outbound.socket, "socket", lambda *args: sock)
    monkeypatch.setattr(notifications.ssl, "create_default_context", lambda: context)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:4444")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:4444")
    notifications._send_feishu(WEBHOOK, None, "test")
    assert len(calls) == 1
    assert sock.connected == ("8.8.8.8", 443)
    assert context.hosts == ["open.feishu.cn"]
    assert b"Host: open.feishu.cn\r\n" in sock.sent[0]
    assert sock.closed


def test_feishu_does_not_follow_redirect(monkeypatch):
    sock = FakeSocket(
        b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/\r\nContent-Length: 0\r\n\r\n"
    )
    monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *args, **kwargs: [address("8.8.8.8", 443)])
    monkeypatch.setattr(outbound.socket, "socket", lambda *args: sock)
    monkeypatch.setattr(notifications.ssl, "create_default_context", FakeContext)
    with pytest.raises(RuntimeError, match="HTTP status"):
        notifications._send_feishu(WEBHOOK, None, "test")
    assert sock.connected == ("8.8.8.8", 443)
    assert sock.closed


@pytest.mark.parametrize("body, accepted", [
    (b'{"code":0}', True), (b'{"StatusCode":"0"}', True),
    (b'{}', False), (b'{"code":false}', False), (b'{"code":null}', False),
    (b'{"code":1}', False), (b'[]', False),
])
def test_feishu_requires_explicit_success_status(monkeypatch, body, accepted):
    sock = FakeSocket(
        b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode("ascii")
        + b"\r\n\r\n" + body
    )
    monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *args, **kwargs: [address("8.8.8.8", 443)])
    monkeypatch.setattr(outbound.socket, "socket", lambda *args: sock)
    monkeypatch.setattr(notifications.ssl, "create_default_context", FakeContext)
    if accepted:
        notifications._send_feishu(WEBHOOK, None, "test")
    else:
        with pytest.raises(RuntimeError):
            notifications._send_feishu(WEBHOOK, None, "test")


def test_smtp_pins_checked_ip_and_keeps_original_tls_hostname(monkeypatch):
    calls = []

    def resolve(*args, **kwargs):
        calls.append(args)
        return [address("8.8.8.8")] if len(calls) == 1 else [address("127.0.0.1")]

    sock = FakeSocket(b"220 smtp.example.com ready\r\n")
    context = FakeContext()
    monkeypatch.setattr(outbound.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(outbound.socket, "socket", lambda *args: sock)
    host, addresses = outbound.resolve_smtp_target("smtp.example.com", 465)
    client = notifications._SMTPSSL(host, 465, addresses, timeout=15, context=context)
    try:
        assert len(calls) == 1
        assert sock.connected == ("8.8.8.8", 465)
        assert client._host == "smtp.example.com"
        assert context.hosts == ["smtp.example.com"]
    finally:
        client.close()


@pytest.mark.parametrize("security", ["ssl", "starttls", "none"])
@pytest.mark.parametrize("send_error", [False, True])
def test_email_verifies_tls_and_quit_does_not_change_delivery_outcome(monkeypatch, security, send_error):
    calls = {}

    class Client:
        def __init__(self, host, port, addresses, **kwargs):
            calls.update(host=host, context=kwargs.get("context"), addresses=addresses)

        def starttls(self, *, context):
            calls["starttls_context"] = context

        def login(self, *args):
            pass

        def send_message(self, message):
            calls["message"] = message
            if send_error:
                raise ValueError("sending failed")

        def quit(self):
            raise OSError("quit failed")

        def close(self):
            calls["closed"] = True
            raise OSError("close failed")

    monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *args, **kwargs: [address("8.8.8.8")])
    monkeypatch.setattr(notifications, "_SMTP", Client)
    monkeypatch.setattr(notifications, "_SMTPSSL", Client)
    setting = SimpleNamespace(
        smtp_host="smtp.example.com", smtp_port=465, smtp_security=security,
        smtp_username="username", sender_name=None,
        sender_email="sender@example.com", recipient_email="recipient@example.com",
    )
    if send_error:
        with pytest.raises(ValueError, match="sending failed"):
            notifications._send_email(setting, "password", "test", "content")
    else:
        notifications._send_email(setting, "password", "test", "content")
    if security in {"ssl", "starttls"}:
        context = calls["context"] if security == "ssl" else calls["starttls_context"]
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True
    assert calls["closed"]


def test_legacy_config_uses_safe_defaults_and_host_lists_are_precise(tmp_path):
    source = Path(__file__).parents[2] / "config" / "config.example.toml"
    text = source.read_text().replace("smtp_allowed_hosts = []\n", "").replace("smtp_allow_private_hosts = []\n", "")
    config = tmp_path / "config.toml"
    config.write_text(text)
    settings = load_settings(config)
    assert settings.security.smtp_allowed_hosts == ()
    assert settings.security.smtp_allow_private_hosts == ()
    config.write_text(text.replace('[security]', '[security]\nsmtp_allowed_hosts = ["SMTP.EXAMPLE.COM.", "2001:4860:4860::8888"]\nsmtp_allow_private_hosts = ["smtp.internal"]'))
    settings = load_settings(config)
    assert settings.security.smtp_allowed_hosts == ("smtp.example.com", "2001:4860:4860::8888")
    assert settings.security.smtp_allow_private_hosts == ("smtp.internal",)
    for value in ('"smtp.example.com"', '["*.example.com"]', '["smtp.example.com:465"]', '[1]'):
        config.write_text(text.replace('[security]', f'[security]\nsmtp_allowed_hosts = {value}'))
        with pytest.raises(ConfigError):
            load_settings(config)


@pytest.fixture()
def notification_client(tmp_path):
    from datetime import datetime, time

    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 9, 30)
    with factory() as db:
        db.add(User(
            id=1, username="user", password_hash="hash", role="user", is_active=True,
            timezone="UTC", currency_code="CNY", created_at=now, updated_at=now,
        ))
        db.add(NotificationSetting(
            user_id=1, advance_time=time(9), same_day_time=time(8, 30), updated_at=now,
        ))
        db.commit()
    app = FastAPI()
    app.state.settings = SimpleNamespace(
        security=SimpleNamespace(smtp_allowed_hosts=(), smtp_allow_private_hosts=()),
        logging=SimpleNamespace(directory=str(tmp_path / "logs")),
    )
    app.state.fernet = Fernet(Fernet.generate_key())

    @app.middleware("http")
    async def set_request_id(request: Request, call_next):
        request.state.request_id = "test"
        return await call_next(request)

    def override_db():
        with factory() as db:
            yield db

    def override_user():
        with factory() as db:
            return db.get(User, 1)

    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(notifications_api.router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        with TestClient(app) as client:
            yield client, factory, app
    finally:
        engine.dispose()


def test_settings_rejects_untrusted_webhook_and_smtp_without_persisting(notification_client, monkeypatch):
    client, factory, _ = notification_client
    response = client.put("/api/v1/me/notification-settings", json={
        "feishu_enabled": True, "feishu_webhook": "https://127.0.0.1/internal",
    })
    assert response.status_code == 400
    assert response.json()["code"] == "FEISHU_WEBHOOK_NOT_ALLOWED"
    monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *args, **kwargs: [address("127.0.0.1")])
    response = client.put("/api/v1/me/notification-settings", json={"smtp_host": "smtp.internal"})
    assert response.status_code == 400
    assert response.json()["code"] == "SMTP_TARGET_NOT_ALLOWED"
    with factory() as db:
        setting = db.get(NotificationSetting, 1)
        assert setting.feishu_webhook_encrypted is None
        assert setting.smtp_host is None


def test_settings_accepts_official_webhook_and_explicit_private_smtp(notification_client, monkeypatch):
    client, _, app = notification_client
    monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *args, **kwargs: [address("10.0.0.8")])
    app.state.settings.security.smtp_allow_private_hosts = ("smtp.internal",)
    response = client.put("/api/v1/me/notification-settings", json={
        "feishu_enabled": True, "feishu_webhook": WEBHOOK,
        "smtp_host": "smtp.internal", "smtp_port": 465,
    })
    assert response.status_code == 200
    assert response.json()["feishu_webhook_configured"] is True


def test_disabling_legacy_invalid_channels_is_allowed_but_reenabling_is_checked(notification_client, monkeypatch):
    client, factory, app = notification_client
    with factory() as db:
        setting = db.get(NotificationSetting, 1)
        setting.feishu_enabled = True
        setting.feishu_webhook_encrypted = app.state.fernet.encrypt(
            b"https://127.0.0.1/legacy-webhook"
        ).decode("ascii")
        setting.smtp_host = "legacy.internal"
        setting.smtp_port = 465
        setting.smtp_security = "ssl"
        setting.sender_email = "sender@example.com"
        setting.recipient_email = "recipient@example.com"
        db.commit()
    monkeypatch.setattr(outbound.socket, "getaddrinfo", lambda *args, **kwargs: [address("127.0.0.1")])
    response = client.put("/api/v1/me/notification-settings", json={
        "email_enabled": False, "feishu_enabled": False,
        "smtp_host": "legacy.internal", "smtp_port": 465, "smtp_security": "ssl",
        "smtp_username": None, "sender_email": "sender@example.com",
        "sender_name": None, "recipient_email": "recipient@example.com",
        "advance_enabled": False, "advance_days": 3, "advance_time": "09:00:00",
        "same_day_enabled": False, "same_day_time": "08:30:00",
    })
    assert response.status_code == 200
    response = client.put("/api/v1/me/notification-settings", json={"same_day_enabled": True})
    assert response.status_code == 200
    response = client.put("/api/v1/me/notification-settings", json={"feishu_enabled": True})
    assert response.status_code == 400
    assert response.json()["code"] == "FEISHU_WEBHOOK_NOT_ALLOWED"
    response = client.put("/api/v1/me/notification-settings", json={"email_enabled": True})
    assert response.status_code == 400
    assert response.json()["code"] == "SMTP_TARGET_NOT_ALLOWED"
