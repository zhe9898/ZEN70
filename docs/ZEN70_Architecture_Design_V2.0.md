# ZEN70: 极客私有边缘云架构设计书 (V2.0)

> "A Secure, AI-Augmented Digital Vault for the Modern Family."

## 1. 核心物理架构与计算栈 (Architecture & Infrastructure)

ZEN70 是一个专为追求极致数据掌控力与性能的“全栈极客家庭”打造的私有边缘云系统。它彻底摒弃了公有云的订阅制租赁模型，采用“本地算力为主、云端大模型增强为辅”的最终一致性混合计算架构。

### 1.1 网关与边缘通信层 (Edge Proxy & Zero-Trust Mesh)
*   **网关边缘**: 采用 `Caddy`。全权负责自动挂载 Let's Encrypt / ZeroSSL 证书的 ACME 挑战，提供极低延迟的 HTTP/3 及 QUIC 反向代理。
*   **零信任网格**: 使用 `Headscale` 驱动的 `WireGuard` 控制面。彻底隐匿暴露面，异地设备通过 P2P 隧道或加密 Relay 回源内网，实现物理底层的内网穿透与终端加密握手。

### 1.2 大脑控制平面 (API Gateway & Core Logic)
*   **框架**: `Python 3.11+ & FastAPI`。
*   基于 ASGI 标准的纯异步 (Asyncio) 非阻塞 IO，承载高吞吐 RESTful 控制命令。
*   建立由协程维护的 SSE (Server-Sent Events) 长连接隧道，向前端投递无感的实时神经元状态。

### 1.3 分布式事务与持久层 (Persistence)
*   **绝对真理库**: `PostgreSQL 15`。承载一切强一致性数据（用户数据、资产元数据、鉴权分配）。通过 RLS (行级安全策略) 实现数据库引擎级的租户域物理隔离。
*   **高并发神经总线**: `Redis 7`。负责：
    *   全 API 入口的动态令牌桶限流 (Rate Limiting)。
    *   主从/集群拓扑与分布式互斥锁。
    *   哨兵降级状态控制 (Circuit Breaker State Machine)。
    *   AI 耗时任务的异步队列 (Job Queue)。

### 1.4 AI 异构算力与引力场 (AI Compute Space)
*   **解耦式工人节点**: `ai_worker.py`。分离部署的重计算负荷守护进程。
*   **跨模态特征提取**: `sentence-transformers/clip-ViT-B-32-multilingual-v1` 本地或 GPU 侧化运行。
*   **向量引擎**: `pgvector`。为 `PostgreSQL` 内挂载 `IVFFlat` 索引，支撑 512 维环境下的 Cosine Distance 相似度度量，为自然语言提供空间检索。

### 1.5 跨端平权与渲染层 (Presentation)
*   `Vue 3` 底层协议驱动架构，`Vite` 极速热更新打包。
*   基于 `Pinia` 的客户端状态切片，基于 `Tailwind CSS + DaisyUI` 的现代极简原子化 UI 设计引擎。

## 2. SRE 与高可用工程学模型 (Site Reliability Engineering)

### 2.1 双极断路器 (Circuit Breakers)
为了避免硬件高负载或网络抖动引起重试风暴（Retry Storm），ZEN70 实装了两级串接断路防御：
*   **后端探针熔断**: 守护线程 `topology_sentinel.py` 1 赫兹低频探测 DB/Redis。一旦失联立即翻转 Redis 哨兵位。
*   **前端毛玻璃降级屏障**: 拦截器捕获到核心端点返回 503 或 504 时，立即拔除当前发散请求并在全局唤起 `zen70-maintenance-mode` 维护状态。不进行重试以免击穿网关，用户可见设备暂不可用骨架屏。

### 2.2 幂等调度闸 (Idempotency)
核心状态突变节点 (如触发大模型生成) 使用 `X-Idempotency-Key` 作为校验防重器。网络超时触发的前端多次重发将仅在计算空间里落盘并执行一次，保证系统账本的不变性。
