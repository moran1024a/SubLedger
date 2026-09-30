from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import SessionRecord, User
from app.security import hash_session_token


def get_db(request: Request):
    session = request.app.state.database.session()
    try:
        yield session
    finally:
        session.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(request.app.state.settings.security.cookie_name)
    if not token:
        raise AppError("AUTH_REQUIRED", "请先登录", 401)
    session_record = db.scalar(
        select(SessionRecord).where(SessionRecord.token_hash == hash_session_token(token))
    )
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if (
        session_record is None
        or session_record.revoked_at is not None
        or session_record.expires_at <= now
        or session_record.user is None
        or not session_record.user.is_active
    ):
        raise AppError("AUTH_SESSION_INVALID", "登录会话已失效", 401)
    request.state.user_id = session_record.user.id
    return session_record.user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin" or user.id != 0:
        raise AppError("PERMISSION_DENIED", "需要管理员权限", 403)
    return user
