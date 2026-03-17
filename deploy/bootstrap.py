#!/usr/bin/env python3
"""
ZEN70 点火脚本 (Bootstrap)。

在裸金属或全新环境中完成：环境基线预检、多源 Git 拉取配置、
调用配置编译器生成运行时配置、基于 docker-compose 启动容器阵列；
支持离线模式 (--offline) 与回滚 (--rollback)。
所有日志为结构化 JSON，携带 X-Request-ID。仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

# -------------------- 常量 --------------------
DEFAULT_PORTS = [80, 443, 53]
MIN_DISK_GB = 10
GIT_SOURCES = [
    "https://github.com/your-org/zen70-config.git",
    "https://gitee.com/your-org/zen70-config.git",
    "http://git.zen70.internal/zen70-config.git",
]
BACKUP_CURRENT = "current"

# -------------------- 结构化日志 --------------------


class JsonFormatter(logging.Formatter):
    """
    自定义 JSON 日志格式化器，对齐 Loki 与任务 0.1 的 config-compiler。

    每条日志为单行 JSON：timestamp（UTC）、level、logger、caller、message、
    X-Request-ID；异常时包含 exception 字段。
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "caller": f"{record.pathname}:{record.lineno}",
            "message": record.getMessage(),
            "X-Request-ID": getattr(record, "request_id", None),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(
    request_id: Optional[str] = None,
    verbose: bool = False,
) -> logging.LoggerAdapter:
    """
    配置全局 JSON 日志并返回带 request_id 的 LoggerAdapter。

    Args:
        request_id: 请求追踪 ID；None 时自动生成 UUID。
        verbose: True 时设为 DEBUG，否则 INFO。

    Returns:
        绑定 request_id 的 LoggerAdapter。
    """
    base_logger = logging.getLogger("bootstrap")
    base_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    base_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    base_logger.addHandler(handler)
    if request_id is None:
        request_id = str(uuid.uuid4())
    return logging.LoggerAdapter(base_logger, {"request_id": request_id})


logger: Optional[logging.LoggerAdapter] = None


# -------------------- 环境预检 --------------------


