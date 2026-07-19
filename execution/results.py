"""Workflow 工具原始 response 校验与系统标准结果组装。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from execution.models import BusinessStatus
from execution.preparation import RunPreparationError, normalize_request_template


class ToolResultError(ValueError):
    """Worker 执行失败、缺少 response 或结果结构不符合契约。"""


class _StrictResult(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class EvaluatorToolResponse(_StrictResult):
    """Script/Agent Evaluator 允许自行返回的字段。"""

    status: BusinessStatus
    reason: str
    data: Any = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def validate_data_json(cls, value: Any) -> Any:
        try:
            return normalize_request_template(value)
        except RunPreparationError as exc:
            raise ValueError(f"data 必须是合法 JSON: {exc}") from exc


class AggregatorToolResponse(_StrictResult):
    """Check Aggregator 给出最终判断，明细由系统保留。"""

    status: BusinessStatus
    reason: str


class CaseAggregatorToolResponse(_StrictResult):
    """Case Aggregator 顶层 reason 可选。"""

    status: BusinessStatus
    reason: str = ""


def _response_from_worker(worker_result: dict[str, Any], label: str) -> Any:
    if not isinstance(worker_result, dict):
        raise ToolResultError(f"{label} Worker 结果必须是对象")
    if worker_result.get("ok") is not True:
        detail = str(worker_result.get("logs") or "执行失败").strip()
        raise ToolResultError(f"{label} 执行失败: {detail}")
    if "response" not in worker_result:
        raise ToolResultError(f"{label} 必须设置顶层 response")
    try:
        return normalize_request_template(worker_result["response"])
    except RunPreparationError as exc:
        raise ToolResultError(f"{label} response 必须是合法 JSON: {exc}") from exc


def validate_parser_worker_result(worker_result: dict[str, Any]) -> Any:
    """Parser response 可为任意 JSON，包括 null、标量、数组或对象。"""
    return _response_from_worker(worker_result, "Parser")


def validate_evaluator_worker_result(worker_result: dict[str, Any]) -> dict[str, Any]:
    """校验 Evaluator 的固定 status/reason/data 原始结构。"""
    response = _response_from_worker(worker_result, "Evaluator")
    try:
        parsed = EvaluatorToolResponse.model_validate(response)
    except ValidationError as exc:
        raise ToolResultError(f"Evaluator response 结构错误: {exc}") from exc
    return parsed.model_dump(mode="json")


def validate_aggregator_worker_result(worker_result: dict[str, Any]) -> dict[str, Any]:
    """校验 Check Aggregator 的 status/reason 判断结构。"""
    response = _response_from_worker(worker_result, "Aggregator")
    try:
        parsed = AggregatorToolResponse.model_validate(response)
    except ValidationError as exc:
        raise ToolResultError(f"Aggregator response 结构错误: {exc}") from exc
    return parsed.model_dump(mode="json")


def validate_case_aggregator_worker_result(
    worker_result: dict[str, Any],
) -> dict[str, Any]:
    """校验 Case Aggregator 的顶层判断结构。"""
    response = _response_from_worker(worker_result, "Case Aggregator")
    try:
        parsed = CaseAggregatorToolResponse.model_validate(response)
    except ValidationError as exc:
        raise ToolResultError(f"Case Aggregator response 结构错误: {exc}") from exc
    return parsed.model_dump(mode="json")


def standardize_evaluator_result(
    raw_result: dict[str, Any],
    *,
    case_id: str,
    check_item: str,
    step_id: str,
) -> dict[str, Any]:
    """补充只由系统掌握的 Case/Check/Step 上下文。"""
    parsed = EvaluatorToolResponse.model_validate(raw_result).model_dump(mode="json")
    return {
        "case_id": case_id,
        "check_item": check_item,
        "step_id": step_id,
        **parsed,
    }


def standardize_check_result(
    decision: dict[str, Any],
    *,
    case_id: str,
    check_item: str,
    step_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """组装 Check Result，并强制保留全部 Evaluator 明细。"""
    parsed = AggregatorToolResponse.model_validate(decision).model_dump(mode="json")
    compact_results = {
        step_id: {
            key: value
            for key, value in result.items()
            if key in {"status", "reason", "data"}
        }
        for step_id, result in step_results.items()
    }
    return {
        "case_id": case_id,
        "check_item": check_item,
        **parsed,
        "step_results": compact_results,
    }


def standardize_case_result(
    decision: dict[str, Any],
    *,
    case_id: str,
    check_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """组装最终 Case Result，并保留全部 Check Result。"""
    parsed = CaseAggregatorToolResponse.model_validate(decision).model_dump(mode="json")
    compact_results = {
        check_item: {
            key: value
            for key, value in result.items()
            if key not in {"case_id", "check_item"}
        }
        for check_item, result in check_results.items()
    }
    result = {
        "case_id": case_id,
        "status": parsed["status"],
        "check_items": compact_results,
    }
    if parsed["reason"]:
        result["reason"] = parsed["reason"]
    return result
