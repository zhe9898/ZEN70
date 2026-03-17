"""
ZEN70 静默数据腐败巡检守护 (Bit-Rot Detection)
法典准则 §3.2.3:
通过低优先级后台任务，对底层冷数据块进行 SHA-256 哈希比对。
若发现物理扇区数据反转，即刻通过告警通道推送预警以实施数据隔离。
由于本模块低频、低并发且与核心业务隔离，明确允许使用独立 SQLite。
"""

import hashlib
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger("zen70.sentinel.bit_rot")

# 独立于 Postgres，规避高并发锁问题的专属本地哈希基线库
DB_PATH = Path(__file__).parent / "bit_rot_baseline.db"


def init_baseline_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_hashes (
            filepath TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            last_checked REAL NOT NULL,
            size INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def compute_sha256(filepath: str, blocksize: int = 65536) -> Optional[str]:
    """大文件防 OOM 流式哈希计算"""
    hasher = hashlib.sha256()
    try:
        with open(filepath, "rb") as afile:
            buf = afile.read(blocksize)
            while len(buf) > 0:
                hasher.update(buf)
                buf = afile.read(blocksize)
                time.sleep(0)  # Yield CPU to prevent monopolization during large file hashes
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"无法读取文件计算哈希: {filepath} - {e}")
        return None


def check_system_load_safe() -> bool:
    """
    法典要求：仅在核心 CPU 负载低于 10% 时才执行（模拟设定）
    为了开发测试，这里调高阈值为 50%
    """
    cpu_usage = psutil.cpu_percent(interval=1)
    if cpu_usage > 50.0:
        logger.info(f"系统当前负载较高 ({cpu_usage}%)，挂起 Bit-Rot 巡检任务。")
        return False
    return True


def scan_and_verify_directory(target_dir: str):
    """递归遍历目标目录，进行状态比对与基线更新"""
    if not check_system_load_safe():
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    corrupted_files = []

    for root, _, files in os.walk(target_dir):
        for name in files:
            filepath = Path(root) / name

            # Skip hidden/system files
            if name.startswith("."):
                continue

            try:
                current_size = filepath.stat().st_size
            except OSError:
                continue

            cursor.execute(
                "SELECT sha256, size FROM file_hashes WHERE filepath = ?", (str(filepath),)
            )
            row = cursor.fetchone()

            if not row:
                # 首次扫描：录入哈希基线
                logger.info(f"➕ 首次发现文件，录入基线: {filepath}")
                file_hash = compute_sha256(str(filepath))
                if file_hash:
                    cursor.execute(
                        "INSERT INTO file_hashes (filepath, sha256, last_checked, size) VALUES (?, ?, ?, ?)",
                        (str(filepath), file_hash, time.time(), current_size),
                    )
            else:
                baseline_hash, baseline_size = row
                # 文件大小如果变了，说明被正常修改或损坏彻底。这里重点查大小一致但哈希变的（即静默位翻转）
                if current_size == baseline_size:
                    current_hash = compute_sha256(str(filepath))
                    if current_hash and current_hash != baseline_hash:
                        logger.critical(f"☢️ [极高危] 静默数据腐败检测触发! 位翻转发生: {filepath}")
                        corrupted_files.append(filepath)
                        # 记录警报（后续通过 alert_manager 触发微信/Push）
                else:
                    # 如果是被主人编辑修改了大小，则更新基线
                    new_hash = compute_sha256(str(filepath))
                    if new_hash:
                        cursor.execute(
                            "UPDATE file_hashes SET sha256 = ?, size = ?, last_checked = ? WHERE filepath = ?",
                            (new_hash, current_size, time.time(), str(filepath)),
                        )

    conn.commit()
    conn.close()

    if corrupted_files:
        logger.critical(
            f"本次巡检发现 {len(corrupted_files)} 个静默腐败文件！需要立即从高可用端或 S3 降级恢复。"
        )
        # TODO: Trigger AlertManager API via httpx or internal call


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    logger.info("启动 ZEN70 静默腐败探针...")
    init_baseline_db()

    # 开发态下，模拟检查当前应用根目录的某个 data 文件夹
    test_dir = Path(__file__).parent.parent / "tests"
    if test_dir.exists():
        scan_and_verify_directory(str(test_dir))
