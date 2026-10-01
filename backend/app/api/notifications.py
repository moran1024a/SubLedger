from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.errors import AppError
from app.models import NotificationSetting, User
from app.schemas import NotificationSettingsPatch, NotificationSettingsResponse
from app.security import decrypt_secret, encrypt_secret
from app.services.logging import write_user_log
from app.services.notifications import send_test_email, send_test_feishu
from app.services.outbound import resolve_smtp_target, validate_feishu_webhook
from app.services.users import lock_user, utc_now

router = APIRouter(prefix="/api/v1/me/notification-settings", tags=["notifications"])


def _settings(db: Session, user_id: int) -> NotificationSetting:
    setting = db.get(NotificationSetting, user_id)
    if setting is None:
        raise AppError("NOTIFICATION_SETTINGS_NOT_FOUND", "通知配置不存在", 404)
    return setting


def _response(setting: NotificationSetting) -> dict:
    return {"email_enabled": setting.email_enabled, "smtp_host": setting.smtp_host, "smtp_port": setting.smtp_port, "smtp_security": setting.smtp_security, "smtp_username": setting.smtp_username, "smtp_password_configured": bool(setting.smtp_password_encrypted), "sender_email": setting.sender_email, "sender_name": setting.sender_name, "recipient_email": setting.recipient_email, "feishu_enabled": setting.feishu_enabled, "feishu_webhook_configured": bool(setting.feishu_webhook_encrypted), "feishu_secret_configured": bool(setting.feishu_secret_encrypted), "advance_enabled": setting.advance_enabled, "advance_days": setting.advance_days, "advance_time": setting.advance_time, "same_day_enabled": setting.same_day_enabled, "same_day_time": setting.same_day_time}


def _validate_enabled_channels(setting: NotificationSetting) -> None:
    if setting.email_enabled and not all((setting.smtp_host, setting.smtp_port, setting.smtp_security, setting.sender_email, setting.recipient_email)):
        raise AppError("EMAIL_SETTINGS_INCOMPLETE", "邮件通知配置不完整", 400)
    if setting.feishu_enabled and not setting.feishu_webhook_encrypted:
        raise AppError("FEISHU_SETTINGS_INCOMPLETE", "飞书通知配置不完整", 400)


@router.get("", response_model=NotificationSettingsResponse)
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _response(_settings(db, user.id))


@router.put("", response_model=NotificationSettingsResponse)
def put_settings(payload: NotificationSettingsPatch, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current = lock_user(db, user.id)
    if current is None or not current.is_active:
        raise AppError("AUTH_INVALID_CREDENTIALS", "用户已停用", 401)
    setting = db.scalar(select(NotificationSetting).where(NotificationSetting.user_id == user.id).with_for_update().execution_options(populate_existing=True))
    if setting is None:
        raise AppError("NOTIFICATION_SETTINGS_NOT_FOUND", "通知配置不存在", 404)
    previous_smtp_target = (setting.smtp_host, setting.smtp_port)
    values = payload.model_dump(exclude_unset=True, exclude={"smtp_password", "feishu_webhook", "feishu_secret"})
    for key, value in values.items():
        setattr(setting, key, value)
    if payload.smtp_password is not None:
        setting.smtp_password_encrypted = encrypt_secret(request.app.state.fernet, payload.smtp_password)
    if payload.feishu_webhook is not None:
        setting.feishu_webhook_encrypted = encrypt_secret(request.app.state.fernet, payload.feishu_webhook)
    if payload.feishu_secret is not None:
        setting.feishu_secret_encrypted = encrypt_secret(request.app.state.fernet, payload.feishu_secret)
    _validate_enabled_channels(setting)
    if setting.smtp_host and (
        setting.email_enabled
        or (setting.smtp_host, setting.smtp_port) != previous_smtp_target
    ):
        try:
            resolve_smtp_target(
                setting.smtp_host, setting.smtp_port or 25, request.app.state.settings.security
            )
        except (ValueError, UnicodeError, OSError) as exc:
            raise AppError("SMTP_TARGET_NOT_ALLOWED", "SMTP 目标不符合服务器安全设置或无法解析", 400) from exc
    if setting.feishu_enabled or payload.feishu_webhook is not None:
        webhook = decrypt_secret(request.app.state.fernet, setting.feishu_webhook_encrypted)
        try:
            if webhook:
                validate_feishu_webhook(webhook)
            elif setting.feishu_enabled:
                raise AppError("FEISHU_SETTINGS_INCOMPLETE", "飞书通知配置不完整", 400)
        except ValueError as exc:
            raise AppError("FEISHU_WEBHOOK_NOT_ALLOWED", "仅支持飞书或 Lark 官方 HTTPS 机器人 Webhook", 400) from exc
    setting.updated_at = utc_now()
    db.commit()
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="notifications", event="notification_settings_updated", request_id=request.state.request_id, message="通知配置已修改")
    return _response(setting)


@router.post("/test-email", status_code=204)
def test_email(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    setting = _settings(db, user.id)
    _validate_enabled_channels(setting)
    try:
        send_test_email(setting, request.app.state.fernet, request.app.state.settings)
    except Exception as exc:
        raise AppError("EMAIL_TEST_FAILED", "测试邮件发送失败", 400) from exc
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="notifications", event="test_email_sent", request_id=request.state.request_id, message="测试邮件已发送")


@router.post("/test-feishu", status_code=204)
def test_feishu(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    setting = _settings(db, user.id)
    _validate_enabled_channels(setting)
    try:
        send_test_feishu(setting, request.app.state.fernet)
    except Exception as exc:
        raise AppError("FEISHU_TEST_FAILED", "测试飞书消息发送失败", 400) from exc
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="notifications", event="test_feishu_sent", request_id=request.state.request_id, message="测试飞书消息已发送")
