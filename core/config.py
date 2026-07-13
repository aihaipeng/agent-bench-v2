import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv


class ConfigError(Exception):
    """配置加载失败异常"""

    pass


def load_config(config_path: str | Path | None = None) -> dict:
    """加载 YAML 配置，替换 ${VAR} 环境变量"""
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    load_dotenv()
    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read()

    def replace_env_var(m):
        """把单个环境变量占位符替换为实际值。"""
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
