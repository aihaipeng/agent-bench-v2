"""测试集请求模板、Run 生命周期、追溯和实时事件 API。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from execution import (
    DEFAULT_ARTIFACT_ROOT,
    DEFAULT_DATABASE_PATH,
    ArtifactStore,
    ArtifactStoreError,
    CaseWorkflowExecutor,
    ExecutionStatus,
    FastAPIConnector,
    RunExecutionParameters,
    RunPreparationError,
    RunPreparationService,
    RunRecord,
    RunRepository,
    RunRepositoryError,
    RunScheduler,
    SchedulerError,
    WorkflowService,
    WorkflowValidationError,
)
from web import routes_tools
from web.files import get_existing_input_path
from web.run_events import (
    TERMINAL_RUN_STATUSES,
    RunEventBroker,
    monitor_run_events,
)


router = APIRouter(prefix="/api/runs", tags=["runs"])

DATABASE_PATH = DEFAULT_DATABASE_PATH
ARTIFACT_ROOT = DEFAULT_ARTIFACT_ROOT


class _ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestTemplateRequest(_ApiModel):
    request_template: Any


class CreateRunRequest(_ApiModel):
    testset_filename: str
    target_id: str
    parameters: RunExecutionParameters = Field(
        default_factory=RunExecutionParameters
    )


class ResumeRunRequest(_ApiModel):
    case_run_ids: list[str] | None = None


@dataclass
class RunServices:
    repository: RunRepository
    artifact_store: ArtifactStore
    scheduler: RunScheduler
    event_broker: RunEventBroker
    monitor_tasks: set[asyncio.Task[None]] = field(default_factory=set)


_services_instance: RunServices | None = None
_services_key: tuple[Path, Path, Path] | None = None


def _current_services_key() -> tuple[Path, Path, Path]:
    return (
        Path(DATABASE_PATH).resolve(),
        Path(ARTIFACT_ROOT).resolve(),
        Path(routes_tools.TOOL_REGISTRY_ROOT).resolve(),
    )


def _get_services() -> RunServices:
    """按当前存储路径延迟装配运行服务，便于本机启动和测试隔离。"""
    global _services_instance, _services_key
    key = _current_services_key()
    if _services_instance is None or _services_key != key:
        repository = RunRepository(key[0])
        artifact_store = ArtifactStore(key[1])
        connector = FastAPIConnector(repository, artifact_store)
        executor = CaseWorkflowExecutor(repository, artifact_store, connector)
        _services_instance = RunServices(
            repository=repository,
            artifact_store=artifact_store,
            scheduler=RunScheduler(repository, executor),
            event_broker=RunEventBroker(),
        )
        _services_key = key
    return _services_instance


def _get_run_or_404(run_id: str) -> RunRecord:
    run = _get_services().repository.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"Run 不存在: {run_id}")
    return run


def _run_payload(run: RunRecord) -> dict[str, Any]:
    services = _get_services()
    cases = services.repository.list_case_runs(run.id)
    return {
        "run": run.model_dump(mode="json"),
        "cases": [case.model_dump(mode="json") for case in cases],
        "active": services.scheduler.is_active(run.id),
    }


def _track_monitor(run_id: str, scheduler_task: asyncio.Task[RunRecord]) -> None:
    services = _get_services()
    monitor = asyncio.create_task(
        monitor_run_events(
            services.repository,
            services.event_broker,
            run_id,
            scheduler_task,
        ),
        name=f"agent-bench-run-events-{run_id}",
    )
    services.monitor_tasks.add(monitor)
    monitor.add_done_callback(services.monitor_tasks.discard)


def _workflow_error(exc: WorkflowValidationError) -> HTTPException:
    return HTTPException(
        400,
        detail={
            "message": "Workflow 校验失败",
            "errors": [
                {"location": issue.location, "message": issue.message}
                for issue in exc.issues
            ],
        },
    )


@router.put("/testsets/{filename}/request-template")
def set_request_template(
    filename: str,
    body: RequestTemplateRequest,
) -> JSONResponse:
    """保存测试集当前请求模板，后续 Run 创建时冻结副本。"""
    path = get_existing_input_path(filename)
    try:
        config = _get_services().repository.set_testset_execution_config(
            path.name,
            body.request_template,
        )
    except (RunRepositoryError, ValidationError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse({"config": config.model_dump(mode="json")})


@router.get("/testsets/{filename}/request-template")
def get_request_template(filename: str) -> JSONResponse:
    """读取测试集当前请求模板。"""
    path = get_existing_input_path(filename)
    config = _get_services().repository.get_testset_execution_config(path.name)
    if config is None:
        raise HTTPException(404, f"测试集未配置请求模板: {path.name}")
    return JSONResponse({"config": config.model_dump(mode="json")})


@router.delete("/testsets/{filename}/request-template")
def delete_request_template(filename: str) -> JSONResponse:
    """删除测试集当前请求模板，不影响已创建 Run 的快照。"""
    path = get_existing_input_path(filename)
    repository = _get_services().repository
    config = repository.get_testset_execution_config(path.name)
    if config is None:
        raise HTTPException(404, f"测试集未配置请求模板: {path.name}")
    repository.delete_testset_execution_config(path.name)
    return JSONResponse({"config": config.model_dump(mode="json")})


@router.post("", status_code=201)
def create_run(body: CreateRunRequest) -> JSONResponse:
    """冻结当前配置并创建 QUEUED Run，不自动启动。"""
    testset_path = get_existing_input_path(body.testset_filename)
    services = _get_services()
    repository = services.repository
    config = repository.get_testset_execution_config(testset_path.name)
    if config is None:
        raise HTTPException(400, f"测试集未配置请求模板: {testset_path.name}")
    binding = repository.get_testset_workflow_binding(testset_path.name)
    if binding is None:
        raise HTTPException(400, f"测试集未绑定 Workflow: {testset_path.name}")
    target = repository.get_target(body.target_id)
    if target is None:
        raise HTTPException(404, f"Target 不存在: {body.target_id}")
    workflow_service = WorkflowService(repository, routes_tools.get_tool_registry())
    try:
        workflow_snapshot = workflow_service.snapshot(binding.workflow_id)
        request_template_source = json.dumps(
            config.request_template,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        prepared = RunPreparationService(repository).create(
            testset_path=testset_path,
            request_template=request_template_source,
            target=target,
            workflow_id=binding.workflow_id,
            workflow_snapshot=workflow_snapshot,
            parameters=body.parameters.model_dump(mode="json"),
        )
    except WorkflowValidationError as exc:
        raise _workflow_error(exc) from exc
    except KeyError as exc:
        raise HTTPException(400, f"绑定的 Workflow 不存在: {binding.workflow_id}") from exc
    except (RunPreparationError, RunRepositoryError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse(_run_payload(prepared.record), status_code=201)


@router.get("")
def list_runs(limit: int = Query(default=100, ge=1, le=500)) -> JSONResponse:
    """按创建时间倒序列出 Run。"""
    services = _get_services()
    runs = services.repository.list_runs(limit)
    return JSONResponse(
        {
            "runs": [
                {
                    **run.model_dump(mode="json"),
                    "active": services.scheduler.is_active(run.id),
                }
                for run in runs
            ]
        }
    )


@router.get("/{run_id}")
def get_run(run_id: str) -> JSONResponse:
    """读取持久化 Run 和全部 Case 当前状态。"""
    return JSONResponse(_run_payload(_get_run_or_404(run_id)))


@router.get("/{run_id}/cases/{case_run_id}")
def get_case_detail(run_id: str, case_run_id: str) -> JSONResponse:
    """读取 Case、HTTP Attempts、工具 Steps 和关联 Artifacts。"""
    _get_run_or_404(run_id)
    repository = _get_services().repository
    case = repository.get_case_run(case_run_id)
    if case is None or case.run_id != run_id:
        raise HTTPException(404, f"CaseRun 不存在: {case_run_id}")
    return JSONResponse(
        {
            "case": case.model_dump(mode="json"),
            "attempts": [
                attempt.model_dump(mode="json")
                for attempt in repository.list_attempts(case.id)
            ],
            "steps": [
                step.model_dump(mode="json")
                for step in repository.list_step_runs(case.id)
            ],
            "artifacts": [
                artifact.model_dump(mode="json")
                for artifact in repository.list_artifacts(
                    run_id,
                    case_run_id=case.id,
                )
            ],
        }
    )


@router.post("/{run_id}/start", status_code=202)
async def start_run(run_id: str) -> JSONResponse:
    """手工启动一个 QUEUED Run。"""
    _get_run_or_404(run_id)
    services = _get_services()
    try:
        task = await services.scheduler.start_run(run_id)
    except SchedulerError as exc:
        raise HTTPException(409, str(exc)) from exc
    _track_monitor(run_id, task)
    await services.event_broker.publish(
        run_id,
        {
            "type": "run_state",
            "run_id": run_id,
            "run": _get_run_or_404(run_id).model_dump(mode="json"),
        },
    )
    return JSONResponse(_run_payload(_get_run_or_404(run_id)), status_code=202)


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str) -> JSONResponse:
    """取消 Run；无法保证已经发出的远端企业 Agent 请求同步终止。"""
    _get_run_or_404(run_id)
    services = _get_services()
    try:
        was_active = await services.scheduler.cancel_run(run_id)
    except SchedulerError as exc:
        raise HTTPException(409, str(exc)) from exc
    run = _get_run_or_404(run_id)
    event_type = (
        "run_state" if run.status not in TERMINAL_RUN_STATUSES else "run_terminal"
    )
    await services.event_broker.publish(
        run_id,
        {
            "type": event_type,
            "run_id": run_id,
            "run": run.model_dump(mode="json"),
        },
    )
    return JSONResponse({**_run_payload(run), "was_active": was_active})


@router.post("/{run_id}/resume", status_code=202)
async def resume_run(run_id: str, body: ResumeRunRequest) -> JSONResponse:
    """手工恢复全部或指定的未成功 Case。"""
    _get_run_or_404(run_id)
    services = _get_services()
    selected = set(body.case_run_ids) if body.case_run_ids is not None else None
    try:
        task = await services.scheduler.resume_run(run_id, selected)
    except SchedulerError as exc:
        raise HTTPException(409, str(exc)) from exc
    _track_monitor(run_id, task)
    await services.event_broker.publish(
        run_id,
        {
            "type": "run_state",
            "run_id": run_id,
            "run": _get_run_or_404(run_id).model_dump(mode="json"),
        },
    )
    return JSONResponse(_run_payload(_get_run_or_404(run_id)), status_code=202)


@router.get("/{run_id}/artifacts")
def list_artifacts(run_id: str) -> JSONResponse:
    """列出 Run 的全部 Artifact 索引。"""
    _get_run_or_404(run_id)
    artifacts = _get_services().repository.list_artifacts(run_id)
    return JSONResponse(
        {"artifacts": [item.model_dump(mode="json") for item in artifacts]}
    )


@router.get("/{run_id}/artifacts/{artifact_id}/download")
def download_artifact(run_id: str, artifact_id: str) -> FileResponse:
    """通过 SQLite 索引和 ArtifactStore 安全下载制品。"""
    _get_run_or_404(run_id)
    services = _get_services()
    artifact = services.repository.get_artifact(artifact_id)
    if artifact is None or artifact.run_id != run_id:
        raise HTTPException(404, f"Artifact 不存在: {artifact_id}")
    try:
        path = services.artifact_store.resolve(
            artifact.relative_path,
            must_exist=True,
        )
    except ArtifactStoreError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, filename=path.name)


def _encode_sse_event(event: dict[str, Any]) -> str:
    event_type = str(event["type"])
    payload = {key: value for key, value in event.items() if key != "type"}
    return (
        f"event: {event_type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


@router.get("/{run_id}/events")
async def stream_run_events(run_id: str) -> StreamingResponse:
    """只推送订阅后产生的实时事件；断线恢复应重新查询详情 API。"""
    _get_run_or_404(run_id)
    services = _get_services()

    async def event_source():
        async with services.event_broker.subscribe(run_id) as subscription:
            current = services.repository.get_run(run_id)
            if current is None or (
                current.status in TERMINAL_RUN_STATUSES
                and not services.scheduler.is_active(run_id)
            ):
                return
            async for event in subscription.iter_events():
                yield ": keepalive\n\n" if event is None else _encode_sse_event(event)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
