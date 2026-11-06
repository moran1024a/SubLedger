from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.errors import AppError
from app.models import BillPlanGroup, User
from app.schemas import (BillPlanGroupResponse, PlanGroupWrite, PlanLayoutResponse,
                         PlanLayoutVersion, PlanLayoutWrite)
from app.services.plan_groups import edit_group, layout_snapshot, lock_layout_user, save_layout
from app.services.logging import write_user_log

router = APIRouter(prefix="/api/v1", tags=["plan groups"])


@router.get("/plans/layout", response_model=PlanLayoutResponse)
def get_layout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lock_layout_user(db, user.id, shared=True)
    return layout_snapshot(db, user.id)


@router.get("/plan-groups", response_model=list[BillPlanGroupResponse])
def list_groups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lock_layout_user(db, user.id, shared=True)
    return list(db.scalars(select(BillPlanGroup).where(BillPlanGroup.user_id == user.id)
                           .order_by(BillPlanGroup.sort_order, BillPlanGroup.id)
                           .with_for_update(read=True)))


def commit_change(db, request, user_id, event, operation):
    try:
        result = operation()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("BILL_GROUP_NAME_CONFLICT", "分组名称已存在", 409) from exc
    write_user_log(request.app.state.settings, user_id=user_id, level="INFO", module="billing",
                   event=event, request_id=request.state.request_id, message="规则分组或排序已更新")
    return result


@router.put("/plans/layout", response_model=PlanLayoutResponse)
def put_layout(payload: PlanLayoutWrite, request: Request,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return commit_change(db, request, user.id, "plan_layout_updated", lambda: save_layout(db, user.id, payload))


@router.post("/plan-groups", response_model=PlanLayoutResponse, status_code=201)
def add_group(payload: PlanGroupWrite, request: Request,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return commit_change(db, request, user.id, "plan_group_created",
                         lambda: edit_group(db, user.id, payload.version, name=payload.name))


@router.patch("/plan-groups/{group_id}", response_model=PlanLayoutResponse)
def rename_group(group_id: int, payload: PlanGroupWrite, request: Request,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return commit_change(db, request, user.id, "plan_group_renamed",
                         lambda: edit_group(db, user.id, payload.version, group_id=group_id, name=payload.name))


@router.delete("/plan-groups/{group_id}", response_model=PlanLayoutResponse)
def remove_group(group_id: int, payload: PlanLayoutVersion, request: Request,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return commit_change(db, request, user.id, "plan_group_deleted",
                         lambda: edit_group(db, user.id, payload.version, group_id=group_id, remove=True))
