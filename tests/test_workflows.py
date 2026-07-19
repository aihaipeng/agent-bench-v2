import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from execution import (
    CheckDefinition,
    InputReference,
    RunRepository,
    RunRepositoryError,
    WorkflowDefinition,
    WorkflowDraft,
    WorkflowRecord,
    WorkflowService,
    WorkflowStepDefinition,
    WorkflowValidationError,
    build_workflow_snapshot,
    decode_json_pointer,
    resolve_json_pointer,
    segments_to_json_pointer,
    validate_workflow_definition,
)
from execution.repository import SCHEMA_VERSION
from web import files, routes_tools, routes_workflows
from web.app import app
from web.tool_registry import SCHEMA_VERSION as TOOL_SCHEMA_VERSION
from web.tool_registry import ToolRegistry


_MISSING = object()


def _tool(tool_id, tool_type="script", *, output_example=_MISSING, code=None):
    record = {
        "schema_version": TOOL_SCHEMA_VERSION,
        "id": tool_id,
        "type": tool_type,
        "name": f"工具 {tool_id}",
        "description": "",
        "code": code if code is not None else f"response = {{'tool': '{tool_id}'}}",
        "parameters": (
            {
                "model": "model-1",
                "model_provider": "provider-1",
                "api_key": "secret",
                "base_url": "https://model.example.test",
                "system_prompt": "system",
                "human_message": "human",
            }
            if tool_type == "agent"
            else {}
        ),
        "created_at": "2026-07-19T10:00:00",
        "updated_at": "2026-07-19T10:00:00",
    }
    if output_example is not _MISSING:
        record["output_example"] = output_example
        record["output_example_configured"] = True
    return record


class _Tools:
    def __init__(self, records):
        self.records = {record["id"]: record for record in records}

    def get_tool(self, tool_id):
        record = self.records.get(tool_id)
        return json.loads(json.dumps(record, ensure_ascii=False)) if record else None


def _single_definition(**overrides) -> WorkflowDefinition:
    data = {
        "parsers": [
            {
                "step_id": "response_parser",
                "tool_id": "parser-tool",
                "inputs": {
                    "raw": {"source": "response", "pointer": "/data"},
                },
            }
        ],
        "checks": [
            {
                "check_item": "intent",
                "evaluators": [
                    {
                        "step_id": "intent_agent",
                        "tool_id": "agent-evaluator",
                        "inputs": {
                            "tool_name": {
                                "source": "response_parser",
                                "pointer": "/tool_calls/0/name",
                            }
                        },
                        "parameters": {"human_message": "判断意图"},
                    }
                ],
            }
        ],
    }
    data.update(overrides)
    return WorkflowDefinition.model_validate(data)


def _multi_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "parsers": [
                {
                    "step_id": "response_parser",
                    "tool_id": "parser-tool",
                    "inputs": {"raw": {"source": "response", "pointer": ""}},
                }
            ],
            "checks": [
                {
                    "check_item": "intent",
                    "evaluators": [
                        {
                            "step_id": "intent_script",
                            "tool_id": "script-evaluator",
                            "inputs": {},
                        },
                        {
                            "step_id": "intent_agent",
                            "tool_id": "agent-evaluator",
                            "inputs": {},
                        },
                    ],
                    "aggregator": {
                        "step_id": "intent_aggregator",
                        "tool_id": "check-aggregator",
                    },
                },
                {
                    "check_item": "i18n",
                    "evaluators": [
                        {
                            "step_id": "i18n_agent",
                            "tool_id": "agent-evaluator",
                            "inputs": {},
                        }
                    ],
                },
            ],
            "case_aggregator": {
                "step_id": "case_aggregator",
                "tool_id": "case-aggregator",
            },
        }
    )


def _tools():
    return _Tools(
        [
            _tool(
                "parser-tool",
                output_example={
                    "tool_calls": [{"name": "example-business-tool"}],
                    "a/b": {"~key": 7},
                },
            ),
            _tool("script-evaluator"),
            _tool("agent-evaluator", "agent"),
            _tool("check-aggregator"),
            _tool("case-aggregator"),
        ]
    )


def test_json_pointer_round_trip_root_escape_arrays_and_missing_fields():
    document = {
        "a/b": {"~key": [{"name": "first"}]},
        "": "empty-key",
    }
    pointer = segments_to_json_pointer(["a/b", "~key", 0, "name"])

    assert pointer == "/a~1b/~0key/0/name"
    assert decode_json_pointer(pointer) == ("a/b", "~key", "0", "name")
    assert resolve_json_pointer(document, pointer) == "first"
    assert resolve_json_pointer(document, "") is document
    assert resolve_json_pointer(document, "/") == "empty-key"
    with pytest.raises(KeyError, match="数组索引无效"):
        resolve_json_pointer(["first", "second"], "/01")
    with pytest.raises(KeyError, match="对象字段不存在"):
        resolve_json_pointer(document, "/missing")


