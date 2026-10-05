"""认证与口令安全（JWT + bcrypt）。"""
from __future__ import annotations

import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:  # 非法哈希串
        return False


def create_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": datetime.now(tz=timezone.utc),
        "exp": datetime.now(tz=timezone.utc)
        + timedelta(minutes=settings.jwt_expire_minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_alg)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_alg])
    except jwt.PyJWTError:
        return None
