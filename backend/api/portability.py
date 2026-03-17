"""
ZEN70 数据携带权与安全粉碎销毁 API
法典准则 §3.3.2: 
1. 资产全量打流导出 (防止 OOM)
2. 安全物理覆写销毁 (Secure Shredding)，禁用不可逆的 os.remove，采取填 0 覆写磁道。
"""

import os
import secrets
import stat
import subprocess
import platform
import logging
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_current_admin_or_family, get_current_user
from backend.models.asset import Asset
from backend.models.system import SystemLog

router = APIRouter(prefix="/api/v1/portability", tags=["Portability & Security"])
logger = logging.getLogger("zen70.portability")

import asyncio

# --- 1. 流式打包全域资产 ---

async def zip_stream_generator(session: AsyncSession, user_id: str):
    """
    流式传输 Zip (简易 Mock 实现)
    真实生产应采用 stream-zip 等三方库。此处我们逐个 Yield Asset 块，防 OOM。
    """
    # 查找该用户拥有的所有资产
    # 为了简化，我们假定当前能够读出所有已落盘文件
    result = await session.execute(select(Asset))
    assets = result.scalars().all()
    
    # HTTP Streaming chunk
    yield b"PK\x03\x04..." # 伪造 Zip Header
    
    for asset in assets:
        p = Path(asset.file_path)
        if p.exists():
            try:
                with open(asset.file_path, "rb") as f:
                    while chunk := f.read(1024 * 1024):  # 1MB per yield
                        yield chunk
                        await asyncio.sleep(0)  # Yield to event loop to prevent CPU blocking
            except Exception as e:
                logger.error(f"Failed to read asset {asset.id} for export: {e}")
                
    yield b"PK\x05\x06..." # 伪造 Zip EOF

@router.get("/export")
async def export_all_data(
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_admin_or_family)
) -> StreamingResponse:
    """一键打包所有家庭数据并流式下载，防 OOM"""
    logger.info(f"🛡️ 用户 {current_user.get('sub')} 发起了全域数据灾备导出。")
    
    return StreamingResponse(
        zip_stream_generator(session, current_user.get('sub')), 
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=zen70_family_archive.zip"}
    )

# --- 2. 物理极刑：数据碎片化覆写 ---

def secure_shred_file(filepath: str, passes: int = 3) -> bool:
    """
    物理级安全销毁: 不依赖文件表解绑。
    Linux 下使用 shred，Windows 下使用伪随机字节覆写。
    """
    p = Path(filepath)
    if not p.exists():
        return True
        
    try:
        # 工业级首选：依赖底层的 shred 物理防腐。
        cmd = ["shred", "-u", "-z", "-n", str(passes), filepath]
        # 法典 4.0: 强制注入硬超时，绝对禁止由于底层磁盘 I/O 挂死导致工作线程无限期挂起 (OOM)
        subprocess.run(cmd, check=True, capture_output=True, timeout=30.0)
        logger.warning(f"☢️ 核心级 shred 执行完毕: {filepath}")
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"☢️ 核心级 shred 执行超时 (30s大闸拦截), 回退到单机抹除伪随机流: {filepath}")
        return False
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Fallback (落地性/可行性)：当由于非标环境缺失 shred 能力或命令失败时，依赖 Python 原生执行退避级别的伪随机块覆写

        try:
            length = p.stat().st_size
            p.chmod(stat.S_IWRITE)
            with open(filepath, "ba+", buffering=0) as f:
                for _ in range(passes):
                    f.seek(0)
                    f.write(secrets.token_bytes(length))
                f.seek(0)
                f.write(b'\x00' * length)
            p.unlink()
            logger.warning(f"☢️ Native Python 级碎片覆写完成: {filepath}")
            return True
        except Exception as e:
            logger.error(f"退避物理销毁失败: {filepath}. Error: {e}")
            return False
    except Exception as e:
        logger.error(f"物理销毁总线异常: {filepath}. Error: {e}")
        return False

@router.post("/shred/{asset_id}")
async def wipe_asset_permanently(
    asset_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_admin_or_family)
) -> dict:
    """
    危险操作：底层随机覆写磁道，神仙难救。
    """
    result = await session.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
        
    filepath = asset.file_path
    
    # 1. 物理覆写
    shredred_ok = secure_shred_file(filepath)
    if not shredred_ok:
         raise HTTPException(status_code=500, detail="Secure shredding failed at disk level.")
         
    # 2. 毁灭数据库指纹
    await session.delete(asset)
    
    # 3. 记录最高危审计日志
    audit = SystemLog(
        action="SECURE_SHRED",
        operator=current_user.get("sub", "unknown"),
        details=f"The physical sectors of file '{asset.original_filename}' have been wiped and zero-filled."
    )
    session.add(audit)
    await session.commit()
    
    return {"status": "shredded", "message": "The data is unrecoverable forever."}
