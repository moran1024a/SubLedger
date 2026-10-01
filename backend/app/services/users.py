from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import NotificationSetting, SessionRecord, User
from app.security import hash_password


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def lock_user(db: Session, user_id: int) -> User | None:
    """Current read shared by credential changes and session creation."""
    return db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))


def revoke_all_sessions(db: Session, user_id: int) -> None:
    db.execute(
        update(SessionRecord)
        .where(SessionRecord.user_id == user_id, SessionRecord.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )


def create_user(db: Session, username: str, password: str, timezone_name: str, currency_code: str) -> User:
    db.execute(select(User.id).where(User.id == 0).with_for_update()).first()
    # Keep ID allocation serialized; a locking read avoids an older MySQL RR snapshot.
    max_id = db.scalar(select(User.id).order_by(User.id.desc()).limit(1).with_for_update())
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


def update_profile_fields(db: Session, user: User, values: dict) -> None:
    if "username" in values and db.scalar(select(User.id).where(User.username == values["username"], User.id != user.id)) is not None:
        raise AppError("USER_USERNAME_CONFLICT", "用户名已存在", 409)
    for key, value in values.items():
        setattr(user, key, value.upper() if key == "currency_code" else value)
    user.updated_at = utc_now()
