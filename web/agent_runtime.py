"""Compile and execute tool Python code in an isolated subprocess."""

from __future__ import annotations

import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from collections.abc import Callable


PYTHON_EXECUTION_TIMEOUT_SECONDS = 120
AGENT_EXECUTION_TIMEOUT_SECONDS = PYTHON_EXECUTION_TIMEOUT_SECONDS
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


class ExecutionAlreadyRunningError(RuntimeError):
    """Raised when an active run already uses the requested run ID."""


def _normalize_worker_inputs(inputs: dict[str, Any] | None) -> dict[str, Any]:
    """在启动子进程前冻结并校验顶层 inputs JSON 对象。"""
    if inputs is None:
        return {}
    if not isinstance(inputs, dict):
        raise ValueError("Worker inputs 必须是 JSON 对象")
    try:
        encoded = json.dumps(inputs, ensure_ascii=False, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"Worker inputs 必须是合法 JSON: {exc}") from exc
    return decoded


@dataclass
class _ExecutionState:
    """Track one cancellable Python worker process."""

    process: subprocess.Popen[bytes] | None = None
    interrupted: bool = False
    created_at: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)


_EXECUTION_STATES: dict[str, _ExecutionState] = {}
_EXECUTION_STATES_LOCK = threading.Lock()
_PRE_CANCEL_TTL_SECONDS = 300
_WORKER_STREAM_EVENT_PREFIX = "\x1e"


def find_agent_template_parameters(python_code: str) -> set[str]:
    """返回代码中引用的模板参数名。"""
    return {match.group(1) for match in PLACEHOLDER_PATTERN.finditer(python_code)}


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


def _prepare_execution(run_id: str | None) -> _ExecutionState | None:
    """Reserve a run ID, honoring an interrupt that arrived before startup."""
    if run_id is None:
        return None

    now = time.monotonic()
    with _EXECUTION_STATES_LOCK:
        expired = [
            existing_id
            for existing_id, existing in _EXECUTION_STATES.items()
            if existing.process is None
            and existing.interrupted
            and now - existing.created_at > _PRE_CANCEL_TTL_SECONDS
        ]
        for existing_id in expired:
            del _EXECUTION_STATES[existing_id]

        state = _EXECUTION_STATES.get(run_id)
        if state is None:
            state = _ExecutionState()
            _EXECUTION_STATES[run_id] = state
            return state

    with state.lock:
        if state.process is not None and state.process.poll() is None:
            raise ExecutionAlreadyRunningError(f"运行任务已存在: {run_id}")
    return state


def _release_execution(run_id: str | None, state: _ExecutionState | None) -> None:
    if run_id is None or state is None:
        return
    with _EXECUTION_STATES_LOCK:
        if _EXECUTION_STATES.get(run_id) is state:
            del _EXECUTION_STATES[run_id]


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate a worker and any child processes it created."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def interrupt_python_run(run_id: str) -> bool:
    """Interrupt a run idempotently, including a run not started yet."""
    normalized = run_id.strip()
    if not normalized:
        return False

    with _EXECUTION_STATES_LOCK:
        state = _EXECUTION_STATES.get(normalized)
        if state is None:
            _EXECUTION_STATES[normalized] = _ExecutionState(interrupted=True)
            return False

    with state.lock:
        state.interrupted = True
        process = state.process
    if process is None or process.poll() is not None:
        return False
    _terminate_process_tree(process)
    return True


def is_python_run_active(run_id: str) -> bool:
    """Return whether a run currently owns a live worker process."""
    with _EXECUTION_STATES_LOCK:
        state = _EXECUTION_STATES.get(run_id)
    if state is None:
        return False
    with state.lock:
        return (
            not state.interrupted
            and state.process is not None
            and state.process.poll() is None
        )


