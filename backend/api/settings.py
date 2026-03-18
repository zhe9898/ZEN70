"""
ZEN70 系统设置路由 (Settings, Feature Flags, AI Model Config)
法典 §2.3.1: 协议驱动 UI 动态生成
法典 §2.2.3: 设备探针与硬件解耦 — 严禁硬编码模型
法典 §4.4.1: 基于角色的视图管控
"""

import datetime
import logging
import os
import platform
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

from backend.api.deps import get_current_user, get_db
from backend.models.feature_flag import (
    AVAILABLE_MODELS,
    DEFAULT_CONFIGS,
    DEFAULT_FLAGS,
    FeatureFlag,
    SystemConfig,
)

router = APIRouter(prefix="/v1/settings", tags=["settings"])
logger = logging.getLogger("zen70.settings")


async def _ensure_defaults(db: Any) -> None:
    """首次启动时自动写入预置开关 + 系统配置（幂等）"""
    for flag in DEFAULT_FLAGS:
        existing = await db.execute(select(FeatureFlag).where(FeatureFlag.key == flag.key))
        if existing.scalars().first() is None:
            db.add(
                FeatureFlag(
                    key=flag.key,
                    enabled=flag.enabled,
                    description=flag.description,
                    category=flag.category,
                )
            )
    for cfg in DEFAULT_CONFIGS:
        existing = await db.execute(select(SystemConfig).where(SystemConfig.key == cfg.key))
        if existing.scalars().first() is None:
            db.add(
                SystemConfig(
                    key=cfg.key,
                    value=cfg.value,
                    description=cfg.description,
                )
            )
    await db.commit()


# =========================================================================
# 功能开关 CRUD
# =========================================================================


