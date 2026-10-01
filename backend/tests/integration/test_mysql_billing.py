"""Opt-in real MySQL tests; each test owns a newly created disposable database."""

import os
from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.api.bills import _locked_owned_bill
from app.models import Base, BillOccurrence, BillPlan, NotificationRecord, NotificationSetting, User
from app.services import notifications
from app.services.billing import disable_plan, enable_plan, ensure_plan_occurrences, update_plan

TODAY = date(2026, 9, 30)
NOW = datetime(2026, 9, 30)


@pytest.fixture
def mysql_sessions():
    configured_url = os.getenv("SUBLEDGER_TEST_MYSQL_URL")
    if not configured_url:
        pytest.skip("Set SUBLEDGER_TEST_MYSQL_URL to an isolated MySQL test server")
    url = make_url(configured_url)
    if url.get_backend_name() != "mysql":
        pytest.fail("These concurrency regressions require actual MySQL")
    database_name = "subledger_test_" + uuid4().hex
    admin = create_engine(url.set(database=None))
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f"CREATE DATABASE `{database_name}`"))
        created = True
        engine = create_engine(url.set(database=database_name), isolation_level="REPEATABLE READ")
        Base.metadata.create_all(engine)
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f"DROP DATABASE `{database_name}`"))
        admin.dispose()


def seed(factory, *, enabled=True, with_bill=False):
    with factory() as db:
        db.add(User(
            id=1, username="test", password_hash="unused", role="user", is_active=True,
            timezone="UTC", currency_code="CNY", created_at=NOW, updated_at=NOW,
        ))
        db.flush()
        db.add(NotificationSetting(user_id=1, email_enabled=True, same_day_enabled=True, same_day_time=time(0), advance_time=time(9), updated_at=NOW))
        plan = BillPlan(
            user_id=1, name="test", amount=Decimal("1.00"), first_due_date=TODAY,
            cycle_type="monthly", is_enabled=enabled, created_at=NOW, updated_at=NOW,
        )
        db.add(plan)
        db.flush()
        bill = None
        if with_bill:
            bill = BillOccurrence(
                user_id=1, plan_id=plan.id, due_date=TODAY, amount_snapshot=Decimal("1.00"),
                is_valid=enabled, invalidated_by_plan_disable=not enabled,
                created_at=NOW, updated_at=NOW,
            )
            db.add(bill)
        db.commit()
        return plan.id, bill.id if bill else None


def establish_request_snapshot(db, plan_id):
    # Authentication's ordinary SELECT establishes a REPEATABLE READ snapshot.
    db.scalar(select(User).where(User.id == 1))
    plan = db.get(BillPlan, plan_id)
    # Also exercise refreshing any bill already present in the identity map.
    list(db.scalars(select(BillOccurrence).where(BillOccurrence.plan_id == plan_id)))
    return plan


def test_disable_then_enable_preserves_concurrent_manual_invalidation(mysql_sessions):
    plan_id, bill_id = seed(mysql_sessions, with_bill=True)
    with mysql_sessions() as stale:
        plan = establish_request_snapshot(stale, plan_id)
        with mysql_sessions() as other:
            bill, _ = _locked_owned_bill(other, 1, bill_id)
            bill.is_valid = False
            bill.invalidated_by_plan_disable = False
            other.commit()
        disable_plan(stale, plan, TODAY)
        stale.commit()
    with mysql_sessions() as db:
        enable_plan(db, db.get(BillPlan, plan_id), TODAY)
        db.commit()
    with mysql_sessions() as db:
        bill = db.get(BillOccurrence, bill_id)
        assert not bill.is_valid
        assert not bill.invalidated_by_plan_disable


def test_completion_sees_bills_committed_after_snapshot(mysql_sessions):
    plan_id, _ = seed(mysql_sessions)
    with mysql_sessions() as stale:
        plan = establish_request_snapshot(stale, plan_id)
        with mysql_sessions() as other:
            ensure_plan_occurrences(other, other.get(BillPlan, plan_id), TODAY)
            other.commit()
        assert ensure_plan_occurrences(stale, plan, TODAY) == []
        stale.commit()
    with mysql_sessions() as db:
        assert db.scalar(select(func.count(BillOccurrence.id))) == 2


