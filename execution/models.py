"""批量测试运行的持久化记录模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now_iso() -> str:
    """返回适合持久化和排序的 UTC ISO 时间。"""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id() -> str:
    """生成不含分隔符的稳定记录 ID。"""
    return uuid4().hex


class ExecutionStatus(str, Enum):
    """Run、Case、Attempt 和 Step 的系统执行状态。"""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class BusinessStatus(str, Enum):
    """Evaluator、Check 和 Case 的业务测试结论。"""

    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIP = "SKIP"


class StepStage(str, Enum):
    """一次工具执行在固定工作流中的阶段。"""

    PARSER = "PARSER"
    EVALUATOR = "EVALUATOR"
    CHECK_AGGREGATOR = "CHECK_AGGREGATOR"
    CASE_AGGREGATOR = "CASE_AGGREGATOR"


class RetentionClass(str, Enum):
    """Artifact 的保留策略分类。"""

    SUCCESS_TEMPORARY = "SUCCESS_TEMPORARY"
    FAILURE_LONG_TERM = "FAILURE_LONG_TERM"
    FINAL_LONG_TERM = "FINAL_LONG_TERM"


class TargetHttpMethod(str, Enum):
    """首期 Target 支持的 HTTP 方法。"""

    POST = "POST"


class _RecordModel(BaseModel):
    """持久化记录的共同 Pydantic 配置。"""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


class TargetConfiguration(_RecordModel):
    """可复用目标环境的用户配置。"""

    name: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    path: str = Field(min_length=1)
    method: TargetHttpMethod = TargetHttpMethod.POST
    headers: dict[str, str] = Field(default_factory=dict)
    target_total_concurrency: int = Field(strict=True, ge=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Target 名称不能为空")
        return normalized

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip()
        if any(character.isspace() for character in normalized):
            raise ValueError("Base URL 不能包含空白字符")
        parsed = urlsplit(normalized)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Base URL 必须是完整的 HTTP 或 HTTPS 地址")
        if parsed.query or parsed.fragment:
            raise ValueError("Base URL 不能包含 query 或 fragment")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("Base URL 端口无效") from exc
        return normalized

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/") or normalized.startswith("//"):
            raise ValueError("Target Path 必须以单个 / 开头")
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ValueError("Target Path 不能包含控制字符")
        parsed = urlsplit(normalized)
        if parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Target Path 只能包含 URL 路径")
        return normalized

    @field_validator("headers", mode="before")
    @classmethod
    def validate_headers(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError("Headers 必须是 JSON 对象")
        normalized: dict[str, str] = {}
        for name, header_value in value.items():
            if not isinstance(name, str) or not _HEADER_NAME.fullmatch(name):
                raise ValueError(f"Header 名称无效: {name}")
            if not isinstance(header_value, str):
                raise ValueError(f"Header 值必须是字符串: {name}")
            if any(character in header_value for character in ("\r", "\n", "\x00")):
                raise ValueError(f"Header 值包含非法控制字符: {name}")
            try:
                header_value.encode("ascii")
            except UnicodeEncodeError as exc:
                raise ValueError(f"Header 值必须是 ASCII 字符: {name}") from exc
            normalized[name] = header_value
        return normalized


class TargetRecord(TargetConfiguration):
    """Target 的持久化记录。"""

    id: str = Field(default_factory=new_id, min_length=1)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class WorkflowRecord(_RecordModel):
    """可复用固定拓扑 Workflow 的持久化记录。"""

    id: str = Field(default_factory=new_id, min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    definition: dict[str, Any]
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    @field_validator("name")
    @classmethod
    def validate_workflow_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Workflow 名称不能为空")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_workflow_description(cls, value: str) -> str:
        return value.strip()


class TestsetWorkflowBinding(_RecordModel):
    """一个测试集到一个 Workflow 的当前绑定。"""

    testset_filename: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    updated_at: str = Field(default_factory=utc_now_iso)


class TestsetExecutionConfig(_RecordModel):
    """测试集当前请求模板配置，Run 创建时冻结副本。"""

    testset_filename: str = Field(min_length=1)
    request_template: Any
    updated_at: str = Field(default_factory=utc_now_iso)

    @field_validator("request_template")
    @classmethod
    def validate_request_template_json(cls, value: Any) -> Any:
        try:
            json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError(f"request_template 必须是合法 JSON: {exc}") from exc
        return value


class RunRecord(_RecordModel):
    """一次完整测试集运行。"""

    id: str = Field(default_factory=new_id, min_length=1)
    testset_filename: str = Field(min_length=1)
    sheet_name: str = Field(min_length=1)
    target_id: str | None = None
    workflow_id: str | None = None
    status: ExecutionStatus = ExecutionStatus.QUEUED
    business_status: BusinessStatus | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    cancel_requested: bool = False
    error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    started_at: str | None = None
    finished_at: str | None = None


class CaseRunRecord(_RecordModel):
    """Run 中一条 Excel 用例的执行记录。"""

    id: str = Field(default_factory=new_id, min_length=1)
    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    row_number: int = Field(ge=1)
    question: str
    status: ExecutionStatus = ExecutionStatus.QUEUED
    business_status: BusinessStatus | None = None
    error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    started_at: str | None = None
    finished_at: str | None = None


class AttemptRecord(_RecordModel):
    """CaseRun 调用目标 FastAPI 的一次 HTTP 尝试。"""

    id: str = Field(default_factory=new_id, min_length=1)
    case_run_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    status: ExecutionStatus = ExecutionStatus.QUEUED
    http_status: int | None = Field(default=None, ge=100, le=599)
    body_code: str | None = None
    error_type: str | None = None
    error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    started_at: str | None = None
    finished_at: str | None = None


class StepRunRecord(_RecordModel):
    """Parser、Evaluator 或 Aggregator 的一次工具执行。"""

    id: str = Field(default_factory=new_id, min_length=1)
    case_run_id: str = Field(min_length=1)
    stage: StepStage
    sequence: int = Field(default=0, ge=0)
    execution_number: int = Field(default=1, ge=1)
    check_item: str | None = None
    step_id: str | None = None
    tool_id: str | None = None
    tool_name: str | None = None
    tool_type: str | None = None
    tool_code_hash: str | None = None
    status: ExecutionStatus = ExecutionStatus.QUEUED
    business_status: BusinessStatus | None = None
    error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    started_at: str | None = None
    finished_at: str | None = None


class ArtifactRecord(_RecordModel):
    """文件系统制品在 SQLite 中的索引。"""

    id: str = Field(default_factory=new_id, min_length=1)
    run_id: str = Field(min_length=1)
    case_run_id: str | None = None
    attempt_id: str | None = None
    step_run_id: str | None = None
    kind: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retention_class: RetentionClass
    expires_at: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
