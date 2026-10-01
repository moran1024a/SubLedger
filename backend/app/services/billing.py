from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import BillOccurrence, BillPlan, NotificationRecord, User
from app.services.users import utc_now
from app.services.cycles import normalize_cycle, plan_cycle, cycle_step

def local_today(timezone_name: str) -> date:
    return utc_now().replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(timezone_name)).date()


def cycle_date(first_due_date: date, cycle_type: str, index: int, cycle_days: int | None = None, cycle_interval: int = 1) -> date:
    if index < 0:
        raise ValueError("index must not be negative")
    kind, interval = normalize_cycle(cycle_type, cycle_days, cycle_interval)
    if kind == "once":
        if index != 0:
            raise ValueError("once cycle has only one date")
        return first_due_date
    days, months = cycle_step(kind, interval)
    if days:
        delta = days * index
        if delta > (date.max - first_due_date).days:
            raise OverflowError("cycle date exceeds the supported date range")
        return first_due_date + timedelta(days=delta)
    month_number = first_due_date.year * 12 + first_due_date.month - 1 + months * index
    year, month_index = divmod(month_number, 12)
    if year > date.max.year:
        raise OverflowError("cycle date exceeds the supported date range")
    month = month_index + 1
    return date(year, month, min(first_due_date.day, calendar.monthrange(year, month)[1]))


