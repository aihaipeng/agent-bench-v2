import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from execution import (
    NODE_RUN_HISTORY_LIMIT,
    WorkflowDraftRecord,
    WorkflowDraftRepository,
    WorkflowNodeRunRecord,
    WorkflowNodeRunStatus,
)
from web import routes_workflow_drafts
from web.app import app


def _graph_body(name="客服评测流程") -> dict:
    return {
        "name": name,
        "description": "验证客服 Agent 回复",
        "nodes": [
            {
                "id": "llm-1",
                "type": "workflowNode",
                "position": {"x": 10, "y": 20},
                "data": {
                    "nodeType": "LLM",
                    "providerId": "provider-1",
                    "modelName": "model-1",
                    "modelParameters": {},
                },
            },
            {
                "id": "start",
                "type": "workflowNode",
                "position": {"x": 0, "y": 0},
                "data": {"nodeType": "START", "label": "开始"},
            },
            {
                "id": "end",
                "type": "workflowNode",
                "position": {"x": 400, "y": 0},
                "data": {"nodeType": "END", "label": "完成"},
            },
        ],
        "edges": [
            {"id": "start-llm", "source": "start", "target": "llm-1"},
            {"id": "llm-end", "source": "llm-1", "target": "end"},
        ],
        "global_variables": [{"id": "v-1", "name": "question", "value": "退款"}],
    }


def _patch_database(tmp_path, monkeypatch):
    database_path = tmp_path / "run_storage" / "agent_bench.sqlite3"
    monkeypatch.setattr(routes_workflow_drafts, "DATABASE_PATH", database_path)
    monkeypatch.setattr(routes_workflow_drafts, "_repository_instance", None)
    monkeypatch.setattr(routes_workflow_drafts, "_repository_path", None)
    return database_path


def _finished_run(workflow_id: str, sequence: int) -> WorkflowNodeRunRecord:
    return WorkflowNodeRunRecord(
        id=f"run-{sequence:02d}",
        workflow_id=workflow_id,
        node_id="llm-1",
        status=WorkflowNodeRunStatus.SUCCESS,
        started_at=f"2026-07-21T10:00:{sequence:02d}.000+00:00",
        finished_at=f"2026-07-21T10:00:{sequence:02d}.100+00:00",
        duration_ms=100,
        provider_name="DeepSeek",
        model_name="deepseek-v4-pro",
        input_snapshot={"question": f"question-{sequence}"},
        request_body={"model": "deepseek-v4-pro", "messages": []},
        events=[{"level": "INFO", "message": "运行完成"}],
        output={"answer": sequence},
        stdout=f"stdout-{sequence}\n",
        stderr=f"stderr-{sequence}\n",
        console=f"stdout-{sequence}\nstderr-{sequence}\n",
        usage={"total_tokens": sequence},
        http_status=200,
        request_id=f"request-{sequence}",
    )


def test_workflow_draft_repository_restart_retention_and_cascade(tmp_path):
    database_path = tmp_path / "agent_bench.sqlite3"
    repository = WorkflowDraftRepository(database_path)
    workflow = repository.create_draft(
        WorkflowDraftRecord(id="workflow-1", **_graph_body())
    )

    for sequence in range(11):
        running = WorkflowNodeRunRecord(
            id=f"run-{sequence:02d}",
            workflow_id=workflow.id,
            node_id="llm-1",
            started_at=f"2026-07-21T10:00:{sequence:02d}.000+00:00",
        )
        repository.create_run(running)
        repository.finish_run(_finished_run(workflow.id, sequence))

    restarted = WorkflowDraftRepository(database_path)
    restored = restarted.get_draft(workflow.id)
    assert restored is not None
    assert restored.nodes[0]["data"]["nodeType"] == "LLM"
    assert restored.global_variables[0]["value"] == "退款"
    runs = restarted.list_node_runs(workflow.id, "llm-1")
    assert len(runs) == NODE_RUN_HISTORY_LIMIT
    assert [run.id for run in runs] == [f"run-{value:02d}" for value in range(10, 0, -1)]
    assert runs[0].output == {"answer": 10}
    assert runs[0].stdout == "stdout-10\n"
    assert runs[0].stderr == "stderr-10\n"
    assert runs[0].console == "stdout-10\nstderr-10\n"

    assert restarted.delete_draft(workflow.id) is True
    assert restarted.list_node_runs(workflow.id, "llm-1") == []


