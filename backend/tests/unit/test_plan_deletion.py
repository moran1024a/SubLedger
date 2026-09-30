from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import plans
from app.api.dependencies import get_current_user, get_db
from app.errors import AppError, app_error_handler
from app.models import Base, BillOccurrence, BillPlan, NotificationRecord, User
from app.services import notifications
from app.services.billing import delete_plan, ensure_plan_occurrences, occurrence_response

TODAY = date(2026, 7, 22)
NOW = datetime(2026, 7, 22, 1, 2, 3)


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def seed_plan(db: Session, *, user_id: int = 1, plan_id: int = 10) -> tuple[User, BillPlan]:
    user = User(
        id=user_id,
        username=f"member-{user_id}",
        password_hash="hash",
        role="user",
        is_active=True,
        timezone="Asia/Shanghai",
        currency_code="CNY",
        created_at=NOW,
        updated_at=NOW,
    )
    plan = BillPlan(
        id=plan_id,
        user_id=user_id,
        name="云服务",
        amount=Decimal("12.50"),
        first_due_date=date(2026, 6, 22),
        cycle_type="monthly",
        cycle_days=None,
        is_enabled=True,
        note=None,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add_all([user, plan])
    db.flush()
    for bill_id, due_date in enumerate(
        (date(2026, 7, 21), TODAY, date(2026, 8, 22)),
        start=100,
    ):
        db.add(
            BillOccurrence(
                id=bill_id,
                user_id=user_id,
                plan_id=plan_id,
                due_date=due_date,
                amount_snapshot=Decimal("12.50"),
                is_valid=True,
                invalidated_by_plan_disable=False,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    db.flush()
    for record_id, bill_id, due_date in (
        (200, 100, date(2026, 7, 21)),
        (201, 101, TODAY),
        (202, 102, date(2026, 8, 22)),
    ):
        db.add(
            NotificationRecord(
                id=record_id,
                user_id=user_id,
                plan_id=plan_id,
                bill_id=bill_id,
                due_date=due_date,
                channel="email",
                reminder_type="same_day",
                status="sent",
                scheduled_at=NOW,
                sent_at=NOW,
                retry_count=0,
                error_message=None,
            )
        )
    db.commit()
    return user, plan


def test_delete_plan_preserves_passed_bill_and_removes_today_and_future(session_factory):
    with session_factory() as db:
        _, plan = seed_plan(db)
        delete_plan(db, plan, TODAY)
        db.commit()

        stored_plan = db.get(BillPlan, plan.id)
        bills = list(
            db.scalars(
                select(BillOccurrence)
                .where(BillOccurrence.plan_id == plan.id)
                .order_by(BillOccurrence.due_date)
            )
        )
        records = list(
            db.scalars(
                select(NotificationRecord).where(NotificationRecord.plan_id == plan.id)
            )
        )

        assert stored_plan is not None
        assert stored_plan.is_enabled is False
        assert stored_plan.deleted_at is not None
        assert [bill.due_date for bill in bills] == [date(2026, 7, 21)]
        assert [record.due_date for record in records] == [date(2026, 7, 21)]
        assert occurrence_response(bills[0], stored_plan, TODAY) == {
            "id": 100,
            "plan_id": 10,
            "plan_name": "云服务",
            "due_date": date(2026, 7, 21),
            "amount": "12.50",
            "is_valid": True,
            "time_status": "passed",
            "cycle_type": "monthly",
            "cycle_days": None,
        }
        assert ensure_plan_occurrences(db, stored_plan, TODAY) == []


def test_delete_endpoint_is_permanent_and_owner_scoped(session_factory, tmp_path, monkeypatch):
    with session_factory() as db:
        user, plan = seed_plan(db)
        other = User(
            id=2,
            username="other",
            password_hash="hash",
            role="user",
            is_active=True,
            timezone="UTC",
            currency_code="CNY",
            created_at=NOW,
            updated_at=NOW,
        )
        foreign_plan = BillPlan(
            id=20,
            user_id=2,
            name="其他规则",
            amount=Decimal("1.00"),
            first_due_date=TODAY,
            cycle_type="once",
            cycle_days=None,
            is_enabled=True,
            note=None,
            deleted_at=None,
            created_at=NOW,
            updated_at=NOW,
        )
        db.add_all([other, foreign_plan])
        db.commit()

    monkeypatch.setattr(plans, "local_today", lambda _: TODAY)

    def fail_log(*args, **kwargs):
        raise OSError("log directory unavailable")

    monkeypatch.setattr(plans, "write_user_log", fail_log)

    app = FastAPI()
    app.state.settings = SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path / "logs")))

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = "test-request"
        return await call_next(request)

    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(plans.router)

    def override_db():
        with session_factory() as db:
            yield db

    def override_user():
        with session_factory() as db:
            return db.get(User, user.id)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    with TestClient(app) as client:
        response = client.delete(f"/api/v1/plans/{plan.id}")
        repeated = client.delete(f"/api/v1/plans/{plan.id}")
        foreign = client.delete("/api/v1/plans/20")
        missing = client.delete("/api/v1/plans/999")

    assert response.status_code == 204
    assert repeated.status_code == 404
    assert repeated.json()["code"] == "BILL_PLAN_NOT_FOUND"
    assert foreign.status_code == 404
    assert foreign.json()["code"] == "BILL_PLAN_NOT_FOUND"
    assert missing.status_code == 404

    with session_factory() as db:
        assert db.get(BillPlan, plan.id).deleted_at is not None
        assert db.scalar(
            select(BillOccurrence).where(
                BillOccurrence.plan_id == plan.id,
                BillOccurrence.due_date >= TODAY,
            )
        ) is None


def test_notification_rechecks_schedule_and_bill_validity_after_lock(
    session_factory,
    monkeypatch,
):
    sent = []
    monkeypatch.setattr(notifications, "_send_email", lambda *args: sent.append(args))
    settings = SimpleNamespace(logging=SimpleNamespace(directory="unused"))
    notification_setting = SimpleNamespace(smtp_password_encrypted=None)

    with session_factory() as db:
        _, plan = seed_plan(db)
        occurrence = db.get(BillOccurrence, 101)
        db.execute(
            delete(NotificationRecord).where(
                NotificationRecord.plan_id == plan.id,
                NotificationRecord.due_date == TODAY,
            )
        )
        occurrence.is_valid = False
        db.commit()

        notifications._attempt_notification(
            db,
            settings,
            None,
            notification_setting,
            plan,
            SimpleNamespace(id=occurrence.id, is_valid=True),
            TODAY,
            "email",
            "same_day",
            NOW,
        )

        assert sent == []
        assert db.scalar(
            select(NotificationRecord).where(
                NotificationRecord.plan_id == plan.id,
                NotificationRecord.due_date == TODAY,
            )
        ) is None

        occurrence.is_valid = True
        plan.first_due_date = date(2026, 7, 23)
        db.commit()

        notifications._attempt_notification(
            db,
            settings,
            None,
            notification_setting,
            plan,
            occurrence,
            TODAY,
            "email",
            "same_day",
            NOW,
        )

        assert sent == []
        assert db.scalar(
            select(NotificationRecord).where(
                NotificationRecord.plan_id == plan.id,
                NotificationRecord.due_date == TODAY,
            )
        ) is None
