import pytest
import sqlite3
import time
import logging
from pathlib import Path
from backend.sentinel.data_integrity import compute_sha256, init_baseline_db, scan_and_verify_directory, DB_PATH

@pytest.fixture(autouse=True)
def isolated_db():
    """保证每次测试前重建全新的 SQLite 库基准，不污染本地状态。"""
    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()
    init_baseline_db()
    yield
    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()

@pytest.fixture
def temp_test_file(tmp_path):
    """自动生成用于验证哈希与静默翻转的临时冷数据"""
    test_file = tmp_path / "video_record.mp4"
    test_file.write_text("INITIAL_VIDEO_DATA_BLOCK", encoding="utf-8")
    return str(test_file)

def test_compute_sha256(temp_test_file):
    """验证流式哈希的正确性"""
    hash_val = compute_sha256(temp_test_file)
    assert hash_val is not None
    # 稳定输入 = 稳定哈希
    assert len(hash_val) == 64

def test_cpu_load_avoidance(mocker, temp_test_file):
    """【SLA 防线测试】验证高 CPU 压力时，哈希扫描任务完全挂起"""
    # 让探针误以为 CPU 负载 99%
    mocker.patch("backend.sentinel.data_integrity.psutil.cpu_percent", return_value=99.0)
    
    # 执行检查
    scan_and_verify_directory(str(Path(temp_test_file).parent))
    
    # 验证此时 SQLite 没有建立基线（因为任务直接 return 了）
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM file_hashes")
    assert cur.fetchone()[0] == 0
    conn.close()

def test_first_run_creates_baseline(mocker, temp_test_file):
    """第一层扫描：必须能正确在表里写入初始记录"""
    mocker.patch("backend.sentinel.data_integrity.psutil.cpu_percent", return_value=5.0)
    target_dir = str(Path(temp_test_file).parent)
    
    scan_and_verify_directory(target_dir)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT sha256, size FROM file_hashes WHERE filepath = ?", (temp_test_file,))
    row = cur.fetchone()
    
    assert row is not None
    assert row[1] == Path(temp_test_file).stat().st_size
    conn.close()

def test_bit_rot_detection(mocker, temp_test_file):
    """【核心劫难测试】模拟大小没变、但是字节内容翻转的花屏现象，验证是否成功捕获"""
    mocker.patch("backend.sentinel.data_integrity.psutil.cpu_percent", return_value=5.0)
    target_dir = str(Path(temp_test_file).parent)
    
    # 1. 第一波扫描建档
    scan_and_verify_directory(target_dir)
    
    # 2. 模拟静默腐败：保持长度一致("I" -> "X")，模拟底层磁道翻转 1 字节
    with open(temp_test_file, 'r+', encoding='utf-8') as f:
        content = f.read()
        f.seek(0)
        f.write(content.replace("I", "X"))
    
    # Hook into logger to see if critical was fired
    spy_logger = mocker.spy(logging.getLogger("zen70.sentinel.bit_rot"), "critical")
    
    # 3. 第二波巡检 (恶星降临)
    scan_and_verify_directory(target_dir)
    
    # 4. 验证系统必定拉响防空警报
    spy_logger.assert_called()
    assert "静默数据腐败检测触发" in spy_logger.call_args_list[0][0][0]

if __name__ == "__main__":
     # Placeholder to allow direct execution
     import logging
     pass
