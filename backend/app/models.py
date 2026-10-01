from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, INTEGER
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False, default="CNY")
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    sessions: Mapped[list[SessionRecord]] = relationship(back_populates="user")
    plans: Mapped[list[BillPlan]] = relationship(back_populates="user")
    occurrences: Mapped[list[BillOccurrence]] = relationship(back_populates="user")
    notification_settings: Mapped[NotificationSetting | None] = relationship(
        back_populates="user", uselist=False
    )


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(INTEGER(unsigned=True), ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))

    user: Mapped[User] = relationship(back_populates="sessions")
    __table_args__ = (Index("ix_sessions_user_id", "user_id"), Index("ix_sessions_expires_at", "expires_at"))


class BillPlan(Base):
    __tablename__ = "bill_plans"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(INTEGER(unsigned=True), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    first_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    cycle_type: Mapped[str] = mapped_column(String(32), nullable=False)
    cycle_interval: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, default=1, server_default="1")
    cycle_days: Mapped[int | None] = mapped_column(INTEGER(unsigned=True))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    user: Mapped[User] = relationship(back_populates="plans")
    occurrences: Mapped[list[BillOccurrence]] = relationship(back_populates="plan")
    __table_args__ = (Index("ix_bill_plans_user_enabled", "user_id", "is_enabled"),)


class BillOccurrence(Base):
    __tablename__ = "bill_occurrences"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(INTEGER(unsigned=True), ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("bill_plans.id"), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_snapshot: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    invalidated_by_plan_disable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    user: Mapped[User] = relationship(back_populates="occurrences")
    plan: Mapped[BillPlan] = relationship(back_populates="occurrences")
    notification_records: Mapped[list[NotificationRecord]] = relationship(back_populates="bill")
    __table_args__ = (
        UniqueConstraint("plan_id", "due_date", name="uq_bill_occurrences_plan_due"),
        Index("ix_bill_occurrences_user_due", "user_id", "due_date"),
        Index("ix_bill_occurrences_user_valid_due", "user_id", "is_valid", "due_date"),
    )


class NotificationSetting(Base):
    __tablename__ = "notification_settings"

    user_id: Mapped[int] = mapped_column(INTEGER(unsigned=True), ForeignKey("users.id"), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    smtp_host: Mapped[str | None] = mapped_column(String(255))
    smtp_port: Mapped[int | None] = mapped_column(INTEGER(unsigned=True))
    smtp_security: Mapped[str | None] = mapped_column(String(16))
    smtp_username: Mapped[str | None] = mapped_column(String(255))
    smtp_password_encrypted: Mapped[str | None] = mapped_column(Text)
    sender_email: Mapped[str | None] = mapped_column(String(255))
    sender_name: Mapped[str | None] = mapped_column(String(128))
    recipient_email: Mapped[str | None] = mapped_column(String(255))
    feishu_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    feishu_webhook_encrypted: Mapped[str | None] = mapped_column(Text)
    feishu_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    advance_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    advance_days: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, default=3)
    advance_time: Mapped[time] = mapped_column(Time, nullable=False)
    same_day_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    same_day_time: Mapped[time] = mapped_column(Time, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    user: Mapped[User] = relationship(back_populates="notification_settings")


class NotificationRecord(Base):
    __tablename__ = "notification_records"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(INTEGER(unsigned=True), ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("bill_plans.id"), nullable=False)
    bill_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), ForeignKey("bill_occurrences.id"))
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    reminder_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    scheduled_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    retry_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(1000))
    attempt_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    next_retry_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    error_code: Mapped[str | None] = mapped_column(String(64))

    bill: Mapped[BillOccurrence | None] = relationship(back_populates="notification_records")
    __table_args__ = (
        UniqueConstraint(
            "plan_id", "due_date", "channel", "reminder_type", name="uq_notification_business_key"
        ),
        Index("ix_notification_records_user_scheduled", "user_id", "scheduled_at"),
        Index("ix_notification_records_status_scheduled", "status", "scheduled_at"),
    )
