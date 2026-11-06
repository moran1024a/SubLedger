from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.api import bills, notification_records
from app.api.dependencies import get_current_user, get_db
from app.api.plans import _owned_plan
from app.errors import AppError
from app.models import Base, BillOccurrence, BillPlan, BillPlanGroup, NotificationRecord, NotificationSetting, User
from app.schemas import BillPlanCreate, BillOccurrenceResponse, NotificationRecordPage, ValidityPatch
from app.services import billing, notifications, plan_lifecycle, statistics
from app.services.bill_calendar import calendar_month


@pytest.fixture
def store(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'endings.db'))
    event.listen(engine, 'connect', lambda connection, _: connection.execute('PRAGMA foreign_keys=ON'))
    with monkeypatch.context() as patch:
        for model in (BillPlan, BillPlanGroup, BillOccurrence, NotificationRecord):
            patch.setattr(model.__table__.c.id, 'type', Integer())
        Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    clock = SimpleNamespace(now=datetime(2026, 11, 7, 10))
    for module in (billing, notifications, plan_lifecycle, notification_records):
        monkeypatch.setattr(module, 'utc_now', lambda: clock.now)
    settings = SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path / 'logs')))
    sent = []
    monkeypatch.setattr(notifications, '_prepare_delivery', lambda *args: ('smtp.test', []))
    monkeypatch.setattr(notifications, '_send_email', lambda *args: sent.append(('email', args[2], args[3])))
    monkeypatch.setattr(notifications, '_send_feishu', lambda *args: sent.append(('feishu', args[2])))
    with factory() as db:
        db.add(User(id=1, username='ending-user', password_hash='hash', role='user', is_active=True,
                    timezone='UTC', currency_code='CNY', created_at=clock.now, updated_at=clock.now))
        db.flush()
        db.add(BillPlanGroup(user_id=1, name='未分组', is_default=True))
        db.add(NotificationSetting(user_id=1, email_enabled=True, advance_enabled=True, advance_days=3,
                                   advance_time=time(9), same_day_enabled=True, same_day_time=time(8, 30),
                                   updated_at=clock.now))
        db.commit()

    def create(kind='month', due=date(2026, 11, 15), interval=1, enabled=True, user_id=1):
        with factory() as db:
            plan = billing.create_plan(db, db.get(User, user_id), BillPlanCreate(
                name='订阅规则', amount='12.50', cycle_type=kind, cycle_interval=interval,
                first_due_date=due,
            ), clock.now.date())
            if not enabled:
                billing.disable_plan(db, plan, clock.now.date())
            db.commit()
            return plan.id

    database = SimpleNamespace(session=factory)
    yield SimpleNamespace(db=factory, database=database, create=create, clock=clock, sent=sent,
                          notify=lambda: notifications.check_notifications(database, settings, None),
                          finish=lambda: plan_lifecycle.finish_ended_plans(database, settings), settings=settings)
    engine.dispose()


def test_disable_fixes_end_date_and_reenable_cancels_it(store):
    pid = store.create(due=date(2026, 10, 15))
    with store.db() as db:
        plan = db.get(BillPlan, pid)
        billing.disable_plan(db, plan, date(2026, 11, 7))
        assert plan.end_date == date(2026, 11, 15)
        billing.disable_plan(db, plan, date(2026, 11, 16))
        billing.update_plan(db, plan, {'name': '改名'}, date(2026, 11, 16))
        assert plan.end_date == date(2026, 11, 15)
        billing.enable_plan(db, plan, date(2026, 11, 7))
        assert plan.end_date is None
        assert all(row.is_valid for row in db.scalars(select(BillOccurrence).where(BillOccurrence.plan_id == pid)))
        db.commit()
    store.clock.now = datetime(2026, 11, 15, 10)
    assert store.finish()['ended'] == 0


@pytest.mark.parametrize('kind,interval,first,today,expected', [
    ('month', 1, date(2026, 1, 31), date(2026, 11, 7), date(2026, 11, 30)),
    ('year', 1, date(2024, 2, 29), date(2027, 2, 1), date(2027, 2, 28)),
    ('month', 3, date(2026, 1, 15), date(2026, 11, 7), date(2027, 1, 15)),
    ('week', 2, date(2026, 11, 1), date(2026, 11, 7), date(2026, 11, 15)),
    ('day', 3, date(2026, 11, 1), date(2026, 11, 7), date(2026, 11, 7)),
])
def test_end_date_uses_original_cycle_including_today(kind, interval, first, today, expected):
    plan = BillPlan(cycle_type=kind, cycle_interval=interval, first_due_date=first)
    assert billing.next_end_date(plan, today) == expected


