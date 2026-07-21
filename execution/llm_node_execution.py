"""LLM node prompt resolution and safe execution helpers."""

from __future__ import annotations

import json
import re
from typing import Any


_VARIABLE_REFERENCE = re.compile(r"\$\{([^{}]+)\}")
_BEARER_VALUE = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+")


class LlmNodeConfigurationError(ValueError):
    pass


def workflow_variables(records: list[dict[str, Any]]) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    for record in records:
        if not isinstance(record, dict):
            raise LlmNodeConfigurationError("Workflow 全局变量必须是对象")
        raw_name = record.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            continue
        if name in variables:
            raise LlmNodeConfigurationError(f"Workflow 全局变量重名: {name}")
        variables[name] = record.get("value")
    return variables


def resolve_prompt_template(template: str, variables: dict[str, Any]) -> str:
    if not isinstance(template, str):
        raise LlmNodeConfigurationError("用户提示词必须是字符串")
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        if not name or name not in variables:
            missing.append(name or match.group(0))
            return match.group(0)
        value = variables[name]
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, allow_nan=False)

    resolved = _VARIABLE_REFERENCE.sub(replace, template)
    if missing:
        unique = list(dict.fromkeys(missing))
        raise LlmNodeConfigurationError(
            "用户提示词缺少变量: " + ", ".join(unique)
        )
    if not resolved.strip():
        raise LlmNodeConfigurationError("用户提示词解析后不能为空")
    return resolved


def redact_sensitive_text(text: str, *secrets: str | None) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return _BEARER_VALUE.sub(r"\1[REDACTED]", redacted)
