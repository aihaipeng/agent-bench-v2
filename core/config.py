import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv


class ConfigError(Exception):
    """配置加载失败异常"""

    pass


def load_config(config_path: str | Path | None = None) -> dict:
    """加载 YAML 配置并替换环境变量占位符。

    Args:
        config_path: 配置文件路径。未提供时使用项目根目录的
            ``config.yaml``。

    Returns:
        解析并校验后的配置字典。

    Raises:
        ConfigError: 环境变量缺失、配置不是对象或必需节点缺失。
    """
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    load_dotenv()
    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read()

    def replace_env_var(m):
        """把单个环境变量占位符替换为实际值。

        Args:
            m: 正则表达式匹配对象。

        Returns:
            环境变量的字符串值。

        Raises:
            ConfigError: 占位符对应的环境变量未设置。
        """
        var_name = m.group(1)
        value = os.getenv(var_name)
        if value is None:
            raise ConfigError(
                f"环境变量 {var_name} 未设置，请检查 .env 文件或系统环境变量"
            )
        return value

    raw = re.sub(r"\$\{(\w+)\}", replace_env_var, raw)
    config = yaml.safe_load(raw)
    if not isinstance(config, dict):
        raise ConfigError(f"配置文件必须包含 YAML 对象: {config_path}")
    for section in ("excel", "target_agent", "llm"):
        if not isinstance(config.get(section), dict):
            raise ConfigError(f"配置缺少对象节点: {section}")
    return config
