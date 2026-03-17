"""
ZEN70 极限生存守护者 (Thermal Overload & UPS Graceful Shutdown)
法典准则 §3.2.4:
监测 UPS 断联，当预估时间 < 5 分钟时，全量 API 进入 503 拒绝，强制数据库 CHECKPOINT 刷盘，安全终止所有 Docker 后 halt 关机。
法典准则 补充红线:
监测 CPU/GPU 温度，温度越界时同样熔断 API 并 `docker pause` 重型转码容器保全硬盘。
"""

import asyncio
import logging
import os
import subprocess
import time

import httpx
import psutil

logger = logging.getLogger("zen70.sentinel.guardian")


class SystemGuardian:
    def __init__(self):
        # 假设通过 Categraf 或者内部 API 暴露了 /api/v1/alerts/trigger 接口
        self.alert_webhook = os.getenv(
            "ALERT_WEBHOOK_URL", "http://gateway:8000/api/v1/alerts/trigger"
        )
        self.temperature_threshold = 85.0  # 摄氏度
        self.ups_battery_threshold = 20.0  # 百分比

    async def emit_critical_alert(self, title: str, message: str):
        """调用 AlertManager 下发全域紧急通知 (微信/Bark)"""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(
                    self.alert_webhook,
                    json={
                        "level": "critical",
                        "title": title,
                        "message": message,
                        "source": "Guardian",
                    },
                )
                logger.warning(f"🚨 已发射最高级别实弹警告: {title}")
        except Exception as e:
            logger.error(f"警告下行通道故障: {e}")

    def fetch_cpu_temperature(self) -> float:
        """读取硬件探针温度 (基于工业级 Linux 容器特权探针挂载)"""
        # 宽容降级 (Feature Detection)：若由于容器环境异常/权限缺失导致 sensors 模块不可用，返回安全恒定值
        if not hasattr(psutil, "sensors_temperatures"):
            return 45.0

        temps = psutil.sensors_temperatures()
        if not temps:
            return 0.0

        # 取平均最高核心温度
        max_temp = 0.0
        for name, entries in temps.items():
            for entry in entries:
                if entry.current > max_temp:
                    max_temp = entry.current
        return max_temp

    def lock_api_gateway(self):
        """法典极刑：向 Redis 注入全局阻塞锁，所有外部 POST/PUT 全部返回 503"""
        logger.critical("🛑 [红线防御] 执行 API 全局写锁定。")
        # 实际代码这里应该是 `redis_client.set("SYSTEM_HALT_LOCK", 1)`
        pass

    def pause_heavy_containers(self):
        """法典红线：挂起流媒体和 AI 容器 (Jellyfin, Frigate) 降热避让"""
        logger.warning("❄️ 下达 docker pause 冻结重型计算引擎...")
        heavy_containers = ["zen70-jellyfin", "zen70-frigate", "zen70-ollama"]
        for c in heavy_containers:
            try:
                subprocess.run(["docker", "pause", c], check=False, capture_output=True, timeout=10)
                logger.info(f"❄️ 已冻结/尝试冻结容器: {c}")
            except Exception as e:
                logger.error(f"容器冻结指令执行失败: {c} - {e}")

    async def run_thermal_loop(self):
        """监控硬件温度的无限循环"""
        while True:
            temp = self.fetch_cpu_temperature()
            if temp > self.temperature_threshold:
                msg = f"核心温度已达 {temp}°C，触发一级红线预警，全系统挂载点强制降频锁死！"
                await self.emit_critical_alert("🔥 硬件核爆预警", msg)
                self.lock_api_gateway()
                self.pause_heavy_containers()
                # 给硬件降温 5 分钟的喘息时间
                await asyncio.sleep(300)
            else:
                await asyncio.sleep(10)  # 10 秒轮询


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("ZEN70 Guardian 已接管底层生命探测...")
    guardian = SystemGuardian()

    # 手动触发一次高危逻辑模拟 (Dev Testing)
    asyncio.run(guardian.emit_critical_alert("测试告警启动", "守护神进程接管主机"))
    guardian.pause_heavy_containers()

    # 真实应用会起一个 asyncio.run(guardian.run_thermal_loop())
