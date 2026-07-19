import asyncio
import hashlib
import sqlite3

import httpx
import pytest

from execution import (
    ArtifactStore,
    BusinessStatus,
    CaseRunRecord,
    CaseWorkflowExecutionError,
    CaseWorkflowExecutor,
    ExecutionStatus,
    FastAPIConnector,
    RunRecord,
    RunRepository,
    TargetRecord,
    WorkflowDefinition,
    WorkflowRecord,
)
from execution.repository import SCHEMA_VERSION


def _tool(tool_id, *, tool_type="script", code="response = None"):
    return {
        "schema_version": 1,
        "id": tool_id,
        "type": tool_type,
        "name": f"工具 {tool_id}",
        "description": "",
        "parameters": (
            {
                "model": "model",
                "model_provider": "provider",
                "api_key": "secret",
                "base_url": "https://example.test",
                "system_prompt": "system",
                "human_message": "human",
            }
            if tool_type == "agent"
            else {}
        ),
        "output_example": None,
        "output_example_configured": False,
        "created_at": "2026-07-19T10:00:00",
        "updated_at": "2026-07-19T10:00:00",
        "code": code,
        "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
    }


def _snapshot(definition, tools):
    workflow = WorkflowRecord(
        id="workflow-1",
        name="Workflow",
        definition=WorkflowDefinition.model_validate(definition).model_dump(mode="json"),
    )
    return {
        "schema_version": 1,
        "workflow": workflow.model_dump(mode="json"),
        "tools": {tool["id"]: tool for tool in tools},
    }


def _context(tmp_path, response_body=None):
    repository = RunRepository(tmp_path / "run_storage" / "agent_bench.sqlite3")
    store = ArtifactStore(tmp_path / "run_storage" / "artifacts")
    target = repository.create_target(
        TargetRecord(
            id="target-1",
            name="Target",
            base_url="http://agent.test",
            path="/api/agent/invoke",
            target_total_concurrency=4,
        )
    )
    run = repository.create_run(
        RunRecord(
            id="run-1",
            testset_filename="cases.xlsx",
            sheet_name="Sheet1",
            target_id=target.id,
        )
    )
    case = repository.create_case_run(
        CaseRunRecord(
            id="case-run-1",
            run_id=run.id,
            case_id="case_001",
            row_number=2,
            question="问题",
        )
    )
    body = response_body or {
        "code": "200",
        "data": {"answer": "企业 Agent 回答"},
    }

    async def handler(request):
        return httpx.Response(200, json=body)

    connector = FastAPIConnector(
        repository,
        store,
        transport=httpx.MockTransport(handler),
    )
    return repository, store, connector, target, run, case


class _ControlledRunner:
    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = []
        self.completed = []
        self.active = 0
        self.max_active = 0
        self.received_inputs = {}

    async def __call__(self, tool, step, inputs, run_id, on_log):
        self.calls.append(step.step_id)
        self.received_inputs[step.step_id] = inputs
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        on_log(f"{step.step_id} started\n")
        try:
            await asyncio.sleep(0.02)
            action = self.behavior[step.step_id]
            if isinstance(action, Exception):
                raise action
            response = action(inputs) if callable(action) else action
            return {"ok": True, "logs": "", "response": response}
        finally:
            self.active -= 1
            self.completed.append(step.step_id)


