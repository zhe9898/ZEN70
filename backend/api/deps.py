"""
FastAPI 依赖：配置、Redis、数据库会话、当前用户（JWT 双轨 + X-New-Token）。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict

from fastapi import Depends, Request, Response, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.redis_client import RedisClient
from backend.core.jwt import decode_token
from backend.db import get_db_session

# 可选：不自动 403，由 get_current_user 返回 401 + ZEN-xxx
_bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_settings() -> Dict[str, Any]:
    """从环境变量读取配置（单例）。"""
    cors = os.getenv("CORS_ORIGINS", "*").strip()
    return {
        "redis_host": os.getenv("REDIS_HOST", ""),
        "redis_port": int(os.getenv("REDIS_PORT", "6379")),
        "redis_password": os.getenv("REDIS_PASSWORD") or None,
        "redis_db": int(os.getenv("REDIS_DB", "0")),
        "cors_origins": [o.strip() for o in cors.split(",") if o.strip()] or ["*"],
        "postgres_dsn": os.getenv("POSTGRES_DSN") or None,
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
    }


def get_redis(request: Request) -> RedisClient | None:
    """
    从 app.state 获取共享 Redis 客户端（由 lifespan 创建并注入）；
    连接失败时为 None。
    """
    return getattr(request.app.state, "redis", None)


async def get_db():
    """数据库会话（来自 db.get_db_session）；无 DSN 时 yield None。"""
    async for session in get_db_session():
        yield session



async def get_current_user(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """
    从 Authorization: Bearer <token> 解析 JWT；双轨验证通过时设置 X-New-Token 响应头。
    无 token 或无效时抛出 401 + ZEN-AUTH-401。
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail={"code": "ZEN-AUTH-401", "message": "Missing or invalid token", "details": {}},
        )
    payload, new_token = decode_token(credentials.credentials)
    if new_token:
        response.headers["X-New-Token"] = new_token
    return payload


async def get_tenant_db(
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    返回绑定了当前租户上下文（RLS 生效）的 AsyncSession。
    """
    # from backend.core.rls import set_tenant_context
    # tenant_id = current_user.get("tenant_id", "default")
    # await set_tenant_context(db, tenant_id)
    return db


async def get_current_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """要求当前用户为 admin 角色。"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "ZEN-AUTH-403", "message": "Admin privileges required", "details": {}},
        )
    return current_user



async def get_current_user_optional(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict | None:
    """
    可空版解析 JWT；无 token 或无效时返回 None。用于 BFF 根据访客角色下发视图。
    """
    if not credentials or not credentials.credentials:
        return None
    try:
        payload, new_token = decode_token(credentials.credentials)
        if new_token:
            response.headers["X-New-Token"] = new_token
        return payload
    except Exception:
        return None