def test_edit_schedule_recomputes_ending_but_amount_and_group_do_not(store):
    pid = store.create(enabled=False)
    with store.db() as db:
        plan = db.get(BillPlan, pid)
        billing.update_plan(db, plan, {'amount': Decimal('30.00'), 'group_id': None}, date(2026, 11, 7))
        assert plan.end_date == date(2026, 11, 15)
        billing.update_plan(db, plan, {'first_due_date': date(2026, 11, 20)}, date(2026, 11, 7))
        assert plan.end_date == date(2026, 11, 20)
        billing.update_plan(db, plan, {'cycle_type': 'once'}, date(2026, 11, 7))
        assert plan.end_date == date(2026, 11, 20)
        billing.enable_plan(db, plan, date(2026, 11, 7))
        assert plan.end_date == date(2026, 11, 20)
        billing.update_plan(db, plan, {'cycle_type': 'month'}, date(2026, 11, 7))
        assert plan.end_date is None


def test_auto_ending_preserves_single_bill_and_notifications_and_is_idempotent(store):
    pid = store.create('once', date(2026, 11, 7))
    with store.db() as db:
        bill = db.scalar(select(BillOccurrence).where(BillOccurrence.plan_id == pid))
        bill_id = bill.id
        db.add(NotificationRecord(user_id=1, plan_id=pid, bill_id=bill_id, due_date=date(2026, 11, 7),
                                  channel='email', reminder_type='end_advance', status='sent',
                                  scheduled_at=datetime(2026, 11, 4, 9), attempt_count=1))
        db.commit()
    assert store.finish()['ended'] == 1
    assert store.finish()['ended'] == 0
    with store.db() as db:
        plan = db.get(BillPlan, pid)
        assert plan.end_date == date(2026, 11, 7)
        assert plan.deleted_at == plan.ended_at == store.clock.now
        assert db.get(BillOccurrence, bill_id).is_valid
        assert len(db.scalars(select(NotificationRecord)).all()) == 1
        with pytest.raises(AppError) as exc:
            _owned_plan(db, 1, pid)
        assert exc.value.code == 'BILL_PLAN_NOT_FOUND'
        result = calendar_month(db, db.get(User, 1), '2026-11')
        assert result['count'] == 1
        assert result['amount'] == '12.50'
        totals = statistics.summary(db, db.get(User, 1))
        assert totals['today'] == {'amount': '12.50', 'count': 1}
        assert totals['next_bill']['bill_id'] == bill_id
    assert store.notify()['sent'] == 1
    assert '单次账单' in store.sent[0][2] and '12.50' in store.sent[0][2]
    assert store.notify()['sent'] == 0


def test_disabled_recurring_retains_history_and_invalid_future_rows(store):
    pid = store.create(due=date(2026, 10, 15), enabled=False)
    with store.db() as db:
        before = [(r.id, r.due_date, r.is_valid) for r in db.scalars(select(BillOccurrence).order_by(BillOccurrence.id))]
    store.clock.now = datetime(2026, 11, 15, 10)
    assert store.finish()['ended'] == 1
    with store.db() as db:
        assert [(r.id, r.due_date, r.is_valid) for r in db.scalars(select(BillOccurrence).order_by(BillOccurrence.id))] == before
        assert db.get(BillPlan, pid).ended_at is not None
    assert store.notify()['sent'] == 1
    assert '不再续期' in store.sent[0][2] and '产生账单' not in store.sent[0][2]


def test_legacy_backfill_is_fixed_and_old_single_rules_end_without_deleting_bills(store):
    pid = store.create(enabled=False)
    old = store.create('once', date(2026, 10, 1))
    with store.db() as db:
        db.get(BillPlan, pid).end_date = None
        db.get(BillPlan, old).end_date = None
        db.commit()
    assert store.finish() == {'ended': 1, 'initialized': 1, 'errors': 0}
    store.clock.now = datetime(2026, 11, 20, 10)
    assert store.finish()['ended'] == 1
    with store.db() as db:
        assert db.get(BillPlan, pid).end_date == date(2026, 11, 15)
        assert db.scalar(select(BillOccurrence).where(BillOccurrence.plan_id == old)).is_valid
    assert store.notify()['sent'] == 0  # no late reminders for prior dates


