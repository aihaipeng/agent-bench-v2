"""固定拓扑 Workflow 定义、静态校验和运行快照。"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from execution.models import WorkflowRecord, utc_now_iso
from execution.preparation import RunPreparationError, normalize_request_template
from execution.repository import RunRepository


class _WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InputReference(_WorkflowModel):
    """一个 inputs 字段到上游 JSON 值的引用。"""

    source: str = Field(min_length=1)
    pointer: str = ""

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("输入来源不能为空")
        return normalized

    @field_validator("pointer")
    @classmethod
    def validate_pointer(cls, value: str) -> str:
        decode_json_pointer(value)
        return value


class WorkflowStepDefinition(_WorkflowModel):
    """Parser、Evaluator 或 Aggregator 的工具步骤配置。"""

    step_id: str = Field(min_length=1)
    tool_id: str = Field(min_length=1)
    inputs: dict[str, InputReference] = Field(default_factory=dict)
    parameters: dict[str, str] = Field(default_factory=dict)

    @field_validator("step_id", "tool_id")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("标识不能为空")
        return normalized

    @field_validator("inputs")
    @classmethod
    def validate_input_names(
        cls,
        value: dict[str, InputReference],
    ) -> dict[str, InputReference]:
        for name in value:
            if not name or name != name.strip():
                raise ValueError("inputs 字段名不能为空或包含首尾空白")
        return value


class CheckDefinition(_WorkflowModel):
    """一个 Check Item 的 Evaluator 与按需 Aggregator。"""

    check_item: str = Field(min_length=1)
    evaluators: list[WorkflowStepDefinition] = Field(min_length=1)
    aggregator: WorkflowStepDefinition | None = None

    @field_validator("check_item")
    @classmethod
    def normalize_check_item(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("check_item 不能为空")
        return normalized


class WorkflowDefinition(_WorkflowModel):
    """首期允许保存的完整固定拓扑。"""

    parsers: list[WorkflowStepDefinition] = Field(default_factory=list)
    checks: list[CheckDefinition] = Field(min_length=1)
    case_aggregator: WorkflowStepDefinition | None = None


class WorkflowDraft(_WorkflowModel):
    """创建或更新 Workflow 的用户配置。"""

    name: str = Field(min_length=1)
    description: str = ""
    definition: WorkflowDefinition

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


@dataclass(frozen=True)
class WorkflowValidationIssue:
    location: str
    message: str


class WorkflowValidationError(ValueError):
    """Workflow 结构与当前工具快照不一致。"""

    def __init__(self, issues: list[WorkflowValidationIssue]):
        self.issues = tuple(issues)
        super().__init__("；".join(f"{item.location}: {item.message}" for item in issues))


class ToolLookup(Protocol):
    def get_tool(self, tool_id: str) -> dict | None: ...


def decode_json_pointer(pointer: str) -> tuple[str, ...]:
    """严格解析 RFC 6901 Pointer，空字符串表示根值。"""
    if pointer == "":
        return ()
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("JSON Pointer 必须为空或以 / 开头")
    tokens: list[str] = []
    for raw_token in pointer[1:].split("/"):
        decoded: list[str] = []
        index = 0
        while index < len(raw_token):
            character = raw_token[index]
            if character != "~":
                decoded.append(character)
                index += 1
                continue
            if index + 1 >= len(raw_token) or raw_token[index + 1] not in {"0", "1"}:
                raise ValueError("JSON Pointer 只允许 ~0 和 ~1 转义")
            decoded.append("~" if raw_token[index + 1] == "0" else "/")
            index += 2
        tokens.append("".join(decoded))
    return tuple(tokens)


def segments_to_json_pointer(segments: list[str | int] | tuple[str | int, ...]) -> str:
    """将字段树或分段路径转换成 RFC 6901 Pointer。"""
    encoded = []
    for segment in segments:
        value = str(segment)
        encoded.append(value.replace("~", "~0").replace("/", "~1"))
    return "" if not encoded else "/" + "/".join(encoded)


def resolve_json_pointer(document: Any, pointer: str) -> Any:
    """在 JSON 示例上取值，不执行表达式或隐式转换。"""
    current = document
    for token in decode_json_pointer(pointer):
        if isinstance(current, dict):
            if token not in current:
                raise KeyError(f"对象字段不存在: {token}")
            current = current[token]
            continue
        if isinstance(current, list):
            if token == "0":
                index = 0
            elif token.isdigit() and not token.startswith("0"):
                index = int(token)
            else:
                raise KeyError(f"数组索引无效: {token}")
            if index >= len(current):
                raise KeyError(f"数组索引越界: {token}")
            current = current[index]
            continue
        raise KeyError(f"不能从标量值继续读取字段: {token}")
    return current


def _all_steps(definition: WorkflowDefinition):
    for index, step in enumerate(definition.parsers):
        yield f"parsers[{index}]", step
    for check_index, check in enumerate(definition.checks):
        for evaluator_index, step in enumerate(check.evaluators):
            yield f"checks[{check_index}].evaluators[{evaluator_index}]", step
        if check.aggregator is not None:
            yield f"checks[{check_index}].aggregator", check.aggregator
    if definition.case_aggregator is not None:
        yield "case_aggregator", definition.case_aggregator


def validate_workflow_definition(
    definition: WorkflowDefinition,
    tools: ToolLookup,
) -> dict[str, dict]:
    """校验固定拓扑并返回本次校验使用的工具快照。"""
    issues: list[WorkflowValidationIssue] = []
    tool_snapshots: dict[str, dict] = {}
    seen_step_ids: dict[str, str] = {}
    for location, step in _all_steps(definition):
        if step.step_id == "response":
            issues.append(
                WorkflowValidationIssue(location + ".step_id", "response 是保留来源名")
            )
        previous = seen_step_ids.get(step.step_id)
        if previous is not None:
            issues.append(
                WorkflowValidationIssue(
                    location + ".step_id",
                    f"step_id 与 {previous} 重复",
                )
            )
        else:
            seen_step_ids[step.step_id] = location

    seen_check_items: dict[str, int] = {}
    for index, check in enumerate(definition.checks):
        if check.check_item in seen_check_items:
            issues.append(
                WorkflowValidationIssue(
                    f"checks[{index}].check_item",
                    f"与 checks[{seen_check_items[check.check_item]}] 重复",
                )
            )
        else:
            seen_check_items[check.check_item] = index
        if len(check.evaluators) > 1 and check.aggregator is None:
            issues.append(
                WorkflowValidationIssue(
                    f"checks[{index}].aggregator",
                    "多个 Evaluator 必须配置 Check Aggregator",
                )
            )
        if len(check.evaluators) == 1 and check.aggregator is not None:
            issues.append(
                WorkflowValidationIssue(
                    f"checks[{index}].aggregator",
                    "单 Evaluator 不执行 Check Aggregator",
                )
            )
    if len(definition.checks) > 1 and definition.case_aggregator is None:
        issues.append(
            WorkflowValidationIssue(
                "case_aggregator",
                "多个 Check Item 必须配置 Case Aggregator",
            )
        )
    if len(definition.checks) == 1 and definition.case_aggregator is not None:
        issues.append(
            WorkflowValidationIssue(
                "case_aggregator",
                "单 Check Item 不执行 Case Aggregator",
            )
        )

    parser_examples: dict[str, Any] = {}
    for index, step in enumerate(definition.parsers):
        location = f"parsers[{index}]"
        tool = _validate_tool_step(step, location, tools, issues, tool_snapshots)
        _validate_inputs(step, location, parser_examples, issues)
        if tool is None:
            continue
        configured = bool(tool.get("output_example_configured")) or (
            "output_example" in tool and tool.get("output_example") is not None
        )
        if not configured:
            issues.append(
                WorkflowValidationIssue(
                    location + ".tool_id",
                    "Parser 工具必须配置 JSON output_example",
                )
            )
            continue
        try:
            parser_examples[step.step_id] = normalize_request_template(
                tool.get("output_example")
            )
        except RunPreparationError as exc:
            issues.append(
                WorkflowValidationIssue(
                    location + ".tool_id",
                    f"Parser output_example 无效: {exc}",
                )
            )

    for check_index, check in enumerate(definition.checks):
        for evaluator_index, step in enumerate(check.evaluators):
            location = f"checks[{check_index}].evaluators[{evaluator_index}]"
            _validate_tool_step(step, location, tools, issues, tool_snapshots)
            _validate_inputs(step, location, parser_examples, issues)
        if check.aggregator is not None:
            location = f"checks[{check_index}].aggregator"
            _validate_tool_step(
                check.aggregator,
                location,
                tools,
                issues,
                tool_snapshots,
                require_script=True,
            )
            if check.aggregator.inputs:
                issues.append(
                    WorkflowValidationIssue(
                        location + ".inputs",
                        "Check Aggregator 输入由系统注入 step_results",
                    )
                )
    if definition.case_aggregator is not None:
        _validate_tool_step(
            definition.case_aggregator,
            "case_aggregator",
            tools,
            issues,
            tool_snapshots,
            require_script=True,
        )
        if definition.case_aggregator.inputs:
            issues.append(
                WorkflowValidationIssue(
                    "case_aggregator.inputs",
                    "Case Aggregator 输入由系统注入 check_results",
                )
            )

    if issues:
        raise WorkflowValidationError(issues)
    return tool_snapshots


def _validate_tool_step(
    step: WorkflowStepDefinition,
    location: str,
    tools: ToolLookup,
    issues: list[WorkflowValidationIssue],
    snapshots: dict[str, dict],
    *,
    require_script: bool = False,
) -> dict | None:
    tool = tools.get_tool(step.tool_id)
    if tool is None:
        issues.append(
            WorkflowValidationIssue(location + ".tool_id", f"工具不存在: {step.tool_id}")
        )
        return None
    snapshots[step.tool_id] = deepcopy(tool)
    if require_script and tool.get("type") != "script":
        issues.append(
            WorkflowValidationIssue(location + ".tool_id", "Aggregator 只允许 Script")
        )
    if tool.get("type") == "script" and step.parameters:
        issues.append(
            WorkflowValidationIssue(
                location + ".parameters",
                "Script 工具不支持节点参数，请通过 inputs 传值",
            )
        )
    return tool


def _validate_inputs(
    step: WorkflowStepDefinition,
    location: str,
    parser_examples: dict[str, Any],
    issues: list[WorkflowValidationIssue],
) -> None:
    for input_name, reference in step.inputs.items():
        input_location = f"{location}.inputs.{input_name}"
        if reference.source == "response":
            continue
        if reference.source not in parser_examples:
            issues.append(
                WorkflowValidationIssue(
                    input_location + ".source",
                    "来源必须是 response 或当前步骤之前可用的 Parser",
                )
            )
            continue
        try:
            resolve_json_pointer(
                parser_examples[reference.source],
                reference.pointer,
            )
        except KeyError as exc:
            issues.append(
                WorkflowValidationIssue(
                    input_location + ".pointer",
                    str(exc),
                )
            )


def build_workflow_snapshot(
    workflow: WorkflowRecord,
    tools: ToolLookup,
) -> dict[str, Any]:
    """冻结 Workflow 和全部引用工具代码、参数及元数据。"""
    definition = WorkflowDefinition.model_validate(workflow.definition)
    tool_snapshots = validate_workflow_definition(definition, tools)
    frozen_tools: dict[str, dict] = {}
    for tool_id, tool in tool_snapshots.items():
        frozen = normalize_request_template(tool)
        frozen["code_sha256"] = hashlib.sha256(
            str(frozen.get("code", "")).encode("utf-8")
        ).hexdigest()
        frozen_tools[tool_id] = frozen
    return {
        "schema_version": 1,
        "workflow": workflow.model_dump(mode="json"),
        "tools": frozen_tools,
    }


class WorkflowService:
    """Workflow 校验、CRUD 与快照的事务边界。"""

    def __init__(self, repository: RunRepository, tools: ToolLookup):
        self.repository = repository
        self.tools = tools

    def create(self, draft: WorkflowDraft) -> WorkflowRecord:
        validate_workflow_definition(draft.definition, self.tools)
        return self.repository.create_workflow(
            WorkflowRecord(
                name=draft.name,
                description=draft.description,
                definition=draft.definition.model_dump(mode="json"),
            )
        )

    def update(self, workflow_id: str, draft: WorkflowDraft) -> WorkflowRecord:
        current = self.repository.get_workflow(workflow_id)
        if current is None:
            raise KeyError(workflow_id)
        validate_workflow_definition(draft.definition, self.tools)
        return self.repository.update_workflow(
            WorkflowRecord(
                id=current.id,
                created_at=current.created_at,
                updated_at=utc_now_iso(),
                name=draft.name,
                description=draft.description,
                definition=draft.definition.model_dump(mode="json"),
            )
        )

    def validation_issues(
        self,
        workflow: WorkflowRecord,
    ) -> tuple[WorkflowValidationIssue, ...]:
        try:
            validate_workflow_definition(
                WorkflowDefinition.model_validate(workflow.definition),
                self.tools,
            )
        except WorkflowValidationError as exc:
            return exc.issues
        return ()

    def snapshot(self, workflow_id: str) -> dict[str, Any]:
        workflow = self.repository.get_workflow(workflow_id)
        if workflow is None:
            raise KeyError(workflow_id)
        return build_workflow_snapshot(workflow, self.tools)
