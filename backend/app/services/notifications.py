from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import smtplib
import ssl
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import BillOccurrence, BillPlan, NotificationRecord, NotificationSetting, User
from app.security import decrypt_secret
from app.services.billing import iter_plan_dates
from app.services.logging import write_system_log
from app.services.outbound import (
    connect_addresses,
    resolve_addresses,
    resolve_smtp_target,
    validate_feishu_webhook,
)
from app.services.users import lock_user, utc_now


class _SMTP(smtplib.SMTP):
    def __init__(self, host, port, addresses, **kwargs):
        self._addresses = addresses
        super().__init__(host, port, **kwargs)

    def _get_socket(self, host, port, timeout):
        return connect_addresses(self._addresses, timeout, self.source_address)


class _SMTPSSL(smtplib.SMTP_SSL):
    def __init__(self, host, port, addresses, **kwargs):
        self._addresses = addresses
        super().__init__(host, port, **kwargs)

    def _get_socket(self, host, port, timeout):
        sock = connect_addresses(self._addresses, timeout, self.source_address)
        try:
            return self.context.wrap_socket(sock, server_hostname=host)
        except Exception:
            sock.close()
            raise


class _WebhookConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, addresses: list[tuple]):
        super().__init__(host, port=443, timeout=15, context=ssl.create_default_context())
        self._create_connection = lambda _, timeout, source_address: connect_addresses(
            addresses, timeout, source_address
        )


def _send_email(setting: NotificationSetting, password: str, subject: str, content: str, settings=None) -> None:
    host, addresses = resolve_smtp_target(
        setting.smtp_host, setting.smtp_port, getattr(settings, "security", None)
    )
    if setting.smtp_security not in {"none", "starttls", "ssl"}:
        raise ValueError("SMTP security mode is invalid")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((setting.sender_name, setting.sender_email)) if setting.sender_name else setting.sender_email
    message["To"] = setting.recipient_email
    message.set_content(content)
    context = ssl.create_default_context()
    if setting.smtp_security == "ssl":
        client = _SMTPSSL(host, setting.smtp_port, addresses, timeout=15, context=context)
    else:
        client = _SMTP(host, setting.smtp_port, addresses, timeout=15)
    try:
        if setting.smtp_security == "starttls":
            client.starttls(context=context)
        if setting.smtp_username:
            client.login(setting.smtp_username, password)
        client.send_message(message)
    finally:
        # QUIT cannot change the outcome after SMTP accepted DATA, and must not
        # mask an exception raised by login or send_message.
        try:
            client.quit()
        except Exception:
            try:
                client.close()
            except Exception:
                pass


