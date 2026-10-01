from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Base, BillOccurrence, BillPlan, User
from app.schemas import BillPlanCreate, BillPlanPatch
from app.services import statistics
from app.services.billing import (
    _future_plan_dates,
    create_plan,
    cycle_date,
    ensure_plan_occurrences,
    iter_plan_dates,
    update_plan,
)

TODAY = date(2026, 9, 30)
NOW = datetime(2026, 9, 30, 0, 0)


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            next_ids = {BillPlan: 1, BillOccurrence: 1}

            @event.listens_for(session, "before_flush")
            def assign_bigint_ids(session, _flush_context, _instances):
                # SQLite only autoincrements INTEGER keys, unlike MySQL BIGINT.
                for item in session.new:
                    if type(item) in next_ids and item.id is None:
                        item.id = next_ids[type(item)]
                        next_ids[type(item)] += 1

            yield session
    finally:
        engine.dispose()


def seed_user(db: Session) -> User:
    user = User(
        id=1,
        username="cycle-test",
        password_hash="hash",
        role="user",
        is_active=True,
        timezone="UTC",
        currency_code="CNY",
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(user)
    db.flush()
    return user


def make_plan(first_due_date=TODAY, cycle_type="custom_days", cycle_days=1) -> BillPlan:
    return BillPlan(
        name="周期测试",
        amount=Decimal("12.50"),
        first_due_date=first_due_date,
        cycle_type=cycle_type,
        cycle_days=cycle_days,
        is_enabled=True,
        created_at=NOW,
        updated_at=NOW,
    )


def create_payload(cycle_days: int, first_due_date=TODAY) -> BillPlanCreate:
    return BillPlanCreate(
        name="周期测试",
        amount="12.50",
        first_due_date=first_due_date,
        cycle_type="custom_days",
        cycle_days=cycle_days,
    )


@pytest.mark.parametrize("days", [1, 36500])
def test_create_and_patch_accept_cycle_day_boundaries(days):
    assert create_payload(days).cycle_days == days
    assert BillPlanPatch(cycle_days=days).cycle_days == days


@pytest.mark.parametrize("days", [-1, 0, 36501, 4294967295])
def test_create_and_patch_reject_out_of_range_cycles(days):
    with pytest.raises(ValidationError):
        create_payload(days)
    with pytest.raises(ValidationError):
        BillPlanPatch(cycle_days=days)


@pytest.mark.parametrize(
    "first_due, cycle_type, days, start, end, expected",
    [
        (
            date(2024, 1, 31), "monthly", None,
            date(2024, 2, 1), date(2024, 4, 30),
            [date(2024, 2, 29), date(2024, 3, 31), date(2024, 4, 30)],
        ),
        (
            date(2023, 1, 31), "monthly", None,
            date(2023, 2, 1), date(2023, 3, 31),
            [date(2023, 2, 28), date(2023, 3, 31)],
        ),
        (
            date(2024, 2, 29), "yearly", None,
            date(2025, 1, 1), date(2026, 12, 31),
            [date(2025, 2, 28), date(2026, 2, 28)],
        ),
        (
            date(2024, 1, 31), "quarterly", None,
            date(2024, 2, 1), date(2024, 12, 31),
            [date(2024, 4, 30), date(2024, 7, 31), date(2024, 10, 31)],
        ),
        (
            TODAY, "custom_days", 10,
            date(2026, 10, 1), date(2026, 10, 30),
            [date(2026, 10, 10), date(2026, 10, 20), date(2026, 10, 30)],
        ),
    ],
)
def test_iterator_preserves_month_end_leap_year_and_custom_dates(
    first_due, cycle_type, days, start, end, expected,
):
    plan = make_plan(first_due, cycle_type, days)
    assert list(iter_plan_dates(plan, start, end)) == expected


@pytest.mark.parametrize("cycle_type", ["monthly", "quarterly", "yearly", "custom_days", "once"])
def test_iterators_stop_at_maximum_date(cycle_type):
    plan = make_plan(date.max, cycle_type, 1 if cycle_type == "custom_days" else None)
    assert list(iter_plan_dates(plan, date.max, date.max)) == [date.max]
    assert list(_future_plan_dates(plan, date.max)) == [date.max]


@pytest.mark.parametrize("cycle_type, days", [("yearly", None), ("custom_days", 36500)])
def test_future_iterator_stops_when_first_future_date_exceeds_maximum(cycle_type, days):
    plan = make_plan(date(9999, 1, 1), cycle_type, days)
    assert list(_future_plan_dates(plan, date.max)) == []


@pytest.mark.parametrize("cycle_type, days", [("monthly", None), ("custom_days", 4294967295)])
def test_cycle_date_reports_overflow_before_constructing_an_invalid_date(cycle_type, days):
    with pytest.raises(OverflowError):
        cycle_date(date.max, cycle_type, 1, days)


def test_legacy_large_cycle_keeps_representable_date_and_stops():
    plan = make_plan(cycle_days=4294967295)
    assert list(iter_plan_dates(plan, TODAY, date.max)) == [TODAY]
    assert list(_future_plan_dates(plan, TODAY)) == [TODAY]
    assert list(_future_plan_dates(plan, date(2026, 10, 1))) == []


@pytest.mark.parametrize("days", [None, 0, -1])
def test_iterators_skip_legacy_invalid_custom_cycles(days):
    plan = make_plan(cycle_days=days)
    assert list(iter_plan_dates(plan, TODAY, date.max)) == []
    assert list(_future_plan_dates(plan, TODAY)) == []


def test_create_near_maximum_date_generates_only_available_occurrences(db):
    user = seed_user(db)
    plan = create_plan(db, user, create_payload(1, date(9999, 12, 30)), date(9999, 12, 30))
    db.flush()
    assert [
        row.due_date for row in db.scalars(
            select(BillOccurrence)
            .where(BillOccurrence.plan_id == plan.id)
            .order_by(BillOccurrence.due_date)
        )
    ] == [date(9999, 12, 30), date.max]
    assert ensure_plan_occurrences(db, plan, date.max) == []


def test_legacy_large_cycle_does_not_break_occurrence_creation_or_statistics(db, monkeypatch):
    user = seed_user(db)
    plan = make_plan(cycle_days=4294967295)
    plan.user_id = user.id
    db.add(plan)
    db.flush()
    assert [row.due_date for row in ensure_plan_occurrences(db, plan, TODAY)] == [TODAY]
    db.flush()
    monkeypatch.setattr(statistics, "local_today", lambda _: TODAY)
    result = statistics.summary(db, user)
    assert result["today"] == {"amount": "12.50", "count": 1}
    assert result["current_year"] == {"amount": "12.50", "count": 1}


@pytest.mark.parametrize("days", [None, 0, 36501, 4294967295])
def test_update_rejects_invalid_cycle_after_merging_with_existing_plan(db, days):
    user = seed_user(db)
    plan = make_plan(cycle_days=days)
    plan.user_id = user.id
    db.add(plan)
    db.flush()
    values = BillPlanPatch(name="新名称").model_dump(exclude_unset=True)
    with pytest.raises(AppError) as error:
        update_plan(db, plan, values, TODAY)
    assert error.value.code == "BILL_INVALID_CYCLE"
    assert plan.name == "周期测试"


def test_update_checks_custom_cycle_against_retained_days(db):
    user = seed_user(db)
    plan = make_plan(cycle_type="monthly", cycle_days=None)
    plan.user_id = user.id
    db.add(plan)
    db.flush()
    with pytest.raises(AppError):
        update_plan(db, plan, {"cycle_type": "custom_days"}, TODAY)
    assert plan.cycle_type == "monthly"
    assert update_plan(db, plan, {"cycle_type": "custom_days", "cycle_days": 36500}, TODAY)
    assert plan.cycle_type == "day" and plan.cycle_interval == 36500
    assert plan.cycle_days is None
    assert update_plan(db, plan, {"cycle_type": "monthly"}, TODAY)
    assert plan.cycle_days is None


@pytest.mark.parametrize('kind, interval, first, expected', [
    ('year', 2, date(2024, 2, 29), [date(2024, 2, 29), date(2026, 2, 28), date(2028, 2, 29)]),
    ('year', 3, date(2024, 2, 29), [date(2024, 2, 29), date(2027, 2, 28), date(2030, 2, 28)]),
    ('month', 2, date(2024, 7, 31), [date(2024, 7, 31), date(2024, 9, 30), date(2024, 11, 30)]),
    ('week', 2, date(2024, 2, 20), [date(2024, 2, 20), date(2024, 3, 5), date(2024, 3, 19)]),
    ('day', 10, date(2024, 2, 20), [date(2024, 2, 20), date(2024, 3, 1), date(2024, 3, 11)]),
])
def test_general_calendar_cycles(kind, interval, first, expected):
    plan = make_plan(first, kind, None)
    plan.cycle_interval = interval
    assert list(iter_plan_dates(plan, first, expected[-1])) == expected
    assert [cycle_date(first, kind, i, cycle_interval=interval) for i in range(3)] == expected
    assert list(iter_plan_dates(plan, expected[1], expected[1])) == [expected[1]]


@pytest.mark.parametrize('kind, limit', [('day', 36500), ('week', 5214), ('month', 1200), ('year', 100), ('once', 1)])
def test_generic_interval_limits(kind, limit):
    for value in (1, limit):
        BillPlanCreate(name='test', amount=1, first_due_date=TODAY, cycle_type=kind, cycle_interval=value)
    for value in (0, -1, limit + 1, 1.5, True, '2'):
        with pytest.raises(ValidationError):
            BillPlanCreate(name='test', amount=1, first_due_date=TODAY, cycle_type=kind, cycle_interval=value)


def test_generic_create_update_statistics_and_equivalent_legacy_patch(db, monkeypatch):
    user = seed_user(db)
    payload = BillPlanCreate(name='two years', amount=240, first_due_date=TODAY, cycle_type='year', cycle_interval=2)
    plan = create_plan(db, user, payload, TODAY)
    db.flush()
    ids = list(db.scalars(select(BillOccurrence.id)))
    monkeypatch.setattr(statistics, 'local_today', lambda _: TODAY)
    totals = statistics.summary(db, user)
    assert totals['averages'] == {'monthly': '10.00', 'daily': '0.33'}
    assert totals['current_year'] == {'amount': '240.00', 'count': 1}
    assert not update_plan(db, plan, {'cycle_type': 'year'}, TODAY)
    assert plan.cycle_interval == 2
    assert not update_plan(db, plan, {'cycle_type': 'year', 'cycle_interval': 2, 'name': 'renamed'}, TODAY)
    assert list(db.scalars(select(BillOccurrence.id))) == ids
    assert update_plan(db, plan, {'cycle_type': 'month', 'cycle_interval': 3}, TODAY)
    db.flush()
    ids = list(db.scalars(select(BillOccurrence.id)))
    assert not update_plan(db, plan, {'cycle_type': 'quarterly'}, TODAY)
    assert list(db.scalars(select(BillOccurrence.id))) == ids
    with pytest.raises(AppError):
        update_plan(db, plan, {'cycle_type': 'year', 'cycle_interval': 101}, TODAY)


@pytest.mark.parametrize('kind', ['day', 'week', 'month', 'year'])
def test_general_cycles_stop_at_representable_date(kind):
    plan = make_plan(date.max, kind, None)
    plan.cycle_interval = 2
    assert list(iter_plan_dates(plan, date.max, date.max)) == [date.max]
