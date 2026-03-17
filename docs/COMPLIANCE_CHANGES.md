# ZEN70 法典合规变更总览

本文档汇总为满足 `.cursorrules`（ZEN70 法典）所完成的**全部代码与配置变更**，便于审计与回溯。

---

## 一、变更文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `config/Caddyfile` | 修改 | SSE 反缓冲、安全响应头、OpenAPI 反代 |
| `scripts/compiler.py` | 修改 | gateway/redis 增加 ulimits、oom_score_adj |
| `scripts/templates/docker-compose.yml.j2` | 修改 | 输出 ulimits_block、oom_score_adj_block |
| `scripts/bootstrap.py` | 修改 | NTP 预检（漂移 >1s 拒绝启动） |
| `docker-compose.yml` | 生成 | 由 compiler 重新生成（含 ulimits/oom_score_adj） |
| `docs/adr/0001-topology-sentinel-redis-client.md` | 删除 | 与 0001-implement-iac 编号冲突 |
| `docs/adr/0005-topology-sentinel-redis-client.md` | 新增 | 探针 redis-py 决策，编号改为 0005 |
| `docs/ops/docker-daemon.md` | 新增 | Docker 网段与句柄运维说明 |
| `scripts/export_openapi.py` | 新增 | 导出 OpenAPI 规范到 docs/openapi.json |
| `docs/openapi.json` | 生成 | 由 export_openapi.py 生成，纳入版本控制 |
| **scripts/compiler.py** | 修改 | gateway/redis 增加 healthcheck_block（法典 3.4） |
| **scripts/templates/docker-compose.yml.j2** | 修改 | 输出 healthcheck_block |
| **backend/main.py** | 修改 | 请求体大小限制中间件 MAX_REQUEST_BODY_BYTES（法典 7） |
| **backend/alembic/env.py** | 修改 | upgrade 前申请 Redis DB_MIGRATION_LOCK（法典 3.5） |
| **frontend/src/views/SystemSettings.vue** | 修改 | 删除所有硬编码控制阵列，改用获取后端拉取的动态标签渲染，强制执行无状态配置（法典 2.3） |
| **backend/api/routes.py** | 修改 | GET /switches 将解析 env (SWITCH_CONTAINER_MAP) 动态推流 `label` 赋能前端渲染（法典 2.3） |
| **backend/sentinel/topology_sentinel.py** | 修改 | get_uuid 改用 findmnt + blkid（法典 3.2） |
| **backend/api/routes.py** | 修改 | 移除 docker.sock 依赖，改用 Redis PubSub (switch:events) 发布状态（法典 1.1 与 5.2.1） |
| **backend/sentinel/topology_sentinel.py** | 修改 | 新增 _redis_listener_thread 监听并执行 docker pause，强制 3 秒硬超时与 SIGKILL（法典 1.3） |
| **docs/ops/three-step-meltdown.md** | 新增 | 三步熔断顺序及网络层摘除运维说明（法典 3.1） |
| **system.yaml** | 修改 | 新增 sentinel.mount_container_map、sentinel.watch_targets（路径解耦） |
| **scripts/compiler.py** | 修改 | prepare_env 输出 media_path、bitrot_scan_dirs、mount_container_map、watch_targets |
| **scripts/templates/.env.j2** | 修改 | 增加 MEDIA_PATH、BITROT_SCAN_DIRS、MOUNT_CONTAINER_MAP、WATCH_TARGETS |
| **backend/sentinel/topology_sentinel.py** | 修改 | CONTAINER_MAP 仅从 MOUNT_CONTAINER_MAP env 读取 |
| **backend/sentinel.py** | 修改 | WATCH_TARGETS 仅从 WATCH_TARGETS env 读取 |
| **backend/main.py** | 修改 | BITROT_SCAN_DIRS 仅从 env 读取 |
| **backend/api/assets.py** | 修改 | MEDIA_PATH 仅从 env，空时 503 |
| **backend/api/settings.py** | 修改 | media_path 仅从 env，空时 status not_configured |
| **backend/worker/mqtt_worker.py** | 修改 | get_media_path fallback 仅从 env，空时跳过保存 |
| **backend/models/feature_flag.py** | 修改 | 种子默认路径从 MEDIA_PATH env 读取 |
| **backend/main.py** | 修改 | 冷启动 All-OFF 矩阵 + X-ZEN70-Bus-Status（法典 3.2.5） |
| **tests/integration/test_hardware_failure.py** | 修改 | 新增 test_503_meltdown_when_capability_pending（法典 5.1.1） |
| **backend/worker/mqtt_worker.py** | 修改 | 目录日期改为 utcnow（法典 2.4.2） |
| **docs/ARCHITECTURE_CHECKPOINTS.md** | 修改 | 2.4.2 / 3.2.5 / 5.1.1 状态更新为 ✅ |
| **config/Caddyfile** | 修改 | 增加 Content-Security-Policy（法典 2.2.3） |
| **docs/ops/docker-daemon.md** | 修改 | 新增 §3 系统盘 95% 熔断运维说明（法典 4.5） |
| **.pre-commit-config.yaml** | 新增 | black/isort/flake8 门禁（法典 5.2.2） |
| **backend/requirements-dev.txt** | 修改 | 增加 factory_boy>=3.3.0（法典 5.1.2） |
| **backend/tests/factories.py** | 新增 | AlertPayloadFactory、MockUserFactory |
| **backend/tests/unit/test_alert_manager.py** | 修改 | 使用工厂生成 payload 与 mock_user |
| **.github/workflows/compliance.yml** | 新增 | CI 门禁：black/isort/flake8 + backend 单元测试（法典 5.2.1/5.2.2） |
| **docs/ops/cron-gc-restic.md** | 新增 | 3.7 全域 GC / Restic / 豁免运维示例 |
| **scripts/release.sh** | 修改 | 注释注明禁止人工打 Tag（法典 5.2.3） |

