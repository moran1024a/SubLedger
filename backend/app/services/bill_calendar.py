"""Read-only calendar: recorded bills take precedence over rule projections."""

from calendar import monthrange
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillOccurrence, BillPlan, User
from app.services.billing import iter_plan_dates, local_today
from app.services.cycles import plan_cycle
from app.services.statistics import money


def calendar_month(db: Session, user: User, month: str | None = None) -> dict:
    today = local_today(user.timezone)
    start = date.fromisoformat(f"{month}-01") if month else today.replace(day=1)
    end = start.replace(day=monthrange(start.year, start.month)[1])
    rows = db.execute(
        select(BillOccurrence, BillPlan)
        .join(BillPlan)
        .where(
            BillOccurrence.user_id == user.id,
            BillPlan.user_id == user.id,
            BillOccurrence.due_date >= start,
            BillOccurrence.due_date <= end,
        )
    ).all()
    # Invalid rows must also suppress inference for their original dates.
    recorded = {(bill.plan_id, bill.due_date) for bill, _ in rows}
    by_date: dict[date, list[dict]] = {}

    def add(plan: BillPlan, due: date, bill: BillOccurrence | None = None):
        kind, interval = plan_cycle(plan)
        by_date.setdefault(due, []).append({
            "bill_id": bill.id if bill else None,
            "plan_id": plan.id,
            "plan_name": plan.name,
            "amount": money(Decimal(bill.amount_snapshot if bill else plan.amount)),
            "cycle_type": kind,
            "cycle_interval": interval,
            "plan_status": "deleted" if plan.deleted_at else (
                "enabled" if plan.is_enabled else "disabled"
            ),
            "is_estimated": bill is None,
        })

    for bill, plan in rows:
        if bill.is_valid:
            add(plan, bill.due_date, bill)

    if end >= today:
        plans = db.scalars(select(BillPlan).where(
            BillPlan.user_id == user.id,
            BillPlan.deleted_at.is_(None),
            BillPlan.is_enabled.is_(True),
            BillPlan.cycle_type != "once",
        ))
        for plan in plans:
            for due in iter_plan_dates(plan, max(start, today), end):
                if (plan.id, due) not in recorded:
                    add(plan, due)

    days = []
    total = Decimal("0")
    count = estimated_count = 0
    for due, bills in sorted(by_date.items()):
        bills.sort(key=lambda item: (item["plan_name"].casefold(), item["plan_id"]))
        amount = sum((Decimal(bill["amount"]) for bill in bills), Decimal("0"))
        estimates = sum(bill["is_estimated"] for bill in bills)
        days.append({
            "date": due, "count": len(bills), "amount": money(amount),
            "estimated_count": estimates, "bills": bills,
        })
        total += amount
        count += len(bills)
        estimated_count += estimates
    return {
        "month": start.strftime("%Y-%m"), "today": today,
        "count": count, "amount": money(total), "estimated_count": estimated_count,
        "days": days,
    }
