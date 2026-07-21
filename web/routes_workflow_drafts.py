"""Workflow Studio draft persistence and real LLM node run APIs."""

import json
import time
import traceback
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel, ConfigDict

from execution import (
    DEFAULT_DATABASE_PATH,
    WorkflowDraftConfiguration,
    WorkflowDraftRecord,
    WorkflowDraftRepository,
    WorkflowDraftRepositoryError,
    WorkflowNodeRunRecord,
    WorkflowNodeRunStatus,
    ModelProviderRepository,
    build_chat_completion_request,
    chat_completions_url,
    invoke_openai_compatible,
    parse_openai_compatible_response,
    redact_sensitive_text,
    resolve_prompt_template,
    utc_now_iso,
    workflow_variables,
    ancestor_node_ids,
    extract_output_variables,
    node_output_mappings,
    resolve_templates,
)


router = APIRouter(prefix="/api/workflow-drafts", tags=["workflow-drafts"])
DATABASE_PATH = DEFAULT_DATABASE_PATH
_repository_instance: WorkflowDraftRepository | None = None
_repository_path: Path | None = None


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowDraftEnvelope(_StrictModel):
    workflow: WorkflowDraftRecord


class WorkflowDraftListResponse(_StrictModel):
    workflows: list[WorkflowDraftRecord]


class WorkflowNodeRunListResponse(_StrictModel):
    runs: list[WorkflowNodeRunRecord]


class WorkflowNodeRunEnvelope(_StrictModel):
    run: WorkflowNodeRunRecord


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


@router.get("", response_model=WorkflowDraftListResponse)
def list_workflow_drafts() -> WorkflowDraftListResponse:
    return WorkflowDraftListResponse(workflows=get_repository().list_drafts())


@router.post("", response_model=WorkflowDraftEnvelope)
def create_workflow_draft(
    body: WorkflowDraftConfiguration,
) -> WorkflowDraftEnvelope:
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


@router.put("/{workflow_id}", response_model=WorkflowDraftEnvelope)
def update_workflow_draft(
    workflow_id: str,
    body: WorkflowDraftConfiguration,
) -> WorkflowDraftEnvelope:
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


def _response_error_message(response, api_key: str) -> str:
    try:
        payload = response.json()
        detail = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except ValueError:
        detail = response.text
    return redact_sensitive_text(
        f"模型供应商返回 HTTP {response.status_code}: {detail}",
        api_key,
    )


def _node_label(node: dict[str, Any]) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    label = data.get("label")
    return label.strip() if isinstance(label, str) and label.strip() else node["id"]


def _latest_output_values(
    repository: WorkflowDraftRepository,
    workflow_id: str,
    node: dict[str, Any],
) -> tuple[dict[str, Any], WorkflowNodeRunRecord | None]:
    run = repository.latest_passed_run(workflow_id, node["id"])
    return (run.output_variables if run else {}), run


def _execution_variable_values(
    repository: WorkflowDraftRepository,
    workflow: WorkflowDraftRecord,
    node_id: str,
) -> dict[str, Any]:
    values = workflow_variables(workflow.global_variables)
    node_by_id = {node["id"]: node for node in workflow.nodes}
    for ancestor_id in ancestor_node_ids(workflow.nodes, workflow.edges, node_id):
        output_values, _run = _latest_output_values(
            repository, workflow.id, node_by_id[ancestor_id]
        )
        values.update(output_values)
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


