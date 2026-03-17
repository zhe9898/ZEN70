# ZEN70 V2.0 图形化部署与点火引擎指南

本指南详细剖析了 ZEN70 系统从裸机环境（Zero-to-Hero）到全栈服务上线的“点火（Bootstrap）”与“编译（Compile）”流程。

我们摒弃了传统繁琐的人工环境配置，采用 `scripts/bootstrap.py` 作为统一入口，利用配置编译器自动生成 Docker 环境。

## 部署核心流程全景图

下图展示了从触发部署到最终微服务群体上线的全生命周期节点：

```mermaid
stateDiagram-v2
    [*] --> 预检诊断阶段: 执行 python scripts/bootstrap.py
    
    state 预检诊断阶段 {
        Docker可用性检测 --> 端口冲突侦测: (探测 80/443/8000)
        端口冲突侦测 --> 磁盘容量校验: (>20GB)
        磁盘容量校验 --> NTP时间漂移审计: (漂移<1s)
        NTP时间漂移审计 --> 内核级安全阻断: (强制 swapoff -a)
    }

    预检诊断阶段 --> 多源配置拉取

    state 多源配置拉取 {
        GitHub(主源) --> Gitee(容灾源): Timeout/Error
        Gitee(容灾源) --> 本地缓存(离线模式): 极寒断网环境
        本地缓存(离线模式) --> Checksum指纹校验: (防篡改)
    }

    多源配置拉取 --> 点火编译期

    state 点火编译期 {
        预建宿主机挂载点 --> 配置编译器(compiler.py): (chown 1000:1000 宿主防夺舍)
        配置编译器(compiler.py) --> 生成强随机凭证: (POSTGRES_PASSWORD, JWT等)
        生成强随机凭证 --> 模板渲染: (输出 docker-compose.yml & .env)
    }

    点火编译期 --> 容器编排启爆

    state 容器编排启爆 {
        验证镜像指纹(images.manifest) --> 启动大动脉隧道: (先启 cloudflared)
        启动大动脉隧道 --> 启动核心集群: (docker compose up -d)
    }

    容器编排启爆 --> [*]: 系统 100% Online
```

---

## IaC 配置流式转换架构 (Schema Pipeline)

由于 ZEN70 遵守配置与环境“绝对解耦”原则，我们通过编译环节动态映射所有机密凭证。以下为配置渲染引擎的数据流向：

```mermaid
graph TD
    A[system.yaml (唯一声明式事实)] -->|读取配置拓扑| C(scripts/compiler.py)
    B[系统环境变量 (OS Env)] -->|注入现有令牌| C
    E[预置密钥库 (.env)] -.->|读取持久化密码| C

    C -->|分析并动态补全缺失密码 (32位高强随机)| F[凭证熔炉 (Secret Generator)]
    F -->|输出变量安全字典| C
    
    C -->|渲染 Jinja2 引擎| D1((docker-compose.yml))
    C -->|渲染 Jinja2 引擎| D2((.env 运行时变体))
    
    D1 --> G[Docker Compose Runtime]
    D2 --> G
    
    subgraph Jinja 模板底库
        T1(docker-compose.yml.j2)
        T2(.env.j2)
    end
    T1 -.-> C
    T2 -.-> C

    style C fill:#0ea5e9,stroke:#0284c7,stroke-width:2px,color:white
    style G fill:#10b981,stroke:#059669,stroke-width:2px,color:white
```

---

## 防脑裂探针接管拓扑层 (Sentinel Topology)

系统拉起后，探针 `Topology Sentinel` 将实时守卫星系级的底层 I/O 与温度状态：

```mermaid
sequenceDiagram
    participant 容器 (Docker)
    participant 网关 (Gateway)
    participant Redis (中心脑)
    participant Sentinel (探针守护者)
    participant Host OS (系统底座)

    Sentinel->>Host OS: 1. 监测挂载点 / GPU 温度 / UPS 电量
    Host OS-->>Sentinel: 挂载点丢失 (Disk Offline)
    Sentinel->>Sentinel: 2. 三次滑动窗口防抖 (确认非偶发抽风)
    Sentinel->>Redis: 3. 写入 PENDING 悲观锁
    Sentinel->>网关: 4. 发布硬件变更 Event
    网关-->>网关: 立即切断 API，全部返回 503 (接口熔断)
    Sentinel->>容器: 5. 跨界执行 `docker pause` 重型转码容器
    Note over Sentinel,容器: 防止容器向不存在的磁盘疯狂写满内存，保全系统盘！
    
    Host OS-->>Sentinel: 6. 磁盘重新供电/挂载恢复
    Sentinel->>Host OS: 7. 执行 findmnt & blkid 交叉核验 UUID
    Host OS-->>Sentinel: 核验通过 (是真的那个盘)
    Sentinel->>Redis: 8. 撤销悲观锁写入 ONLINE
    Sentinel->>容器: 9. `docker unpause` 唤醒重载
    网关-->>网关: 恢复 200 OK 调度服务
```

## 极速起飞指令

**前置依赖**：一台运行现代 Linux 发行版（如 Debian 12 / Ubuntu 22.04）并安装了 Docker 的宿主机。

```bash
# 仅仅一行命令即可点火整个航母战斗群
sudo python3 scripts/bootstrap.py
```
