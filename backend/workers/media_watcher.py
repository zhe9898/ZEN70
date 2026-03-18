import asyncio
import logging
import os
from pathlib import Path

import cv2
import redis
from PIL import Image
from sqlalchemy import select
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.db import _async_session_factory
from backend.models.asset import Asset

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("media_watcher")

# 初始化配置
MEDIA_PATH = os.getenv("MEDIA_PATH")
if not MEDIA_PATH:
    MEDIA_PATH = str(Path.cwd() / "media")
MEDIA_PATH = Path(MEDIA_PATH)
MEDIA_PATH.mkdir(parents=True, exist_ok=True)

# Redis 配置 (供污点检测 Toleration 使用)
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")


def get_redis_client():
    try:
        user = os.getenv("REDIS_USER", "default")
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            username=user if REDIS_PASSWORD else None,
            decode_responses=True,
            socket_connect_timeout=2,
        )
    except Exception:
        return None


# 懒加载大模型
model = None
tag_embeddings = None
TAG_LIST = ["笑脸", "宝宝", "家庭聚会", "拥抱", "猫狗宠物", "自然风景", "公路旅行", "室内建筑"]
EMOTION_TAGS = {"笑脸", "家庭聚会", "拥抱", "宝宝"}


def load_ai_model():
    global model, tag_embeddings
    if model is None:
        logger.info("Initializing CLIP Multilingual Model (this may take a while)...")
        from sentence_transformers import SentenceTransformer

        # 使用多语言 CLIP 模型支持中文
        model = SentenceTransformer("clip-ViT-B-32-multilingual-v1")
        tag_embeddings = model.encode(TAG_LIST)
        logger.info("AI Model successfully loaded into memory.")
    return model


def process_image_or_video(file_path: Path, asset_type: str):
    """提取图片或视频的一帧，返回 (图像_RGB_PIL, 向量)"""
    m = load_ai_model()
    img_pil = None

    try:
        if asset_type == "video":
            cap = cv2.VideoCapture(str(file_path))
            if not cap.isOpened():
                raise Exception("Cannot open video")

            # 取位于 1/3 处的帧以避开片头黑屏
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_count // 3))

            ret, frame = cap.read()
            cap.release()
            if not ret:
                raise Exception("Cannot read frame from video")

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(frame_rgb)
        else:
            img_pil = Image.open(file_path).convert("RGB")

        emb = m.encode(img_pil)
        return img_pil, emb.tolist()
    except Exception as e:
        logger.error(f"Failed to process media {file_path}: {e}")
        return None, None


def classify_tags(image_embedding):
    """通过计算 Cosine Similarity 进行 Zero-Shot 标签预测"""
    if image_embedding is None or tag_embeddings is None:
        return [], False

    import numpy as np

    emb = np.array(image_embedding)
    # Cosine similarity
    similarities = np.dot(tag_embeddings, emb) / (np.linalg.norm(tag_embeddings, axis=1) * np.linalg.norm(emb))

    # 选出相似度大于阈值的标签
    THRESHOLD = 0.22
    matched_tags = []
    for idx, score in enumerate(similarities):
        if score > THRESHOLD:
            matched_tags.append(TAG_LIST[idx])

    is_emotion = any(tag in EMOTION_TAGS for tag in matched_tags)
    return matched_tags, is_emotion