def test_amount_update_includes_newly_committed_bills(mysql_sessions):
    plan_id, _ = seed(mysql_sessions)
    with mysql_sessions() as stale:
        plan = establish_request_snapshot(stale, plan_id)
        with mysql_sessions() as other:
            ensure_plan_occurrences(other, other.get(BillPlan, plan_id), TODAY)
            other.commit()
        update_plan(stale, plan, {"amount": Decimal("2.00")}, TODAY)
        stale.commit()
    with mysql_sessions() as db:
        assert list(db.scalars(select(BillOccurrence.amount_snapshot))) == [
            Decimal("2.00"), Decimal("2.00"),
        ]


def test_enable_does_not_restore_bill_manually_invalidated_after_snapshot(mysql_sessions):
    plan_id, bill_id = seed(mysql_sessions, enabled=False, with_bill=True)
    with mysql_sessions() as stale:
        plan = establish_request_snapshot(stale, plan_id)
        with mysql_sessions() as other:
            bill, _ = _locked_owned_bill(other, 1, bill_id)
            bill.invalidated_by_plan_disable = False
            other.commit()
        enable_plan(stale, plan, TODAY)
        stale.commit()
    with mysql_sessions() as db:
        assert not db.get(BillOccurrence, bill_id).is_valid


def test_notification_rechecks_record_sent_after_snapshot(mysql_sessions, monkeypatch, tmp_path):
    plan_id, _ = seed(mysql_sessions)
    with mysql_sessions() as db:
        record = NotificationRecord(
            user_id=1, plan_id=plan_id, due_date=TODAY, channel="email",
            reminder_type="same_day", status="failed", scheduled_at=NOW, retry_count=1,
        )
        db.add(record)
        db.commit()
        record_id = record.id
    sent = []
    monkeypatch.setattr(notifications, "_prepare_delivery", lambda *args: ("smtp.example.com", []))
    monkeypatch.setattr(notifications, "_send_email", lambda *args: sent.append("email"))
    with mysql_sessions() as stale:
        plan = establish_request_snapshot(stale, plan_id)
        cached = stale.get(NotificationRecord, record_id)
        assert cached.status == "failed"
        with mysql_sessions() as other:
            other.scalar(select(BillPlan).where(BillPlan.id == plan_id).with_for_update())
            record = other.get(NotificationRecord, record_id)
            record.status = "sent"
            record.sent_at = NOW
            other.commit()
        notifications._attempt_notification(
            stale, SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path / "logs"))),
            None, plan,
            TODAY, "email", "same_day", NOW,
        )
        stale.commit()
    assert sent == []


def test_parallel_account_creation_uses_current_id_after_stale_snapshot(mysql_sessions, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.services import users

    monkeypatch.setattr(users, 'hash_password', lambda value: 'hash')
    with mysql_sessions() as db:
        db.add(User(id=0, username='admin', password_hash='unused', role='admin',
                    is_active=True, timezone='UTC', currency_code='CNY', created_at=NOW, updated_at=NOW))
        db.commit()
    ready = Barrier(2)

    def create(name):
        with mysql_sessions() as db:
            # Both requests authenticate before either inserts a new user.
            db.scalar(select(User).where(User.id == 0))
            ready.wait(timeout=10)
            result = users.create_user(db, name, 'password', 'UTC', 'CNY')
            db.commit()
            return result.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(create, name) for name in ('first', 'second')]
        assert sorted(future.result(timeout=15) for future in futures) == [1, 2]


def test_twenty_users_with_twenty_thousand_bills(mysql_sessions, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from app.api import bills

    monkeypatch.setattr(bills, 'local_today', lambda zone: TODAY)
    with mysql_sessions() as db:
        db.execute(User.__table__.insert(), [dict(
            id=i, username=f'member-{i}', password_hash='hash', role='user', is_active=True,
            timezone='UTC', currency_code='CNY', created_at=NOW, updated_at=NOW,
        ) for i in range(1, 21)])
        db.execute(BillPlan.__table__.insert(), [dict(
            id=i, user_id=i, name=f'Cloud-{i}', amount=1, first_due_date=TODAY,
            cycle_type='custom_days', cycle_days=1, is_enabled=True, created_at=NOW, updated_at=NOW,
        ) for i in range(1, 21)])
        db.execute(BillOccurrence.__table__.insert(), [dict(
            user_id=i, plan_id=i, due_date=TODAY + timedelta(days=offset), amount_snapshot=1,
            is_valid=True, invalidated_by_plan_disable=False, created_at=NOW, updated_at=NOW,
        ) for i in range(1, 21) for offset in range(-500, 500)])
        db.commit()

    def query(user_id):
        with mysql_sessions() as db:
            user = SimpleNamespace(id=user_id, timezone='UTC')
            for status, sort in [('upcoming', 'asc'), ('passed', 'desc')]:
                result = bills.list_bills(q='Cloud', sort=sort, start_date=None, end_date=None,
                                         time_status=status, is_valid=True, plan_id=None,
                                         page=1, page_size=20, user=user, db=db)
                assert result['total'] == 500
                assert len(result['items']) == 20
                assert all(item['plan_id'] == user_id for item in result['items'])
                expected = TODAY if status == 'upcoming' else TODAY - timedelta(days=1)
                assert result['items'][0]['due_date'] == expected

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(query, user_id) for user_id in range(1, 21)]
        for future in futures:
            future.result(timeout=30)

