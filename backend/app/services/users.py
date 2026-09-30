from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import NotificationSetting, SessionRecord, User
from app.security import hash_password


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def revoke_all_sessions(db: Session, user_id: int) -> None:
    db.execute(
        update(SessionRecord)
        .where(SessionRecord.user_id == user_id, SessionRecord.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )


def create_user(db: Session, settings, username: str, password: str, timezone_name: str, currency_code: str) -> User:
    db.execute(select(User.id).where(User.id == 0).with_for_update()).first()
    if db.scalar(select(func.count(User.id))) >= settings.app.max_users:
        raise AppError("USER_LIMIT_REACHED", "账户数量已达到上限", 400)
    max_id = db.scalar(select(func.max(User.id)))
    user = User(
        id=(max_id or 0) + 1,
        username=username,
        password_hash=hash_password(password),
        role="user",
        is_active=True,
        timezone=timezone_name,
        currency_code=currency_code.upper(),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(user)
    db.flush()
    db.add(NotificationSetting(user_id=user.id, advance_time=time(9, 0), same_day_time=time(8, 30), updated_at=utc_now()))
    return user
