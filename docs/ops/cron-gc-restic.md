# 全域 GC 与灾备 Cron（法典 3.7）

以下为法典 3.7「全域自动化 GC 与灾备」的**运维落实示例**。需在部署环境中按需配置 cron 或 systemd timer，并核对保留期与受保护资产。

---

## 1. 容器级 GC（法典 3.7.1）

**目的**：定期清理悬空镜像与废弃卷，避免磁盘被占满；**严禁**清理带 `zen70.gc.keep=true` 的容器/卷。

**示例（每周一次，低峰期）**：

```bash
# 仅清理无 zen70.gc.keep 标签的悬空资源；保留带 zen70.gc.keep=true 的资产
docker system prune -a --volumes --force --filter "label!=zen70.gc.keep=true"
```

建议：在 compose 或 system.yaml 中为核心服务（gateway、redis、数据库、探针）的镜像/卷打上 `zen70.gc.keep=true`，避免被 prune 误删。

---

## 2. 灾备级 GC：Restic forget --prune（法典 3.7.2）

**目的**：Restic 推流到 S3 后执行 `forget --prune` 裁剪旧快照；保留期需大于 S3 Object Lock（如 30 天）。

**示例**：

```bash
restic -r s3:s3.amazonaws.com/your-bucket forget --keep-within 30d --prune
```

对需永久保留的快照使用 `restic tag --set keep-forever <snapshot-id>`，forget 时排除该标签。

---

## 3. 应用级 / PostgreSQL（法典 3.7.3）

- **PostgreSQL**：确保 `autovacuum` 开启；低峰期可手动执行 `VACUUM ANALYZE`。
- **多媒体转码残骸**：由应用或独立脚本定期清理临时文件与失败任务产物。

---

## 4. 不可删除区域（法典 3.7 豁免）

- 在 IaC 中为核心资产配置 `protected: true`（如 `zen70.gc.keep=true` 标签、Restic `keep-forever`、物理目录 `/mnt/data/archive` 黑名单）。
- 自动化清理与 95% 熔断脚本**禁止**触碰上述受保护资产。

---

## 5. 参考

- 法典 3.7：容器 GC、Restic forget、autovacuum、protected 声明式豁免。
- 检查点：`docs/ARCHITECTURE_CHECKPOINTS.md` 3.7.x。
