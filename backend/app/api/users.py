from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db, require_admin
from app.errors import AppError
from app.models import User
from app.schemas import AdminPasswordReset, AdminSummaryResponse, AdminUserCreate, AdminUserPatch, PasswordChange, UserProfilePatch, UserResponse, UserPage
from app.security import hash_password, verify_password
from app.services.logging import write_user_log
from app.services.users import create_user, lock_user, revoke_all_sessions, update_profile_fields

router = APIRouter(tags=["users"])


@router.patch("/api/v1/me/profile", response_model=UserResponse)
def update_profile(payload: UserProfilePatch, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    values = payload.model_dump(exclude_unset=True)
    user = lock_user(db, user.id)
    if user is None or not user.is_active:
        raise AppError("AUTH_INVALID_CREDENTIALS", "用户已停用", 401)
    update_profile_fields(db, user, values)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "username" not in values:
            raise
        raise AppError("USER_USERNAME_CONFLICT", "用户名已存在", 409) from exc
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="users", event="profile_updated", request_id=request.state.request_id, message="用户资料已修改", data={"fields": list(values)})
    return user


@router.put("/api/v1/me/password", status_code=204)
def change_password(payload: PasswordChange, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = lock_user(db, user.id)
    if user is None or not user.is_active or not verify_password(user.password_hash, payload.current_password):
        raise AppError("AUTH_INVALID_PASSWORD", "当前密码错误", 400)
    user.password_hash = hash_password(payload.new_password)
    revoke_all_sessions(db, user.id)
    db.commit()
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="users", event="password_changed", request_id=request.state.request_id, message="密码已修改")


@router.get("/api/v1/admin/summary", response_model=AdminSummaryResponse)
def admin_summary(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    total_users = db.scalar(select(func.count(User.id))) or 0
    active_users = db.scalar(
        select(func.count(User.id)).where(User.role == "user", User.is_active.is_(True))
    ) or 0
    inactive_users = db.scalar(
        select(func.count(User.id)).where(User.role == "user", User.is_active.is_(False))
    ) or 0
    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": inactive_users,
    }


@router.get("/api/v1/admin/users", response_model=UserPage)
def list_users(
    q: str | None = Query(default=None, max_length=64),
    is_active: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    filters = []
    if q and q.strip():
        filters.append(User.username.icontains(q.strip(), autoescape=True))
    if is_active is not None:
        filters.append(User.is_active == is_active)
    total = db.scalar(select(func.count(User.id)).where(*filters)) or 0
    items = db.scalars(
        select(User).where(*filters).order_by(User.id)
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.post("/api/v1/admin/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def add_user(payload: AdminUserCreate, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        created = create_user(db, payload.username, payload.password, payload.timezone, payload.currency_code)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("USER_USERNAME_CONFLICT", "用户名已存在", 409) from exc
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="users", event="user_created", request_id=request.state.request_id, message="普通用户已创建", data={"user_id": created.id})
    return created


@router.get("/api/v1/admin/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None:
        raise AppError("USER_NOT_FOUND", "用户不存在", 404)
    return target


@router.patch("/api/v1/admin/users/{user_id}", response_model=UserResponse)
def patch_user(user_id: int, payload: AdminUserPatch, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = lock_user(db, user_id)
    if target is None or target.id == 0:
        raise AppError("USER_NOT_FOUND", "普通用户不存在", 404)
    values = payload.model_dump(exclude_unset=True, exclude={"revoke_sessions"})
    update_profile_fields(db, target, values)
    if payload.revoke_sessions:
        revoke_all_sessions(db, target.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "username" not in values:
            raise
        raise AppError("USER_USERNAME_CONFLICT", "用户名已存在", 409) from exc
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="users", event="user_updated", request_id=request.state.request_id, message="普通用户已修改", data={"target_user_id": target.id, "fields": list(values)})
    return target


@router.put("/api/v1/admin/users/{user_id}/password", status_code=204)
def reset_password(user_id: int, payload: AdminPasswordReset, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = lock_user(db, user_id)
    if target is None or target.id == 0:
        raise AppError("USER_NOT_FOUND", "普通用户不存在", 404)
    target.password_hash = hash_password(payload.password)
    revoke_all_sessions(db, target.id)
    db.commit()
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="users", event="user_password_reset", request_id=request.state.request_id, message="普通用户密码已重置", data={"target_user_id": target.id})


@router.post("/api/v1/admin/users/{user_id}/disable", status_code=204)
def disable_user(user_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = lock_user(db, user_id)
    if target is None or target.id == 0:
        raise AppError("USER_NOT_FOUND", "普通用户不存在", 404)
    target.is_active = False
    revoke_all_sessions(db, target.id)
    db.commit()
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="users", event="user_disabled", request_id=request.state.request_id, message="普通用户已停用", data={"target_user_id": target.id})


@router.post("/api/v1/admin/users/{user_id}/enable", response_model=UserResponse)
def enable_user(user_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = lock_user(db, user_id)
    if target is None or target.id == 0:
        raise AppError("USER_NOT_FOUND", "普通用户不存在", 404)
    target.is_active = True
    from app.services.billing import ensure_plan_occurrences, local_today
    for plan in target.plans:
        if plan.is_enabled and plan.deleted_at is None:
            ensure_plan_occurrences(db, plan, local_today(target.timezone))
    db.commit()
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="users", event="user_enabled", request_id=request.state.request_id, message="普通用户已启用", data={"target_user_id": target.id})
    return target
