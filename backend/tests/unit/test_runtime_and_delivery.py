from datetime import datetime, time, timedelta, timezone
from threading import Event, Thread
from types import SimpleNamespace
import socket
import time as clock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api import notification_records, runtime
from app.api.dependencies import get_current_user, get_db
from app.config import NotificationConfig, SchedulerConfig
from app.errors import AppError, app_error_handler
from app.models import Base, BillPlan, NotificationRecord, NotificationSetting, SessionRecord, User
from app.scheduler import Scheduler
from app.services.auth import cleanup_expired_sessions
from app.services import notifications, outbound


def settings(tmp_path):
    return SimpleNamespace(app=SimpleNamespace(timezone="UTC"),
        scheduler=SchedulerConfig(True, 0, 5, 60, 1),
        logging=SimpleNamespace(directory=str(tmp_path / 'logs')),
        notifications=NotificationConfig())


def test_task_health_distinguishes_failure_warning_and_overdue(tmp_path):
    scheduler = Scheduler(settings(tmp_path), None, None)
    scheduler.running = True
    assert scheduler.snapshot()['status'] == 'ok'
    scheduler._run('notification_check', lambda: {'failed': 3})
    assert scheduler.snapshot()['status'] == 'ok'
    assert scheduler.snapshot()['tasks'][1]['status'] == 'warning'
    for _ in range(3):
        scheduler._run('notification_check', lambda: {'errors': 1})
    assert scheduler.snapshot()['status'] == 'error'
    scheduler._run('notification_check', lambda: {'sent': 1})
    assert scheduler.snapshot()['status'] == 'ok'
    state = scheduler._states['notification_check']
    state.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=121)
    assert scheduler.snapshot()['status'] == 'error'
    state.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    state.running = True
    scheduler._started_monotonic[state.id] = clock.monotonic() - 901
    assert scheduler.snapshot()['status'] == 'error'
    scheduler.settings.scheduler = SchedulerConfig(False, 0, 5, 60, 1)
    assert scheduler.snapshot()['status'] == 'disabled'


def test_runtime_endpoint_is_admin_only(tmp_path):
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(runtime.router)
    app.state.scheduler = Scheduler(settings(tmp_path), None, None)
    current = SimpleNamespace(id=1, role='user')
    app.dependency_overrides[get_current_user] = lambda: current
    with TestClient(app) as client:
        assert client.get('/api/v1/admin/runtime').status_code == 403
        current.id, current.role = 0, 'admin'
        response = client.get('/api/v1/admin/runtime')
        assert response.status_code == 200
        assert len(response.json()['tasks']) == 4


@pytest.fixture
def database(monkeypatch, tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'test.db'))
    with monkeypatch.context() as patch:
        patch.setattr(NotificationRecord.__table__.c.id, 'type', Integer())
        Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with factory() as db:
        for i in (1, 2):
            db.add(User(id=i, username=f'u{i}', password_hash='hash', role='user', is_active=True, timezone='UTC', currency_code='CNY', created_at=now, updated_at=now))
            db.add(NotificationSetting(user_id=i, email_enabled=True, smtp_host='smtp.test', smtp_port=25, smtp_security='none', sender_email='a@example.com', recipient_email='b@example.com', same_day_enabled=True, same_day_time=time(0), advance_enabled=False, advance_time=time(9), updated_at=now))
            db.add(BillPlan(id=i, user_id=i, name=f'plan{i}', amount=1, cycle_type='once', first_due_date=now.date(), is_enabled=True, created_at=now, updated_at=now))
        db.commit()
    yield SimpleNamespace(session=factory)
    engine.dispose()


def test_session_cleanup_is_bounded_and_preserves_valid_sessions(database):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with database.session() as db:
        for i in range(1, 8):
            db.add(SessionRecord(id=i, user_id=1, token_hash=f't{i}', created_at=now, expires_at=now + timedelta(days=1 if i == 7 else -1)))
        db.commit()
    assert cleanup_expired_sessions(database, batch_size=2, limit=3) == 3
    assert cleanup_expired_sessions(database, batch_size=2) == 3
    assert cleanup_expired_sessions(database) == 0
    with database.session() as db:
        assert list(db.scalars(select(SessionRecord.id))) == [7]


