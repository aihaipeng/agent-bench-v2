from __future__ import annotations

import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from web import routes_workflow_drafts
from web.app import app


def _patch_database(tmp_path, monkeypatch):
    database_path = tmp_path / "run_storage" / "agent_bench.sqlite3"
    monkeypatch.setattr(routes_workflow_drafts, "DATABASE_PATH", database_path)
    monkeypatch.setattr(routes_workflow_drafts, "_repository_instance", None)
    monkeypatch.setattr(routes_workflow_drafts, "_repository_path", None)
    return database_path


def _node_body(node_type: str, data: dict) -> dict:
    node_id = f"{node_type.lower()}-1"
    return {
        "name": f"{node_type} 真实执行",
        "description": "",
        "nodes": [
            {
                "id": "start",
                "type": "workflowNode",
                "position": {"x": 0, "y": 0},
                "data": {"nodeType": "START", "label": "开始"},
            },
            {
                "id": node_id,
                "type": "workflowNode",
                "position": {"x": 200, "y": 0},
                "data": {"nodeType": node_type, **data},
            },
            {
                "id": "end",
                "type": "workflowNode",
                "position": {"x": 400, "y": 0},
                "data": {"nodeType": "END", "label": "完成"},
            },
        ],
        "edges": [
            {"id": "start-node", "source": "start", "target": node_id},
            {"id": "node-end", "source": node_id, "target": "end"},
        ],
        "global_variables": [{"id": "question", "name": "question", "value": "退款"}],
    }


def _run(client: TestClient, workflow: dict, node_type: str) -> dict:
    response = client.post(
        f"/api/workflow-drafts/{workflow['id']}/nodes/{node_type.lower()}-1/runs"
    )
    assert response.status_code == 200
    return response.json()["run"]


def test_script_and_agent_preserve_raw_stdout_stderr_and_extract_response(
    tmp_path, monkeypatch
):
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)
    code = (
        "import sys\n"
        "print('raw stdout', flush=True)\n"
        "print('raw stderr', file=sys.stderr, flush=True)\n"
        "response = {'items': [{'id': 3, 'value': inputs['question']}] }\n"
    )
    for node_type in ("SCRIPT", "AGENT"):
        body = _node_body(node_type, {
            "mainPy": code,
            "outputVariables": [{
                "id": "value",
                "name": "selected_value",
                "type": "STRING",
                "value": "response.items[id==3].value",
            }],
        })
        workflow = client.post("/api/workflow-drafts", json=body).json()["workflow"]
        run = _run(client, workflow, node_type)

        assert run["status"] == "SUCCESS"
        assert run["stdout"] == "raw stdout\n"
        assert run["stderr"] == "raw stderr\n"
        assert json.loads(run["response_body"])["items"][0]["id"] == 3
        assert run["output_variables"] == {"selected_value": "退款"}
        assert run["request_body"]["inputs"] == {"question": "退款"}


def test_script_failure_preserves_output_and_traceback(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)
    workflow = client.post("/api/workflow-drafts", json=_node_body(
        "SCRIPT", {"mainPy": "print('before failure', flush=True)\nraise ValueError('bad rule')"}
    )).json()["workflow"]

    run = _run(client, workflow, "SCRIPT")

    assert run["status"] == "FAILED"
    assert run["stdout"] == "before failure\n"
    assert "Traceback" in run["stderr"]
    assert "bad rule" in run["error"]["message"]
    assert "bad rule" in run["error"]["traceback"]


def test_output_extraction_failure_preserves_original_response(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)
    workflow = client.post("/api/workflow-drafts", json=_node_body(
        "SCRIPT", {
            "mainPy": "response = {'actual': {'id': 3}}",
            "outputVariables": [{
                "id": "missing",
                "name": "missing_value",
                "type": "AUTO",
                "value": "response.expected.id",
            }],
        }
    )).json()["workflow"]

    run = _run(client, workflow, "SCRIPT")

    assert run["status"] == "FAILED"
    assert json.loads(run["response_body"]) == {"actual": {"id": 3}}
    assert "response.expected.id" in run["error"]["message"]
    assert run["output_variables"] == {}


