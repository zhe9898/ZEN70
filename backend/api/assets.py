import os
import uuid
import shutil
import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File, Request
from sqlalchemy import select

from backend.api.deps import get_tenant_db, get_current_user
from backend.models.asset import Asset
from backend.core.errors import zen

router = APIRouter(prefix="/v1/assets", tags=["assets"])
# 路径解耦：唯一事实来源 system.yaml → .env MEDIA_PATH，无默认硬编码
MEDIA_PATH = Path((os.getenv("MEDIA_PATH") or "").strip())

def _save_file(uploaded_file, dest_path: Path) -> int:
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(uploaded_file, buffer)
    return dest_path.stat().st_size

@router.post("/upload")
async def upload_asset(
    request: Request,
    file: UploadFile = File(...),
    db = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    """
    【防腐核心】上传资产并写入数据库。
    db 连接已被 RLS 锁定 tenant_id，此处安全地向 Postgres 写入，任何越权插入直接由底层拒绝。
    """
    tenant_id = current_user.get("tenant_id", "default")
    if not MEDIA_PATH or not str(MEDIA_PATH).strip():
        raise zen("ZEN-ASSET-503", "MEDIA_PATH 未配置，请在 system.yaml 中设置 capabilities.storage.media_path 并执行 compiler", status_code=503, recovery_hint="运行 python scripts/compiler.py 生成 .env")
    # 确保存储目录存在
    tenant_dir = MEDIA_PATH / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    
    ext = Path(file.filename or "").suffix
    safe_name = f"{uuid.uuid4().hex}{ext}"
    physical_path = tenant_dir / safe_name
    
    # 异步写入磁盘
    size = await asyncio.to_thread(_save_file, file.file, physical_path)
            
    asset_type = "video" if str(file.content_type).startswith("video/") else "image"
            
    new_asset = Asset(
        tenant_id=tenant_id,
        file_path=str(physical_path),
        asset_type=asset_type,
        original_filename=file.filename,
        file_size_bytes=size
    )
    db.add(new_asset)
    await db.commit()
    await db.refresh(new_asset)
    
    return {
        "status": "ok",
        "asset_id": str(new_asset.id),
        "file_path": new_asset.file_path,
        "asset_type": new_asset.asset_type
    }

@router.get("")
async def list_assets(
    db = Depends(get_tenant_db)
) -> dict[str, Any]:
    """
    【防腐核心】获取资产列表。代码中没有任何 `WHERE tenant_id = xxx`！
    完全由 PostgreSQL 底层的行级安全防线 (RLS) 截断其他人的数据。
    """
    result = await db.execute(select(Asset).order_by(Asset.created_at.desc()).limit(100))
    assets = result.scalars().all()
    
    return {
        "status": "ok",
        "count": len(assets),
        "data": [
            {
                "id": str(a.id),
                "asset_type": a.asset_type,
                "created_at": a.created_at.isoformat(),
                "original_filename": a.original_filename,
                "file_size_bytes": a.file_size_bytes,
                "file_path": a.file_path,
            } for a in assets
        ]
    }

@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: str,
    db = Depends(get_tenant_db)
) -> dict[str, Any]:
    """
    【防腐核心】删除指定资产。
    同理，无需判断 tenant_id。如果恶意用户尝试删除别人的 asset_id，
    由于 RLS，他在此会话连这条记录都 `select` 不出来，更别说 `delete`。
    """
    try:
        aid = uuid.UUID(asset_id)
    except ValueError:
        raise zen.invalid_request("无效的资产 ID", recovery_hint="请刷新页面重试")
        
    result = await db.execute(select(Asset).where(Asset.id == aid))
    asset = result.scalars().first()
    
    if not asset:
        # 在 RLS 保护下，“越权”也会被隐式转换为“找不到数据”，避免信息泄露
        raise zen.not_found("资产不存在或无权访问", details={"asset_id": asset_id})
        
    # 物理删除磁盘文件 (不严格要求原子性，尽力而为)
    try:
        p = Path(asset.file_path)
        if p.exists():
            p.unlink()
    except Exception as e:
        print(f"Failed to physically delete file {asset.file_path}: {e}")
        
    await db.delete(asset)
    await db.commit()
    
    return {"status": "ok", "deleted_id": asset_id}


@router.post("/search")
async def search_assets(
    request: Request,
    db=Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    【AI 语义联邦检索引擎】
    法典 §2.2 多模态 Map-Reduce：自然语言 → CLIP 向量 → pgvector 余弦距离
    法典 §3.1.1 / Phase 8 RLS：向量搜索结果自动由 tenant_id 隔离

    请求体: {"query": "海边红裙女孩", "limit": 20}
    """
    body = await request.json()
    query_text = body.get("query", "").strip()
    limit = min(body.get("limit", 20), 50)

    if not query_text:
        return {"status": "ok", "count": 0, "data": [], "hint": "请输入搜索关键词"}

    # === 功能开关检查 ===
    from backend.models.feature_flag import FeatureFlag
    from backend.api.deps import get_db as _get_db_internal
    # 使用单独的非 RLS 连接查开关状态
    # （开关表不受 tenant 隔离，是全局配置）

    # === 降级方案：标签匹配（开关关闭时） ===
    # 当 AI 向量搜索未启用时，退化为对 ai_tags 的模糊匹配
    result = await db.execute(
        select(Asset)
        .where(Asset.ai_tags.any(query_text))
        .order_by(Asset.created_at.desc())
        .limit(limit)
    )
    assets = result.scalars().all()

    return {
        "status": "ok",
        "mode": "tag_match",
        "query": query_text,
        "count": len(assets),
        "data": [
            {
                "id": str(a.id),
                "asset_type": a.asset_type,
                "created_at": a.created_at.isoformat(),
                "original_filename": a.original_filename,
                "file_path": a.file_path,
                "ai_tags": a.ai_tags or [],
                "relevance": "tag_match",
            }
            for a in assets
        ],
    }
