import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure backend module is discoverable by Alembic
# 强制注入项目根目录到 sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

# 尝试加载当前目录上一级的下一级（即项目根目录）的 .env
load_dotenv(root_dir / ".env")

# Set config sqlalchemy.url dynamically
POSTGRES_DSN = os.getenv("POSTGRES_DSN")
if POSTGRES_DSN:
    if POSTGRES_DSN.startswith("postgresql://"):
        POSTGRES_DSN = POSTGRES_DSN.replace("postgresql://", "postgresql+asyncpg://", 1)
    if os.getenv("DB_OFFLINE_LOCAL") == "1":
        # Force rewrite for Windows port-forwarded offline tasks
        POSTGRES_DSN = POSTGRES_DSN.replace("@pgbouncer:5432/", "@localhost:5432/").replace(
            "@postgres:5432/", "@localhost:5432/"
        )
    config.set_main_option("sqlalchemy.url", POSTGRES_DSN)

import backend.models.asset
import backend.models.device
import backend.models.feature_flag
import backend.models.system

# Import all models to ensure they are registered with Base.metadata
from backend.models.user import Base

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


import threading
import time

# 法典 3.5：upgrade head 前必须向 Redis 申请全局互斥锁 DB_MIGRATION_LOCK，防并发 DDL 脑裂
DB_MIGRATION_LOCK_KEY = "zen70:DB_MIGRATION_LOCK"
DB_MIGRATION_LOCK_TIMEOUT = 120  # 初始锁持有时间（秒）


def _watchdog_thread(redis_client, lock, stop_event):
    """守护线程：每 10 秒为迁移锁自动续期，防长耗时 DDL 超时脑裂"""
    while not stop_event.is_set():
        try:
            # PEXPIRE 续期 120 秒
            redis_client.pexpire(lock.name, DB_MIGRATION_LOCK_TIMEOUT * 1000)
        except Exception as e:
            # 仅记录或静默，若 Redis 崩溃，锁终将自然释放
            pass
        # 每隔 10 秒心跳一次
        stop_event.wait(10)


def _acquire_migration_lock() -> "tuple[object, object, threading.Event, threading.Thread] | None":
    """尝试连接 Redis 并获取迁移锁；不可用时返回 None（离线模式可跳过）。"""
    try:
        import redis
    except ImportError:
        return None
    try:
        host = os.environ.get("REDIS_HOST", "redis")
        port = int(os.environ.get("REDIS_PORT", "6379"))
        password = os.environ.get("REDIS_PASSWORD") or None
        user = os.environ.get("REDIS_USER", "default")
        r = redis.Redis(
            host=host,
            port=port,
            password=password,
            username=user if password else None,
            socket_connect_timeout=5,
            decode_responses=True,
        )
        r.ping()
        lock = r.lock(DB_MIGRATION_LOCK_KEY, timeout=DB_MIGRATION_LOCK_TIMEOUT)
        if lock.acquire(blocking=True, blocking_timeout=60):
            # 成功获取后，拉起看门狗
            stop_event = threading.Event()
            watchdog = threading.Thread(
                target=_watchdog_thread, args=(r, lock, stop_event), daemon=True
            )
            watchdog.start()
            return (r, lock, stop_event, watchdog)
        raise RuntimeError("无法在 60s 内获取 DB_MIGRATION_LOCK，可能有其他节点正在执行迁移")
    except Exception:
        if os.getenv("SKIP_DB_MIGRATION_LOCK"):
            return None
        raise


def run_migrations_online() -> None:
    """Run migrations in 'online' mode. 法典 3.5：先获取 Redis 迁移锁及看门狗再执行。"""
    lock_bundle = _acquire_migration_lock()
    try:
        asyncio.run(run_async_migrations())
    finally:
        if lock_bundle is not None:
            _r, lock, stop_event, watchdog = lock_bundle
            try:
                stop_event.set()  # 通知看门狗停转
                watchdog.join(timeout=2.0)
                lock.release()  # type: ignore
            except Exception:
                pass
            try:
                _r.close()  # type: ignore
            except Exception:
                pass


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