def _run_python_worker(
    python_code: str,
    runtime_label: str,
    timeout_seconds: float,
    run_id: str | None = None,
    inputs: dict[str, Any] | None = None,
    strict_response_json: bool = False,
) -> dict[str, Any]:
    """Run Python code with the shared subprocess worker protocol."""
    normalized_inputs = _normalize_worker_inputs(inputs)
    payload = json.dumps(
        {
            "code": python_code,
            "runtime_label": runtime_label,
            "inputs": normalized_inputs,
            "strict_response_json": strict_response_json,
        },
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    state = _prepare_execution(run_id)
    process: subprocess.Popen[bytes] | None = None
    try:
        if state is not None:
            with state.lock:
                if state.interrupted:
                    return {"ok": False, "interrupted": True, "logs": ""}
                process = subprocess.Popen(
                    [sys.executable, "-m", "web.agent_worker"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=(
                        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    )
                    if os.name == "nt"
                    else 0,
                    start_new_session=os.name != "nt",
                )
                state.process = process
        else:
            process = subprocess.Popen(
                [sys.executable, "-m", "web.agent_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if os.name == "nt"
                else 0,
                start_new_session=os.name != "nt",
            )

        try:
            stdout, stderr = process.communicate(payload, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            process.communicate()
            return {
                "ok": False,
                "logs": f"{runtime_label} 执行超时，已终止子进程（{timeout_seconds:g} 秒）\n",
            }

        if state is not None:
            with state.lock:
                if state.interrupted:
                    return {"ok": False, "interrupted": True, "logs": ""}
    finally:
        _release_execution(run_id, state)

    raw_output = stdout.decode("utf-8", errors="replace").strip()
    if not raw_output:
        detail = (
            stderr.decode("utf-8", errors="replace").strip()
            or f"Worker 退出码: {process.returncode}"
        )
        return {"ok": False, "logs": detail + "\n"}
    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        detail = f"{runtime_label} Worker 返回了无效结果\n" + raw_output
        if stderr:
            detail += "\n" + stderr.decode("utf-8", errors="replace")
        return {"ok": False, "logs": detail + "\n"}

    result["logs"] = str(result.get("logs", ""))
    return result


def _parse_worker_stream_line(raw_line: bytes) -> list[dict[str, Any]]:
    """Parse marked protocol events while preserving unmarked native output."""
    text = raw_line.decode("utf-8", errors="replace")
    parts = text.split(_WORKER_STREAM_EVENT_PREFIX)
    parsed: list[dict[str, Any]] = []
    if parts[0]:
        parsed.append({"type": "log", "text": parts[0]})
    for part in parts[1:]:
        candidate = part.rstrip("\r\n")
        try:
            event = json.loads(candidate)
        except json.JSONDecodeError:
            parsed.append(
                {"type": "log", "text": _WORKER_STREAM_EVENT_PREFIX + part}
            )
            continue
        if isinstance(event, dict):
            parsed.append(event)
    return parsed


def _stream_python_worker(
    python_code: str,
    runtime_label: str,
    on_log: Callable[[str], None],
    timeout_seconds: float,
    run_id: str,
    inputs: dict[str, Any] | None = None,
    strict_response_json: bool = False,
) -> dict[str, Any]:
    """Run a worker and deliver complete log lines as they are produced."""
    normalized_inputs = _normalize_worker_inputs(inputs)
    payload = json.dumps(
        {
            "code": python_code,
            "runtime_label": runtime_label,
            "stream": True,
            "inputs": normalized_inputs,
            "strict_response_json": strict_response_json,
        },
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    state = _prepare_execution(run_id)
    process: subprocess.Popen[bytes] | None = None
    try:
        if state is None:
            raise RuntimeError("流式运行必须提供 run_id")
        with state.lock:
            if state.interrupted:
                return {"ok": False, "interrupted": True, "logs": ""}
            process = subprocess.Popen(
                [sys.executable, "-m", "web.agent_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=(
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
                if os.name == "nt"
                else 0,
                start_new_session=os.name != "nt",
            )
            state.process = process

        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        process.stdin.write(payload)
        process.stdin.close()

        output_queue: queue.Queue[tuple[str, bytes | None]] = queue.Queue()

        def read_lines(stream, source: str) -> None:
            try:
                while True:
                    line = stream.readline()
                    if not line:
                        break
                    output_queue.put((source, line))
            finally:
                output_queue.put((source, None))

        readers = [
            threading.Thread(
                target=read_lines,
                args=(process.stdout, "stdout"),
                daemon=True,
            ),
            threading.Thread(
                target=read_lines,
                args=(process.stderr, "stderr"),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()

        deadline = time.monotonic() + timeout_seconds
        closed_sources: set[str] = set()
        result: dict[str, Any] | None = None
        while len(closed_sources) < 2:
            with state.lock:
                if state.interrupted:
                    process.wait(timeout=5)
                    return {"ok": False, "interrupted": True, "logs": ""}

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                message = (
                    f"{runtime_label} 执行超时，已终止子进程"
                    f"（{timeout_seconds:g} 秒）\n"
                )
                on_log(message)
                _terminate_process_tree(process)
                process.wait(timeout=5)
                return {"ok": False, "logs": ""}

            try:
                source, raw_line = output_queue.get(timeout=min(0.1, remaining))
            except queue.Empty:
                continue
            if raw_line is None:
                closed_sources.add(source)
                continue
            if source == "stderr":
                on_log(raw_line.decode("utf-8", errors="replace"))
                continue
            for event in _parse_worker_stream_line(raw_line):
                if event.get("type") == "log":
                    on_log(str(event.get("text", "")))
                elif event.get("type") == "result" and isinstance(
                    event.get("result"), dict
                ):
                    result = event["result"]

        process.wait(timeout=5)
        with state.lock:
            if state.interrupted:
                return {"ok": False, "interrupted": True, "logs": ""}
        if result is None:
            on_log(f"{runtime_label} Worker 未返回执行结果\n")
            return {"ok": False, "logs": ""}
        result["logs"] = ""
        return result
    finally:
        if process is not None and process.poll() is None:
            _terminate_process_tree(process)
        _release_execution(run_id, state)


def run_agent_python(
    python_code: str,
    parameters: dict[str, str],
    timeout_seconds: float = AGENT_EXECUTION_TIMEOUT_SECONDS,
    run_id: str | None = None,
    inputs: dict[str, Any] | None = None,
    strict_response_json: bool = False,
) -> dict[str, Any]:
    """Compile and run Agent code in the current virtual environment's Python."""
    compiled = compile_agent_template(python_code, parameters)
    return _run_python_worker(
        compiled,
        "Agent",
        timeout_seconds,
        run_id,
        inputs,
        strict_response_json,
    )


def run_script_python(
    python_code: str,
    timeout_seconds: float = PYTHON_EXECUTION_TIMEOUT_SECONDS,
    run_id: str | None = None,
    inputs: dict[str, Any] | None = None,
    strict_response_json: bool = False,
) -> dict[str, Any]:
    """Run Script code without Agent template parameter replacement."""
    return _run_python_worker(
        python_code,
        "Script",
        timeout_seconds,
        run_id,
        inputs,
        strict_response_json,
    )


def stream_agent_python(
    python_code: str,
    parameters: dict[str, str],
    on_log: Callable[[str], None],
    run_id: str,
    timeout_seconds: float = AGENT_EXECUTION_TIMEOUT_SECONDS,
    inputs: dict[str, Any] | None = None,
    strict_response_json: bool = False,
) -> dict[str, Any]:
    """Compile and stream Agent code from a cancellable worker."""
    compiled = compile_agent_template(python_code, parameters)
    return _stream_python_worker(
        compiled,
        "Agent",
        on_log,
        timeout_seconds,
        run_id,
        inputs,
        strict_response_json,
    )


def stream_script_python(
    python_code: str,
    on_log: Callable[[str], None],
    run_id: str,
    timeout_seconds: float = PYTHON_EXECUTION_TIMEOUT_SECONDS,
    inputs: dict[str, Any] | None = None,
    strict_response_json: bool = False,
) -> dict[str, Any]:
    """Stream Script code without applying Agent placeholders."""
    return _stream_python_worker(
        python_code,
        "Script",
        on_log,
        timeout_seconds,
        run_id,
        inputs,
        strict_response_json,
    )
