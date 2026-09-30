from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.errors import AppError
from app.models import BillPlan, User
from app.schemas import BillPlanCreate, BillPlanPatch, BillPlanResponse
from app.services.billing import create_plan, delete_plan, disable_plan, enable_plan, local_today, plan_response, update_plan
from app.services.logging import write_user_log

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])


def _owned_plan(db: Session, user_id: int, plan_id: int) -> BillPlan:
    plan = db.scalar(select(BillPlan).where(BillPlan.id == plan_id, BillPlan.user_id == user_id, BillPlan.deleted_at.is_(None)))
    if plan is None:
        raise AppError("BILL_PLAN_NOT_FOUND", "账单规则不存在", 404)
    return plan


@router.post("", response_model=BillPlanResponse, status_code=status.HTTP_201_CREATED)
def add_plan(payload: BillPlanCreate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = create_plan(db, user, payload, local_today(user.timezone))
    db.commit()
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="billing", event="plan_created", request_id=request.state.request_id, message="账单规则已创建", data={"plan_id": plan.id})
    return plan_response(plan)


@router.get("", response_model=list[BillPlanResponse])
def list_plans(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [plan_response(plan) for plan in db.scalars(select(BillPlan).where(BillPlan.user_id == user.id, BillPlan.deleted_at.is_(None)).order_by(BillPlan.id.desc()))]


@router.get("/{plan_id}", response_model=BillPlanResponse)
def get_plan(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return plan_response(_owned_plan(db, user.id, plan_id))


@router.patch("/{plan_id}", response_model=BillPlanResponse)
def patch_plan(plan_id: int, payload: BillPlanPatch, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _owned_plan(db, user.id, plan_id)
    values = payload.model_dump(exclude_unset=True)
    rebuilt = update_plan(db, plan, values, local_today(user.timezone))
    db.commit()
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="billing", event="plan_updated", request_id=request.state.request_id, message="账单规则已修改", data={"plan_id": plan.id, "fields": list(values), "future_bills_rebuilt": rebuilt})
    return {**plan_response(plan), "future_bills_rebuilt": rebuilt}


@router.delete("/{plan_id}", status_code=204)
def remove_plan(plan_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _owned_plan(db, user.id, plan_id)
    cutoff = local_today(user.timezone)
    delete_plan(db, plan, cutoff)
    db.commit()
    try:
        write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="billing", event="plan_deleted", request_id=request.state.request_id, message="账单规则已删除", data={"plan_id": plan.id, "cutoff_date": cutoff.isoformat()})
    except OSError:
        pass


@router.post("/{plan_id}/disable", status_code=204)
def disable(plan_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _owned_plan(db, user.id, plan_id)
    disable_plan(db, plan, local_today(user.timezone))
    db.commit()
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="billing", event="plan_disabled", request_id=request.state.request_id, message="账单规则已停用", data={"plan_id": plan.id})


@router.post("/{plan_id}/enable", response_model=BillPlanResponse)
def enable(plan_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _owned_plan(db, user.id, plan_id)
    enable_plan(db, plan, local_today(user.timezone))
    db.commit()
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="billing", event="plan_enabled", request_id=request.state.request_id, message="账单规则已启用", data={"plan_id": plan.id})
    return plan_response(plan)
