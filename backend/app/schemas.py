from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


def _serialize_utc(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_timezone(value: str | None) -> str | None:
    if value is None:
        return value
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("invalid timezone") from exc
    return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=255)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: Literal["admin", "user"]
    is_active: bool
    timezone: str
    currency_code: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_timestamps(self, value: datetime) -> str:
        return _serialize_utc(value)


class UserProfilePatch(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=64)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    currency_code: str | None = Field(default=None, min_length=3, max_length=8)

    @model_validator(mode="before")
    @classmethod
    def reject_null_fields(cls, data):
        if isinstance(data, dict) and any(value is None for value in data.values()):
            raise ValueError("profile fields must not be null")
        return data

    _timezone_validator = field_validator("timezone")(_validate_timezone)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=255)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    currency_code: str = Field(default="CNY", min_length=3, max_length=8)

    _timezone_validator = field_validator("timezone")(_validate_timezone)


class AdminUserPatch(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=64)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    currency_code: str | None = Field(default=None, min_length=3, max_length=8)
    revoke_sessions: bool = False

    @model_validator(mode="before")
    @classmethod
    def reject_null_fields(cls, data):
        if isinstance(data, dict):
            for field in ("username", "timezone", "currency_code", "revoke_sessions"):
                if field in data and data[field] is None:
                    raise ValueError(f"{field} must not be null")
        return data

    _timezone_validator = field_validator("timezone")(_validate_timezone)


class AdminPasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=255)


CycleType = Literal["once", "monthly", "quarterly", "yearly", "custom_days"]


class BillPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    first_due_date: date
    cycle_type: CycleType
    cycle_days: int | None = Field(default=None, ge=1, le=36500)
    note: str | None = None

    @model_validator(mode="after")
    def validate_cycle_days(self):
        if self.cycle_type == "custom_days" and self.cycle_days is None:
            raise ValueError("cycle_days is required for custom_days")
        if self.cycle_type != "custom_days" and self.cycle_days is not None:
            raise ValueError("cycle_days is only allowed for custom_days")
        return self


class BillPlanPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    first_due_date: date | None = None
    cycle_type: CycleType | None = None
    cycle_days: int | None = Field(default=None, ge=1, le=36500)
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null_required_fields(cls, data):
        if isinstance(data, dict):
            for field in ("name", "amount", "first_due_date", "cycle_type"):
                if field in data and data[field] is None:
                    raise ValueError(f"{field} must not be null")
        return data

    @model_validator(mode="after")
    def validate_cycle_days(self):
        if self.cycle_type is not None and self.cycle_type != "custom_days" and self.cycle_days is not None:
            raise ValueError("cycle_days is only allowed for custom_days")
        return self


class BillPlanResponse(BaseModel):
    id: int
    future_bills_rebuilt: bool = False
    name: str
    amount: str
    first_due_date: date
    cycle_type: str
    cycle_days: int | None
    is_enabled: bool
    note: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_timestamps(self, value: datetime) -> str:
        return _serialize_utc(value)


class BillOccurrenceResponse(BaseModel):
    id: int
    plan_id: int
    plan_name: str
    due_date: date
    amount: str
    is_valid: bool
    time_status: Literal["upcoming", "passed"]
    cycle_type: CycleType
    cycle_days: int | None


class BillOccurrencePage(BaseModel):
    items: list[BillOccurrenceResponse]
    page: int
    page_size: int
    total: int


class ValidityPatch(BaseModel):
    is_valid: bool


class NotificationSettingsPatch(BaseModel):
    email_enabled: bool = False
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_security: Literal["none", "starttls", "ssl"] | None = None
    smtp_username: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = None
    sender_email: str | None = Field(default=None, max_length=255)
    sender_name: str | None = Field(default=None, max_length=128)
    recipient_email: str | None = Field(default=None, max_length=255)
    feishu_enabled: bool = False
    feishu_webhook: str | None = None
    feishu_secret: str | None = None
    advance_enabled: bool = False
    advance_days: int = Field(default=3, ge=0, le=365)
    advance_time: time = time(9, 0)
    same_day_enabled: bool = False
    same_day_time: time = time(8, 30)


class NotificationSettingsResponse(BaseModel):
    email_enabled: bool
    smtp_host: str | None
    smtp_port: int | None
    smtp_security: str | None
    smtp_username: str | None
    smtp_password_configured: bool
    sender_email: str | None
    sender_name: str | None
    recipient_email: str | None
    feishu_enabled: bool
    feishu_webhook_configured: bool
    feishu_secret_configured: bool
    advance_enabled: bool
    advance_days: int
    advance_time: time
    same_day_enabled: bool
    same_day_time: time


class StatisticsBucket(BaseModel):
    amount: str
    count: int


class NextBillResponse(BaseModel):
    bill_id: int | None
    name: str
    amount: str
    due_date: date
    days_remaining: int


class StatisticsResponse(BaseModel):
    date: date
    today: StatisticsBucket
    current_month: StatisticsBucket
    averages: dict[str, str]
    current_year: StatisticsBucket
    next_bill: NextBillResponse | None


class AdminSummaryResponse(BaseModel):
    total_users: int
    active_users: int
    inactive_users: int


class LogFileResponse(BaseModel):
    date: str
    filename: str
    size: int
    modified_at: datetime

    @field_serializer("modified_at")
    def serialize_modified_at(self, value: datetime) -> str:
        return _serialize_utc(value)


class UserPage(BaseModel):
    items: list[UserResponse]
    page: int
    page_size: int
    total: int
