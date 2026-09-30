from __future__ import annotations

import hashlib
import secrets
import time
from pathlib import Path
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken


password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def load_or_create_fernet_key(path: str | Path) -> Fernet:
    key_path = Path(path)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        if key_path.stat().st_mode & 0o777 != 0o600:
            raise ValueError(f"encryption key file permissions must be 0600: {key_path}")
        key = key_path.read_bytes().strip()
        try:
            fernet = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid encryption key file: {key_path}") from exc
    else:
        key = Fernet.generate_key()
        key_path.write_bytes(key + b"\n")
        key_path.chmod(0o600)
        fernet = Fernet(key)
    return fernet


def encrypt_secret(fernet: Fernet, value: str | None) -> str | None:
    if value is None:
        return None
    return fernet.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(fernet: Fernet, value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return fernet.decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("unable to decrypt stored secret") from exc


class LoginFailureLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300, max_keys: int = 4096):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._attempts: dict[str, list[float]] = {}
        self._lock = Lock()

    def allowed(self, key: str, max_attempts: int | None = None) -> bool:
        now = time.monotonic()
        with self._lock:
            attempts = [timestamp for timestamp in self._attempts.get(key, []) if now - timestamp < self.window_seconds]
            if attempts:
                self._attempts[key] = attempts
            else:
                self._attempts.pop(key, None)
            self._prune_if_needed()
            return len(attempts) < (max_attempts or self.max_attempts)

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            attempts = [timestamp for timestamp in self._attempts.get(key, []) if now - timestamp < self.window_seconds]
            attempts.append(now)
            self._attempts[key] = attempts
            self._prune_if_needed()

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def _prune_if_needed(self) -> None:
        if len(self._attempts) <= self.max_keys:
            return
        oldest_key = min(
            self._attempts,
            key=lambda item: self._attempts[item][-1],
        )
        self._attempts.pop(oldest_key, None)