def test_notification_retry_intervals_cap_and_permanent_failures(database, monkeypatch, tmp_path):
    monkeypatch.setattr(notifications, '_prepare_delivery', lambda *args: ('smtp.test', []))
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=12, minute=0)
    monkeypatch.setattr(notifications, 'utc_now', lambda: now)
    sent = []
    def temporary(*args):
        sent.append(1)
        raise notifications.DeliveryError('NETWORK_ERROR', retryable=True)
    monkeypatch.setattr(notifications, '_send_email', temporary)
    def attempt(user_id=1):
        with database.session() as db:
            result = notifications._attempt_notification(db, settings(tmp_path), None, db.get(BillPlan, user_id), now.date(), 'email', 'same_day', datetime.combine(now.date(), time(0)))
            db.commit()
            return result
    assert attempt() == 'failed'
    with database.session() as db:
        record = db.scalar(select(NotificationRecord))
        assert record.next_retry_at == now + timedelta(seconds=60)
        assert record.attempt_count == 1
    assert attempt() is None
    now += timedelta(seconds=60)
    assert attempt() == 'failed'
    with database.session() as db:
        assert db.scalar(select(NotificationRecord)).next_retry_at == now + timedelta(seconds=300)
    now += timedelta(seconds=300)
    assert attempt() == 'failed'
    now += timedelta(seconds=300)
    assert attempt() is None
    assert len(sent) == 3
    with database.session() as db:
        record = db.scalar(select(NotificationRecord))
        assert record.status == 'failed' and record.next_retry_at is None
    monkeypatch.setattr(notifications, '_send_email', lambda *args: (_ for _ in ()).throw(notifications.DeliveryError('SMTP_REJECTED')))
    assert attempt(2) == 'failed'
    assert attempt(2) is None


def test_unknown_is_not_retried_and_expired_window_is_skipped(database, monkeypatch, tmp_path):
    monkeypatch.setattr(notifications, '_prepare_delivery', lambda *args: ('smtp.test', []))
    monkeypatch.setattr(notifications, '_send_email', lambda *args: (_ for _ in ()).throw(notifications.DeliveryError('DELIVERY_UNKNOWN', unknown=True)))
    counts = notifications.check_notifications(database, settings(tmp_path), None)
    assert counts['unknown'] == 2 and counts['errors'] == 0
    assert notifications.check_notifications(database, settings(tmp_path), None)['unknown'] == 0
    with database.session() as db:
        record = db.scalar(select(NotificationRecord))
        record.status = 'retry_wait'
        record.next_retry_at = None
        record.scheduled_at -= timedelta(days=1)
        record.due_date -= timedelta(days=1)
        plan = db.get(BillPlan, record.plan_id)
        plan.first_due_date = record.due_date
        db.commit()
        assert notifications._attempt_notification(db, settings(tmp_path), None, plan, record.due_date, 'email', 'same_day', record.scheduled_at) is None
        assert record.attempt_count == 1


def test_configuration_changed_during_dns_prevents_send(database, monkeypatch, tmp_path):
    def prepare(*args):
        with database.session() as db:
            db.get(NotificationSetting, 1).email_enabled = False
            db.commit()
        return ('smtp.test', [])
    monkeypatch.setattr(notifications, '_prepare_delivery', prepare)
    sent = []
    monkeypatch.setattr(notifications, '_send_email', lambda *args: sent.append(1))
    with database.session() as db:
        plan = db.get(BillPlan, 1)
        assert notifications._attempt_notification(db, settings(tmp_path), None, plan, plan.first_due_date, 'email', 'same_day', datetime.combine(plan.first_due_date, time(0))) is None
    assert sent == []


def test_record_api_is_paginated_private_and_sanitized(database):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with database.session() as db:
        for i in (1, 2):
            db.add(NotificationRecord(user_id=i, plan_id=i, due_date=now.date(), channel='email', reminder_type='same_day', status='failed', scheduled_at=now, error_message='secret password', attempt_count=1))
        db.add(NotificationRecord(user_id=1, plan_id=1, due_date=now.date()-timedelta(days=1), channel='email', reminder_type='same_day', status='retry_wait', scheduled_at=now-timedelta(days=1), attempt_count=1))
        db.commit()
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(notification_records.router)
    def session():
        with database.session() as db:
            yield db
    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, timezone='UTC')
    with TestClient(app) as client:
        response = client.get('/api/v1/me/notification-records?page_size=1')
        assert response.status_code == 200
        assert response.json()['total'] == 2
        assert len(response.json()['items']) == 1
        assert 'secret password' not in response.text and 'plan2' not in response.text
        expired = client.get('/api/v1/me/notification-records?status=expired').json()
        assert expired['total'] == 1 and expired['items'][0]['next_retry_at'] is None
        assert client.get('/api/v1/me/notification-records?start_date=2026-10-02&end_date=2026-10-01').status_code == 400
        assert client.get('/api/v1/me/notification-records?page_size=101').status_code == 422