@pytest.mark.parametrize("pointer", ["field", "/bad~", "/bad~2escape"])
def test_json_pointer_rejects_non_rfc6901_syntax(pointer):
    with pytest.raises(ValueError):
        decode_json_pointer(pointer)


def test_single_and_multi_topologies_validate_without_redundant_nodes():
    single_tools = validate_workflow_definition(_single_definition(), _tools())
    multi_tools = validate_workflow_definition(_multi_definition(), _tools())

    assert set(single_tools) == {"parser-tool", "agent-evaluator"}
    assert set(multi_tools) == {
        "parser-tool",
        "script-evaluator",
        "agent-evaluator",
        "check-aggregator",
        "case-aggregator",
    }


@pytest.mark.parametrize(
    "definition, expected_message",
    [
        (
            WorkflowDefinition.model_validate(
                {
                    "checks": [
                        {
                            "check_item": "intent",
                            "evaluators": [
                                {"step_id": "one", "tool_id": "script-evaluator"},
                                {"step_id": "two", "tool_id": "agent-evaluator"},
                            ],
                        }
                    ]
                }
            ),
            "多个 Evaluator 必须配置",
        ),
        (
            WorkflowDefinition.model_validate(
                {
                    "checks": [
                        {
                            "check_item": "intent",
                            "evaluators": [
                                {"step_id": "one", "tool_id": "script-evaluator"}
                            ],
                            "aggregator": {
                                "step_id": "extra",
                                "tool_id": "check-aggregator",
                            },
                        }
                    ]
                }
            ),
            "单 Evaluator 不执行",
        ),
        (
            WorkflowDefinition.model_validate(
                {
                    "checks": [
                        {
                            "check_item": "intent",
                            "evaluators": [
                                {"step_id": "one", "tool_id": "script-evaluator"}
                            ],
                        },
                        {
                            "check_item": "i18n",
                            "evaluators": [
                                {"step_id": "two", "tool_id": "agent-evaluator"}
                            ],
                        },
                    ]
                }
            ),
            "多个 Check Item 必须配置",
        ),
    ],
)
def test_aggregators_are_required_only_for_actual_fan_in(
    definition, expected_message
):
    with pytest.raises(WorkflowValidationError, match=expected_message):
        validate_workflow_definition(definition, _tools())


def test_validation_reports_duplicate_ids_check_items_and_wrong_aggregator_type():
    definition = WorkflowDefinition.model_validate(
        {
            "checks": [
                {
                    "check_item": "intent",
                    "evaluators": [
                        {"step_id": "duplicate", "tool_id": "script-evaluator"},
                        {"step_id": "duplicate", "tool_id": "agent-evaluator"},
                    ],
                    "aggregator": {
                        "step_id": "agg",
                        "tool_id": "agent-evaluator",
                    },
                },
                {
                    "check_item": "intent",
                    "evaluators": [
                        {"step_id": "other", "tool_id": "missing-tool"}
                    ],
                },
            ],
            "case_aggregator": {
                "step_id": "case",
                "tool_id": "case-aggregator",
            },
        }
    )

    with pytest.raises(WorkflowValidationError) as caught:
        validate_workflow_definition(definition, _tools())

    messages = [issue.message for issue in caught.value.issues]
    assert any("step_id" in message and "重复" in message for message in messages)
    assert any("check" in issue.location and "重复" in issue.message for issue in caught.value.issues)
    assert "Aggregator 只允许 Script" in messages
    assert "工具不存在: missing-tool" in messages


def test_parser_sources_must_be_earlier_and_pointers_must_match_output_example():
    definition = WorkflowDefinition.model_validate(
        {
            "parsers": [
                {
                    "step_id": "first",
                    "tool_id": "parser-tool",
                    "inputs": {
                        "future": {"source": "second", "pointer": ""},
                    },
                },
                {
                    "step_id": "second",
                    "tool_id": "parser-tool",
                    "inputs": {
                        "valid": {
                            "source": "first",
                            "pointer": "/tool_calls/0/name",
                        }
                    },
                },
            ],
            "checks": [
                {
                    "check_item": "intent",
                    "evaluators": [
                        {
                            "step_id": "eval",
                            "tool_id": "agent-evaluator",
                            "inputs": {
                                "missing": {
                                    "source": "second",
                                    "pointer": "/tool_calls/9/name",
                                }
                            },
                        }
                    ],
                }
            ],
        }
    )

    with pytest.raises(WorkflowValidationError) as caught:
        validate_workflow_definition(definition, _tools())

    assert any("之前可用的 Parser" in issue.message for issue in caught.value.issues)
    assert any("数组索引越界" in issue.message for issue in caught.value.issues)


