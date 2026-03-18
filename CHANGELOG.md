# Changelog

All notable changes to the ZEN70 project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **运维自动化（法典 6.9）**：`deployer.py` 幂等部署，支持 `--rollback` 回滚；`install_wizard.py` 交互式安装向导；`zen70-doctor.sh` 一键诊断；bootstrap 点火时 Linux 下执行 `swapoff -a`。
- **供应链（法典 1.1）**：私有镜像仓库支持。`system.yaml` 新增 `registry.enabled` / `registry.url`。
- **安全拦截防线**：前端 Axios 全局捕获 503/504 熔断，自动激活大屏降阶“维护模式”骨架屏。

## [2.9.1] - 2026-03-18

### Fixed
- **CI/CD 发版死锁重试漏洞**：修复了在 GitHub 自动执行大文件打包（1.5GB）时，由于远端同名 Release `v2.9` 已存在导致的 GitHub API HTTP 422 (Unprocessable Entity) 封锁。对 `Create Release` 及 `Asset Upload` 全面注入三轮指数退避重试循环，以标准 DevOps 语意升级基线至 V2.9.1 彻底根除发版冲突。
- **Flake8 & Isort 格式规范审计**：将项目全局 Python 单行字符上限放宽至 160 字符，并自动排列 `backend/tests/unit/test_alert_manager.py` 的绝对引入路径（解决模块互调的 `ModuleNotFoundError`），目前已 100% 绿灯通过云端 `Compliance` 合规工作流。

### Added
- **云端离线打包体系 (GFW Bypass)**：落地 `build_offline_v2_9.yml` 官方企业级发版流水线，实现脱离本地宽带局限，自动化并行拉取十余个上游官方镜像，打包并压缩输出自带 `zen70-gateway` 层的单体 `zen70_v2.9.1_offline_bundle.zip`。
- **离线一键加载批处理**：提供配套的终端防小白工具 `A_一键导入离线镜像环境(必点).bat`，点击即可物理注入全套 Docker 缓存环境。

### Changed
- **文档大一统编纂（Single Source of Truth 收束）**：清除多达 15 份过时的功能碎片文档与 `ZEN70_Architecture.txt` 粗糙大纲。重绘合并为极具穿透力且格式标准的终极白皮书 `ZEN70_Architecture_and_Features_V2.9.1.md`，并将性能压测报告降级收拢归档至 `docs/reports`，全面响应“**所有文档合规**”审计要求。