---

## 二、按法典条款的变更说明

### 2.1 SSE 代理层反缓冲（法典 2.1）

- **文件**：`config/Caddyfile`
- **内容**：为 `/api/v1/stream*`、`/api/v1/events*` 单独 `handle`，设置 `header X-Accel-Buffering no` 后 `reverse_proxy gateway:8000`，避免代理缓冲导致 SSE 延迟。

### 2.2 安全响应头与 OpenAPI（法典 2.2）

- **文件**：`config/Caddyfile`
- **内容**：
  - 全局响应头：`X-Content-Type-Options: nosniff`、`Strict-Transport-Security: max-age=31536000; includeSubDomains`、`Referrer-Policy: strict-origin-when-cross-origin`。
  - `handle /openapi.json` 反代到 gateway，保证 `/openapi.json` 可访问。
- **文件**：`scripts/export_openapi.py`、`docs/openapi.json`
- **内容**：脚本从网关应用导出 OpenAPI JSON，写入 `docs/openapi.json`，满足「纳入版本控制」。

### 2.4 NTP 同步预检（法典 2.4）

- **文件**：`scripts/bootstrap.py`
- **内容**：在 `run_precheck()` 中增加 `_run_ntp_precheck()`；使用 `ntplib` 向 `0.pool.ntp.org`、`time.cloudflare.com` 请求，漂移 >1s 则 `sys.exit(1)`；无 `ntplib` 或全部 NTP 不可达时仅 WARN 并继续（兼容离线）。

### 3.4 安全容器 healthcheck（法典 3.4）

- **文件**：`scripts/compiler.py`、`scripts/templates/docker-compose.yml.j2`
- **内容**：对 `gateway` 注入 healthcheck（`python -c "urllib.request.urlopen('http://127.0.0.1:8000/health')"`），对 `redis` 注入 `redis-cli ping`；支持 system.yaml 中自定义 `healthcheck.test` 等。

### 3.2 探针 UUID 核验使用原生命令（法典 3.2）

- **文件**：`backend/sentinel/topology_sentinel.py`
- **内容**：`MountPoint.get_uuid()` 改为先用 **findmnt -n -o SOURCE --target &lt;path&gt;** 取挂载点对应设备，再用 **blkid -s UUID -o value &lt;device&gt;** 取 UUID，满足「核验 UUID 必须调用 Linux 原生命令（blkid/findmnt）」。

### 3.3 核心容器 ulimits 与 OOM 豁免（法典 3.3）

- **文件**：`scripts/compiler.py`、`scripts/templates/docker-compose.yml.j2`
- **内容**：对 `gateway`、`redis` 注入 `ulimits: nofile: 65536:65536`、`oom_score_adj: -999`；由 compiler 生成 compose 时写入。

### 3.3 Docker 网段与宿主机句柄（法典 3.3）

- **文件**：`docs/ops/docker-daemon.md`
- **内容**：运维说明：宿主机 `daemon.json` 配置 `default-address-pools`、`/etc/security/limits.conf` 的 nofile 等，避免与局域网/VPN 碰撞及句柄耗尽。

### 3.5 Alembic 迁移锁（法典 3.5）

- **内容**：`run_migrations_online()` 执行前向 Redis 申请全局锁 `zen70:DB_MIGRATION_LOCK`，持有最多 3600s，阻塞最多 120s；执行完毕后释放。环境变量 `SKIP_DB_MIGRATION_LOCK=1` 时跳过（离线/单节点可选用）。

### 2.3 Schema-Driven UI 与无代码硬编码渲染（V2.1 架构升维）