def _multi_workflow_snapshot():
    definition = {
        "parsers": [
            {
                "step_id": "parser_one",
                "tool_id": "parser-one-tool",
                "inputs": {
                    "answer": {"source": "response", "pointer": "/data/answer"}
                },
            },
            {
                "step_id": "parser_two",
                "tool_id": "parser-two-tool",
                "inputs": {
                    "answer": {"source": "parser_one", "pointer": "/answer"}
                },
            },
        ],
        "checks": [
            {
                "check_item": "intent",
                "evaluators": [
                    {
                        "step_id": "intent_rule",
                        "tool_id": "intent-rule-tool",
                        "inputs": {
                            "answer": {"source": "parser_two", "pointer": "/answer"}
                        },
                    },
                    {
                        "step_id": "intent_agent",
                        "tool_id": "intent-agent-tool",
                        "inputs": {},
                    },
                ],
                "aggregator": {
                    "step_id": "intent_aggregator",
                    "tool_id": "check-aggregator-tool",
                },
            },
            {
                "check_item": "i18n",
                "evaluators": [
                    {
                        "step_id": "i18n_agent",
                        "tool_id": "i18n-agent-tool",
                        "inputs": {},
                    }
                ],
            },
        ],
        "case_aggregator": {
            "step_id": "case_aggregator",
            "tool_id": "case-aggregator-tool",
        },
    }
    tool_ids = [
        "parser-one-tool",
        "parser-two-tool",
        "intent-rule-tool",
        "intent-agent-tool",
        "check-aggregator-tool",
        "i18n-agent-tool",
        "case-aggregator-tool",
    ]
    return _snapshot(definition, [_tool(tool_id) for tool_id in tool_ids])


def test_full_case_executes_parsers_in_order_checks_in_parallel_and_keeps_errors(
    tmp_path,
):
    repository, store, connector, target, run, case = _context(tmp_path)
    runner = _ControlledRunner(
        {
            "parser_one": lambda inputs: {"answer": inputs["answer"]},
            "parser_two": lambda inputs: {"answer": inputs["answer"] + " parsed"},
            "intent_rule": {
                "status": "FAIL",
                "reason": "规则失败",
                "data": {"score": 0},
            },
            "intent_agent": RuntimeError("模型调用失败"),
            "intent_aggregator": lambda inputs: {
                "status": "FAIL",
                "reason": ",".join(
                    sorted(result["status"] for result in inputs["step_results"].values())
                ),
            },
            "i18n_agent": {"status": "PASS", "reason": "中文", "data": {}},
            "case_aggregator": lambda inputs: {
                "status": "FAIL",
                "reason": "intent 未通过",
            },
        }
    )
    executor = CaseWorkflowExecutor(
        repository,
        store,
        connector,
        tool_runner=runner,
    )

    result = asyncio.run(
        executor.execute(
            run=run,
            case_run=case,
            target=target,
            request_body={"question": case.question},
            workflow_snapshot=_multi_workflow_snapshot(),
        )
    )

    assert runner.calls[:2] == ["parser_one", "parser_two"]
    assert runner.completed.index("parser_one") < runner.calls.index("parser_two")
    assert runner.received_inputs["parser_two"] == {"answer": "企业 Agent 回答"}
    assert runner.received_inputs["intent_rule"] == {
        "answer": "企业 Agent 回答 parsed"
    }
    assert runner.max_active >= 3
    assert set(runner.received_inputs["intent_aggregator"]["step_results"]) == {
        "intent_rule",
        "intent_agent",
    }
    assert runner.received_inputs["intent_aggregator"]["step_results"][
        "intent_agent"
    ]["status"] == "ERROR"
    assert set(runner.received_inputs["case_aggregator"]["check_results"]) == {
        "intent",
        "i18n",
    }
    assert result.case_run.status == ExecutionStatus.SUCCEEDED
    assert result.case_run.business_status == BusinessStatus.FAIL
    assert result.result["status"] == "FAIL"
    assert result.result["check_items"]["intent"]["step_results"][
        "intent_agent"
    ]["status"] == "ERROR"

    steps = repository.list_step_runs(case.id)
    assert len(steps) == 7
    assert [step.stage for step in steps].count("PARSER") == 2
    assert [step.stage for step in steps].count("EVALUATOR") == 3
    assert [step.stage for step in steps].count("CHECK_AGGREGATOR") == 1
    assert [step.stage for step in steps].count("CASE_AGGREGATOR") == 1
    assert next(step for step in steps if step.step_id == "intent_agent").status == "ERROR"
    assert all(step.tool_name.startswith("工具 ") for step in steps)
    artifacts = repository.list_artifacts(run.id, case_run_id=case.id)
    kinds = [artifact.kind for artifact in artifacts]
    assert kinds.count("response") == 1
    assert kinds.count("check_result") == 2
    assert kinds.count("case_result") == 1
    assert kinds.count("tool_log") == 7
    assert result.result_artifact.retention_class == "FINAL_LONG_TERM"
    assert store.read_json(result.result_artifact.relative_path) == result.result
    assert all(
        artifact.retention_class != "SUCCESS_TEMPORARY"
        for artifact in artifacts
    )


