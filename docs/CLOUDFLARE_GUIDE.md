# 🌐 ZEN70 + Cloudflare Zero Trust 穿透配置完全指南

这是针对部署 ZEN70 时，使用 Cloudflare Tunnel 进行外网穿透的图文补充说明。
如果你在访问你的域名时遇到了 **“错误 1033：Cloudflare 隧道错误 (Error 1033: Argo Tunnel error)”**，说明你已经成功连接了隧道（点火成功），但**尚未在 Cloudflare 后台配置「公共主机名 (Public Hostname)」路由**。

请严格按照以下步骤完成最后一步配置：

## 🛑 避坑指南：千万别下载安装 Cloudflare 客户端！

当你第一次在 Cloudflare 后台创建隧道时，它会展示一个页面，让你选择操作系统（Windows/macOS/Linux），并提供诸如“下载 `cloudflared-windows-amd64.msi`”、“打开命令提示符运行……”等 4 个步骤。

**请绝对、千万、务必不要照做！不要下载那个 msi，也不要在你的电脑上运行那行代码！**

ZEN70 架构的精髓在于**纯净的容器化**。它的底层已经内置了原生的 Docker 版 Cloudflared 连接器，部署时会自动拉起，绝不会弄脏您的 Windows 宿主机。

**你唯一要做的：**
在它给你的那段长长的、类似 `cloudflared.exe service install eyJhIj...` 的代码里，**只用鼠标拖蓝选中并且复制最后面的那串 `eyJh...` 开头的乱码**。不管你是选的哪个操作系统页面，这串 Token 密码都是一样的。把这串 Token 粘贴到我们的部署网页里即可。

---

## 🚨 解决 1033 错误的终极方案：添加路线 (Public Hostname)

1️⃣ **回到 Cloudflare Zero Trust 工作台**
- 在左侧菜单找到 `Networks` -> `Tunnels`。
- 找到你刚才创建的隧道（状态应该是 `Active` 绿色的），点击右侧的 `Configure`（配置）。

2️⃣ **添加公共主机名 (Public Hostname)**
- 在隧道配置页面，点击顶部的 **`Public Hostname`** 选项卡。
- 点击右侧的蓝色按钮 **`Add a public hostname` (添加路线 / 添加公共主机名)**。

3️⃣ **填写路由映射表（最关键的一步！）**
在弹出的「添加路线」窗口中，请这样填写：

### 【Public Hostname (外网访问信息)】
- **Subdomain (子域名)**: 如果你要用 `nas.zen70.cn` 访问，就填 `nas`。如果你要用顶级域名 `zen70.cn` 访问，这里**留空不要填**！
- **Domain (域名)**: 下拉选择你的域名（例如 `zen70.cn`）。
- **Path (路径)**: **留空不要填**。

### 【Service (内网服务信息)】
- **Type (类型)**: 下拉选择 **`HTTP`** （注意，就算你要 HTTPS 访问，这里内网也必须选 HTTP）。
- **URL**: 填写 **`localhost:8000`** （这是因为我们 ZEN70 的网关默认暴露在本地的 8000 端口）。

4️⃣ **保存配置**
- 点击右下角的 **`Save hostname` (保存主机名)**。

---

## 🎉 验收成果
保存成功后，等待大约 15 秒钟的全球 DNS 同步。
现在，打开你手机上的游览器（断开家里 WiFi，使用 5G 移动网络测试），直接输入：
`http://zen70.cn` （或者你配置的域名）

你就能看到 ZEN70 的网关或控制台界面了！1033 错误彻底消失。

> **💡 为什么会有 1033 错误？**
> 当你把 `eyJh...` 的 Token 喂给部署工具时，工具确实帮你把你家电脑连上了 Cloudflare 的网。但是，Cloudflare 作为门卫，它虽然接到了网线的另一端，却不知道当外人访问 `zen70.cn` 时，要把流量送往你家电脑里的哪个管子（ZEN70 占用的是 8000 端口管子）。我们刚才配置的 `localhost:8000` 就是告诉门卫指路的动作！
