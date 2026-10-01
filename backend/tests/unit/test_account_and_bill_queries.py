from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import bills, users
from app.api.dependencies import get_current_user, get_db, require_admin
from app.config import load_settings
from app.errors import AppError, app_error_handler
from app.models import Base, BillOccurrence, BillPlan, User
from app.services import users as user_service

NOW = datetime(2026, 10, 1)
TODAY = date(2026, 10, 1)


@pytest.fixture
def client(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        for number in range(26):
            db.add(User(id=number, username=f'member-{number:02}', password_hash='hash',
                        role='admin' if number == 0 else 'user', is_active=number % 2 == 0,
                        timezone='Asia/Shanghai', currency_code='CNY', created_at=NOW, updated_at=NOW))
        db.flush()
        for number, owner in ((1, 1), (2, 2)):
            db.add(BillPlan(id=number, user_id=owner, name='Cloud 100%_storage', amount=10,
                            first_due_date=TODAY, cycle_type='monthly', is_enabled=True,
                            deleted_at=NOW if number == 1 else None, created_at=NOW, updated_at=NOW))
        db.flush()
        for number, due in enumerate((date(2026, 9, 29), date(2026, 9, 30), TODAY, date(2026, 10, 2)), 1):
            db.add(BillOccurrence(id=number, user_id=1, plan_id=1, due_date=due,
                                  amount_snapshot=10, is_valid=number != 4,
                                  invalidated_by_plan_disable=False, created_at=NOW, updated_at=NOW))
        db.add(BillOccurrence(id=5, user_id=2, plan_id=2, due_date=TODAY,
                              amount_snapshot=10, is_valid=True, invalidated_by_plan_disable=False,
                              created_at=NOW, updated_at=NOW))
        db.commit()
    app = FastAPI()
    app.include_router(bills.router)
    app.include_router(users.router)
    app.add_exception_handler(AppError, app_error_handler)
    app.state.settings = SimpleNamespace()

    @app.middleware('http')
    async def request_id(request: Request, call_next):
        request.state.request_id = 'test'
        return await call_next(request)

    def session():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, timezone='Asia/Shanghai')
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=0)
    monkeypatch.setattr(bills, 'local_today', lambda zone: TODAY)
    monkeypatch.setattr(users, 'write_user_log', lambda *args, **kwargs: None)
    monkeypatch.setattr(user_service, 'hash_password', lambda password: 'hash')
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()


def test_create_beyond_twenty_and_summary_without_quota(client):
    response = client.post('/api/v1/admin/users', json={'username': 'new-member', 'password': 'password123'})
    assert response.status_code == 201, response.text
    assert response.json()['id'] == 26
    assert client.get('/api/v1/admin/summary').json() == {
        'total_users': 27, 'active_users': 13, 'inactive_users': 13,
    }
    duplicate = client.post('/api/v1/admin/users', json={'username': 'new-member', 'password': 'password123'})
    assert duplicate.status_code == 409


def test_user_pagination_and_combined_filters(client):
    response = client.get('/api/v1/admin/users', params={'page': 2, 'page_size': 20}).json()
    assert response['total'] == 26
    assert [item['id'] for item in response['items']] == list(range(20, 26))
    filtered = client.get('/api/v1/admin/users', params={'q': 'MEMBER-0', 'is_active': False}).json()
    assert [item['id'] for item in filtered['items']] == [1, 3, 5, 7, 9]
    assert filtered['total'] == 5
    assert client.get('/api/v1/admin/users', params={'q': '%'}).json()['total'] == 0
    assert client.get('/api/v1/admin/users', params={'page_size': 101}).status_code == 422


def test_bill_default_compatibility_and_upcoming(client):
    assert [item['id'] for item in client.get('/api/v1/bills').json()['items']] == [1, 2, 3, 4]
    result = client.get('/api/v1/bills', params={'time_status': 'upcoming'}).json()
    assert [item['id'] for item in result['items']] == [3, 4]
    assert all(item['time_status'] == 'upcoming' for item in result['items'])
    assert client.get('/api/v1/bills', params={'time_status': 'upcoming', 'is_valid': False}).json()['total'] == 1


def test_history_descending_and_date_boundaries(client):
    result = client.get('/api/v1/bills', params={'time_status': 'passed', 'sort': 'desc', 'page_size': 1}).json()
    assert result['total'] == 2
    assert result['items'][0]['id'] == 2
    result = client.get('/api/v1/bills', params={'start_date': '2026-10-01', 'end_date': '2026-10-01'}).json()
    assert [item['id'] for item in result['items']] == [3]


def test_search_deleted_plan_history_and_escape_wildcards(client):
    result = client.get('/api/v1/bills', params={'q': 'cloud 100%_', 'sort': 'desc'}).json()
    assert result['total'] == 4
    assert [item['id'] for item in result['items']] == [4, 3, 2, 1]
    assert client.get('/api/v1/bills', params={'q': 'missing%'}).json()['total'] == 0
    assert client.get('/api/v1/bills', params={'plan_id': 2}).json()['total'] == 0


@pytest.mark.parametrize('params,status', [
    ({'start_date': '2026-10-02', 'end_date': '2026-10-01'}, 400),
    ({'start_date': '2026-02-30'}, 422),
    ({'sort': 'unexpected'}, 422),
    ({'q': 'x' * 129}, 422),
    ({'page': 0}, 422),
])
def test_bill_invalid_queries(client, params, status):
    assert client.get('/api/v1/bills', params=params).status_code == status


def test_legacy_quota_is_ignored(tmp_path):
    template = Path('config/config.example.toml').read_text()
    config = tmp_path / 'config.toml'
    config.write_text(template.replace('[app]', '[app]\nmax_users = 1'))
    settings = load_settings(config)
    assert not hasattr(settings.app, 'max_users')