@pytest.mark.parametrize('operation', ['reset_password', 'disable_user'])
def test_login_rechecks_credentials_after_admin_change(mysql_sessions, monkeypatch, tmp_path, operation):
    from app.api import users as api
    from app.errors import AppError
    from app.schemas import AdminPasswordReset
    from app.security import LoginFailureLimiter
    from app.services.auth import authenticate_user, create_session
    seed(mysql_sessions)
    monkeypatch.setattr('app.services.auth.verify_password', lambda hashed, plain: hashed == plain)
    monkeypatch.setattr(api, 'hash_password', lambda value: value)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path))))), state=SimpleNamespace(request_id='test'))
    with mysql_sessions() as stale:
        user = authenticate_user(stale, 'test', 'unused', LoginFailureLimiter())
        with mysql_sessions() as admin:
            if operation == 'reset_password':
                api.reset_password(1, AdminPasswordReset(password='new-password'), request, SimpleNamespace(id=0), admin)
            else:
                api.disable_user(1, request, SimpleNamespace(id=0), admin)
        with pytest.raises(AppError, match='用户名或密码错误'):
            create_session(stale, user, 7)


def test_reset_waits_for_login_then_revokes_its_session(mysql_sessions, monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.api import users as api
    from app.models import SessionRecord
    from app.schemas import AdminPasswordReset
    from app.services.auth import create_session
    seed(mysql_sessions)
    monkeypatch.setattr(api, 'hash_password', lambda value: value)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path))))), state=SimpleNamespace(request_id='test'))
    started = Event()
    def reset():
        with mysql_sessions() as db:
            started.set()
            api.reset_password(1, AdminPasswordReset(password='new-password'), request, SimpleNamespace(id=0), db)
    with mysql_sessions() as login, ThreadPoolExecutor(max_workers=1) as pool:
        create_session(login, login.get(User, 1), 7)
        job = pool.submit(reset)
        assert started.wait(5)
        login.commit()
        job.result(timeout=10)
    with mysql_sessions() as db:
        assert all(record.revoked_at is not None for record in db.scalars(select(SessionRecord)))
        assert db.scalar(select(func.count(SessionRecord.id))) == 1


def test_summary_uses_three_queries_and_preserves_totals(mysql_sessions, monkeypatch):
    from sqlalchemy import event
    from app.services import statistics
    plan_id, _ = seed(mysql_sessions, with_bill=True)
    monkeypatch.setattr(statistics, 'local_today', lambda zone: TODAY)
    with mysql_sessions() as db:
        user = db.get(User, 1)
        queries = []
        engine = db.get_bind()
        def track(connection, cursor, statement, parameters, context, many):
            if statement.lstrip().upper().startswith('SELECT'):
                queries.append(statement)
        event.listen(engine, 'before_cursor_execute', track)
        try:
            result = statistics.summary(db, user)
        finally:
            event.remove(engine, 'before_cursor_execute', track)
        assert len(queries) == 3
        assert result['today'] == {'amount': '1.00', 'count': 1}
        assert result['current_year'] == {'amount': '4.00', 'count': 4}


def test_bill_completion_locks_user_before_child_inserts(mysql_sessions):
    from sqlalchemy.exc import OperationalError
    plan_id, _ = seed(mysql_sessions)
    with mysql_sessions() as billing:
        ensure_plan_occurrences(billing, billing.get(BillPlan, plan_id), TODAY)
        # The new occurrences have not been flushed yet. A User lock must
        # already protect the transaction before acquiring any child FK lock.
        with mysql_sessions() as changing_user:
            with pytest.raises(OperationalError) as caught:
                changing_user.scalar(select(User).where(User.id == 1).with_for_update(nowait=True))
            assert caught.value.orig.args[0] == 3572
        billing.commit()


