"""
ZEN70 API v1 路由：能力矩阵、软开关、SSE 事件流。
"""

from __future__ import annotations

import asyncio
import asyncio.subprocess

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from backend.api.deps import get_redis
from backend.api.models import CapabilityResponse, SwitchStateResponse
from backend.core.redis_client import RedisClient, CHANNEL_HARDWARE_EVENTS, CHANNEL_SWITCH_EVENTS, CHANNEL_BOARD_EVENTS
from backend.api import board

router = APIRouter(prefix="/api/v1", tags=["v1"])
router.include_router(board.router)


@router.get(
    "/capabilities",
    response_model=dict[str, CapabilityResponse],
    summary="获取能力矩阵",
)
async def get_capabilities(
    redis: RedisClient | None = Depends(get_redis),
) -> dict:
    """返回当前所有服务能力（从 Redis 读取）。Redis 不可用或异常时返回空字典（乐观放行）。"""
    if redis is None:
        return {}
    try:
        return await redis.get_capabilities()
    except Exception:
        return {}


import os
import json

@router.get(
    "/switches",
    response_model=dict[str, SwitchStateResponse],
    summary="获取所有软开关状态",
)
async def get_all_switches(
    redis: RedisClient | None = Depends(get_redis),
) -> dict:
    """批量获取所有软开关状态，前端用于初始化控制面板。"""
    if redis is None:
        return {}
    
    # 从环境变量(由 compiler.py 注入)解析可用的开关及其物理容器映射，实现后端驱动前端
    switch_map_str = os.getenv("SWITCH_CONTAINER_MAP", "{}")
    try:
        switch_map = json.loads(switch_map_str)
    except json.JSONDecodeError:
        switch_map = {}

    # Redis 中获取所有的当前状态
    switches_data = await redis.get_all_switches()
    results = {}

    # 优先展示 system.yaml 配置定义的可用开关，如果 Redis 无状态则补全为 OFF
    for name, container_name in switch_map.items():
        switch = switches_data.get(name, {})
        raw_state = (switch.get("state") or "OFF").upper()
        state = raw_state if raw_state in ("ON", "OFF", "PENDING") else "OFF"
        try:
            updated_at = float(switch.get("updated_at", 0))
        except (TypeError, ValueError):
            updated_at = 0.0
            
        results[name] = SwitchStateResponse(
            state=state,
            reason=switch.get("reason"),
            updated_at=updated_at,
            updated_by=switch.get("updated_by") or "system",
            label=f"🎯 架构资源 [{name}] ({container_name})"
        )
        
    # 对于在 Redis 中存在但不在 system.yaml 映射中的废弃开关也展示出来（可能需要清理）
    for name, switch in switches_data.items():
        if name not in results:
            raw_state = (switch.get("state") or "OFF").upper()
            state = raw_state if raw_state in ("ON", "OFF", "PENDING") else "OFF"
            try:
                updated_at = float(switch.get("updated_at", 0))
            except (TypeError, ValueError):
                updated_at = 0.0
            results[name] = SwitchStateResponse(
                state=state,
                reason=switch.get("reason"),
                updated_at=updated_at,
                updated_by=switch.get("updated_by") or "system",
                label=f"孤立状态 [{name}]"
            )

    return results


@router.get(
    "/switches/{name}",
    response_model=SwitchStateResponse,
    summary="获取单个软开关状态",
)
async def get_switch(
    name: str,
    redis: RedisClient | None = Depends(get_redis),
) -> SwitchStateResponse:
    """返回指定软开关状态；不存在时返回默认 OFF。"""
    if redis is None:
        return SwitchStateResponse(state="OFF", updated_at=0.0, updated_by="system")
    switch = await redis.get_switch(name)
    if not switch:
        return SwitchStateResponse(state="OFF", updated_at=0.0, updated_by="system")
    raw_state = (switch.get("state") or "OFF").upper()
    state = raw_state if raw_state in ("ON", "OFF", "PENDING") else "OFF"
    try:
        updated_at = float(switch.get("updated_at", 0))
    except (TypeError, ValueError):
        updated_at = 0.0
    return SwitchStateResponse(
        state=state,
        reason=switch.get("reason"),
        updated_at=updated_at,
        updated_by=switch.get("updated_by") or "system",
    )


