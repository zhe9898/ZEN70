"""
ZEN70 多租户硬隔离控制器 (Row-Level Security)
由 API 层级注入当前 tenant_id，在数据库连接层面锁定查询可见性。
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("zen70.rls")


async def apply_rls_policies(session: AsyncSession):
    """
    系统初始化或表结构创建完毕后执行，启用 PostgreSQL 原生的行级安全。
    只在表创建阶段或者系统启动阶段执行一次。
    """
    try:
        # 对 assets 表启用并强制 RLS（强制连 Table Owner/Superuser 都受限，除非特权关闭）
        await session.execute(text("ALTER TABLE assets ENABLE ROW LEVEL SECURITY;"))
        await session.execute(text("ALTER TABLE assets FORCE ROW LEVEL SECURITY;"))

        # 肃清旧策略
        await session.execute(text("DROP POLICY IF EXISTS tenant_isolation_policy ON assets;"))

        # 建立读写受限的绝对策略
        # 允许所有操作 (ALL)，条件为: tenant_id = current_setting('zen70.current_tenant', true)
        policy_sql = """
        CREATE POLICY tenant_isolation_policy ON assets
        AS PERMISSIVE FOR ALL
        TO PUBLIC
        USING (tenant_id = current_setting('zen70.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('zen70.current_tenant', true));
        """
        await session.execute(text(policy_sql))
        await session.commit()
        logger.info("Database Row-Level Security (RLS) applied for assets.")
    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to apply RLS policy: {e}")
        # 如果不是 Postgres 引擎（如 SQLite 测试），此步会报错，视需求 suppress


async def set_tenant_context(session: AsyncSession, tenant_id: str):
    """
    在单次数据库事务会话开启时，注入当前请求的 tenant_id。
    所有基于此 Session 的 ORM Query 都会因为 RLS 策略被无感知地拦截过滤。
    """
    if not tenant_id:
        tenant_id = "default"  # 防御性回退

    await session.execute(text("SET LOCAL zen70.current_tenant = :tenant"), {"tenant": tenant_id})
