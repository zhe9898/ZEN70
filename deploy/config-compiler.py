#!/usr/bin/env python3
"""
ZEN70 配置编译器 (IaC)。

读取单体 config/system.yaml 或 config/conf.d/*.yml 碎片并合并配置树；
根据 config_version 自动迁移配置；
使用 Jinja2 渲染 deploy/templates/ 模板，生成彻底隔离的 .env 与 docker-compose.yml。
遵循 pathlib、强类型、JSON 结构化日志与异常处理强制规范。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jinja2
import yaml

# -------------------- 常量 --------------------
CURRENT_CONFIG_VERSION = 2

# -------------------- 结构化日志 --------------------


class JsonFormatter(logging.Formatter):
    """
    自定义 JSON 日志格式化器，对齐 Loki 收集标准。

    每条日志输出为单行 JSON，包含 timestamp（UTC ISO8601）、level、logger、
    caller（文件名:行号）、message、request_id；若存在异常则包含 exception 字段。
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "caller": f"{record.pathname}:{record.lineno}",
            "message": record.getMessage(),
            "X-Request-ID": getattr(record, "request_id", None),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(request_id: Optional[str] = None) -> logging.LoggerAdapter:
    """
    配置全局 JSON 日志并返回带 request_id 的 LoggerAdapter。

    Args:
        request_id: 编译期请求追踪 ID；若为 None 则自动生成 UUID。

    Returns:
        绑定 request_id 的 LoggerAdapter，每条日志的 record 均带 request_id 供 JsonFormatter 输出。
    """
    base_logger = logging.getLogger("config-compiler")
    base_logger.setLevel(logging.DEBUG)
    base_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    base_logger.addHandler(handler)
    if request_id is None:
        request_id = str(uuid.uuid4())
    return logging.LoggerAdapter(base_logger, {"request_id": request_id})


# 全局 logger，在 main() 中初始化
logger: Optional[logging.LoggerAdapter] = None


# -------------------- 配置编译器核心 --------------------