from pydantic import BaseModel
class SwitchToggleRequest(BaseModel):
    state: str

@router.post(
    "/switches/{name}",
    response_model=SwitchStateResponse,
    summary="手动触发功能软开关并执行物理熔断/拉起",
)
async def toggle_switch(
    name: str,
    req: SwitchToggleRequest,
    redis: RedisClient | None = Depends(get_redis),
) -> SwitchStateResponse:
    """
    更新软开关状态，同时针对底层特定容器(Jellyfin, Ollama, Frigate)
    下发物理 docker pause/unpause 指令，强制释放系统 CPU 资源。
    """
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis不可用，无法执行总线广播")

    new_state = req.state.upper()
    if new_state not in ("ON", "OFF"):
        raise HTTPException(status_code=400, detail="Invalid state, use ON or OFF")

    # TODO: 后续应增加 JWT RBAC 鉴权，目前假定有权限
    await redis.set_switch(name, new_state, updated_by="manual_override", reason="User manual toggle")

    # ZEN70 1.1: Web网关通过 Redis pub/sub 与拥有 docker.sock 权限的底层探针通信
    # 我们不在网关层直接执行 subprocess (受制于 read_only 和 cap_drop)，而是发布变更事件
    import json
    payload = json.dumps({"switch": name, "state": new_state})
    pubsub = redis.pubsub()
    # redis-py 在 FastApi 这里的 pubsub 可能只用于订阅，如果是发布，可以直接 redis._client.publish
    try:
        await redis._client.publish(CHANNEL_SWITCH_EVENTS, payload)
    except Exception as e:
        # 如果 Redis 临时断联，静默回退，前端依然能拿到写入缓存的状态
        pass

    return await get_switch(name, redis)



@router.get(
    "/events",
    summary="SSE 事件流",
)
async def sse_events(
    request: Request,
    redis: RedisClient | None = Depends(get_redis),
):
    """
    订阅硬件状态变更与软开关事件，以 Server-Sent Events 推送。
    频道：hardware:events、switch:events。
    """
    if redis is None:
        return JSONResponse(
            status_code=503,
            content={
                "code": "ZEN-SSE-5001",
                "message": "Redis not available",
                "recovery_hint": "Wait for bus ready and retry; do not loop",
                "details": {},
            },
        )
    pubsub = redis.pubsub()

    async def event_generator():
        try:
            await pubsub.subscribe(CHANNEL_HARDWARE_EVENTS, CHANNEL_SWITCH_EVENTS, CHANNEL_BOARD_EVENTS)
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    if getattr(request, "is_disconnected", None) and callable(request.is_disconnected):
                        if request.is_disconnected():
                            break
                    message = await asyncio.wait_for(
                        pubsub.get_message(timeout=1.0, ignore_subscribe_messages=True),
                        timeout=2.0,
                    )
                    if message and message.get("type") == "message":
                        channel = message.get("channel", "")
                        data = message.get("data", "{}")
                        yield f"event: {channel}\ndata: {data}\n\n"
                    else:
                        yield ": heartbeat\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                except asyncio.CancelledError:
                    break
                except Exception:
                    # 静默降级：异常时发送心跳保持连接，避免未捕获异常导致流中断
                    yield ": heartbeat\n\n"
        finally:
            try:
                await pubsub.unsubscribe(CHANNEL_HARDWARE_EVENTS, CHANNEL_SWITCH_EVENTS, CHANNEL_BOARD_EVENTS)
            except Exception:
                pass
            try:
                await pubsub.aclose()
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
