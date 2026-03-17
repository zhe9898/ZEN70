"""
ZEN70 MQTT Frigate Event Worker
法典 §3 智能安防与视觉监控: 监听 Frigate 的 MQTT 事件流，精准捕获人/车/动物入侵帧存入 Asset，触发下游 AI 处理链。

使用方式: python -m backend.worker.mqtt_worker
"""

import asyncio
import base64
import json
import logging
import os
import signal
import sys
from typing import Any
from datetime import datetime
from pathlib import Path

import aiomqtt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import _async_session_factory
from backend.models.asset import Asset
from backend.models.feature_flag import SystemConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [MQTT-WORKER] %(message)s")
logger = logging.getLogger("zen70.mqtt_worker")

MQTT_HOST = os.getenv("MQTT_HOST", "zen70-mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = "frigate/events"

async def get_media_path(session: AsyncSession) -> str:
    result = await session.execute(select(SystemConfig).where(SystemConfig.key == "media_path"))
    config = result.scalar_one_or_none()
    if config and config.value:
         # Try to extract actual path, in settings it's stored as JSON string
         try:
             # SystemConfig stores value as JSON encoded string OR raw string sometimes, Handle both.
             val = json.loads(config.value)
             if isinstance(val, dict) and 'value' in val:
                 return val['value']
             return str(val)
         except json.JSONDecodeError:
             return config.value
    # 路径解耦：fallback 仅来自 env（compiler 从 system.yaml 写入）
    media = (os.getenv("MEDIA_PATH") or "").strip()
    return f"{media}/frigate_snapshots" if media else ""

async def process_event(event_data: dict) -> None:
    """Parse Frigate event and save snapshot to Asset."""
    event_type = event_data.get("type")
    # We care about new or updated events where there is a snapshot
    if event_type not in ("new", "update"):
         return
         
    after = event_data.get("after", {})
    if not after.get("has_snapshot"):
         return
         
    event_id = after.get("id")
    label = after.get("label", "unknown")
    camera = after.get("camera", "unknown")
    
    # We might not get raw base64 in newer frigate versions from MQTT, sometimes we need to fetch from API. 
    # But as per plan, we assume snapshot payload is passed or we just fetch from API: http://frigate:5000/api/events/{id}/snapshot.jpg
    # Let's write the fetch logic just in case.
    # For now, if we have a base64 snapshot in the event (frigate sometimes sends it in a separate topic or if configured), we use it.
    snapshot_b64 = after.get("snapshot")
    
    if not snapshot_b64:
         logger.debug(f"Event {event_id} has no embedded snapshot. Need API fetch (mocking for now).")
         return
         
    try:
        image_data = base64.b64decode(snapshot_b64)
    except Exception as e:
        logger.error(f"Failed to decode base64 snapshot: {e}")
        return

    if _async_session_factory is None:
         logger.error("DB Session Factory not initialized.")
         return
         
    async with _async_session_factory() as session:
        # Avoid duplicate processing for the same event
        existing = await session.execute(select(Asset).where(Asset.media_metadata['frigate_event_id'].astext == event_id))
        if existing.scalar_one_or_none():
             logger.debug(f"Event {event_id} already processed.")
             return
             
        media_root = await get_media_path(session)
        if not media_root:
            logger.warning("MEDIA_PATH not set; skipping frigate snapshot save")
            return
        # We store frigate snapshots under {media_root}/frigate/{camera}/{date}
        today = datetime.utcnow().strftime("%Y-%m-%d")
        dest_dir = Path(media_root) / "frigate" / camera / today
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        file_name = f"{event_id}_{label}.jpg"
        file_path = dest_dir / file_name
        
        # Write to disk
        with open(file_path, "wb") as f:
             f.write(image_data)
             
        # Insert into Asset
        asset = Asset(
             tenant_id="admin_tenant", # Frigate events are globally admin owned for now
             file_path=str(file_path),
             asset_type="image",
             original_filename=file_name,
             file_size_bytes=len(image_data),
             media_metadata={
                 "source": "frigate",
                 "camera": camera,
                 "label": label,
                 "score": after.get("top_score"),
                 "frigate_event_id": event_id
             },
             embedding_status="pending"
        )
        session.add(asset)
        await session.commit()
        logger.info(f"📸 捕获 Frigate 抓拍: {camera} -> {label} (ID: {event_id}), 触发 CLIP 处理链")

async def main_loop() -> None:
    logger.info(f"🚀 MQTT Worker 启动, 尝试连接 mosquitto: {MQTT_HOST}:{MQTT_PORT}")
    
    # We use infinite retry for the worker
    while True:
        try:
            async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
                logger.info(f"✅ 成功连接 MQTT Broker，订阅 {MQTT_TOPIC}")
                await client.subscribe(MQTT_TOPIC)
                
                async for message in client.messages:
                    try:
                        payload_str = message.payload.decode("utf-8")
                        event_data = json.loads(payload_str)
                        await process_event(event_data)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse MQTT payload as JSON.")
                    except Exception as e:
                        logger.error(f"Error processing MQTT message: {e}")
        except aiomqtt.MqttError as e:
            logger.error(f"MQTT连接错误: {e}. 5秒后重试...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Worker 循环异常: {e}. 5秒后重试...")
            await asyncio.sleep(5)

def _handle_signal(signum: int, frame: Any) -> None:
    logger.info(f"收到信号 {signum}，Worker 优雅退出...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    asyncio.run(main_loop())
