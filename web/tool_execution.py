"""Dispatch validated tool templates to their execution mode."""

from __future__ import annotations

from typing import Any
from collections.abc import Callable

from web.tool_runtime import TOOL_EXECUTION_TIMEOUT_SECONDS, stream_tool_worker
from web.tool_templates import ToolTemplate


def execute_tool_template(
    template: ToolTemplate,
    inputs: dict[str, Any],
    on_log: Callable[[str], None],
    run_id: str,
    timeout_seconds: float = TOOL_EXECUTION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    definition = template.definition
    payload: dict[str, Any] = {
        "inputs": inputs,
        "config": definition.config,
        "template_type": template.manifest.type,
    }
    if template.manifest.type == "HTTP" and definition.execution_mode == "CONFIG":
        payload.update(mode="HTTP_CONFIG", http=definition.http.model_dump(mode="json"))
    else:
        payload.update(mode="PYTHON", code=template.main_py)
    return stream_tool_worker(payload, on_log, run_id, timeout_seconds)