class ConfigCompiler:
    """
    ZEN70 配置编译器：加载/合并配置、版本迁移、Jinja2 模板渲染。

    支持单体 system.yaml 或 conf.d/*.yml 碎片目录；迁移后渲染 .env 与 docker-compose.yml 到指定输出目录。
    """

    def __init__(
        self,
        config_path: Path,
        templates_dir: Path,
        output_dir: Path,
    ) -> None:
        """
        初始化编译器路径与状态。

        Args:
            config_path: 配置文件路径（单文件）或碎片配置目录（conf.d）。
            templates_dir: Jinja2 模板所在目录（如 deploy/templates）。
            output_dir: 生成 .env 与 docker-compose.yml 的输出目录（默认 ./out）。
        """
        self.config_path = config_path.resolve()
        self.templates_dir = templates_dir.resolve()
        self.output_dir = output_dir.resolve()
        self.raw_config: Dict[str, Any] = {}
        self.config: Dict[str, Any] = {}
        self.migration_log: List[str] = []

    def load_config(self) -> Dict[str, Any]:
        """
        加载并合并配置：单文件或碎片目录（按文件名排序，后覆盖前）。

        Returns:
            合并后的原始配置字典。

        Raises:
            不直接抛出；失败时记录错误日志并调用 sys.exit(1)。
        """
        try:
            if self.config_path.is_file():
                logger.info(f"Loading single config file: {self.config_path}")
                text = self.config_path.read_text(encoding="utf-8")
                self.raw_config = yaml.safe_load(text) or {}
            elif self.config_path.is_dir():
                logger.info(f"Loading fragmented config from directory: {self.config_path}")
                yaml_files = sorted(
                    list(self.config_path.glob("*.yml")) + list(self.config_path.glob("*.yaml"))
                )
                yaml_files = [p for p in yaml_files if not (p.name.endswith(".local.yml") or p.name.endswith(".local.yaml"))]
                if not yaml_files:
                    raise FileNotFoundError(f"No .yml/.yaml files found in {self.config_path}")
                merged: Dict[str, Any] = {}
                for yf in yaml_files:
                    logger.debug(f"Merging file: {yf.name}")
                    part_text = yf.read_text(encoding="utf-8")
                    part = yaml.safe_load(part_text) or {}
                    merged = self._deep_merge(merged, part)
                self.raw_config = merged
            else:
                raise FileNotFoundError(f"Config path not found: {self.config_path}")
            return self.raw_config
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {e}", exc_info=True)
            sys.exit(1)
        except OSError as e:
            logger.error(f"I/O error loading config: {e}", exc_info=True)
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to load config: {e}", exc_info=True)
            sys.exit(1)
        return self.raw_config

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        递归深合并：override 覆盖 base，嵌套字典递归合并。

        Args:
            base: 基础字典。
            override: 覆盖字典，同键时以 override 为准，子字典递归合并。

        Returns:
            新字典，不修改 base/override。
        """
        result: Dict[str, Any] = deepcopy(base)
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    def migrate_config(self) -> Dict[str, Any]:
        """
        根据 config_version 执行版本迁移，返回迁移后的配置。

        迁移链：v1 -> v2（示例：为 storage 项补充 backup_tier）。
        不修改 self.raw_config；变更说明写入 self.migration_log。

        Returns:
            迁移后的配置字典（含 config_version 更新）。
        """
        config = deepcopy(self.raw_config)
        version = config.get("config_version", 1)
        if not isinstance(version, int):
            version = 1

        if version >= CURRENT_CONFIG_VERSION:
            self.migration_log.append(f"Config version is already v{version}")
            self.config = config
            return config

        while version < CURRENT_CONFIG_VERSION:
            if version == 1:
                config, changes = self._migrate_v1_to_v2(config)
                self.migration_log.append(f"Migrated from v1 to v2: {changes}")
                version = config.get("config_version", 2)
            else:
                break

        if version < CURRENT_CONFIG_VERSION:
            logger.warning(
                f"Config version v{version} not fully migrated to v{CURRENT_CONFIG_VERSION}"
            )
        self.config = config
        return config

    def _migrate_v1_to_v2(self, old_cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        """
        v1 -> v2 迁移：为 storage 下各项补充默认 backup_tier（法典要求）。

        Args:
            old_cfg: 当前配置（v1）。

        Returns:
            (新配置字典, 变更描述)。
        """
        new_cfg = deepcopy(old_cfg)
        new_cfg["config_version"] = 2
        changes_parts: List[str] = []
        if "storage" in new_cfg and isinstance(new_cfg["storage"], dict):
            for name, stor in new_cfg["storage"].items():
                if isinstance(stor, dict) and "backup_tier" not in stor:
                    stor["backup_tier"] = "critical"
                    changes_parts.append(name)
        changes = "Added default backup_tier=critical to storage items: " + ", ".join(changes_parts) if changes_parts else "No storage items to update"
        return new_cfg, changes

    def render_templates(self) -> None:
        """
        使用 Jinja2 渲染 templates_dir 下所有 .j2 模板，写入 output_dir。

        向模板注入全局函数：now()（UTC 时间字符串）、generate_secret()（安全随机串）。
        输出文件名：去掉后缀 .j2（如 .env.j2 -> .env，docker-compose.yml.j2 -> docker-compose.yml）。

        Raises:
            不直接抛出；模板缺失或渲染失败时记录错误并 sys.exit(1)。
        """
        if not self.templates_dir.exists():
            logger.error(f"Templates directory not found: {self.templates_dir}")
            sys.exit(1)

        try:
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(str(self.templates_dir)),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        except Exception as e:
            logger.error(f"Failed to create Jinja2 environment: {e}", exc_info=True)
            sys.exit(1)

        env.globals["now"] = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        env.globals["generate_secret"] = lambda length=32: __import__("secrets").token_urlsafe(length)
        env.filters["tojson"] = json.dumps

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create output directory {self.output_dir}: {e}", exc_info=True)
            sys.exit(1)

        j2_files = list(self.templates_dir.glob("*.j2"))
        if not j2_files:
            logger.error(f"No .j2 template files found in {self.templates_dir}")
            sys.exit(1)

        for template_path in j2_files:
            template_name = template_path.name
            try:
                template = env.get_template(template_name)
                rendered = template.render(**self.config)
            except jinja2.TemplateError as e:
                logger.error(
                    f"Template rendering failed for {template_name}: {e}",
                    exc_info=True,
                )
                sys.exit(1)
            except Exception as e:
                logger.error(
                    f"Unexpected error rendering template {template_name}: {e}",
                    exc_info=True,
                )
                sys.exit(1)

            output_name = template_name[:-3] if template_name.endswith(".j2") else template_name
            output_path = self.output_dir / output_name
            try:
                output_path.write_text(rendered, encoding="utf-8")
                logger.info(f"Generated file: {output_path}")
            except OSError as e:
                logger.error(
                    f"Failed to write output file {output_path}: {e}",
                    exc_info=True,
                )
                sys.exit(1)

    def run(self, validate_only: bool = False) -> None:
        """
        执行完整编译流程：加载 -> 迁移 ->（可选）渲染。

        Args:
            validate_only: 若为 True，仅执行加载与迁移，不渲染、不写文件。
        """
        logger.info("Loading configuration")
        self.load_config()

        logger.info("Migrating configuration")
        self.migrate_config()
        for log_line in self.migration_log:
            logger.info(log_line)

        if validate_only:
            logger.info("Validation passed (no files generated)")
            return

        logger.info("Rendering templates")
        self.render_templates()
        logger.info("Compilation completed successfully")


# -------------------- 命令行入口 --------------------


def main() -> None:
    """解析命令行参数，初始化日志与编译器，执行编译或仅验证。"""
    parser = argparse.ArgumentParser(
        description="ZEN70 配置编译器：单一事实来源解析，生成 .env 与 docker-compose.yml"
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="config/system.yaml",
        help="配置文件路径（单体）或 conf.d 目录（碎片），默认 config/system.yaml",
    )
    parser.add_argument(
        "--templates",
        default="deploy/templates",
        help="模板目录，默认 deploy/templates",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="./out",
        help="输出目录，默认 ./out",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="仅验证配置（加载+迁移），不生成文件",
    )
    args = parser.parse_args()

    global logger
    logger = setup_logging(request_id=str(uuid.uuid4()))

    base = Path.cwd()
    config_path = (base / args.config).resolve()
    templates_dir = (base / args.templates).resolve()
    output_dir = (base / args.output_dir).resolve()

    compiler = ConfigCompiler(
        config_path=config_path,
        templates_dir=templates_dir,
        output_dir=output_dir,
    )
    try:
        compiler.run(validate_only=args.validate)
    except SystemExit:
        raise
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
