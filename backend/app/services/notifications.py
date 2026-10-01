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

from app.config import NotificationConfig
from app.models import BillOccurrence, BillPlan, NotificationRecord, NotificationSetting, User
from app.security import decrypt_secret
from app.services.billing import iter_plan_dates
from app.services.logging import write_system_log
from app.services.outbound import (
    SendDeadline,
    connect_addresses,
    resolve_addresses,
    resolve_smtp_target,
    validate_feishu_webhook,
)
from app.services.users import lock_user, utc_now


class DeliveryError(RuntimeError):
    def __init__(self, code, *, retryable=False, unknown=False, message=None):
        super().__init__(message or code)
        self.code = code
        self.retryable = retryable
        self.unknown = unknown


def notification_config(settings):
    return getattr(settings, "notifications", NotificationConfig())


def classify_error(exc, *, submitted=False):
    if isinstance(exc, DeliveryError):
        return exc
    if isinstance(exc, smtplib.SMTPResponseException):
        return DeliveryError("SMTP_REJECTED", retryable=400 <= exc.smtp_code < 500)
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        temporary = bool(exc.recipients) and all(400 <= item[0] < 500 for item in exc.recipients.values())
        return DeliveryError("SMTP_RECIPIENT_REJECTED", retryable=temporary)
    if submitted:
        return DeliveryError("DELIVERY_UNKNOWN", unknown=True)
    if isinstance(exc, ssl.SSLCertVerificationError):
        return DeliveryError("TLS_CERTIFICATE_INVALID")
    if isinstance(exc, (TimeoutError, OSError, smtplib.SMTPServerDisconnected)):
        return DeliveryError("NETWORK_TIMEOUT" if isinstance(exc, TimeoutError) else "NETWORK_ERROR", retryable=True)
    return DeliveryError("CHANNEL_CONFIGURATION_INVALID")


class _SMTP(smtplib.SMTP):
    def __init__(self, host, port, addresses, *, deadline=None, **kwargs):
        self._addresses = addresses
        self._deadline = deadline
        self.message_started = False
        super().__init__(host, port, **kwargs)

    def _get_socket(self, host, port, timeout):
        return connect_addresses(self._addresses, timeout, self.source_address, self._deadline)

    def data(self, msg):
        # Conservative ambiguity boundary: an interrupted DATA exchange may have
        # reached the provider. Explicit SMTP rejections are still safe to retry.
        self.message_started = True
        return super().data(msg)


class _SMTPSSL(smtplib.SMTP_SSL):
    def __init__(self, host, port, addresses, *, deadline=None, **kwargs):
        self._addresses = addresses
        self._deadline = deadline
        self.message_started = False
        super().__init__(host, port, **kwargs)

    def _get_socket(self, host, port, timeout):
        sock = connect_addresses(self._addresses, timeout, self.source_address, self._deadline)
        try:
            return self.context.wrap_socket(sock, server_hostname=host)
        except Exception:
            sock.close()
            raise

    def data(self, msg):
        self.message_started = True
        return super().data(msg)


class _WebhookConnection(http.client.HTTPSConnection):
    def __init__(self, host, addresses, deadline, connect_timeout):
        super().__init__(host, port=443, timeout=connect_timeout, context=deadline.wrap_context(ssl.create_default_context()))
        self._create_connection = lambda _, timeout, source_address: connect_addresses(
            addresses, timeout, source_address, deadline
        )


def _prepare_delivery(setting, channel, settings, fernet):
    timeout = notification_config(settings).dns_timeout_seconds
    if channel == "email":
        host, addresses = resolve_smtp_target(setting.smtp_host, setting.smtp_port, getattr(settings, "security", None), timeout=timeout)
        return host, addresses
    webhook = decrypt_secret(fernet, setting.feishu_webhook_encrypted)
    host, _ = validate_feishu_webhook(webhook)
    return host, resolve_addresses(host, 443, timeout=timeout)