class _HttpHandler(BaseHTTPRequestHandler):
    status = 200

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length).decode()
        payload = json.dumps({"id": 3, "body": body}).encode()
        self.send_response(self.status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


def test_http_preserves_raw_response_and_extracts_body(tmp_path, monkeypatch):
    _HttpHandler.status = 200
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _patch_database(tmp_path, monkeypatch)
        client = TestClient(app)
        workflow = client.post("/api/workflow-drafts", json=_node_body(
            "HTTP", {
                "httpConfig": {
                    "method": "POST",
                    "url": f"http://127.0.0.1:{server.server_port}/check",
                    "headers": [{"id": "h", "key": "x-test", "value": "yes"}],
                    "params": [],
                    "bodyType": "raw",
                    "bodyText": "{\"question\": \"${question}\"}",
                    "bodyFields": [],
                },
                "outputVariables": [{
                    "id": "selected",
                    "name": "selected_id",
                    "type": "INTEGER",
                    "value": "response.body.id",
                }],
            }
        )).json()["workflow"]
        run = _run(client, workflow, "HTTP")
    finally:
        server.shutdown()
        server.server_close()

    assert run["status"] == "SUCCESS"
    assert run["stdout"] == ""
    assert run["stderr"] == ""
    assert json.loads(run["response_body"])["body"]["body"] == '{"question": "退款"}'
    assert run["output_variables"] == {"selected_id": 3}


def test_http_error_preserves_original_response_and_error(tmp_path, monkeypatch):
    _HttpHandler.status = 500
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _patch_database(tmp_path, monkeypatch)
        client = TestClient(app)
        workflow = client.post("/api/workflow-drafts", json=_node_body(
            "HTTP", {
                "httpConfig": {
                    "method": "POST",
                    "url": f"http://127.0.0.1:{server.server_port}/failure",
                    "headers": [],
                    "params": [],
                    "bodyType": "none",
                    "bodyText": "",
                    "bodyFields": [],
                }
            }
        )).json()["workflow"]
        run = _run(client, workflow, "HTTP")
    finally:
        server.shutdown()
        server.server_close()

    assert run["status"] == "FAILED"
    assert json.loads(run["response_body"])["status_code"] == 500
    assert run["http_status"] == 500
    assert "HTTP 500" in run["error"]["message"]


def test_http_configuration_failure_is_persisted(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)
    workflow = client.post("/api/workflow-drafts", json=_node_body(
        "HTTP", {
            "httpConfig": {
                "method": "POST",
                "url": "",
                "headers": [],
                "params": [],
                "bodyType": "none",
                "bodyText": "",
                "bodyFields": [],
            }
        }
    )).json()["workflow"]

    run = _run(client, workflow, "HTTP")

    assert run["status"] == "FAILED"
    assert run["request_body"] == {}
    assert run["response_body"] == ""
    assert "URL 不能为空" in run["error"]["message"]
    listed = client.get(
        f"/api/workflow-drafts/{workflow['id']}/nodes/http-1/runs"
    ).json()["runs"]
    assert listed == [run]


def test_script_node_can_be_interrupted_and_rejects_duplicate_runs(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    workflow_client = TestClient(app)
    control_client = TestClient(app)
    workflow = workflow_client.post("/api/workflow-drafts", json=_node_body(
        "SCRIPT",
        {
            "mainPy": (
                "import time\n"
                "print('before interrupt', flush=True)\n"
                "time.sleep(30)\n"
                "response = {'finished': True}\n"
            )
        },
    )).json()["workflow"]
    run_url = f"/api/workflow-drafts/{workflow['id']}/nodes/script-1/runs"
    interrupt_url = f"/api/workflow-drafts/{workflow['id']}/nodes/script-1/interrupt"

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(lambda: workflow_client.post(run_url))
        time.sleep(0.1)
        duplicate = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            duplicate = control_client.post(run_url)
            if duplicate.status_code == 409:
                break
            time.sleep(0.05)
        assert duplicate is not None
        assert duplicate.status_code == 409

        time.sleep(0.5)
        interrupted = control_client.post(interrupt_url)
        assert interrupted.status_code == 200
        assert interrupted.json() == {"interrupted": True}
        response = pending.result(timeout=10)

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["status"] == "INTERRUPTED"
    assert run["stdout"] == "before interrupt\n"
    assert run["error"] == {
        "type": "INTERRUPTED",
        "message": "用户中断节点",
        "traceback": "",
    }
    assert control_client.post(interrupt_url).json() == {"interrupted": False}
    assert control_client.get(
        f"/api/workflow-drafts/{workflow['id']}/nodes/script-1/runs"
    ).json()["runs"][0] == run

    rerun_nodes = json.loads(json.dumps(workflow["nodes"]))
    script_node = next(node for node in rerun_nodes if node["id"] == "script-1")
    script_node["data"]["mainPy"] = "response = {'rerun': True}\n"
    rerun_body = {
        "name": workflow["name"],
        "description": workflow["description"],
        "nodes": rerun_nodes,
        "edges": workflow["edges"],
        "global_variables": workflow["global_variables"],
    }
    assert control_client.put(
        f"/api/workflow-drafts/{workflow['id']}", json=rerun_body
    ).status_code == 200
    rerun = control_client.post(run_url).json()["run"]
    assert rerun["status"] == "SUCCESS"
    assert rerun["output"] == {"rerun": True}
