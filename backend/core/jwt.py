"""
ZEN70 JWT 签发与双轨验证。

环境变量：JWT_SECRET_CURRENT、JWT_SECRET_PREVIOUS、JWT_ACCESS_TOKEN_EXPIRE_MINUTES。
验证时优先 CURRENT，失败则尝试 PREVIOUS；PREVIOUS 通过时签发新令牌（由调用方通过 X-New-Token 返回）。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

import jwt
from fastapi import HTTPException, status

ALGORITHM = "HS256"
_IS_PROD = os.getenv("ZEN70_ENV", "").lower() == "production"
_CURRENT = os.getenv("JWT_SECRET_CURRENT") or os.getenv("JWT_SECRET") or ("" if _IS_PROD else "change-me-in-production")
_PREVIOUS = os.getenv("JWT_SECRET_PREVIOUS") or None
_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))

if _IS_PROD and not _CURRENT:
    raise RuntimeError("JWT_SECRET_CURRENT or JWT_SECRET must be set in production (ZEN70_ENV=production)")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    *,
    use_current_secret: bool = True,
) -> str:
    """签发 access token；默认使用 JWT_SECRET_CURRENT。"""
    to_encode = data.copy()
    if expires_delta is not None:
        expire = _now() + expires_delta
    else:
        expire = _now() + timedelta(minutes=_EXPIRE_MINUTES)
    to_encode["exp"] = expire
    to_encode["iat"] = _now()
    secret = _CURRENT if use_current_secret else _PREVIOUS or _CURRENT
    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)


def decode_token(token: str) -> Tuple[dict[str, Any], Optional[str]]:
    """
    验证 JWT，支持双轨：先 CURRENT，失败再 PREVIOUS。
    返回 (payload, new_token)。
    若用 PREVIOUS 验证成功，new_token 为用 CURRENT 签发的新令牌；否则为 None。
    """
    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "ZEN-AUTH-401", "message": "Missing or invalid token", "details": {}},
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 先尝试当前密钥
    try:
        payload = jwt.decode(token, _CURRENT, algorithms=[ALGORITHM])

        # 法典 1.6: 双轨无感轮转 (超过 50% 寿命自动签发新 Token)
        exp = payload.get("exp")
        iat = payload.get("iat")
        if exp and iat:
            current_timestamp = _now().timestamp()
            lifespan = exp - iat
            if (current_timestamp - iat) > (lifespan / 2):
                new_token = create_access_token(
                    {k: v for k, v in payload.items() if k not in ("exp", "iat", "nbf")},
                    use_current_secret=True,
                )
                return payload, new_token

        return payload, None
    except jwt.InvalidTokenError:
        pass
    # 再尝试旧密钥
    if _PREVIOUS:
        try:
            payload = jwt.decode(token, _PREVIOUS, algorithms=[ALGORITHM])
            new_token = create_access_token(
                {k: v for k, v in payload.items() if k not in ("exp", "iat", "nbf")},
                use_current_secret=True,
            )
            return payload, new_token
        except jwt.InvalidTokenError:
            pass
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "ZEN-AUTH-401", "message": "Invalid or expired token", "details": {}},
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_access_token_expire_seconds() -> int:
    """返回 access token 有效期（秒），供响应 expires_in。"""
    return _EXPIRE_MINUTES * 60
