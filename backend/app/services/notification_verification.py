"""Short-lived, process-local proofs for tested notification drafts."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from threading import BoundedSemaphore, Lock
import time

from app.errors import AppError
from app.models import NotificationSetting
from app.security import decrypt_secret

CHANNEL_FIELDS = {
    "email": ("smtp_host", "smtp_port", "smtp_security", "smtp_username", "smtp_password_encrypted", "sender_email", "sender_name", "recipient_email"),
    "feishu": ("feishu_webhook_encrypted", "feishu_secret_encrypted"),
}


class NotificationVerification:
    ttl = 600
    cooldown = 30

    def __init__(self):
        self._key = secrets.token_bytes(32)
        self._lock = Lock()
        self._slots = BoundedSemaphore(4)
        self._attempts = {}
        self._inflight = set()
        self._grants = {}

    def digest(self, values):
        data = json.dumps(values, sort_keys=True, default=str, ensure_ascii=False).encode()
        return hmac.new(self._key, data, hashlib.sha256).hexdigest()

    def version(self, setting):
        return self.digest({c.name: getattr(setting, c.name) for c in NotificationSetting.__table__.columns})

    def channel_digest(self, setting, channel, fernet):
        values = {}
        for field in CHANNEL_FIELDS[channel]:
            value = getattr(setting, field)
            if field.endswith("_encrypted"):
                value = decrypt_secret(fernet, value)
            values[field] = value or None
        return self.digest(values)

    def start(self, user_id, channel):
        now = time.monotonic()
        with self._lock:
            self._attempts = {k: v for k, v in self._attempts.items() if v > now}
            self._grants = {k: v for k, v in self._grants.items() if v[-1] > now}
            key = (user_id, channel)
            if key in self._attempts or key in self._inflight:
                raise AppError("NOTIFICATION_TEST_RATE_LIMITED", "请等待 30 秒后再测试", 429)
            if not self._slots.acquire(blocking=False):
                raise AppError("NOTIFICATION_TEST_BUSY", "测试通道繁忙，请稍后再试", 429)
            self._attempts[key] = now + self.cooldown
            self._inflight.add(key)
            self._grants.pop(key, None)

    def finish(self, user_id, channel):
        with self._lock:
            self._inflight.discard((user_id, channel))
        self._slots.release()

    def issue(self, user_id, channel, session, config, version):
        token = secrets.token_urlsafe(32)
        with self._lock:
            # Bound transient proof storage, not the number of user accounts.
            if len(self._grants) >= 2048:
                self._grants.pop(min(self._grants, key=lambda k: self._grants[k][-1]))
            self._grants[(user_id, channel)] = (token, session, config, version, time.monotonic() + self.ttl)
        return {"verification_token": token, "expires_at": datetime.now(timezone.utc) + timedelta(seconds=self.ttl), "channel": channel}

    def check(self, user_id, channel, token, session, config, version):
        with self._lock:
            grant = self._grants.get((user_id, channel))
            valid = grant is not None and grant[-1] > time.monotonic() and hmac.compare_digest(grant[0].encode(), (token or "").encode()) and grant[1:4] == (session, config, version)
        if not valid:
            raise AppError("NOTIFICATION_TEST_REQUIRED", f"请先测试当前{'邮件' if channel == 'email' else '飞书'}配置，再保存", 400)

    def consume(self, user_id):
        with self._lock:
            for channel in CHANNEL_FIELDS:
                self._grants.pop((user_id, channel), None)
