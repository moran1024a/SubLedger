from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.errors import AppError
from app.models import NotificationSetting, User
from app.schemas import NotificationSettingsPatch, NotificationSettingsResponse
from app.security import decrypt_secret, encrypt_secret
from app.services.logging import write_user_log
from app.services.notifications import classify_error, notification_config, send_test_email, send_test_feishu, setting_version
from app.services.outbound import resolve_smtp_target, validate_feishu_webhook
from app.services.users import lock_user, utc_now
from app.services.notification_verification import NotificationVerification, CHANNEL_FIELDS
from threading import Lock

_verifier_lock = Lock()

def _verifier(request):
    with _verifier_lock:
        if not hasattr(request.app.state, "notification_verification"):
            request.app.state.notification_verification = NotificationVerification()
        return request.app.state.notification_verification

def _session(request):
    # Proofs are bound to the session without retaining its raw cookie.
    cookie_name = request.app.state.settings.security.cookie_name
    return _verifier(request).digest(request.cookies.get(cookie_name))


router = APIRouter(prefix="/api/v1/me/notification-settings", tags=["notifications"])


def _settings(db: Session, user_id: int) -> NotificationSetting:
    setting = db.get(NotificationSetting, user_id)
    if setting is None:
        raise AppError("NOTIFICATION_SETTINGS_NOT_FOUND", "通知配置不存在", 404)
    return setting


def _response(setting: NotificationSetting, request) -> dict:
    return {"settings_version": _verifier(request).version(setting), "email_enabled": setting.email_enabled, "smtp_host": setting.smtp_host, "smtp_port": setting.smtp_port, "smtp_security": setting.smtp_security, "smtp_username": setting.smtp_username, "smtp_password_configured": bool(setting.smtp_password_encrypted), "sender_email": setting.sender_email, "sender_name": setting.sender_name, "recipient_email": setting.recipient_email, "feishu_enabled": setting.feishu_enabled, "feishu_webhook_configured": bool(setting.feishu_webhook_encrypted), "feishu_secret_configured": bool(setting.feishu_secret_encrypted), "advance_enabled": setting.advance_enabled, "advance_days": setting.advance_days, "advance_time": setting.advance_time, "same_day_enabled": setting.same_day_enabled, "same_day_time": setting.same_day_time}


def _validate_enabled_channels(setting: NotificationSetting) -> None:
    if setting.email_enabled and not all((setting.smtp_host, setting.smtp_port, setting.smtp_security, setting.sender_email, setting.recipient_email)):
        raise AppError("EMAIL_SETTINGS_INCOMPLETE", "邮件通知配置不完整", 400)
    if setting.feishu_enabled and not setting.feishu_webhook_encrypted:
        raise AppError("FEISHU_SETTINGS_INCOMPLETE", "飞书通知配置不完整", 400)



def _candidate(original, payload, request):
    setting = SimpleNamespace(**{column.name: getattr(original, column.name) for column in NotificationSetting.__table__.columns})
    values = payload.model_dump(exclude_unset=True, exclude={"smtp_password", "feishu_webhook", "feishu_secret", "settings_version", "email_verification_token", "feishu_verification_token"})
    for key, value in values.items():
        setattr(setting, key, value)
    if payload.smtp_password is not None:
        setting.smtp_password_encrypted = encrypt_secret(request.app.state.fernet, payload.smtp_password)
    if payload.feishu_webhook is not None:
        setting.feishu_webhook_encrypted = encrypt_secret(request.app.state.fernet, payload.feishu_webhook)
    if payload.feishu_secret is not None:
        setting.feishu_secret_encrypted = encrypt_secret(request.app.state.fernet, payload.feishu_secret)
    return setting


