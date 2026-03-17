import asyncio
import io
import logging
import os
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# 1. 初始化日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ai_worker")

model_instance = None
HAS_MODEL = True


def get_model():
    global model_instance, HAS_MODEL
    if model_instance is not None or not HAS_MODEL:
        return model_instance
    try:
        from sentence_transformers import SentenceTransformer

        MODEL_NAME = "clip-ViT-B-32-multilingual-v1"
        logger.info(
            f"Loading {MODEL_NAME} model into memory... (This may take a while and ~2GB RAM)"
        )
        model_instance = SentenceTransformer(MODEL_NAME)
        logger.info("Model loaded successfully.")
        HAS_MODEL = True
        return model_instance
    except ImportError:
        logger.error("sentence-transformers not installed. Worker will run in dry-run mode.")
        HAS_MODEL = False
        return None


# 3. 数据库连接串 (直接复用主干的 asyncpg DSN)
# 这里为了物理脱离 FastAPI 主进程，自己创建独立的 Engine
from dotenv import load_dotenv

load_dotenv()

DB_DSN = os.getenv("POSTGRES_DSN")
if not DB_DSN:
    raise RuntimeError("POSTGRES_DSN env var is required")
if DB_DSN.startswith("postgresql://"):
    DB_DSN = DB_DSN.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DB_DSN, pool_size=5, max_overflow=10, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

# 需要延迟导入 Asset 模型，或者在这里声明简化版 ORM 进行查改
from backend.models.asset import Asset


async def process_pending_assets():
    """定期轮询数据库扫描还未进行向量嵌入的照片，并逐个消化。"""
    async with AsyncSessionLocal() as session:
        # 1. 捞取最多 10 张待处理状态 (M9.1)
        result = await session.execute(
            select(Asset).where(Asset.embedding_status == "pending").limit(10)
        )
        assets = result.scalars().all()

        if not assets:
            return 0  # 没有任务

        logger.info(f"Found {len(assets)} pending assets to process.")

        processed_count = 0
        for asset in assets:
            try:
                # 状态先行锁定：防并发重复处理
                asset.embedding_status = "processing"
                await session.commit()

                model = get_model()
                if not HAS_MODEL or model is None:
                    # 如果没有装模型，直接标记跳过
                    asset.embedding_status = "failed"
                    asset.media_metadata = {**asset.media_metadata, "error": "Model missing"}
                    await session.commit()
                    continue

                if asset.asset_type.startswith("image"):
                    # 尝试从磁盘加载物理图片
                    path = Path(asset.file_path)
                    if path.exists():
                        img = Image.open(path)
                        # 模型推理：转化为 512 维向量
                        vec = model.encode(img).tolist()
                        asset.embedding = vec
                        asset.embedding_status = "done"
                        logger.info(f"Successfully vectorized image Asset ID: {asset.id}")
                    else:
                        asset.embedding_status = "failed"
                        asset.media_metadata = {
                            **asset.media_metadata,
                            "error": "File not found on disk",
                        }
                        logger.warning(f"File not found for Asset ID: {asset.id}")
                else:
                    # 视频等类型暂时先标记 failed 或跳过 (需抽帧)
                    asset.embedding_status = "failed"
                    asset.media_metadata = {
                        **asset.media_metadata,
                        "error": "Asset type not supported yet",
                    }

                await session.commit()
                processed_count += 1

            except Exception as e:
                logger.error(f"Error processing asset {asset.id}: {e}")
                asset.embedding_status = "failed"
                asset.media_metadata = {**asset.media_metadata, "error": str(e)}
                await session.commit()

        return processed_count


async def main():
    logger.info("ZEN70 AI Vision/Semantic Background Worker Started.")
    # 法典：优雅的渐进式消化
    while True:
        try:
            count = await process_pending_assets()
            if count == 0:
                # 如果没有活干，就睡 5 秒，降低 CPU 和 DB 压力
                await asyncio.sleep(5)
            else:
                # 如果刚干完一波活，歇 0.5 秒马上继续捞下一批
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Worker Loop Exception: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