@router.post(
    "/{workflow_id}/nodes/{node_id}/runs",
    response_model=WorkflowNodeRunEnvelope,
)
async def run_llm_node(
    workflow_id: str,
    node_id: str,
) -> WorkflowNodeRunEnvelope:
    workflow = get_workflow_or_404(workflow_id)
    node = _find_node(workflow, node_id)
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
        if provider.protocol != "OPENAI_COMPATIBLE":
            raise ValueError(f"当前节点执行不支持协议: {provider.protocol}")
        api_key = provider.api_key
        provider_name = provider.name or "未命名供应商"
        messages: list[dict[str, str]] = []
        if resolved_system_prompt.strip():
            messages.append({"role": "system", "content": resolved_system_prompt})
        messages.append({"role": "user", "content": resolved_user_prompt})
        request_body = build_chat_completion_request(
            model_name=model_name,
            messages=messages,
            model_parameters=resolved_model_parameters,
        )
        events.append(_event("INFO", f"请求模型 {provider_name} / {model_name}"))
        response = await invoke_openai_compatible(
            base_url=provider.base_url,
            api_key=api_key,
            request_body=request_body,
        )
        request_id = _provider_request_id(response.headers)
        http_status = response.status_code
        response_body = redact_sensitive_text(response.text, api_key)
        events.append(_event("INFO", f"供应商返回 HTTP {response.status_code}"))
        if not response.is_success:
            raise RuntimeError(_response_error_message(response, api_key))
        parsed = parse_openai_compatible_response(
            response,
            stream=False,
        )
        native_response = response.json()
        output_variables = extract_output_variables(
            node,
            request=request_body,
            response=native_response,
        )
        events.append(_event("INFO", "模型输出接收完成"))
        completed = running.model_copy(
            update={
                "status": WorkflowNodeRunStatus.PASSED,
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
    except Exception as exc:
        message = redact_sensitive_text(str(exc), api_key)
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
                    "traceback": redact_sensitive_text(traceback.format_exc(), api_key),
                },
            }
        )
    repository.finish_run(completed)
    return WorkflowNodeRunEnvelope(run=completed)


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
    workflow = get_workflow_or_404(workflow_id)
    node = _find_node(workflow, node_id)

    async def generate():
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
            resolved_model_parameters["stream"] = True
            input_snapshot["resolved_system_prompt"] = resolved_system_prompt
            input_snapshot["resolved_user_prompt"] = resolved_user_prompt
            events.append(_event("INFO", "用户提示词变量解析完成"))
            provider = ModelProviderRepository(DATABASE_PATH).get(provider_id)
            if provider is None or model_name not in provider.models:
                raise ValueError("模型已失效")
            if provider.protocol != "OPENAI_COMPATIBLE":
                raise ValueError(f"当前节点执行不支持协议: {provider.protocol}")
            api_key = provider.api_key
            provider_name = provider.name or "未命名供应商"
            messages: list[dict[str, str]] = []
            if resolved_system_prompt.strip():
                messages.append({"role": "system", "content": resolved_system_prompt})
            messages.append({"role": "user", "content": resolved_user_prompt})
            request_body = build_chat_completion_request(
                model_name=model_name,
                messages=messages,
                model_parameters=resolved_model_parameters,
            )
            events.append(_event("INFO", f"流式请求模型 {provider_name} / {model_name}"))
            original_parts: list[str] = []
            safe_parts: list[str] = []
            async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
                async with client.stream(
                    "POST",
                    chat_completions_url(provider.base_url),
                    headers={
                        "accept": "application/json",
                        "authorization": f"Bearer {api_key}",
                        "content-type": "application/json",
                    },
                    json=request_body,
                ) as response:
                    http_status = response.status_code
                    request_id = _provider_request_id(response.headers)
                    async for chunk in response.aiter_text():
                        original_parts.append(chunk)
                        safe_chunk = redact_sensitive_text(chunk, api_key)
                        safe_parts.append(safe_chunk)
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
                        raise RuntimeError(_response_error_message(buffered_response, api_key))
            events.append(_event("INFO", "流式原始响应接收完成，未执行解析"))
            completed = running.model_copy(
                update={
                    "status": WorkflowNodeRunStatus.PASSED,
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
                    "usage": None,
                    "http_status": http_status,
                    "request_id": request_id,
                }
            )
        except Exception as exc:
            message = redact_sensitive_text(str(exc), api_key)
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
                        "traceback": redact_sensitive_text(traceback.format_exc(), api_key),
                    },
                }
            )
        repository.finish_run(completed)
        yield _sse_event("run", completed.model_dump(mode="json"))

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
