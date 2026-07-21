"""In-memory event streams for local Workflow node executions."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any


MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_TRUNCATED_MESSAGE = (
    "\n[日志已截断：单次运行最多展示 5 MB，程序仍在继续执行]\n"
)
RUN_RETENTION_SECONDS = 300
SSE_KEEPALIVE_SECONDS = 15
TERMINAL_EVENT_TYPES = {"complete", "interrupted"}


class RunStreamError(RuntimeError):
    """Raised when a stream cannot be created or consumed."""


@dataclass
class RunEventStream:
    """Queue and bounded log state for one execution."""

    run_id: str
    max_log_bytes: int = MAX_LOG_BYTES
    events: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    created_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    connected: bool = False
    log_bytes: int = 0
    logs_truncated: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def publish_log(self, text: str) -> None:
        """Publish text while keeping the retained stream within its byte cap."""
        if not text:
            return
        marker = LOG_TRUNCATED_MESSAGE.encode("utf-8")
        encoded = text.encode("utf-8")
        with self.lock:
            if self.logs_truncated:
                return
            content_limit = max(0, self.max_log_bytes - len(marker))
            remaining = max(0, content_limit - self.log_bytes)
            if len(encoded) <= remaining:
                self.log_bytes += len(encoded)
                emitted = text
            else:
                prefix = encoded[:remaining].decode("utf-8", errors="ignore")
                emitted = prefix + LOG_TRUNCATED_MESSAGE
                self.log_bytes += len(emitted.encode("utf-8"))
                self.logs_truncated = True
        self.events.put({"type": "log", "text": emitted})

    def publish_result(self, result: dict[str, Any], latency_ms: float) -> None:
        """Publish exactly one terminal event."""
        payload = dict(result)
        payload.pop("logs", None)
        payload["latency_ms"] = latency_ms
        payload["logs_truncated"] = self.logs_truncated
        event_type = "interrupted" if payload.get("interrupted") else "complete"
        with self.lock:
            if self.finished_at is not None:
                return
            self.finished_at = time.monotonic()
        self.events.put({"type": event_type, "result": payload})


class RunStreamManager:
    """Start background executions and expose their ordered event queues."""

    def __init__(
        self,
        max_log_bytes: int = MAX_LOG_BYTES,
        retention_seconds: float = RUN_RETENTION_SECONDS,
    ) -> None:
        self.max_log_bytes = max_log_bytes
        self.retention_seconds = retention_seconds
        self._runs: dict[str, RunEventStream] = {}
        self._lock = threading.Lock()

    def start(
        self,
        run_id: str,
        runner: Callable[[Callable[[str], None]], dict[str, Any]],
    ) -> RunEventStream:
        normalized = run_id.strip()
        if not normalized:
            raise RunStreamError("run_id 不能为空")
        self._cleanup()
        with self._lock:
            if normalized in self._runs:
                raise RunStreamError(f"运行任务已存在: {normalized}")
            stream = RunEventStream(normalized, self.max_log_bytes)
            self._runs[normalized] = stream

        def execute() -> None:
            started_at = time.perf_counter()
            try:
                result = runner(stream.publish_log)
            except BaseException as exc:  # noqa: BLE001 - keep runner thread alive
                stream.publish_log(
                    f"执行服务失败: {type(exc).__name__}: {exc}\n"
                )
                result = {"ok": False}
            latency_ms = round((time.perf_counter() - started_at) * 1000, 1)
            stream.publish_result(result, latency_ms)

        threading.Thread(
            target=execute,
            name=f"tool-run-{normalized}",
            daemon=True,
        ).start()
        return stream

    def get(self, run_id: str) -> RunEventStream | None:
        self._cleanup()
        with self._lock:
            return self._runs.get(run_id)

    def iter_events(
        self,
        run_id: str,
        keepalive_seconds: float = SSE_KEEPALIVE_SECONDS,
    ) -> Iterator[dict[str, Any] | None]:
        stream = self.get(run_id)
        if stream is None:
            raise RunStreamError(f"运行任务不存在: {run_id}")
        with stream.lock:
            if stream.connected:
                raise RunStreamError(f"运行日志已连接: {run_id}")
            stream.connected = True
        terminal_seen = False
        try:
            while not terminal_seen:
                try:
                    event = stream.events.get(timeout=keepalive_seconds)
                except queue.Empty:
                    yield None
                    continue
                terminal_seen = event.get("type") in TERMINAL_EVENT_TYPES
                yield event
        finally:
            with stream.lock:
                stream.connected = False
            if terminal_seen:
                with self._lock:
                    if self._runs.get(run_id) is stream:
                        del self._runs[run_id]

    def _cleanup(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [
                run_id
                for run_id, stream in self._runs.items()
                if stream.finished_at is not None
                and now - stream.finished_at > self.retention_seconds
            ]
            for run_id in expired:
                del self._runs[run_id]
