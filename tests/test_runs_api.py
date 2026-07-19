import json
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from execution import (
    ArtifactStore,
    CaseWorkflowExecutor,
    ExecutionStatus,
    FastAPIConnector,
    RunRepository,
    RunScheduler,
    TargetRecord,
    WorkflowRecord,
)
from web import files, routes_runs, routes_tools
from web.app import app
from web.run_events import RunEventBroker
from web.tool_registry import SCHEMA_VERSION as TOOL_SCHEMA_VERSION


def _save_workbook(path):
    workbook = Workbook()
    first = workbook.active
    first.title = "首个 Sheet"
    first.append(["case_id", "question"])
    first.append(["case_001", "第一个问题"])
    first.append(["case_002", "第二个问题"])
    ignored = workbook.create_sheet("忽略 Sheet")
    ignored.append(["case_id", "question"])
    ignored.append(["ignored", "不应执行"])
    workbook.save(path)


def _script_evaluator():
    return {
        "schema_version": TOOL_SCHEMA_VERSION,
        "id": "status-evaluator",
        "type": "script",
        "name": "状态检查",
        "description": "",
        "parameters": {},
        "code": "print('evaluated')\nresponse = {'status': 'PASS', 'reason': 'ok'}",
        "created_at": "2026-07-19T00:00:00",
        "updated_at": "2026-07-19T00:00:00",
    }


