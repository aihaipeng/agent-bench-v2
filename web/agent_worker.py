"""Subprocess entry point for unrestricted local Agent Python execution."""

from __future__ import annotations

import json
import math
import sys
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Any, TextIO

from pydantic import BaseModel, TypeAdapter
from rich.console import Console


RESPONSE_ADAPTER = TypeAdapter(Any)
STREAM_EVENT_PREFIX = "\x1e"


def _reject_non_finite_numbers(value: Any, seen: set[int] | None = None) -> None:
    """Pydantic 会把 NaN 转成 null；严格模式必须在转换前拒绝。"""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("response 包含 NaN 或 Infinity")
        return
    if isinstance(value, BaseModel):
        _reject_non_finite_numbers(value.model_dump(), seen)
        return
    if not isinstance(value, (dict, list, tuple, set, frozenset)):
        return
    seen = seen or set()
    identity = id(value)
    if identity in seen:
        return
    seen.add(identity)
    values = value.values() if isinstance(value, dict) else value
    for item in values:
        _reject_non_finite_numbers(item, seen)


class LineStreamingWriter:
    """Convert text writes into complete-line or explicit-flush events."""

    encoding = "utf-8"
    errors = "replace"

    def __init__(self, emit_line) -> None:
        self._emit_line = emit_line
        self._pending = ""
        self._lock = threading.Lock()

    def write(self, value: str) -> int:
        text = str(value)
        with self._lock:
            self._pending += text
            while "\n" in self._pending:
                end = self._pending.index("\n") + 1
                line = self._pending[:end]
                self._pending = self._pending[end:]
                self._emit_line(line)
        return len(text)

    def flush(self) -> None:
        with self._lock:
            if self._pending:
                pending = self._pending
                self._pending = ""
                self._emit_line(pending)

    def isatty(self) -> bool:
        return False


def _serialize_response(value: Any, *, strict: bool = False) -> Any:
    """把任意 Python 返回值转换为 JSON 可序列化结构。"""
    if strict:
        _reject_non_finite_numbers(value)
        serialized = RESPONSE_ADAPTER.dump_python(
            value,
            mode="json",
            warnings="error",
            serialize_as_any=True,
        )
        json.dumps(serialized, ensure_ascii=False, allow_nan=False)
        return serialized
    try:
        return RESPONSE_ADAPTER.dump_python(
            value,
            mode="json",
            warnings="none",
            fallback=repr,
            serialize_as_any=True,
        )
    except Exception:
        return repr(value)


def execute_python_code(
    code: str,
    runtime_label: str = "Agent",
    output: TextIO | LineStreamingWriter | None = None,
    inputs: dict[str, Any] | None = None,
    strict_response_json: bool = False,
) -> dict[str, Any]:
    owns_output = output is None
    output = output or StringIO()
    console = Console(file=output, force_terminal=False, color_system=None, width=140)
    namespace: dict[str, Any] = {
        "__name__": "__agent_runtime__",
        "inputs": inputs or {},
    }
    try:
        with redirect_stdout(output), redirect_stderr(output):
            compiled = compile(
                code,
                "<agent-python>",
                "exec",
                dont_inherit=True,
            )
            exec(compiled, namespace)
        # 用户代码显式启用延迟注解时，尽量补全只定义但尚未使用的模型。
        for _value in namespace.values():
            if isinstance(_value, type) and issubclass(_value, BaseModel) and _value is not BaseModel:
                try:
                    _value.model_rebuild()
                except Exception:
                    pass  # rebuild 失败不应影响用户代码的正常执行
        result: dict[str, Any] = {
            "ok": True,
            "logs": output.getvalue() if owns_output else "",
        }
        if "response" in namespace:
            result["response"] = _serialize_response(
                namespace["response"],
                strict=strict_response_json,
            )
        return result
    except BaseException as exc:  # noqa: BLE001 - worker must report user-code failures
        console.print(f"[bold red]{runtime_label} 执行失败[/bold red]")
        console.print(f"[bold red]错误类型: {type(exc).__name__}[/bold red]")
        console.print(f"[bold red]错误信息: {exc}[/bold red]")
        if isinstance(exc, ModuleNotFoundError):
            module_name = exc.name or "未知模块"
            console.print()
            console.print(f"[bold yellow]缺少 Python 模块: {module_name}[/bold yellow]")
            console.print("系统不会自动安装依赖。")
            console.print("请将提供该模块的发行包加入 pyproject.toml，并执行 uv sync 后重试。")
        console.print()
        console.print("[bold yellow]完整 Traceback:[/bold yellow]")
        console.print(traceback.format_exc())
        return {
            "ok": False,
            "logs": output.getvalue() if owns_output else "",
        }


def _write_stream_event(protocol_stdout, event_type: str, **payload: Any) -> None:
    event = {"type": event_type, **payload}
    protocol_stdout.write(
        (STREAM_EVENT_PREFIX + json.dumps(event, ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
    )
    protocol_stdout.flush()


def main() -> None:
    protocol_stdout = sys.stdout.buffer
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        inputs = payload.get("inputs", {})
        if not isinstance(inputs, dict):
            raise ValueError("Worker inputs 必须是 JSON 对象")
        strict_response_json = bool(payload.get("strict_response_json", False))
        if payload.get("stream"):
            output = LineStreamingWriter(
                lambda text: _write_stream_event(
                    protocol_stdout,
                    "log",
                    text=text,
                )
            )
            result = execute_python_code(
                str(payload.get("code", "")),
                str(payload.get("runtime_label") or "Agent"),
                output,
                inputs,
                strict_response_json,
            )
            output.flush()
            _write_stream_event(protocol_stdout, "result", result=result)
            return
        result = execute_python_code(
            str(payload.get("code", "")),
            str(payload.get("runtime_label") or "Agent"),
            inputs=inputs,
            strict_response_json=strict_response_json,
        )
    except BaseException as exc:  # noqa: BLE001 - keep the parent protocol intact
        result = {
            "ok": False,
            "logs": f"Agent Worker 启动失败: {type(exc).__name__}: {exc}\n",
        }
    protocol_stdout.write(
        json.dumps(result, ensure_ascii=False).encode("utf-8")
    )
    protocol_stdout.flush()


if __name__ == "__main__":
    main()
