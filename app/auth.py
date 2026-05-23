from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, Response, status


SESSION_COOKIE = "open_arbitrage_admin"
CAPTCHA_COOKIE = "open_arbitrage_captcha"
ADMIN_LOGIN_REQUIRED_HEADER = "X-Admin-Login-Required"
DEFAULT_CAPTCHA_ALPHABET = "23456789"


@dataclass(slots=True)
class AdminAuthConfig:
    enabled: bool
    username: str
    password: str
    password_hash: str | None
    secret_key: str
    session_ttl_seconds: int
    secure_cookie: bool

    @classmethod
    def from_env(cls) -> "AdminAuthConfig":
        return cls(
            enabled=os.getenv("ADMIN_AUTH_ENABLED", "true").lower() == "true",
            username=os.getenv("ADMIN_USERNAME", "admin"),
            password=os.getenv("ADMIN_PASSWORD", ""),
            password_hash=os.getenv("ADMIN_PASSWORD_HASH") or None,
            secret_key=os.getenv("ADMIN_SECRET_KEY", ""),
            session_ttl_seconds=int(os.getenv("ADMIN_SESSION_TTL_SECONDS", "28800")),
            secure_cookie=os.getenv("ADMIN_SECURE_COOKIE", "false").lower() == "true",
        )


@dataclass(slots=True)
class AdminCaptchaConfig:
    enabled: bool
    ttl_seconds: int
    length: int
    alphabet: str

    @classmethod
    def from_env(cls) -> "AdminCaptchaConfig":
        length = int(os.getenv("ADMIN_CAPTCHA_LENGTH", "5"))
        alphabet = os.getenv("ADMIN_CAPTCHA_ALPHABET", DEFAULT_CAPTCHA_ALPHABET).strip() or DEFAULT_CAPTCHA_ALPHABET
        return cls(
            enabled=os.getenv("ADMIN_CAPTCHA_ENABLED", "true").lower() == "true",
            ttl_seconds=int(os.getenv("ADMIN_CAPTCHA_TTL_SECONDS", "300")),
            length=max(4, min(8, length)),
            alphabet=alphabet,
        )


def verify_admin_credentials(username: str, password: str, config: AdminAuthConfig | None = None) -> bool:
    config = config or AdminAuthConfig.from_env()
    if not secrets.compare_digest(username, config.username):
        return False
    if config.password_hash:
        return secrets.compare_digest(make_password_hash(password, salt_from_hash(config.password_hash)), config.password_hash)
    return bool(config.password) and secrets.compare_digest(password, config.password)


def create_admin_session(username: str, config: AdminAuthConfig | None = None) -> str:
    config = config or AdminAuthConfig.from_env()
    require_secret(config)
    issued_at = str(int(time.time()))
    payload = base64.urlsafe_b64encode(f"{username}:{issued_at}".encode("utf-8")).decode("ascii").rstrip("=")
    signature = sign(payload, config.secret_key)
    return f"{payload}.{signature}"


def validate_admin_session(token: str | None, config: AdminAuthConfig | None = None) -> bool:
    config = config or AdminAuthConfig.from_env()
    if not config.enabled:
        return True
    if not token:
        return False
    try:
        payload, signature = token.split(".", 1)
        if not secrets.compare_digest(signature, sign(payload, config.secret_key)):
            return False
        decoded = base64.urlsafe_b64decode(pad_base64(payload)).decode("utf-8")
        username, issued_at_text = decoded.rsplit(":", 1)
        if not secrets.compare_digest(username, config.username):
            return False
        return time.time() - int(issued_at_text) <= config.session_ttl_seconds
    except Exception:
        return False


def require_admin_api(request: Request) -> None:
    config = AdminAuthConfig.from_env()
    if config.enabled and not validate_admin_session(request.cookies.get(SESSION_COOKIE), config):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required.",
            headers={
                ADMIN_LOGIN_REQUIRED_HEADER: "true",
                "Set-Cookie": expired_admin_cookie_header(),
            },
        )


def set_admin_cookie(response: Response, username: str, config: AdminAuthConfig | None = None) -> None:
    config = config or AdminAuthConfig.from_env()
    response.set_cookie(
        SESSION_COOKIE,
        create_admin_session(username, config),
        max_age=config.session_ttl_seconds,
        httponly=True,
        secure=config.secure_cookie,
        samesite="lax",
        path="/",
    )


