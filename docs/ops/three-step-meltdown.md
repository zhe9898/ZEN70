# 三步极刑熔断顺序（法典 3.1）运维说明

硬件掉线或温度超限时，**严禁**网关直接越权操作容器，必须严格按序执行以下三步。

---

## 1. API 层熔断

- **含义**：网关抛出 **503 Service Unavailable**，拒绝新任务。
- **现状**：探针/温控将熔断状态写入 Redis，网关读取能力矩阵后对写请求返回 503；或 thermal_ups_guardian 注入全局阻塞锁，网关统一 503。
- **无需额外运维**：由现有网关与探针逻辑自动完成。

---

## 2. 网络层断流

- **含义**：从 Nginx/Caddy **摘除路由**，屏蔽对后端 API 的转发，避免请求继续打到已熔断的服务。
- **现状**：未自动化，需运维在熔断后**手动或通过脚本**摘除路由。

### Caddy 2 操作示例

**方式 A：修改 Caddyfile 后重载**

1. 编辑 `config/Caddyfile`，将 `handle /api/*` 块注释或改为返回 503：
   ```caddyfile
   # handle /api/* {
   #     reverse_proxy gateway:8000
   # }
   handle /api/* {
       respond "Service Unavailable" 503
   }
   ```
2. 重载 Caddy：`docker exec zen70-caddy caddy reload --config /etc/caddy/Caddyfile`
   - 或宿主机：`docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile`

**方式 B：Caddy Admin API（若已开启）**

- 若 Caddy 配置了 admin 接口，可通过 API 动态修改配置并 reload（此处不展开）。

熔断解除后，恢复 `handle /api/*` 为 `reverse_proxy gateway:8000` 并再次 `caddy reload`。

---

## 3. 容器级降级

- **含义**：向底层下发指令：纯 I/O 容器 `docker pause`（3s 异步超时升级 SIGKILL）；有状态服务 `docker stop -t 10`。
- **现状**：由 **topology_sentinel**、**thermal_ups_guardian** 等在检测到异常后执行 `docker pause` 等，无需常规人工干预。

---

## 小结

| 步骤       | 负责方           | 自动化情况 |
|------------|------------------|------------|
| 1. API 503 | 网关 + Redis 状态 | 已自动     |
| 2. 网络摘除 | Caddy/运维       | 需手动或脚本 |
| 3. 容器降级 | 探针/温控        | 已自动     |

后续若需将「网络层摘除」自动化，可考虑：熔断时由探针或网关调用 Caddy Admin API、或通过编排将 Caddy 的 `/api` 上游切换为本地 503 占位服务。
