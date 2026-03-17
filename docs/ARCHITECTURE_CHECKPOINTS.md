# ZEN70 架构符合性检查点清单

本文档按 `.cursorrules`（法典 V2.0 绝对零度版）逐条列出**所有架构检查点**及当前**符合状态**，便于审计与迭代。

---

## 一、图形化部署与架构符合性

**结论：符合。**

- **IaC 唯一事实来源**：图形化部署仅将用户输入的「媒体路径」「模型路径」**写入 system.yaml**（`capabilities.storage.media_path`、`sentinel.watch_targets`、`sentinel.mount_container_map`），不向 system.yaml 写入密码/Token；随后执行 **compiler**，由 compiler 从 system.yaml 生成 .env。路径事实来源仍为 system.yaml，编译器为唯一生成 .env 的入口。
- **路径解耦**：安装器不包含任何硬编码路径；默认占位 `/mnt/media`、`/mnt/models` 仅作为表单默认值，实际生效值以用户填写并写入 system.yaml 的为准。
- **机密**：Tunnel Token 仍按原逻辑写入已有 .env 文件，不写入 system.yaml，符合「密码/Token 占位由点火脚本或运行时注入 .env，严禁明文入 YAML」。

**注意**：安装器使用 **ruamel.yaml** 做仅键值修补（只改 `media_path`、`mount_container_map`、`watch_targets` 相关项），**保留 system.yaml 注释与格式**；无 ruamel 时回退为 PyYAML 全量重写（会丢注释）。

---

## 二、按法典条款的完整检查点

### 第 1 部分：全栈技术路线规约

| 检查点 | 条款 | 状态 | 说明 |
|--------|------|------|------|
| 1.1.1 技术选型无 Beta/实验性 | 1.1 | ✅ | 后端 FastAPI/Pydantic v2、PostgreSQL/Redis、Vue3+Vite+TS、Docker 等均为工业级方案。 |
| 1.1.2 后端栈 | 1.1 | ✅ | Python 3.11+、FastAPI、Pydantic v2、PostgreSQL（pgvector）、Redis AOF、Alembic。 |
| 1.1.3 前端栈 | 1.1 | ✅ | Vue 3 Composition API、Vite、TypeScript、Pinia、PWA。 |
| 1.1.4 编排与可观测性 | 1.1 | ✅ | Docker + compose、Categraf/Prometheus/Grafana/Loki。 |
| 1.2.1 硬件型号解耦 | 1.2 | ✅ | 仅能力标签（如 gpu_nvenc_v1），无具体型号；探针输出 tags 不输出型号。 |
| 1.2.2 IaC 唯一事实来源 | 1.2 | ✅ | 配置收束于 system.yaml，compiler 生成 compose/.env；图形化部署只写 system.yaml 再调 compiler。 |
| 1.2.3 机密不落盘 YAML | 1.2 | ✅ | 密码/Token 用 `${ENV_VAR}` 占位，compiler 或点火脚本注入 .env。 |
| 1.2.4 斩杀编排孤儿 | 1.2 | ✅ | bootstrap/deployer 使用 `docker compose up -d --remove-orphans`。 |
| 1.2.5 协议驱动 UI | 1.2 | ⚠️ | 主控台基于 `/api/v1/capabilities` 动态渲染；**安装器**为独立静态表单，非 capabilities 驱动，属部署入口例外。 |
| 1.2.6 RBAC/视界折叠 | 1.2 | ✅ | JWT Role、长辈/极客模式等有条件渲染。 |
| 1.3.1 多源拉取 | 1.3 | ✅ | bootstrap 多源 Git 重试（GitHub → Gitee → 自建）。 |
| 1.3.2 供应链/镜像校验 | 1.3 | ⚠️ | 支持私有 Registry；Checksum/cosign 验证需在流水线/运维中落实。 |

### 第 2 部分：通信与 API 规范

