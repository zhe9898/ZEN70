# Docker 宿主机运维说明（法典 3.3）

以下配置需在**宿主机**完成，非容器内；用于满足 ZEN70 法典 3.3（Docker 网段防碰撞、系统级句柄扩容）。

---

## 1. Docker 网段防碰撞（default-address-pools）

**目的**：将 Docker 默认网段限制在生僻网段，避免与局域网/VPN 路由碰撞。

**操作**：编辑 `/etc/docker/daemon.json`（Linux）或 Docker Desktop 设置中的 daemon 配置，增加：

```json
{
  "default-address-pools": [
    {
      "base": "10.200.0.0/16",
      "size": 24
    }
  ]
}
```

修改后执行 `systemctl restart docker`（或 Docker Desktop 重启），使配置生效。

---

## 2. 系统级句柄扩容（nofile）

**目的**：防止高并发下出现 `Too many open files`；与 compose 中 `ulimits: nofile: 65536:65536` 配合。

**操作**：在宿主机 `/etc/security/limits.conf` 中增加（或确认已有）：

```
* soft nofile 65536
* hard nofile 65536
```

对 systemd 管理的服务，可额外在对应 service 文件中设置 `LimitNOFILE=65536`。

---

## 3. 系统盘 95% 熔断（法典 4.5）

**目的**：系统盘使用率超过 95% 时触发只读/熔断，防止死锁与进一步写满。

**建议**：由监控（Categraf/Prometheus）采集根分区或指定系统盘使用率；告警触发后按「三步熔断」执行：① API 503 ② 网络层摘除 ③ 对高频写组件执行 `docker pause`。探针或独立脚本可轮询 `df` 输出，超过阈值时写入 Redis 全局锁，由网关统一 503；必要时由运维下发 `docker pause` 指定容器。

---

## 4. 参考

- 法典 3.3：Docker 网段防碰撞、强制系统级句柄扩容。
- 容器内 `ulimits` 与 `oom_score_adj` 已由 `scripts/compiler.py` 生成到 `docker-compose.yml`（gateway、redis）。
