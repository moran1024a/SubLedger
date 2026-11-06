from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import plan_groups, plans
from app.api.dependencies import get_current_user, get_db
from app.errors import AppError, app_error_handler
from app.models import Base, BillOccurrence, BillPlan, BillPlanGroup, NotificationRecord, User
from app.schemas import BillPlanCreate, PlanLayoutWrite
from app.services.billing import create_plan, update_plan
from app.services.plan_groups import edit_group, layout_snapshot, save_layout

NOW = datetime(2026, 11, 7)
TODAY = NOW.date()


@pytest.fixture
def sessions():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)

    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)

    @event.listens_for(factory, 'before_flush')
    def sqlite_ids(db, *_):
        for model in (BillPlan, BillOccurrence):
            next_id = (db.scalar(select(func.max(model.id))) or 0) + 1
            for row in db.new:
                if isinstance(row, model) and row.id is None:
                    row.id = next_id
                    next_id += 1

    with factory() as db:
        for user_id in (1, 2):
            db.add(User(id=user_id, username=f'user{user_id}', password_hash='unused', role='user', is_active=True, timezone='UTC', currency_code='CNY', created_at=NOW, updated_at=NOW))
        db.flush()
        db.add_all([
            BillPlanGroup(id=1, user_id=1, name='未分组', sort_order=0, is_default=True),
            BillPlanGroup(id=2, user_id=1, name='服务', sort_order=1),
            BillPlanGroup(id=3, user_id=2, name='未分组', sort_order=0, is_default=True),
        ])
        db.flush()
        for plan_id, user_id, group_id, position in ((10, 1, None, 1), (11, 1, None, 0), (12, 1, 2, 0), (20, 2, None, 0)):
            db.add(BillPlan(id=plan_id, user_id=user_id, group_id=group_id, sort_order=position, name=f'规则{plan_id}', amount=Decimal('10.00'), first_due_date=TODAY, cycle_type='month', cycle_interval=1, is_enabled=True, created_at=NOW, updated_at=NOW))
        db.flush()
        db.add(BillOccurrence(id=30, user_id=1, plan_id=12, due_date=TODAY, amount_snapshot=Decimal('8.00'), is_valid=False, invalidated_by_plan_disable=False, created_at=NOW, updated_at=NOW))
        db.flush()
        db.add(NotificationRecord(id=40, user_id=1, plan_id=12, bill_id=30, due_date=TODAY, channel='email', reminder_type='same_day', status='sent', scheduled_at=NOW, sent_at=NOW, retry_count=0))
        db.commit()
    yield factory
    engine.dispose()


def payload(version, groups=((1, [11, 10]), (2, [12]))):
    return PlanLayoutWrite(version=version, groups=[{'id': group_id, 'plan_ids': ids} for group_id, ids in groups])


def billing_state(db):
    return (
        [(b.id, b.plan_id, b.due_date, b.amount_snapshot, b.is_valid, b.invalidated_by_plan_disable, b.updated_at) for b in db.scalars(select(BillOccurrence))],
        [(r.id, r.bill_id, r.status, r.sent_at, r.retry_count) for r in db.scalars(select(NotificationRecord))],
        [(p.id, p.amount, p.first_due_date, p.cycle_type, p.cycle_interval, p.updated_at) for p in db.scalars(select(BillPlan).order_by(BillPlan.id))],
    )


def test_group_and_rule_reordering_moves_across_groups_without_changing_bills(sessions):
    with sessions() as db:
        before = billing_state(db)
        snapshot = layout_snapshot(db, 1)
        assert [p['id'] for p in snapshot['plans']] == [11, 10, 12]
        result = save_layout(db, 1, payload(snapshot['version'], ((2, [10, 12]), (1, [11]))))
        db.commit()
        assert result['version'] != snapshot['version']
        assert [g.id for g in result['groups']] == [2, 1]
        assert [p['id'] for p in result['plans']] == [10, 12, 11]
        assert db.get(BillPlan, 10).group_id == 2
        assert billing_state(db) == before
    with sessions() as db:
        assert [p['id'] for p in layout_snapshot(db, 1)['plans']] == [10, 12, 11]


@pytest.mark.parametrize('groups', [
    ((1, [11]), (2, [12])),  # Missing rule.
    ((1, [11, 10]), (2, [12, 10])),  # Duplicate rule.
    ((1, [11, 10]), (2, [12, 20])),  # Another user's rule.
    ((1, [11, 10, 12]),),  # Missing group.
    ((1, [11, 10]), (3, [12])),  # Another user's group.
    ((1, [11, 10]), (1, [12])),  # Duplicate group.
])
def test_invalid_layout_is_rejected_without_partial_changes(sessions, groups):
    with sessions() as db:
        snapshot = layout_snapshot(db, 1)
        with pytest.raises(AppError) as caught:
            save_layout(db, 1, payload(snapshot['version'], groups))
        assert caught.value.code == 'BILL_LAYOUT_INVALID'
        assert layout_snapshot(db, 1)['version'] == snapshot['version']