def test_expiration_uses_user_timezone_and_ignores_notification_switches(store):
    pid = store.create('once', date(2026, 11, 8))
    store.clock.now = datetime(2026, 11, 7, 18)
    assert store.finish()['ended'] == 0
    with store.db() as db:
        db.get(User, 1).timezone = 'Asia/Singapore'
        setting = db.get(NotificationSetting, 1)
        setting.email_enabled = setting.same_day_enabled = setting.advance_enabled = False
        db.commit()
    assert store.finish()['ended'] == 1
    assert store.notify()['sent'] == 0
    with store.db() as db:
        assert db.get(BillPlan, pid).ended_at is not None


def test_manual_deletion_never_sends_ending_notifications(store):
    pid = store.create('once', date(2026, 11, 7))
    with store.db() as db:
        billing.delete_plan(db, db.get(BillPlan, pid), date(2026, 11, 7))
        db.commit()
        assert db.get(BillPlan, pid).ended_at is None
    assert store.finish()['ended'] == store.notify()['sent'] == 0


@pytest.mark.parametrize('kind,enabled', [('month', False), ('once', True)])
def test_end_reminders_follow_existing_days_times_and_send_once(store, kind, enabled):
    store.create(kind, date(2026, 11, 15), enabled=enabled)
    store.clock.now = datetime(2026, 11, 11, 10)
    assert store.notify()['sent'] == 0
    store.clock.now = datetime(2026, 11, 12, 8, 59)
    assert store.notify()['sent'] == 0
    store.clock.now = datetime(2026, 11, 12, 9)
    assert store.notify()['sent'] == 1
    assert store.notify()['sent'] == 0
    store.clock.now = datetime(2026, 11, 15, 0)
    assert store.finish()['ended'] == 1
    assert store.notify()['sent'] == 0
    store.clock.now = datetime(2026, 11, 15, 8, 30)
    assert store.notify()['sent'] == 1
    assert store.notify()['sent'] == 0
    with store.db() as db:
        assert list(db.scalars(select(NotificationRecord.reminder_type).order_by(NotificationRecord.id))) == ['end_advance', 'end_same_day']


def test_ending_retries_survive_deletion_and_cancel_after_reenable(store, monkeypatch):
    pid = store.create(due=date(2026, 11, 10), enabled=False)
    failures = []
    def fail(*args):
        failures.append(1)
        raise notifications.DeliveryError('NETWORK_ERROR', retryable=True)
    monkeypatch.setattr(notifications, '_send_email', fail)
    assert store.notify()['failed'] == 1
    with store.db() as db:
        billing.enable_plan(db, db.get(BillPlan, pid), date(2026, 11, 7))
        db.commit()
    store.clock.now += timedelta(seconds=60)
    store.notify()
    assert len(failures) == 2  # active rule's distinct ordinary bill reminder
    with store.db() as db:
        record = db.scalar(select(NotificationRecord).where(NotificationRecord.reminder_type == 'end_advance'))
        assert record.attempt_count == 1
    single = store.create('once', date(2026, 11, 7))
    assert store.finish()['ended'] == 1
    store.notify()
    with store.db() as db:
        record = db.scalar(select(NotificationRecord).where(NotificationRecord.plan_id == single))
        assert record.status == 'retry_wait'
        record_id = record.id
    store.clock.now += timedelta(seconds=60)
    monkeypatch.setattr(notifications, '_send_email', lambda *args: store.sent.append(args[3]))
    assert store.notify()['sent'] >= 1
    with store.db() as db:
        record = db.get(NotificationRecord, record_id)
        assert record.attempt_count == 2 and record.status == 'sent'


def test_reenable_during_dns_cancels_end_notification(store, monkeypatch):
    pid = store.create(due=date(2026, 11, 10), enabled=False)
    def prepare(*args):
        with store.db() as db:
            billing.enable_plan(db, db.get(BillPlan, pid), date(2026, 11, 7))
            db.commit()
        return ('smtp.test', [])
    monkeypatch.setattr(notifications, '_prepare_delivery', prepare)
    assert store.notify()['sent'] == 0
    with store.db() as db:
        assert db.scalar(select(NotificationRecord)) is None