@router.get("/flags")
async def list_flags(
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """获取功能开关列表。Admin 全量，非 Admin 只看已启用的。"""
    await _ensure_defaults(db)
    result = await db.execute(select(FeatureFlag).order_by(FeatureFlag.category))
    flags = result.scalars().all()
    role = current_user.get("role", "family")

    data = []
    for f in flags:
        if role != "admin" and not f.enabled:
            continue
        data.append(
            {
                "key": f.key,
                "enabled": f.enabled,
                "description": f.description,
                "category": f.category,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            }
        )
    return {"status": "ok", "count": len(data), "data": data}


@router.put("/flags/{key}")
async def toggle_flag(
    key: str,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """【Admin Only】切换功能开关状态。"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅指挥官可修改功能开关")

    result = await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))
    flag = result.scalars().first()
    if not flag:
        raise HTTPException(status_code=404, detail=f"未知的功能开关: {key}")

    new_state = not flag.enabled
    await db.execute(update(FeatureFlag).where(FeatureFlag.key == key).values(enabled=new_state, updated_at=datetime.datetime.utcnow()))
    await db.commit()
    logger.info(f"功能开关 [{key}] 已{'启用' if new_state else '禁用'} by {current_user.get('username', 'unknown')}")

    return {
        "status": "ok",
        "key": key,
        "enabled": new_state,
        "message": f"{'✅ 已启用' if new_state else '⛔ 已禁用'}: {flag.description}",
    }


# =========================================================================
# 系统配置 CRUD
# =========================================================================


@router.get("/config")
async def list_config(
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """【Admin Only】获取所有系统配置项。"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅指挥官可查看系统配置")
    await _ensure_defaults(db)

    result = await db.execute(select(SystemConfig))
    configs = result.scalars().all()
    return {
        "status": "ok",
        "data": {c.key: {"value": c.value, "description": c.description} for c in configs},
    }


@router.put("/config/{key}")
async def update_config(
    key: str,
    request: Any,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    【Admin Only】修改系统配置项。
    请求体: {"value": "new_value"}
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅指挥官可修改系统配置")

    body = await request.json()
    new_value = body.get("value")
    if new_value is None:
        raise HTTPException(status_code=400, detail="缺少 value 字段")

    await _ensure_defaults(db)
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=404, detail=f"未知的配置项: {key}")

    await db.execute(update(SystemConfig).where(SystemConfig.key == key).values(value=str(new_value), updated_at=datetime.datetime.utcnow()))
    await db.commit()

    logger.info(f"配置项 [{key}] 更新为 [{new_value}] by {current_user.get('username', 'unknown')}")

    return {"status": "ok", "key": key, "value": str(new_value), "message": f"✅ {key} 已更新"}


# =========================================================================
# AI 模型管理 — 基于 Provider Registry 抽象层
# =========================================================================


@router.get("/ai-models")
async def list_available_models(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    【Admin】聚合所有 Provider 的模型列表。
    自动发现 Ollama 已下载模型、vLLM 已加载模型、本地 CLIP 可选模型。
    法典 §2.2.1: 严禁硬编码模型 — 一切从 Provider 动态拉取。
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅指挥官可查看模型列表")

    from backend.core.ai_providers import get_model_registry

    registry = get_model_registry()
    models = await registry.discover_all_models()

    # 按 provider 分组
    grouped: dict[str, list] = {}
    for m in models:
        p = m.get("provider", "unknown")
        grouped.setdefault(p, []).append(m)

    return {"status": "ok", "total": len(models), "by_provider": grouped}


@router.post("/ai-models/scan")
async def scan_models(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    【Admin Only】触发扫描所有 Provider 的已下载模型。
    Ollama: 调用 /api/tags 自动注册已拉取模型。
    vLLM: 调用 /v1/models 自动发现。
    结果实时返回（无缓存），指挥官可在 UI 看到最新状态。
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅指挥官可扫描模型")

    from backend.core.ai_providers import get_model_registry

    registry = get_model_registry()
    models = await registry.discover_all_models()
    health = await registry.health_all()

    return {
        "status": "ok",
        "discovered": len(models),
        "models": models,
        "provider_health": health,
        "message": f"✅ 扫描完成，发现 {len(models)} 个模型",
    }


@router.get("/ai-providers/health")
async def provider_health(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """聚合所有 AI Provider 的健康状态。"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅指挥官可查看 Provider 状态")

    from backend.core.ai_providers import get_model_registry

    registry = get_model_registry()
    return {"status": "ok", "providers": await registry.health_all()}


@router.get("/ai-providers/endpoints")
async def list_provider_endpoints(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    【Admin】获取所有 Provider 端点配置。
    前端设置页据此渲染端口配置表单。
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅指挥官可查看端点配置")

    from backend.core.ai_providers import get_model_registry

    registry = get_model_registry()
    return {"status": "ok", "endpoints": registry.get_all_endpoints()}


@router.put("/ai-providers/{provider}/url")
async def update_provider_url(
    provider: str,
    request: Any,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    【Admin Only】修改 Provider 端点地址。
    请求体: {"url": "http://192.168.1.100:11434"}

    热更新：修改后立即生效，无需重启后端。
    持久化：写入 SystemConfig 表，重启后自动恢复。
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅指挥官可修改端点配置")

    body = await request.json()
    url = body.get("url", "").strip().rstrip("/")

    if not url:
        raise HTTPException(status_code=400, detail="URL 不能为空")

    from backend.core.ai_providers import get_model_registry

    registry = get_model_registry()

    if not registry.update_url(provider, url):
        raise HTTPException(
            status_code=404,
            detail=f"未知 Provider: {provider}。已注册: {list(registry.providers.keys())}",
        )

    # 持久化到 SystemConfig
    config_key = f"provider_url_{provider}"
    await _ensure_defaults(db)
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == config_key))
    existing = result.scalars().first()
    if existing:
        await db.execute(update(SystemConfig).where(SystemConfig.key == config_key).values(value=url, updated_at=datetime.datetime.utcnow()))
    else:
        db.add(
            SystemConfig(
                key=config_key,
                value=url,
                description=f"Provider [{provider}] 端点地址（指挥官配置）",
            )
        )
    await db.commit()

    logger.info(f"Provider [{provider}] 端点更新为 [{url}] by {current_user.get('username', 'unknown')}")

    return {
        "status": "ok",
        "provider": provider,
        "url": url,
        "message": f"✅ {provider} 端点已更新为: {url}",
    }


@router.put("/ai-model")
async def switch_ai_model(
    request: Any,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    【Admin Only】选择默认模型（按用途）。
    请求体: {"capability": "chat|embed|vision", "model_id": "xxx", "provider": "ollama"}

    法典 §2.2.3: 模型选择权归指挥官，代码仅负责路由分发。
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅指挥官可切换模型")

    body = await request.json()
    capability = body.get("capability", "chat").strip()
    model_id = body.get("model_id", "").strip()
    provider = body.get("provider", "").strip()

    if not model_id:
        raise HTTPException(status_code=400, detail="缺少 model_id")

    # 校验 Provider 是否存在
    from backend.core.ai_providers import get_model_registry

    registry = get_model_registry()
    if provider and not registry.get_provider(provider):
        raise HTTPException(
            status_code=400,
            detail=f"未知 Provider: {provider}。已注册: {list(registry.providers.keys())}",
        )

    # 将选定模型写入 SystemConfig
    config_key = f"ai_model_{capability}"
    await _ensure_defaults(db)

    # 检查 config key 是否存在，不存在则创建
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == config_key))
    existing = result.scalars().first()
    if existing:
        await db.execute(
            update(SystemConfig).where(SystemConfig.key == config_key).values(value=f"{provider}:{model_id}", updated_at=datetime.datetime.utcnow())
        )
    else:
        db.add(
            SystemConfig(
                key=config_key,
                value=f"{provider}:{model_id}",
                description=f"默认 {capability} 模型（指挥官选定）",
            )
        )
    await db.commit()

    logger.info(f"AI 模型 [{capability}] 切换为 [{provider}:{model_id}] by {current_user.get('username', 'unknown')}")

    return {
        "status": "ok",
        "capability": capability,
        "model_id": model_id,
        "provider": provider,
        "message": f"✅ {capability} 模型已切换为: {model_id} ({provider})",
    }


# =========================================================================
# 系统信息
# =========================================================================


@router.get("/system")
async def system_info(
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """【Admin Only】获取系统基础信息 + AI Provider 健康状态。"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅指挥官可查看系统信息")

    await _ensure_defaults(db)

    # 读取当前所有 AI 模型配置
    result = await db.execute(select(SystemConfig).where(SystemConfig.key.like("ai_model_%")))
    model_configs = {c.key: c.value for c in result.scalars().all()}

    # Provider 健康状态
    from backend.core.ai_providers import get_model_registry

    registry = get_model_registry()
    provider_health = await registry.health_all()

    # GPU 检测
    gpu_status = "unknown"
    capability_tags = os.getenv("CAPABILITY_TAGS", "")
    if "gpu_nvenc" in capability_tags:
        gpu_status = "available (NVENC)"
    elif Path("/dev/dri/renderD128").exists():
        gpu_status = "available (DRI)"
    else:
        gpu_status = "not_detected"

    # 磁盘用量
    media_path = (os.getenv("MEDIA_PATH") or "").strip()
    disk_info: dict[str, Any] = {
        "path": media_path,
        "status": "not_configured" if not media_path else "unknown",
    }
    try:
        if not media_path:
            raise OSError("MEDIA_PATH not set")
        stat = os.statvfs(media_path)  # type: ignore
        total_gb = (stat.f_blocks * stat.f_frsize) / (1024**3)
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
        disk_info = {
            "path": media_path,
            "total_gb": round(total_gb, 1),
            "free_gb": round(free_gb, 1),
            "usage_pct": round((1 - free_gb / total_gb) * 100, 1) if total_gb > 0 else 0,
        }
    except (OSError, AttributeError):
        disk_info["status"] = "unavailable"

    return {
        "status": "ok",
        "version": "1.60.0",
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "gpu": gpu_status,
        "disk": disk_info,
        "uptime": datetime.datetime.utcnow().isoformat(),
        "ai_models": model_configs,
        "ai_providers": provider_health,
    }