def test_parser_requires_declared_example_and_aggregator_inputs_are_system_owned():
    tools = _tools()
    tools.records["parser-tool"].pop("output_example")
    tools.records["parser-tool"]["output_example_configured"] = False
    definition = WorkflowDefinition.model_validate(
        {
            "checks": [
                {
                    "check_item": "intent",
                    "evaluators": [
                        {"step_id": "one", "tool_id": "script-evaluator"},
                        {"step_id": "two", "tool_id": "agent-evaluator"},
                    ],
                    "aggregator": {
                        "step_id": "agg",
                        "tool_id": "check-aggregator",
                        "inputs": {"manual": {"source": "response", "pointer": ""}},
                    },
                }
            ],
        }
    )
    definition.parsers = [
        WorkflowStepDefinition(step_id="parser", tool_id="parser-tool")
    ]

    with pytest.raises(WorkflowValidationError) as caught:
        validate_workflow_definition(definition, tools)

    assert any("output_example" in issue.message for issue in caught.value.issues)
    assert any("系统注入 step_results" in issue.message for issue in caught.value.issues)


def test_workflow_snapshot_freezes_full_tools_and_code_hash(tmp_path):
    registry = ToolRegistry(tmp_path / "tool_registry")
    for record in _tools().records.values():
        registry.create_tool(record)
    workflow = WorkflowRecord(
        id="workflow-1",
        name="回归工作流",
        definition=_single_definition().model_dump(mode="json"),
    )

    snapshot = build_workflow_snapshot(workflow, registry)
    expected_code = registry.get_tool("parser-tool")["code"]
    changed = registry.get_tool("parser-tool")
    changed["name"] = "外部修改"
    changed["code"] = "response = 'changed'"
    registry.update_tool("parser-tool", changed)

    assert snapshot["workflow"]["id"] == workflow.id
    assert snapshot["tools"]["parser-tool"]["code"] == expected_code
    assert snapshot["tools"]["parser-tool"]["name"] == "工具 parser-tool"
    assert snapshot["tools"]["parser-tool"]["code_sha256"] == hashlib.sha256(
        expected_code.encode("utf-8")
    ).hexdigest()
    assert snapshot["tools"]["agent-evaluator"]["parameters"]["api_key"] == "secret"


def test_v2_migration_workflow_repository_binding_restart_and_cascade(tmp_path):
    database_path = tmp_path / "agent_bench.sqlite3"
    with sqlite3.connect(database_path, isolation_level=None) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.execute("BEGIN IMMEDIATE")
        RunRepository._apply_v1(connection)
        RunRepository._apply_v2(connection)
        connection.execute(
            "INSERT INTO schema_migrations VALUES (1, 'v1'), (2, 'v2')"
        )
        connection.commit()

    repository = RunRepository(database_path)
    workflow = repository.create_workflow(
        WorkflowRecord(
            id="workflow-1",
            name="Workflow",
            definition=_single_definition().model_dump(mode="json"),
        )
    )
    binding = repository.bind_testset_workflow("cases.xlsx", workflow.id)

    restarted = RunRepository(database_path)
    assert restarted.schema_version() == SCHEMA_VERSION == 5
    assert restarted.get_workflow(workflow.id) == workflow
    assert restarted.get_testset_workflow_binding("cases.xlsx") == binding
    assert restarted.count_workflow_bindings(workflow.id) == 1

    updated = restarted.update_workflow(
        WorkflowRecord(
            id=workflow.id,
            created_at=workflow.created_at,
            name="Updated",
            description="说明",
            definition=_multi_definition().model_dump(mode="json"),
        )
    )
    assert updated.name == "Updated"
    with pytest.raises(RunRepositoryError, match="FOREIGN KEY"):
        restarted.bind_testset_workflow("other.xlsx", "missing-workflow")
    assert restarted.delete_workflow(workflow.id) is True
    assert restarted.get_testset_workflow_binding("cases.xlsx") is None