def test_zero_day_advance_merges_with_same_day_and_old_once_send_is_not_repeated(store):
    pid = store.create('once', date(2026, 11, 7))
    with store.db() as db:
        db.get(NotificationSetting, 1).advance_days = 0
        db.commit()
    assert store.notify()['sent'] == 1
    with store.db() as db:
        assert db.scalar(select(NotificationRecord)).reminder_type == 'end_same_day'
        db.scalar(select(NotificationRecord)).reminder_type = 'same_day'
        db.commit()
    assert store.finish()['ended'] == 1
    assert store.notify()['sent'] == 0
    assert len(store.sent) == 1


def test_ending_records_remain_available_through_api(store):
    store.create('once', date(2026, 11, 7))
    store.finish()
    store.notify()
    app = FastAPI()
    app.include_router(notification_records.router)
    def session():
        with store.db() as db:
            yield db
    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, timezone='UTC')
    with TestClient(app) as client:
        response = client.get('/api/v1/me/notification-records')
        assert response.status_code == 200
        assert response.json()['items'][0]['reminder_type'] == 'end_same_day'


def test_completed_once_bill_can_be_invalidated_and_restored_on_due_date(store):
    pid = store.create('once', date(2026, 11, 7))
    assert store.finish()['ended'] == 1
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=store.settings)),
                              state=SimpleNamespace(request_id='restore-once'))
    with store.db() as db:
        bill = db.scalar(select(BillOccurrence).where(BillOccurrence.plan_id == pid))
        user = db.get(User, 1)
        invalid = bills.set_validity(bill.id, ValidityPatch(is_valid=False), request, user, db)
        assert BillOccurrenceResponse.model_validate(invalid).can_restore
        assert statistics.summary(db, user)['today']['count'] == 0
        restored = bills.set_validity(bill.id, ValidityPatch(is_valid=True), request, user, db)
        assert restored['is_valid'] and restored['can_restore']
        assert restored['plan_status'] == 'deleted'
        assert statistics.summary(db, user)['today']['count'] == 1
    assert store.finish()['ended'] == 0


@pytest.mark.parametrize('kind,finish', [('once', False), ('month', False), ('month', True)])
def test_disabled_current_bills_still_cannot_be_restored(store, kind, finish):
    pid = store.create(kind, date(2026, 11, 7), enabled=False)
    if finish:
        assert store.finish()['ended'] == 1
    with store.db() as db:
        bill = db.scalar(select(BillOccurrence).where(
            BillOccurrence.plan_id == pid, BillOccurrence.due_date == date(2026, 11, 7)))
        user = db.get(User, 1)
        response = bills.get_bill(bill.id, user, db)
        assert not response['can_restore']
        with pytest.raises(AppError) as exc:
            bills.set_validity(bill.id, ValidityPatch(is_valid=True), None, user, db)
        assert exc.value.code == 'BILL_PLAN_DISABLED'


@pytest.mark.parametrize('reminder_type', ['advance', 'same_day'])
@pytest.mark.parametrize('status,attempts', [
    ('failed', 3), ('failed', 1), ('sent', 1), ('unknown', 1), ('sending', 1),
])
def test_legacy_once_terminal_records_are_not_retried(store, reminder_type, status, attempts):
    due = date(2026, 11, 10) if reminder_type == 'advance' else date(2026, 11, 7)
    pid = store.create('once', due)
    with store.db() as db:
        record = NotificationRecord(user_id=1, plan_id=pid, due_date=due, channel='email',
                                    reminder_type=reminder_type, status=status,
                                    scheduled_at=datetime(2026, 11, 7, 9), attempt_count=attempts)
        db.add(record)
        db.commit()
        record_id = record.id
    assert store.notify() == {'sent': 0, 'failed': 0, 'unknown': 0, 'errors': 0}
    with store.db() as db:
        records = db.scalars(select(NotificationRecord)).all()
        assert [(r.id, r.status, r.attempt_count, r.reminder_type) for r in records] == [
            (record_id, status, attempts, reminder_type)]
    assert not store.sent


