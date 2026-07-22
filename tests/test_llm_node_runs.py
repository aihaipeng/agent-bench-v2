from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
                "x_api_key": self.headers.get("x-api-key"),
                "anthropic_version": self.headers.get("anthropic-version"),
                "body": body,
            }
        )
        if body.get("stream") is True and self.__class__.response_status == 200:
            if self.path.endswith("/messages"):
                payload = (
                    'event: message_start\n'
                    'data: {"type":"message_start","message":{"usage":{"input_tokens":11,'
                    '"output_tokens":1}}}\n\n'
                    'event: content_block_delta\n'
                    'data: {"type":"content_block_delta","delta":{"type":"text_delta",'
                    '"text":"stream output"}}\n\n'
                    'event: message_delta\n'
                    'data: {"type":"message_delta","usage":{"output_tokens":6}}\n\n'
                ).encode()
            else:
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
                "id": "start",
                "type": "workflowNode",
                "position": {"x": 0, "y": 0},
                "data": {"nodeType": "START", "label": "开始"},
            },
            {
                "id": "llm-1",
                "type": "workflowNode",
                "position": {"x": 200, "y": 0},
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
        "global_variables": [
            {"id": "variable-1", "name": "question", "value": "退款流程"}
        ],
    }


def _create_provider(
    database_path,
    base_url: str,
    *,
    protocol: str = "OPENAI_COMPATIBLE",
    model_configs: dict | None = None,
):
    ModelProviderRepository(database_path).create(
        ModelProviderRecord(
            id="provider-1",
            name="Local Gateway",
            api_key="secret-never-return",
            base_url=base_url,
            protocol=protocol,
            model_endpoint=f"{base_url}/models",
            models=["model-1"],
            model_configs=model_configs or {},
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
        body["nodes"][1]["data"]["outputVariables"].append(
            {
                "id": "output-2",
                "name": "sent_prompt",
                "type": "STRING",
                "value": "request.messages[0].content",
            }
        )
        body["nodes"][1]["data"]["outputVariables"].append(
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
    assert run["status"] == "SUCCESS"
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
            "x_api_key": None,
            "anthropic_version": None,
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


def test_anthropic_node_uses_native_protocol_model_defaults_and_node_overrides(
    tmp_path, monkeypatch
):
    _GatewayHandler.requests = []
    _GatewayHandler.response_status = 200
    _GatewayHandler.response_body = {
        "id": "message-1",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Anthropic 原生响应"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 13, "output_tokens": 8},
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        database_path = _patch_database(tmp_path, monkeypatch)
        _create_provider(
            database_path,
            base_url,
            protocol="ANTHROPIC",
            model_configs={
                "model-1": {
                    "context_window": 200000,
                    "max_output_tokens": 8192,
                    "default_body": {
                        "max_tokens": 4096,
                        "temperature": 0.2,
                        "metadata": {"source": "model", "priority": "default"},
                    },
                }
            },
        )
        body = _workflow_body(
            base_url,
            parameters={
                "temperature": 0.7,
                "metadata": {"priority": "node"},
            },
        )
        body["nodes"][1]["data"]["systemPrompt"] = "你是企业评测助手"
        body["nodes"][1]["data"]["outputVariables"] = [
            {
                "id": "output-1",
                "name": "llm_output",
                "value": "response.content[0].text",
            },
            {
                "id": "output-2",
                "name": "token_count",
                "type": "INTEGER",
                "value": "response.usage.output_tokens",
            },
        ]
        client = TestClient(app)
        workflow = client.post("/api/workflow-drafts", json=body).json()["workflow"]
        run = client.post(
            f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/runs"
        ).json()["run"]
    finally:
        server.shutdown()
        server.server_close()

    assert run["status"] == "SUCCESS"
    assert run["output"] == "Anthropic 原生响应"
    assert run["usage"] == {"input_tokens": 13, "output_tokens": 8}
    assert run["output_variables"] == {
        "llm_output": "Anthropic 原生响应",
        "token_count": 8,
    }
    assert run["request_body"]["system"] == "你是企业评测助手"
    assert run["request_body"]["messages"] == [
        {"role": "user", "content": "请评估：退款流程"}
    ]
    assert run["request_body"]["max_tokens"] == 4096
    assert run["request_body"]["temperature"] == 0.7
    assert run["request_body"]["metadata"] == {
        "source": "model",
        "priority": "node",
    }
    assert _GatewayHandler.requests == [
        {
            "path": "/v1/messages",
            "authorization": None,
            "x_api_key": "secret-never-return",
            "anthropic_version": "2023-06-01",
            "body": run["request_body"],
        }
    ]


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
            {"id": "start-llm", "source": "start", "target": "llm-1"},
            {"id": "edge-1", "source": "llm-1", "target": "llm-2"},
            {"id": "llm-end", "source": "llm-2", "target": "end"},
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

    assert first["status"] == "SUCCESS"
    assert second["status"] == "SUCCESS"
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
    assert final["status"] == "SUCCESS"
    assert final["output"] == raw
    assert final["response_body"] == raw
    assert final["usage"] == {"total_tokens": 17}
    assert final["request_body"]["stream"] is True
    assert final["request_body"]["stream_options"] == {"include_usage": True}
    assert final["output_variables"] == {}
    assert any("已提取 token usage" in event["message"] for event in final["events"])
    assert any("未执行输出解析" in event["message"] for event in final["events"])


def test_anthropic_stream_uses_native_endpoint_and_keeps_raw_sse(tmp_path, monkeypatch):
    _GatewayHandler.requests = []
    _GatewayHandler.response_status = 200
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        database_path = _patch_database(tmp_path, monkeypatch)
        _create_provider(database_path, base_url, protocol="ANTHROPIC")
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

    events = []
    current_event = None
    for line in response.text.splitlines():
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            events.append((current_event, json.loads(line[6:])))
    raw = "".join(payload["chunk"] for event, payload in events if event == "raw")
    final = [payload for event, payload in events if event == "run"][0]
    assert final["status"] == "SUCCESS"
    assert final["response_body"] == raw
    assert final["output_variables"] == {}
    assert final["usage"] == {"input_tokens": 11, "output_tokens": 6}
    assert _GatewayHandler.requests[0]["path"] == "/v1/messages"
    assert _GatewayHandler.requests[0]["authorization"] is None
    assert _GatewayHandler.requests[0]["x_api_key"] == "secret-never-return"
    assert _GatewayHandler.requests[0]["anthropic_version"] == "2023-06-01"
    assert _GatewayHandler.requests[0]["body"]["stream"] is True
    assert _GatewayHandler.requests[0]["body"]["max_tokens"] == 8192


def test_llm_stream_can_be_interrupted_and_persists_partial_raw_response(
    tmp_path, monkeypatch
):
    database_path = _patch_database(tmp_path, monkeypatch)
    _create_provider(database_path, "http://gateway.invalid/v1")

    class _SlowStream:
        status_code = 200
        headers = {"x-request-id": "slow-request"}
        is_success = True

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def aiter_text(self):
            yield 'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            await asyncio.sleep(30)

    class _SlowClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def stream(self, *_args, **_kwargs):
            return _SlowStream()

    monkeypatch.setattr(routes_workflow_drafts.httpx, "AsyncClient", _SlowClient)
    client = TestClient(app)
    control_client = TestClient(app)
    workflow = client.post(
        "/api/workflow-drafts",
        json=_workflow_body("http://gateway.invalid/v1", parameters={"stream": True}),
    ).json()["workflow"]
    stream_url = f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/runs/stream"
    interrupt_url = f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/interrupt"

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(lambda: client.post(stream_url))
        time.sleep(0.1)
        duplicate = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            duplicate = control_client.post(stream_url)
            if duplicate.status_code == 409:
                break
            time.sleep(0.05)
        assert duplicate is not None and duplicate.status_code == 409
        time.sleep(0.2)
        assert control_client.post(interrupt_url).json() == {"interrupted": True}
        response = pending.result(timeout=10)

    assert response.status_code == 200
    runs = control_client.get(
        f"/api/workflow-drafts/{workflow['id']}/nodes/llm-1/runs"
    ).json()["runs"]
    assert runs[0]["status"] == "INTERRUPTED"
    assert "partial" in runs[0]["response_body"]
    assert runs[0]["error"]["type"] == "INTERRUPTED"
