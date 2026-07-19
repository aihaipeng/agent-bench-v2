"""固定拓扑 Workflow 与测试集绑定 API。"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from execution import (
    DEFAULT_DATABASE_PATH,
    RunRepository,
    RunRepositoryError,
    WorkflowDraft,
    WorkflowRecord,
    WorkflowService,
    WorkflowValidationError,
)
from web.files import get_existing_input_path
from web.routes_tools import get_tool_registry


router = APIRouter(prefix="/api/workflows", tags=["workflows"])

DATABASE_PATH = DEFAULT_DATABASE_PATH
_repository_instance: RunRepository | None = None
_repository_path: Path | None = None


class WorkflowBindingRequest(BaseModel):
    workflow_id: str


def _get_repository() -> RunRepository:
    global _repository_instance, _repository_path
    path = Path(DATABASE_PATH).resolve()
    if _repository_instance is None or _repository_path != path:
        _repository_instance = RunRepository(path)
        _repository_path = path
    return _repository_instance


def _get_service() -> WorkflowService:
    return WorkflowService(_get_repository(), get_tool_registry())


def _get_workflow_or_404(workflow_id: str) -> WorkflowRecord:
    workflow = _get_repository().get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(404, f"Workflow 不存在: {workflow_id}")
    return workflow


def _validation_error_response(exc: WorkflowValidationError) -> HTTPException:
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


def _to_api_workflow(workflow: WorkflowRecord) -> dict:
    service = _get_service()
    issues = service.validation_issues(workflow)
    return {
        **workflow.model_dump(mode="json"),
        "binding_count": _get_repository().count_workflow_bindings(workflow.id),
        "valid": not issues,
        "validation_errors": [
            {"location": issue.location, "message": issue.message}
            for issue in issues
        ],
    }


@router.get("")
def list_workflows() -> JSONResponse:
    """列出 Workflow，并实时返回工具/字段引用有效性。"""
    return JSONResponse(
        {
            "workflows": [
                _to_api_workflow(workflow)
                for workflow in _get_repository().list_workflows()
            ]
        }
    )


@router.post("")
def create_workflow(body: WorkflowDraft) -> JSONResponse:
    """校验并创建 Workflow。"""
    try:
        workflow = _get_service().create(body)
    except WorkflowValidationError as exc:
        raise _validation_error_response(exc) from exc
    except RunRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse({"workflow": _to_api_workflow(workflow)})


@router.put("/bindings/{filename}")
def bind_testset_workflow(
    filename: str,
    body: WorkflowBindingRequest,
) -> JSONResponse:
    """把 inputs 中一个测试集绑定到一个有效 Workflow。"""
    path = get_existing_input_path(filename)
    workflow = _get_workflow_or_404(body.workflow_id)
    issues = _get_service().validation_issues(workflow)
    if issues:
        raise _validation_error_response(WorkflowValidationError(list(issues)))
    try:
        binding = _get_repository().bind_testset_workflow(path.name, workflow.id)
    except RunRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse({"binding": binding.model_dump(mode="json")})


@router.get("/bindings/{filename}")
def get_testset_workflow_binding(filename: str) -> JSONResponse:
    """读取测试集当前绑定。"""
    path = get_existing_input_path(filename)
    binding = _get_repository().get_testset_workflow_binding(path.name)
    if binding is None:
        raise HTTPException(404, f"测试集未绑定 Workflow: {path.name}")
    workflow = _get_workflow_or_404(binding.workflow_id)
    return JSONResponse(
        {
            "binding": binding.model_dump(mode="json"),
            "workflow": _to_api_workflow(workflow),
        }
    )


@router.delete("/bindings/{filename}")
def delete_testset_workflow_binding(filename: str) -> JSONResponse:
    """解除测试集当前绑定。"""
    path = get_existing_input_path(filename)
    binding = _get_repository().get_testset_workflow_binding(path.name)
    if binding is None:
        raise HTTPException(404, f"测试集未绑定 Workflow: {path.name}")
    _get_repository().delete_testset_workflow_binding(path.name)
    return JSONResponse({"binding": binding.model_dump(mode="json")})


@router.get("/{workflow_id}")
def get_workflow(workflow_id: str) -> JSONResponse:
    """读取一个 Workflow。"""
    return JSONResponse(
        {"workflow": _to_api_workflow(_get_workflow_or_404(workflow_id))}
    )


@router.put("/{workflow_id}")
def update_workflow(workflow_id: str, body: WorkflowDraft) -> JSONResponse:
    """完整校验并更新 Workflow。"""
    _get_workflow_or_404(workflow_id)
    try:
        workflow = _get_service().update(workflow_id, body)
    except WorkflowValidationError as exc:
        raise _validation_error_response(exc) from exc
    except KeyError as exc:
        raise HTTPException(404, f"Workflow 不存在: {workflow_id}") from exc
    except RunRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse({"workflow": _to_api_workflow(workflow)})


@router.delete("/{workflow_id}")
def delete_workflow(workflow_id: str) -> JSONResponse:
    """删除 Workflow；当前测试集绑定会同时解除。"""
    workflow = _get_workflow_or_404(workflow_id)
    _get_repository().delete_workflow(workflow_id)
    return JSONResponse({"workflow": workflow.model_dump(mode="json")})
