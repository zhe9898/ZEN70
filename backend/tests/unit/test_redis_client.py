"""
单元测试：Redis 状态机客户端。

验证能力矩阵、软开关、锁的 CRUD 与发布事件；未连接或异常时返回安全默认值。
需本地 Redis（默认 localhost:6379），否则相关用例跳过。
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

try:
    import pytest_asyncio
except ImportError:
    pytest_asyncio = None

# 仅在可导入时运行异步测试
if pytest_asyncio is None:
    pytestmark = pytest.mark.skip(reason="pytest-asyncio not installed")
else:
    from backend.core.redis_client import (
        Capability,
        NodeInfo,
        RedisClient,
        SwitchState,
    )


async def _redis_available() -> bool:
    """检测 Redis 是否可用。"""
    try:
        client = RedisClient()
        await client.connect()
        await client.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client():
    """已连接并会在测试后关闭的 Redis 客户端。"""
    c = RedisClient(host="localhost", port=6379)
    try:
        await c.connect()
        yield c
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")
    finally:
        await c.close()


# -------------------- 未连接时的降级行为 --------------------


@pytest.mark.asyncio
async def test_not_connected_returns_safe_defaults():
    """未调用 connect 时，读操作返回空/None，写操作返回 False。"""
    with patch.dict(os.environ, {"REDIS_HOST": "localhost"}):
        c = RedisClient()
    assert c._redis is None

    caps = await c.get_capabilities()
    assert caps == {}

    node = await c.get_node("any")
    assert node is None

    nodes = await c.get_all_nodes()
    assert nodes == {}

    sw = await c.get_switch("any")
    assert sw is None

    hw = await c.get_hardware("/mnt/x")
    assert hw is None

    assert await c.set_capability("x", {"endpoint": "http://x", "status": "online"}) is False
    assert await c.set_switch("x", "ON") is False
    assert await c.acquire_lock("x") is False
    assert await c.is_locked("x") is False


# -------------------- 能力矩阵 --------------------


@pytest.mark.asyncio
async def test_capabilities_crud(client: RedisClient):
    """能力矩阵：设置、读取、删除。"""
    cap: Capability = {
        "endpoint": "http://test:8000",
        "models": ["model1"],
        "status": "online",
        "reason": None,
    }
    assert await client.set_capability("test_svc", cap) is True
    caps = await client.get_capabilities()
    assert "test_svc" in caps
    assert caps["test_svc"]["endpoint"] == "http://test:8000"
    assert caps["test_svc"]["status"] == "online"

    assert await client.delete_capability("test_svc") is True
    caps = await client.get_capabilities()
    assert "test_svc" not in caps


# -------------------- 软开关 --------------------


@pytest.mark.asyncio
async def test_switch_set_get(client: RedisClient):
    """软开关：设置后能正确读取。"""
    assert await client.set_switch("test_switch", "ON", reason="test", updated_by="unit") is True
    sw = await client.get_switch("test_switch")
    assert sw is not None
    assert sw["state"] == "ON"
    assert sw["reason"] == "test"
    assert sw["updated_by"] == "unit"
    assert "updated_at" in sw and sw["updated_at"] > 0

    assert await client.set_switch("test_switch", "OFF", reason="off") is True
    sw2 = await client.get_switch("test_switch")
    assert sw2 is not None and sw2["state"] == "OFF"


# -------------------- 锁 --------------------


@pytest.mark.asyncio
async def test_lock_acquire_release(client: RedisClient):
    """锁：获取、检查、释放。"""
    lock_name = "test_lock_redis_client"
    assert await client.acquire_lock(lock_name, ttl=10) is True
    assert await client.is_locked(lock_name) is True
    assert await client.acquire_lock(lock_name, ttl=10) is False  # 已持有
    assert await client.release_lock(lock_name) is True
    assert await client.is_locked(lock_name) is False
    assert await client.release_lock(lock_name) is True  # 重复释放不报错


# -------------------- Redis 故障时的降级 --------------------


@pytest.mark.asyncio
async def test_redis_error_returns_safe_default():
    """Redis 操作抛异常时，返回空/False 而不抛出。"""
    with patch.dict(os.environ, {"REDIS_HOST": "localhost"}):
        c = RedisClient()
    try:
        await c.connect()
    except Exception:
        pytest.skip("Redis not available")
    try:
        with patch.object(c._redis, "hgetall", AsyncMock(side_effect=ConnectionError("mock"))):
            caps = await c.get_capabilities()
            assert caps == {}
        with patch.object(c._redis, "hset", AsyncMock(side_effect=ConnectionError("mock"))):
            ok = await c.set_capability("x", {"endpoint": "http://x", "status": "online"})
            assert ok is False
    finally:
        await c.close()


# -------------------- 节点（可选，依赖 Redis） --------------------


@pytest.mark.asyncio
async def test_register_and_get_node(client: RedisClient):
    """节点注册与获取。"""
    info: NodeInfo = {
        "node_id": "test-node",
        "hostname": "host1",
        "role": "worker",
        "capabilities": ["cpu", "gpu"],
        "resources": {"cpu_cores": 8, "ram_mb": 16384},
        "endpoint": "http://host1:8000",
        "load": {"cpu_percent": 10.0, "gpu_percent": 0.0},
    }
    assert await client.register_node("test-node", info) is True
    node = await client.get_node("test-node")
    assert node is not None
    assert node.get("hostname") == "host1"
    assert node.get("role") == "worker"
    assert node.get("capabilities") == ["cpu", "gpu"]
    assert node.get("resources", {}).get("cpu_cores") == 8
