"""
ZEN70 Redis 状态机访问层。

提供能力矩阵、节点状态、软开关、硬件状态、锁及发布/订阅的统一接口；
键名与频道规范见模块常量。供网关、探针、调度器使用。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional, TypedDict

try:
    import redis.asyncio as redis
    from redis.asyncio import Redis
except ImportError:
    redis = None  # type: ignore
    Redis = None  # type: ignore

# -------------------- 键与频道常量 --------------------
KEY_CAPABILITIES = "capabilities"
KEY_NODE_PREFIX = "cluster:nodes:"
KEY_SWITCH_PREFIX = "switch:"
KEY_HW_PREFIX = "hw:"
KEY_LOCK_PREFIX = "lock:"
KEY_AUTH_CHALLENGE_PREFIX = "auth:challenge:"
CHANNEL_HARDWARE_EVENTS = "hardware:events"
CHANNEL_SWITCH_EVENTS = "switch:events"
CHANNEL_BOARD_EVENTS = "board:events"

# -------------------- 日志（复用集中模块） --------------------
from backend.core.structured_logging import get_logger


# -------------------- 数据结构 (TypedDict) --------------------


class Capability(TypedDict, total=False):
    """单个能力描述。"""
    endpoint: str
    models: Optional[List[str]]
    status: str  # online/offline/unknown
    reason: Optional[str]


class NodeInfo(TypedDict, total=False):
    """节点信息。"""
    node_id: str
    hostname: str
    role: str  # master/worker
    capabilities: List[str]
    resources: Dict[str, Any]
    endpoint: str
    last_seen: float
    load: Dict[str, float]


class SwitchState(TypedDict, total=False):
    """软开关状态。"""
    state: str  # ON/OFF/PENDING
    reason: Optional[str]
    updated_at: float
    updated_by: Optional[str]


class HardwareState(TypedDict, total=False):
    """硬件状态（与探针写入格式一致）。"""
    path: str
    uuid: Optional[str]
    state: str  # online/offline/pending
    timestamp: float
    reason: Optional[str]


# -------------------- Redis 客户端 --------------------


def _node_to_redis(info: NodeInfo) -> Dict[str, str]:
    """将 NodeInfo 转为 Redis HSET 可用的 str 字典。"""
    out: Dict[str, str] = {}
    for k, v in info.items():
        if v is None:
            continue
        if k in ("capabilities", "resources", "load"):
            out[k] = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
        elif k == "last_seen":
            out[k] = str(float(v))
        else:
            out[k] = str(v)
    return out


def _redis_to_node(data: Dict[str, str]) -> NodeInfo:
    """将 Redis HGETALL 结果转为 NodeInfo。"""
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if not v:
            continue
        if k in ("capabilities", "resources", "load"):
            try:
                out[k] = json.loads(v)
            except json.JSONDecodeError:
                out[k] = v
        elif k == "last_seen":
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = 0.0
        else:
            out[k] = v
    return out  # type: ignore


class RedisClient:
    """
    Redis 状态机客户端：能力矩阵、节点、软开关、硬件状态、锁；所有操作带异常捕获与安全默认值。
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        db: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> None:
        h = host or os.getenv("REDIS_HOST")
        if not h:
            raise RuntimeError("REDIS_HOST env var is required")
        self.host = h
        self.port = port if port is not None else int(os.getenv("REDIS_PORT", "6379"))
        self.password = password if password is not None else os.getenv("REDIS_PASSWORD") or None
        self.db = db if db is not None else int(os.getenv("REDIS_DB", "0"))
        self.logger = get_logger("redis_client", request_id)
        self._redis: Optional[Redis] = None

    async def connect(self) -> None:
        """建立连接（使用 redis 内置连接池）。"""
        if redis is None:
            raise RuntimeError("redis package not installed (pip install redis)")
        if self._redis is not None:
            return
        self._redis = redis.Redis(
            host=self.host,
            port=self.port,
            password=self.password,
            db=self.db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            socket_keepalive=True,
        )
        try:
            await self._redis.ping()
            self.logger.info("Connected to Redis")
        except Exception as e:
            self.logger.error(f"Redis connection failed: {e}", exc_info=True)
            self._redis = None
            raise

    async def close(self) -> None:
        """关闭连接。"""
        if self._redis:
            await self._redis.aclose()  # type: ignore[union-attr]
            self._redis = None
            self.logger.info("Redis connection closed")

    async def ping(self) -> bool:
        """健康检查：Redis 可达返回 True。"""
        if not self._redis:
            return False
        try:
            await self._redis.ping()
            return True
        except Exception:
            return False

    def pubsub(self):
        """返回底层 Redis 的 PubSub，用于 SSE 订阅（如 hardware:events, switch:events）。"""
        if not self._redis:
            return None
        return self._redis.pubsub()

    # -------------------- 能力矩阵 --------------------

    async def _retry_once(self, coro, fallback: Any, op_name: str = "op"):
        """关键读操作：失败时重试 1 次（间隔 0.1s），仍失败返回 fallback。"""
        try:
            return await coro()
        except Exception as e:
            self.logger.warning(f"{op_name} failed, retrying once: {e}")
            await asyncio.sleep(0.1)
        try:
            return await coro()
        except Exception as e:
            self.logger.error(f"{op_name} failed after retry: {e}", exc_info=True)
            return fallback

    async def get_capabilities(self) -> Dict[str, Capability]:
        """获取能力矩阵；Redis 不可用或异常时返回空字典（含 1 次重试）。"""
        if not self._redis:
            self.logger.error("Redis not connected")
            return {}

        async def _get():
            data = await self._redis.hgetall(KEY_CAPABILITIES)
            if not data:
                return {}
            result: Dict[str, Capability] = {}
            for key, value in data.items():
                try:
                    result[key] = json.loads(value)
                except json.JSONDecodeError:
                    self.logger.warning(f"Invalid JSON for capability {key}: {value}")
            return result

        return await self._retry_once(_get, {}, "get_capabilities")

    async def set_capability(self, name: str, capability: Capability) -> bool:
        """设置单个能力。"""
        if not self._redis:
            return False
        try:
            await self._redis.hset(KEY_CAPABILITIES, name, json.dumps(capability))
            return True
        except Exception as e:
            self.logger.error(f"Failed to set capability {name}: {e}", exc_info=True)
            return False

    async def delete_capability(self, name: str) -> bool:
        """删除能力。"""
        if not self._redis:
            return False
        try:
            await self._redis.hdel(KEY_CAPABILITIES, name)
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete capability {name}: {e}", exc_info=True)
            return False

    # -------------------- 节点状态 --------------------

    async def register_node(self, node_id: str, info: NodeInfo) -> bool:
        """注册或更新节点信息；设置心跳过期时间。"""
        key = f"{KEY_NODE_PREFIX}{node_id}"
        if not self._redis:
            return False
        try:
            info = dict(info)
            info["last_seen"] = time.time()
            mapping = _node_to_redis(info)
            await self._redis.hset(key, mapping=mapping)
            await self._redis.expire(key, 60)
            return True
        except Exception as e:
            self.logger.error(f"Failed to register node {node_id}: {e}", exc_info=True)
            return False

    async def get_node(self, node_id: str) -> Optional[NodeInfo]:
        """获取节点信息。"""
        key = f"{KEY_NODE_PREFIX}{node_id}"
        if not self._redis:
            return None
        try:
            data = await self._redis.hgetall(key)
            if not data:
                return None
            return _redis_to_node(data)
        except Exception as e:
            self.logger.error(f"Failed to get node {node_id}: {e}", exc_info=True)
            return None

    async def get_all_nodes(self) -> Dict[str, NodeInfo]:
        """获取所有节点。"""
        if not self._redis:
            return {}
        try:
            keys = await self._redis.keys(f"{KEY_NODE_PREFIX}*")
            result: Dict[str, NodeInfo] = {}
            for key in keys:
                nid = key[len(KEY_NODE_PREFIX):] if key.startswith(KEY_NODE_PREFIX) else key.split(":")[-1]
                node = await self.get_node(nid)
                if node:
                    result[nid] = node
            return result
        except Exception as e:
            self.logger.error(f"Failed to get all nodes: {e}", exc_info=True)
            return {}

    async def heartbeat(self, node_id: str, load: Dict[str, float]) -> bool:
        """节点心跳：更新 last_seen 与 load，刷新过期时间。"""
        key = f"{KEY_NODE_PREFIX}{node_id}"
        if not self._redis:
            return False
        try:
            pipe = self._redis.pipeline()
            pipe.hset(key, "last_seen", str(time.time()))
            pipe.hset(key, "load", json.dumps(load))
            pipe.expire(key, 60)
            await pipe.execute()
            return True
        except Exception as e:
            self.logger.error(f"Failed to heartbeat node {node_id}: {e}", exc_info=True)
            return False

    # -------------------- 软开关 --------------------

    async def get_switch(self, name: str) -> Optional[SwitchState]:
        """获取软开关状态；失败时重试 1 次。"""
        key = f"{KEY_SWITCH_PREFIX}{name}"
        if not self._redis:
            return None

        async def _get():
            data = await self._redis.hgetall(key)
            if not data:
                return None
            return {
                "state": data.get("state", ""),
                "reason": data.get("reason"),
                "updated_at": float(data.get("updated_at", 0)),
                "updated_by": data.get("updated_by"),
            }

        return await self._retry_once(_get, None, f"get_switch({name})")

    async def get_all_switches(self) -> Dict[str, SwitchState]:
        """获取所有软开关状态。"""
        if not self._redis:
            return {}
        try:
            keys = await self._redis.keys(f"{KEY_SWITCH_PREFIX}*")
            if not keys:
                return {}
            
            result: Dict[str, SwitchState] = {}
            # 使用 pipeline 批量获取所有开关信息以提升性能
            pipe = self._redis.pipeline()
            for key in keys:
                pipe.hgetall(key)
            results = await pipe.execute()
            
            for key, data in zip(keys, results):
                if data:
                    name = key[len(KEY_SWITCH_PREFIX):] if key.startswith(KEY_SWITCH_PREFIX) else key.split(":")[-1]
                    result[name] = {
                        "state": data.get("state", ""),
                        "reason": data.get("reason"),
                        "updated_at": float(data.get("updated_at", 0)),
                        "updated_by": data.get("updated_by"),
                    }
            return result
        except Exception as e:
            self.logger.error(f"Failed to get_all_switches: {e}", exc_info=True)
            return {}

    async def set_switch(
        self,
        name: str,
        state: str,
        reason: str = "",
        updated_by: str = "system",
    ) -> bool:
        """设置软开关并发布 switch:events。"""
        key = f"{KEY_SWITCH_PREFIX}{name}"
        if not self._redis:
            return False
        try:
            payload: Dict[str, str] = {
                "state": state,
                "reason": reason,
                "updated_at": str(time.time()),
                "updated_by": updated_by,
            }
            event = {"name": name, **payload}
            pipe = self._redis.pipeline()
            pipe.hset(key, mapping=payload)
            pipe.publish(CHANNEL_SWITCH_EVENTS, json.dumps(event))
            await pipe.execute()
            return True
        except Exception as e:
            self.logger.error(f"Failed to set switch {name}: {e}", exc_info=True)
            return False

    # -------------------- 硬件状态 --------------------

    async def get_hardware(self, path: str) -> Optional[HardwareState]:
        """获取硬件状态。"""
        key = f"{KEY_HW_PREFIX}{path}"
        if not self._redis:
            return None
        try:
            data = await self._redis.hgetall(key)
            if not data:
                return None
            hw: HardwareState = {
                "path": data.get("path", path),
                "uuid": data.get("uuid"),
                "state": data.get("state", ""),
                "timestamp": float(data.get("timestamp", 0)),
                "reason": data.get("reason"),
            }
            return hw
        except Exception as e:
            self.logger.error(f"Failed to get hardware {path}: {e}", exc_info=True)
            return None

    async def set_hardware(
        self,
        path: str,
        state: str,
        reason: str = "",
        uuid_val: Optional[str] = None,
    ) -> bool:
        """更新硬件状态并发布 hardware:events。"""
        key = f"{KEY_HW_PREFIX}{path}"
        if not self._redis:
            return False
        try:
            ts = time.time()
            payload: Dict[str, str] = {
                "path": path,
                "uuid": uuid_val or "",
                "state": state,
                "timestamp": str(ts),
                "reason": reason,
            }
            event = dict(payload, timestamp=ts)  # JSON 序列化时 timestamp 为 float
            pipe = self._redis.pipeline()
            pipe.hset(key, mapping=payload)
            pipe.publish(CHANNEL_HARDWARE_EVENTS, json.dumps(event))
            await pipe.execute()
            return True
        except Exception as e:
            self.logger.error(f"Failed to set hardware {path}: {e}", exc_info=True)
            return False

    # -------------------- 锁 --------------------

    async def acquire_lock(self, name: str, ttl: int = 20) -> bool:
        """获取分布式锁（非阻塞）；成功返回 True。"""
        key = f"{KEY_LOCK_PREFIX}{name}"
        if not self._redis:
            return False
        try:
            result = await self._redis.set(key, "locked", nx=True, ex=ttl)
            return result is True
        except Exception as e:
            self.logger.error(f"Failed to acquire lock {name}: {e}", exc_info=True)
            return False

    async def release_lock(self, name: str) -> bool:
        """释放锁。"""
        key = f"{KEY_LOCK_PREFIX}{name}"
        if not self._redis:
            return False
        try:
            await self._redis.delete(key)
            return True
        except Exception as e:
            self.logger.error(f"Failed to release lock {name}: {e}", exc_info=True)
            return False

    async def is_locked(self, name: str) -> bool:
        """检查锁是否存在。"""
        key = f"{KEY_LOCK_PREFIX}{name}"
        if not self._redis:
            return False
        try:
            n = await self._redis.exists(key)
            return n > 0
        except Exception as e:
            self.logger.error(f"Failed to check lock {name}: {e}", exc_info=True)
            return False

    # -------------------- 认证挑战（WebAuthn） --------------------

    async def set_auth_challenge(self, challenge_b64: str, value: str, ttl: int = 300) -> bool:
        """存储认证挑战，用于 register/login 完成时校验。"""
        key = f"{KEY_AUTH_CHALLENGE_PREFIX}{challenge_b64}"
        if not self._redis:
            return False
        try:
            await self._redis.setex(key, ttl, value)
            return True
        except Exception as e:
            self.logger.error(f"Failed to set auth challenge: {e}", exc_info=True)
            return False

    async def get_auth_challenge(self, challenge_b64: str) -> Optional[str]:
        """获取并删除挑战（一次性使用）。"""
        key = f"{KEY_AUTH_CHALLENGE_PREFIX}{challenge_b64}"
        if not self._redis:
            return None
        try:
            value = await self._redis.get(key)
            if value:
                await self._redis.delete(key)
            return value
        except Exception as e:
            self.logger.error(f"Failed to get auth challenge: {e}", exc_info=True)
            return None

    async def incr_with_expire(self, key: str, window_sec: int) -> int:
        """INCR key，首次时设置过期时间，返回递增后的值。"""
        if not self._redis:
            return 0
        try:
            n = await self._redis.incr(key)
            if n == 1:
                await self._redis.expire(key, window_sec)
            return n
        except Exception as e:
            self.logger.error(f"Failed to incr_with_expire {key}: {e}", exc_info=True)
            return 0
