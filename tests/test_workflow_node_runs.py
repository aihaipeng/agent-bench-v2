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


def test_script_preserves_raw_logs_and_maps_multiple_python_variables(
    tmp_path, monkeypatch
):
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)
    code = (
        "import sys\n"
        "print('raw stdout', flush=True)\n"
        "print('raw stderr', file=sys.stderr, flush=True)\n"
        "msg = inputs['question']\n"
        "score = '95'\n"
    )
    body = _node_body("SCRIPT", {
        "mainPy": code,
        "outputVariables": [
            {
                "id": "value",
                "name": "selected_value",
                "type": "STRING",
                "pythonVariable": "msg",
            },
            {
                "id": "score",
                "name": "quality_score",
                "type": "INTEGER",
                "pythonVariable": "score",
            },
        ],
    })
    workflow = client.post("/api/workflow-drafts", json=body).json()["workflow"]
    run = _run(client, workflow, "SCRIPT")

    assert run["status"] == "SUCCESS"
    assert run["stdout"] == "raw stdout\n"
    assert run["stderr"] == "raw stderr\n"
    assert run["console"] == "raw stdout\nraw stderr\n"
    assert json.loads(run["response_body"]) == {"msg": "退款", "score": "95"}
    assert run["output_variables"] == {
        "selected_value": "退款",
        "quality_score": 95,
    }
    assert run["request_body"]["inputs"] == {"question": "退款"}


def test_agent_preserves_raw_logs_and_extracts_response(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)
    code = (
        "import sys\n"
        "print('raw stdout', flush=True)\n"
        "print('raw stderr', file=sys.stderr, flush=True)\n"
        "response = {'items': [{'id': 3, 'value': inputs['question']}] }\n"
    )
    body = _node_body("AGENT", {
        "mainPy": code,
        "outputVariables": [{
            "id": "value",
            "name": "selected_value",
            "type": "STRING",
            "value": "response.items[id==3].value",
        }],
    })
    workflow = client.post("/api/workflow-drafts", json=body).json()["workflow"]
    run = _run(client, workflow, "AGENT")

    assert run["status"] == "SUCCESS"
    assert run["stdout"] == "raw stdout\n"
    assert run["stderr"] == "raw stderr\n"
    assert json.loads(run["response_body"])["items"][0]["id"] == 3
    assert run["output_variables"] == {"selected_value": "退款"}


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


def test_script_missing_python_variable_outputs_null_and_console_warning(
    tmp_path, monkeypatch
):
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)
    workflow = client.post("/api/workflow-drafts", json=_node_body(
        "SCRIPT", {
            "mainPy": "print('before mapping', flush=True)\nactual = {'id': 3}",
            "outputVariables": [{
                "id": "missing",
                "name": "missing_value",
                "type": "AUTO",
                "pythonVariable": "expected",
            }],
        }
    )).json()["workflow"]

    run = _run(client, workflow, "SCRIPT")

    assert run["status"] == "SUCCESS"
    assert json.loads(run["response_body"]) == {"expected": None}
    assert run["stdout"] == "before mapping\n"
    assert run["stderr"] == (
        "[WARNING] Python 顶层变量不存在，输出 null: expected\n"
    )
    assert run["console"] == (
        "before mapping\n"
        "[WARNING] Python 顶层变量不存在，输出 null: expected\n"
    )
    assert run["error"] is None
    assert run["output_variables"] == {"missing_value": None}


def test_script_type_conversion_failure_preserves_raw_variable_snapshot(
    tmp_path, monkeypatch
):
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)
    workflow = client.post("/api/workflow-drafts", json=_node_body(
        "SCRIPT",
        {
            "mainPy": "score = '3.1'\nprint(score, flush=True)",
            "outputVariables": [{
                "id": "score",
                "name": "quality_score",
                "type": "INTEGER",
                "pythonVariable": "score",
            }],
        },
    )).json()["workflow"]

    run = _run(client, workflow, "SCRIPT")

    assert run["status"] == "FAILED"
    assert run["stdout"] == "3.1\n"
    assert json.loads(run["response_body"]) == {"score": "3.1"}
    assert "输出变量 quality_score 转换失败" in run["error"]["message"]
    assert "INTEGER" in run["error"]["message"]
    assert "[ERROR] 输出变量 quality_score 转换失败" in run["console"]
    assert run["output_variables"] == {}


