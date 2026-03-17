"""
ZEN70 API 请求/响应 Pydantic 模型 (v2)。

统一错误码、健康检查、能力矩阵、软开关等结构。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = Field(..., description="healthy / unhealthy")
    version: str = Field(default="1.56.0", description="API 版本")
    services: Dict[str, str] = Field(default_factory=dict, description="依赖服务状态")


class ErrorResponse(BaseModel):
    """统一错误响应（ZEN-xxx 错误码）。契约含 recovery_hint（V2.0）。"""

    code: str = Field(..., description="错误码，如 ZEN-INT-5000")
    message: str = Field(..., description="用户可读说明")
    recovery_hint: Optional[str] = Field(default=None, description="恢复建议，供前端展示")
    details: Optional[Dict[str, Any]] = Field(default=None, description="附加信息")


class CapabilityResponse(BaseModel):
    """单个能力描述。"""

    endpoint: str = ""
    models: Optional[List[str]] = None
    status: str = Field(..., description="online / offline / unknown")
    reason: Optional[str] = None


class SwitchStateResponse(BaseModel):
    """软开关状态。"""

    state: str = Field(..., description="ON / OFF / PENDING")
    reason: Optional[str] = None
    updated_at: float = 0.0
    updated_by: str = "system"
    label: Optional[str] = Field(default=None, description="UI展示用的动态名称")