def test_dns_wait_is_bounded_and_does_not_send(monkeypatch):
    unblock = Event()
    finished = Event()
    def stalled(*args, **kwargs):
        unblock.wait(2)
        finished.set()
        return []
    monkeypatch.setattr(outbound.socket, 'getaddrinfo', stalled)
    start = clock.monotonic()
    try:
        with pytest.raises(TimeoutError):
            outbound.resolve_addresses('example.com', 443, timeout=0.03)
        assert clock.monotonic() - start < 0.5
    finally:
        unblock.set()
        assert finished.wait(1)


def test_deadline_interrupts_a_real_slow_drip_response():
    reader, writer = socket.socketpair()
    finished = Event()
    def drip():
        try:
            while not finished.wait(0.015):
                writer.sendall(b'x')
        except OSError:
            pass
    thread = Thread(target=drip)
    thread.start()
    start = clock.monotonic()
    try:
        with outbound.SendDeadline(0.08) as deadline:
            deadline.track(reader)
            with reader.makefile('rb') as stream:
                stream.read(10000)
            assert deadline.expired
        assert clock.monotonic() - start < 0.6
    finally:
        finished.set()
        reader.close()
        writer.close()
        thread.join(1)


def test_smtp_rejection_and_ambiguous_delivery_are_distinct():
    import smtplib
    assert notifications.classify_error(smtplib.SMTPDataError(451, b'retry'), submitted=True).retryable
    assert not notifications.classify_error(smtplib.SMTPDataError(550, b'reject'), submitted=True).retryable
    failure = notifications.classify_error(TimeoutError(), submitted=True)
    assert failure.unknown and not failure.retryable


def test_deadline_interrupts_tls_handshake():
    import ssl
    reader, peer = socket.socketpair()
    start = clock.monotonic()
    try:
        with outbound.SendDeadline(0.06) as deadline:
            deadline.track(reader)
            with pytest.raises(OSError):
                deadline.wrap_context(ssl.create_default_context()).wrap_socket(reader, server_hostname='smtp.example.com')
            assert deadline.expired
        assert clock.monotonic() - start < 0.6
    finally:
        reader.close()
        peer.close()


def test_health_endpoint_reflects_task_failure_without_disclosing_details(tmp_path, monkeypatch):
    from app.main import create_app
    from test_spa import make_settings
    config = make_settings(tmp_path)
    config.scheduler = SchedulerConfig(True, 0, 5, 60, 1)
    app = create_app(config)
    monkeypatch.setattr(app.state.database, 'check_connection', lambda: True)
    app.state.scheduler.running = True
    app.state.scheduler._states['notification_check'].consecutive_failures = 3
    app.state.scheduler._states['notification_check'].last_error = 'PrivateDiagnostic'
    client = TestClient(app)
    try:
        response = client.get('/health')
        assert response.status_code == 503
        assert response.json()['scheduler'] == 'error'
        assert 'PrivateDiagnostic' not in response.text
        config.scheduler = SchedulerConfig(False, 0, 5, 60, 1)
        assert client.get('/health').status_code == 200
    finally:
        client.close()
        app.state.database.dispose()


@pytest.mark.parametrize('source,replacement', [
    ('dns_timeout_seconds = 5', 'dns_timeout_seconds = 0'),
    ('connect_timeout_seconds = 5', 'connect_timeout_seconds = 31'),
    ('send_timeout_seconds = 30', 'send_timeout_seconds = 121'),
    ('task_timeout_seconds = 900', 'task_timeout_seconds = 0'),
    ('session_cleanup_hour = 2', 'session_cleanup_hour = 24'),
])
def test_new_config_limits(tmp_path, source, replacement):
    from pathlib import Path
    from app.config import ConfigError, load_settings
    config = Path(__file__).resolve().parents[2] / 'config/config.example.toml'
    path = tmp_path / 'config.toml'
    path.write_text(config.read_text().replace(source, replacement))
    with pytest.raises(ConfigError):
        load_settings(path)


def test_015_config_remains_compatible(tmp_path):
    from pathlib import Path
    from app.config import load_settings
    source = (Path(__file__).resolve().parents[2] / 'config/config.example.toml').read_text()
    source = source.replace('session_cleanup_hour = 2\n', '').replace('task_timeout_seconds = 900\n', '')
    begin, end = source.index('[notifications]'), source.index('[logging]')
    path = tmp_path / 'config.toml'
    path.write_text(source[:begin] + source[end:])
    config = load_settings(path)
    assert config.notifications == NotificationConfig()
    assert config.scheduler.session_cleanup_hour == 2
    assert config.scheduler.task_timeout_seconds == 900