def test_stale_layout_cannot_overwrite_another_change(sessions):
    with sessions() as db:
        version = layout_snapshot(db, 1)['version']
        result = edit_group(db, 1, version, name='家庭')
        db.commit()
        with pytest.raises(AppError) as caught:
            save_layout(db, 1, payload(version))
        assert caught.value.code == 'BILL_LAYOUT_CHANGED'
        assert layout_snapshot(db, 1)['version'] == result['version']


def test_delete_group_moves_live_and_deleted_rules_and_preserves_all_bills(sessions):
    with sessions() as db:
        db.get(BillPlan, 10).group_id = 2
        db.get(BillPlan, 10).deleted_at = NOW
        db.flush()
        before = billing_state(db)
        edit_group(db, 1, layout_snapshot(db, 1)['version'], group_id=2, remove=True)
        db.commit()
        assert db.get(BillPlanGroup, 2) is None
        assert db.get(BillPlan, 10).group_id is None
        assert db.get(BillPlan, 12).group_id is None
        assert [p['id'] for p in layout_snapshot(db, 1)['plans']] == [11, 12]
        assert billing_state(db) == before


@pytest.mark.parametrize('kwargs, code', [
    ({'group_id': 1, 'name': '改名'}, 'BILL_DEFAULT_GROUP'),
    ({'group_id': 1, 'remove': True}, 'BILL_DEFAULT_GROUP'),
    ({'group_id': 3, 'name': '改名'}, 'BILL_GROUP_NOT_FOUND'),
    ({'name': '服务'}, 'BILL_GROUP_NAME_CONFLICT'),
])
def test_default_group_and_other_users_are_protected(sessions, kwargs, code):
    with sessions() as db:
        with pytest.raises(AppError) as caught:
            edit_group(db, 1, layout_snapshot(db, 1)['version'], **kwargs)
        assert caught.value.code == code


def test_new_rules_append_to_selected_group_and_patch_can_move_to_ungrouped(sessions):
    with sessions() as db:
        plan = create_plan(db, db.get(User, 1), BillPlanCreate(name='新规则', amount='3.00', first_due_date=TODAY, cycle_type='once', group_id=2), TODAY)
        db.commit()
        assert plan.group_id == 2
        assert plan.sort_order == 1
        bills = [(b.id, b.due_date) for b in db.scalars(select(BillOccurrence).where(BillOccurrence.plan_id == plan.id))]
        assert update_plan(db, plan, {'group_id': None}, TODAY) is False
        db.commit()
        assert plan.group_id is None
        assert plan.sort_order == 2
        assert [(b.id, b.due_date) for b in db.scalars(select(BillOccurrence).where(BillOccurrence.plan_id == plan.id))] == bills
        with pytest.raises(AppError) as caught:
            update_plan(db, plan, {'group_id': 3}, TODAY)
        assert caught.value.code == 'BILL_GROUP_NOT_FOUND'


def test_layout_routes_validate_names_and_return_saved_order(sessions, monkeypatch):
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(plan_groups.router)
    app.include_router(plans.router)
    app.state.settings = SimpleNamespace()
    monkeypatch.setattr(plan_groups, 'write_user_log', lambda *args, **kwargs: None)

    @app.middleware('http')
    async def request_id(request, call_next):
        request.state.request_id = 'test'
        return await call_next(request)

    def get_session():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = get_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    with TestClient(app) as client:
        response = client.get('/api/v1/plans/layout')
        assert response.status_code == 200
        snapshot = response.json()
        response = client.post('/api/v1/plan-groups', json={'name': '  家庭  ', 'version': snapshot['version']})
        assert response.status_code == 201
        snapshot = response.json()
        assert snapshot['groups'][-1]['name'] == '家庭'
        assert client.post('/api/v1/plan-groups', json={'name': '   ', 'version': snapshot['version']}).status_code == 422
        assert client.post('/api/v1/plan-groups', json={'name': 'x' * 65, 'version': snapshot['version']}).status_code == 422
        new_id = snapshot['groups'][-1]['id']
        response = client.put('/api/v1/plans/layout', json=payload(snapshot['version'], ((2, [10]), (new_id, [12]), (1, [11]))).model_dump())
        assert response.status_code == 200
        snapshot = response.json()
        assert [p['id'] for p in client.get('/api/v1/plans').json()] == [10, 12, 11]
        assert client.request('DELETE', f'/api/v1/plan-groups/{new_id}', json={'version': snapshot['version']}).status_code == 200
        assert client.get('/api/v1/plan-groups').status_code == 200
