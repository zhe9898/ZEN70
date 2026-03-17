#!/usr/bin/env python3
"""
ZEN70 自动化基座验真脚本 (遵循 T-02 规范)
支持直接运行或作为模块导入调用。
智能轮询健康状态、日志扫描、Docker 重试。
"""
import re
import sys
import time
from typing import List

try:
    import docker
except ImportError:
    docker = None

PROJECT_LABEL = "com.docker.compose.project=zen70"
MAX_WAIT = 60
CHECK_INTERVAL = 2
FATAL_PATTERN = re.compile(
    r"(FATAL|Permission denied|panic|address already in use)",
    re.IGNORECASE,
)


def get_docker_client(retries: int = 3, delay: int = 2):  # type: ignore
    """创建 Docker 客户端，带重试机制。"""
    if docker is None:
        print("[ERROR] 未安装 docker 包，请 pip install docker")
        return None
    for attempt in range(retries):
        try:
            return docker.from_env()
        except Exception as e:
            print(f"[WARN] 连接 Docker 失败 (尝试 {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None


def wait_for_containers_ready(client, project_label: str, timeout: int = MAX_WAIT) -> bool:
    """
    等待项目内所有容器进入健康/运行状态。
    返回 True 表示所有容器就绪，False 表示超时或失败。
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        containers = client.containers.list(all=True, filters={"label": project_label})
        if not containers:
            print("[ERROR] 未找到任何项目容器")
            return False

        all_ready = True
        for c in containers:
            c.reload()
            status = c.status
            health = c.attrs.get("State", {}).get("Health", {}).get("Status")
            if health:
                ready = health == "healthy"
                state_desc = f"health={health}"
            else:
                ready = status == "running"
                state_desc = f"status={status}"

            if not ready:
                all_ready = False
                print(f"[WAIT] 容器 {c.name} 未就绪 ({state_desc})")

        if all_ready:
            return True
        time.sleep(CHECK_INTERVAL)

    print(f"[ERROR] 等待容器就绪超时 ({timeout}秒)")
    return False


def scan_container_logs(container) -> List[str]:
    """扫描容器最近 50 行日志中的致命错误。"""
    try:
        logs = container.logs(tail=50).decode("utf-8", errors="ignore")
        return [line.strip() for line in logs.split("\n") if FATAL_PATTERN.search(line)]
    except Exception as e:
        print(f"[WARN] 读取容器 {container.name} 日志失败: {e}")
        return []


def verify_infrastructure(exit_on_fail: bool = True) -> bool:
    """
    执行基础设施验真。
    若 exit_on_fail=True，失败时直接退出进程；否则返回布尔值。
    """
    print("\n[INFO] 开始执行自动化基座验真...")

    client = get_docker_client()
    if not client:
        print("[ERROR] 无法连接到 Docker Daemon")
        if exit_on_fail:
            sys.exit(1)
        return False

    if not wait_for_containers_ready(client, PROJECT_LABEL):
        if exit_on_fail:
            sys.exit(1)
        return False

    containers = client.containers.list(all=True, filters={"label": PROJECT_LABEL})
    all_passed = True

    for container in containers:
        name = container.name
        status = container.status
        health = container.attrs.get("State", {}).get("Health", {}).get("Status")
        health_info = f", health={health}" if health else ""
        print(f"[CHECK] 容器 {name}: status={status}{health_info}")

        bad_lines = scan_container_logs(container)
        if bad_lines:
            print(f"[WARN] 容器 {name} 发现疑似致命日志:")
            for bl in bad_lines[:3]:
                print(f"    -> {bl}")
            all_passed = False

    if all_passed:
        print("\n[OK] ZEN70 基础设施全线绿灯")
    else:
        print("\n[FAIL] 基础设施验真未通过，请排查上述警告。")
        if exit_on_fail:
            sys.exit(1)

    return all_passed


if __name__ == "__main__":
    verify_infrastructure(exit_on_fail=True)