async def process_pending_assets():
    """扫描数据库中状态为 pending 的记录，调用大模型并更新"""
    if not _async_session_factory:
        logger.error("Database connection not initialized.")
        return

    while True:
        try:
            # Toleration rejection: 检查系统级污点 (Taint)
            r = get_redis_client()
            if r is not None:
                gpu_state = r.hgetall("hw:gpu")
                if gpu_state and gpu_state.get("taint"):
                    taint = gpu_state["taint"]
                    if "NoSchedule" in taint:
                        logger.warning(f"Taint Active ({taint}). Media watcher yielding execution (Toleration Rejection).")
                        await asyncio.sleep(15)
                        continue

            async with _async_session_factory() as db:
                # 查找未处理资产 (添加 FOR UPDATE SKIP LOCKED 防止多容器节点竞态拉取同一个资源)
                result = await db.execute(select(Asset).where(Asset.embedding_status == "pending").limit(10).with_for_update(skip_locked=True))
                assets = result.scalars().all()

                for asset in assets:
                    logger.info(f"Processing asset {asset.id} ({asset.original_filename})")
                    # 状态变更为 processing防止多实例竞争
                    asset.embedding_status = "processing"
                    await db.commit()

                    physical_path = Path(asset.file_path)
                    if not physical_path.exists():
                        logger.warning(f"File not found: {physical_path}, marking as failed")
                        asset.embedding_status = "failed"
                        await db.commit()
                        continue

                    # 执行模型推断 (放于线程池)
                    img_pil, emb = await asyncio.to_thread(process_image_or_video, physical_path, asset.asset_type)

                    if emb:
                        tags, is_emotion = classify_tags(emb)
                        asset.embedding = emb
                        asset.ai_tags = tags
                        asset.is_emotion_highlight = is_emotion
                        asset.embedding_status = "done"
                        logger.info(f"Asset {asset.id} processed successfully. Tags: {tags}, Emotion: {is_emotion}")
                    else:
                        asset.embedding_status = "failed"

                    await db.commit()

        except Exception as e:
            logger.error(f"Error in processing loop: {e}")

        await asyncio.sleep(5)


class NASDirectoryEventHandler(FileSystemEventHandler):
    """监控 NAS 目录变动，直接写入数据库 (处理从局域网 SMB 放入的裸文件)"""

    def __init__(self, loop):
        self.loop = loop

    def on_created(self, event):
        if event.is_directory:
            return
        self.handle_new_file(Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory:
            return
        self.handle_new_file(Path(event.dest_path))

    def handle_new_file(self, file_path: Path):
        # 防抖：忽略隐藏文件或非媒体文件
        if file_path.name.startswith("."):
            return
        ext = file_path.suffix.lower()
        if ext not in [".jpg", ".jpeg", ".png", ".heic", ".mp4", ".mov", ".avi"]:
            return

        logger.info(f"Detected new raw file injected via NAS/SMB: {file_path}")
        asyncio.run_coroutine_threadsafe(self._insert_to_db(file_path), self.loop)

    async def _insert_to_db(self, file_path: Path):
        # 尝试从路径推断 tenant_id (假设路径格式为 MEDIA_PATH/tenant_id/file)
        try:
            rel = file_path.relative_to(MEDIA_PATH)
            tenant_id = rel.parts[0]
        except Exception:
            tenant_id = "default"

        asset_type = "video" if file_path.suffix.lower() in [".mp4", ".mov", ".avi"] else "image"

        async with _async_session_factory() as db:
            result = await db.execute(select(Asset).where(Asset.file_path == str(file_path)))
            if result.scalars().first():
                return  # 已经存在于数据库

            new_asset = Asset(
                tenant_id=tenant_id,
                file_path=str(file_path),
                asset_type=asset_type,
                original_filename=file_path.name,
                file_size_bytes=file_path.stat().st_size,
                embedding_status="pending",
            )
            db.add(new_asset)
            await db.commit()
            logger.info(f"Injected bare NAS file into database: {file_path.name}")


async def main():
    logger.info("Starting ZEN70 AI Media Watcher Daemon...")
    # 提前在后台线程中慢速加载大模型，避免阻塞启动的即时响应
    asyncio.create_task(asyncio.to_thread(load_ai_model))

    # 启动文件系统防腐监听
    loop = asyncio.get_running_loop()
    observer = Observer()
    observer.schedule(NASDirectoryEventHandler(loop), str(MEDIA_PATH), recursive=True)
    observer.start()
    logger.info(f"Watchdog observing directory: {MEDIA_PATH}")

    # 启动后台处理池
    await process_pending_assets()


if __name__ == "__main__":
    asyncio.run(main())
