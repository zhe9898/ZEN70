#!/usr/bin/env python3
"""
ZEN70 拓扑探针守护进程 (Topology Sentinel)。

负责硬件热插拔检测、容器熔断、状态机更新；不采集周期性指标（由 Categraf 负责）。
以固定周期轮询挂载点存活与 GPU 心跳，滑动窗口防抖、悲观锁、三重核验后写 Redis 并发布事件。
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone

import redis


# -------------------- 常量 --------------------
class HWState:
    ONLINE: str = "online"
    OFFLINE: str = "offline"
    PENDING: str = "pending"
    UNKNOWN: str = "unknown"


REDIS_CHANNEL_EVENTS = "hardware:events"
REDIS_KEY_GPU = "hw:gpu"
DEFAULT_PENDING_TTL = 20


def _load_container_map() -> Dict[str, str]:
    """路径解耦：挂载路径→容器名仅来自 .env（由 compiler 从 system.yaml 写入）。"""
    raw = os.getenv("MOUNT_CONTAINER_MAP", "{}")
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


CONTAINER_MAP: Dict[str, str] = _load_container_map()

# -------------------- 日志（复用 backend.core 集中模块） --------------------
try:
    from backend.core.structured_logging import get_logger as _get_logger
except ImportError:
    # 兼容单文件调试，使用标准 logging
    def _get_logger(name: str, req_id: Optional[str]) -> logging.LoggerAdapter:
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logging.LoggerAdapter(logger, extra={})


def setup_logging(request_id: Optional[str] = None) -> logging.LoggerAdapter:
    """
    配置 JSON 日志并返回带 request_id 的 LoggerAdapter。
    探针调用 Docker 时继承进程环境，若配置 DOCKER_HOST 则自动使用 TCP 寻址（禁止直接挂载 sock）。
    """
    base_logger = logging.getLogger("topology-sentinel")
    base_logger.handlers.clear()
    return _get_logger("topology-sentinel", request_id)


logger: Optional[logging.LoggerAdapter] = None


# -------------------- 挂载点配置 --------------------


class MountPoint:
    """
    单个挂载点配置：路径、期望 UUID、最小剩余空间；维护滑动窗口状态缓存。
    """

    def __init__(
        self,
        path: str,
        expected_uuid: Optional[str] = None,
        min_space_gb: int = 1,
    ) -> None:
        self.path = Path(path)
        self.expected_uuid = expected_uuid
        self.min_space_bytes = min_space_gb * (1024**3)
        self.state_cache: Deque[bool] = deque(maxlen=3)
        self.pending_lock_key = f"lock:{path}"

    def check_exists(self) -> bool:
        """检查挂载路径是否存在。"""
        try:
            return self.path.exists()
        except Exception as e:
            if logger:
                logger.warning(f"check_exists failed for {self.path}: {e}")
            return False

    def get_uuid(self) -> Optional[str]:
        """法典 3.2：通过 Linux 原生命令 findmnt + blkid 获取挂载点对应设备 UUID。自动降级防腐。"""
        path_str = str(self.path.resolve())
        try:
            # 1) findmnt 取挂载点对应设备（如 /dev/sda1）
            r1 = subprocess.run(
                ["findmnt", "-n", "-o", "SOURCE", "--target", path_str],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r1.returncode != 0 or not (r1.stdout and r1.stdout.strip()):
                return None
            device = r1.stdout.strip()
            if not device or device == "rootfs":
                return None

            # str() conversion for type checkers
            s_device = str(device)
            # 2) blkid 取该设备 UUID
            r2 = subprocess.run(
                ["blkid", "-s", "UUID", "-o", "value", s_device],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r2.returncode != 0 or not (r2.stdout and r2.stdout.strip()):
                return None
            return r2.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            if logger:
                logger.debug(f"get_uuid failed for {self.path}: {e}")
            return None

    def get_free_space(self) -> int:
        """返回挂载点可用空间字节数；失败返回 0。"""
        try:
            return shutil.disk_usage(self.path).free
        except Exception as e:
            if logger:
                logger.warning(f"get_free_space failed for {self.path}: {e}")
            return 0

    def verify_full(self) -> Tuple[bool, str]:
        """
        三重交叉核验：路径存在、UUID 匹配（若配置）、最小剩余空间。
        返回 (是否通过, 原因说明)。
        """
        if not self.check_exists():
            return False, "path not exists"
        if self.expected_uuid is not None and self.expected_uuid != "":
            actual = self.get_uuid()
            if actual != self.expected_uuid:
                return False, f"UUID mismatch (expected {self.expected_uuid}, got {actual})"
        free = self.get_free_space()
        if free < self.min_space_bytes:
            return False, f"insufficient space: {free} < {self.min_space_bytes}"
        return True, "ok"


# -------------------- 探针主类 --------------------


class TopologySentinel:
    """
    拓扑探针：轮询挂载点与 GPU，防抖后更新 Redis 状态并发布事件，必要时执行 docker pause/unpause。
    """

    def __init__(self) -> None:
        host = os.getenv("REDIS_HOST")
        if not host:
            raise RuntimeError("REDIS_HOST env var is required")
        self.redis_host = host
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_password = os.getenv("REDIS_PASSWORD") or None
        self.mock = os.getenv("MOCK_HARDWARE", "false").lower() in ("true", "1")
        self.interval = max(1, int(os.getenv("PROBE_INTERVAL", "5")))
        self.window_size = max(1, min(10, int(os.getenv("DEBOUNCE_WINDOW", "3"))))
        self.pending_ttl = int(os.getenv("PENDING_LOCK_TTL", str(DEFAULT_PENDING_TTL)))

        # 法典 7.2.1: 边缘节点脑裂防护静默状态 (Stop-Pulling)
        self.is_zombie = False
        self.redis_timeout_count = 0
        self.max_redis_timeouts = max(2, int(os.getenv("MAX_REDIS_TIMEOUTS", "6")))  # 默认 6 * 5s = 30s 熔断

        self.mounts: List[MountPoint] = []
        mount_points_env = os.getenv("MOUNT_POINTS", "").strip()
        if mount_points_env:
            for part in mount_points_env.split(";"):
                part = part.strip()
                if not part:
                    continue
                seg = [s.strip() for s in part.split(",")]
                path = seg[0]
                uid = seg[1] if len(seg) > 1 and seg[1] else None
                min_gb = int(seg[2]) if len(seg) > 2 and seg[2].isdigit() else 1
                self.mounts.append(MountPoint(path, uid, min_gb))

        self._redis: Optional[redis.Redis] = None
        self._connect_redis()

        if logger:
            logger.info(f"TopologySentinel initialized mock={self.mock} interval={self.interval}s " f"mounts={len(self.mounts)}")

    def _connect_redis(self) -> None:
        """连接 Redis，失败时指数退避重试（2/4/8/16/32s）后退出。"""
        backoff = [2, 4, 8, 16, 32]
        user = os.getenv("REDIS_USER", "default")
        for attempt in range(5):
            try:
                r = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    username=user if self.redis_password else None,
                    password=self.redis_password,
                    decode_responses=True,
                    socket_connect_timeout=5,
                )
                r.ping()
                self._redis = r
                if logger:
                    logger.info("Connected to Redis")
                return
            except Exception as e:
                if logger:
                    logger.warning(f"Redis connection attempt {attempt + 1}/5 failed: {e}, " f"next retry in {backoff[attempt]}s")
                time.sleep(backoff[attempt])
        if logger:
            logger.error("Redis unavailable after retries, entering zombie mode (Split-Brain Prevention)")
        self.is_zombie = True

    def _redis_ok(self) -> bool:
        """检查 Redis 是否可用，多次超时进入脑裂防备的 zombie 态，恢复重置"""
        try:
            r = self._redis
            if r is not None:
                r.ping()
                if self.is_zombie:
                    if logger:
                        logger.info("Redis reconnected. Leaving zombie mode.")
                self.is_zombie = False
                self.redis_timeout_count = 0
                return True
        except Exception:
            self.redis_timeout_count += 1
            if self.redis_timeout_count >= self.max_redis_timeouts and not self.is_zombie:
                if logger:
                    logger.warning("Redis ping threshold exceeded, entering zombie mode (Split-Brain Prevention)")
                self.is_zombie = True
        try:
            self._connect_redis()
            return True
        except Exception:
            return False

    def _get_actual_running_containers(self) -> set[str]:
        """Observe: 获取当前真正在运行的 Docker 容器名列表"""
        if self.is_zombie:
            return set()
        try:
            r = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return set([line.strip() for line in r.stdout.strip().split("\n") if line.strip()])
        except Exception as e:
            if logger:
                logger.error(f"Observe failed: {e}")
            return set()

    def _reconcile_loop(self) -> None:
        """
        K3s-Inspired Reconciliation Loop (声明式控制循环): Observe -> Diff -> Act
        核心思想: 抛弃事件触发器, 改为保证系统实际状态向预期状态收敛.
        预期状态 (Desired state): yaml 中的 SWITCH_CONTAINER_MAP 配合用户手动设置 (存 Redis switch_expected:) + 污点 (Taints) 妥协.
        """
        if not self._redis_ok() or not self._redis or self.is_zombie:
            return

        # 1. 整理预期状态 (Desired)
        # 获取所有系统登记的名义开关及其对应的后端容器
        switch_map_raw = os.getenv("SWITCH_CONTAINER_MAP", "{}")
        try:
            switch_map = json.loads(switch_map_raw)
        except json.JSONDecodeError:
            switch_map = {}

        gpu_taints = set()
        r = self._redis
        if r is not None:
            try:
                gpu_state_raw: Dict[Any, Any] = r.hgetall(REDIS_KEY_GPU)
                if gpu_state_raw and gpu_state_raw.get("taint"):
                    gpu_taints.add(gpu_state_raw["taint"])
            except Exception:
                pass

        desired_running_containers = set()
        containers_managed_by_sentinel = set()

        for switch_name, container_name in switch_map.items():
            containers_managed_by_sentinel.add(container_name)

            # 默认预期状态
            expected_state = "OFF"
            try:
                # 优先读取用户在 Redis 中明确要求的状态
                if r is not None:
                    redis_exp = r.get(f"switch_expected:{switch_name}")
                    if redis_exp:
                        expected_state = str(redis_exp)
            except Exception:
                pass

            # 污点退避 (Toleration Rejection)
            # 如果节点有 overheating 污点, 那么像媒体转码这类非核心应用强制挂起(期望状态跌活为 OFF)
            if "overheating:NoSchedule" in gpu_taints and "media" in switch_name.lower():
                if expected_state == "ON":
                    if logger:
                        logger.warning(f"Taint Active (overheating). Forcing component '{switch_name}' to OFF to protect node.")
                    expected_state = "OFF"

            # 结合挂载点状态
            # (省略这部分复杂逻辑, 这里简化为如果 expected_state == ON 则进入 desired set)
            if expected_state == "ON":
                desired_running_containers.add(container_name)

        # 2. 观察实际状态 (Observe)
        actual_running = self._get_actual_running_containers()

        # 3. 对比差异 (Diff) & 执行同步 (Act)
        # 只管治 SWITCH_CONTAINER_MAP 列表里的容器，不干涉核心网关等容器
        for container in containers_managed_by_sentinel:
            should_run = container in desired_running_containers
            is_running = container in actual_running

            if should_run and not is_running:
                # 状态弹簧对齐: 应该跑但没跑 -> docker-compose up
                if logger:
                    logger.info(f"[Reconcile] Diff detected: {container} is OFF but expected ON. Act: compose up")
                try:
                    subprocess.run(
                        ["docker-compose", "up", "-d", container],
                        cwd=Path(__file__).parent.parent.parent,  # 指向 e:/新建文件夹 目录
                        timeout=30,
                    )
                except Exception as e:
                    if logger:
                        logger.error(f"[Reconcile] Up act failed for {container}: {e}")

            elif not should_run and is_running:
                # 状态弹簧对齐: 不该跑但跑了 -> docker rm -f 驱逐
                # 彻底销毁旧实例，下次被唤醒时将完全重演挂载 (Eviction 机制)
                if logger:
                    logger.info(f"[Reconcile] Diff detected: {container} is ON but expected OFF (or Tainted). Act: docker rm -f")
                try:
                    subprocess.run(["docker", "rm", "-f", container], timeout=10)
                except Exception as e:
                    if logger:
                        logger.error(f"[Reconcile] Rm act failed for {container}: {e}")

    def _update_state(
        self,
        mount: MountPoint,
        state: str,
        reason: str = "",
    ) -> None:
        """更新 Redis 中 hw:<path> 哈希并发布 hardware:events 事件。"""
        r = self._redis
        if r is None:
            return
        key = f"hw:{mount.path}"
        data: Dict[str, str] = {
            "path": str(mount.path),
            "uuid": mount.expected_uuid or "",
            "state": state,
            "timestamp": str(time.time()),
            "reason": reason,
        }
        try:
            r.hset(key, mapping=data)
            event = {
                "type": "hardware_change",
                "path": str(mount.path),
                "state": state,
                "reason": reason,
            }
            r.publish(REDIS_CHANNEL_EVENTS, json.dumps(event))
            if logger:
                logger.info(f"State updated {mount.path}: {state} ({reason})")
        except Exception as e:
            if logger is not None:
                logger.error(f"Redis update_state failed: {e}", exc_info=True)

    def _check_gpu(self) -> Dict[str, Any]:
        """检测 GPU 状态，并主动生成污点 (Taints) 信号供控制循环参考"""
        if self.mock:
            return {
                "online": "true",
                "temp": "45",
                "util": "30",
                "tags": json.dumps(["gpu_nvenc_v1"]),
            }
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=temperature.gpu,utilization.gpu",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return {"online": "false"}
            line = result.stdout.strip().split("\n")[0]
            parts = [p.strip().replace(" %", "").replace(" ", "") for p in line.split(",")]

            payload = {"online": "true", "tags": json.dumps(["gpu_nvenc_v1", "gpu_cuvid"])}
            if len(parts) >= 2:
                payload["temp"] = parts[0]
                payload["util"] = parts[1]

                # 注入污点机制 (Taint: overheating:NoSchedule)
                try:
                    target_temp = int(parts[0])
                    if target_temp > 85:
                        payload["taint"] = "overheating:NoSchedule"
                    else:
                        payload["taint"] = ""  # 清理污点
                except ValueError:
                    pass

            return payload
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
            if logger:
                logger.warning(f"GPU check failed: {e}")
            return {"online": "false", "tags": "[]"}

    def _handle_mount(self, mount: MountPoint) -> None:
        """对单个挂载点执行检测防抖与状态更新；不再在此直接执行降级（交由 Reconcile）"""
        if not self._redis_ok():
            return
        exists: bool
        if self.mock:
            exists = (time.time() % 10) > 3
        else:
            exists = mount.check_exists()
        mount.state_cache.append(exists)

        if len(mount.state_cache) < self.window_size:
            return
        if not all(v == mount.state_cache[0] for v in mount.state_cache):
            return

        current_alive = mount.state_cache[0]
        new_state = HWState.ONLINE if current_alive else HWState.OFFLINE

        key = f"hw:{mount.path}"
        cur_state: Optional[str] = None
        r = self._redis
        try:
            if r is not None:
                cur_state_val = r.hget(key, "state")
                if cur_state_val:
                    cur_state = str(cur_state_val)
        except Exception:
            pass

        if new_state == HWState.OFFLINE:
            if cur_state != HWState.PENDING:
                try:
                    if r is not None:
                        r.setex(mount.pending_lock_key, self.pending_ttl, "PENDING")
                except Exception as e:
                    if logger is not None:
                        logger.error(f"Redis setex PENDING failed: {e}")
                self._update_state(mount, HWState.PENDING, "offline detected")
                # 移除了 self._docker_pause() 调用, 交由声明式控制循环对齐
        else:
            if cur_state == HWState.PENDING:
                ok, reason = mount.verify_full()
                if ok:
                    if logger:
                        logger.info(f"Mount {mount.path} passed verification")
                    self._update_state(mount, HWState.ONLINE, "verified online")
                    try:
                        if r is not None:
                            r.delete(mount.pending_lock_key)
                    except Exception:
                        pass
                    # 移除了 self._docker_unpause() 调用, 交由声明式控制循环对齐
                else:
                    if logger is not None:
                        logger.warning(f"Mount {mount.path} logic verification failed: {reason}")
                    self._update_state(mount, HWState.PENDING, f"verification failed: {reason}")
            elif cur_state != HWState.ONLINE:
                self._update_state(mount, HWState.ONLINE, "online")

    def run_once(self) -> None:
        """执行一次检测周期与强一致性调谐。"""
        # Step 1: 处理挂载点心跳 (I/O)
        for mount in self.mounts:
            try:
                self._handle_mount(mount)
            except Exception as e:
                if logger:
                    logger.error(f"Error handling mount {mount.path}: {e}")

        # Step 2: 处理 GPU 状态核验并打污点
        r = self._redis
        if self._redis_ok() and r is not None:
            try:
                gpu_state = self._check_gpu()
                r.hset(REDIS_KEY_GPU, mapping=gpu_state)
            except Exception as e:
                if logger:
                    logger.warning(f"GPU state write failed: {e}")

        # Step 3: K3s 调谐循环 (Reconcile loop)
        try:
            self._reconcile_loop()
        except Exception as e:
            if logger:
                logger.error(f"Reconcile loop crashed: {e}", exc_info=True)

    def _redis_listener_thread(self):
        """后台专职监听 Redis pub/sub，现在只做状态写入(Desired State)，不直接操作物理层。"""
        r = self._redis
        if r is None or self.is_zombie:
            return
        try:
            pubsub = r.pubsub()
            pubsub.subscribe("switch:events")
            if logger is not None:
                logger.info("Topology sentinel starting declarative Redis pub/sub listener on switch:events")
            for message in pubsub.listen():
                if message and message.get("type") == "message":
                    data = message.get("data")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    try:
                        obj = json.loads(data)
                        switch_name = obj.get("switch")
                        state = obj.get("state")
                        if not switch_name or not state:
                            continue

                        # 把前端下达的“期望状态”写入 Redis 缓存。物理拉平交给 Reconcile Loop.
                        if logger is not None:
                            logger.info(f"Setting desired state for {switch_name} to {state}")
                        r.set(f"switch_expected:{switch_name}", str(state))

                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            if logger is not None:
                logger.error(f"Redis listener thread crashed: {e}")

    def run(self) -> None:
        """主循环：按间隔周期执行 run_once；单次超时（interval*2）则告警并等待本周期结束再下一轮。"""
        if logger:
            logger.info("Starting topology sentinel main loop")

        # 启动后台监听线程 (守护线程)
        listener = threading.Thread(target=self._redis_listener_thread, daemon=True)
        listener.start()

        cycle_timeout = max(self.interval * 2, 10)
        while True:
            t = threading.Thread(target=self._run_once_safe)
            t.start()
            t.join(timeout=cycle_timeout)
            if t.is_alive():
                if logger:
                    logger.warning(f"run_once exceeded {cycle_timeout}s, waiting for cycle to finish")
                t.join()
            time.sleep(self.interval)

    def _evict_zombie_tasks(self) -> None:
        """
        K3s 优雅驱逐 (Eviction & Tombstones): 探测失联超过 15 秒的 Worker 节点,
        并为其认领的积压任务颁发墓碑 (Tombstone), 防止脑裂双写。
        """
        r = self._redis
        if not self._redis_ok() or r is None:
            return

        stream_key = "zen70:iot:stream:commands"
        group_name = "zen70_iot_workers"

        try:
            # 1. 获取所有消费者信息
            consumers = r.xinfo_consumers(stream_key, group_name)
            for c in consumers:
                idle_ms = c.get("idle", 0)
                pending_count = c.get("pending", 0)
                consumer_name = c.get("name", "")

                # 2. 如果 Worker 失联超过 15 秒且手头有卡住的任务
                if idle_ms > 15000 and pending_count > 0:
                    if logger is not None:
                        logger.warning(f"🧟‍♂️ [Eviction] Worker {consumer_name} is OFFINE (>15s). Evicting tasks!")

                    # 3. 查出它卡住的 Message ID
                    pending_info = r.xpending_range(stream_key, group_name, "-", "+", pending_count, consumer_name)
                    for p in pending_info:
                        msg_id = p.get("message_id")
                        if not msg_id:
                            continue

                        # 4. 读取原始 Payload 获取 command_id
                        msg_data = r.xrange(stream_key, msg_id, msg_id)
                        if msg_data:
                            _, payload = msg_data[0]
                            command_id = payload.get("command_id")
                            if command_id:
                                # 5. 宣判物理死亡 (写入墓碑，保留 24 小时)
                                tombstone_key = f"zen70:tombstone:{command_id}"
                                r.setex(tombstone_key, 86400, "evicted")
                                if logger is not None:
                                    logger.info(f"🪦 [Eviction] Tombstone written for dead command: {command_id}")

        except Exception as e:
            # Redis 流可能还没初始化，或者命令不支持，容错处理
            if logger is not None:
                logger.debug(f"Eviction loop skipped: {e}")

    def _run_once_safe(self) -> None:
        """run_once 的线程安全包装，捕获异常避免拖垮线程。"""
        try:
            self.run_once()
        except Exception as e:
            if logger:
                logger.error(f"run_once error: {e}", exc_info=True)


# -------------------- 入口 --------------------


def main() -> None:
    """解析环境、初始化日志与探针并进入主循环。"""
    global logger
    logger = setup_logging(request_id=str(uuid.uuid4()))
    sentinel = TopologySentinel()
    try:
        sentinel.run()
    except KeyboardInterrupt:
        if logger:
            logger.info("Shutting down by user")
        sys.exit(0)
    except Exception as e:
        if logger:
            logger.critical(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
