"""
ZEN70 异步数据库连接与会话工厂。

使用 SQLAlchemy 2.0 + asyncpg；POSTGRES_DSN 需为 postgresql://...，此处自动转为 postgresql+asyncpg。
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models.user import Base

_DSN = os.getenv("POSTGRES_DSN") or ""
# postgresql://... -> postgresql+asyncpg://...
_ASYNC_DSN = _DSN.replace("postgresql://", "postgresql+asyncpg://", 1) if _DSN else ""

if _ASYNC_DSN:
    _engine = create_async_engine(
        _ASYNC_DSN,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=os.getenv("SQL_ECHO", "").lower() in ("1", "true"),
    )
    _async_session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
else:
    _engine = None
    _async_session_factory = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """供 FastAPI Depends 使用的异步会话；无 DSN 时 yield None 并提前返回（调用方需处理）。"""
    if _async_session_factory is None:
        yield None  # type: ignore[misc]
        return
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    创建所有表（仅开发/初始化用）。
    生产环境表结构变更必须 100% 依赖 Alembic 增量迁移，禁止直连 DDL。
    """
    if _engine is None:
        return
    async with _engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)

    # (ZEN70) 强行下发并行级安全底座
    from backend.core.rls import apply_rls_policies

    async with _async_session_factory() as session:
        await apply_rls_policies(session)
