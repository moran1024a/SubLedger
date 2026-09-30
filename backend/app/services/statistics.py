from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillOccurrence, BillPlan, User
from app.services.billing import iter_plan_dates, local_today

TWOPLACES = Decimal("0.01")


def money(value: Decimal) -> str:
    return f"{value.quantize(TWOPLACES, rounding=ROUND_HALF_UP):.2f}"


def _range_totals(db: Session, user_id: int, start: date, end: date, infer_from: date) -> tuple[Decimal, int]:
    plans = list(db.scalars(select(BillPlan).where(BillPlan.user_id == user_id, BillPlan.deleted_at.is_(None))))
    rows = list(db.scalars(select(BillOccurrence).where(BillOccurrence.user_id == user_id, BillOccurrence.due_date >= start, BillOccurrence.due_date <= end)))
    total = Decimal("0")
    count = 0
    existing: set[tuple[int, date]] = set()
    for occurrence in rows:
        existing.add((occurrence.plan_id, occurrence.due_date))
        if occurrence.is_valid:
            total += Decimal(occurrence.amount_snapshot)
            count += 1
    inference_start = max(start, infer_from)
    for plan in plans:
        if not plan.is_enabled or plan.cycle_type == "once":
            continue
        for due_date in iter_plan_dates(plan, inference_start, end):
            if (plan.id, due_date) not in existing:
                total += Decimal(plan.amount)
                count += 1
    return total, count


def summary(db: Session, user: User) -> dict:
    today = local_today(user.timezone)
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    year_start = date(today.year, 1, 1)
    year_end = date(today.year, 12, 31)
    today_total, today_count = _range_totals(db, user.id, today, today, today)
    month_total, month_count = _range_totals(db, user.id, month_start, month_end, today)
    year_total, year_count = _range_totals(db, user.id, year_start, year_end, today)
    monthly_average = Decimal("0")
    daily_average = Decimal("0")
    plans = db.scalars(select(BillPlan).where(BillPlan.user_id == user.id, BillPlan.is_enabled.is_(True), BillPlan.deleted_at.is_(None), BillPlan.cycle_type != "once"))
    for plan in plans:
        amount = Decimal(plan.amount)
        if plan.cycle_type == "monthly":
            monthly_average += amount
            daily_average += amount * Decimal(12) / Decimal(365)
        elif plan.cycle_type == "quarterly":
            monthly_average += amount / Decimal(3)
            daily_average += amount * Decimal(4) / Decimal(365)
        elif plan.cycle_type == "yearly":
            monthly_average += amount / Decimal(12)
            daily_average += amount / Decimal(365)
        elif plan.cycle_type == "custom_days":
            days = Decimal(plan.cycle_days)
            monthly_average += amount * Decimal(365) / days / Decimal(12)
            daily_average += amount / days
    next_row = db.execute(
        select(BillOccurrence, BillPlan)
        .join(BillPlan)
        .where(
            BillOccurrence.user_id == user.id,
            BillPlan.user_id == user.id,
            BillPlan.deleted_at.is_(None),
            BillOccurrence.is_valid.is_(True),
            BillOccurrence.due_date >= today,
        )
        .order_by(BillOccurrence.due_date, BillOccurrence.id)
        .limit(1)
    ).first()
    next_bill = None
    if next_row is not None:
        occurrence, plan = next_row
        next_bill = {"bill_id": occurrence.id, "name": plan.name, "amount": money(Decimal(occurrence.amount_snapshot)), "due_date": occurrence.due_date, "days_remaining": (occurrence.due_date - today).days}
    return {"date": today, "today": {"amount": money(today_total), "count": today_count}, "current_month": {"amount": money(month_total), "count": month_count}, "averages": {"monthly": money(monthly_average), "daily": money(daily_average)}, "current_year": {"amount": money(year_total), "count": year_count}, "next_bill": next_bill}