def _patch_runtime(tmp_path, monkeypatch):
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    workbook_path = inputs_dir / "cases.xlsx"
    _save_workbook(workbook_path)
    database_path = tmp_path / "run_storage" / "agent_bench.sqlite3"
    artifact_root = tmp_path.parent / "run-api-artifacts"
    tool_root = tmp_path / "tool_registry"

    monkeypatch.setattr(files, "INPUTS_DIR", inputs_dir)
    monkeypatch.setattr(routes_runs, "DATABASE_PATH", database_path)
    monkeypatch.setattr(routes_runs, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(routes_runs, "_services_instance", None)
    monkeypatch.setattr(routes_runs, "_services_key", None)
    monkeypatch.setattr(routes_tools, "TOOL_REGISTRY_ROOT", tool_root)
    monkeypatch.setattr(routes_tools, "_registry_instance", None)
    monkeypatch.setattr(routes_tools, "_registry_root", None)

    registry = routes_tools.get_tool_registry()
    registry.create_tool(_script_evaluator())
    repository = RunRepository(database_path)
    target = repository.create_target(
        TargetRecord(
            id="target-1",
            name="内网 FastAPI",
            base_url="http://agent.test",
            path="/api/agent/invoke",
            headers={"X-Environment": "test"},
            target_total_concurrency=2,
        )
    )
    workflow = repository.create_workflow(
        WorkflowRecord(
            id="workflow-1",
            name="单项检查",
            definition={
                "parsers": [],
                "checks": [
                    {
                        "check_item": "status",
                        "evaluators": [
                            {
                                "step_id": "status-evaluator-step",
                                "tool_id": "status-evaluator",
                                "inputs": {},
                                "parameters": {},
                            }
                        ],
                        "aggregator": None,
                    }
                ],
                "case_aggregator": None,
            },
        )
    )
    repository.bind_testset_workflow(workbook_path.name, workflow.id)
    return repository, target, workbook_path, artifact_root


def _inject_mock_fastapi(repository, artifact_root, monkeypatch):
    target_app = FastAPI()
    received = []

    @target_app.post("/api/agent/invoke")
    async def invoke(body: dict):
        received.append(body)
        return {"code": 200, "data": {"answer": body.get("question")}}

    store = ArtifactStore(artifact_root)
    connector = FastAPIConnector(
        repository,
        store,
        transport=httpx.ASGITransport(app=target_app),
    )
    executor = CaseWorkflowExecutor(repository, store, connector)
    services = routes_runs.RunServices(
        repository=repository,
        artifact_store=store,
        scheduler=RunScheduler(repository, executor),
        event_broker=RunEventBroker(),
    )
    monkeypatch.setattr(routes_runs, "_services_instance", services)
    monkeypatch.setattr(
        routes_runs,
        "_services_key",
        routes_runs._current_services_key(),
    )
    return services, received


def _parse_sse(text):
    events = []
    for block in text.split("\n\n"):
        event_type = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_type = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        if event_type and data is not None:
            events.append({"type": event_type, "data": data})
    return events


def _wait_for_terminal(client, run_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        detail = client.get(f"/api/runs/{run_id}").json()
        if detail["run"]["status"] in {"SUCCEEDED", "ERROR", "CANCELLED"}:
            return detail
        time.sleep(0.02)
    raise AssertionError(f"Run 未在 {timeout} 秒内结束: {run_id}")


def test_request_template_crud_supports_arbitrary_json_root(tmp_path, monkeypatch):
    _patch_runtime(tmp_path, monkeypatch)
    client = TestClient(app)

    missing = client.get("/api/runs/testsets/cases.xlsx/request-template")
    saved = client.put(
        "/api/runs/testsets/cases.xlsx/request-template",
        json={"request_template": "${question}"},
    )
    restored = client.get("/api/runs/testsets/cases.xlsx/request-template")
    created = client.post(
        "/api/runs",
        json={"testset_filename": "cases.xlsx", "target_id": "target-1"},
    )
    invalid = client.put(
        "/api/runs/testsets/cases.xlsx/request-template",
        content='{"request_template":NaN}',
        headers={"Content-Type": "application/json"},
    )
    after_invalid = client.get(
        "/api/runs/testsets/cases.xlsx/request-template"
    )
    deleted = client.delete(
        "/api/runs/testsets/cases.xlsx/request-template"
    )

    assert missing.status_code == 404
    assert saved.status_code == 200
    assert saved.json()["config"]["request_template"] == "${question}"
    assert restored.json()["config"] == saved.json()["config"]
    assert created.status_code == 201
    assert created.json()["run"]["snapshot"]["request_template"] == "${question}"
    assert invalid.status_code == 400
    assert after_invalid.json()["config"] == saved.json()["config"]
    assert deleted.json()["config"] == saved.json()["config"]
    assert client.get(
        "/api/runs/testsets/cases.xlsx/request-template"
    ).status_code == 404
    assert client.put(
        "/api/runs/testsets/../outside.xlsx/request-template",
        json={"request_template": {}},
    ).status_code in {404, 422}


def test_create_run_freezes_current_config_and_remains_queued(
    tmp_path,
    monkeypatch,
):
    repository, _, workbook_path, _ = _patch_runtime(tmp_path, monkeypatch)
    client = TestClient(app)
    template = {
        "question": "${question}",
        "username": "tester",
        "nested": [1, True, None],
    }
    client.put(
        "/api/runs/testsets/cases.xlsx/request-template",
        json={"request_template": template},
    )

    created = client.post(
        "/api/runs",
        json={
            "testset_filename": "cases.xlsx",
            "target_id": "target-1",
            "parameters": {
                "timeout_seconds": 600,
                "case_concurrency": 2,
                "connection_retry_count": 1,
                "retry_interval_seconds": 0.1,
            },
        },
    )
    payload = created.json()
    run_id = payload["run"]["id"]

    assert created.status_code == 201
    assert payload["run"]["status"] == "QUEUED"
    assert payload["active"] is False
    assert len(payload["cases"]) == 2
    assert repository.list_attempts(payload["cases"][0]["id"]) == []
    assert payload["run"]["snapshot"]["request_template"] == template
    assert payload["run"]["snapshot"]["excel"]["sheet_name"] == "首个 Sheet"
    assert payload["run"]["snapshot"]["excel"]["ignored_sheet_names"] == [
        "忽略 Sheet"
    ]
    assert payload["run"]["snapshot"]["target"]["id"] == "target-1"
    assert payload["run"]["snapshot"]["workflow"]["tools"][
        "status-evaluator"
    ]["code"].startswith("print")

    client.put(
        "/api/runs/testsets/cases.xlsx/request-template",
        json={"request_template": {"changed": "${question}"}},
    )
    _save_workbook(workbook_path)
    restored = client.get(f"/api/runs/{run_id}").json()
    assert restored["run"]["snapshot"]["request_template"] == template
    assert restored["run"]["status"] == "QUEUED"


def test_manual_start_live_sse_trace_download_resume_and_restart_readback(
    tmp_path,
    monkeypatch,
):
    repository, _, _, artifact_root = _patch_runtime(tmp_path, monkeypatch)
    services, received = _inject_mock_fastapi(
        repository,
        artifact_root,
        monkeypatch,
    )

    with TestClient(app) as client:
        configured = client.put(
            "/api/runs/testsets/cases.xlsx/request-template",
            json={
                "request_template": {
                    "question": "${question}",
                    "username": "tester",
                }
            },
        )
        created = client.post(
            "/api/runs",
            json={
                "testset_filename": "cases.xlsx",
                "target_id": "target-1",
                "parameters": {"case_concurrency": 1},
            },
        )
        assert configured.status_code == 200
        assert created.status_code == 201
        run_id = created.json()["run"]["id"]
        assert created.json()["run"]["status"] == "QUEUED"

        with ThreadPoolExecutor(max_workers=1) as executor:
            stream_future = executor.submit(client.get, f"/api/runs/{run_id}/events")
            deadline = time.monotonic() + 5
            while (
                not services.event_broker._subscribers
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert services.event_broker._subscribers
            started = client.post(f"/api/runs/{run_id}/start")
            stream_response = stream_future.result(timeout=15)

        detail = _wait_for_terminal(client, run_id)
        events = _parse_sse(stream_response.text)
        assert started.status_code == 202
        assert detail["run"]["status"] == "SUCCEEDED"
        assert detail["run"]["business_status"] == "PASS"
        assert [body["question"] for body in received] == [
            "第一个问题",
            "第二个问题",
        ]
        assert all("case_id" not in body for body in received)
        assert events[-1]["type"] == "run_terminal"
        assert events[-1]["data"]["run"]["status"] == "SUCCEEDED"

        case_id = detail["cases"][0]["id"]
        case_detail = client.get(
            f"/api/runs/{run_id}/cases/{case_id}"
        ).json()
        assert len(case_detail["attempts"]) == 1
        assert case_detail["attempts"][0]["status"] == "SUCCEEDED"
        assert len(case_detail["steps"]) == 1
        assert case_detail["steps"][0]["stage"] == "EVALUATOR"
        assert {item["kind"] for item in case_detail["artifacts"]} >= {
            "request",
            "response",
            "evaluator_result",
            "case_result",
        }

        artifacts = client.get(f"/api/runs/{run_id}/artifacts").json()[
            "artifacts"
        ]
        result_artifact = next(
            item for item in artifacts if item["kind"] == "case_result"
        )
        downloaded = client.get(
            f"/api/runs/{run_id}/artifacts/{result_artifact['id']}/download"
        )
        assert downloaded.status_code == 200
        assert json.loads(downloaded.content)["status"] == "PASS"

        no_replay = client.get(f"/api/runs/{run_id}/events")
        assert no_replay.status_code == 200
        assert _parse_sse(no_replay.text) == []

        retry_case = detail["cases"][0]
        repository.update_case_run_status(
            retry_case["id"],
            ExecutionStatus.ERROR,
            error="手工恢复测试",
        )
        repository.update_run_status(
            run_id,
            ExecutionStatus.ERROR,
            error="手工恢复测试",
        )
        resumed = client.post(
            f"/api/runs/{run_id}/resume",
            json={"case_run_ids": [retry_case["id"]]},
        )
        resumed_detail = _wait_for_terminal(client, run_id)
        retried_case = client.get(
            f"/api/runs/{run_id}/cases/{retry_case['id']}"
        ).json()
        untouched_case = client.get(
            f"/api/runs/{run_id}/cases/{detail['cases'][1]['id']}"
        ).json()
        assert resumed.status_code == 202
        assert resumed_detail["run"]["status"] == "SUCCEEDED"
        assert len(retried_case["attempts"]) == 2
        assert len(retried_case["steps"]) == 2
        assert len(untouched_case["attempts"]) == 1

        monkeypatch.setattr(routes_runs, "_services_instance", None)
        monkeypatch.setattr(routes_runs, "_services_key", None)
        restarted = client.get(f"/api/runs/{run_id}")
        assert restarted.status_code == 200
        assert restarted.json()["run"]["status"] == "SUCCEEDED"
        assert restarted.json()["active"] is False


def test_cancel_queued_run_and_missing_dependencies_are_reported(
    tmp_path,
    monkeypatch,
):
    _patch_runtime(tmp_path, monkeypatch)
    client = TestClient(app)

    missing_template = client.post(
        "/api/runs",
        json={"testset_filename": "cases.xlsx", "target_id": "target-1"},
    )
    assert missing_template.status_code == 400
    assert "请求模板" in missing_template.json()["detail"]

    client.put(
        "/api/runs/testsets/cases.xlsx/request-template",
        json={"request_template": {"question": "${question}"}},
    )
    created = client.post(
        "/api/runs",
        json={"testset_filename": "cases.xlsx", "target_id": "target-1"},
    ).json()
    run_id = created["run"]["id"]
    cancelled = client.post(f"/api/runs/{run_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["was_active"] is False
    assert cancelled.json()["run"]["status"] == "CANCELLED"
    assert all(
        case["status"] == "CANCELLED" for case in cancelled.json()["cases"]
    )
    assert client.post(f"/api/runs/{run_id}/start").status_code == 409
    assert client.get("/api/runs/missing").status_code == 404
    assert client.get(
        f"/api/runs/{run_id}/artifacts/missing/download"
    ).status_code == 404