def test_workflow_node_run_migrates_legacy_passed_status_to_success(tmp_path):
    database_path = tmp_path / "agent_bench.sqlite3"
    repository = WorkflowDraftRepository(database_path)
    workflow = repository.create_draft(
        WorkflowDraftRecord(id="workflow-legacy", **_graph_body())
    )
    repository.create_run(
        WorkflowNodeRunRecord(
            id="legacy-run",
            workflow_id=workflow.id,
            node_id="llm-1",
        )
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE workflow_node_runs SET status = 'PASSED' WHERE id = 'legacy-run'"
        )
        connection.commit()

    restarted = WorkflowDraftRepository(database_path)
    runs = restarted.list_node_runs(workflow.id, "llm-1")

    assert runs[0].status == WorkflowNodeRunStatus.SUCCESS


def test_workflow_draft_api_crud_and_persistent_run_listing(tmp_path, monkeypatch):
    database_path = _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    created_response = client.post("/api/workflow-drafts", json=_graph_body())
    assert created_response.status_code == 200
    created = created_response.json()["workflow"]
    assert client.get("/api/workflow-drafts").json()["workflows"] == [created]
    assert client.get(f"/api/workflow-drafts/{created['id']}").json()["workflow"] == created

    updated_response = client.put(
        f"/api/workflow-drafts/{created['id']}",
        json=_graph_body(name="更新后的流程"),
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()["workflow"]
    assert updated["name"] == "更新后的流程"
    assert updated["created_at"] == created["created_at"]

    repository = WorkflowDraftRepository(database_path)
    running = WorkflowNodeRunRecord(
        id="persisted-run",
        workflow_id=created["id"],
        node_id="llm-1",
    )
    repository.create_run(running)
    repository.finish_run(
        WorkflowNodeRunRecord(
            **running.model_dump(
                mode="json", exclude={"status", "finished_at", "error"}
            ),
            status="FAILED",
            finished_at="2026-07-21T10:01:00.000+00:00",
            error={"type": "RuntimeError", "message": "upstream failed"},
        )
    )
    runs = client.get(
        f"/api/workflow-drafts/{created['id']}/nodes/llm-1/runs"
    ).json()["runs"]
    assert runs[0]["id"] == "persisted-run"
    assert runs[0]["status"] == "FAILED"

    routes_workflow_drafts._repository_instance = None
    routes_workflow_drafts._repository_path = None
    assert client.get(f"/api/workflow-drafts/{created['id']}").status_code == 200
    assert client.delete(f"/api/workflow-drafts/{created['id']}").status_code == 200
    assert client.get(f"/api/workflow-drafts/{created['id']}").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {**_graph_body(), "name": "   "},
        {**_graph_body(), "extra": True},
        {**_graph_body(), "nodes": [{"id": "node-1", "data": []}]},
        {
            **_graph_body(),
            "edges": [{"id": "edge-1", "source": "llm-1", "target": "missing"}],
        },
    ],
)
def test_workflow_draft_api_rejects_invalid_graph(tmp_path, monkeypatch, body):
    _patch_database(tmp_path, monkeypatch)
    assert TestClient(app).post("/api/workflow-drafts", json=body).status_code == 422


@pytest.mark.parametrize("mode", ["isolated", "cycle"])
def test_workflow_draft_api_rejects_isolated_nodes_and_cycles(
    tmp_path, monkeypatch, mode
):
    _patch_database(tmp_path, monkeypatch)
    body = _graph_body()
    orphan = {
        "id": "script-orphan",
        "type": "workflowNode",
        "position": {"x": 200, "y": 160},
        "data": {"nodeType": "SCRIPT", "label": "游离脚本"},
    }
    if mode == "isolated":
        body["nodes"].append(orphan)
    else:
        body["nodes"].append(orphan)
        body["edges"].extend([
            {"id": "llm-script", "source": "llm-1", "target": "script-orphan"},
            {"id": "script-llm", "source": "script-orphan", "target": "llm-1"},
        ])

    response = TestClient(app).post("/api/workflow-drafts", json=body)

    assert response.status_code == 422
    assert f"Workflow 存在{'游离节点' if mode == 'isolated' else '循环依赖'}" in response.text
    if mode == "isolated":
        assert "游离脚本" in response.text


