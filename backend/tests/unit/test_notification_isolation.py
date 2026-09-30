from datetime import datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import Integer, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, BillPlan, NotificationRecord, NotificationSetting, User
from app.services import notifications


@pytest.fixture()
def notification_database(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    # MySQL BIGINT auto-increments; SQLite requires the exact INTEGER type.
    with monkeypatch.context() as patch:
        patch.setattr(NotificationRecord.__table__.c.id, "type", Integer())
        Base.metadata.create_all(engine)

    class TrackedSession(Session):
        rollbacks = 0
        commits = 0

        def rollback(self):
            TrackedSession.rollbacks += 1
            return super().rollback()

        def commit(self):
            TrackedSession.commits += 1
            return super().commit()

    factory = sessionmaker(engine, class_=TrackedSession, expire_on_commit=False)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with factory() as db:
        for user_id in (1, 2):
            db.add(User(
                id=user_id, username=f"user-{user_id}", password_hash="hash", role="user",
                is_active=True, timezone="UTC", currency_code="CNY",
                created_at=now, updated_at=now,
            ))
            db.add(NotificationSetting(
                user_id=user_id, email_enabled=True, same_day_enabled=True,
                same_day_time=time(0), advance_enabled=False, advance_time=time(9),
                updated_at=now,
            ))
        for plan_id, user_id in ((1, 1), (2, 1), (3, 2)):
            db.add(BillPlan(
                id=plan_id, user_id=user_id, name=f"plan-{plan_id}", amount=Decimal("1.00"),
                cycle_type="once", first_due_date=now.date(), cycle_days=None,
                is_enabled=True, created_at=now, updated_at=now,
            ))
        db.commit()
    TrackedSession.rollbacks = 0
    TrackedSession.commits = 0
    try:
        yield SimpleNamespace(session=factory), TrackedSession
    finally:
        engine.dispose()


def test_bad_rule_rolls_back_and_does_not_stop_rules_or_users(notification_database, monkeypatch, tmp_path):
    database, tracked = notification_database
    original = notifications.iter_plan_dates
    sent = []

    def failing_dates(plan, *args):
        if plan.id == 1:
            raise OverflowError("corrupt legacy cycle")
        return original(plan, *args)

    monkeypatch.setattr(notifications, "iter_plan_dates", failing_dates)
    monkeypatch.setattr(notifications, "_send_email", lambda *args: sent.append(args[3]))
    settings = SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path / "logs")))
    notifications.check_notifications(database, settings, None)
    assert sent == [
        f"plan-2 将于 {datetime.now(timezone.utc).date().isoformat()} 产生账单，金额 1.00。",
        f"plan-3 将于 {datetime.now(timezone.utc).date().isoformat()} 产生账单，金额 1.00。",
    ]
    assert tracked.rollbacks == 1
    with database.session() as db:
        records = db.scalars(select(NotificationRecord).order_by(NotificationRecord.plan_id)).all()
        assert [(record.plan_id, record.status) for record in records] == [(2, "sent"), (3, "sent")]
    # Previously sent records are still skipped, and no-op attempts end their transaction.
    commits = tracked.commits
    notifications.check_notifications(database, settings, None)
    assert len(sent) == 2
    assert tracked.commits - commits >= 2


def test_database_rule_failure_rolls_back_without_aborting_later_notifications(notification_database, monkeypatch, tmp_path):
    database, tracked = notification_database
    original = notifications._attempt_notification
    attempted = []

    def failing_attempt(db, settings, fernet, setting, plan, *args):
        attempted.append(plan.id)
        if plan.id == 1:
            # Simulate an exception after the plan row was acquired/modified.
            plan.name = "must roll back"
            db.flush()
            raise RuntimeError("database operation failed")
        return original(db, settings, fernet, setting, plan, *args)

    monkeypatch.setattr(notifications, "_attempt_notification", failing_attempt)
    monkeypatch.setattr(notifications, "_send_email", lambda *args: None)
    settings = SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path / "logs")))
    notifications.check_notifications(database, settings, None)
    assert attempted == [1, 2, 3]
    assert tracked.rollbacks == 1
    with database.session() as db:
        assert db.get(BillPlan, 1).name == "plan-1"
        assert [record.plan_id for record in db.scalars(select(NotificationRecord))] == [2, 3]


def test_bad_user_configuration_does_not_stop_next_user(notification_database, monkeypatch, tmp_path):
    database, tracked = notification_database
    with database.session() as db:
        db.get(User, 1).timezone = "invalid/timezone"
        db.commit()
    sent = []
    monkeypatch.setattr(notifications, "_send_email", lambda *args: sent.append(args[3]))
    settings = SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path / "logs")))
    notifications.check_notifications(database, settings, None)
    assert len(sent) == 1
    assert sent[0].startswith("plan-3 ")
    assert tracked.rollbacks == 1