def test_single_evaluator_and_single_check_create_no_aggregator_steps(tmp_path):
    repository, store, connector, target, run, case = _context(tmp_path)
    definition = {
        "checks": [
            {
                "check_item": "tool_use",
                "evaluators": [
                    {
                        "step_id": "tool_use_rule",
                        "tool_id": "rule-tool",
                        "inputs": {
                            "answer": {"source": "response", "pointer": "/data/answer"}
                        },
                    }
                ],
            }
        ]
    }
    runner = _ControlledRunner(
        {
            "tool_use_rule": {
                "status": "PASS",
                "reason": "工具已调用",
                "data": {},
            }
        }
    )
    executor = CaseWorkflowExecutor(
        repository, store, connector, tool_runner=runner
    )

    result = asyncio.run(
        executor.execute(
            run=run,
            case_run=case,
            target=target,
            request_body={"question": "问题"},
            workflow_snapshot=_snapshot(definition, [_tool("rule-tool")]),
        )
    )

    assert runner.calls == ["tool_use_rule"]
    assert [step.stage for step in repository.list_step_runs(case.id)] == ["EVALUATOR"]
    assert result.result["status"] == "PASS"
    assert result.result["check_items"]["tool_use"]["step_results"][
        "tool_use_rule"
    ]["status"] == "PASS"


def test_parser_failure_stops_checks_and_marks_case_execution_error(tmp_path):
    repository, store, connector, target, run, case = _context(tmp_path)
    definition = {
        "parsers": [{"step_id": "parser", "tool_id": "parser-tool"}],
        "checks": [
            {
                "check_item": "intent",
                "evaluators": [{"step_id": "never", "tool_id": "eval-tool"}],
            }
        ],
    }
    runner = _ControlledRunner(
        {"parser": RuntimeError("parser broken"), "never": {"status": "PASS", "reason": ""}}
    )
    executor = CaseWorkflowExecutor(repository, store, connector, tool_runner=runner)

    with pytest.raises(CaseWorkflowExecutionError) as caught:
        asyncio.run(
            executor.execute(
                run=run,
                case_run=case,
                target=target,
                request_body={},
                workflow_snapshot=_snapshot(
                    definition,
                    [_tool("parser-tool"), _tool("eval-tool")],
                ),
            )
        )

    assert runner.calls == ["parser"]
    assert caught.value.case_run.status == "ERROR"
    assert caught.value.case_run.business_status == "ERROR"
    assert caught.value.result["check_items"] == {}
    steps = repository.list_step_runs(case.id)
    assert len(steps) == 1
    assert steps[0].status == "ERROR"
    assert store.read_json(caught.value.result_artifact.relative_path)["status"] == "ERROR"


