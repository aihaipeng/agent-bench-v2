"""单个 Case 的 Connector、Parser、Check 与 Aggregator 执行器。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from execution.artifacts import ArtifactStore
from execution.connector import ConnectorResult, FastAPIConnector
from execution.models import (
    ArtifactRecord,
    BusinessStatus,
    CaseRunRecord,
    ExecutionStatus,
    RetentionClass,
    RunRecord,
    StepRunRecord,
    StepStage,
    TargetRecord,
    WorkflowRecord,
    utc_now_iso,
)
from execution.repository import RunRepository
from execution.results import (
    ToolResultError,
    standardize_case_result,
    standardize_check_result,
    standardize_evaluator_result,
    validate_aggregator_worker_result,
    validate_case_aggregator_worker_result,
    validate_evaluator_worker_result,
    validate_parser_worker_result,
)
from execution.workflows import (
    CheckDefinition,
    WorkflowDefinition,
    WorkflowStepDefinition,
    resolve_json_pointer,
)
from web.agent_runtime import (
    interrupt_python_run,
    stream_agent_python,
    stream_script_python,
)


ToolRunner = Callable[
    [dict[str, Any], WorkflowStepDefinition, dict[str, Any], str, Callable[[str], None]],
    Awaitable[dict[str, Any]],
]


@dataclass(frozen=True)
class CaseExecutionResult:
    case_run: CaseRunRecord
    result: dict[str, Any]
    result_artifact: ArtifactRecord
    connector_result: ConnectorResult


class CaseWorkflowExecutionError(RuntimeError):
    """Case 已持久化为 ERROR 后通知调度层。"""

    def __init__(
        self,
        message: str,
        *,
        case_run: CaseRunRecord,
        result: dict[str, Any],
        result_artifact: ArtifactRecord | None,
    ):
        super().__init__(message)
        self.case_run = case_run
        self.result = result
        self.result_artifact = result_artifact


class _StepExecutionError(RuntimeError):
    def __init__(self, message: str, step_run: StepRunRecord):
        super().__init__(message)
        self.step_run = step_run


class _CaseAggregationError(RuntimeError):
    def __init__(self, message: str, result: dict[str, Any]):
        super().__init__(message)
        self.result = result


class CaseWorkflowExecutor:
    """执行一个 Case，状态和全部中间结果实时持久化。"""

    def __init__(
        self,
        repository: RunRepository,
        artifact_store: ArtifactStore,
        connector: FastAPIConnector,
        *,
        tool_runner: ToolRunner | None = None,
    ):
        self.repository = repository
        self.artifact_store = artifact_store
        self.connector = connector
        self.tool_runner = tool_runner or self._run_frozen_tool

    async def execute(
        self,
        *,
        run: RunRecord,
        case_run: CaseRunRecord,
        target: TargetRecord,
        request_body: Any,
        workflow_snapshot: dict[str, Any],
        timeout_seconds: float = 600,
        connection_retry_count: int = 0,
        retry_interval_seconds: float = 0,
        request_slot: AbstractAsyncContextManager[None] | None = None,
    ) -> CaseExecutionResult:
        """执行完整 Case；业务 FAIL 仍返回执行 SUCCEEDED。"""
        active_case = self.repository.update_case_run_status(
            case_run.id,
            ExecutionStatus.RUNNING,
            business_status=None,
            error=None,
            started_at=utc_now_iso(),
        )
        try:
            definition, tools = self._read_workflow_snapshot(workflow_snapshot)
            if request_slot is None:
                connector_result = await self._invoke_connector(
                    run=run,
                    case_run=active_case,
                    target=target,
                    request_body=request_body,
                    timeout_seconds=timeout_seconds,
                    connection_retry_count=connection_retry_count,
                    retry_interval_seconds=retry_interval_seconds,
                )
            else:
                async with request_slot:
                    connector_result = await self._invoke_connector(
                        run=run,
                        case_run=active_case,
                        target=target,
                        request_body=request_body,
                        timeout_seconds=timeout_seconds,
                        connection_retry_count=connection_retry_count,
                        retry_interval_seconds=retry_interval_seconds,
                    )
            response = self.artifact_store.read_json(
                connector_result.response_artifact.relative_path
            )
            final_result = await self._execute_workflow(
                run=run,
                case_run=active_case,
                definition=definition,
                tools=tools,
                response=response,
            )
            result_artifact = self._persist_json_artifact(
                run=run,
                case_run=active_case,
                kind="case_result",
                area="case-results",
                content=final_result,
                retention=RetentionClass.FINAL_LONG_TERM,
            )
            if final_result["status"] in {
                BusinessStatus.FAIL.value,
                BusinessStatus.ERROR.value,
            }:
                self._retain_case_failure_artifacts(run.id, active_case.id)
            completed_case = self.repository.update_case_run_status(
                active_case.id,
                ExecutionStatus.SUCCEEDED,
                business_status=BusinessStatus(final_result["status"]),
                error=None,
                finished_at=utc_now_iso(),
            )
            return CaseExecutionResult(
                case_run=completed_case,
                result=final_result,
                result_artifact=result_artifact,
                connector_result=connector_result,
            )
        except asyncio.CancelledError:
            self.repository.update_case_run_status(
                active_case.id,
                ExecutionStatus.CANCELLED,
                error="Case 本地执行已取消",
                finished_at=utc_now_iso(),
            )
            raise
        except _CaseAggregationError as exc:
            self._raise_case_error(active_case, run, str(exc), exc.result, exc)
        except Exception as exc:
            error_result = {
                "case_id": active_case.case_id,
                "status": BusinessStatus.ERROR.value,
                "reason": str(exc) or type(exc).__name__,
                "check_items": {},
            }
            self._raise_case_error(active_case, run, error_result["reason"], error_result, exc)
        raise RuntimeError("Case 执行未产生结果")

    async def _invoke_connector(self, **kwargs: Any) -> ConnectorResult:
        return await self.connector.invoke(**kwargs)

    async def _execute_workflow(
        self,
        *,
        run: RunRecord,
        case_run: CaseRunRecord,
        definition: WorkflowDefinition,
        tools: dict[str, dict[str, Any]],
        response: Any,
    ) -> dict[str, Any]:
        parser_outputs: dict[str, Any] = {}
        for index, step in enumerate(definition.parsers):
            inputs = self._build_inputs(step, response, parser_outputs)
            output, _ = await self._run_step(
                run=run,
                case_run=case_run,
                step=step,
                tool=self._tool_snapshot(tools, step),
                stage=StepStage.PARSER,
                sequence=index,
                check_item=None,
                inputs=inputs,
                validate=validate_parser_worker_result,
                transform=lambda value: value,
                result_kind="parser_result",
            )
            parser_outputs[step.step_id] = output

        check_results_list = await asyncio.gather(
            *(
                self._execute_check(
                    run=run,
                    case_run=case_run,
                    check=check,
                    check_index=index,
                    tools=tools,
                    response=response,
                    parser_outputs=parser_outputs,
                )
                for index, check in enumerate(definition.checks)
            )
        )
        check_results = {
            check.check_item: result
            for check, result in zip(definition.checks, check_results_list, strict=True)
        }
        if definition.case_aggregator is None:
            only_check = definition.checks[0]
            check_result = check_results[only_check.check_item]
            return standardize_case_result(
                {
                    "status": check_result["status"],
                    "reason": check_result.get("reason", ""),
                },
                case_id=case_run.case_id,
                check_results=check_results,
            )

        step = definition.case_aggregator
        try:
            result, _ = await self._run_step(
                run=run,
                case_run=case_run,
                step=step,
                tool=self._tool_snapshot(tools, step),
                stage=StepStage.CASE_AGGREGATOR,
                sequence=900_000,
                check_item=None,
                inputs={"check_results": check_results},
                validate=validate_case_aggregator_worker_result,
                transform=lambda decision: standardize_case_result(
                    decision,
                    case_id=case_run.case_id,
                    check_results=check_results,
                ),
                result_kind="case_aggregator_result",
            )
            return result
        except _StepExecutionError as exc:
            result = standardize_case_result(
                {"status": "ERROR", "reason": str(exc)},
                case_id=case_run.case_id,
                check_results=check_results,
            )
            self._persist_json_artifact(
                run=run,
                case_run=case_run,
                step_run=exc.step_run,
                kind="case_aggregator_result",
                area=f"steps/{exc.step_run.id}",
                content=result,
                retention=RetentionClass.FAILURE_LONG_TERM,
            )
            raise _CaseAggregationError(str(exc), result) from exc

    async def _execute_check(
        self,
        *,
        run: RunRecord,
        case_run: CaseRunRecord,
        check: CheckDefinition,
        check_index: int,
        tools: dict[str, dict[str, Any]],
        response: Any,
        parser_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        evaluator_results = await asyncio.gather(
            *(
                self._execute_evaluator(
                    run=run,
                    case_run=case_run,
                    check=check,
                    check_index=check_index,
                    evaluator_index=index,
                    step=step,
                    tool=self._tool_snapshot(tools, step),
                    inputs=self._build_inputs(step, response, parser_outputs),
                )
                for index, step in enumerate(check.evaluators)
            )
        )
        step_results = {
            step.step_id: result
            for step, result in zip(check.evaluators, evaluator_results, strict=True)
        }
        if check.aggregator is None:
            evaluator = evaluator_results[0]
            check_result = standardize_check_result(
                {"status": evaluator["status"], "reason": evaluator["reason"]},
                case_id=case_run.case_id,
                check_item=check.check_item,
                step_results=step_results,
            )
        else:
            step = check.aggregator
            try:
                check_result, _ = await self._run_step(
                    run=run,
                    case_run=case_run,
                    step=step,
                    tool=self._tool_snapshot(tools, step),
                    stage=StepStage.CHECK_AGGREGATOR,
                    sequence=500_000 + check_index,
                    check_item=check.check_item,
                    inputs={"step_results": step_results},
                    validate=validate_aggregator_worker_result,
                    transform=lambda decision: standardize_check_result(
                        decision,
                        case_id=case_run.case_id,
                        check_item=check.check_item,
                        step_results=step_results,
                    ),
                    result_kind="check_aggregator_result",
                )
            except _StepExecutionError as exc:
                check_result = standardize_check_result(
                    {"status": "ERROR", "reason": str(exc)},
                    case_id=case_run.case_id,
                    check_item=check.check_item,
                    step_results=step_results,
                )
                self._persist_json_artifact(
                    run=run,
                    case_run=case_run,
                    step_run=exc.step_run,
                    kind="check_aggregator_result",
                    area=f"steps/{exc.step_run.id}",
                    content=check_result,
                    retention=RetentionClass.FAILURE_LONG_TERM,
                )

        retention = self._business_retention(check_result["status"])
        self._persist_json_artifact(
            run=run,
            case_run=case_run,
            kind="check_result",
            area=f"checks/{check_index}",
            content=check_result,
            retention=retention,
        )
        return check_result

    async def _execute_evaluator(
        self,
        *,
        run: RunRecord,
        case_run: CaseRunRecord,
        check: CheckDefinition,
        check_index: int,
        evaluator_index: int,
        step: WorkflowStepDefinition,
        tool: dict[str, Any],
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            result, _ = await self._run_step(
                run=run,
                case_run=case_run,
                step=step,
                tool=tool,
                stage=StepStage.EVALUATOR,
                sequence=100_000 + check_index * 1_000 + evaluator_index,
                check_item=check.check_item,
                inputs=inputs,
                validate=validate_evaluator_worker_result,
                transform=lambda raw: standardize_evaluator_result(
                    raw,
                    case_id=case_run.case_id,
                    check_item=check.check_item,
                    step_id=step.step_id,
                ),
                result_kind="evaluator_result",
            )
            return result
        except _StepExecutionError as exc:
            error_result = standardize_evaluator_result(
                {"status": "ERROR", "reason": str(exc), "data": {}},
                case_id=case_run.case_id,
                check_item=check.check_item,
                step_id=step.step_id,
            )
            self._persist_json_artifact(
                run=run,
                case_run=case_run,
                step_run=exc.step_run,
                kind="evaluator_result",
                area=f"steps/{exc.step_run.id}",
                content=error_result,
                retention=RetentionClass.FAILURE_LONG_TERM,
            )
            return error_result

    async def _run_step(
        self,
        *,
        run: RunRecord,
        case_run: CaseRunRecord,
        step: WorkflowStepDefinition,
        tool: dict[str, Any],
        stage: StepStage,
        sequence: int,
        check_item: str | None,
        inputs: dict[str, Any],
        validate: Callable[[dict[str, Any]], Any],
        transform: Callable[[Any], Any],
        result_kind: str,
    ) -> tuple[Any, StepRunRecord]:
        execution_number = self.repository.next_step_execution_number(
            case_run.id,
            stage.value,
            step.step_id,
        )
        step_run = self.repository.create_step_run(
            StepRunRecord(
                case_run_id=case_run.id,
                stage=stage,
                sequence=sequence,
                execution_number=execution_number,
                check_item=check_item,
                step_id=step.step_id,
                tool_id=str(tool.get("id") or step.tool_id),
                tool_name=str(tool.get("name") or ""),
                tool_type=str(tool.get("type") or ""),
                tool_code_hash=str(tool.get("code_sha256") or ""),
                status=ExecutionStatus.RUNNING,
                started_at=utc_now_iso(),
            )
        )
        logs: list[str] = []
        log_saved = False
        try:
            self._verify_tool_hash(tool)
            worker_result = await self.tool_runner(
                tool,
                step,
                inputs,
                step_run.id,
                logs.append,
            )
            validated = validate(worker_result)
            output = transform(validated)
            business_status = self._result_business_status(output)
            retention = (
                self._business_retention(business_status.value)
                if business_status is not None
                else RetentionClass.SUCCESS_TEMPORARY
            )
            self._persist_text_artifact(
                run=run,
                case_run=case_run,
                step_run=step_run,
                kind="tool_log",
                area=f"steps/{step_run.id}",
                content="".join(logs),
                retention=retention,
            )
            log_saved = True
            self._persist_json_artifact(
                run=run,
                case_run=case_run,
                step_run=step_run,
                kind=result_kind,
                area=f"steps/{step_run.id}",
                content=output,
                retention=retention,
            )
            completed = self.repository.update_step_run_status(
                step_run.id,
                ExecutionStatus.SUCCEEDED,
                business_status=business_status,
                error=None,
                finished_at=utc_now_iso(),
            )
            return output, completed
        except asyncio.CancelledError:
            interrupt_python_run(step_run.id)
            if not log_saved:
                self._persist_text_artifact(
                    run=run,
                    case_run=case_run,
                    step_run=step_run,
                    kind="tool_log",
                    area=f"steps/{step_run.id}",
                    content="".join(logs),
                    retention=RetentionClass.FAILURE_LONG_TERM,
                )
            self.repository.update_step_run_status(
                step_run.id,
                ExecutionStatus.CANCELLED,
                error="工具本地执行已取消",
                finished_at=utc_now_iso(),
            )
            raise
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            if not logs or message not in logs[-1]:
                logs.append(f"{type(exc).__name__}: {message}\n")
            if not log_saved:
                self._persist_text_artifact(
                    run=run,
                    case_run=case_run,
                    step_run=step_run,
                    kind="tool_log",
                    area=f"steps/{step_run.id}",
                    content="".join(logs),
                    retention=RetentionClass.FAILURE_LONG_TERM,
                )
            failed = self.repository.update_step_run_status(
                step_run.id,
                ExecutionStatus.ERROR,
                business_status=BusinessStatus.ERROR,
                error=message,
                finished_at=utc_now_iso(),
            )
            raise _StepExecutionError(
                f"{step.step_id} 执行失败: {message}",
                failed,
            ) from exc

    async def _run_frozen_tool(
        self,
        tool: dict[str, Any],
        step: WorkflowStepDefinition,
        inputs: dict[str, Any],
        run_id: str,
        on_log: Callable[[str], None],
    ) -> dict[str, Any]:
        code = str(tool.get("code") or "")
        if tool.get("type") == "agent":
            parameters = {
                **dict(tool.get("parameters") or {}),
                **step.parameters,
            }
            return await asyncio.to_thread(
                stream_agent_python,
                code,
                parameters,
                on_log,
                run_id,
                120,
                inputs,
                True,
            )
        return await asyncio.to_thread(
            stream_script_python,
            code,
            on_log,
            run_id,
            120,
            inputs,
            True,
        )

    @staticmethod
    def _read_workflow_snapshot(
        snapshot: dict[str, Any],
    ) -> tuple[WorkflowDefinition, dict[str, dict[str, Any]]]:
        if not isinstance(snapshot, dict):
            raise ValueError("Workflow 快照必须是对象")
        workflow = WorkflowRecord.model_validate(snapshot.get("workflow"))
        definition = WorkflowDefinition.model_validate(workflow.definition)
        tools = snapshot.get("tools")
        if not isinstance(tools, dict):
            raise ValueError("Workflow 快照缺少 tools")
        return definition, tools

    @staticmethod
    def _tool_snapshot(
        tools: dict[str, dict[str, Any]],
        step: WorkflowStepDefinition,
    ) -> dict[str, Any]:
        tool = tools.get(step.tool_id)
        if not isinstance(tool, dict):
            raise ValueError(f"Workflow 快照缺少工具: {step.tool_id}")
        return tool

    @staticmethod
    def _verify_tool_hash(tool: dict[str, Any]) -> None:
        code = str(tool.get("code") or "")
        expected = str(tool.get("code_sha256") or "")
        actual = hashlib.sha256(code.encode("utf-8")).hexdigest()
        if expected != actual:
            raise ValueError(f"工具代码哈希不一致: {tool.get('id', '')}")

    @staticmethod
    def _build_inputs(
        step: WorkflowStepDefinition,
        response: Any,
        parser_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        inputs: dict[str, Any] = {}
        for name, reference in step.inputs.items():
            source = (
                response
                if reference.source == "response"
                else parser_outputs[reference.source]
            )
            inputs[name] = resolve_json_pointer(source, reference.pointer)
        return inputs

    @staticmethod
    def _result_business_status(result: Any) -> BusinessStatus | None:
        if isinstance(result, dict) and result.get("status") in {
            item.value for item in BusinessStatus
        }:
            return BusinessStatus(result["status"])
        return None

    @staticmethod
    def _business_retention(status: str) -> RetentionClass:
        return (
            RetentionClass.SUCCESS_TEMPORARY
            if status in {BusinessStatus.PASS.value, BusinessStatus.SKIP.value}
            else RetentionClass.FAILURE_LONG_TERM
        )

    def _persist_json_artifact(
        self,
        *,
        run: RunRecord,
        case_run: CaseRunRecord,
        kind: str,
        area: str,
        content: Any,
        retention: RetentionClass,
        step_run: StepRunRecord | None = None,
    ) -> ArtifactRecord:
        artifact_id = uuid4().hex
        relative_path = (
            f"runs/{run.id}/cases/{case_run.id}/{area}/{artifact_id}.json"
        )
        info = self.artifact_store.write_json(relative_path, content)
        return self._index_artifact(
            artifact_id=artifact_id,
            run=run,
            case_run=case_run,
            step_run=step_run,
            kind=kind,
            retention=retention,
            relative_path=info.relative_path,
            size_bytes=info.size_bytes,
            sha256=info.sha256,
        )

    def _persist_text_artifact(
        self,
        *,
        run: RunRecord,
        case_run: CaseRunRecord,
        kind: str,
        area: str,
        content: str,
        retention: RetentionClass,
        step_run: StepRunRecord | None = None,
    ) -> ArtifactRecord:
        artifact_id = uuid4().hex
        relative_path = f"runs/{run.id}/cases/{case_run.id}/{area}/{artifact_id}.log"
        info = self.artifact_store.write_text(relative_path, content)
        return self._index_artifact(
            artifact_id=artifact_id,
            run=run,
            case_run=case_run,
            step_run=step_run,
            kind=kind,
            retention=retention,
            relative_path=info.relative_path,
            size_bytes=info.size_bytes,
            sha256=info.sha256,
        )

    def _index_artifact(
        self,
        *,
        artifact_id: str,
        run: RunRecord,
        case_run: CaseRunRecord,
        step_run: StepRunRecord | None,
        kind: str,
        retention: RetentionClass,
        relative_path: str,
        size_bytes: int,
        sha256: str,
    ) -> ArtifactRecord:
        record = ArtifactRecord(
            id=artifact_id,
            run_id=run.id,
            case_run_id=case_run.id,
            step_run_id=step_run.id if step_run else None,
            kind=kind,
            relative_path=relative_path,
            size_bytes=size_bytes,
            sha256=sha256,
            retention_class=retention,
        )
        try:
            return self.repository.create_artifact(record)
        except Exception:
            self.artifact_store.delete(relative_path)
            raise

    def _raise_case_error(
        self,
        case_run: CaseRunRecord,
        run: RunRecord,
        message: str,
        result: dict[str, Any],
        cause: Exception,
    ) -> None:
        artifact: ArtifactRecord | None = None
        try:
            artifact = self._persist_json_artifact(
                run=run,
                case_run=case_run,
                kind="case_result",
                area="case-results",
                content=result,
                retention=RetentionClass.FINAL_LONG_TERM,
            )
        finally:
            self._retain_case_failure_artifacts(run.id, case_run.id)
            failed_case = self.repository.update_case_run_status(
                case_run.id,
                ExecutionStatus.ERROR,
                business_status=BusinessStatus.ERROR,
                error=message,
                finished_at=utc_now_iso(),
            )
        raise CaseWorkflowExecutionError(
            message,
            case_run=failed_case,
            result=result,
            result_artifact=artifact,
        ) from cause

    def _retain_case_failure_artifacts(self, run_id: str, case_run_id: str) -> None:
        for artifact in self.repository.list_artifacts(
            run_id,
            case_run_id=case_run_id,
        ):
            if artifact.retention_class == RetentionClass.SUCCESS_TEMPORARY:
                self.repository.update_artifact_retention(
                    artifact.id,
                    RetentionClass.FAILURE_LONG_TERM,
                )