def _send_feishu(webhook: str, secret: str | None, content: str) -> None:
    host, path = validate_feishu_webhook(webhook)
    addresses = resolve_addresses(host, 443)
    payload: dict = {"msg_type": "text", "content": {"text": content}}
    if secret:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        signature = base64.b64encode(hmac.new(string_to_sign, b"", hashlib.sha256).digest()).decode("ascii")
        payload.update({"timestamp": timestamp, "sign": signature})
    connection = _WebhookConnection(host, addresses)
    try:
        connection.request(
            "POST", path, body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        # Redirects are errors. The standard client does not consult proxy
        # environment variables or follow a redirect to an untrusted target.
        if not 200 <= response.status < 300:
            raise RuntimeError("Feishu webhook returned an unsuccessful HTTP status")
        body = json.loads(response.read(65537))
    finally:
        connection.close()
    if not isinstance(body, dict):
        raise RuntimeError("Feishu webhook returned an invalid response")
    status = body.get("code", body.get("StatusCode"))
    if type(status) not in (str, int) or status not in (0, "0"):
        raise RuntimeError("Feishu webhook rejected the message")


def send_test_email(setting: NotificationSetting, fernet, settings=None) -> None:
    password = decrypt_secret(fernet, setting.smtp_password_encrypted) or ""
    _send_email(setting, password, "SubLedger 测试通知", "邮件通知配置正常。", settings)


def send_test_feishu(setting: NotificationSetting, fernet) -> None:
    webhook = decrypt_secret(fernet, setting.feishu_webhook_encrypted)
    if not webhook:
        raise ValueError("Feishu webhook is not configured")
    secret = decrypt_secret(fernet, setting.feishu_secret_encrypted)
    _send_feishu(webhook, secret, "SubLedger 飞书通知配置正常。")


def check_notifications(database, settings, fernet) -> None:
    now_utc = datetime.now(timezone.utc)
    with database.session() as db:
        user_ids = db.scalars(
            select(User.id).where(User.is_active.is_(True)).order_by(User.id)
        ).all()
    for user_id in user_ids:
        with database.session() as db:
            try:
                user = db.get(User, user_id)
                setting = db.get(NotificationSetting, user_id)
                if user is None or not user.is_active or setting is None:
                    continue
                local_now = now_utc.astimezone(ZoneInfo(user.timezone))
                plan_ids = db.scalars(
                    select(BillPlan.id).where(
                        BillPlan.user_id == user_id,
                        BillPlan.is_enabled.is_(True),
                        BillPlan.deleted_at.is_(None),
                    ).order_by(BillPlan.id)
                ).all()
                reminder_specs = []
                if setting.advance_enabled:
                    reminder_specs.append(("advance", setting.advance_days, setting.advance_time))
                if setting.same_day_enabled:
                    reminder_specs.append(("same_day", 0, setting.same_day_time))
                for reminder_type, days_before, reminder_time in reminder_specs:
                    due_date = local_now.date() + timedelta(days=days_before)
                    scheduled_local = datetime.combine(
                        local_now.date(), reminder_time, tzinfo=ZoneInfo(user.timezone)
                    )
                    if scheduled_local > local_now:
                        continue
                    for plan_id in plan_ids:
                        try:
                            plan = db.get(BillPlan, plan_id)
                            if plan is None:
                                continue
                            channels = []
                            if setting.email_enabled:
                                channels.append("email")
                            if setting.feishu_enabled:
                                channels.append("feishu")
                            for channel in channels:
                                _attempt_notification(
                                    db, settings, fernet, plan,
                                    due_date, channel, reminder_type,
                                    scheduled_local.astimezone(timezone.utc).replace(tzinfo=None),
                                )
                                # _attempt_notification can skip a previously sent
                                # record while holding a row lock. End every attempt.
                                db.commit()
                        except Exception as exc:
                            db.rollback()
                            _log_check_failure(settings, user_id, plan_id, exc)
            except Exception as exc:
                db.rollback()
                _log_check_failure(settings, user_id, None, exc)


def _log_check_failure(settings, user_id, plan_id, exc) -> None:
    try:
        write_system_log(
            settings, level="ERROR", module="notifications",
            event="notification_check_failed", request_id=None,
            message="通知规则检查失败",
            data={"user_id": user_id, "plan_id": plan_id, "error_type": type(exc).__name__},
        )
    except Exception:
        # Logging failure must not stop subsequent rules and users either.
        pass


def _attempt_notification(db, settings, fernet, plan, due_date, channel, reminder_type, scheduled_at) -> None:
    user = lock_user(db, plan.user_id)
    setting = db.scalar(select(NotificationSetting).where(NotificationSetting.user_id == plan.user_id).with_for_update().execution_options(populate_existing=True))
    if user is None or not user.is_active or setting is None:
        return
    if channel not in {"email", "feishu"} or not getattr(setting, f"{channel}_enabled"):
        return
    if reminder_type not in {"advance", "same_day"} or not getattr(setting, f"{reminder_type}_enabled"):
        return
    days = setting.advance_days if reminder_type == "advance" else 0
    reminder_time = setting.advance_time if reminder_type == "advance" else setting.same_day_time
    expected = datetime.combine(due_date - timedelta(days=days), reminder_time, tzinfo=ZoneInfo(user.timezone)).astimezone(timezone.utc).replace(tzinfo=None)
    if scheduled_at != expected:
        return
    plan = db.scalar(
        select(BillPlan)
        .where(BillPlan.id == plan.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        plan is None
        or not plan.is_enabled
        or plan.deleted_at is not None
        or due_date not in set(iter_plan_dates(plan, due_date, due_date))
    ):
        return
    occurrence = db.scalar(
        select(BillOccurrence)
        .where(
            BillOccurrence.plan_id == plan.id,
            BillOccurrence.due_date == due_date,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if occurrence is not None and not occurrence.is_valid:
        return
    record = db.scalar(
        select(NotificationRecord).where(
            NotificationRecord.plan_id == plan.id,
            NotificationRecord.due_date == due_date,
            NotificationRecord.channel == channel,
            NotificationRecord.reminder_type == reminder_type,
        ).with_for_update().execution_options(populate_existing=True)
    )
    if record is not None and (record.status == "sent" or record.retry_count >= 3):
        return
    if record is None:
        record = NotificationRecord(user_id=plan.user_id, plan_id=plan.id, bill_id=occurrence.id if occurrence else None, due_date=due_date, channel=channel, reminder_type=reminder_type, status="pending", scheduled_at=scheduled_at, retry_count=0)
        try:
            with db.begin_nested():
                db.add(record)
                db.flush()
        except IntegrityError:
            record = db.scalar(
                select(NotificationRecord).where(
                    NotificationRecord.plan_id == plan.id,
                    NotificationRecord.due_date == due_date,
                    NotificationRecord.channel == channel,
                    NotificationRecord.reminder_type == reminder_type,
                ).with_for_update().execution_options(populate_existing=True)
            )
            if record is None or record.status == "sent" or record.retry_count >= 3:
                return
    content = f"{plan.name} 将于 {due_date.isoformat()} 产生账单，金额 {plan.amount:.2f}。"
    record.status = "sending"
    db.flush()
    try:
        if channel == "email":
            password = decrypt_secret(fernet, setting.smtp_password_encrypted) or ""
            _send_email(setting, password, "SubLedger 账单提醒", content, settings)
        else:
            webhook = decrypt_secret(fernet, setting.feishu_webhook_encrypted)
            if not webhook:
                raise ValueError("Feishu webhook is not configured")
            _send_feishu(webhook, decrypt_secret(fernet, setting.feishu_secret_encrypted), content)
        record.status = "sent"
        record.sent_at = utc_now()
        record.error_message = None
    except Exception as exc:
        error_summary = type(exc).__name__
        record.status = "failed"
        record.retry_count += 1
        record.error_message = error_summary
        write_system_log(settings, level="ERROR", module="notifications", event="notification_failed", request_id=None, message="通知发送失败", data={"user_id": plan.user_id, "plan_id": plan.id, "channel": channel, "error_type": error_summary})