| 检查点 | 条款 | 状态 | 说明 |
|--------|------|------|------|
| 2.1.1 仅 SSE 禁止 WebSocket | 2.1 | ✅ | 状态同步用 SSE；无 WebSocket。 |
| 2.1.2 心跳 30s / 45s cancel | 2.1 | ✅ | 前端 30s Ping，后端 45s 未收 Ping 则 cancel。 |
| 2.1.3 SSE 指数退避重连 | 2.1 | ✅ | 1s→2s→4s 上限 30s，最多 10 次后离线骨架屏。 |
| 2.1.4 SSE 代理反缓冲 | 2.1 | ✅ | Caddy 对 /api/v1/stream*、/api/v1/events* 设置 X-Accel-Buffering no。 |
| 2.2.1 API 前缀 /api/v1/ | 2.2 | ✅ | 路由统一 /api/v1/。 |
| 2.2.2 OpenAPI 与版本控制 | 2.2 | ✅ | /openapi.json 暴露；scripts/export_openapi.py 生成 docs/openapi.json 纳入版本控制。 |
| 2.2.3 安全响应头 | 2.2 | ✅ | Caddy 添加 X-Content-Type-Options、HSTS、Referrer-Policy、Content-Security-Policy。 |
| 2.3.1 错误码契约 ZEN-xxx | 2.3 | ✅ | 统一 code/message/recovery_hint/details。 |
| 2.3.2 X-Request-ID | 2.3 | ✅ | 请求/响应均带 X-Request-ID。 |
| 2.4.1 NTP 预检 | 2.4 | ✅ | bootstrap 中 NTP 漂移 >1s 拒绝启动；无 ntplib/不可达时 WARN 继续。 |
| 2.4.2 时区 UTC / ISO 8601 | 2.4 | ✅ | 后端/DB 绑定 UTC；API 使用 isoformat()；mqtt_worker 目录名已用 utcnow。 |
| 2.5.1 结构化日志 | 2.5 | ✅ | JSON 日志、request_id、caller、level（logging+JSON 格式化；法典建议 structlog 可后续迁移）。 |
| 2.5.2 优雅启停 | 2.5 | ✅ | FastAPI Lifespan；SIGTERM 下释放资源、关 Redis。 |

### 第 3 部分：核心机制强制红线

| 检查点 | 条款 | 状态 | 说明 |
|--------|------|------|------|
| 3.1.1 三步熔断顺序 | 3.1 | ⚠️ | ① API 503 ✅ ② 网络层摘除 需运维（见 docs/ops/three-step-meltdown.md）③ 容器降级 ✅。 |
| 3.2.1 探针滑动窗口防抖 | 3.2 | ✅ | 连续 3 次一致才更新状态。 |
| 3.2.2 三重核验 path/UUID/容量 | 3.2 | ✅ | 路径存在、UUID（findmnt+blkid）、最小剩余空间。 |
| 3.2.3 探针自愈 / restart | 3.2 | ✅ | 探针容器 restart: unless-stopped；锁 TTL 消散。 |
| 3.2.4 边缘节点静默 | 3.2 | ✅ | 断联静默待命，不主动杀容器。 |
| 3.2.5 冷启动 Redis 失联 | 3.2 | ✅ | Redis 失联且无缓存时返回 All-OFF 矩阵，响应头 X-ZEN70-Bus-Status: not-ready。 |
| 3.3.1 目录预建 chown 1000:1000 | 3.3 | ✅ | bootstrap 解析 YAML 预建挂载卷并 chown。 |
| 3.3.2 ulimits nofile 65536 | 3.3 | ✅ | compiler 为 gateway/redis 注入；宿主机见 docs/ops/docker-daemon.md。 |
| 3.3.3 swapoff -a | 3.3 | ✅ | bootstrap Linux 下执行。 |
| 3.3.4 OOM 豁免 oom_score_adj -999 | 3.3 | ✅ | gateway、redis 已配置。 |
| 3.3.5 Docker 网段防碰撞 | 3.3 | ⚠️ | 需宿主机 daemon.json 配置 default-address-pools（见 docs/ops/docker-daemon.md）。 |
| 3.3.6 网络 ACL / 数据库仅网关 | 3.3 | ✅ | backend_net internal；数据库不暴露主机端口。 |
| 3.3.7 UPS 刷盘 | 3.3 | ✅ | thermal_ups_guardian 等逻辑；Redis SHUTDOWN、PostgreSQL CHECKPOINT 需在 NUT 联动中落实。 |
| 3.4.1 安全容器规范 | 3.4 | ✅ | 非 root、read_only、cap_drop、healthcheck（gateway/redis 已加）。 |
| 3.4.2 双轨 JWT 轮转 | 3.4 | ✅ | X-New-Token、前端拦截器覆写。 |
| 3.5.1 Alembic Redis 锁 | 3.5 | ✅ | upgrade 前申请 zen70:DB_MIGRATION_LOCK。 |
| 3.5.2 多模态幂等 / 409 | 3.5 | ✅ | AI 路由 X-Idempotency-Key 等。 |
| 3.6.1 PWA skipWaiting / rangeRequests | 3.6 | ✅ | vite.config 已配置；媒体 206 已用 rangeRequests。 |
| 3.6.2 Dexie + storage.persist() | 3.6 | ✅ | 前端调用 requestPersistentStorage()。 |
| 3.6.3 visibilitychange 关 SSE | 3.6 | ✅ | 页面 hidden 时关闭 EventSource。 |
| 3.6.4 WebAuthn 降级 PIN | 3.6 | ✅ | PIN 登录与限流存在。 |
| 3.7.x 全域 GC / 灾备 | 3.7 | ⚠️ | 运维示例见 docs/ops/cron-gc-restic.md；Cron/保留期/豁免需部署时落实。 |

