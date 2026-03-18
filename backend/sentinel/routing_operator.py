"""
K3s 级动态路由控制器 (Routing Operator)

核心架构规范 (法典 Phase 7):
1. Status Watch (状态监听): 监听开关期望状态的变化。
2. Dynamic Compilation (动态编译): 当发生变化时，写入 routes.json 并调用 compiler.py 渲染全新 Caddyfile。
3. API Reload (热更新): 将新渲染的 Caddyfile 通过 HTTP 原生 API 推送给 Caddy 节点，实现绝对零停机 (Zero-Downtime)。
"""

import asyncio
import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path

import httpx
import redis.asyncio as aioredis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [ROUTING-OPERATOR] %(message)s")
logger = logging.getLogger(__name__)

# 配置硬编码，但在实际运行中会依赖系统级 yaml/env 的挂载
# 这里的端口只是模拟，实际系统中 Jellyfin 通常是 8096, Frigate 5000, Ollama 11434
DEFAULT_PORTS = {"media": "8096", "vision": "5000", "llm": "11434"}


class RoutingOperator:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_password = os.getenv("REDIS_PASSWORD", None)
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.caddy_api_url = "http://127.0.0.1:2019/load"  # 默认假设在宿主机能反向访问到 Caddy Admin
        self.last_hash = ""

        # 读取编译器传给 .env 的硬编码字典
        raw_map = os.getenv("SWITCH_CONTAINER_MAP", "{}")
        try:
            self.switch_map = json.loads(raw_map)
        except Exception:
            self.switch_map = {
                "media": "zen70-jellyfin",
                "vision": "zen70-frigate",
                "llm": "zen70-ollama",
            }

    async def _get_redis(self) -> aioredis.Redis:
        return aioredis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            password=self.redis_password,
            decode_responses=True,
        )

    async def _compile_routes(self, routes: list):
        """调用 IaC 编译器，生成最新的 Caddyfile"""
        routes_path = self.project_root / "routes.json"
        with open(routes_path, "w", encoding="utf-8") as f:
            json.dump(routes, f, ensure_ascii=False, indent=2)

        compiler_script = self.project_root / "scripts" / "compiler.py"
        try:
            # 阻塞执行编译器，生成全新的 ./config/Caddyfile
            subprocess.run(
                [sys.executable, str(compiler_script)],
                cwd=str(self.project_root),
                check=True,
                capture_output=True,
            )
            logger.info("🟢 [Operator] The Compiler 成功渲染新拓扑至 Caddyfile")
        except subprocess.CalledProcessError as e:
            logger.error(f"🔴 [Operator] The Compiler 执行失败: {e.stderr.decode()}")
            raise

    async def _reload_caddy(self):
        """调用 Caddy 原生 Admin API 实现微秒级热拉起"""
        caddyfile_path = self.project_root / "config" / "Caddyfile"
        if not caddyfile_path.exists():
            logger.warning("[Operator] 找不到生成的 Caddyfile，跳过 Reload")
            return

        with open(caddyfile_path, "rb") as f:
            caddyfile_data = f.read()

        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    self.caddy_api_url,
                    headers={"Content-Type": "text/caddyfile"},
                    content=caddyfile_data,
                    timeout=5.0,
                )
            if res.status_code == 200:
                logger.info("🟢 [Operator] Caddy 热更 API 调用成功 (Zero-Downtime Reload)!")
            else:
                logger.error(f"🔴 [Operator] Caddy Reload 失败: {res.status_code} - {res.text}")
        except Exception as e:
            logger.warning(f"🟠 [Operator] Caddy API 通信异常 (可能刚启动或无 Caddy 容器): {e}")

    async def spin_loop(self):
        logger.info("🚀 Routing Operator K3s-Controller 已就绪...")
        import sys

        while True:
            try:
                r = await self._get_redis()
                current_routes = []

                for switch_key, container_name in self.switch_map.items():
                    # Watch: 探究当前意图状态 (可能被 Taint 影响，或者被用户彻底关停)
                    state = await r.get(f"switch_expected:{switch_key}")
                    if state == "ON":
                        target_port = DEFAULT_PORTS.get(switch_key, "80")
                        current_routes.append(
                            {
                                "path": f"/{switch_key}/*",
                                "target": f"{container_name}:{target_port}",
                            }
                        )

                await r.aclose()

                # Reconcile: 对比状态指纹，若发生拓扑变更，执行 Dynamic Compilation + Reload
                routes_str = json.dumps(current_routes, sort_keys=True)
                routes_hash = hashlib.md5(routes_str.encode()).hexdigest()

                if routes_hash != self.last_hash:
                    logger.info("🌀 [Operator] 侦测到节点拓扑变更，开始调谐 (Reconcile)...")
                    try:
                        # 对于内部嵌套的缺库补充，强制导包
                        global sys
                        import sys

                        await self._compile_routes(current_routes)
                        await self._reload_caddy()
                        self.last_hash = routes_hash
                    except Exception as e:
                        logger.error(f"[Operator] 调谐期崩溃: {e}")

            except Exception as e:
                logger.debug(f"Operator loop issue: {e}")

            await asyncio.sleep(5)  # 避坑：死循环非常吃 CPU，严格防卫 5 秒间隔


if __name__ == "__main__":
    op = RoutingOperator()
    asyncio.run(op.spin_loop())