def check_docker() -> Tuple[bool, str]:
    """
    检查 Docker 是否可用（docker info 成功即视为可用）。

    Returns:
        (是否可用, 错误信息；可用时为空串)。
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return True, ""
        return False, result.stderr or "docker info failed"
    except FileNotFoundError:
        return False, "Docker not found (docker not in PATH)"
    except subprocess.TimeoutExpired:
        return False, "docker info timed out"
    except Exception as e:
        return False, str(e)


def _get_port_check_output() -> Optional[str]:
    """获取端口监听列表，跨平台：Linux 用 ss，Windows 用 netstat。"""
    if platform.system() == "Windows":
        try:
            r = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None
    try:
        r = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def check_ports(ports: List[int]) -> Tuple[bool, str]:
    """
    检查指定端口是否已被占用。

    Args:
        ports: 待检查端口列表（如 80, 443, 53）。

    Returns:
        (全部未被占用为 True, 错误信息；占用时列出端口及说明)。
    """
    out = _get_port_check_output()
    if not out:
        return True, "Could not determine port usage (ss/netstat unavailable), skipping"

    occupied: List[int] = []
    for port in ports:
        needle = f":{port}"
        for line in out.splitlines():
            if needle in line and ("LISTEN" in line or "LISTENING" in line or "0.0.0.0" in line or "::" in line):
                occupied.append(port)
                break
    if not occupied:
        return True, f"Ports {ports} OK (no conflict)"
    return False, f"Port(s) already in use: {occupied}. Check with ss -tlnp (Linux) or netstat -ano (Windows)."


def check_disk_space(work_dir: Path, min_gb: int = MIN_DISK_GB) -> Tuple[bool, str]:
    """
    检查工作目录所在磁盘可用空间是否 >= min_gb。

    Args:
        work_dir: 工作目录，用于确定盘符（Windows）或分区。
        min_gb: 最小可用空间（GB）。

    Returns:
        (满足为 True, 说明或错误信息)。
    """
    try:
        if platform.system() == "Windows":
            root = Path(work_dir.resolve().drive + "\\")
        else:
            root = Path("/")
        stat = shutil.disk_usage(root)
        free_gb = stat.free // (1024**3)
        if free_gb < min_gb:
            return False, f"Insufficient disk space: {free_gb}GB free (need >= {min_gb}GB)"
        return True, f"Disk space OK: {free_gb}GB free on {root}"
    except Exception as e:
        return False, f"Failed to check disk space: {e}"


def check_kernel_params() -> Tuple[bool, str]:
    """
    检查内核参数（仅 Linux），如 net.core.rmem_max。

    Returns:
        (通过为 True, 说明或警告信息)。Windows 上直接返回通过。
    """
    if platform.system() != "Linux":
        return True, "Kernel params check skipped (non-Linux)"
    path = Path("/proc/sys/net/core/rmem_max")
    try:
        if not path.exists():
            return True, "Kernel rmem_max not found, skipping"
        val = int(path.read_text().strip())
        if val < 212992:
            return False, f"net.core.rmem_max={val}, recommend >= 212992"
        return True, "Kernel parameters OK"
    except Exception as e:
        return False, f"Failed to check kernel params: {e}"


# -------------------- Git 多源拉取 --------------------


def pull_config(
    sources: List[str],
    work_dir: Path,
    repo_dir_name: str = "repo",
    offline: bool = False,
) -> bool:
    """
    从多源拉取配置到工作目录；离线模式下仅校验本地 config 存在。

    拉取逻辑：依次尝试各 source；若 repo_dir 已存在则 git pull，否则 git clone。
    成功后将 repo 内 config/ 与 deploy/ 复制到 work_dir（dirs_exist_ok）。

    Args:
        sources: Git 仓库 URL 列表（主源优先）。
        work_dir: 工作根目录（将在此下创建 repo_dir 并复制 config、deploy）。
        repo_dir_name: 克隆到的子目录名。
        offline: 若为 True，不执行拉取，仅检查 work_dir/config 存在。

    Returns:
        成功为 True，否则 False。
    """
    if offline:
        config_dir = work_dir / "config"
        has_system = (config_dir / "system.yaml").exists()
        confd = config_dir / "conf.d"
        has_fragments = confd.exists() and any(confd.glob("*.yml"))
        if config_dir.exists() and (has_system or has_fragments):
            logger.info("Offline mode: using existing config")
            return True
        logger.error("Offline mode but no local config found (config/system.yaml or config/conf.d/*.yml)")
        return False

    repo_path = work_dir / repo_dir_name
    for source in sources:
        logger.info(f"Attempting to pull from {source}")
        try:
            if repo_path.exists():
                cmd = ["git", "-C", str(repo_path), "pull", "--depth", "1", "origin", "main"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode != 0:
                    cmd_fetch = ["git", "-C", str(repo_path), "fetch", "--depth", "1", "origin", "main"]
                    subprocess.run(cmd_fetch, capture_output=True, timeout=60)
                    subprocess.run(["git", "-C", str(repo_path), "reset", "--hard", "origin/main"], capture_output=True, timeout=10)
            else:
                work_dir.mkdir(parents=True, exist_ok=True)
                cmd = ["git", "clone", "--depth", "1", "--single-branch", "--branch", "main", source, str(repo_path)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    cmd = ["git", "clone", "--depth", "1", source, str(repo_path)]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.warning(f"Pull from {source} failed: {result.stderr or result.stdout}")
                continue

            src_config = repo_path / "config"
            src_deploy = repo_path / "deploy"
            if src_config.exists():
                dst_config = work_dir / "config"
                dst_config.mkdir(parents=True, exist_ok=True)
                for item in src_config.iterdir():
                    dst = dst_config / item.name
                    if item.is_dir():
                        shutil.copytree(item, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dst)
            if src_deploy.exists():
                dst_deploy = work_dir / "deploy"
                dst_deploy.mkdir(parents=True, exist_ok=True)
                for item in src_deploy.iterdir():
                    dst = dst_deploy / item.name
                    if item.is_dir():
                        shutil.copytree(item, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dst)
            logger.info(f"Successfully pulled from {source}")
            return True
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout pulling from {source}")
        except Exception as e:
            logger.warning(f"Exception pulling from {source}: {e}", exc_info=True)
    logger.error("All Git sources failed")
    return False


# -------------------- 配置编译 --------------------


def run_compiler(
    work_dir: Path,
    config_path: Path,
    output_dir: Path,
    validate_only: bool = False,
) -> bool:
    """
    调用 deploy/config-compiler.py 生成 runtime 配置。

    Args:
        work_dir: 项目根目录（用于解析相对路径）。
        config_path: 配置文件或目录（如 config/system.yaml 或 config/）。
        output_dir: 输出目录（如 runtime/）。
        validate_only: 仅验证不生成文件。

    Returns:
        进程返回 0 为 True，否则 False。
    """
    compiler_script = Path(__file__).resolve().parent / "config-compiler.py"
    if not compiler_script.exists():
        logger.error(f"config-compiler.py not found: {compiler_script}")
        return False
    try:
        config_arg = str(config_path.relative_to(work_dir)) if config_path.is_relative_to(work_dir) else str(config_path)
    except ValueError:
        config_arg = str(config_path)
    try:
        out_arg = str(output_dir.relative_to(work_dir)) if output_dir.is_relative_to(work_dir) else str(output_dir)
    except ValueError:
        out_arg = str(output_dir)
    cmd: List[str] = [
        sys.executable,
        str(compiler_script),
        config_arg,
        "--output-dir",
        out_arg,
    ]
    if validate_only:
        cmd.append("--validate")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout:
            for line in result.stdout.splitlines():
                logger.info(line.strip() or " ")
        if result.returncode != 0:
            if result.stderr:
                logger.error(f"Compiler stderr: {result.stderr}")
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error("Config compiler timed out", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Config compiler failed: {e}", exc_info=True)
        return False


# -------------------- 容器操作 --------------------


def _compose_cmd() -> List[str]:
    """返回 docker compose 命令：优先 'docker compose'，否则 'docker-compose'。"""
    try:
        r = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            timeout=5,
        )
        if r.returncode == 0:
            return ["docker", "compose"]
    except Exception:
        pass
    return ["docker-compose"]


def start_containers(compose_file: Path, env_file: Optional[Path] = None) -> bool:
    """
    在 compose 文件所在目录执行 up -d，保证 .env 同目录被加载。

    Args:
        compose_file: docker-compose.yml 路径。
        env_file: 可选 .env 路径；不传则使用 compose 同目录下的 .env。

    Returns:
        成功为 True。
    """
    runtime_dir = compose_file.parent
    compose_name = compose_file.name
    cmd = _compose_cmd() + ["-f", compose_name, "up", "-d"]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(runtime_dir),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.error(f"Failed to start containers: {result.stderr or result.stdout}")
            return False
        logger.info("Containers started successfully")
        return True
    except subprocess.TimeoutExpired:
        logger.error("docker compose up timed out", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Failed to start containers: {e}", exc_info=True)
        return False


def stop_containers(compose_file: Path) -> bool:
    """停止 compose 定义的容器。"""
    runtime_dir = compose_file.parent
    compose_name = compose_file.name
    cmd = _compose_cmd() + ["-f", compose_name, "down"]
    try:
        subprocess.run(cmd, cwd=str(runtime_dir), capture_output=True, timeout=120)
        return True
    except Exception as e:
        logger.warning(f"Stop containers: {e}", exc_info=True)
        return False


def save_backup(runtime_dir: Path, version: str = BACKUP_CURRENT) -> None:
    """将 runtime/.env 和 runtime/docker-compose.yml 复制到 runtime/backups/<version>/。"""
    backup_dir = runtime_dir / "backups" / version
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in (".env", "docker-compose.yml"):
        src = runtime_dir / name
        if src.exists():
            shutil.copy2(src, backup_dir / name)
    logger.info(f"Backup saved to runtime/backups/{version}")


def restore_backup(runtime_dir: Path, version: str) -> bool:
    """从 runtime/backups/<version>/ 恢复 .env 和 docker-compose.yml 到 runtime/。"""
    backup_dir = runtime_dir / "backups" / version
    compose_dst = runtime_dir / "docker-compose.yml"
    if not backup_dir.exists() or not (backup_dir / "docker-compose.yml").exists():
        logger.error(f"Backup not found: runtime/backups/{version}")
        return False
    for name in (".env", "docker-compose.yml"):
        src = backup_dir / name
        if src.exists():
            shutil.copy2(src, runtime_dir / name)
    logger.info(f"Restored runtime from backups/{version}")
    return True


def rollback_to(version: str, runtime_dir: Path) -> bool:
    """
    回滚到指定版本：恢复备份、停止当前容器、再启动。

    Args:
        version: 备份版本名（如 current 或 v1.56.0）。
        runtime_dir: runtime 目录。

    Returns:
        成功为 True。
    """
    logger.info(f"Rolling back to version {version}")
    compose_file = runtime_dir / "docker-compose.yml"
    if not restore_backup(runtime_dir, version):
        return False
    stop_containers(compose_file)
    return start_containers(compose_file)


# -------------------- 主流程 --------------------


def main() -> None:
    """解析参数，执行预检、拉取、编译、启动或回滚。"""
    parser = argparse.ArgumentParser(
        description="ZEN70 点火脚本：环境预检、多源拉取、配置编译、容器启动"
    )
    parser.add_argument("--offline", action="store_true", help="离线模式，跳过 Git 拉取")
    parser.add_argument(
        "--rollback",
        metavar="VERSION",
        help="回滚到指定版本（如 current 或 v1.56.0）",
    )
    parser.add_argument(
        "--config-source",
        nargs="+",
        default=GIT_SOURCES,
        help="Git 源列表（主源优先）",
    )
    parser.add_argument("--verbose", action="store_true", help="输出 DEBUG 日志")
    args = parser.parse_args()

    global logger
    logger = setup_logging(verbose=args.verbose)

    work_dir = Path.cwd().resolve()
    config_dir = work_dir / "config"
    runtime_dir = work_dir / "runtime"

    # ---------- 环境预检 ----------
    logger.info("Starting environment preflight checks")
    ok, msg = check_docker()
    if not ok:
        logger.error(f"Docker check failed: {msg}")
        sys.exit(1)
    logger.info("Docker OK")

    ok, msg = check_ports(DEFAULT_PORTS)
    if not ok:
        logger.error(msg)
        sys.exit(1)
    logger.info(msg)

    ok, msg = check_disk_space(work_dir)
    if not ok:
        logger.error(msg)
        sys.exit(1)
    logger.info(msg)

    ok, msg = check_kernel_params()
    if not ok:
        logger.warning(msg)
    else:
        logger.info(msg)

    # ---------- 回滚模式 ----------
    if args.rollback:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        if not rollback_to(args.rollback, runtime_dir):
            sys.exit(1)
        logger.info("Bootstrap rollback completed successfully")
        return

    # ---------- 拉取配置 ----------
    logger.info("Pulling configuration")
    if not pull_config(args.config_source, work_dir, offline=args.offline):
        sys.exit(1)

    # ---------- 配置编译 ----------
    config_path = config_dir / "system.yaml"
    if not config_path.exists():
        config_path = config_dir
    runtime_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Running config compiler")
    if not run_compiler(work_dir, config_path, runtime_dir):
        sys.exit(1)

    compose_file = runtime_dir / "docker-compose.yml"
    if not compose_file.exists():
        logger.error("docker-compose.yml was not generated in runtime/")
        sys.exit(1)

    # ---------- 启动容器 ----------
    logger.info("Starting containers")
    if not start_containers(compose_file):
        sys.exit(1)

    save_backup(runtime_dir, BACKUP_CURRENT)
    logger.info("Bootstrap completed successfully")


if __name__ == "__main__":
    main()
