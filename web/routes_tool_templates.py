"""Tool template CRUD API."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from web.tool_templates import (
    AgentDefinition,
    HttpDefinition,
    LlmDefinition,
    ScriptDefinition,
    TemplateDefinition,
    TemplateField,
    TemplateManifest,
    TemplateRepositoryError,
    ToolTemplate,
    ToolTemplateRepository,
    template_to_dict,
)
from web.tool_template_archives import (
    MAX_ARCHIVE_BYTES,
    build_template_archive,
    parse_template_archive,
)
from web.run_stream import RunStreamError, RunStreamManager
from web.tool_execution import execute_tool_template
from web.tool_runtime import ToolExecutionError, interrupt_tool_run


router = APIRouter(prefix="/api/tool-templates", tags=["tool-templates"])
TOOL_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "tool_registry"
_repository_instance: ToolTemplateRepository | None = None
_repository_root: Path | None = None
_run_stream_manager = RunStreamManager()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _repository() -> ToolTemplateRepository:
    global _repository_instance, _repository_root
    root = Path(TOOL_TEMPLATE_ROOT).resolve()
    if _repository_instance is None or _repository_root != root:
        _repository_instance = ToolTemplateRepository(root)
        _repository_root = root
    return _repository_instance


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TemplateCreateRequest(StrictRequest):
    type: Literal["HTTP", "AGENT", "LLM", "SCRIPT"]
    name: str = Field(min_length=1)
    description: str = ""


class TemplateUpdateRequest(StrictRequest):
    name: str = Field(min_length=1)
    description: str = ""
    inputs: list[TemplateField] = Field(default_factory=list)
    outputs: list[TemplateField] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    execution_mode: Literal["CONFIG", "CODE"] | None = None
    http: dict[str, Any] | None = None
    main_py: str | None = None


class TemplateExportRequest(StrictRequest):
    template_ids: list[str] = Field(default_factory=list)


class TemplateRunRequest(StrictRequest):
    run_id: str = Field(min_length=1, max_length=128)
    inputs: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=120, gt=0, le=120)


class TemplatePublishRequest(StrictRequest):
    type: Literal["HTTP", "AGENT", "LLM", "SCRIPT"]
    name: str = Field(min_length=1)
    description: str = ""
    definition: TemplateDefinition
    main_py: str | None = None


def _default_definition(template_type: str) -> TemplateDefinition:
    fields = {
        "type": template_type,
        "inputs": [],
        "outputs": [],
        "config": {},
    }
    if template_type == "HTTP":
        return HttpDefinition.model_validate({**fields, "execution_mode": "CONFIG"})
    if template_type == "AGENT":
        return AgentDefinition.model_validate(fields)
    if template_type == "LLM":
        return LlmDefinition.model_validate(fields)
    return ScriptDefinition.model_validate(fields)


def _default_main_py(template_type: str) -> str | None:
    if template_type == "HTTP":
        return None
    return "response = inputs\n"


def _get_or_404(template_id: str) -> ToolTemplate:
    template = _repository().get_template(template_id)
    if template is None:
        raise HTTPException(404, f"工具模板不存在: {template_id}")
    return template


@router.get("")
def list_templates(
    template_type: Literal["HTTP", "AGENT", "LLM", "SCRIPT"] | None = Query(None, alias="type"),
) -> dict:
    templates = _repository().list_templates()
    if template_type:
        templates = [item for item in templates if item.manifest.type == template_type]
    templates.sort(key=lambda item: (item.manifest.updated_at, item.manifest.id), reverse=True)
    return {"templates": [template_to_dict(item) for item in templates]}


@router.post("")
def create_template(body: TemplateCreateRequest) -> dict:
    now = _now_iso()
    try:
        template = ToolTemplate(
            manifest=TemplateManifest(
                id=uuid4().hex,
                type=body.type,
                name=body.name,
                description=body.description,
                created_at=now,
                updated_at=now,
            ),
            definition=_default_definition(body.type),
            main_py=_default_main_py(body.type),
        )
        saved = _repository().create_template(template)
    except (TemplateRepositoryError, ValidationError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"template": template_to_dict(saved)}


def _clear_api_keys(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            normalized = str(key).replace("-", "_").lower()
            sanitized[key] = "" if normalized in {"api_key", "apikey"} else _clear_api_keys(item)
        return sanitized
    if isinstance(value, list):
        return [_clear_api_keys(item) for item in value]
    return value


@router.post("/publish")
def publish_template(body: TemplatePublishRequest) -> dict:
    if body.definition.type != body.type:
        raise HTTPException(400, "type 必须与 definition.type 一致")
    now = _now_iso()
    try:
        definition = body.definition.model_copy(
            update={"config": _clear_api_keys(body.definition.config)},
            deep=True,
        )
        template = ToolTemplate(
            manifest=TemplateManifest(
                id=uuid4().hex,
                type=body.type,
                name=body.name,
                description=body.description,
                created_at=now,
                updated_at=now,
            ),
            definition=definition,
            main_py=body.main_py,
        )
        saved = _repository().create_template(template)
    except (TemplateRepositoryError, ValidationError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"template": template_to_dict(saved)}


@router.post("/import")
async def import_templates(file: UploadFile = File(...)) -> dict:
    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise HTTPException(400, "只支持 ZIP 工具模板包")
    content = await file.read(MAX_ARCHIVE_BYTES + 1)
    if len(content) > MAX_ARCHIVE_BYTES:
        raise HTTPException(400, "ZIP 文件超过 20 MB 限制")
    try:
        templates = parse_template_archive(content)
        saved = _repository().create_templates(templates)
    except TemplateRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "imported": len(saved),
        "templates": [template_to_dict(item) for item in saved],
    }


@router.post("/export")
def export_templates(body: TemplateExportRequest) -> Response:
    requested_ids = list(dict.fromkeys(body.template_ids))
    if requested_ids:
        templates = []
        missing = []
        for template_id in requested_ids:
            template = _repository().get_template(template_id)
            if template is None:
                missing.append(template_id)
            else:
                templates.append(template)
        if missing:
            raise HTTPException(404, f"工具模板不存在: {', '.join(missing)}")
    else:
        templates = _repository().list_templates()
    try:
        content = build_template_archive(templates)
    except TemplateRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="tool-templates.zip"'},
    )


@router.post("/{template_id}/runs")
def start_template_run(template_id: str, body: TemplateRunRequest) -> dict:
    template = _get_or_404(template_id)
    try:
        _run_stream_manager.start(
            body.run_id,
            lambda on_log: execute_tool_template(
                template,
                body.inputs,
                on_log,
                body.run_id,
                body.timeout_seconds,
            ),
        )
    except (RunStreamError, ToolExecutionError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"run_id": body.run_id, "status": "RUNNING"}


@router.get("/runs/{run_id}/events")
def stream_template_run(run_id: str) -> StreamingResponse:
    if _run_stream_manager.get(run_id) is None:
        raise HTTPException(404, f"运行任务不存在: {run_id}")

    def generate():
        try:
            for event in _run_stream_manager.iter_events(run_id):
                if event is None:
                    yield ": keepalive\n\n"
                    continue
                event_type = str(event.get("type", "message"))
                yield (
                    f"event: {event_type}\n"
                    f"data: {json.dumps(event, ensure_ascii=False, allow_nan=False)}\n\n"
                )
        except RunStreamError as exc:
            yield (
                "event: complete\n"
                f"data: {json.dumps({'type': 'complete', 'result': {'ok': False, 'error': str(exc)}}, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/interrupt")
def interrupt_template_run(run_id: str) -> dict:
    if _run_stream_manager.get(run_id) is None:
        raise HTTPException(404, f"运行任务不存在: {run_id}")
    interrupted = interrupt_tool_run(run_id)
    return {"run_id": run_id, "interrupted": interrupted}


@router.get("/{template_id}")
def get_template(template_id: str) -> dict:
    return {"template": template_to_dict(_get_or_404(template_id))}


@router.put("/{template_id}")
def update_template(template_id: str, body: TemplateUpdateRequest) -> dict:
    current = _get_or_404(template_id)
    definition_data = {
        "type": current.manifest.type,
        "inputs": body.inputs,
        "outputs": body.outputs,
        "config": body.config,
    }
    if current.manifest.type == "HTTP":
        definition_data.update(
            execution_mode=body.execution_mode or current.definition.execution_mode,
            http=body.http if body.http is not None else current.definition.http,
        )
    definition_class = {
        "HTTP": HttpDefinition,
        "AGENT": AgentDefinition,
        "LLM": LlmDefinition,
        "SCRIPT": ScriptDefinition,
    }[current.manifest.type]
    try:
        definition = definition_class.model_validate(definition_data)
        updated = ToolTemplate(
            manifest=current.manifest.model_copy(
                update={
                    "name": body.name,
                    "description": body.description,
                    "updated_at": _now_iso(),
                }
            ),
            definition=definition,
            main_py=body.main_py if body.main_py is not None else current.main_py,
        )
        saved = _repository().update_template(template_id, updated)
    except (TemplateRepositoryError, ValidationError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"template": template_to_dict(saved)}


@router.delete("/{template_id}")
def delete_template(template_id: str) -> dict:
    deleted = _repository().delete_template(template_id)
    if deleted is None:
        raise HTTPException(404, f"工具模板不存在: {template_id}")
    return {"template": template_to_dict(deleted)}


@router.post("/refresh")
def refresh_templates() -> dict:
    errors = _repository().refresh()
    return {"loaded": len(_repository().list_templates()), "errors": errors}
