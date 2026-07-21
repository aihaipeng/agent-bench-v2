from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from execution import ModelProviderRecord, ModelProviderRepository
from web import routes_workflow_drafts
from web.app import app


class _GatewayHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    response_status = 200
    response_body: dict = {}

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length))
        self.__class__.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("authorization"),
                "body": body,
            }
        )
        if body.get("stream") is True and self.__class__.response_status == 200:
            payload = (
                'data: {"choices":[{"delta":{"content":"stream "}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"output"},"finish_reason":"stop"}],'
                '"usage":{"total_tokens":17}}\n\n'
                "data: [DONE]\n\n"
            ).encode()
            content_type = "text/event-stream"
        else:
            payload = json.dumps(self.__class__.response_body).encode()
            content_type = "application/json"
        self.send_response(self.__class__.response_status)
        self.send_header("content-type", content_type)
        self.send_header("x-request-id", "gateway-request-1")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


def _patch_database(tmp_path, monkeypatch):
    database_path = tmp_path / "run_storage" / "agent_bench.sqlite3"
    monkeypatch.setattr(routes_workflow_drafts, "DATABASE_PATH", database_path)
    monkeypatch.setattr(routes_workflow_drafts, "_repository_instance", None)
    monkeypatch.setattr(routes_workflow_drafts, "_repository_path", None)
    return database_path


def _workflow_body(base_url: str, *, user_prompt="请评估：${question}", parameters=None):
    return {
        "name": "LLM 节点真实运行",
        "description": "",
        "nodes": [
            {
                "id": "llm-1",
                "type": "workflowNode",
                "position": {"x": 0, "y": 0},
                "data": {
                    "nodeType": "LLM",
                    "providerId": "provider-1",
                    "modelName": "model-1",
                    "systemPrompt": "",
                    "userPrompt": user_prompt,
                    "modelParameters": parameters or {},
                    "outputVariables": [
                        {
                            "id": "output-1",
                            "name": "llm_output",
                            "value": "response.choices[0].message.content",
                        }
                    ],
                },
            }
        ],
        "edges": [],
        "global_variables": [
            {"id": "variable-1", "name": "question", "value": "退款流程"}
        ],
    }


def _create_provider(database_path, base_url: str):
    ModelProviderRepository(database_path).create(
        ModelProviderRecord(
            id="provider-1",
            name="Local Gateway",
            api_key="secret-never-return",
            base_url=base_url,
            protocol="OPENAI_COMPATIBLE",
            model_endpoint=f"{base_url}/models",
            models=["model-1"],
        )
    )


