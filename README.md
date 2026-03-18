# ZEN70 私有云 (The Ultimate SRE Fortress)

拥有极高物理防腐能力、跨端平权、且彻底与硬件型号解耦的家庭 AI 私有云底座。

---

## 极速启动 (Zero-Day Bootstrapping)

任何拿到这份代码的朋友或运维人员，**仅需一步**即可通过绝美的图形化 UI 拉起全域系统：

```bash
# 一键触发 Web 图形化安装向导
python start_installer.py
```
*(运行后，按提示在您的浏览器中访问 `http://127.0.0.1:8080` 即可开启向导！)*

**前置要求**：宿主机已安装 Docker，且 Daemon 处于运行状态。

该脚本具备**绝对幂等性**，可反复执行而不会破坏已有状态。点火成功后，脚本会**自动执行基于容器原生 `health.Status` 的全自动基座验真探针**（遵循 ZEN70 T-02 规范），无需手动执行任何 `docker` 验证命令，验证通过即代表基座全线绿灯。

---

## 🛜 中国大陆特供：V2.9 全原厂离线防波堤版 (绝对隔离)

由于 GFW 防火长城对 Docker Hub 的阻断，导致国内直连拉取镜像 100% 会触发超时死锁或 `toomanyrequests` 限流。
为彻底根治此问题，系统目前已接入 **企业级 GitHub Actions 云端流水线**。所有的编译、拉取、打包工作均在海外云端完成，输出 100% 纯净、幂等的开箱即用离线包。

**极简离线安装流程 (无需任何代理/加速器)：**
1. 访问我们官方的 Releases 页面：👉 `https://github.com/zhe9898/ZEN70/releases`
2. 下载最新释出的 **`zen70_v2.9_offline_bundle.zip`** (约 1.5GB)。
3. 解压缩包至任意目录。
4. **【核心步骤】**：双击执行 `A_一键导入离线镜像环境(必点).bat`。系统会静默将 15 个原厂容器镜像瞬间打入宿主机 Docker 缓存！
5. 导入完成后，像往常一样双击 `zen70_start.bat` 一键点火升空，纵享丝滑！

---

## 🔄 无感升级与容器热更 (Zero-Downtime Upgrade)

如果您修改了 `system.yaml` 或者后端/前端的代码并希望更新您本地离线的系统，整个过程可以在**系统不掉线**的情况下平滑完成：

1. 将您的代码更改 `git push` 推送至您的 GitHub 仓库主干。
2. 访问仓库的 **Actions** 页面，在左侧找到 **Build V2.9 Offline Bundle**，点击 **Run workflow** 手动触发一次全新的云端私有构建。
3. 待构建完成后，前往 Releases 页面下载最新生成的 ZIP 环境包覆盖至本地。
4. 双击运行 `A_一键导入离线镜像环境(必点).bat` 注入新版本镜像。
5. **无需停止现有系统！** 请直接双击 `zen70_start.bat`。
   - *(由于系统集成了企业级 `update_config: order: start-first` 滚动更新策略，Docker Compose 会自动先启动新版容器，待健康探针测试通过后，再平滑切断并销毁旧容器，实现极其优雅的**无感热替换**！)*

---

## 核心架构目标

- **绝对解耦**：软件逻辑与硬件型号彻底切割，硬件仅作为抽象「能力」存在。
- **IaC 唯一事实来源**：所有全栈配置收束于 `system.yaml`。
- **物理防腐大闸**：探针感应、容器冻结与前端骨架屏安抚。
- **跨端平权**：PWA 覆盖、WebAuthn 无密鉴权。

---

## 目录层级

| 目录 | 说明 |
|------|------|
| `backend/` | FastAPI 异步高并发中枢 |
| `frontend/` | Vue 3 + Vite 协议驱动渲染 |
| `scripts/` | 点火脚本、配置编译器、验真探针 |
| `config/` | IaC 配置 `system.yaml` |
| `docs/` | **[架构设计书 (ZEN70_Architecture_Design_V3.0.md)](docs/ZEN70_Architecture_Design_V3.0.md)** <br> **[核心业务原素 (ZEN70_Business_Features_V3.0.md)](docs/ZEN70_Business_Features_V3.0.md)** |
| `tests/` | 单元/集成/E2E 测试 |

---

## 点火参数

| 参数 | 说明 |
|------|------|
| `--skip-pull` | 跳过多源拉取，使用已有 system.yaml |
| `--offline` | 离线模式 |
| `--no-up` | 仅预检 + 编译，不启动容器 |
| `--skip-mounts` | 跳过挂载点预建 |
| `-v` | 详细日志 |

---

## 运维工具

| 脚本 | 说明 |
|------|------|
| `python start_installer.py` | 🌟 全新 Web 傻瓜式图形部署向导 (V3.0) |
| `python scripts/bootstrap.py` | 硬核命令行一键点火脚本 |
| `python scripts/install_wizard.py` | 交互式终端安装向导 |
| `python scripts/deployer.py` | 幂等部署（支持 `--rollback` 回滚） |
| `./zen70-doctor.sh` | 一键诊断（Docker、磁盘、容器状态） |

---

## 🛡️ 架构红线与 PR 审查强制清单 (Absolute Decoupling)

任何提交至本仓库的 Pull Request 必须满足以下三条 **“绝对解耦”** 红线，否则严禁合入：

- [ ] **1. 硬件零硬编码 (Hardware Decoupling)**
  - 探针及业务代码仅通过“能力标签”（如 `["gpu_nvenc_v1"]`）进行握手与调度，严禁写死型号、PCI 地址。
  - 严禁拼接原生 `os.path`，必须彻底使用跨平台的 `pathlib.Path` 解析。
- [ ] **2. IaC 隔离断崖 (IaC as Single Source of Truth)**
  - 严禁手动编写 `docker-compose.yml`、`.env` 或是 Nginx / Caddy 配置。
  - 一切系统变量和镜像映射必须从 `system.yaml` 中产生并经由 `compiler.py` 编译流转，代码内只允许 `os.getenv()` 提取。
- [ ] **3. 协议驱动 UI (Schema-Driven Rendering)**
  - 前端 `frontend/src` 内部严禁包含任何硬编码的服务卡片或逻辑开关。
  - 面板渲染视图必须 100% 依赖拉取的 `/api/v1/capabilities` 后端矩阵进行 `v-for` 循环遍历与生成。
