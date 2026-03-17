"""
ZEN70 流媒体中枢路由 (Media Center API)
法典 §4.1.1: BFF 层按角色过滤媒体库，屏蔽敏感内容
法典 §4.2.2: GPU 离线时 CPU 降级预案
"""

import logging
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_current_user

router = APIRouter(prefix="/v1/media", tags=["media"])
logger = logging.getLogger("zen70.media")

JELLYFIN_URL = os.getenv("JELLYFIN_URL", "http://jellyfin:8096")

# 需要 admin 权限才能看到的媒体库名称关键词（BFF 过滤红线）
SENSITIVE_LIBRARY_KEYWORDS = {"adult", "private", "nsfw", "18+", "成人"}


async def _probe_jellyfin() -> dict[str, Any] | None:
    """尝试探活 Jellyfin 引擎，若离线返回 None"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{JELLYFIN_URL}/System/Info/Public")
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.warning(f"Jellyfin 探活失败: {e}")
    return None


@router.get("/status")
async def media_status(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    查询 Jellyfin 是否在线，返回服务状态与版本信息。
    所有角色可见（但展示内容由 BFF 层按角色过滤）。
    """
    info = await _probe_jellyfin()
    if info is None:
        return {
            "status": "offline",
            "message": "流媒体引擎不在线，请检查存储介质与容器状态。",
            "recovery_hint": "请在控制台尝试启动 Jellyfin 容器",
        }

    return {
        "status": "online",
        "server_name": info.get("ServerName", "ZEN70 Media"),
        "version": info.get("Version", "unknown"),
        "startup_wizard_completed": info.get("StartupWizardCompleted", False),
    }


@router.get("/libraries")
async def media_libraries(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    【防腐核心 / BFF 视界折叠】
    获取 Jellyfin 媒体库列表，但由网关层基于 JWT 角色严格过滤：
    - admin / 指挥官：全景模式，看到所有媒体库
    - family：屏蔽名称包含敏感关键词的库
    - child：只暴露明确标记为安全的库
    """
    info = await _probe_jellyfin()
    if info is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ZEN-MEDIA-5001",
                "message": "流媒体引擎离线",
                "recovery_hint": "请检查物理存储是否已接入并尝试重启对应容器",
            },
        )

    # 从 Jellyfin 拉取媒体库元数据
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{JELLYFIN_URL}/Library/VirtualFolders")
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail="无法获取媒体库列表")
            libraries = resp.json()
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="连接流媒体引擎异常")

    role = current_user.get("role", "family")

    # BFF 过滤逻辑
    filtered = []
    for lib in libraries:
        name = lib.get("Name", "").lower()

        if role == "child":
            # 儿童模式：只显示明确包含 "kids" / "children" / "儿童" 的库
            if any(k in name for k in ("kids", "children", "儿童", "动画")):
                filtered.append(_format_library(lib))
        elif role == "family":
            # 家庭模式：排除敏感内容
            if not any(keyword in name for keyword in SENSITIVE_LIBRARY_KEYWORDS):
                filtered.append(_format_library(lib))
        else:
            # admin / commander：全景模式
            filtered.append(_format_library(lib))

    return {
        "status": "ok",
        "count": len(filtered),
        "data": filtered,
    }


def _format_library(lib: dict) -> dict:
    """格式化单个媒体库信息"""
    return {
        "id": lib.get("ItemId", ""),
        "name": lib.get("Name", ""),
        "type": lib.get("CollectionType", "unknown"),
        "locations": lib.get("Locations", []),
    }


@router.post("/transcode/hint")
async def transcode_hint(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    【法典 §4.2.2 GPU 降级预案】
    返回推荐的转码参数。
    当 GPU 离线时，网关根据 CPU 负载决定是否允许软转码或直接拒绝。
    """
    # 读取探针上报的能力标签
    gpu_available = Path("/dev/dri/renderD128").exists() or "gpu_nvenc_v1" in os.getenv(
        "CAPABILITY_TAGS", ""
    )

    if gpu_available:
        return {
            "status": "ok",
            "engine": "hardware",
            "codec": "h264_nvenc",
            "hint": "GPU 硬件加速转码已就绪",
        }

    # CPU 降级 - 检查负载
    try:
        load_avg = os.getloadavg()[0]  # 1 分钟平均负载
        cpu_count = os.cpu_count() or 1
        utilization = load_avg / cpu_count
    except (OSError, AttributeError):
        utilization = 0.5  # Windows 默认中等

    if utilization > 0.8:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ZEN-MEDIA-5002",
                "message": "GPU 离线且 CPU 过载，拒绝转码请求",
                "recovery_hint": "请等待算力恢复或接入 GPU 硬件加速卡",
                "cpu_utilization": round(utilization, 2),
            },
        )

    return {
        "status": "degraded",
        "engine": "software",
        "codec": "libx264",
        "hint": f"GPU 离线，已降级为 CPU 软转码 (当前负载 {utilization:.0%})",
        "cpu_utilization": round(utilization, 2),
    }