@pytest.mark.parametrize('reminder_type', ['advance', 'same_day'])
@pytest.mark.parametrize('attempts', [1, 2])
def test_legacy_once_retry_keeps_record_budget_and_backoff(store, monkeypatch, reminder_type, attempts):
    due = date(2026, 11, 10) if reminder_type == 'advance' else date(2026, 11, 7)
    pid = store.create('once', due)
    retry_at = datetime(2026, 11, 7, 10, 5)
    scheduled_at = datetime(2026, 11, 7, 9 if reminder_type == 'advance' else 8, 30)
    with store.db() as db:
        record = NotificationRecord(user_id=1, plan_id=pid, due_date=due, channel='email',
                                    reminder_type=reminder_type, status='retry_wait',
                                    scheduled_at=scheduled_at, attempt_count=attempts,
                                    retry_count=attempts, next_retry_at=retry_at,
                                    last_attempt_at=store.clock.now, error_code='NETWORK_ERROR')
        db.add(record)
        db.commit()
        record_id = record.id
    assert store.notify()['sent'] == 0
    assert not store.sent
    with store.db() as db:
        assert len(db.scalars(select(NotificationRecord)).all()) == 1
        assert db.get(NotificationRecord, record_id).next_retry_at == retry_at

    def fail(*args):
        raise notifications.DeliveryError('NETWORK_ERROR', retryable=True)
    monkeypatch.setattr(notifications, '_send_email', fail)
    store.clock.now = retry_at
    assert store.notify()['failed'] == 1
    with store.db() as db:
        record = db.get(NotificationRecord, record_id)
        assert len(db.scalars(select(NotificationRecord)).all()) == 1
        assert record.reminder_type == 'end_' + reminder_type
        assert record.attempt_count == record.retry_count == attempts + 1
        assert record.scheduled_at == scheduled_at
        assert record.next_retry_at == (retry_at + timedelta(minutes=5) if attempts == 1 else None)
        assert record.status == ('retry_wait' if attempts == 1 else 'failed')
    store.clock.now += timedelta(minutes=5)
    assert store.notify()['failed'] == (1 if attempts == 1 else 0)
    store.clock.now += timedelta(minutes=5)
    assert store.notify()['failed'] == 0
    with store.db() as db:
        assert db.get(NotificationRecord, record_id).attempt_count == 3


def test_reenabled_end_reminder_displays_cancelled_and_leaves_retry_filter(store, monkeypatch):
    pid = store.create(due=date(2026, 11, 10), enabled=False)
    def fail(*args):
        raise notifications.DeliveryError('NETWORK_ERROR', retryable=True)
    monkeypatch.setattr(notifications, '_send_email', fail)
    assert store.notify()['failed'] == 1
    with store.db() as db:
        billing.enable_plan(db, db.get(BillPlan, pid), store.clock.now.date())
        db.commit()
    store.clock.now += timedelta(minutes=10)
    monkeypatch.setattr(notifications, '_send_email', lambda *args: store.sent.append(args[3]))
    assert store.notify()['sent'] == 1  # Only the ordinary bill reminder.
    with store.db() as db:
        user = db.get(User, 1)
        response = notification_records.list_records(status='cancelled', page=1, page_size=20,
                                                     user=user, db=db)
        parsed = NotificationRecordPage.model_validate(response)
        assert parsed.total == 1
        assert parsed.items[0].reminder_type == 'end_advance'
        assert parsed.items[0].status == 'cancelled'
        assert parsed.items[0].next_retry_at is None
        assert parsed.items[0].attempt_count == 1
        assert notification_records.list_records(status='retry_wait', page=1, page_size=20,
                                                 user=user, db=db)['total'] == 0


@pytest.mark.parametrize('kind,enabled,reminder_type,status,expected', [
    ('month', True, 'end_same_day', 'pending', 'cancelled'),
    ('month', True, 'end_advance', 'sent', 'sent'),
    ('month', True, 'end_advance', 'failed', 'failed'),
    ('month', True, 'advance', 'retry_wait', 'retry_wait'),
    ('month', False, 'end_advance', 'retry_wait', 'retry_wait'),
    ('once', True, 'end_advance', 'retry_wait', 'retry_wait'),
])
def test_cancelled_record_status_only_applies_to_pending_recurring_endings(
        store, kind, enabled, reminder_type, status, expected):
    pid = store.create(kind, date(2026, 11, 10), enabled=enabled)
    with store.db() as db:
        db.add(NotificationRecord(user_id=1, plan_id=pid, due_date=date(2026, 11, 10),
                                  channel='email', reminder_type=reminder_type, status=status,
                                  scheduled_at=store.clock.now, attempt_count=1,
                                  next_retry_at=store.clock.now + timedelta(minutes=1)))
        db.commit()
        response = notification_records.list_records(status=expected, page=1, page_size=20,
                                                     user=db.get(User, 1), db=db)
        assert response['total'] == 1
        assert response['items'][0]['status'] == expected
        assert (response['items'][0]['next_retry_at'] is not None) == (expected == 'retry_wait')
