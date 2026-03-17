"""
ZEN70 物联网设备模型 (Devices)
提供全局无硬编码的强类型物理设备拓扑。
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.user import Base


class Device(Base):
    """
    全屋智能 IoT 设备拓扑节点表。
    遵循系统解耦协议：名称、图标、房间及类别皆需数据库记录，而非代码写死。
    """

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)  # light, sensor, curtain
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    icon: Mapped[str] = mapped_column(String(16), nullable=False)
    room: Mapped[str] = mapped_column(String(64), nullable=False)

    # 指令重试容忍上限，超出将被打入 DLQ
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
