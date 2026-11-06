"""End rules without deleting their bills or interrupting end-date notifications."""
from datetime import timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select

from app.models import BillPlan, User
from app.services.billing import next_end_date
from app.services.logging import write_system_log, write_user_log
from app.services.users import lock_user, utc_now


def finish_plan(db, user_id, plan_id):
    # Structural changes share the exclusive User lock with layout writes.
    user = lock_user(db, user_id)
    if user is None:
        return None
    plan = db.scalar(select(BillPlan).where(
        BillPlan.id == plan_id, BillPlan.user_id == user_id,
    ).with_for_update().execution_options(populate_existing=True))
    if plan is None or plan.deleted_at is not None or (plan.is_enabled and plan.cycle_type != "once"):
        return None
    now = utc_now()
    today = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(user.timezone)).date()
    initialized = plan.end_date is None
    if initialized:
        plan.end_date = next_end_date(plan, today)
    if plan.end_date is not None and plan.end_date <= today:
        plan.is_enabled = False
        plan.ended_at = plan.deleted_at = plan.updated_at = now
        return "ended"
    return "initialized" if initialized and plan.end_date is not None else None


def finish_ended_plans(database, settings):
    counts = {"ended": 0, "initialized": 0, "errors": 0}
    with database.session() as db:
        users = db.execute(select(User.id, User.timezone).order_by(User.id)).all()
    for user_id, timezone_name in users:
        try:
            today = utc_now().replace(tzinfo=timezone.utc).astimezone(ZoneInfo(timezone_name)).date()
            with database.session() as db:
                ids = db.scalars(select(BillPlan.id).where(
                    BillPlan.user_id == user_id, BillPlan.deleted_at.is_(None),
                    or_(BillPlan.is_enabled.is_(False), BillPlan.cycle_type == "once"),
                    or_(BillPlan.end_date.is_(None), BillPlan.end_date <= today),
                ).order_by(BillPlan.id)).all()
            for plan_id in ids:
                try:
                    with database.session() as db:
                        outcome = finish_plan(db, user_id, plan_id)
                        db.commit()
                        if outcome:
                            counts[outcome] += 1
                        if outcome == "ended":
                            plan = db.get(BillPlan, plan_id)
                            write_user_log(settings, user_id=user_id, level="INFO", module="billing",
                                           event="plan_auto_deleted", request_id=None,
                                           message="账单规则周期结束，已自动移除，账单记录保留",
                                           data={"plan_id": plan_id, "end_date": plan.end_date.isoformat()})
                except Exception as exc:
                    counts["errors"] += 1
                    _log_failure(settings, user_id, plan_id, exc)
        except Exception as exc:
            counts["errors"] += 1
            _log_failure(settings, user_id, None, exc)
    return counts


def _log_failure(settings, user_id, plan_id, exc):
    try:
        write_system_log(settings, level="ERROR", module="billing", event="plan_expiration_failed",
                         request_id=None, message="账单规则周期结束处理失败",
                         data={"user_id": user_id, "plan_id": plan_id, "error_type": type(exc).__name__})
    except Exception:
        pass
