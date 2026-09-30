from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import SessionRecord, User
from app.security import LoginFailureLimiter, generate_session_token, hash_session_token, verify_password
from app.services.users import utc_now


_DUMMY_PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$2HY0bhCgQBLiXLicTPK/rQ$5/5mIwE9UJDnvqNKrd+xsjBYG92QLGt91TaK3X+MTu8"


def authenticate_user(
    db: Session,
    username: str,
    password: str,
    limiter: LoginFailureLimiter,
    client_key: str | None = None,
) -> User:
    account_key = f"user:{username.lower()}"
    source_key = f"source:{client_key}" if client_key else None
    if not limiter.allowed(account_key, max_attempts=20) or (
        source_key is not None and not limiter.allowed(source_key)
    ):
        raise AppError("AUTH_RATE_LIMITED", "登录尝试过于频繁，请稍后再试", 429)
    user = db.scalar(select(User).where(User.username == username))
    password_hash = user.password_hash if user is not None and user.is_active else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(password_hash, password)
    if user is None or not user.is_active or not password_valid:
        limiter.record_failure(account_key)
        if source_key is not None:
            limiter.record_failure(source_key)
        raise AppError("AUTH_INVALID_CREDENTIALS", "用户名或密码错误", 401)
    limiter.clear(account_key)
    if source_key is not None:
        limiter.clear(source_key)
    return user


def create_session(db: Session, user: User, expire_days: int) -> str:
    token = generate_session_token()
    now = utc_now()
    db.add(
        SessionRecord(
            user_id=user.id,
            token_hash=hash_session_token(token),
            created_at=now,
            expires_at=now + timedelta(days=expire_days),
        )
    )
    db.flush()
    return token


def revoke_session(db: Session, token: str) -> None:
    session_record = db.scalar(
        select(SessionRecord).where(SessionRecord.token_hash == hash_session_token(token))
    )
    if session_record is not None:
        session_record.revoked_at = utc_now()