def _send_email(setting, password, subject, content, settings=None, target=None):
    config = notification_config(settings)
    host, addresses = target or resolve_smtp_target(setting.smtp_host, setting.smtp_port, getattr(settings, "security", None), timeout=config.dns_timeout_seconds)
    if setting.smtp_security not in {"none", "starttls", "ssl"}:
        raise ValueError("SMTP security mode is invalid")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((setting.sender_name, setting.sender_email)) if setting.sender_name else setting.sender_email
    message["To"] = setting.recipient_email
    message.set_content(content)
    client = None
    submitting = False
    with SendDeadline(config.send_timeout_seconds) as deadline:
        context = deadline.wrap_context(ssl.create_default_context())
        try:
            if setting.smtp_security == "ssl":
                client = _SMTPSSL(host, setting.smtp_port, addresses, timeout=config.connect_timeout_seconds, context=context, deadline=deadline)
            else:
                client = _SMTP(host, setting.smtp_port, addresses, timeout=config.connect_timeout_seconds, deadline=deadline)
            if setting.smtp_security == "starttls":
                client.starttls(context=context)
            if setting.smtp_username:
                client.login(setting.smtp_username, password)
            submitting = True
            client.send_message(message)
        except ValueError:
            raise
        except Exception as exc:
            raise classify_error(exc, submitted=getattr(client, "message_started", submitting)) from exc
        finally:
            # SMTP acceptance is final. QUIT failure cannot turn success into a
            # retry; closing directly also avoids spending the budget on QUIT.
            if client:
                try:
                    client.close()
                except OSError:
                    pass


