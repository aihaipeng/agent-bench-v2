"""企业 Agent 目标环境管理 API。"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from execution import (
    DEFAULT_DATABASE_PATH,
    RunRepository,
    RunRepositoryError,
    TargetConfiguration,
    TargetRecord,
)


router = APIRouter(prefix="/api/targets", tags=["targets"])

DATABASE_PATH = DEFAULT_DATABASE_PATH
_repository_instance: RunRepository | None = None
_repository_path: Path | None = None


class TargetEnvelope(BaseModel):
    target: TargetRecord


class TargetListResponse(BaseModel):
    targets: list[TargetRecord]


def _get_repository() -> RunRepository:
    """返回当前数据库路径对应的仓储，允许测试隔离临时数据库。"""
    global _repository_instance, _repository_path
    path = Path(DATABASE_PATH).resolve()
    if _repository_instance is None or _repository_path != path:
        _repository_instance = RunRepository(path)
        _repository_path = path
    return _repository_instance


def _get_target_or_404(target_id: str) -> TargetRecord:
    target = _get_repository().get_target(target_id)
    if target is None:
        raise HTTPException(404, f"Target 不存在: {target_id}")
    return target


@router.get("", response_model=TargetListResponse)
def list_targets() -> TargetListResponse:
    """列出全部 Target。"""
    return TargetListResponse(targets=_get_repository().list_targets())


@router.post("", response_model=TargetEnvelope)
def create_target(body: TargetConfiguration) -> TargetEnvelope:
    """创建一个 Target，名称允许重复，ID 由系统生成。"""
    try:
        target = _get_repository().create_target(
            TargetRecord(**body.model_dump(mode="json"))
        )
    except RunRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return TargetEnvelope(target=target)


@router.get("/{target_id}", response_model=TargetEnvelope)
def get_target(target_id: str) -> TargetEnvelope:
    """读取一个 Target。"""
    return TargetEnvelope(target=_get_target_or_404(target_id))


@router.put("/{target_id}", response_model=TargetEnvelope)
def update_target(
    target_id: str,
    body: TargetConfiguration,
) -> TargetEnvelope:
    """完整更新一个 Target。"""
    current = _get_target_or_404(target_id)
    updated = TargetRecord(
        id=current.id,
        created_at=current.created_at,
        **body.model_dump(mode="json"),
    )
    try:
        saved = _get_repository().update_target(updated)
    except RunRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return TargetEnvelope(target=saved)


@router.delete("/{target_id}", response_model=TargetEnvelope)
def delete_target(target_id: str) -> TargetEnvelope:
    """删除一个 Target，并返回删除前快照。"""
    target = _get_target_or_404(target_id)
    if not _get_repository().delete_target(target_id):
        raise HTTPException(404, f"Target 不存在: {target_id}")
    return TargetEnvelope(target=target)
