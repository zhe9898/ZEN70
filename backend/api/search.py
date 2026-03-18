"""
ZEN70 跨模态 AI 语义搜索引擎
法典 §3 智能安防与视觉监控: 提供自然语言搜索视频/快照的端点
"""

import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.models.asset import Asset

logger = logging.getLogger("search_api")

# Lazy-load semantic model to save RAM until a search is actually performed
semantic_model = None


def get_semantic_model():
    global semantic_model
    if semantic_model is None:
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Lazy-loading CLIP model for semantic search...")
            semantic_model = SentenceTransformer("clip-ViT-B-32-multilingual-v1")
        except ImportError:
            logger.error("Missing sentence-transformers. Semantic search is disabled.")
            return None
    return semantic_model


router = APIRouter(prefix="/api/v1/search", tags=["AI Search"])


@router.get("/semantic")
async def semantic_search(
    q: str = Query(..., description="自然语言查询，如 '穿红衣服踩单车的人'"),
    limit: int = Query(16, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    法典要求: 用户可以通过自然语言直接检索物理世界发生的监控事件。
    依托 PostgreSQL pgvector 扩展及 IVFFlat 索引执行向量近似最近邻搜索 (ANN)。
    """
    model = get_semantic_model()
    if not model:
        return {"query": q, "results": [], "error": "AI embedding model not loaded down at server"}

    # 1. 文本转为 512 维向量 (投递到线程池，防止阻塞 FastAPI 异步主循环，符合现代高并发工程学)
    encoded = await run_in_threadpool(model.encode, q)
    query_vector = encoded.tolist()

    # 2. 从数据库中执行高效向量检索
    # 注意: SQL 查询已由 deps.get_db 的 RLS policy 进行租户隔离
    stmt = select(Asset).where(Asset.embedding_status == "done").order_by(Asset.embedding.cosine_distance(query_vector)).limit(limit)

    result = await db.execute(stmt)
    assets = result.scalars().all()

    return {
        "query": q,
        "results": [
            {
                "id": str(a.id),
                "file_path": a.file_path,
                "original_filename": a.original_filename,
                "asset_type": a.asset_type,
                "ai_tags": a.ai_tags,
                "created_at": a.created_at.isoformat(),
                "metadata": a.media_metadata,
            }
            for a in assets
        ],
    }


@router.get("/emotion")
async def get_emotion_highlights(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    专门为长辈与妻子准备的“情感相册”流端点。
    只抓取含有高光特征 (is_emotion_highlight=True) 的物理录像切片。
    """
    stmt = select(Asset).where(Asset.is_emotion_highlight == True).order_by(Asset.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    assets = result.scalars().all()

    return {
        "results": [
            {
                "id": str(a.id),
                "file_path": a.file_path,
                "ai_tags": a.ai_tags,
                "created_at": a.created_at.isoformat(),
            }
            for a in assets
        ]
    }
