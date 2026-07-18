"""Subprocess entry point for unrestricted local Agent Python execution."""

from __future__ import annotations

import json
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Any

from pydantic import BaseModel
from rich.console import Console


def execute_agent_code(code: str) -> dict[str, Any]:
    output = StringIO()
    console = Console(file=output, force_terminal=False, color_system=None, width=140)
    namespace: dict[str, Any] = {"__name__": "__agent_runtime__"}
    try:
        with redirect_stdout(output), redirect_stderr(output):
            exec(compile(code, "<agent-python>", "exec"), namespace)
        # Pydantic 在 exec() 中不会自动完成前向引用的 schema 构建，
        # 对所有 BaseModel 子类调用 model_rebuild() 确保 list[OtherModel] 等工作正常
        for _value in namespace.values():
            if isinstance(_value, type) and issubclass(_value, BaseModel) and _value is not BaseModel:
                try:
                    _value.model_rebuild()
                except Exception:
                    pass  # rebuild 失败不应影响用户代码的正常执行
        if "response" not in namespace:
            raise RuntimeError("Python 代码必须给顶层变量 response 赋值")
        return {"ok": True, "logs": output.getvalue()}
    except BaseException as exc:  # noqa: BLE001 - worker must report user-code failures
        console.print("[bold red]Agent 执行失败[/bold red]")
        console.print(f"[bold red]错误类型: {type(exc).__name__}[/bold red]")
        console.print(f"[bold red]错误信息: {exc}[/bold red]")
        console.print()
        console.print("[bold yellow]完整 Traceback:[/bold yellow]")
        console.print(traceback.format_exc())
        return {"ok": False, "logs": output.getvalue()}


def main() -> None:
    protocol_stdout = sys.stdout.buffer
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        result = execute_agent_code(str(payload.get("code", "")))
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