def test_016_migration_preserves_attempts_and_sent_records(mysql_sessions):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    engine = mysql_sessions.kw['bind']
    Base.metadata.drop_all(engine)
    config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, '0002_add_bill_plan_deleted_at')
    with mysql_sessions() as db:
        db.add(User(id=1, username='migration', password_hash='unused', role='user', is_active=True, timezone='UTC', currency_code='CNY', created_at=NOW, updated_at=NOW))
        db.flush()
        db.execute(text("INSERT INTO bill_plans (id,user_id,name,amount,cycle_type,first_due_date,is_enabled,created_at,updated_at) VALUES (1,1,'migration',1,'once',:today,1,:now,:now)"), {'today': TODAY, 'now': NOW})
        db.flush()
        for index, (status, count) in enumerate([('sent', 2), ('failed', 1), ('sending', 0), ('failed', 3)]):
            db.execute(text("INSERT INTO notification_records (user_id,plan_id,due_date,channel,reminder_type,status,scheduled_at,retry_count) VALUES (1,1,:day,'email','same_day',:status,:now,:count)"), dict(day=date(2026, 9, 1+index), status=status, now=NOW, count=count))
        db.commit()
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
        command.upgrade(config, 'head')
    with mysql_sessions() as db:
        records = list(db.scalars(select(NotificationRecord).order_by(NotificationRecord.id)))
        assert [(r.status, r.attempt_count) for r in records] == [('sent', 3), ('retry_wait', 1), ('unknown', 1), ('failed', 3)]
        assert all(r.last_attempt_at is None for r in records)
        assert records[1].next_retry_at == NOW
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0004_general_cycles'


def test_016_dns_preparation_does_not_hold_user_lock(mysql_sessions, monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.services.users import utc_now
    current = utc_now()
    plan_id, _ = seed(mysql_sessions)
    with mysql_sessions() as db:
        db.get(BillPlan, plan_id).first_due_date = current.date()
        db.commit()
    entered, proceed = Event(), Event()
    def prepare(*args):
        entered.set()
        assert proceed.wait(5)
        return 'smtp.test', []
    monkeypatch.setattr(notifications, '_prepare_delivery', prepare)
    sent = []
    monkeypatch.setattr(notifications, '_send_email', lambda *args: sent.append(1))
    def attempt():
        with mysql_sessions() as db:
            notifications._attempt_notification(db, SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path))), None, db.get(BillPlan, plan_id), current.date(), 'email', 'same_day', datetime.combine(current.date(), time(0)))
            db.commit()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(attempt)
        try:
            assert entered.wait(5)
            with mysql_sessions() as db:
                user = db.scalar(select(User).where(User.id == 1).with_for_update(nowait=True))
                user.is_active = False
                db.commit()
        finally:
            proceed.set()
        future.result(timeout=5)
    assert sent == []


def test_016_send_timeout_releases_user_lock(mysql_sessions, tmp_path):
    import socket
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Thread
    from app.config import NotificationConfig
    from app.services.users import lock_user, utc_now
    current = utc_now()
    plan_id, _ = seed(mysql_sessions)
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    server.settimeout(5)
    connected = Event()
    closed = Event()
    def accept():
        conn, _ = server.accept()
        with conn:
            connected.set()
            conn.settimeout(5)
            assert conn.recv(1024) == b''
            closed.set()
    thread = Thread(target=accept, daemon=True)
    thread.start()
    with mysql_sessions() as db:
        db.get(BillPlan, plan_id).first_due_date = current.date()
        setting = db.get(NotificationSetting, 1)
        setting.smtp_host, setting.smtp_port, setting.smtp_security = '127.0.0.1', server.getsockname()[1], 'none'
        setting.sender_email, setting.recipient_email = 'sender@example.com', 'receiver@example.com'
        db.commit()
    settings = SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path)), security=SimpleNamespace(smtp_allow_private_hosts=['127.0.0.1']), notifications=NotificationConfig(send_timeout_seconds=0.2, connect_timeout_seconds=0.1))
    def attempt():
        with mysql_sessions() as db:
            result = notifications._attempt_notification(db, settings, None, db.get(BillPlan, plan_id), current.date(), 'email', 'same_day', datetime.combine(current.date(), time(0)))
            db.commit()
            return result
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(attempt)
            assert connected.wait(5)
            with mysql_sessions() as db:
                lock_user(db, 1).is_active = False
                db.commit()
            assert future.result(timeout=5) == 'failed'
            assert closed.wait(2)
        with mysql_sessions() as db:
            record = db.scalar(select(NotificationRecord))
            assert record.status == 'retry_wait' and record.attempt_count == 1
    finally:
        server.close()
        thread.join(5)