def iter_plan_dates(plan: BillPlan, start: date, end: date):
    if end < start or end < plan.first_due_date:
        return
    try:
        kind, interval = plan_cycle(plan)
    except ValueError:
        return
    if kind == "once":
        if start <= plan.first_due_date <= end:
            yield plan.first_due_date
        return
    days, months = cycle_step(kind, interval)
    if days:
        index = max(0, ((start - plan.first_due_date).days + days - 1) // days)
    else:
        delta = (start.year - plan.first_due_date.year) * 12 + start.month - plan.first_due_date.month
        index = max(0, delta // months)
    while True:
        try:
            current = cycle_date(plan.first_due_date, kind, index, cycle_interval=interval)
        except (OverflowError, ValueError):
            return
        if current > end:
            return
        if current >= start:
            yield current
        index += 1


def _add_occurrence(db: Session, plan: BillPlan, due_date: date) -> BillOccurrence:
    now = utc_now()
    occurrence = BillOccurrence(user_id=plan.user_id, plan_id=plan.id, due_date=due_date, amount_snapshot=plan.amount, is_valid=True, created_at=now, updated_at=now)
    db.add(occurrence)
    return occurrence


def _lock_plan(db: Session, plan: BillPlan) -> BillPlan:
    # Child inserts acquire a shared User FK lock. Acquire it before Plan,
    # consistently with notifications and account enable/disable operations.
    db.execute(select(User.id).where(User.id == plan.user_id).with_for_update(read=True)).first()
    db.flush()
    locked = db.scalar(
        select(BillPlan)
        .where(BillPlan.id == plan.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return locked or plan


def _require_live_plan(plan: BillPlan) -> None:
    if plan.deleted_at is not None:
        raise AppError("BILL_PLAN_NOT_FOUND", "账单规则不存在", 404)


def _future_plan_dates(plan: BillPlan, today: date):
    yield from iter_plan_dates(plan, today, date.max)


def ensure_plan_occurrences(db: Session, plan: BillPlan, today: date) -> list[BillOccurrence]:
    plan = _lock_plan(db, plan)
    if plan.deleted_at is not None or not plan.is_enabled:
        return []
    existing = {
        item.due_date: item
        for item in db.scalars(
            select(BillOccurrence)
            .where(BillOccurrence.plan_id == plan.id, BillOccurrence.due_date == plan.first_due_date if plan.cycle_type == "once" else BillOccurrence.due_date >= today)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    created: list[BillOccurrence] = []
    if plan.cycle_type == "once":
        if plan.first_due_date not in existing:
            created.append(_add_occurrence(db, plan, plan.first_due_date))
        return created
    needed = max(0, 2 - sum(due_date >= today for due_date in existing))
    for due_date in _future_plan_dates(plan, today):
        if needed == 0:
            break
        if due_date not in existing:
            created.append(_add_occurrence(db, plan, due_date))
            existing[due_date] = created[-1]
            needed -= 1
    return created


def create_plan(db: Session, user: User, data, today: date) -> BillPlan:
    db.execute(select(User.id).where(User.id == user.id).with_for_update(read=True)).first()
    now = utc_now()
    kind, interval = normalize_cycle(data.cycle_type, data.cycle_days, data.cycle_interval, validate=True)
    plan = BillPlan(user_id=user.id, name=data.name, amount=data.amount, first_due_date=data.first_due_date, cycle_type=kind, cycle_interval=interval, cycle_days=None, is_enabled=True, note=data.note, created_at=now, updated_at=now)
    db.add(plan)
    db.flush()
    if plan.cycle_type != "once" and plan.first_due_date < today:
        for due_date in iter_plan_dates(plan, date(today.year, 1, 1), today - timedelta(days=1)):
            _add_occurrence(db, plan, due_date)
    ensure_plan_occurrences(db, plan, today)
    return plan


def update_plan(db: Session, plan: BillPlan, values: dict, today: date) -> bool:
    plan = _lock_plan(db, plan)
    _require_live_plan(plan)
    values = values.copy()
    next_cycle = values.get("cycle_type", plan.cycle_type)
    next_days = values.get("cycle_days", plan.cycle_days if next_cycle == "custom_days" else None)
    interval = values.get("cycle_interval", (getattr(plan, "cycle_interval", None) or 1) if next_cycle == plan.cycle_type else 1)
    # Legacy PATCH {cycle_days: N} remains usable for a migrated daily rule.
    if "cycle_days" in values and values["cycle_days"] is not None and "cycle_type" not in values and next_cycle == "day":
        interval, next_days = values["cycle_days"], None
    try:
        if next_days is not None and next_cycle != "custom_days":
            raise ValueError("cycle_days only belongs to legacy custom_days")
        kind, interval = normalize_cycle(next_cycle, next_days, interval, validate=True)
        old_cycle = plan_cycle(plan)
    except ValueError as exc:
        raise AppError("BILL_INVALID_CYCLE", "周期单位或间隔无效，请检查支持的范围", 400) from exc
    schedule_changed = old_cycle != (kind, interval) or values.get("first_due_date", plan.first_due_date) != plan.first_due_date
    values.update(cycle_type=kind, cycle_interval=interval, cycle_days=None)
    amount_changed = "amount" in values and values["amount"] != plan.amount
    for key, value in values.items():
        setattr(plan, key, value)
    plan.updated_at = utc_now()
    if schedule_changed:
        db.execute(
            delete(NotificationRecord).where(
                NotificationRecord.plan_id == plan.id,
                NotificationRecord.due_date >= today,
            )
        )
        db.execute(
            delete(BillOccurrence).where(
                BillOccurrence.plan_id == plan.id,
                BillOccurrence.due_date >= today,
            )
        )
        db.flush()
        if plan.is_enabled:
            ensure_plan_occurrences(db, plan, today)
    elif amount_changed:
        now = utc_now()
        for occurrence in db.scalars(
            select(BillOccurrence)
            .where(BillOccurrence.plan_id == plan.id, BillOccurrence.due_date >= today)
            .with_for_update()
            .execution_options(populate_existing=True)
        ):
            occurrence.amount_snapshot = plan.amount
            occurrence.updated_at = now
    return schedule_changed


def disable_plan(db: Session, plan: BillPlan, today: date) -> None:
    plan = _lock_plan(db, plan)
    _require_live_plan(plan)
    was_enabled = plan.is_enabled
    plan.is_enabled = False
    plan.updated_at = utc_now()
    if not was_enabled:
        return
    now = utc_now()
    for occurrence in db.scalars(
        select(BillOccurrence)
        .where(
            BillOccurrence.plan_id == plan.id,
            BillOccurrence.due_date >= today,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ):
        occurrence.invalidated_by_plan_disable = occurrence.is_valid
        occurrence.is_valid = False
        occurrence.updated_at = now


def enable_plan(db: Session, plan: BillPlan, today: date) -> None:
    plan = _lock_plan(db, plan)
    _require_live_plan(plan)
    was_enabled = plan.is_enabled
    plan.is_enabled = True
    plan.updated_at = utc_now()
    if not was_enabled:
        now = utc_now()
        for occurrence in db.scalars(
            select(BillOccurrence)
            .where(
                BillOccurrence.plan_id == plan.id,
                BillOccurrence.due_date >= today,
                BillOccurrence.invalidated_by_plan_disable.is_(True),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ):
            occurrence.is_valid = True
            occurrence.invalidated_by_plan_disable = False
            occurrence.updated_at = now
    ensure_plan_occurrences(db, plan, today)


def delete_plan(db: Session, plan: BillPlan, today: date) -> None:
    plan = _lock_plan(db, plan)
    _require_live_plan(plan)
    future_bill_ids = select(BillOccurrence.id).where(
        BillOccurrence.plan_id == plan.id,
        BillOccurrence.due_date >= today,
    )
    db.execute(
        delete(NotificationRecord).where(
            NotificationRecord.plan_id == plan.id,
            or_(
                NotificationRecord.due_date >= today,
                NotificationRecord.bill_id.in_(future_bill_ids),
            ),
        )
    )
    db.execute(
        delete(BillOccurrence).where(
            BillOccurrence.plan_id == plan.id,
            BillOccurrence.due_date >= today,
        )
    )
    now = utc_now()
    plan.is_enabled = False
    plan.deleted_at = now
    plan.updated_at = now
    db.flush()


def complete_all_active_plans(database) -> None:
    with database.session() as db:
        users = db.scalars(select(User).where(User.is_active.is_(True))).all()
        for user in users:
            today = local_today(user.timezone)
            plans = db.scalars(select(BillPlan).where(BillPlan.user_id == user.id, BillPlan.is_enabled.is_(True), BillPlan.deleted_at.is_(None), BillPlan.cycle_type != "once")).all()
            for plan in plans:
                ensure_plan_occurrences(db, plan, today)
            db.commit()


def plan_response(plan: BillPlan) -> dict:
    return {"id": plan.id, "name": plan.name, "amount": f"{Decimal(plan.amount):.2f}", "first_due_date": plan.first_due_date, "cycle_type": plan_cycle(plan)[0], "cycle_interval": plan_cycle(plan)[1], "cycle_days": None, "is_enabled": plan.is_enabled, "note": plan.note, "created_at": plan.created_at, "updated_at": plan.updated_at}


def occurrence_response(occurrence: BillOccurrence, plan: BillPlan, today: date) -> dict:
    return {"id": occurrence.id, "plan_id": occurrence.plan_id, "plan_name": plan.name, "due_date": occurrence.due_date, "amount": f"{Decimal(occurrence.amount_snapshot):.2f}", "is_valid": occurrence.is_valid, "time_status": "upcoming" if occurrence.due_date >= today else "passed", "cycle_type": plan_cycle(plan)[0], "cycle_interval": plan_cycle(plan)[1], "cycle_days": None, "plan_status": "deleted" if getattr(plan, "deleted_at", None) else "enabled" if plan.is_enabled else "disabled"}