def test_llm_node_real_http_run_persists_output_usage_and_safe_request(
    tmp_path, monkeypatch
):
    _GatewayHandler.requests = []
    _GatewayHandler.response_status = 200
    _GatewayHandler.response_body = {
        "choices": [
            {"message": {"role": "assistant", "content": "需要先核对订单状态"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 21, "completion_tokens": 18, "total_tokens": 39},
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        database_path = _patch_database(tmp_path, monkeypatch)
        _create_provider(database_path, base_url)
        client = TestClient(app)
        body = _workflow_body(base_url)
        body["nodes"][0]["data"]["outputVariables"].append(
            {
                "id": "output-2",
                "name": "sent_prompt",
                "type": "STRING",
                "value": "request.messages[0].content",
            }
        )
        body["nodes"][0]["data"]["outputVariables"].append(
            {
                "id": "output-3",
                "name": "token_count",
                "type": "INTEGER",
                "value": "response.usage.total_tokens",
            }
        )
        workflow = client.post(
            "/api/workflow-drafts", json=body
        ).json()["workflow"]

        response = client.post(
            f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/runs"
        )
    finally:
        server.shutdown()
        server.server_close()

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["status"] == "PASSED"
    assert run["output"] == "需要先核对订单状态"
    assert run["usage"]["total_tokens"] == 39
    assert run["http_status"] == 200
    assert run["request_id"] == "gateway-request-1"
    assert json.loads(run["response_body"]) == _GatewayHandler.response_body
    assert run["output_variables"] == {
        "llm_output": "需要先核对订单状态",
        "sent_prompt": "请评估：退款流程",
        "token_count": 39,
    }
    assert run["input_snapshot"]["resolved_user_prompt"] == "请评估：退款流程"
    assert run["request_body"]["messages"] == [
        {"role": "user", "content": "请评估：退款流程"}
    ]
    assert "max_tokens" not in run["request_body"]
    assert "max_completion_tokens" not in run["request_body"]
    serialized = json.dumps(run, ensure_ascii=False)
    assert "secret-never-return" not in serialized
    assert _GatewayHandler.requests == [
        {
            "path": "/v1/chat/completions",
            "authorization": "Bearer secret-never-return",
            "body": run["request_body"],
        }
    ]
    listed = client.get(
        f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/runs"
    ).json()["runs"]
    assert listed == [run]
    groups = client.get(
        f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/variables"
    ).json()["groups"]
    assert groups[0]["label"] == "全局变量"
    assert groups[0]["variables"][0]["name"] == "question"
    assert groups[1]["label"] == "llm-1"
    assert groups[1]["variables"] == [
        {
            "name": "llm_output",
            "value": "需要先核对订单状态",
            "path": "response.choices[0].message.content",
            "available": True,
        },
        {
            "name": "sent_prompt",
            "value": "请评估：退款流程",
            "path": "request.messages[0].content",
            "available": True,
        },
        {
            "name": "token_count",
            "value": 39,
            "path": "response.usage.total_tokens",
            "available": True,
        },
    ]


def test_llm_node_missing_variable_fails_before_provider_request(tmp_path, monkeypatch):
    _GatewayHandler.requests = []
    database_path = _patch_database(tmp_path, monkeypatch)
    _create_provider(database_path, "http://127.0.0.1:1/v1")
    client = TestClient(app)
    workflow = client.post(
        "/api/workflow-drafts",
        json=_workflow_body("unused", user_prompt="${missing}"),
    ).json()["workflow"]

    run = client.post(
        f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/runs"
    ).json()["run"]

    assert run["status"] == "FAILED"
    assert run["error"]["type"] == "LlmNodeConfigurationError"
    assert "缺少变量: missing" in run["error"]["message"]
    assert run["request_body"] == {}
    assert run["response_body"] == ""
    assert _GatewayHandler.requests == []


def test_llm_node_http_error_is_persisted_without_api_key(tmp_path, monkeypatch):
    _GatewayHandler.requests = []
    _GatewayHandler.response_status = 429
    _GatewayHandler.response_body = {
        "error": {"message": "quota exhausted for secret-never-return"}
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        database_path = _patch_database(tmp_path, monkeypatch)
        _create_provider(database_path, base_url)
        client = TestClient(app)
        workflow = client.post(
            "/api/workflow-drafts", json=_workflow_body(base_url)
        ).json()["workflow"]
        run = client.post(
            f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/runs"
        ).json()["run"]
    finally:
        server.shutdown()
        server.server_close()

    assert run["status"] == "FAILED"
    assert run["error"]["type"] == "RuntimeError"
    assert "HTTP 429" in run["error"]["message"]
    assert "[REDACTED]" in run["error"]["message"]
    assert "secret-never-return" not in json.dumps(run, ensure_ascii=False)
    assert json.loads(run["response_body"])["error"]["message"].startswith(
        "quota exhausted"
    )


def test_downstream_llm_can_reference_ancestor_native_response_value(tmp_path, monkeypatch):
    _GatewayHandler.requests = []
    _GatewayHandler.response_status = 200
    _GatewayHandler.response_body = {
        "choices": [{"message": {"content": "first output"}, "finish_reason": "stop"}]
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        database_path = _patch_database(tmp_path, monkeypatch)
        _create_provider(database_path, base_url)
        body = _workflow_body(base_url)
        body["nodes"].append(
            {
                "id": "llm-2",
                "type": "workflowNode",
                "position": {"x": 200, "y": 0},
                "data": {
                    "nodeType": "LLM",
                    "label": "下游判断",
                    "providerId": "provider-1",
                    "modelName": "model-1",
                    "systemPrompt": "",
                    "userPrompt": "复核上游原始响应：${llm_output}",
                    "modelParameters": {},
                    "outputVariables": [
                        {
                            "id": "output-2",
                            "name": "review_output",
                            "value": "response.choices[0].message.content",
                        }
                    ],
                },
            }
        )
        body["edges"] = [
            {"id": "edge-1", "source": "llm-1", "target": "llm-2"}
        ]
        client = TestClient(app)
        workflow = client.post("/api/workflow-drafts", json=body).json()["workflow"]

        first = client.post(
            f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/runs"
        ).json()["run"]
        second = client.post(
            f"/api/workflow-drafts/{workflow['id']}/nodes/llm-2/runs"
        ).json()["run"]
    finally:
        server.shutdown()
        server.server_close()

    assert first["status"] == "PASSED"
    assert second["status"] == "PASSED"
    assert "first output" in second["input_snapshot"]["resolved_user_prompt"]
    assert second["output_variables"] == {"review_output": "first output"}
    groups = client.get(
        f"/api/workflow-drafts/{workflow['id']}/nodes/llm-2/variables"
    ).json()["groups"]
    assert [group["label"] for group in groups] == [
        "全局变量",
        "llm-1",
        "下游判断",
    ]
    assert groups[1]["variables"][0]["value"] == "first output"


def test_llm_node_stream_endpoint_emits_raw_chunks_and_persists_final_run(
    tmp_path, monkeypatch
):
    _GatewayHandler.requests = []
    _GatewayHandler.response_status = 200
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        database_path = _patch_database(tmp_path, monkeypatch)
        _create_provider(database_path, base_url)
        client = TestClient(app)
        workflow = client.post(
            "/api/workflow-drafts",
            json=_workflow_body(base_url, parameters={"stream": True}),
        ).json()["workflow"]

        response = client.post(
            f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/runs/stream"
        )
    finally:
        server.shutdown()
        server.server_close()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = []
    current_event = None
    for line in response.text.splitlines():
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            events.append((current_event, json.loads(line[6:])))
    raw = "".join(payload["chunk"] for event, payload in events if event == "raw")
    final = [payload for event, payload in events if event == "run"][0]
    assert "data:" in raw
    assert "stream output" not in raw
    assert final["status"] == "PASSED"
    assert final["output"] == raw
    assert final["response_body"] == raw
    assert final["usage"] is None
    assert final["request_body"]["stream"] is True
    assert final["output_variables"] == {}
    assert any("未执行解析" in event["message"] for event in final["events"])
