"""
ZEN70 媒体资产模型 (Assets)
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Boolean, DateTime, Enum, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.user import Base


class Asset(Base):
    """
    多模态媒体资产表。
    启用 RLS (Row-Level Security) 进行租户硬隔离。
    """

    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # 文件存储相对路径（基地址在 system.yaml 的 media_path）
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)

    # 资产类型 (如 image, video, document)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, default="image")

    # 用于存放 EXIF、AI 视觉标签、人脸聚类等无结构化元数据
    media_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=True, default=dict)

    # 原始文件名
    original_filename: Mapped[str] = mapped_column(String(256), nullable=True)

    # 大小 (bytes)
    file_size_bytes: Mapped[int] = mapped_column(nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # =========================================================================
    # AI 语义联邦字段 (Phase 9)
    # =========================================================================

    # 512 维 CLIP 语义向量 (pgvector)
    # 注意: 需要 CREATE EXTENSION IF NOT EXISTS vector; 在 DB 中预先执行
    embedding: Mapped[Any] = mapped_column(Vector(512), nullable=True)

    # AI 自动打的语义标签 (如 ["风景", "海滩", "人物"])
    ai_tags: Mapped[list] = mapped_column(ARRAY(String), nullable=True, default=list)

    # 情感高光时刻标记 (Elderly/Family Dashboard 使用)
    is_emotion_highlight: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    # 向量提取状态: pending / processing / done / failed
    embedding_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)

    __table_args__ = (
        # 法典 1.4/2.1.3: 默认采用构建速度快、内存开销小的 IVFFlat 索引。运维依据监控动态切 HNSW。
        Index(
            "ix_asset_embedding",
            embedding,
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