def test_check_aggregator_error_continues_to_case_aggregator(tmp_path):
    repository, store, connector, target, run, case = _context(tmp_path)
    snapshot = _multi_workflow_snapshot()
    runner = _ControlledRunner(
        {
            "parser_one": {"answer": "one"},
            "parser_two": {"answer": "two"},
            "intent_rule": {"status": "PASS", "reason": "ok"},
            "intent_agent": {"status": "PASS", "reason": "ok"},
            "intent_aggregator": RuntimeError("aggregator broken"),
            "i18n_agent": {"status": "PASS", "reason": "ok"},
            "case_aggregator": lambda inputs: {
                "status": "ERROR",
                "reason": inputs["check_results"]["intent"]["reason"],
            },
        }
    )
    executor = CaseWorkflowExecutor(repository, store, connector, tool_runner=runner)

    result = asyncio.run(
        executor.execute(
            run=run,
            case_run=case,
            target=target,
            request_body={},
            workflow_snapshot=snapshot,
        )
    )

    assert "case_aggregator" in runner.calls
    assert result.case_run.status == "SUCCEEDED"
    assert result.case_run.business_status == "ERROR"
    assert result.result["check_items"]["intent"]["status"] == "ERROR"


def test_case_aggregator_failure_marks_case_error_but_preserves_check_results(tmp_path):
    repository, store, connector, target, run, case = _context(tmp_path)
    runner = _ControlledRunner(
        {
            "parser_one": {"answer": "one"},
            "parser_two": {"answer": "two"},
            "intent_rule": {"status": "PASS", "reason": "ok"},
            "intent_agent": {"status": "PASS", "reason": "ok"},
            "intent_aggregator": {"status": "PASS", "reason": "ok"},
            "i18n_agent": {"status": "PASS", "reason": "ok"},
            "case_aggregator": RuntimeError("case aggregation broken"),
        }
    )
    executor = CaseWorkflowExecutor(repository, store, connector, tool_runner=runner)

    with pytest.raises(CaseWorkflowExecutionError) as caught:
        asyncio.run(
            executor.execute(
                run=run,
                case_run=case,
                target=target,
                request_body={},
                workflow_snapshot=_multi_workflow_snapshot(),
            )
        )

    assert caught.value.case_run.status == "ERROR"
    assert caught.value.result["status"] == "ERROR"
    assert set(caught.value.result["check_items"]) == {"intent", "i18n"}
    assert caught.value.result_artifact.retention_class == "FINAL_LONG_TERM"


def test_default_runner_executes_real_script_subprocess_with_mapped_inputs(tmp_path):
    repository, store, connector, target, run, case = _context(tmp_path)
    parser_code = "response = {'answer': inputs['raw']['data']['answer']}"
    evaluator_code = (
        "print('evaluating', flush=True)\n"
        "response = {'status': 'PASS', 'reason': inputs['answer'], 'data': {}}"
    )
    definition = {
        "parsers": [
            {
                "step_id": "parser",
                "tool_id": "parser-tool",
                "inputs": {"raw": {"source": "response", "pointer": ""}},
            }
        ],
        "checks": [
            {
                "check_item": "answer",
                "evaluators": [
                    {
                        "step_id": "evaluator",
                        "tool_id": "evaluator-tool",
                        "inputs": {
                            "answer": {"source": "parser", "pointer": "/answer"}
                        },
                    }
                ],
            }
        ],
    }
    executor = CaseWorkflowExecutor(repository, store, connector)

    result = asyncio.run(
        executor.execute(
            run=run,
            case_run=case,
            target=target,
            request_body={"question": "问题"},
            workflow_snapshot=_snapshot(
                definition,
                [
                    _tool("parser-tool", code=parser_code),
                    _tool("evaluator-tool", code=evaluator_code),
                ],
            ),
        )
    )

    assert result.result["status"] == "PASS"
    assert result.result["check_items"]["answer"]["reason"] == "企业 Agent 回答"
    log_artifacts = [
        artifact
        for artifact in repository.list_artifacts(run.id, case_run_id=case.id)
        if artifact.kind == "tool_log"
    ]
    assert any("evaluating" in store.read_text(item.relative_path) for item in log_artifacts)


