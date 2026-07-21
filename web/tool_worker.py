"""Subprocess entry point for Python and HTTP Workflow node execution."""

from __future__ import annotations

import json
import math
import sys
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

import httpx
from pydantic import BaseModel, TypeAdapter


_RESPONSE_ADAPTER = TypeAdapter(Any)
_STREAM_EVENT_PREFIX = "\x1e"


class _HttpResponseError(RuntimeError):
    def __init__(self, status_code: int, response: dict[str, Any]) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.response = response


def _emit_event(event: dict[str, Any]) -> None:
    sys.__stdout__.buffer.write(
        (
            _STREAM_EVENT_PREFIX
            + json.dumps(event, ensure_ascii=True, allow_nan=False)
            + "\n"
        ).encode("utf-8")
    )
    sys.__stdout__.buffer.flush()


class _LineWriter:
    encoding = "utf-8"
    errors = "replace"

    def __init__(self, stream: str) -> None:
        self.stream = stream
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
                _emit_event({"type": "log", "stream": self.stream, "text": line})
        return len(text)

    def flush(self) -> None:
        with self._lock:
            if self._pending:
                pending = self._pending
                self._pending = ""
                _emit_event({"type": "log", "stream": self.stream, "text": pending})

    def isatty(self) -> bool:
        return False


def _reject_non_finite(value: Any, seen: set[int] | None = None) -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("response 包含 NaN 或 Infinity")
        return
    if isinstance(value, BaseModel):
        _reject_non_finite(value.model_dump(), seen)
        return
    if not isinstance(value, (dict, list, tuple, set, frozenset)):
        return
    seen = seen or set()
    identity = id(value)
    if identity in seen:
        raise ValueError("response 包含循环引用")
    seen.add(identity)
    values = value.values() if isinstance(value, dict) else value
    for item in values:
        _reject_non_finite(item, seen)
    seen.remove(identity)


def _serialize_response(value: Any) -> Any:
    _reject_non_finite(value)
    serialized = _RESPONSE_ADAPTER.dump_python(
        value,
        mode="json",
        warnings="error",
        serialize_as_any=True,
    )
    json.dumps(serialized, ensure_ascii=False, allow_nan=False)
    return serialized


def _execute_python(payload: dict[str, Any]) -> Any:
    code = payload.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("main.py 不能为空")
    namespace = {
        "__name__": "__tool_runtime__",
        "inputs": payload["inputs"],
        "config": payload["config"],
        "response": None,
    }
    exec(compile(code, "<workflow-node-main.py>", "exec"), namespace, namespace)
    return namespace.get("response")


def _execute_http(payload: dict[str, Any]) -> Any:
    request = payload["http"]
    body_type = request.get("body_type", "NONE")
    body = request.get("body")
    kwargs: dict[str, Any] = {
        "headers": request.get("headers") or {},
        "timeout": float(payload["config"].get("timeout_seconds", 30)),
        "follow_redirects": bool(payload["config"].get("follow_redirects", True)),
        "verify": bool(payload["config"].get("verify_tls", True)),
    }
    if request.get("params"):
        kwargs["params"] = request["params"]
    if body_type == "RAW":
        if isinstance(body, str):
            kwargs["content"] = body
        else:
            kwargs["json"] = body
    elif body_type in {"FORM_DATA", "FORM_URLENCODED"}:
        kwargs["data"] = body or {}
    elif body_type == "BINARY":
        kwargs["content"] = body.encode("utf-8") if isinstance(body, str) else bytes(body or [])
    response = httpx.request(request["method"], request["url"], **kwargs)
    try:
        response_body = response.json()
    except ValueError:
        response_body = response.text
    result = {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response_body,
    }
    if not response.is_success:
        raise _HttpResponseError(response.status_code, result)
    return result


def main() -> None:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if not isinstance(payload.get("inputs"), dict):
            raise ValueError("inputs 必须是 JSON 对象")
        if not isinstance(payload.get("config"), dict):
            raise ValueError("config 必须是 JSON 对象")
    except Exception as exc:  # noqa: BLE001
        _emit_event({"type": "result", "result": {"ok": False, "error": str(exc)}})
        return

    stdout_writer = _LineWriter("stdout")
    stderr_writer = _LineWriter("stderr")
    try:
        with redirect_stdout(stdout_writer), redirect_stderr(stderr_writer):
            if payload.get("mode") == "HTTP_CONFIG":
                response = _execute_http(payload)
            elif payload.get("mode") == "PYTHON":
                response = _execute_python(payload)
            else:
                raise ValueError("未知工具执行模式")
        stdout_writer.flush()
        stderr_writer.flush()
        result = {"ok": True, "response": _serialize_response(response)}
    except Exception as exc:  # noqa: BLE001
        with redirect_stderr(stderr_writer):
            traceback.print_exc()
        stdout_writer.flush()
        stderr_writer.flush()
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if isinstance(exc, _HttpResponseError):
            result["response"] = _serialize_response(exc.response)
            result["http_status"] = exc.status_code
    _emit_event({"type": "result", "result": result})


if __name__ == "__main__":
    main()
