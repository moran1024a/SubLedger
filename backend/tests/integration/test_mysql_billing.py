"""Opt-in real MySQL tests; each test owns a newly created disposable database."""

import os
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.api.bills import _locked_owned_bill
from app.models import Base, BillOccurrence, BillPlan, NotificationRecord, User
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
            None, SimpleNamespace(smtp_password_encrypted=None), plan, None,
            TODAY, "email", "same_day", NOW,
        )
        stale.commit()
    assert sent == []
