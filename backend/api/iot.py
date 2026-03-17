"""
ZEN70 智能家居物联网控制器 (IoT Hub)
法典准则: 全部异步下发 MQTT; 坚决不允许前端直连缓慢的硬件 HTTP 端点.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict
import logging
import time

from backend.api.deps import get_db, get_current_user, get_redis
from backend.core.redis_client import RedisClient
from sqlalchemy.future import select
from backend.models.device import Device

router = APIRouter(prefix="/api/v1/iot", tags=["Smart Home IoT"])
logger = logging.getLogger("zen70.iot")

@router.get("/devices")
async def list_devices(
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    拉取全域智能家居设备列表极其最后已知状态。
    真实数据从 PostgreSQL (唯一事实来源) 获取，状态由 Redis 缓存覆盖。
    """
    result = await db.execute(select(Device).where(Device.is_active == True))
    db_devices = result.scalars().all()
    
    if not db_devices:
        return {"devices": []}
        
    devices = []
    
    # 【性能极速优化】构造 MGET 批量键阵列，消除 O(N) 的网络交互与阻塞惩罚
    redis_keys = [f"zen70:iot:state:{d.id}" for d in db_devices]
    try:
        # 使用底层 Async Redis 客户端的 mget 达到 O(1) 访问
        cached_states = await redis.redis.mget(redis_keys)
    except Exception as e:
        logger.warning(f"Failed to execute MGET pipeline for IoT topologies: {e}")
        cached_states = [None] * len(db_devices)
    
    for idx, d in enumerate(db_devices):
        devices.append({
            "id": d.id,
            "type": d.type,
            "name": d.name,
            "state": cached_states[idx] if cached_states[idx] else "OFF",
            "icon": d.icon,
            "room": d.room
        })
            
    return {"devices": devices}

@router.post("/control")
async def control_device(
    payload: Dict[str, Any],
    request: Request,
    redis: RedisClient = Depends(get_redis),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    接收前端发来的按键事件，并将其投递到 Redis Streams 缓冲池。
    执行 Worker 将捞取执行并实施绝对去重。
    """
    import uuid
    import time
    
    device_id = payload.get("device_id")
    action = payload.get("action")
    
    # 幂等性防护：如果前端带了 command_id 优先使用，否则后端生成
    command_id = payload.get("command_id") or uuid.uuid4().hex
    
    if not device_id or not action:
        raise HTTPException(status_code=400, detail="Missing device_id or action")
        
    # 模拟架构红线：中继层(HA/Z2M)健康度检查与 503 熔断
    # 生产环境中可以通过 `ping` Mosquitto 或 HA 探针实现
    proxy_health = await redis.get("zen70:iot:proxy_health")
    if proxy_health == "OFFLINE":
        logger.warning(f"🔴 [IoT Hub] 拦截指令 {command_id}，中继网络全域掉线 (503 circuit breaker)")
        # 根据 V2.7 红线，返回 503 静默熔断，同时将心跳异常透传给前端
        raise HTTPException(
            status_code=503, 
            detail="IoT Service Proxy (HA/Z2M) is currently offline or under maintenance."
        )

    # 提取全局 TraceID
    trace_id = getattr(request.state, "trace_id", "unknown")

    # 将请求安全地打入 Redis Stream (XADD)，确保送达队列
    stream_key = "zen70:iot:stream:commands"
    msg_data = {
        "command_id": command_id,
        "device_id": device_id,
        "action": action,
        "user_sub": current_user.get("sub", "unknown"),
        "timestamp": str(int(time.time())),
        "trace_id": trace_id
    }
    
    try:
        # XADD 推入消息，限制 Stream 最大长度 10000 防爆库 (应用 approximate=True 极致优化性能)
        await redis.redis.xadd(stream_key, msg_data, maxlen=10000, approximate=True)
        logger.info(f"🟢 [IoT Hub] 控制指令已入列 Streams: {command_id} -> {device_id}={action}")
        
    except Exception as e:
        logger.error(f"Failed to push message to Redis Streams: {e}")
        raise HTTPException(status_code=500, detail="Internal queue engine failure")
        
    # 架构 V2.7 红线：
    # 绝对禁止在此处（网关层）做 optimistic 乐观更新 UI 或推送 SSE！
    # 前端的 UI 变化必须严苛地等待设备执行完电机操作后，由 worker 从 MQTT 收到确认报文并发送。
    
    return {"status": "enqueued", "command_id": command_id}
