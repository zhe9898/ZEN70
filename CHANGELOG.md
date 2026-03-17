\# Changelog



All notable changes to the ZEN70 project will be documented in this file.



The format is based on \[Keep a Changelog](https://keepachangelog.com/en/1.0.0/),

and this project adheres to \[Semantic Versioning](https://semver.org/spec/v2.0.0.html).



\## \[Unreleased]

\### Added

\- **运维自动化（法典 6.9）**：`deployer.py` 幂等部署，支持 `--rollback` 回滚；`install_wizard.py` 交互式安装向导；`zen70-doctor.sh` 一键诊断；bootstrap 点火时 Linux 下执行 `swapoff -a`。

\- **供应链（法典 1.1）**：私有镜像仓库支持。`system.yaml` 新增 `registry.enabled` / `registry.url`；启用时编译器为预拉取镜像加上 registry 前缀，`.env` 支持 `REGISTRY_URL` / `REGISTRY_USER` / `REGISTRY_PASSWORD`；bootstrap 在 compose up 前根据 `.env` 执行 `docker login`。

\- **供应链**：可选镜像 digest 校验。在 `system.yaml` 同目录创建 `images.manifest`（格式：`image:tag sha256:digest`），bootstrap 会在 compose up 前拉取并校验 digest，不匹配时告警。提供 `config/images.manifest.sample` 示例。

\- 初始化 ZEN70 工程目录结构 (backend, frontend, config, deploy, docs, tests)。

\- 引入 `.cursorrules` 全局系统提示词与架构规范文件。

\- 添加 `.gitignore` 配置文件，设置各技术栈的基础忽略规则与数据隔离防线。

\- 添加 `.github/workflows/ci.yml` 持续集成流水线基础配置。

\- 添加 `README.md` 项目核心声明文档。

\- 归档《ZEN70 架构实施》至 docs 目录。

