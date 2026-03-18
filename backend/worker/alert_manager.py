"""
ZEN70 跨平台多梯队告警下发 (Multi-tier Alerts)
法典准则 §3.2.3, §3.2.4:
必须对接 Web Push、微信（第三方代理）、Bark（私有）。
此模块接受各种级别警告并向主人手机实施强通知。
"""

import asyncio
import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db, get_settings
from backend.models.system import SystemLog

logger = logging.getLogger("zen70.alert_manager")
router = APIRouter(prefix="/api/v1/alerts", tags=["System Alerts"])


class AlertPayload(BaseModel):
    level: str  # 'info', 'warning', 'critical'
    title: str
    message: str
    source: str = "ZEN70_Sentinel"


async def push_to_bark(bark_url: str, title: str, body: str, level: str):
    """
    推送到 iOS Bark 客户端。
    支持修改通知铃声和徽章。
    """
    if not bark_url:
        return

    url = f"{bark_url.rstrip('/')}/{title}/{body}"
    params = {}
    if level == "critical":
        params["sound"] = "alarm"  # 刺耳报警音
        params["level"] = "timeSensitive"  # 穿透专注模式
        params["icon"] = "https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/png/zen.png"  # 假定的本地图标

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url, params=params)
            res.raise_for_status()
            logger.info(f"⚡ Bark 推送成功: {title}")
    except Exception as e:
        logger.error(f"Bark 推送失败: {e}")


async def push_to_serverchan(sckey: str, title: str, body: str):
    """
    推送到微信 Server酱。
    由于微信强推，适合父母和不装独立 APP 的用户。
    """
    if not sckey:
        return

    url = f"https://sctapi.ftqq.com/{sckey}.send"
    data = {"title": title, "desp": body}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(url, data=data)
            res.raise_for_status()
            logger.info(f"⚡ Server酱(微信) 推送成功: {title}")
    except Exception as e:
        logger.error(f"Server酱推送失败: {e}")


@router.post("/trigger")
async def trigger_alert_endpoint(
    payload: AlertPayload,
    settings: dict = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """触发警报。分为本地审计与外网推送双通道。"""

    # 1. 持久化到安全审计库
    audit = SystemLog(
        action=f"ALERT_{payload.level.upper()}",
        operator=payload.source,
        details=f"[{payload.title}] {payload.message}",
    )
    db.add(audit)
    await db.commit()

    # 低危不推送，仅界面发红点
    if payload.level == "info":
        return {"status": "logged"}

    # 2. 异步发射强提醒网络请求
    tasks = []

    # TODO: 从数据库的系统配置表里读取 Token，而不是环境变量
    bark_cfg = os.environ.get("BARK_URL", "")  # ex: https://api.day.app/yourkey
    sc_cfg = os.environ.get("SERVER_CHAN_KEY", "")

    # 如果是高危情况（例如硬盘腐败、断电），强行穿透两端
    if payload.level in ["warning", "critical"]:
        if bark_cfg:
            tasks.append(push_to_bark(bark_cfg, payload.title, payload.message, payload.level))
        if sc_cfg:
            tasks.append(push_to_serverchan(sc_cfg, payload.title, payload.message))

    if tasks:
        # 不阻塞响应，Fire and Forget
        asyncio.create_task(asyncio.wait(tasks))

    return {"status": "alert_dispatched", "channels": len(tasks)}
