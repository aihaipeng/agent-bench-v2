"""Run 生命周期实时事件广播，不保存历史或断线回放数据。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from execution.models import ExecutionStatus, RunRecord

if TYPE_CHECKING:
    from execution.repository import RunRepository


SSE_KEEPALIVE_SECONDS = 15.0
TERMINAL_EVENT_TYPES = {"run_terminal"}
TERMINAL_RUN_STATUSES = {
    ExecutionStatus.SUCCEEDED.value,
    ExecutionStatus.ERROR.value,
    ExecutionStatus.CANCELLED.value,
}


@dataclass
class RunEventSubscription:
    """一个 SSE 客户端独占的临时事件队列。"""

    queue: asyncio.Queue[dict[str, Any]]

    async def iter_events(
        self,
        keepalive_seconds: float = SSE_KEEPALIVE_SECONDS,
    ) -> AsyncIterator[dict[str, Any] | None]:
        """按发布顺序产出事件，空闲时产出 keepalive。"""
        terminal_seen = False
        while not terminal_seen:
            try:
                event = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=keepalive_seconds,
                )
            except TimeoutError:
                yield None
                continue
            terminal_seen = event.get("type") in TERMINAL_EVENT_TYPES
            yield event


class RunEventBroker:
    """把订阅后产生的 Run 事件广播给当前连接的客户端。"""

    def __init__(self) -> None:
        self._subscribers: dict[
            str,
            set[asyncio.Queue[dict[str, Any]]],
        ] = {}
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def subscribe(self, run_id: str) -> AsyncIterator[RunEventSubscription]:
        """注册临时订阅，连接断开时立即释放队列。"""
        normalized = run_id.strip()
        if not normalized:
            raise ValueError("run_id 不能为空")
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(normalized, set()).add(queue)
        try:
            yield RunEventSubscription(queue)
        finally:
            async with self._lock:
                subscribers = self._subscribers.get(normalized)
                if subscribers is not None:
                    subscribers.discard(queue)
                    if not subscribers:
                        self._subscribers.pop(normalized, None)

    async def publish(self, run_id: str, event: dict[str, Any]) -> int:
        """向当前订阅者广播事件；没有订阅者时不保留事件。"""
        normalized = run_id.strip()
        if not normalized:
            raise ValueError("run_id 不能为空")
        if not isinstance(event.get("type"), str) or not event["type"].strip():
            raise ValueError("事件 type 不能为空")
        async with self._lock:
            queues = tuple(self._subscribers.get(normalized, ()))
        for queue in queues:
            queue.put_nowait(dict(event))
        return len(queues)

    async def subscriber_count(self, run_id: str) -> int:
        """返回当前连接数，供服务诊断和测试使用。"""
        async with self._lock:
            return len(self._subscribers.get(run_id, ()))


async def monitor_run_events(
    repository: RunRepository,
    broker: RunEventBroker,
    run_id: str,
    scheduler_task: asyncio.Task[RunRecord],
    *,
    poll_interval_seconds: float = 0.1,
) -> None:
    """把持久化的 Run/Case 状态变化转成实时提示事件。"""
    previous_run_updated_at: str | None = None
    previous_case_updated_at: dict[str, str] = {}

    async def publish_changes() -> None:
        nonlocal previous_run_updated_at
        run = repository.get_run(run_id)
        if run is not None and run.updated_at != previous_run_updated_at:
            previous_run_updated_at = run.updated_at
            await broker.publish(
                run_id,
                {
                    "type": "run_state",
                    "run_id": run_id,
                    "run": run.model_dump(mode="json"),
                },
            )
        for case in repository.list_case_runs(run_id):
            if previous_case_updated_at.get(case.id) == case.updated_at:
                continue
            previous_case_updated_at[case.id] = case.updated_at
            await broker.publish(
                run_id,
                {
                    "type": "case_state",
                    "run_id": run_id,
                    "case": case.model_dump(mode="json"),
                },
            )

    while not scheduler_task.done():
        await publish_changes()
        await asyncio.sleep(poll_interval_seconds)

    try:
        await scheduler_task
    except BaseException:
        pass
    await publish_changes()
    run = repository.get_run(run_id)
    if run is not None:
        await broker.publish(
            run_id,
            {
                "type": "run_terminal",
                "run_id": run_id,
                "run": run.model_dump(mode="json"),
            },
        )