def _send_feishu(webhook, secret, content, settings=None, target=None):
    config = notification_config(settings)
    host, path = validate_feishu_webhook(webhook)
    _, addresses = target or (host, resolve_addresses(host, 443, timeout=config.dns_timeout_seconds))
    payload = {"msg_type": "text", "content": {"text": content}}
    if secret:
        timestamp = str(int(time.time()))
        signature = base64.b64encode(hmac.new(f"{timestamp}\n{secret}".encode(), b"", hashlib.sha256).digest()).decode("ascii")
        payload.update({"timestamp": timestamp, "sign": signature})
    submitted = False
    with SendDeadline(config.send_timeout_seconds) as deadline:
        connection = _WebhookConnection(host, addresses, deadline, config.connect_timeout_seconds)
        try:
            connection.connect()
            submitted = True
            connection.request("POST", path, body=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            if not 200 <= response.status < 300:
                # Explicit rejection (including throttling) is safe to retry.
                raise DeliveryError("WEBHOOK_HTTP_ERROR", retryable=response.status == 429 or response.status >= 500, message="Feishu webhook returned an unsuccessful HTTP status")
            body = json.loads(response.read(65537))
            if not isinstance(body, dict):
                raise DeliveryError("DELIVERY_UNKNOWN", unknown=True)
            status = body.get("code", body.get("StatusCode"))
            if type(status) not in (str, int) or status not in (0, "0"):
                raise DeliveryError("WEBHOOK_REJECTED")
        except Exception as exc:
            raise classify_error(exc, submitted=submitted) from exc
        finally:
            connection.close()


def send_test_email(setting, fernet, settings=None):
    password = decrypt_secret(fernet, setting.smtp_password_encrypted) or ""
    _send_email(setting, password, "SubLedger 测试通知", "邮件通知配置正常。", settings)


def send_test_feishu(setting, fernet, settings=None):
    webhook = decrypt_secret(fernet, setting.feishu_webhook_encrypted)
    if not webhook:
        raise ValueError("Feishu webhook is not configured")
    _send_feishu(webhook, decrypt_secret(fernet, setting.feishu_secret_encrypted), "SubLedger 飞书通知配置正常。", settings)


def check_notifications(database, settings, fernet) -> dict:
    counts = {"sent": 0, "failed": 0, "unknown": 0, "errors": 0}
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
                local_now = datetime.now(timezone.utc).astimezone(ZoneInfo(user.timezone))
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
                                outcome = _attempt_notification(
                                    db, settings, fernet, plan,
                                    due_date, channel, reminder_type,
                                    scheduled_local.astimezone(timezone.utc).replace(tzinfo=None),
                                )
                                # _attempt_notification can skip a previously sent
                                # record while holding a row lock. End every attempt.
                                db.commit()
                                if outcome in counts:
                                    counts[outcome] += 1
                        except Exception as exc:
                            db.rollback()
                            counts["errors"] += 1
                            _log_check_failure(settings, user_id, plan_id, exc)
            except Exception as exc:
                db.rollback()
                counts["errors"] += 1
                _log_check_failure(settings, user_id, None, exc)
    return counts


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


def setting_version(setting):
    # Compare the actual configuration, not timestamp precision or a stale ORM
    # object that populate_existing would mutate in place.
    return tuple(getattr(setting, column.name) for column in NotificationSetting.__table__.columns)


def _eligible_record(record, now):
    return record is None or (
        record.status in {"pending", "retry_wait"}
        and record.attempt_count < 3
        and (record.next_retry_at is None or record.next_retry_at <= now)
    )


def _attempt_notification(db, settings, fernet, plan, due_date, channel, reminder_type, scheduled_at):
    snapshot = db.get(NotificationSetting, plan.user_id)
    if snapshot is None or channel not in {"email", "feishu"} or not getattr(snapshot, f"{channel}_enabled"):
        return
    # Avoid DNS for rules that are not due and notifications already completed.
    if not plan.is_enabled or plan.deleted_at is not None or due_date not in set(iter_plan_dates(plan, due_date, due_date)):
        return
    business_key = (
        NotificationRecord.plan_id == plan.id, NotificationRecord.due_date == due_date,
        NotificationRecord.channel == channel, NotificationRecord.reminder_type == reminder_type,
    )
    if not _eligible_record(db.scalar(select(NotificationRecord).where(*business_key)), utc_now()):
        return
    version = setting_version(snapshot)
    target, preparation_error = None, None
    try:
        target = _prepare_delivery(snapshot, channel, settings, fernet)
    except Exception as exc:
        preparation_error = classify_error(exc)
    # DNS has finished before any row lock is acquired.
    user = lock_user(db, plan.user_id)
    setting = db.scalar(select(NotificationSetting).where(NotificationSetting.user_id == plan.user_id).with_for_update().execution_options(populate_existing=True))
    if user is None or not user.is_active or setting is None or setting_version(setting) != version:
        return
    if reminder_type not in {"advance", "same_day"} or not getattr(setting, f"{reminder_type}_enabled"):
        return
    days = setting.advance_days if reminder_type == "advance" else 0
    reminder_time = setting.advance_time if reminder_type == "advance" else setting.same_day_time
    zone = ZoneInfo(user.timezone)
    scheduled_local = datetime.combine(due_date - timedelta(days=days), reminder_time, tzinfo=zone)
    expected = scheduled_local.astimezone(timezone.utc).replace(tzinfo=None)
    now = utc_now()
    if scheduled_at != expected or scheduled_local.date() != now.replace(tzinfo=timezone.utc).astimezone(zone).date() or expected > now:
        return
    plan = db.scalar(select(BillPlan).where(BillPlan.id == plan.id).with_for_update().execution_options(populate_existing=True))
    if plan is None or not plan.is_enabled or plan.deleted_at is not None or due_date not in set(iter_plan_dates(plan, due_date, due_date)):
        return
    occurrence = db.scalar(select(BillOccurrence).where(BillOccurrence.plan_id == plan.id, BillOccurrence.due_date == due_date).with_for_update().execution_options(populate_existing=True))
    if occurrence is not None and not occurrence.is_valid:
        return
    record = db.scalar(select(NotificationRecord).where(*business_key).with_for_update().execution_options(populate_existing=True))
    if not _eligible_record(record, now):
        return
    if record is None:
        record = NotificationRecord(user_id=plan.user_id, plan_id=plan.id, bill_id=occurrence.id if occurrence else None, due_date=due_date, channel=channel, reminder_type=reminder_type, status="pending", scheduled_at=scheduled_at, retry_count=0, attempt_count=0)
        # The locked plan serializes creation of this unique business key.
        db.add(record)
    record.attempt_count += 1
    record.last_attempt_at = now
    record.next_retry_at = None
    record.status = "sending"
    db.flush()
    content = f"{plan.name} 将于 {due_date.isoformat()} 产生账单，金额 {plan.amount:.2f}。"
    try:
        if preparation_error:
            raise preparation_error
        if channel == "email":
            password = decrypt_secret(fernet, setting.smtp_password_encrypted) or ""
            _send_email(setting, password, "SubLedger 账单提醒", content, settings, target)
        else:
            _send_feishu(decrypt_secret(fernet, setting.feishu_webhook_encrypted), decrypt_secret(fernet, setting.feishu_secret_encrypted), content, settings, target)
        record.status = "sent"
        record.sent_at = utc_now()
        record.error_message = None
        record.error_code = None
        return "sent"
    except Exception as exc:
        failure = classify_error(exc)
        record.status = "unknown" if failure.unknown else "failed"
        record.retry_count += 1
        record.error_code = failure.code
        record.error_message = failure.code
        if failure.retryable and record.attempt_count < 3:
            retry_at = utc_now() + timedelta(seconds=(60, 300)[record.attempt_count - 1])
            if retry_at.replace(tzinfo=timezone.utc).astimezone(zone).date() == scheduled_local.date():
                record.status = "retry_wait"
                record.next_retry_at = retry_at
        write_system_log(settings, level="ERROR", module="notifications", event="notification_failed", request_id=None, message="通知发送失败", data={"user_id": plan.user_id, "plan_id": plan.id, "channel": channel, "error_code": failure.code})
        return "unknown" if failure.unknown else "failed"