def clear_admin_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(SESSION_COOKIE, path="/admin")


def generate_captcha_code(config: AdminCaptchaConfig | None = None) -> str:
    config = config or AdminCaptchaConfig.from_env()
    return "".join(secrets.choice(config.alphabet) for _ in range(config.length))


def create_admin_captcha_challenge(
    answer: str,
    captcha_config: AdminCaptchaConfig | None = None,
    auth_config: AdminAuthConfig | None = None,
) -> str:
    captcha_config = captcha_config or AdminCaptchaConfig.from_env()
    auth_config = auth_config or AdminAuthConfig.from_env()
    require_secret(auth_config)
    issued_at = str(int(time.time()))
    nonce = secrets.token_urlsafe(12)
    digest = captcha_digest(answer, nonce, issued_at, auth_config.secret_key)
    payload = base64.urlsafe_b64encode(f"{nonce}:{issued_at}:{digest}".encode("utf-8")).decode("ascii").rstrip("=")
    signature = sign(payload, auth_config.secret_key)
    return f"{payload}.{signature}"


def validate_admin_captcha(
    answer: str | None,
    token: str | None,
    captcha_config: AdminCaptchaConfig | None = None,
    auth_config: AdminAuthConfig | None = None,
) -> bool:
    captcha_config = captcha_config or AdminCaptchaConfig.from_env()
    auth_config = auth_config or AdminAuthConfig.from_env()
    if not auth_config.enabled or not captcha_config.enabled:
        return True
    if not answer or not token:
        return False
    try:
        payload, signature = token.split(".", 1)
        if not secrets.compare_digest(signature, sign(payload, auth_config.secret_key)):
            return False
        decoded = base64.urlsafe_b64decode(pad_base64(payload)).decode("utf-8")
        nonce, issued_at_text, expected_digest = decoded.rsplit(":", 2)
        if time.time() - int(issued_at_text) > captcha_config.ttl_seconds:
            return False
        actual_digest = captcha_digest(answer, nonce, issued_at_text, auth_config.secret_key)
        return secrets.compare_digest(actual_digest, expected_digest)
    except Exception:
        return False


def set_captcha_cookie(response: Response, answer: str, config: AdminAuthConfig | None = None) -> None:
    config = config or AdminAuthConfig.from_env()
    captcha_config = AdminCaptchaConfig.from_env()
    response.set_cookie(
        CAPTCHA_COOKIE,
        create_admin_captcha_challenge(answer, captcha_config, config),
        max_age=captcha_config.ttl_seconds,
        httponly=True,
        secure=config.secure_cookie,
        samesite="lax",
        path="/admin",
    )


def clear_captcha_cookie(response: Response) -> None:
    response.delete_cookie(CAPTCHA_COOKIE, path="/admin")


def captcha_digest(answer: str, nonce: str, issued_at: str, secret_key: str) -> str:
    normalized = "".join(answer.upper().split())
    return hmac.new(
        secret_key.encode("utf-8"),
        f"captcha:{nonce}:{issued_at}:{normalized}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def expired_admin_cookie_header() -> str:
    return (
        f"{SESSION_COOKIE}=; Max-Age=0; Path=/admin; "
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; SameSite=lax"
    )


def sign(payload: str, secret_key: str) -> str:
    return hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def pad_base64(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode("ascii")


def make_password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 210_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def salt_from_hash(password_hash: str) -> str:
    parts = password_hash.split("$", 2)
    if len(parts) != 3 or parts[0] != "pbkdf2_sha256":
        raise ValueError("Unsupported password hash format.")
    return parts[1]


def require_secret(config: AdminAuthConfig) -> None:
    if config.enabled and len(config.secret_key) < 32:
        raise RuntimeError("ADMIN_SECRET_KEY must be at least 32 characters when admin auth is enabled.")


def auth_status(request: Request) -> dict[str, Any]:
    config = AdminAuthConfig.from_env()
    return {
        "enabled": config.enabled,
        "authenticated": validate_admin_session(request.cookies.get(SESSION_COOKIE), config),
        "username": config.username if config.enabled else "disabled",
    }
