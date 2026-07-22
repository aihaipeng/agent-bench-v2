"""Workflow Studio draft persistence and real LLM node run APIs."""

import json
import asyncio
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator
from web.tool_runtime import interrupt_tool_run, stream_tool_worker

from execution import (
    DEFAULT_DATABASE_PATH,
    WorkflowDraftConfiguration,
    WorkflowDraftRecord,
    WorkflowDraftRepository,
    WorkflowDraftRepositoryError,
    WorkflowNodeRunRecord,
    WorkflowNodeRunStatus,
    ModelProviderRepository,
    anthropic_headers,
    anthropic_messages_url,
    build_anthropic_request,
    build_chat_completion_request,
    chat_completions_url,
    extract_streaming_usage,
    invoke_anthropic,
    invoke_openai_compatible,
    model_http_client_options,
    parse_anthropic_response,
    parse_openai_compatible_response,
    redact_sensitive_text,
    resolve_prompt_template,
    utc_now_iso,
    workflow_variables,
    ancestor_node_ids,
    extract_output_variables,
    extract_script_output_variables,
    nearest_ancestor_output_sources,
    node_output_mappings,
    resolve_templates,
    validate_workflow_graph,
)


router = APIRouter(prefix="/api/workflow-drafts", tags=["workflow-drafts"])
DATABASE_PATH = DEFAULT_DATABASE_PATH
_repository_instance: WorkflowDraftRepository | None = None
_repository_path: Path | None = None


@dataclass
class _ActiveNodeRun:
    task: asyncio.Task[Any] | None
    loop: asyncio.AbstractEventLoop
    worker_run_id: str | None = None
    interrupted: bool = False


_ACTIVE_NODE_RUNS: dict[tuple[str, str], _ActiveNodeRun] = {}
_ACTIVE_NODE_RUNS_LOCK = threading.Lock()
_CURRENT_TASK = object()


def _register_active_node_run(
    workflow_id: str,
    node_id: str,
    *,
    task: asyncio.Task[Any] | None | object = _CURRENT_TASK,
) -> _ActiveNodeRun:
    key = (workflow_id, node_id)
    active = _ActiveNodeRun(
        task=asyncio.current_task() if task is _CURRENT_TASK else task,
        loop=asyncio.get_running_loop(),
    )
    with _ACTIVE_NODE_RUNS_LOCK:
        if key in _ACTIVE_NODE_RUNS:
            raise HTTPException(409, "节点正在运行，请勿重复启动")
        _ACTIVE_NODE_RUNS[key] = active
    return active


def _set_active_task(active: _ActiveNodeRun) -> None:
    with _ACTIVE_NODE_RUNS_LOCK:
        active.task = asyncio.current_task()
        interrupted = active.interrupted
    if interrupted and active.task is not None and not active.task.done():
        active.loop.call_soon_threadsafe(active.task.cancel)


def _set_active_worker_run(active: _ActiveNodeRun, worker_run_id: str) -> None:
    with _ACTIVE_NODE_RUNS_LOCK:
        active.worker_run_id = worker_run_id
        interrupted = active.interrupted
    if interrupted:
        interrupt_tool_run(worker_run_id)


def _unregister_active_node_run(
    workflow_id: str, node_id: str, active: _ActiveNodeRun
) -> None:
    key = (workflow_id, node_id)
    with _ACTIVE_NODE_RUNS_LOCK:
        if _ACTIVE_NODE_RUNS.get(key) is active:
            del _ACTIVE_NODE_RUNS[key]