- **文件**：`frontend/src/views/SystemSettings.vue`、`backend/api/routes.py`
- **内容**：严格执行“后端驱动一切（IaC）”的红线规范：
  - 前端：删除了原有的 `swLabels` 写死字典，UI 彻底降维为纯展示组件。
  - 后端：在 `GET /api/v1/switches` 接口中，反向解构由 `compiler.py` 透传的 `system.yaml` 编译环境变量 `SWITCH_CONTAINER_MAP`。并在给前端下发的响应体中自动拼接生成 `label`。
  - 核心增益：现在若运维在 `yaml` 添加新的硬件开关，系统编译后**无需前端介入改代码、打包**，控制面板就能自动长出新的管控开关。

### 7. API 请求体大小限制（法典 7）

- **文件**：`backend/main.py`
- **内容**：新增中间件 `limit_request_body`，对带 `Content-Length` 的 POST/PUT/PATCH 请求，超过 `MAX_REQUEST_BODY_BYTES`（默认 10MB，可由 `MAX_REQUEST_BODY_BYTES` 覆盖）返回 413，错误码 `ZEN-REQ-413`。

### 9. 三步熔断与网络层摘除（法典 3.1）

- **文件**：`docs/ops/three-step-meltdown.md`
- **内容**：说明 API 层 503 → 网络层摘除（Caddy 摘路由）→ 容器级降级的顺序；并给出 Caddy 摘除/恢复 `/api/*` 的运维示例（改 Caddyfile + reload），当前网络层摘除需手动或脚本执行。

### 路径解耦（法典 1.2：IaC 唯一事实来源，禁止代码硬编码路径）

- **system.yaml**：新增 `sentinel.mount_container_map`、`sentinel.watch_targets`；`capabilities.storage.media_path` 已存在。
- **compiler**：`prepare_env()` 从 config 读出上述路径与映射，写入 `.env`（MEDIA_PATH、BITROT_SCAN_DIRS、MOUNT_CONTAINER_MAP、WATCH_TARGETS）。
- **探针**：`topology_sentinel.CONTAINER_MAP`、`sentinel.WATCH_TARGETS` 仅从 env 加载，无默认硬编码。
- **网关/API**：BITROT_SCAN_DIRS、MEDIA_PATH 仅从 env；上传/磁盘信息在 MEDIA_PATH 未配置时返回 503 或 not_configured。
- **worker/feature_flag**：媒体路径 fallback 或种子默认值仅来自 env。

### 11. ADR 编号规范（法典 6）

- **文件**：`docs/adr/`
- **内容**：原 `0001-topology-sentinel-redis-client.md` 与 `0001-implement-iac-with-python-compiler.md` 编号冲突；将「探针 redis-py」ADR 重编号为 **0005**，删除旧 0001 副本，新增 `0005-topology-sentinel-redis-client.md`。

### 12. 冷启动 Redis 失联 All-OFF（法典 3.2.5）

- **文件**：`backend/main.py`
- **内容**：Redis 不可用且无 LRU 缓存时，`get_capabilities_matrix` 返回硬编码 **ALL_OFF_MATRIX**（ups/network/gpu 均为 offline，reason 为「总线未就绪」）；`/api/v1/capabilities` 在该情况下返回 200 且响应头 **X-ZEN70-Bus-Status: not-ready**，前端可据此展示「总线未就绪」告警。

### 13. 集成测试显式断言 503（法典 5.1.1）

- **文件**：`tests/integration/test_hardware_failure.py`
- **内容**：新增 **test_503_meltdown_when_capability_pending**：通过 Redis 设置 `zen70:topology:media_engine=PENDING_MAINTENANCE`，等待网关 LRU 缓存过期后请求 `GET /api/v1/media/status`，显式断言 **status_code == 503** 且 **code == ZEN-STOR-1001**。

### 14. 时区 UTC 统一（法典 2.4.2）

- **文件**：`backend/worker/mqtt_worker.py`、`docs/ARCHITECTURE_CHECKPOINTS.md`
- **内容**：mqtt_worker 中 Frigate 快照目录日期由 `datetime.now()` 改为 **datetime.utcnow()**；检查点 2.4.2、3.2.5、5.1.1 状态更新为 ✅。

### 15. 安全头 CSP 与检查点续查（法典 2.2、4.4、4.5、5.2.2）