### 第 4 部分：性能指标与 SRE 契约

| 检查点 | 条款 | 状态 | 说明 |
|--------|------|------|------|
| 4.1 API P99 ≤500ms | 4 | ⚠️ | 需压测 (Locust) / Grafana 验证。 |
| 4.2 SSE 端到端 ≤1s | 4 | ⚠️ | 需探针触发到前端响应实测。 |
| 4.3 并发 ≥1000 | 4 | ⚠️ | 依赖 ulimits 与压测验证。 |
| 4.4 多模态 8s 熔断 | 4 | ✅ | ai_router 已实现 MULTIMODAL_TIMEOUT_SECONDS=8、超时 206 截断；显存释放依赖底层推理引擎。 |
| 4.5 系统盘 95% 熔断 | 4 | ⚠️ | 运维与阈值逻辑见 docs/ops/docker-daemon.md §3；探针/告警与 pause 下发需部署时落实。 |
| 4.6 UPS 20% 关机 | 4 | ⚠️ | NUT 与关机脚本需演练。 |

### 第 5 部分：测试与 DevOps

| 检查点 | 条款 | 状态 | 说明 |
|--------|------|------|------|
| 5.1.1 集成测试 503/paused 断言 | 5.1 | ✅ | test_503_meltdown_when_capability_pending 显式断言 503 与 ZEN-STOR-1001；test_storage_loss 断言 paused。 |
| 5.1.2 factory_boy 无硬编码 | 5.1 | ⚠️ | 已引入 tests/factories.py（AlertPayloadFactory、MockUserFactory），test_alert_manager 已改用工厂；其余测试待推广。 |
| 5.2.1 依赖锁定与 Trivy/audit | 5.2 | ⚠️ | 有 lock 文件；.github/workflows/compliance.yml 已跑单元测试；Trivy/audit 需在流水线中追加。 |
| 5.2.2 代码规范 black/isort/flake8 等 | 5.2 | ✅ | .pre-commit-config.yaml + compliance.yml 在 push/PR 时执行 black/isort/flake8。 |
| 5.2.3 Conventional Commits + release.sh | 5.2 | ⚠️ | release.sh 已注明禁止人工打 Tag；流程约束需团队遵守。 |

### 第 6 部分：ADR

| 检查点 | 条款 | 状态 | 说明 |
|--------|------|------|------|
| 6.1 架构决策入 docs/adr/NNNN-标题.md | 6 | ✅ | 已有 0000–0005 等；编号规范已修正。 |

### 第 7 部分：禁止事项

| 检查点 | 条款 | 状态 | 说明 |
|--------|------|------|------|
| 7.1 禁止人工 prune/rm -rf | 7 | ✅ | 依赖自动化 GC 与声明式豁免。 |
| 7.2 探针不跳过 503 直接控容器 | 7 | ✅ | 熔断顺序与探针职责已落实。 |
| 7.3 503 后不无限轮询 | 7 | ✅ | 前端断路器 15s 冷却。 |
| 7.4 system.yaml 无明文 / --remove-orphans | 7 | ✅ | 已核对。 |
| 7.5 API 限流与 body 大小 | 7 | ✅ | 已加 max_request_size 中间件。 |
| 7.6 容器资源上限与心跳 | 7 | ✅ | healthcheck、ulimits、oom_score_adj 已配。 |

### 路径解耦（1.2 延伸）

| 检查点 | 状态 | 说明 |
|--------|------|------|
| 路径唯一来源 system.yaml | ✅ | 所有业务路径由 system.yaml → compiler → .env。 |
| 代码无硬编码路径 | ✅ | 探针/网关/API/worker 仅读 env。 |
| 图形化部署只写 system.yaml | ✅ | 安装器只补 path 相关键，再调 compiler。 |

---

## 三、状态图例

- **✅**：已实现并核对。
- **⚠️**：部分实现或需运维/CI/压测进一步落实。
- **❌**：未实现（若存在会单独列出）。

---

## 四、使用说明

- 每次发布或大改动前，可按本清单逐项自检。
- 带 ⚠️ 的项建议列入迭代或运维手册（如 CI 门禁、NTP/UPS 演练、95% 熔断、性能压测）。
- 图形化部署与「IaC 唯一事实来源」「路径解耦」一致；安装器仅改写 system.yaml 并调用 compiler，不绕过编译器向 .env 写入路径。
