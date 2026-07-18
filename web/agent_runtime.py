"""Compile and execute Agent Python templates in an isolated subprocess."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any


AGENT_EXECUTION_TIMEOUT_SECONDS = 120
AGENT_PARAMETER_NAMES = {
    "model",
    "model_provider",
    "api_key",
    "base_url",
    "system_prompt",
    "human_message",
}
PLACEHOLDER_PATTERN = re.compile(r"\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}")
LEGACY_PLACEHOLDER_PATTERN = re.compile(
    r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}"
)


class AgentTemplateError(ValueError):
    """Raised when Agent template placeholders are invalid."""


def migrate_legacy_agent_template(python_code: str) -> str:
    """Convert legacy ``{{name}}`` placeholders without touching Python braces."""

    return LEGACY_PLACEHOLDER_PATTERN.sub(
        lambda match: "${" + match.group(1) + "}",
        python_code,
    )


def compile_agent_template(python_code: str, parameters: dict[str, str]) -> str:
    """Replace supported placeholders with escaped Python literals."""
    unknown = sorted(
        {
            match.group(1)
            for match in PLACEHOLDER_PATTERN.finditer(python_code)
            if match.group(1) not in AGENT_PARAMETER_NAMES
        }
    )
    if unknown:
        raise AgentTemplateError(f"未知模板参数: {', '.join(unknown)}")

    values: dict[str, str | None] = {
        name: parameters.get(name, "") for name in AGENT_PARAMETER_NAMES
    }
    if not values["system_prompt"]:
        values["system_prompt"] = None

    def replace(match: re.Match[str]) -> str:
        return repr(values[match.group(1)])

    compiled = PLACEHOLDER_PATTERN.sub(replace, python_code)
    if "${" in compiled:
        raise AgentTemplateError("存在无法识别的模板占位符")
    return compiled


def _redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def run_agent_python(
    python_code: str,
    parameters: dict[str, str],
    timeout_seconds: float = AGENT_EXECUTION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Compile and run Agent code in the current virtual environment's Python."""
    compiled = compile_agent_template(python_code, parameters)
    payload = json.dumps({"code": compiled}, ensure_ascii=False).encode("utf-8")
    try:
        process = subprocess.run(
            [sys.executable, "-m", "web.agent_worker"],
            input=payload,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "logs": f"Agent 执行超时，已终止子进程（{timeout_seconds:g} 秒）\n",
        }

    api_key = parameters.get("api_key", "")
    raw_output = process.stdout.decode("utf-8", errors="replace").strip()
    if not raw_output:
        detail = (
            process.stderr.decode("utf-8", errors="replace").strip()
            or f"Worker 退出码: {process.returncode}"
        )
        return {"ok": False, "logs": _redact(detail, [api_key]) + "\n"}
    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        detail = "Agent Worker 返回了无效结果\n" + raw_output
        if process.stderr:
            detail += "\n" + process.stderr.decode("utf-8", errors="replace")
        return {"ok": False, "logs": _redact(detail, [api_key]) + "\n"}

    result["logs"] = _redact(str(result.get("logs", "")), [api_key])
    return result
