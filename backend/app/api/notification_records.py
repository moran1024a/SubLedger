from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.errors import AppError
from app.models import BillPlan, NotificationRecord, User
from app.services.users import utc_now
from app.schemas import NotificationRecordPage

router = APIRouter(prefix="/api/v1/me/notification-records", tags=["notifications"])

ERROR_MESSAGES = {
    "DELIVERY_UNKNOWN": "渠道未返回明确结果，请检查是否收到消息",
    "NETWORK_TIMEOUT": "网络连接或发送超时",
    "NETWORK_ERROR": "无法连接通知渠道",
    "TLS_CERTIFICATE_INVALID": "服务器证书校验失败",
    "SMTP_REJECTED": "邮件服务器拒绝请求，请检查账户和发送设置",
    "SMTP_RECIPIENT_REJECTED": "邮件服务器拒绝收件地址",
    "WEBHOOK_HTTP_ERROR": "飞书服务返回错误状态",
    "WEBHOOK_REJECTED": "飞书拒绝消息，请检查机器人和签名设置",
    "CHANNEL_CONFIGURATION_INVALID": "通知配置不完整或不符合安全设置",
}


@router.get("", response_model=NotificationRecordPage)
def list_records(
    channel: Literal["email", "feishu"] | None = None,
    status: Literal["pending", "retry_wait", "sent", "failed", "unknown", "expired"] | None = None,
    start_date: date | None = None, end_date: date | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise AppError("INVALID_DATE_RANGE", "开始日期不能晚于结束日期", 400)
    zone = ZoneInfo(user.timezone)

    def midnight(value):
        try:
            return datetime.combine(value, time.min, tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
        except OverflowError:
            return datetime.min if value.year == 1 else datetime.max

    today = utc_now().replace(tzinfo=timezone.utc).astimezone(zone).date()
    effective_status = case(
        ((NotificationRecord.status.in_(["pending", "retry_wait"])) & (NotificationRecord.scheduled_at < midnight(today)), "expired"),
        else_=NotificationRecord.status,
    )
    filters = [NotificationRecord.user_id == user.id, BillPlan.user_id == user.id]
    if channel:
        filters.append(NotificationRecord.channel == channel)
    if status:
        filters.append(effective_status == status)
    if start_date:
        filters.append(NotificationRecord.scheduled_at >= midnight(start_date))
    if end_date and end_date < date.max:
        filters.append(NotificationRecord.scheduled_at < midnight(end_date + timedelta(days=1)))
    base = select(NotificationRecord, BillPlan.name, effective_status.label("display_status")).join(BillPlan, BillPlan.id == NotificationRecord.plan_id).where(*filters)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(base.order_by(NotificationRecord.scheduled_at.desc(), NotificationRecord.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()

    def utc(value):
        return value.replace(tzinfo=timezone.utc) if value else None

    return {
        "items": [{
            "id": record.id, "plan_id": record.plan_id, "plan_name": name,
            "due_date": record.due_date, "channel": record.channel,
            "reminder_type": record.reminder_type, "status": display_status,
            "scheduled_at": utc(record.scheduled_at), "sent_at": utc(record.sent_at),
            "attempt_count": record.attempt_count, "last_attempt_at": utc(record.last_attempt_at),
            "next_retry_at": utc(record.next_retry_at) if display_status == "retry_wait" else None,
            "error_code": record.error_code,
            "error_message": ERROR_MESSAGES.get(record.error_code, "历史记录未保存详细原因" if record.error_message else None),
        } for record, name, display_status in rows],
        "page": page, "page_size": page_size, "total": total,
    }