def test_failed_case_can_rerun_same_workflow_step_with_new_execution_number(tmp_path):
    repository, store, connector, target, run, case = _context(tmp_path)
    definition = {
        "parsers": [{"step_id": "parser", "tool_id": "parser-tool"}],
        "checks": [
            {
                "check_item": "intent",
                "evaluators": [{"step_id": "eval", "tool_id": "eval-tool"}],
            }
        ],
    }
    snapshot = _snapshot(definition, [_tool("parser-tool"), _tool("eval-tool")])
    failing = _ControlledRunner(
        {"parser": RuntimeError("first failed"), "eval": {"status": "PASS", "reason": ""}}
    )
    with pytest.raises(CaseWorkflowExecutionError):
        asyncio.run(
            CaseWorkflowExecutor(
                repository, store, connector, tool_runner=failing
            ).execute(
                run=run,
                case_run=case,
                target=target,
                request_body={},
                workflow_snapshot=snapshot,
            )
        )
    succeeding = _ControlledRunner(
        {
            "parser": {},
            "eval": {"status": "PASS", "reason": "second passed"},
        }
    )

    result = asyncio.run(
        CaseWorkflowExecutor(
            repository, store, connector, tool_runner=succeeding
        ).execute(
            run=run,
            case_run=repository.get_case_run(case.id),
            target=target,
            request_body={},
            workflow_snapshot=snapshot,
        )
    )

    parser_steps = [
        step for step in repository.list_step_runs(case.id) if step.step_id == "parser"
    ]
    assert [step.execution_number for step in parser_steps] == [1, 2]
    assert [step.status for step in parser_steps] == ["ERROR", "SUCCEEDED"]
    assert [attempt.attempt_number for attempt in repository.list_attempts(case.id)] == [1, 2]
    assert result.case_run.status == "SUCCEEDED"
    assert len(
        [
            artifact
            for artifact in repository.list_artifacts(run.id, case_run_id=case.id)
            if artifact.kind == "request"
        ]
    ) == 1


def test_v3_to_v4_migration_preserves_step_and_artifact_links(tmp_path):
    database_path = tmp_path / "v3.sqlite3"
    with sqlite3.connect(database_path, isolation_level=None) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.execute("BEGIN IMMEDIATE")
        RunRepository._apply_v1(connection)
        RunRepository._apply_v2(connection)
        RunRepository._apply_v3(connection)
        connection.execute(
            "INSERT INTO schema_migrations VALUES (1, 'v1'), (2, 'v2'), (3, 'v3')"
        )
        connection.execute(
            """
            INSERT INTO runs(
                id, testset_filename, sheet_name, status, parameters_json,
                snapshot_json, cancel_requested, created_at, updated_at
            ) VALUES ('run', 'cases.xlsx', 'Sheet1', 'RUNNING', '{}', '{}', 0, 'c', 'u')
            """
        )
        connection.execute(
            """
            INSERT INTO case_runs(
                id, run_id, case_id, row_number, question, status, created_at, updated_at
            ) VALUES ('case', 'run', 'case_1', 2, 'q', 'RUNNING', 'c', 'u')
            """
        )
        connection.execute(
            """
            INSERT INTO step_runs(
                id, case_run_id, stage, sequence, step_id, status, created_at, updated_at
            ) VALUES ('step', 'case', 'PARSER', 0, 'parser', 'SUCCEEDED', 'c', 'u')
            """
        )
        connection.execute(
            """
            INSERT INTO artifacts(
                id, run_id, case_run_id, step_run_id, kind, relative_path,
                size_bytes, sha256, retention_class, created_at
            ) VALUES ('artifact', 'run', 'case', 'step', 'parser_result',
                      'runs/run/result.json', 2, ?, 'SUCCESS_TEMPORARY', 'c')
            """,
            ("a" * 64,),
        )
        connection.commit()

    repository = RunRepository(database_path)
    repository.initialize()

    assert repository.schema_version() == SCHEMA_VERSION == 5
    steps = repository.list_step_runs("case")
    assert len(steps) == 1
    assert steps[0].id == "step"
    assert steps[0].execution_number == 1
    artifacts = repository.list_artifacts("run", case_run_id="case")
    assert len(artifacts) == 1
    assert artifacts[0].step_run_id == "step"