def _patch_api_storage(tmp_path, monkeypatch):
    database_path = tmp_path / "run_storage" / "agent_bench.sqlite3"
    tool_root = tmp_path / "tool_registry"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    monkeypatch.setattr(routes_workflows, "DATABASE_PATH", database_path)
    monkeypatch.setattr(routes_workflows, "_repository_instance", None)
    monkeypatch.setattr(routes_workflows, "_repository_path", None)
    monkeypatch.setattr(routes_tools, "TOOL_REGISTRY_ROOT", tool_root)
    monkeypatch.setattr(routes_tools, "_registry_instance", None)
    monkeypatch.setattr(routes_tools, "_registry_root", None)
    monkeypatch.setattr(files, "INPUTS_DIR", inputs)
    registry = routes_tools.get_tool_registry()
    for record in _tools().records.values():
        registry.create_tool(record)
    return database_path, inputs, registry


def _draft_body(definition=None):
    return {
        "name": "企业 Agent 回归",
        "description": "固定拓扑",
        "definition": (definition or _single_definition()).model_dump(mode="json"),
    }


def test_workflow_api_crud_binding_and_live_invalid_state(tmp_path, monkeypatch):
    database_path, inputs, registry = _patch_api_storage(tmp_path, monkeypatch)
    (inputs / "cases.xlsx").touch()
    (inputs / "other.xlsx").touch()
    client = TestClient(app)

    created_response = client.post("/api/workflows", json=_draft_body())
    duplicate_name = client.post("/api/workflows", json=_draft_body())
    assert created_response.status_code == 200
    assert duplicate_name.status_code == 200
    created = created_response.json()["workflow"]
    assert created["valid"] is True
    assert created["binding_count"] == 0
    assert created["id"] != duplicate_name.json()["workflow"]["id"]

    bound = client.put(
        "/api/workflows/bindings/cases.xlsx",
        json={"workflow_id": created["id"]},
    )
    assert bound.status_code == 200
    fetched_binding = client.get("/api/workflows/bindings/cases.xlsx")
    assert fetched_binding.status_code == 200
    assert fetched_binding.json()["workflow"]["binding_count"] == 1
    assert client.get(f"/api/workflows/{created['id']}").status_code == 200

    changed = registry.get_tool("parser-tool")
    changed["output_example"] = {"different": True}
    changed["output_example_configured"] = True
    registry.update_tool("parser-tool", changed)
    invalid = client.get(f"/api/workflows/{created['id']}").json()["workflow"]
    assert invalid["valid"] is False
    assert any(
        "对象字段不存在" in issue["message"]
        for issue in invalid["validation_errors"]
    )
    refused_binding = client.put(
        "/api/workflows/bindings/other.xlsx",
        json={"workflow_id": created["id"]},
    )
    assert refused_binding.status_code == 400

    changed["output_example"] = {"tool_calls": [{"name": "restored"}]}
    registry.update_tool("parser-tool", changed)
    update_body = _draft_body()
    update_body["name"] = "更新后的工作流"
    updated = client.put(f"/api/workflows/{created['id']}", json=update_body)
    assert updated.status_code == 200
    assert updated.json()["workflow"]["name"] == "更新后的工作流"

    deleted = client.delete(f"/api/workflows/{created['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/workflows/bindings/cases.xlsx").status_code == 404
    assert RunRepository(database_path).get_workflow(created["id"]) is None


def test_workflow_api_rejects_invalid_topology_pointer_and_missing_testset(
    tmp_path, monkeypatch
):
    _patch_api_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    invalid = _single_definition()
    invalid.checks[0].evaluators[0].inputs["tool_name"] = InputReference(
        source="response_parser",
        pointer="/tool_calls/99/name",
    )

    response = client.post("/api/workflows", json=_draft_body(invalid))
    structurally_empty = client.post(
        "/api/workflows",
        json={"name": "empty", "definition": {"checks": []}},
    )
    missing_testset = client.put(
        "/api/workflows/bindings/missing.xlsx",
        json={"workflow_id": "missing"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "Workflow 校验失败"
    assert "数组索引越界" in response.text
    assert structurally_empty.status_code == 422
    assert missing_testset.status_code == 404


def test_tool_output_example_api_persists_null_and_removes_field(
    tmp_path, monkeypatch
):
    _, _, registry = _patch_api_storage(tmp_path, monkeypatch)
    client = TestClient(app)

    saved = client.put(
        "/api/tools/parser-tool/output-example",
        json={"output_example": None},
    )
    assert saved.status_code == 200
    assert saved.json()["tool"]["output_example_configured"] is True
    manifest_path = registry.root / "parser-tool" / "manifest.json"
    assert "output_example" in json.loads(manifest_path.read_text(encoding="utf-8"))

    removed = client.delete("/api/tools/parser-tool/output-example")
    assert removed.status_code == 200
    assert removed.json()["tool"]["output_example_configured"] is False
    assert "output_example" not in json.loads(manifest_path.read_text(encoding="utf-8"))
