# ZEN70: 极客私有边缘云架构与业务全景白皮书 (V2.0)

> "A Secure, AI-Augmented Digital Vault for the Modern Family."

## 第一部分：系统底座与物理架构 (Architecture & Infrastructure)

ZEN70 是一个专为追求极致数据掌控力与性能的“全栈极客家庭”打造的私有边缘云系统。它彻底摒弃了公有云的订阅制租赁模型，采用“本地算力为主、云端大模型增强为辅”的混合计算架构。

### 1. 核心技术栈 (Technology Stack)
*   **网关与边缘代理层 (Edge Proxy)**: `Caddy` - 自动管理 Let's Encrypt / ZeroSSL 证书，提供极低延迟的 HTTP/3 反向代理。
*   **零信任组网层 (Zero-Trust Mesh)**: `Headscale / WireGuard` - 负责异地设备（异地父母、公司电脑）安全接入内网，实现物理级内网穿透与隧道加密。
*   **后端大脑层 (API Gateway & Core Logic)**: `Python 3.11+ & FastAPI` - 采用纯异步 (Asyncio) 机制，提供极高吞吐量的 RESTful API 与 SSE (Server-Sent Events) 长连接推送。
*   **分布式事务与持久层 (Persistence)**:
    *   `PostgreSQL 15`: 作为架构的“绝对真理 (Single Source of Truth)”，存储用户、资产元数据及权限策略。
    *   `Redis 7`: 作为高并发神经总线，负责限流 (Rate Limiting)、分布式锁、熔断状态控制、SSE 订阅发布 (Pub/Sub) 及 AI 离线任务队列。
*   **前端交互与渲染层 (Presentation)**:
    *   `Vue 3 (Composition API) + Vite`
    *   `Pinia` (状态域管理)、`Tailwind CSS + DaisyUI` (现代极简原子化 UI 设计)
*   **算力异构与向量引力场 (AI Compute Space)**:
    *   `sentence-transformers/clip` + CPU/GPU Worker (独立守护进程) 负责跨模态特征提取。
    *   `pgvector` (`IVFFlat` 索引) 负责 PostgreSQL 层面的高维相近语义极速检索。

### 2. SRE 与高可用工程学模型 (SRE & Engineering)
*   **双极断路器 (Circuit Breakers)**: 后端网关挂载 `Sentinel` 探针检查 DB/Redis 健康度；前端 Axios 拦截器捕获 503/504 错误并触发毛玻璃 PWA “维护中”降级屏障，有效防止重试风暴击穿网关。
*   **幂等调度闸 (Idempotency)**: 核心 AI 节点请求携带 `X-Idempotency-Key`，拦截网络抖动带来的重复计算损耗。

---

## 第二部分：七大核心业务矩阵 (Business Features Matrix)

### M1. 零信任安全与租户域隔离 (Zero-Trust RBAC)
*   **数字隔离**: 通过 PostgreSQL 的 RLS (Row-Level Security) 在数据最底层实施物理隔离，代码层即使存在越权逻辑，也无法读取其他租户 (Tenant) 的“相册或心跳”。
*   **双轨制 JWT 令牌 (Dual-Track JWT)**: 通过 Header (`Authorization`) 和无感刷新机制提供极具安全性的短生命周期令牌，完美防范 XSS 与 CSRF 劫持。
*   **家庭角色体系 (Family Roles)**: 内置 `admin` (管理员/极客)、`elder` (长辈 - 默认极简 UI 与防范式兜底)、`child` (过滤敏感信息)。

### M2. 实时神经中枢与设备感知 (Real-time SSE Dashboard)
*   建立单向高效的 Server-Sent Events 流。
*   动态掌控服务器的 CPU/内存水位、Redis/Postgres 集群健康度，并将硬件指标实时投射至“极客控制台”仪表盘。

### M3. 边缘 Web Push 入侵感知 (VAPID Web Push)
*   采用 `pywebpush` 生成的 ECDSA 椭圆曲线加密。
*   前端 Service Worker 挂载 `PushManager`，即使用户关闭了浏览器标签页，私有云也能绕过微信/苹果的中心化服务器，直接向 Android/iOS 设备投递零延迟的“入侵侦测”原生横幅报警。

### M4. AI 视觉感知与记忆追溯 (AI Vision Matrix)
*   **物理层解耦**: 彻底剥离传统的堵塞型 AI 推理模型。新上传的照片与视频由独立的 `ai_worker.py` (后台守护进程) 读取。
*   **跨模态特征映射**: 使用 `CLIP` 视觉语言模型，将物理图像降维转换为 512 维的纯数学向量浮点数组。
*   **✨ 智能语义追溯 (Semantic Search)**: "一条红色的狗在草地上跑"。彻底告别原始的文件名和时间戳，系统将理解用户的自然语言并基于 `Cosine Distance` 瞬间在 pgvector 库中锁定那些高光的瞬间。

### M5. 端云混合算力无缝换挡 (Hybrid Compute Toggle)
*   支持在 JWT 层瞬间切换 AI 的执行策略。
*   **🛡️ 绝对私有 (Local)**: 敏感请求 (如家庭私密照片解析) 彻底断网运行。
*   **☁️ 云端增强 (Cloud)**: 当算力瓶颈时，调用并伪装请求路由至第三方顶尖大模型代理点获取爆发性智能扩展。

### M6. 现代极简“数字画廊”界面 (UI Aesthetics)
*   **Masonry 瀑布流引擎**: 采用 CSS Column 级自排版引擎，淘汰古典的刚性格栅，展现无垠的内容张力。
*   **沉浸式定制壁纸 (Custom Wallpaper Engine)**: 应用在全局注入极致高斯模糊效果，支持用户自传私人精美照片作为底色。
*   **分类与直觉交互 (Tabs & FAB)**: 依托 Vue Computed 极速切片的“情绪时刻(Emotion)”与“视频(Video)”相册卡组。废止笨重的上传框，导入现代极简主义的悬浮动态上传核 (Floating Action Button)。

### M7. 动态全量与增量灾备 (Disaster Recovery Checkpoints)
*   通过 `scripts/backup.py` 提供数据库和静态 `media` 的热备份。
*   前端在断网失联状态下提示“存储受限警告”，强制提醒离线状态的非一致性。