def test_metadata_update_preserves_invalid_graph_and_rejects_blank_name(
    tmp_path,
    monkeypatch,
):
    _patch_database(tmp_path, monkeypatch)
    body = _graph_body()
    body["edges"] = []
    client = TestClient(app)
    created = client.post(
        "/api/workflow-drafts?for_node_run=true",
        json=body,
    ).json()["workflow"]

    updated = client.patch(
        f"/api/workflow-drafts/{created['id']}/metadata",
        json={"name": "  新名称  ", "description": "  新说明  "},
    )

    assert updated.status_code == 200
    workflow = updated.json()["workflow"]
    assert workflow["name"] == "新名称"
    assert workflow["description"] == "新说明"
    assert workflow["nodes"] == created["nodes"]
    assert workflow["edges"] == []
    assert workflow["global_variables"] == created["global_variables"]
    assert client.patch(
        f"/api/workflow-drafts/{created['id']}/metadata",
        json={"name": "   ", "description": ""},
    ).status_code == 422
    assert client.patch(
        "/api/workflow-drafts/missing/metadata",
        json={"name": "不存在", "description": ""},
    ).status_code == 404


def test_workflow_draft_accepts_single_node_without_system_nodes(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    body = _graph_body()
    body["nodes"] = [body["nodes"][0]]
    body["edges"] = []

    response = TestClient(app).post("/api/workflow-drafts", json=body)

    assert response.status_code == 200


def test_workflow_draft_accepts_parallel_complete_paths(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    body = _graph_body()
    script = {
        "id": "script-1",
        "type": "workflowNode",
        "position": {"x": 200, "y": 160},
        "data": {"nodeType": "SCRIPT", "label": "规则校验"},
    }
    body["nodes"].append(script)
    body["edges"].extend([
        {"id": "start-script", "source": "start", "target": "script-1"},
        {"id": "script-end", "source": "script-1", "target": "end"},
    ])

    response = TestClient(app).post("/api/workflow-drafts", json=body)

    assert response.status_code == 200


def test_explicit_save_rejects_incomplete_graph_but_single_node_run_allows_it(
    tmp_path, monkeypatch
):
    database_path = _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)
    created = client.post("/api/workflow-drafts", json=_graph_body()).json()["workflow"]
    invalid_update = _graph_body(name="invalid update")
    invalid_update["edges"] = []

    update = client.put(
        f"/api/workflow-drafts/{created['id']}", json=invalid_update
    )

    assert update.status_code == 422
    assert client.get(f"/api/workflow-drafts/{created['id']}").json()["workflow"]["name"] == "客服评测流程"

    node_run_snapshot = client.put(
        f"/api/workflow-drafts/{created['id']}?for_node_run=true",
        json=invalid_update,
    )
    assert node_run_snapshot.status_code == 200

    historical = _graph_body(name="historical invalid")
    historical["nodes"] = [historical["nodes"][0]]
    historical["edges"] = []
    WorkflowDraftRepository(database_path).create_draft(
        WorkflowDraftRecord(id="historical-invalid", **historical)
    )
    run = client.post(
        "/api/workflow-drafts/historical-invalid/nodes/llm-1/runs"
    )
    assert run.status_code == 200
    assert run.json()["run"]["status"] == "FAILED"
    assert run.json()["run"]["error"]["message"] == "用户提示词解析后不能为空"


def test_workflow_draft_rejects_visible_variable_name_conflicts(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    body = _graph_body()
    body["global_variables"] = [
        {"id": "global-1", "name": "shared", "value": "global"}
    ]
    body["nodes"][0]["data"]["outputVariables"] = [
        {"id": "output-1", "name": "shared", "value": "response.result"}
    ]

    response = TestClient(app).post("/api/workflow-drafts", json=body)

    assert response.status_code == 422
    assert "变量名冲突: shared" in response.text


def test_workflow_draft_rejects_unknown_output_variable_type(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    body = _graph_body()
    body["nodes"][0]["data"]["outputVariables"] = [
        {
            "id": "output-1",
            "name": "created_at",
            "type": "DATE",
            "value": "response.created_at",
        }
    ]

    response = TestClient(app).post("/api/workflow-drafts", json=body)

    assert response.status_code == 422
    assert "不支持的输出变量类型: DATE" in response.text


def test_parallel_branches_with_equal_distance_outputs_are_rejected(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    base_node = _graph_body()["nodes"][0]
    left = json.loads(json.dumps(base_node))
    right = json.loads(json.dumps(base_node))
    start = json.loads(json.dumps(base_node))
    end = json.loads(json.dumps(base_node))
    left["id"], right["id"], start["id"], end["id"] = "left", "right", "start", "end"
    left["data"]["label"], right["data"]["label"], start["data"]["label"], end["data"]["label"] = (
        "Left",
        "Right",
        "开始",
        "End",
    )
    start["data"]["nodeType"] = "START"
    end["data"]["nodeType"] = "END"
    for node in (left, right):
        node["data"]["outputVariables"] = [
            {"id": f"output-{node['id']}", "name": "same", "value": "response.result"}
        ]
    end["data"]["outputVariables"] = []
    isolated = {
        "name": "isolated",
        "description": "",
        "nodes": [start, left, right, end],
        "edges": [
            {"id": "start-left", "source": "start", "target": "left"},
            {"id": "start-right", "source": "start", "target": "right"},
            {"id": "left-end", "source": "left", "target": "end"},
            {"id": "right-end", "source": "right", "target": "end"},
        ],
        "global_variables": [],
    }
    client = TestClient(app)
    merged = client.post("/api/workflow-drafts", json=isolated)
    assert merged.status_code == 422
    assert "变量名等距冲突: same (Left / Right)" in merged.text


def test_linear_duplicate_output_names_allow_nearest_ancestor_override(
    tmp_path, monkeypatch
):
    _patch_database(tmp_path, monkeypatch)
    base_node = _graph_body()["nodes"][0]
    nodes = []
    for node_id, label, node_type in (
        ("start", "开始", "START"),
        ("far", "Far", "HTTP"),
        ("near", "Near", "HTTP"),
        ("end", "结束", "END"),
    ):
        node = json.loads(json.dumps(base_node))
        node["id"] = node_id
        node["data"]["label"] = label
        node["data"]["nodeType"] = node_type
        node["data"]["outputVariables"] = (
            [{"id": f"output-{node_id}", "name": "same", "value": "response.result"}]
            if node_type == "HTTP"
            else []
        )
        nodes.append(node)
    body = {
        "name": "nearest override",
        "description": "",
        "nodes": nodes,
        "edges": [
            {"id": "start-far", "source": "start", "target": "far"},
            {"id": "far-near", "source": "far", "target": "near"},
            {"id": "near-end", "source": "near", "target": "end"},
        ],
        "global_variables": [],
    }

    response = TestClient(app).post("/api/workflow-drafts", json=body)

    assert response.status_code == 200


def test_legacy_script_mapping_is_optional_and_does_not_block_execution(
    tmp_path, monkeypatch
):
    database_path = _patch_database(tmp_path, monkeypatch)
    body = _graph_body(name="legacy script mapping")
    body["nodes"][0]["data"]["nodeType"] = "SCRIPT"
    body["nodes"][0]["data"]["outputVariables"] = [
        {"id": "legacy", "name": "message", "value": "response.message"}
    ]
    historical = WorkflowDraftRecord.model_construct(
        id="legacy-script",
        created_at="2026-07-22T00:00:00Z",
        updated_at="2026-07-22T00:00:00Z",
        **body,
    )
    WorkflowDraftRepository(database_path).create_draft(historical)
    client = TestClient(app)

    listed = client.get("/api/workflow-drafts")
    loaded = client.get("/api/workflow-drafts/legacy-script")
    saved = client.put("/api/workflow-drafts/legacy-script", json=body)
    executed = client.post(
        "/api/workflow-drafts/legacy-script/nodes/llm-1/runs"
    )

    assert listed.status_code == 200
    assert loaded.status_code == 200
    assert saved.status_code == 200
    assert executed.status_code == 200
    run = executed.json()["run"]
    assert run["status"] == "SUCCESS"
    assert run["output_variables"] == {"message": None}
    assert "输出 null: message" in run["console"]


def test_variable_groups_skip_ancestors_without_output_mappings(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    body = _graph_body()
    client = TestClient(app)
    workflow = client.post("/api/workflow-drafts", json=body).json()["workflow"]

    groups = client.get(
        f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/variables"
    ).json()["groups"]

    assert [group["label"] for group in groups] == ["全局变量", "llm-1"]
