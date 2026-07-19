"""多 Run 公平调度、Target 请求槽、取消和手工恢复。"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from execution.case_executor import CaseWorkflowExecutionError, CaseWorkflowExecutor
from execution.models import (
    BusinessStatus,
    CaseRunRecord,
    ExecutionStatus,
    RunRecord,
    TargetRecord,
    utc_now_iso,
)
from execution.preparation import render_request_body
from execution.repository import RunRepository, RunRepositoryError


class SchedulerError(RuntimeError):
    """Run 不存在、已活动或恢复选择无效。"""


class RunExecutionParameters(BaseModel):
    """Run 启动时冻结的调度与 Connector 参数。"""

    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float = Field(default=600, gt=0)
    case_concurrency: int = Field(default=1, strict=True, ge=1)
    connection_retry_count: int = Field(default=0, strict=True, ge=0)
    retry_interval_seconds: float = Field(default=0, ge=0)


@dataclass
class _TargetState:
    run_limits: dict[str, int] = field(default_factory=dict)
    queues: dict[str, deque[asyncio.Future[None]]] = field(
        default_factory=lambda: defaultdict(deque)
    )
    rotation: deque[str] = field(default_factory=deque)
    active: int = 0
    active_by_run: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def limit(self) -> int:
        return min(self.run_limits.values()) if self.run_limits else 0


class TargetRequestCoordinator:
    """按 Run 轮询分配同一 Target 的 HTTP 请求槽。"""

    def __init__(self):
        self._states: dict[str, _TargetState] = {}
        self._lock = asyncio.Lock()

    async def register_run(self, target_id: str, run_id: str, limit: int) -> None:
        if limit < 1:
            raise SchedulerError("target_total_concurrency 必须大于 0")
        async with self._lock:
            state = self._states.setdefault(target_id, _TargetState())
            state.run_limits[run_id] = limit
            self._grant(state)

    async def unregister_run(self, target_id: str, run_id: str) -> None:
        async with self._lock:
            state = self._states.get(target_id)
            if state is None:
                return
            queue = state.queues.pop(run_id, deque())
            for future in queue:
                if not future.done():
                    future.set_exception(SchedulerError(f"Run 已退出调度: {run_id}"))
            state.rotation = deque(item for item in state.rotation if item != run_id)
            state.run_limits.pop(run_id, None)
            self._grant(state)
            if not state.run_limits and state.active == 0:
                self._states.pop(target_id, None)

    @asynccontextmanager
    async def request_slot(self, target_id: str, run_id: str):
        await self._acquire(target_id, run_id)
        try:
            yield
        finally:
            await self._release(target_id, run_id)

    async def _acquire(self, target_id: str, run_id: str) -> None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        async with self._lock:
            state = self._states.get(target_id)
            if state is None or run_id not in state.run_limits:
                raise SchedulerError(f"Run 未注册 Target 调度: {run_id}")
            state.queues[run_id].append(future)
            if run_id not in state.rotation:
                state.rotation.append(run_id)
            self._grant(state)
        try:
            await future
        except BaseException:
            async with self._lock:
                state = self._states.get(target_id)
                if state is not None:
                    if (
                        future.done()
                        and not future.cancelled()
                        and future.exception() is None
                    ):
                        state.active -= 1
                        state.active_by_run[run_id] -= 1
                    else:
                        try:
                            state.queues[run_id].remove(future)
                        except ValueError:
                            pass
                    self._grant(state)
            raise

    async def _release(self, target_id: str, run_id: str) -> None:
        async with self._lock:
            state = self._states.get(target_id)
            if state is None:
                return
            state.active -= 1
            state.active_by_run[run_id] -= 1
            self._grant(state)
            if not state.run_limits and state.active == 0:
                self._states.pop(target_id, None)

    @staticmethod
    def _grant(state: _TargetState) -> None:
        while state.active < state.limit and state.rotation:
            run_id = state.rotation.popleft()
            queue = state.queues[run_id]
            while queue and queue[0].cancelled():
                queue.popleft()
            if not queue:
                state.queues.pop(run_id, None)
                continue
            future = queue.popleft()
            state.active += 1
            state.active_by_run[run_id] += 1
            future.set_result(None)
            if queue:
                state.rotation.append(run_id)
            else:
                state.queues.pop(run_id, None)

    async def stats(self, target_id: str) -> dict[str, Any]:
        async with self._lock:
            state = self._states.get(target_id)
            if state is None:
                return {"limit": 0, "active": 0, "active_by_run": {}}
            return {
                "limit": state.limit,
                "active": state.active,
                "active_by_run": dict(state.active_by_run),
            }


@dataclass(frozen=True)
class _RunContext:
    run: RunRecord
    target: TargetRecord
    workflow_snapshot: dict[str, Any]
    request_template: Any
    parameters: RunExecutionParameters
    cases: tuple[CaseRunRecord, ...]


@dataclass
class _ActiveRun:
    context: _RunContext
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    case_tasks: set[asyncio.Task] = field(default_factory=set)
    task: asyncio.Task[RunRecord] | None = None


class RunScheduler:
    """只运行显式启动/恢复的 Run，不在服务启动时自动恢复。"""

    RECOVERABLE_CASE_STATUSES = {
        ExecutionStatus.QUEUED.value,
        ExecutionStatus.ERROR.value,
        ExecutionStatus.CANCELLED.value,
        ExecutionStatus.RUNNING.value,
    }

    def __init__(
        self,
        repository: RunRepository,
        case_executor: CaseWorkflowExecutor,
        *,
        coordinator: TargetRequestCoordinator | None = None,
    ):
        self.repository = repository
        self.case_executor = case_executor
        self.coordinator = coordinator or TargetRequestCoordinator()
        self._active: dict[str, _ActiveRun] = {}
        self._lock = asyncio.Lock()

    async def start_run(self, run_id: str) -> asyncio.Task[RunRecord]:
        """首次启动 QUEUED Run，只选择尚未开始的 Case。"""
        return await self._start(run_id, resume=False, case_run_ids=None)

    async def resume_run(
        self,
        run_id: str,
        case_run_ids: set[str] | None = None,
    ) -> asyncio.Task[RunRecord]:
        """手工恢复未开始、取消、异常或服务中断遗留 Case。"""
        return await self._start(run_id, resume=True, case_run_ids=case_run_ids)

    async def _start(
        self,
        run_id: str,
        *,
        resume: bool,
        case_run_ids: set[str] | None,
    ) -> asyncio.Task[RunRecord]:
        async with self._lock:
            if run_id in self._active:
                raise SchedulerError(f"Run 已在执行: {run_id}")
            run = self.repository.get_run(run_id)
            if run is None:
                raise SchedulerError(f"Run 不存在: {run_id}")
            if not resume and run.status != ExecutionStatus.QUEUED:
                raise SchedulerError("首次启动只允许 QUEUED Run")
            context = self._build_context(run, resume, case_run_ids)
            await self.coordinator.register_run(
                context.target.id,
                run.id,
                context.target.target_total_concurrency,
            )
            active = _ActiveRun(context=context)
            self._active[run.id] = active
            active.task = asyncio.create_task(
                self._execute_run(active),
                name=f"agent-bench-run-{run.id}",
            )
            return active.task

    def _build_context(
        self,
        run: RunRecord,
        resume: bool,
        selected_ids: set[str] | None,
    ) -> _RunContext:
        try:
            target = TargetRecord.model_validate(run.snapshot["target"])
            workflow_snapshot = run.snapshot["workflow"]
            request_template = run.snapshot["request_template"]
            if not isinstance(workflow_snapshot, dict):
                raise ValueError("workflow 必须是对象")
            parameters = RunExecutionParameters.model_validate(run.parameters)
        except (KeyError, ValueError) as exc:
            raise SchedulerError(f"Run 快照或参数无效: {exc}") from exc
        all_cases = self.repository.list_case_runs(run.id)
        by_id = {case.id: case for case in all_cases}
        eligible_statuses = (
            self.RECOVERABLE_CASE_STATUSES
            if resume
            else {ExecutionStatus.QUEUED.value}
        )
        if selected_ids is not None:
            missing = selected_ids - set(by_id)
            if missing:
                raise SchedulerError(f"CaseRun 不属于 Run: {', '.join(sorted(missing))}")
            invalid = [
                case_id
                for case_id in selected_ids
                if by_id[case_id].status not in eligible_statuses
            ]
            if invalid:
                raise SchedulerError(
                    "以下 CaseRun 已成功完成或不可恢复: " + ", ".join(sorted(invalid))
                )
            cases = tuple(case for case in all_cases if case.id in selected_ids)
        else:
            cases = tuple(case for case in all_cases if case.status in eligible_statuses)
        return _RunContext(
            run=run,
            target=target,
            workflow_snapshot=workflow_snapshot,
            request_template=request_template,
            parameters=parameters,
            cases=cases,
        )

    async def cancel_run(self, run_id: str) -> bool:
        """停止新 Case，并取消本地等待中的 HTTP/工具任务。"""
        run = self.repository.get_run(run_id)
        if run is None:
            raise SchedulerError(f"Run 不存在: {run_id}")
        self.repository.update_run_status(
            run_id,
            ExecutionStatus.CANCELLED if run_id not in self._active else ExecutionStatus.RUNNING,
            cancel_requested=True,
            error="用户请求取消 Run",
            finished_at=utc_now_iso() if run_id not in self._active else None,
        )
        async with self._lock:
            active = self._active.get(run_id)
            if active is None:
                for case in self.repository.list_case_runs(run_id):
                    if case.status != ExecutionStatus.SUCCEEDED:
                        if case.status == ExecutionStatus.RUNNING:
                            self.repository.mark_case_interrupted(
                                case.id,
                                "取消服务中断遗留 Case",
                            )
                        self.repository.update_case_run_status(
                            case.id,
                            ExecutionStatus.CANCELLED,
                            error="用户请求取消 Run",
                            finished_at=utc_now_iso(),
                        )
                return False
            active.cancel_event.set()
            for task in tuple(active.case_tasks):
                task.cancel()
            return True

    async def wait_run(self, run_id: str) -> RunRecord:
        async with self._lock:
            active = self._active.get(run_id)
            task = active.task if active else None
        if task is None:
            run = self.repository.get_run(run_id)
            if run is None:
                raise SchedulerError(f"Run 不存在: {run_id}")
            return run
        return await task

    def is_active(self, run_id: str) -> bool:
        return run_id in self._active

    async def _execute_run(self, active: _ActiveRun) -> RunRecord:
        context = active.context
        run = context.run
        started_at = run.started_at or utc_now_iso()
        self.repository.update_run_status(
            run.id,
            ExecutionStatus.RUNNING,
            business_status=None,
            error=None,
            cancel_requested=False,
            started_at=started_at,
        )
        pending = deque(context.cases)
        task_cases: dict[asyncio.Task, CaseRunRecord] = {}
        try:
            while pending or task_cases:
                if active.cancel_event.is_set():
                    while pending:
                        case = pending.popleft()
                        self.repository.update_case_run_status(
                            case.id,
                            ExecutionStatus.CANCELLED,
                            error="Run 已取消，Case 未派发",
                            finished_at=utc_now_iso(),
                        )
                    for task in tuple(task_cases):
                        task.cancel()
                    await asyncio.gather(*task_cases, return_exceptions=True)
                    task_cases.clear()
                    active.case_tasks.clear()
                    break

                while (
                    pending
                    and len(task_cases) < context.parameters.case_concurrency
                    and not active.cancel_event.is_set()
                ):
                    case = pending.popleft()
                    task = asyncio.create_task(self._execute_case(context, case))
                    task_cases[task] = case
                    active.case_tasks.add(task)
                if not task_cases:
                    continue
                done, _ = await asyncio.wait(
                    task_cases,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    task_cases.pop(task, None)
                    active.case_tasks.discard(task)
                    try:
                        task.result()
                    except (CaseWorkflowExecutionError, asyncio.CancelledError):
                        pass
                    except Exception:
                        pass

            return self._finalize_run(run.id, cancelled=active.cancel_event.is_set())
        except Exception as exc:
            return self.repository.update_run_status(
                run.id,
                ExecutionStatus.ERROR,
                business_status=BusinessStatus.ERROR,
                error=str(exc) or type(exc).__name__,
                finished_at=utc_now_iso(),
            )
        finally:
            await self.coordinator.unregister_run(context.target.id, run.id)
            async with self._lock:
                if self._active.get(run.id) is active:
                    self._active.pop(run.id, None)

    async def _execute_case(
        self,
        context: _RunContext,
        case: CaseRunRecord,
    ) -> None:
        if case.status == ExecutionStatus.RUNNING:
            case = self.repository.mark_case_interrupted(
                case.id,
                "服务中断后手工恢复",
            )
        request_body = render_request_body(context.request_template, case.question)
        try:
            await self.case_executor.execute(
                run=context.run,
                case_run=case,
                target=context.target,
                request_body=request_body,
                workflow_snapshot=context.workflow_snapshot,
                timeout_seconds=context.parameters.timeout_seconds,
                connection_retry_count=context.parameters.connection_retry_count,
                retry_interval_seconds=context.parameters.retry_interval_seconds,
                request_slot=self.coordinator.request_slot(
                    context.target.id,
                    context.run.id,
                ),
            )
        except CaseWorkflowExecutionError:
            raise
        except asyncio.CancelledError:
            current = self.repository.get_case_run(case.id)
            if current is not None and current.status not in {
                ExecutionStatus.SUCCEEDED.value,
                ExecutionStatus.ERROR.value,
                ExecutionStatus.CANCELLED.value,
            }:
                self.repository.update_case_run_status(
                    case.id,
                    ExecutionStatus.CANCELLED,
                    error="Run 取消了本地 Case 任务",
                    finished_at=utc_now_iso(),
                )
            raise
        except Exception as exc:
            self.repository.update_case_run_status(
                case.id,
                ExecutionStatus.ERROR,
                business_status=BusinessStatus.ERROR,
                error=str(exc) or type(exc).__name__,
                finished_at=utc_now_iso(),
            )

    def _finalize_run(self, run_id: str, *, cancelled: bool) -> RunRecord:
        cases = self.repository.list_case_runs(run_id)
        business_status = self._aggregate_business_status(cases)
        if cancelled:
            status = ExecutionStatus.CANCELLED
            error = "用户请求取消 Run"
        elif all(case.status == ExecutionStatus.SUCCEEDED for case in cases):
            status = ExecutionStatus.SUCCEEDED
            error = None
        else:
            status = ExecutionStatus.ERROR
            error = "Run 包含未成功完成的 Case"
            business_status = BusinessStatus.ERROR
        return self.repository.update_run_status(
            run_id,
            status,
            business_status=business_status,
            error=error,
            finished_at=utc_now_iso(),
        )

    @staticmethod
    def _aggregate_business_status(
        cases: list[CaseRunRecord],
    ) -> BusinessStatus | None:
        statuses = {case.business_status for case in cases if case.business_status}
        if BusinessStatus.ERROR in statuses:
            return BusinessStatus.ERROR
        if BusinessStatus.FAIL in statuses:
            return BusinessStatus.FAIL
        if BusinessStatus.PASS in statuses:
            return BusinessStatus.PASS
        if statuses and statuses == {BusinessStatus.SKIP.value}:
            return BusinessStatus.SKIP
        return None
