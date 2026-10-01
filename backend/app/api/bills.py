from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.errors import AppError
from app.models import BillOccurrence, BillPlan, User
from app.schemas import BillOccurrencePage, BillOccurrenceResponse, ValidityPatch
from app.services.billing import local_today, occurrence_response
from app.services.logging import write_user_log
from app.services.users import utc_now

router = APIRouter(prefix="/api/v1/bills", tags=["bills"])


def _owned_bill(db: Session, user_id: int, bill_id: int) -> tuple[BillOccurrence, BillPlan]:
    row = db.execute(select(BillOccurrence, BillPlan).join(BillPlan).where(BillOccurrence.id == bill_id, BillOccurrence.user_id == user_id)).first()
    if row is None:
        raise AppError("BILL_OCCURRENCE_NOT_FOUND", "账单实例不存在", 404)
    return row[0], row[1]


def _locked_owned_bill(db: Session, user_id: int, bill_id: int) -> tuple[BillOccurrence, BillPlan]:
    db.execute(select(User.id).where(User.id == user_id).with_for_update(read=True)).first()
    plan_id = db.scalar(
        select(BillOccurrence.plan_id).where(
            BillOccurrence.id == bill_id,
            BillOccurrence.user_id == user_id,
        )
    )
    if plan_id is None:
        raise AppError("BILL_OCCURRENCE_NOT_FOUND", "账单实例不存在", 404)
    plan = db.scalar(
        select(BillPlan)
        .where(BillPlan.id == plan_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    occurrence = db.scalar(
        select(BillOccurrence)
        .where(
            BillOccurrence.id == bill_id,
            BillOccurrence.user_id == user_id,
            BillOccurrence.plan_id == plan_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if plan is None or occurrence is None:
        raise AppError("BILL_OCCURRENCE_NOT_FOUND", "账单实例不存在", 404)
    return occurrence, plan


@router.get("", response_model=BillOccurrencePage)
def list_bills(
    q: str | None = Query(default=None, max_length=128),
    sort: str = Query(default="asc", pattern="^(asc|desc)$"),
    start_date: date | None = None,
    end_date: date | None = None,
    time_status: str | None = Query(default=None, pattern="^(upcoming|passed)$"),
    is_valid: bool | None = None,
    plan_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if start_date is not None and end_date is not None and start_date > end_date:
        raise AppError("INVALID_DATE_RANGE", "开始日期不能晚于结束日期", 400)
    today = local_today(user.timezone)
    filters = [BillOccurrence.user_id == user.id]
    if start_date is not None:
        filters.append(BillOccurrence.due_date >= start_date)
    if end_date is not None:
        filters.append(BillOccurrence.due_date <= end_date)
    if time_status == "upcoming":
        filters.append(BillOccurrence.due_date >= today)
    elif time_status == "passed":
        filters.append(BillOccurrence.due_date < today)
    if is_valid is not None:
        filters.append(BillOccurrence.is_valid == is_valid)
    if plan_id is not None:
        filters.append(BillOccurrence.plan_id == plan_id)
    if q and q.strip():
        filters.append(BillPlan.name.icontains(q.strip(), autoescape=True))
    count_query = select(func.count(BillOccurrence.id))
    if q and q.strip():
        count_query = count_query.join(BillPlan)
    total = db.scalar(count_query.where(*filters)) or 0
    ordering = (
        (BillOccurrence.due_date.desc(), BillOccurrence.id.desc())
        if sort == "desc"
        else (BillOccurrence.due_date.asc(), BillOccurrence.id.asc())
    )
    query = (
        select(BillOccurrence, BillPlan)
        .join(BillPlan)
        .where(*filters)
        .order_by(*ordering)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = db.execute(query).all()
    return {
        "items": [occurrence_response(occurrence, plan, today) for occurrence, plan in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/{bill_id}", response_model=BillOccurrenceResponse)
def get_bill(bill_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    occurrence, plan = _owned_bill(db, user.id, bill_id)
    return occurrence_response(occurrence, plan, local_today(user.timezone))


@router.patch("/{bill_id}/validity", response_model=BillOccurrenceResponse)
def set_validity(bill_id: int, payload: ValidityPatch, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    occurrence, plan = _locked_owned_bill(db, user.id, bill_id)
    if (
        payload.is_valid
        and not plan.is_enabled
        and occurrence.due_date >= local_today(user.timezone)
    ):
        raise AppError(
            "BILL_PLAN_DISABLED",
            "停用规则的当前及未来账单不能恢复有效",
            400,
        )
    occurrence.is_valid = payload.is_valid
    occurrence.invalidated_by_plan_disable = False
    occurrence.updated_at = utc_now()
    db.commit()
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="billing", event="bill_validity_updated", request_id=request.state.request_id, message="账单有效性已修改", data={"bill_id": occurrence.id, "is_valid": occurrence.is_valid})
    return occurrence_response(occurrence, plan, local_today(user.timezone))
