from datetime import date, datetime
from decimal import Decimal
from itertools import count
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import bills
from app.api.dependencies import get_current_user, get_db
from app.models import Base, BillOccurrence, BillPlan, User
from app.services import bill_calendar, billing

TODAY = date(2026, 11, 7)
NOW = datetime(2026, 11, 7)


@pytest.fixture
def store(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(bill_calendar, 'local_today', lambda zone: TODAY)
    with factory() as db:
        users = [User(id=user_id, username=f'user{user_id}', password_hash='unused',
                      role='user', is_active=True, timezone='UTC', currency_code='CNY',
                      created_at=NOW, updated_at=NOW) for user_id in (1, 2)]
        db.add_all(users)
        db.commit()
        ids = count(1)

        def plan(plan_id=1, **values):
            fields = dict(id=plan_id, user_id=1, name=f'规则{plan_id}', amount=Decimal('10.00'),
                          first_due_date=date(2026, 1, 1), cycle_type='month', cycle_interval=1,
                          is_enabled=True, created_at=NOW, updated_at=NOW)
            fields.update(values)
            result = BillPlan(**fields)
            db.add(result)
            db.flush()
            return result

        def occurrence(plan, due=TODAY, amount='8.00', valid=True):
            result = BillOccurrence(id=next(ids), user_id=plan.user_id, plan_id=plan.id,
                                    due_date=due, amount_snapshot=Decimal(amount), is_valid=valid,
                                    invalidated_by_plan_disable=False, created_at=NOW, updated_at=NOW)
            db.add(result)
            db.flush()
            return result

        yield SimpleNamespace(db=db, user=users[0], plan=plan, occurrence=occurrence,
                              factory=factory, engine=engine)
    engine.dispose()


def test_recorded_amounts_take_precedence_and_invalid_dates_are_not_reinferred(store):
    plan = store.plan(cycle_type='day', amount=Decimal('1.25'), first_due_date=date(2026, 11, 1))
    store.occurrence(plan, date(2026, 11, 6), '.80')
    today = store.occurrence(plan, TODAY, '.99')
    store.occurrence(plan, date(2026, 11, 8), '1.11', valid=False)
    store.occurrence(plan, date(2026, 11, 9), '1.25')
    result = bill_calendar.calendar_month(store.db, store.user, '2026-11')
    days = {item['date']: item for item in result['days']}
    assert result['count'] == 24
    assert result['amount'] == '29.29'
    assert result['estimated_count'] == 21
    assert date(2026, 11, 8) not in days
    assert days[TODAY]['bills'][0]['bill_id'] == today.id
    assert days[TODAY]['bills'][0]['amount'] == '0.99'
    assert not days[TODAY]['bills'][0]['is_estimated']
    assert days[date(2026, 11, 10)]['bills'][0]['bill_id'] is None
    assert days[date(2026, 11, 10)]['bills'][0]['is_estimated']
    assert days[date(2026, 11, 10)]['amount'] == '1.25'


def test_past_months_only_include_actual_history(store):
    plan = store.plan(cycle_type='day', first_due_date=date(2020, 1, 1))
    assert bill_calendar.calendar_month(store.db, store.user, '2026-10')['days'] == []
    store.occurrence(plan, date(2026, 10, 31), '3.50')
    result = bill_calendar.calendar_month(store.db, store.user, '2026-10')
    assert result['amount'] == '3.50'
    assert result['count'] == 1
    assert result['estimated_count'] == 0


def test_disabled_deleted_and_other_users_are_not_projected_but_history_survives(store):
    disabled = store.plan(1, is_enabled=False, cycle_type='day')
    deleted = store.plan(2, deleted_at=NOW, cycle_type='day')
    foreign = store.plan(3, user_id=2, cycle_type='day')
    once = store.plan(4, cycle_type='once', first_due_date=date(2026, 11, 15))
    store.occurrence(disabled, date(2026, 11, 4), '17.00')
    store.occurrence(deleted, date(2026, 11, 5), '27.00')
    store.occurrence(foreign, TODAY, '999.00')
    store.occurrence(once, date(2026, 11, 15), '4.50')
    result = bill_calendar.calendar_month(store.db, store.user, '2026-11')
    assert result['amount'] == '48.50'
    assert result['count'] == 3
    assert result['estimated_count'] == 0
    assert [item['bills'][0]['plan_status'] for item in result['days']] == ['disabled', 'deleted', 'enabled']
    assert all(b['plan_id'] != foreign.id for item in result['days'] for b in item['bills'])


@pytest.mark.parametrize('anchor,kind,interval,month,expected', [
    (date(2026, 1, 31), 'month', 1, '2028-02', [29]),
    (date(2026, 1, 31), 'month', 1, '2028-03', [31]),
    (date(2026, 1, 31), 'month', 3, '2027-04', [30]),
    (date(2024, 2, 29), 'year', 1, '2027-02', [28]),
    (date(2024, 2, 29), 'year', 1, '2028-02', [29]),
    (date(2026, 10, 30), 'day', 10, '2026-11', [9, 19, 29]),
    (date(2026, 11, 7), 'week', 2, '2026-11', [7, 21]),
    (date(2026, 1, 31), 'quarterly', 1, '2027-04', [30]),
    (date(2027, 3, 1), 'month', 1, '2027-02', []),
])
def test_calendar_reuses_anchored_cycle_rules(store, anchor, kind, interval, month, expected):
    store.plan(first_due_date=anchor, cycle_type=kind, cycle_interval=interval)
    result = bill_calendar.calendar_month(store.db, store.user, month)
    assert [item['date'].day for item in result['days']] == expected
    assert result['count'] == result['estimated_count'] == len(expected)


def test_calendar_is_read_only_and_does_not_truncate_days_at_the_list_page_limit(store):
    for plan_id in range(1, 206):
        store.plan(plan_id, first_due_date=TODAY)
    store.db.commit()
    queries = []

    def capture(connection, cursor, statement, parameters, context, many):
        queries.append(statement.lstrip().upper())

    event.listen(store.engine, 'before_cursor_execute', capture)
    try:
        result = bill_calendar.calendar_month(store.db, store.user, '2026-11')
    finally:
        event.remove(store.engine, 'before_cursor_execute', capture)
    assert result['count'] == 205
    assert result['amount'] == '2050.00'
    assert len(result['days'][0]['bills']) == 205
    assert len(queries) <= 2
    assert all(query.startswith('SELECT') for query in queries)
    assert not store.db.new and not store.db.dirty and not store.db.deleted
    assert list(store.db.scalars(select(BillOccurrence))) == []


def test_calendar_uses_account_timezone_for_today_and_default_month(store, monkeypatch):
    monkeypatch.setattr(bill_calendar, 'local_today', billing.local_today)
    monkeypatch.setattr(billing, 'utc_now', lambda: datetime(2026, 11, 1, 0, 30))
    store.user.timezone = 'America/Los_Angeles'
    result = bill_calendar.calendar_month(store.db, store.user)
    assert result['today'] == date(2026, 10, 31)
    assert result['month'] == '2026-10'
    store.user.timezone = 'Pacific/Kiritimati'
    result = bill_calendar.calendar_month(store.db, store.user)
    assert result['today'] == date(2026, 11, 1)
    assert result['month'] == '2026-11'


def test_calendar_route_returns_full_month_and_validates_months(store):
    store.plan(first_due_date=TODAY)
    store.db.commit()
    app = FastAPI()
    app.include_router(bills.router)

    def get_session():
        with store.factory() as db:
            yield db

    app.dependency_overrides[get_db] = get_session
    app.dependency_overrides[get_current_user] = lambda: store.user
    with TestClient(app) as client:
        response = client.get('/api/v1/bills/calendar')
        assert response.status_code == 200
        assert response.json()['month'] == '2026-11'
        assert response.json()['days'][0]['date'] == '2026-11-07'
        assert response.json()['days'][0]['bills'][0]['bill_id'] is None
        for invalid in ('2026-13', '2026-00', '2026-1', '26-11', '2026-11-07', '0000-01', '0999-12', 'x'):
            assert client.get('/api/v1/bills/calendar', params={'month': invalid}).status_code == 422
        assert client.get('/api/v1/bills/calendar', params={'month': '1000-01'}).status_code == 200
        assert client.get('/api/v1/bills/calendar', params={'month': '9999-12'}).status_code == 200