def test_016_expired_cleanup_preserves_concurrent_login(mysql_sessions, monkeypatch):
    from app.models import SessionRecord
    from app.services.auth import cleanup_expired_sessions, create_session
    from datetime import timedelta
    from app.services.users import utc_now
    seed(mysql_sessions)
    now = utc_now()
    with mysql_sessions() as db:
        db.add(SessionRecord(user_id=1, token_hash='expired', created_at=now, expires_at=now-timedelta(days=1)))
        db.commit()
    with mysql_sessions() as login:
        create_session(login, login.get(User, 1), 7)
        assert cleanup_expired_sessions(SimpleNamespace(session=mysql_sessions)) == 1
        login.commit()
    with mysql_sessions() as db:
        assert db.scalar(select(func.count(SessionRecord.id))) == 1
        assert db.scalar(select(SessionRecord.expires_at)) > now


def test_017_cycle_migration_preserves_bills_and_deleted_plans(mysql_sessions):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    engine = mysql_sessions.kw['bind']
    Base.metadata.drop_all(engine)
    config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, '0003_notification_attempts')
        connection.execute(text("INSERT INTO users (id,username,password_hash,role,is_active,timezone,currency_code,created_at,updated_at) VALUES (1,'migration','unused','user',1,'UTC','CNY',:now,:now)"), {'now': NOW})
        for index, (kind, days) in enumerate([('once', None), ('monthly', None), ('quarterly', None), ('yearly', None), ('custom_days', 17)], 1):
            connection.execute(text("INSERT INTO bill_plans (id,user_id,name,amount,first_due_date,cycle_type,cycle_days,is_enabled,deleted_at,created_at,updated_at) VALUES (:id,1,'migration',12.50,:today,:kind,:days,:enabled,:deleted,:now,:now)"), dict(id=index, today=TODAY, kind=kind, days=days, enabled=index!=5, deleted=NOW if index==5 else None, now=NOW))
            connection.execute(text("INSERT INTO bill_occurrences (id,user_id,plan_id,due_date,amount_snapshot,is_valid,invalidated_by_plan_disable,created_at,updated_at) VALUES (:id,1,:id,:today,9.50,0,0,:now,:now)"), dict(id=index, today=TODAY, now=NOW))
        before = connection.execute(text('SELECT * FROM bill_occurrences ORDER BY id')).all()
        command.upgrade(config, 'head')
        command.upgrade(config, 'head')
        assert connection.execute(text('SELECT * FROM bill_occurrences ORDER BY id')).all() == before
        assert connection.execute(text('SELECT cycle_type, cycle_interval, cycle_days FROM bill_plans ORDER BY id')).all() == [('once',1,None),('month',1,None),('month',3,None),('year',1,None),('day',17,None)]
        assert connection.scalar(text('SELECT deleted_at FROM bill_plans WHERE id=5')) == NOW


def test_017_draft_test_holds_no_user_lock_and_rejects_concurrent_change(mysql_sessions, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from cryptography.fernet import Fernet
    from app.api import notifications as api
    from app.schemas import NotificationSettingsPatch
    from app.errors import AppError
    seed(mysql_sessions)
    with mysql_sessions() as db:
        setting = db.get(NotificationSetting, 1)
        setting.email_enabled = False
        db.commit()
    entered, proceed = Event(), Event()
    def send(*args):
        entered.set()
        assert proceed.wait(5)
    monkeypatch.setattr(api, 'send_test_email', send)
    request = SimpleNamespace(cookies={}, state=SimpleNamespace(request_id='test'), app=SimpleNamespace(state=SimpleNamespace(fernet=Fernet(Fernet.generate_key()), settings=SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path))))))
    payload = NotificationSettingsPatch(email_enabled=True, smtp_host='smtp.example.com', smtp_port=465, smtp_security='ssl', sender_email='sender@example.com', recipient_email='receiver@example.com')
    def test_draft():
        with mysql_sessions() as db:
            return api._test_channel('email', payload, request, db.get(User, 1), db)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(test_draft)
        assert entered.wait(5)
        try:
            with mysql_sessions() as db:
                db.scalar(select(User).where(User.id == 1).with_for_update(nowait=True))
                setting = db.scalar(select(NotificationSetting).where(NotificationSetting.user_id == 1).with_for_update(nowait=True))
                setting.advance_days = 7
                db.commit()
        finally:
            proceed.set()
        with pytest.raises(AppError) as caught:
            future.result(timeout=5)
        assert caught.value.code == 'NOTIFICATION_SETTINGS_CHANGED'