@router.get("", response_model=NotificationSettingsResponse)
def get_settings(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _response(_settings(db, user.id), request)


@router.put("", response_model=NotificationSettingsResponse)
def put_settings(payload: NotificationSettingsPatch, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    original = _settings(db, user.id)
    version = setting_version(original)
    verifier = _verifier(request)
    base_version = verifier.version(original)
    if payload.settings_version is not None and payload.settings_version != base_version:
        raise AppError("NOTIFICATION_SETTINGS_CHANGED", "通知设置已被修改，请重新加载后再保存", 409)
    setting = _candidate(original, payload, request)
    previous_smtp_target = (original.smtp_host, original.smtp_port)
    _validate_enabled_channels(setting)
    if setting.smtp_host and (
        (setting.email_enabled and not original.email_enabled)
        or (setting.smtp_host, setting.smtp_port) != previous_smtp_target
    ):
        try:
            resolve_smtp_target(
                setting.smtp_host, setting.smtp_port or 25, request.app.state.settings.security,
                timeout=notification_config(request.app.state.settings).dns_timeout_seconds
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
    required_proofs = []
    for channel in CHANNEL_FIELDS:
        changed = verifier.channel_digest(original, channel, request.app.state.fernet) != verifier.channel_digest(setting, channel, request.app.state.fernet)
        newly_enabled = getattr(setting, channel + "_enabled") and not getattr(original, channel + "_enabled")
        if changed or newly_enabled:
            proof = (user.id, channel, getattr(payload, channel + "_verification_token"), _session(request), verifier.channel_digest(setting, channel, request.app.state.fernet), base_version)
            verifier.check(*proof)
            required_proofs.append(proof)
    current = lock_user(db, user.id)
    if current is None or not current.is_active:
        raise AppError("AUTH_INVALID_CREDENTIALS", "用户已停用", 401)
    locked = db.scalar(select(NotificationSetting).where(NotificationSetting.user_id == user.id).with_for_update().execution_options(populate_existing=True))
    if locked is None:
        raise AppError("NOTIFICATION_SETTINGS_NOT_FOUND", "通知配置不存在", 404)
    if setting_version(locked) != version:
        raise AppError("NOTIFICATION_SETTINGS_CHANGED", "通知设置已被修改，请重新加载后再保存", 409)
    # A lock wait or another test can invalidate a previously checked proof.
    for proof in required_proofs:
        verifier.check(*proof)
    for column in NotificationSetting.__table__.columns:
        if column.name not in {"user_id", "updated_at"}:
            setattr(locked, column.name, getattr(setting, column.name))
    locked.updated_at = utc_now()
    db.commit()
    verifier.consume(user.id)
    write_user_log(request.app.state.settings, user_id=user.id, level="INFO", module="notifications", event="notification_settings_updated", request_id=request.state.request_id, message="通知配置已修改")
    return _response(locked, request)


def _test_channel(channel, payload, request, user, db):
    verifier = _verifier(request)
    original = _settings(db, user.id)
    version = verifier.version(original)
    if payload and payload.settings_version is not None and payload.settings_version != version:
        raise AppError("NOTIFICATION_SETTINGS_CHANGED", "通知设置已被修改，请重新加载后再测试", 409)
    candidate = _candidate(original, payload or NotificationSettingsPatch(), request)
    # A channel test never depends on whether another draft channel is complete.
    if channel == "email" and not all((candidate.smtp_host, candidate.smtp_port, candidate.smtp_security, candidate.sender_email, candidate.recipient_email)):
        raise AppError("EMAIL_SETTINGS_INCOMPLETE", "请填写完整的邮件配置后测试", 400)
    if channel == "feishu" and not candidate.feishu_webhook_encrypted:
        raise AppError("FEISHU_SETTINGS_INCOMPLETE", "请填写飞书 Webhook 后测试", 400)
    config = verifier.channel_digest(candidate, channel, request.app.state.fernet)
    user_id = user.id
    # Network I/O uses detached settings and holds neither a row lock nor a DB transaction.
    db.rollback()
    verifier.start(user_id, channel)
    try:
        try:
            (send_test_email if channel == "email" else send_test_feishu)(candidate, request.app.state.fernet, request.app.state.settings)
        except Exception as exc:
            raise _test_error(exc, "邮件" if channel == "email" else "飞书") from exc
        current = lock_user(db, user_id)
        if current is None or not current.is_active:
            raise AppError("AUTH_INVALID_CREDENTIALS", "用户已停用", 401)
        locked = db.scalar(select(NotificationSetting).where(NotificationSetting.user_id == user_id).with_for_update().execution_options(populate_existing=True))
        if locked is None or verifier.version(locked) != version:
            raise AppError("NOTIFICATION_SETTINGS_CHANGED", "测试期间配置已被修改，请重新加载后测试", 409)
        result = verifier.issue(user_id, channel, _session(request), config, version)
        db.rollback()
        write_user_log(request.app.state.settings, user_id=user_id, level="INFO", module="notifications", event="notification_draft_tested", request_id=request.state.request_id, message="通知配置测试通过")
        return result if payload is not None else Response(status_code=204)
    finally:
        verifier.finish(user_id, channel)


@router.post("/test-email")
def test_email(request: Request, payload: NotificationSettingsPatch | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _test_channel("email", payload, request, user, db)


@router.post("/test-feishu")
def test_feishu(request: Request, payload: NotificationSettingsPatch | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _test_channel("feishu", payload, request, user, db)


def _test_error(exc, channel):
    failure = classify_error(exc)
    message = "发送结果未知，请先检查是否收到消息，避免重复发送" if failure.unknown else f"测试{channel}发送失败：{failure.code}"
    return AppError(failure.code, message, 400)