def _interrupt_active_node_run(workflow_id: str, node_id: str) -> bool:
    with _ACTIVE_NODE_RUNS_LOCK:
        active = _ACTIVE_NODE_RUNS.get((workflow_id, node_id))
        if active is None or active.interrupted:
            return False
        active.interrupted = True
        worker_run_id = active.worker_run_id
        task = active.task
    if worker_run_id:
        interrupt_tool_run(worker_run_id)
    elif task is not None and not task.done():
        active.loop.call_soon_threadsafe(task.cancel)
    return True


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowDraftSnapshot(_StrictModel):
    """Response shape that does not revalidate persisted legacy node contracts."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)
    name: str
    description: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    global_variables: list[dict[str, Any]]
    id: str
    created_at: str
    updated_at: str


class WorkflowDraftMetadataUpdate(_StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Workflow 名称不能为空")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()


class WorkflowDraftEnvelope(_StrictModel):
    workflow: WorkflowDraftSnapshot


class WorkflowDraftListResponse(_StrictModel):
    workflows: list[WorkflowDraftSnapshot]


class WorkflowNodeRunListResponse(_StrictModel):
    runs: list[WorkflowNodeRunRecord]


class WorkflowNodeRunEnvelope(_StrictModel):
    run: WorkflowNodeRunRecord


class WorkflowNodeInterruptResponse(_StrictModel):
    interrupted: bool


class WorkflowVariableItem(_StrictModel):
    name: str
    value: Any = None
    path: str | None = None
    available: bool


class WorkflowVariableGroup(_StrictModel):
    id: str
    label: str
    variables: list[WorkflowVariableItem]


class WorkflowVariableGroupsResponse(_StrictModel):
    groups: list[WorkflowVariableGroup]


def get_repository() -> WorkflowDraftRepository:
    global _repository_instance, _repository_path
    path = Path(DATABASE_PATH).resolve()
    if _repository_instance is None or _repository_path != path:
        _repository_instance = WorkflowDraftRepository(path)
        _repository_path = path
    return _repository_instance


def get_workflow_or_404(workflow_id: str) -> WorkflowDraftRecord:
    workflow = get_repository().get_draft(workflow_id)
    if workflow is None:
        raise HTTPException(404, f"Workflow 草稿不存在: {workflow_id}")
    return workflow


def _validate_complete_graph(workflow: WorkflowDraftConfiguration) -> None:
    try:
        validate_workflow_graph(workflow.nodes, workflow.edges)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("", response_model=WorkflowDraftListResponse)
def list_workflow_drafts() -> WorkflowDraftListResponse:
    return WorkflowDraftListResponse(workflows=get_repository().list_drafts())


@router.post("", response_model=WorkflowDraftEnvelope)
def create_workflow_draft(
    body: WorkflowDraftConfiguration,
    for_node_run: bool = Query(default=False),
) -> WorkflowDraftEnvelope:
    if not for_node_run:
        _validate_complete_graph(body)
    try:
        workflow = get_repository().create_draft(
            WorkflowDraftRecord(**body.model_dump(mode="json"))
        )
    except WorkflowDraftRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return WorkflowDraftEnvelope(workflow=workflow)


@router.get("/{workflow_id}", response_model=WorkflowDraftEnvelope)
def get_workflow_draft(workflow_id: str) -> WorkflowDraftEnvelope:
    return WorkflowDraftEnvelope(workflow=get_workflow_or_404(workflow_id))


@router.patch("/{workflow_id}/metadata", response_model=WorkflowDraftEnvelope)
def update_workflow_draft_metadata(
    workflow_id: str,
    body: WorkflowDraftMetadataUpdate,
) -> WorkflowDraftEnvelope:
    """独立保存名称和说明，不要求当前画布通过完整 DAG 校验。"""
    get_workflow_or_404(workflow_id)
    try:
        saved = get_repository().update_metadata(
            workflow_id,
            name=body.name,
            description=body.description,
        )
    except WorkflowDraftRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return WorkflowDraftEnvelope(workflow=saved)


@router.put("/{workflow_id}", response_model=WorkflowDraftEnvelope)
def update_workflow_draft(
    workflow_id: str,
    body: WorkflowDraftConfiguration,
    for_node_run: bool = Query(default=False),
) -> WorkflowDraftEnvelope:
    if not for_node_run:
        _validate_complete_graph(body)
    current = get_workflow_or_404(workflow_id)
    updated = WorkflowDraftRecord(
        id=current.id,
        created_at=current.created_at,
        **body.model_dump(mode="json"),
    )
    try:
        saved = get_repository().update_draft(updated)
    except WorkflowDraftRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return WorkflowDraftEnvelope(workflow=saved)


@router.delete("/{workflow_id}", response_model=WorkflowDraftEnvelope)
def delete_workflow_draft(workflow_id: str) -> WorkflowDraftEnvelope:
    workflow = get_workflow_or_404(workflow_id)
    if not get_repository().delete_draft(workflow_id):
        raise HTTPException(404, f"Workflow 草稿不存在: {workflow_id}")
    return WorkflowDraftEnvelope(workflow=workflow)


@router.get(
    "/{workflow_id}/nodes/{node_id}/runs",
    response_model=WorkflowNodeRunListResponse,
)
def list_workflow_node_runs(
    workflow_id: str,
    node_id: str,
) -> WorkflowNodeRunListResponse:
    get_workflow_or_404(workflow_id)
    return WorkflowNodeRunListResponse(
        runs=get_repository().list_node_runs(workflow_id, node_id)
    )


def _event(level: str, message: str) -> dict[str, str]:
    return {"time": utc_now_iso(), "level": level, "message": message}


def _find_node(workflow: WorkflowDraftRecord, node_id: str) -> dict[str, Any]:
    for node in workflow.nodes:
        if node.get("id") == node_id:
            return node
    raise HTTPException(404, f"Workflow 节点不存在: {node_id}")


def _provider_request_id(headers: Any) -> str | None:
    for name in ("x-request-id", "request-id", "x-dashscope-request-id"):
        value = headers.get(name)
        if value:
            return value
    return None


def _response_error_message(response, *secrets: str | None) -> str:
    try:
        payload = response.json()
        detail = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except ValueError:
        detail = response.text
    return redact_sensitive_text(
        f"模型供应商返回 HTTP {response.status_code}: {detail}",
        *secrets,
    )


def _provider_request_options(provider) -> dict[str, Any]:
    return {
        "proxy_mode": provider.proxy_mode,
        "proxy_url": provider.proxy_url,
        "proxy_username": provider.proxy_username,
        "proxy_password": provider.proxy_password,
        "verify_ssl": provider.verify_ssl,
    }


def _model_default_body(provider, model_name: str) -> dict[str, Any]:
    configuration = provider.model_configs.get(model_name)
    return configuration.default_body if configuration is not None else {}


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)


def _safe_http_headers(headers: dict[str, Any]) -> dict[str, Any]:
    secret_names = {"authorization", "proxy-authorization", "cookie", "set-cookie"}
    return {
        key: "[REDACTED]" if key.lower() in secret_names else value
        for key, value in headers.items()
    }


def _rows_to_mapping(rows: Any, variables: dict[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise ValueError(f"{label} 必须是数组")
    result: dict[str, Any] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{label} 字段必须是对象")
        key = row.get("key", "")
        if not isinstance(key, str) or not key.strip():
            continue
        result[key.strip()] = resolve_templates(row.get("value", ""), variables)
    return result


def _http_execution_request(
    data: dict[str, Any], variables: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config = data.get("httpConfig") if isinstance(data.get("httpConfig"), dict) else {}
    method = str(config.get("method", "POST")).upper().strip()
    url = resolve_templates(str(config.get("url", "")), variables).strip()
    if not url:
        raise ValueError("HTTP 请求 URL 不能为空")
    headers = _rows_to_mapping(config.get("headers", []), variables, "Headers")
    params = _rows_to_mapping(config.get("params", []), variables, "Params")
    body_type = str(config.get("bodyType", "none")).upper().replace("-", "_")
    if body_type not in {"NONE", "FORM_DATA", "X_WWW_FORM_URLENCODED", "RAW", "BINARY"}:
        raise ValueError(f"不支持的 Body 类型: {body_type}")
    if body_type == "BINARY":
        raise ValueError("HTTP Binary Body 需要文件内容，当前节点暂不支持直接执行")
    worker_body_type = "FORM_URLENCODED" if body_type == "X_WWW_FORM_URLENCODED" else body_type
    if body_type in {"FORM_DATA", "X_WWW_FORM_URLENCODED"}:
        body = _rows_to_mapping(config.get("bodyFields", []), variables, "Body")
    elif body_type == "RAW":
        body = resolve_templates(str(config.get("bodyText", "")), variables)
    else:
        body = None
    execution_request = {
        "method": method,
        "url": url,
        "headers": headers,
        "params": params,
        "body_type": worker_body_type,
        "body": body,
    }
    extraction_request = execution_request.copy()
    if body_type == "RAW" and isinstance(body, str):
        # Parsing is isolated from the request sent by the worker and the raw log.
        try:
            extraction_request["body"] = json.loads(body)
        except json.JSONDecodeError:
            pass
    logged_request = {
        **execution_request,
        "headers": _safe_http_headers(headers),
    }
    return execution_request, extraction_request, logged_request


async def _run_python_or_http_node(
    workflow: WorkflowDraftRecord,
    node: dict[str, Any],
    repository: WorkflowDraftRepository,
    active: _ActiveNodeRun,
) -> WorkflowNodeRunRecord:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    node_type = data.get("nodeType")
    variables = _execution_variable_values(repository, workflow, node["id"])
    config = data.get("config") if isinstance(data.get("config"), dict) else {}
    config = resolve_templates(config, variables)
    input_snapshot: dict[str, Any] = {
        "node_type": node_type,
        "inputs": variables,
        "config": config,
    }
    events = [_event("INFO", f"开始执行 {node_type} 节点")]
    started = time.perf_counter()
    input_snapshot["resolved_inputs"] = variables
    request_for_extraction: dict[str, Any] = {}
    execution_request: dict[str, Any] = {}
    logged_request: dict[str, Any] = {}
    worker_payload: dict[str, Any] = {}
    run = WorkflowNodeRunRecord(
        workflow_id=workflow.id,
        node_id=node["id"],
        status=WorkflowNodeRunStatus.RUNNING,
        input_snapshot=input_snapshot,
        request_body=logged_request,
        events=events,
    )
    repository.create_run(run)
    timeout_seconds = config.get("timeout_seconds", config.get("timeoutSeconds", 120))
    try:
        timeout_seconds = float(timeout_seconds)
    except (TypeError, ValueError) as exc:
        timeout_seconds = 120
        events.append(_event("WARN", f"超时配置无效，使用默认值 120 秒: {exc}"))
    try:
        if node_type == "HTTP":
            execution_request, request_for_extraction, logged_request = (
                _http_execution_request(data, variables)
            )
            worker_payload = {
                "mode": "HTTP_CONFIG",
                "inputs": variables,
                "config": config,
                "http": execution_request,
            }
        elif node_type in {"AGENT", "SCRIPT"}:
            request_for_extraction = {"inputs": variables, "config": config}
            logged_request = request_for_extraction
            worker_payload = {
                "mode": "PYTHON",
                "code": data.get("mainPy") or "pass",
                "inputs": variables,
                "config": config,
            }
            if node_type == "SCRIPT":
                worker_payload["output_variable_names"] = list(dict.fromkeys(
                    mapping["path"] for mapping in node_output_mappings(node)
                ))
        else:
            raise ValueError(f"不支持真实执行的节点类型: {node_type}")
        events.append(_event("INFO", "开始执行子进程"))
        worker_run_id = uuid4().hex
        _set_active_worker_run(active, worker_run_id)
        worker_result = await asyncio.to_thread(
            stream_tool_worker,
            worker_payload,
            lambda message: events.append(_event("INFO", message)),
            worker_run_id,
            timeout_seconds,
        )
        output_key = "python_variables" if node_type == "SCRIPT" else "response"
        raw_response = worker_result.get(output_key) if output_key in worker_result else None
        response_body = _json_text(raw_response) if output_key in worker_result else ""
        stdout = str(worker_result.get("stdout", ""))
        stderr = str(worker_result.get("stderr", ""))
        console = str(worker_result.get("console", ""))
        http_status = worker_result.get("http_status")
        if http_status is None and isinstance(raw_response, dict):
            http_status = raw_response.get("status_code")
        events.append(_event("INFO", "子进程执行完成"))
        if worker_result.get("interrupted"):
            return run.model_copy(update={
                "status": WorkflowNodeRunStatus.INTERRUPTED,
                "finished_at": utc_now_iso(),
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "input_snapshot": input_snapshot,
                "request_body": logged_request,
                "events": events + [_event("WARN", "用户中断节点")],
                "output": raw_response,
                "stdout": stdout,
                "stderr": stderr,
                "console": console,
                "response_body": response_body,
                "http_status": http_status,
                "error": {
                    "type": "INTERRUPTED",
                    "message": "用户中断节点",
                    "traceback": "",
                },
            })
        if not worker_result.get("ok"):
            message = str(worker_result.get("error") or "节点执行失败")
            raise RuntimeError(message)
        if node_type == "SCRIPT":
            output_variables = extract_script_output_variables(
                node,
                raw_response if isinstance(raw_response, dict) else {},
            )
            events.append(_event("INFO", "Script 顶层变量采集完成"))
        else:
            output_variables = extract_output_variables(
                node,
                request=request_for_extraction,
                response=raw_response,
            )
            events.append(_event("INFO", "输出变量提取完成"))
        return run.model_copy(update={
            "status": WorkflowNodeRunStatus.SUCCESS,
            "finished_at": utc_now_iso(),
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "input_snapshot": input_snapshot,
            "request_body": logged_request,
            "events": events,
            "output": raw_response,
            "stdout": stdout,
            "stderr": stderr,
            "console": console,
            "response_body": response_body,
            "output_variables": output_variables,
            "http_status": http_status,
        })
    except asyncio.CancelledError:
        events.append(_event("WARN", "用户中断节点"))
        worker_result = locals().get("worker_result", {})
        output_key = "python_variables" if node_type == "SCRIPT" else "response"
        raw_response = worker_result.get(output_key) if isinstance(worker_result, dict) else None
        response_body = _json_text(raw_response) if isinstance(worker_result, dict) and output_key in worker_result else ""
        return run.model_copy(update={
            "status": WorkflowNodeRunStatus.INTERRUPTED,
            "finished_at": utc_now_iso(),
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "input_snapshot": input_snapshot,
            "request_body": logged_request,
            "events": events,
            "output": raw_response,
            "stdout": str(worker_result.get("stdout", "")) if isinstance(worker_result, dict) else "",
            "stderr": str(worker_result.get("stderr", "")) if isinstance(worker_result, dict) else "",
            "console": str(worker_result.get("console", "")) if isinstance(worker_result, dict) else "",
            "response_body": response_body,
            "http_status": worker_result.get("http_status") if isinstance(worker_result, dict) else None,
            "error": {"type": "INTERRUPTED", "message": "用户中断节点", "traceback": ""},
        })
    except Exception as exc:
        message = str(exc)
        events.append(_event("ERROR", message))
        worker_result = locals().get("worker_result", {})
        output_key = "python_variables" if node_type == "SCRIPT" else "response"
        raw_response = worker_result.get(output_key) if isinstance(worker_result, dict) else None
        response_body = _json_text(raw_response) if isinstance(worker_result, dict) and output_key in worker_result else ""
        console = str(worker_result.get("console", "")) if isinstance(worker_result, dict) else ""
        if node_type == "SCRIPT" and message and message not in console:
            console += f"[ERROR] {message}\n"
        return run.model_copy(update={
            "status": WorkflowNodeRunStatus.FAILED,
            "finished_at": utc_now_iso(),
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "input_snapshot": input_snapshot,
            "request_body": logged_request,
            "events": events,
            "output": raw_response,
            "stdout": str(worker_result.get("stdout", "")) if isinstance(worker_result, dict) else "",
            "stderr": str(worker_result.get("stderr", "")) if isinstance(worker_result, dict) else "",
            "console": console,
            "response_body": response_body,
            "http_status": worker_result.get("http_status") if isinstance(worker_result, dict) else None,
            "error": {
                "type": type(exc).__name__,
                "message": message,
                "traceback": traceback.format_exc(),
            },
        })


def _node_label(node: dict[str, Any]) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    label = data.get("label")
    return label.strip() if isinstance(label, str) and label.strip() else node["id"]


def _latest_output_values(
    repository: WorkflowDraftRepository,
    workflow_id: str,
    node: dict[str, Any],
) -> tuple[dict[str, Any], WorkflowNodeRunRecord | None]:
    run = repository.latest_success_run(workflow_id, node["id"])
    return (run.output_variables if run else {}), run


def _execution_variable_values(
    repository: WorkflowDraftRepository,
    workflow: WorkflowDraftRecord,
    node_id: str,
) -> dict[str, Any]:
    values = workflow_variables(workflow.global_variables)
    node_by_id = {node["id"]: node for node in workflow.nodes}
    source_by_name = nearest_ancestor_output_sources(
        workflow.nodes, workflow.edges, node_id
    )
    outputs_by_node: dict[str, dict[str, Any]] = {}
    for source_id in set(source_by_name.values()):
        output_values, _run = _latest_output_values(
            repository, workflow.id, node_by_id[source_id]
        )
        outputs_by_node[source_id] = output_values
    for name, source_id in source_by_name.items():
        source_values = outputs_by_node[source_id]
        if name in source_values:
            values[name] = source_values[name]
    return values


@router.get(
    "/{workflow_id}/nodes/{node_id}/variables",
    response_model=WorkflowVariableGroupsResponse,
)
def get_workflow_node_variables(
    workflow_id: str,
    node_id: str,
) -> WorkflowVariableGroupsResponse:
    workflow = get_workflow_or_404(workflow_id)
    current = _find_node(workflow, node_id)
    repository = get_repository()
    groups = [
        WorkflowVariableGroup(
            id="global",
            label="全局变量",
            variables=[
                WorkflowVariableItem(
                    name=str(record.get("name", "")).strip(),
                    value=record.get("value"),
                    available=True,
                )
                for record in workflow.global_variables
                if str(record.get("name", "")).strip()
            ],
        )
    ]
    node_by_id = {node["id"]: node for node in workflow.nodes}
    visible_node_ids = ancestor_node_ids(workflow.nodes, workflow.edges, node_id) + [node_id]
    for visible_id in visible_node_ids:
        node = node_by_id[visible_id] if visible_id != node_id else current
        mappings = node_output_mappings(node)
        if visible_id != node_id and not mappings:
            continue
        output_values, _run = _latest_output_values(repository, workflow.id, node)
        groups.append(
            WorkflowVariableGroup(
                id=visible_id,
                label=_node_label(node),
                variables=[
                    WorkflowVariableItem(
                        name=mapping["name"],
                        value=output_values.get(mapping["name"]),
                        path=mapping["path"] or None,
                        available=mapping["name"] in output_values,
                    )
                    for mapping in mappings
                ],
            )
        )
    return WorkflowVariableGroupsResponse(groups=groups)


async def _run_node_without_registry(
    workflow_id: str,
    node_id: str,
    active: _ActiveNodeRun,
) -> WorkflowNodeRunEnvelope:
    workflow = get_workflow_or_404(workflow_id)
    node = _find_node(workflow, node_id)
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    if data.get("nodeType") in {"HTTP", "AGENT", "SCRIPT"}:
        repository = get_repository()
        run = await _run_python_or_http_node(workflow, node, repository, active)
        repository.finish_run(run)
        return WorkflowNodeRunEnvelope(run=run)
    provider_id = data.get("providerId") if isinstance(data.get("providerId"), str) else ""
    model_name = data.get("modelName") if isinstance(data.get("modelName"), str) else ""
    system_prompt = data.get("systemPrompt") if isinstance(data.get("systemPrompt"), str) else ""
    user_prompt = data.get("userPrompt") if isinstance(data.get("userPrompt"), str) else ""
    model_parameters = data.get("modelParameters")
    input_snapshot = {
        "system_prompt": system_prompt,
        "user_prompt_template": user_prompt,
        "variables": workflow.global_variables,
    }
    events = [_event("INFO", "开始执行 LLM 节点")]
    running = WorkflowNodeRunRecord(
        workflow_id=workflow_id,
        node_id=node_id,
        provider_name="",
        model_name=model_name,
        input_snapshot=input_snapshot,
        events=events,
    )
    repository = get_repository()
    repository.create_run(running)
    started = time.perf_counter()
    api_key: str | None = None
    response_body = ""
    request_body: dict[str, Any] = {}
    provider_name = ""
    http_status: int | None = None
    request_id: str | None = None
    try:
        if data.get("nodeType") != "LLM":
            raise ValueError("只有 LLM 节点可使用模型网关执行")
        if not provider_id or not model_name:
            raise ValueError("未选择有效模型")
        if not isinstance(model_parameters, dict):
            raise ValueError("高级参数必须是 JSON 对象")
        variables = _execution_variable_values(repository, workflow, node_id)
        resolved_system_prompt = resolve_templates(system_prompt, variables)
        resolved_user_prompt = resolve_prompt_template(user_prompt, variables)
        resolved_model_parameters = resolve_templates(model_parameters, variables)
        resolved_model_parameters["stream"] = False
        input_snapshot["resolved_user_prompt"] = resolved_user_prompt
        input_snapshot["resolved_system_prompt"] = resolved_system_prompt
        events.append(_event("INFO", "用户提示词变量解析完成"))

        provider = ModelProviderRepository(DATABASE_PATH).get(provider_id)
        if provider is None or model_name not in provider.models:
            raise ValueError("模型已失效")
        api_key = provider.api_key
        provider_name = provider.name or "未命名供应商"
        user_messages = [{"role": "user", "content": resolved_user_prompt}]
        model_defaults = _model_default_body(provider, model_name)
        if provider.protocol == "ANTHROPIC":
            request_body = build_anthropic_request(
                model_name=model_name,
                messages=user_messages,
                system_prompt=resolved_system_prompt,
                model_defaults=model_defaults,
                model_parameters=resolved_model_parameters,
            )
            invoke = invoke_anthropic
            parse = parse_anthropic_response
        elif provider.protocol == "OPENAI_COMPATIBLE":
            messages = list(user_messages)
            if resolved_system_prompt.strip():
                messages.insert(0, {"role": "system", "content": resolved_system_prompt})
            request_body = build_chat_completion_request(
                model_name=model_name,
                messages=messages,
                model_defaults=model_defaults,
                model_parameters=resolved_model_parameters,
            )
            invoke = invoke_openai_compatible
            parse = lambda target: parse_openai_compatible_response(
                target, stream=False
            )
        else:
            raise ValueError(f"当前节点执行不支持协议: {provider.protocol}")
        events.append(_event("INFO", f"请求模型 {provider_name} / {model_name}"))
        response = await invoke(
            base_url=provider.base_url,
            api_key=api_key,
            request_body=request_body,
            **_provider_request_options(provider),
        )
        request_id = _provider_request_id(response.headers)
        http_status = response.status_code
        response_body = redact_sensitive_text(
            response.text, api_key, provider.proxy_password
        )
        events.append(_event("INFO", f"供应商返回 HTTP {response.status_code}"))
        if not response.is_success:
            raise RuntimeError(
                _response_error_message(response, api_key, provider.proxy_password)
            )
        parsed = parse(response)
        native_response = response.json()
        output_variables = extract_output_variables(
            node,
            request=request_body,
            response=native_response,
        )
        events.append(_event("INFO", "模型输出接收完成"))
        completed = running.model_copy(
            update={
                "status": WorkflowNodeRunStatus.SUCCESS,
                "finished_at": utc_now_iso(),
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "provider_name": provider_name,
                "model_name": model_name,
                "input_snapshot": input_snapshot,
                "request_body": request_body,
                "events": events,
                "output": parsed["output"],
                "response_body": response_body,
                "output_variables": output_variables,
                "usage": parsed["usage"],
                "http_status": response.status_code,
                "request_id": request_id,
            }
        )
    except asyncio.CancelledError:
        events.append(_event("WARN", "用户中断节点"))
        completed = running.model_copy(
            update={
                "status": WorkflowNodeRunStatus.INTERRUPTED,
                "finished_at": utc_now_iso(),
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "provider_name": provider_name,
                "model_name": model_name,
                "input_snapshot": input_snapshot,
                "request_body": request_body,
                "events": events,
                "response_body": response_body,
                "http_status": http_status,
                "request_id": request_id,
                "error": {"type": "INTERRUPTED", "message": "用户中断节点", "traceback": ""},
            }
        )
    except Exception as exc:
        proxy_password = provider.proxy_password if "provider" in locals() else None
        message = redact_sensitive_text(str(exc), api_key, proxy_password)
        events.append(_event("ERROR", message))
        completed = running.model_copy(
            update={
                "status": WorkflowNodeRunStatus.FAILED,
                "finished_at": utc_now_iso(),
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "provider_name": provider_name,
                "model_name": model_name,
                "input_snapshot": input_snapshot,
                "request_body": request_body,
                "events": events,
                "response_body": response_body,
                "http_status": http_status,
                "request_id": request_id,
                "error": {
                    "type": type(exc).__name__,
                    "message": message,
                    "traceback": redact_sensitive_text(
                        traceback.format_exc(), api_key, proxy_password
                    ),
                },
            }
        )
    repository.finish_run(completed)
    return WorkflowNodeRunEnvelope(run=completed)


@router.post(
    "/{workflow_id}/nodes/{node_id}/runs",
    response_model=WorkflowNodeRunEnvelope,
)
async def run_workflow_node(
    workflow_id: str,
    node_id: str,
) -> WorkflowNodeRunEnvelope:
    active = _register_active_node_run(workflow_id, node_id)
    try:
        return await _run_node_without_registry(workflow_id, node_id, active)
    finally:
        _unregister_active_node_run(workflow_id, node_id, active)


@router.post(
    "/{workflow_id}/nodes/{node_id}/interrupt",
    response_model=WorkflowNodeInterruptResponse,
)
def interrupt_workflow_node(
    workflow_id: str,
    node_id: str,
) -> WorkflowNodeInterruptResponse:
    get_workflow_or_404(workflow_id)
    return WorkflowNodeInterruptResponse(
        interrupted=_interrupt_active_node_run(workflow_id, node_id)
    )


def _sse_event(event: str, payload: Any) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, allow_nan=False)}\n\n"
    )


@router.post("/{workflow_id}/nodes/{node_id}/runs/stream")
async def stream_llm_node(
    workflow_id: str,
    node_id: str,
) -> StreamingResponse:
    active = _register_active_node_run(workflow_id, node_id, task=None)
    try:
        workflow = get_workflow_or_404(workflow_id)
        node = _find_node(workflow, node_id)
    except Exception:
        _unregister_active_node_run(workflow_id, node_id, active)
        raise

    async def generate():
        _set_active_task(active)
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        provider_id = data.get("providerId") if isinstance(data.get("providerId"), str) else ""
        model_name = data.get("modelName") if isinstance(data.get("modelName"), str) else ""
        system_prompt = data.get("systemPrompt") if isinstance(data.get("systemPrompt"), str) else ""
        user_prompt = data.get("userPrompt") if isinstance(data.get("userPrompt"), str) else ""
        model_parameters = data.get("modelParameters")
        input_snapshot = {
            "system_prompt": system_prompt,
            "user_prompt_template": user_prompt,
            "variables": workflow.global_variables,
        }
        events = [_event("INFO", "开始流式执行 LLM 节点")]
        running = WorkflowNodeRunRecord(
            workflow_id=workflow_id,
            node_id=node_id,
            model_name=model_name,
            input_snapshot=input_snapshot,
            events=events,
        )
        repository = get_repository()
        repository.create_run(running)
        started = time.perf_counter()
        api_key: str | None = None
        provider_name = ""
        request_body: dict[str, Any] = {}
        response_body = ""
        http_status: int | None = None
        request_id: str | None = None
        safe_parts: list[str] = []
        original_parts: list[str] = []
        usage: dict[str, Any] | None = None
        try:
            with _ACTIVE_NODE_RUNS_LOCK:
                interrupted_before_start = active.interrupted
            if interrupted_before_start:
                raise asyncio.CancelledError
            if data.get("nodeType") != "LLM":
                raise ValueError("只有 LLM 节点可使用模型网关执行")
            if not provider_id or not model_name:
                raise ValueError("未选择有效模型")
            if not isinstance(model_parameters, dict):
                raise ValueError("高级参数必须是 JSON 对象")
            variables = _execution_variable_values(repository, workflow, node_id)
            resolved_system_prompt = resolve_templates(system_prompt, variables)
            resolved_user_prompt = resolve_prompt_template(user_prompt, variables)
            resolved_model_parameters = resolve_templates(model_parameters, variables)
            resolved_model_parameters["stream"] = True
            input_snapshot["resolved_system_prompt"] = resolved_system_prompt
            input_snapshot["resolved_user_prompt"] = resolved_user_prompt
            events.append(_event("INFO", "用户提示词变量解析完成"))
            provider = ModelProviderRepository(DATABASE_PATH).get(provider_id)
            if provider is None or model_name not in provider.models:
                raise ValueError("模型已失效")
            api_key = provider.api_key
            provider_name = provider.name or "未命名供应商"
            user_messages = [{"role": "user", "content": resolved_user_prompt}]
            model_defaults = _model_default_body(provider, model_name)
            if provider.protocol == "ANTHROPIC":
                request_body = build_anthropic_request(
                    model_name=model_name,
                    messages=user_messages,
                    system_prompt=resolved_system_prompt,
                    model_defaults=model_defaults,
                    model_parameters=resolved_model_parameters,
                )
                request_url = anthropic_messages_url(provider.base_url)
                request_headers = anthropic_headers(api_key)
            elif provider.protocol == "OPENAI_COMPATIBLE":
                messages = list(user_messages)
                if resolved_system_prompt.strip():
                    messages.insert(0, {"role": "system", "content": resolved_system_prompt})
                request_body = build_chat_completion_request(
                    model_name=model_name,
                    messages=messages,
                    model_defaults=model_defaults,
                    model_parameters=resolved_model_parameters,
                )
                stream_options = request_body.get("stream_options")
                if not isinstance(stream_options, dict):
                    stream_options = {}
                request_body["stream_options"] = {
                    **stream_options,
                    "include_usage": True,
                }
                request_url = chat_completions_url(provider.base_url)
                request_headers = {
                    "accept": "application/json",
                    "authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                }
            else:
                raise ValueError(f"当前节点执行不支持协议: {provider.protocol}")
            events.append(_event("INFO", f"流式请求模型 {provider_name} / {model_name}"))
            async with httpx.AsyncClient(
                **model_http_client_options(
                    provider.base_url,
                    timeout_seconds=120,
                    **_provider_request_options(provider),
                )
            ) as client:
                async with client.stream(
                    "POST",
                    request_url,
                    headers=request_headers,
                    json=request_body,
                ) as response:
                    http_status = response.status_code
                    request_id = _provider_request_id(response.headers)
                    async for chunk in response.aiter_text():
                        original_parts.append(chunk)
                        safe_chunk = redact_sensitive_text(
                            chunk, api_key, provider.proxy_password
                        )
                        safe_parts.append(safe_chunk)
                        response_body = "".join(safe_parts)
                        yield _sse_event("raw", {"chunk": safe_chunk})
                    original_body = "".join(original_parts)
                    response_body = "".join(safe_parts)
                    events.append(_event("INFO", f"供应商流结束 HTTP {response.status_code}"))
                    buffered_response = httpx.Response(
                        response.status_code,
                        headers=response.headers,
                        content=original_body.encode("utf-8"),
                    )
                    if not response.is_success:
                        raise RuntimeError(
                            _response_error_message(
                                buffered_response, api_key, provider.proxy_password
                            )
                        )
            usage = extract_streaming_usage(original_body)
            usage_message = "已提取 token usage" if usage else "供应商未返回 token usage"
            events.append(_event("INFO", f"流式原始响应接收完成，{usage_message}；未执行输出解析"))
            completed = running.model_copy(
                update={
                    "status": WorkflowNodeRunStatus.SUCCESS,
                    "finished_at": utc_now_iso(),
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "provider_name": provider_name,
                    "model_name": model_name,
                    "input_snapshot": input_snapshot,
                    "request_body": request_body,
                    "events": events,
                    "output": response_body,
                    "response_body": response_body,
                    "output_variables": {},
                    "usage": usage,
                    "http_status": http_status,
                    "request_id": request_id,
                }
            )
        except asyncio.CancelledError:
            response_body = "".join(safe_parts)
            usage = extract_streaming_usage("".join(original_parts))
            events.append(_event("WARN", "用户中断节点"))
            completed = running.model_copy(
                update={
                    "status": WorkflowNodeRunStatus.INTERRUPTED,
                    "finished_at": utc_now_iso(),
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "provider_name": provider_name,
                    "model_name": model_name,
                    "input_snapshot": input_snapshot,
                    "request_body": request_body,
                    "events": events,
                    "response_body": response_body,
                    "usage": usage,
                    "http_status": http_status,
                    "request_id": request_id,
                    "error": {"type": "INTERRUPTED", "message": "用户中断节点", "traceback": ""},
                }
            )
        except Exception as exc:
            response_body = "".join(safe_parts) or response_body
            proxy_password = provider.proxy_password if "provider" in locals() else None
            message = redact_sensitive_text(str(exc), api_key, proxy_password)
            events.append(_event("ERROR", message))
            completed = running.model_copy(
                update={
                    "status": WorkflowNodeRunStatus.FAILED,
                    "finished_at": utc_now_iso(),
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "provider_name": provider_name,
                    "model_name": model_name,
                    "input_snapshot": input_snapshot,
                    "request_body": request_body,
                    "events": events,
                    "response_body": response_body,
                    "http_status": http_status,
                    "request_id": request_id,
                    "error": {
                        "type": type(exc).__name__,
                        "message": message,
                        "traceback": redact_sensitive_text(
                            traceback.format_exc(), api_key, proxy_password
                        ),
                    },
                }
            )
        repository.finish_run(completed)
        yield _sse_event("run", completed.model_dump(mode="json"))

    async def tracked_generate():
        try:
            async for item in generate():
                yield item
        finally:
            _unregister_active_node_run(workflow_id, node_id, active)

    return StreamingResponse(
        tracked_generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
