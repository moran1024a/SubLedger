from __future__ import annotations

from datetime import time

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import NotificationSetting, User
from app.security import hash_password
from app.services.users import utc_now


def ensure_bootstrap_admin(db: Session, settings: Settings) -> User:
    admin = db.get(User, 0)
    if admin is None:
        now = utc_now()
        admin = User(id=0, username=settings.bootstrap_admin.username, password_hash=hash_password(settings.bootstrap_admin.password), role="admin", is_active=True, timezone=settings.app.timezone, currency_code="CNY", created_at=now, updated_at=now)
        db.add(admin)
        db.flush()
        db.add(NotificationSetting(user_id=admin.id, advance_time=time(9, 0), same_day_time=time(8, 30), updated_at=now))
        db.commit()
    elif admin.role != "admin" or not admin.is_active:
        admin.role = "admin"
        admin.is_active = True
        db.commit()
    return admin
