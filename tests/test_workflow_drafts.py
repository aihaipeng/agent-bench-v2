import json

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
            }
        ],
        "edges": [],
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
        status=WorkflowNodeRunStatus.PASSED,
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

    assert restarted.delete_draft(workflow.id) is True
    assert restarted.list_node_runs(workflow.id, "llm-1") == []


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


def test_isolated_branches_may_reuse_output_name_until_they_merge(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    base_node = _graph_body()["nodes"][0]
    left = json.loads(json.dumps(base_node))
    right = json.loads(json.dumps(base_node))
    end = json.loads(json.dumps(base_node))
    left["id"], right["id"], end["id"] = "left", "right", "end"
    left["data"]["label"], right["data"]["label"], end["data"]["label"] = (
        "Left",
        "Right",
        "End",
    )
    for node in (left, right):
        node["data"]["outputVariables"] = [
            {"id": f"output-{node['id']}", "name": "same", "value": "response.result"}
        ]
    end["data"]["outputVariables"] = []
    isolated = {
        "name": "isolated",
        "description": "",
        "nodes": [left, right, end],
        "edges": [],
        "global_variables": [],
    }
    client = TestClient(app)
    assert client.post("/api/workflow-drafts", json=isolated).status_code == 200

    isolated["name"] = "merged"
    isolated["edges"] = [
        {"id": "left-end", "source": "left", "target": "end"},
        {"id": "right-end", "source": "right", "target": "end"},
    ]
    merged = client.post("/api/workflow-drafts", json=isolated)
    assert merged.status_code == 422
    assert "变量名冲突: same" in merged.text


def test_variable_groups_skip_ancestors_without_output_mappings(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    body = _graph_body()
    start = {
        "id": "start",
        "type": "workflowNode",
        "position": {"x": 0, "y": 0},
        "data": {"nodeType": "START", "label": "开始", "outputVariables": []},
    }
    body["nodes"].insert(0, start)
    body["edges"] = [
        {"id": "start-llm", "source": "start", "target": "llm-1"}
    ]
    client = TestClient(app)
    workflow = client.post("/api/workflow-drafts", json=body).json()["workflow"]

    groups = client.get(
        f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/variables"
    ).json()["groups"]

    assert [group["label"] for group in groups] == ["全局变量", "llm-1"]