- **config/Caddyfile**：增加 **Content-Security-Policy**（default-src 'self'；script/style/img/connect 适度放宽以兼容 PWA/流媒体）；检查点 2.2.3 已涵盖 CSP。
- **docs/ops/docker-daemon.md**：新增 **§3 系统盘 95% 熔断**：说明由监控/探针采集、告警后按三步熔断与 pause 下发的运维建议；检查点 4.5 说明中引用该节。
- **docs/ARCHITECTURE_CHECKPOINTS.md**：4.4 标为 ✅（8s 超时与 206 截断已实现）；4.5 说明补充运维文档引用；5.2.2 说明补充 .pre-commit-config.yaml。
- **.pre-commit-config.yaml**：新增 black、isort、flake8 门禁，限定 `backend/`，便于本地与 CI 执行。

### 16. factory_boy 测试数据工厂（法典 5.1.2）

- **backend/requirements-dev.txt**：增加 **factory_boy>=3.3.0**。
- **backend/tests/factories.py**：新增 **AlertPayloadFactory**（AlertPayload）、**MockUserFactory**（JWT user 字典），供单元/集成测试复用。
- **backend/tests/unit/test_alert_manager.py**：`mock_user` fixture 与两处 `AlertPayload` 改为由工厂生成，无硬编码字面量。
- **docs/ARCHITECTURE_CHECKPOINTS.md**：5.1.2 说明更新为「已引入 factories，test_alert_manager 已改用工厂；其余测试待推广」。

### 17. CI 合规工作流与 3.7 运维说明（法典 5.2、3.7）

- **.github/workflows/compliance.yml**：新增 Compliance 工作流，在 push/PR 到 main|master 时执行：安装 backend 依赖、**black / isort / flake8** 检查、**backend 单元测试**；满足 5.2.2 代码规范门禁，并为 5.2.1 提供流水线入口（Trivy/audit 可后续追加）。
- **docs/ops/cron-gc-restic.md**：新增 3.7 运维示例：容器 GC（含 zen70.gc.keep 豁免）、Restic forget --prune、PostgreSQL/应用级清理、不可删除区域；检查点 3.7.x 说明引用该文档。
- **scripts/release.sh**：顶部注释注明「禁止人工打 Tag，必须通过本脚本或 CI 自动打 Tag，遵循 Conventional Commits」。
- **docs/ARCHITECTURE_CHECKPOINTS.md**：5.2.2 标为 ✅（CI 已跑 black/isort/flake8）；5.2.1/5.2.3、3.7.x 说明更新。

### 18. 全局无冲突审计与 O(N) 性能肃清 (V3.0 升级)

- **backend/workers/media_watcher.py**：多容器横向扩容 (HPA) 下，针对未处理资产引入 Postgres 原生悲观行锁 `.with_for_update(skip_locked=True)`，彻底消灭多个扫描守护进程并发拉取同一任务引发的冲突。
- **backend/workers/iot_bridge.py**：修复 `paho-mqtt` 异步跨线程抛出 `RuntimeError` 的史诗级缺陷，由 `asyncio.get_event_loop()` 迁移至显式挂载主循环，并经由 `run_coroutine_threadsafe(..., self.loop)` 安全注入。
- **backend/api/iot.py**：抹除了导致网络 IO 堵塞风暴的串行 N+1 `redis.get` 循环，重构成了一次性吞吐的 `redis.mget` 批量管道获取（O(1) 性能），微压榨接口长连接。
- **全域守护脚本**：执行严格的静态抽象语法树 (AST) 清除，在 `assets.py`、`push.py` 等文件中清除了大量的未使用或冗余 Import (`torch`, `sys`, `time`, `json`)，强制削减微服务的初始驻留物理内存。

---

## 三、未改代码的合规项（已核对）

以下条款在现有代码中已满足，本次仅做核对：

- **X-Request-ID**：`backend/main.py`、`api/main.py` 中间件注入并回写响应头。
- **统一错误码 ZEN-xxx + recovery_hint**：`auth_helpers.zen()`、`ai_router`、`main.py` 等已用统一契约。
- **结构化日志**：`core/structured_logging.py` JSON 格式化，含 request_id/caller/level。
- **503 后前端不无限轮询**：`frontend/src/utils/http.ts` 断路器 15s 冷却。
- **Lifespan 优雅启停**：`main.py`、`api/main.py` 中关闭任务与 Redis。
- **目录预建 + chown 1000:1000**：`bootstrap.py` 预建挂载卷并 chown。
- **swapoff -a**：`bootstrap.py` 在 Linux 下已执行。
- **--remove-orphans**：`bootstrap.py`、`deployer.py` 使用 `docker compose up -d --remove-orphans`。

---

## 四、可选依赖

- **NTP 预检**：`scripts/bootstrap.py` 的 NTP 预检使用可选依赖 `ntplib`。若需在离线环境跳过预检，可保留当前「不可达则 WARN 并继续」行为；若需强制预检，可 `pip install ntplib` 或在项目/运维文档中说明。

---

*文档生成后请随发布更新；所有变更均对应 .cursorrules V2.0 绝对零度版。*