def test_downstream_script_uses_unique_nearest_duplicate_output(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    def script_node(node_id, code, output_name, python_variable):
        return {
            "id": node_id,
            "type": "workflowNode",
            "position": {"x": 0, "y": 0},
            "data": {
                "nodeType": "SCRIPT",
                "label": node_id,
                "mainPy": code,
                "outputVariables": [{
                    "id": f"output-{node_id}",
                    "name": output_name,
                    "type": "STRING",
                    "pythonVariable": python_variable,
                }],
            },
        }

    start = {
        "id": "start",
        "type": "workflowNode",
        "position": {"x": 0, "y": 0},
        "data": {"nodeType": "START", "label": "开始"},
    }
    end = {
        "id": "end",
        "type": "workflowNode",
        "position": {"x": 0, "y": 0},
        "data": {"nodeType": "END", "label": "结束"},
    }
    far = script_node("far", "msg = 'far'", "message", "msg")
    near = script_node("near", "msg = 'near'", "message", "msg")
    consumer = script_node(
        "consumer",
        "selected = inputs['message']\nprint(selected, flush=True)",
        "selected_message",
        "selected",
    )
    body = {
        "name": "nearest output execution",
        "description": "",
        # Keep far after near so list order cannot accidentally determine precedence.
        "nodes": [start, near, consumer, far, end],
        "edges": [
            {"id": "start-far", "source": "start", "target": "far"},
            {"id": "far-near", "source": "far", "target": "near"},
            {"id": "near-consumer", "source": "near", "target": "consumer"},
            {"id": "consumer-end", "source": "consumer", "target": "end"},
        ],
        "global_variables": [],
    }
    created = client.post("/api/workflow-drafts", json=body)
    assert created.status_code == 200
    workflow = created.json()["workflow"]

    for node_id in ("far", "near"):
        run = client.post(
            f"/api/workflow-drafts/{workflow['id']}/nodes/{node_id}/runs"
        ).json()["run"]
        assert run["status"] == "SUCCESS"
    downstream = client.post(
        f"/api/workflow-drafts/{workflow['id']}/nodes/consumer/runs"
    ).json()["run"]

    assert downstream["status"] == "SUCCESS"
    assert downstream["stdout"] == "near\n"
    assert downstream["request_body"]["inputs"]["message"] == "near"
    assert downstream["output_variables"] == {"selected_message": "near"}


class _HttpHandler(BaseHTTPRequestHandler):
    status = 200

    def do_GET(self):  # noqa: N802
        payload = json.dumps({"id": 3, "body": ""}).encode()
        self.send_response(self.status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

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


def test_script_requests_response_variable_runs_without_platform_serialization(
    tmp_path, monkeypatch
):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _patch_database(tmp_path, monkeypatch)
        client = TestClient(app)
        code = (
            "import requests\n"
            f"url = 'http://127.0.0.1:{server.server_port}/chat/1'\n"
            "response = requests.get(url, timeout=10)\n"
            "response.raise_for_status()\n"
            "data = response.json()\n"
            "print(data, flush=True)\n"
        )
        workflow = client.post("/api/workflow-drafts", json=_node_body(
            "SCRIPT",
            {
                "mainPy": code,
                "outputVariables": [
                    {
                        "id": "data",
                        "name": "api_result",
                        "type": "OBJECT",
                        "pythonVariable": "data",
                    },
                    {
                        "id": "legacy",
                        "name": "msg",
                        "type": "AUTO",
                        "value": "response.stdout",
                    },
                ],
            },
        )).json()["workflow"]
        run = _run(client, workflow, "SCRIPT")
    finally:
        server.shutdown()
        server.server_close()

    assert run["status"] == "SUCCESS", json.dumps(run, ensure_ascii=False, indent=2)
    assert run["output_variables"]["api_result"]["id"] == 3
    assert run["output_variables"]["msg"] is None
    assert "'id': 3" in run["stdout"]
    assert "输出 null: msg" in run["console"]
    assert run["error"] is None


def test_http_preserves_raw_request_response_and_extracts_json_body(
    tmp_path, monkeypatch
):
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
                    "bodyText": (
                        '{\n  "username": "test",\n'
                        '  "password": "123456",\n'
                        '  "email": "test@example.com",\n'
                        '  "question": "${question}"\n}'
                    ),
                    "bodyFields": [],
                },
                "outputVariables": [
                    {
                        "id": "selected",
                        "name": "selected_id",
                        "type": "INTEGER",
                        "value": "response.body.id",
                    },
                    {
                        "id": "username",
                        "name": "sent_username",
                        "type": "STRING",
                        "value": "request.body.username",
                    },
                ],
            }
        )).json()["workflow"]
        run = _run(client, workflow, "HTTP")
    finally:
        server.shutdown()
        server.server_close()

    assert run["status"] == "SUCCESS"
    assert run["stdout"] == ""
    assert run["stderr"] == ""
    expected_body = (
        '{\n  "username": "test",\n'
        '  "password": "123456",\n'
        '  "email": "test@example.com",\n'
        '  "question": "退款"\n}'
    )
    assert run["request_body"]["body"] == expected_body
    assert json.loads(run["response_body"])["body"]["body"] == expected_body
    assert run["output_variables"] == {
        "selected_id": 3,
        "sent_username": "test",
    }


def test_isolated_http_node_variables_include_own_latest_output(
    tmp_path, monkeypatch
):
    _HttpHandler.status = 200
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _patch_database(tmp_path, monkeypatch)
        client = TestClient(app)
        body = _node_body("HTTP", {
            "label": "游离 HTTP",
            "httpConfig": {
                "method": "POST",
                "url": f"http://127.0.0.1:{server.server_port}/check",
                "headers": [{"id": "content-type", "key": "Content-Type", "value": "application/json"}],
                "params": [],
                "bodyType": "raw",
                "bodyText": '{"username":"test"}',
                "bodyFields": [],
            },
            "outputVariables": [{
                "id": "username",
                "name": "username",
                "type": "STRING",
                "value": "request.body.username",
            }],
        })
        body["edges"] = []
        workflow = client.post(
            "/api/workflow-drafts?for_node_run=true", json=body
        ).json()["workflow"]
        run = _run(client, workflow, "HTTP")
        response = client.get(
            f"/api/workflow-drafts/{workflow['id']}/nodes/http-1/variables"
        )
    finally:
        server.shutdown()
        server.server_close()

    assert run["status"] == "SUCCESS"
    assert run["output_variables"] == {"username": "test"}
    assert response.status_code == 200
    groups = response.json()["groups"]
    assert [group["id"] for group in groups] == ["global", "http-1"]
    assert groups[1] == {
        "id": "http-1",
        "label": "游离 HTTP",
        "variables": [{
            "name": "username",
            "value": "test",
            "path": "request.body.username",
            "available": True,
        }],
    }


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
    script_node["data"]["mainPy"] = "rerun = True\n"
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
    assert rerun["output"] == {}
