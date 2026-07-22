"""多节点参数传递 + 执行逻辑 端到端测试。

覆盖：
- D1~D2:  HTTP → SCRIPT / SCRIPT → SCRIPT 变量传递
- D3~D5:  HTTP → LLM / SCRIPT → LLM / LLM → SCRIPT
- D6:     三节点链 A→B→C
- D7:     并行扇入
- D8:     同名变量最近优先
- D9~D10: 上游未执行 / 上游失败
- D11:    全局变量与上游同名 → 创建时直接拒绝 (422)
- D12:    类型转换失败阻塞
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from execution import ModelProviderRecord, ModelProviderRepository
from web import routes_workflow_drafts
from web.app import app


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _patch_database(tmp_path, monkeypatch):
    database_path = tmp_path / "run_storage" / "agent_bench.sqlite3"
    monkeypatch.setattr(routes_workflow_drafts, "DATABASE_PATH", database_path)
    monkeypatch.setattr(routes_workflow_drafts, "_repository_instance", None)
    monkeypatch.setattr(routes_workflow_drafts, "_repository_path", None)
    return database_path


def _start_node(client: TestClient, draft: dict, node_keyword: str) -> dict:
    node = next(n for n in draft["nodes"] if node_keyword in n["id"])
    resp = client.post(f"/api/workflow-drafts/{draft['id']}/nodes/{node['id']}/runs")
    assert resp.status_code == 200, resp.text
    return resp.json()["run"]


def _create_draft(client: TestClient, body: dict) -> dict:
    resp = client.post("/api/workflow-drafts", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["workflow"]


def _create_draft_or_422(client: TestClient, body: dict) -> int:
    """创建草稿，返回 status_code（允许 422 的场景）。"""
    resp = client.post("/api/workflow-drafts", json=body)
    return resp.status_code


def _node_entry(node_id: str, node_type: str, data: dict) -> dict:
    return {
        "id": node_id,
        "type": "workflowNode",
        "position": {"x": 0, "y": 0},
        "data": {"nodeType": node_type, **data},
    }


START = _node_entry("start", "START", {"label": "开始"})
END = _node_entry("end", "END", {"label": "结束"})


def _edge(source: str, target: str) -> dict:
    return {"id": f"{source}-{target}", "source": source, "target": target}


# ---------------------------------------------------------------------------
# HTTP mock server（供 HTTP 节点调用）
# ---------------------------------------------------------------------------

class _EchoHandler(BaseHTTPRequestHandler):
    status = 200
    body_override: bytes | None = None

    def _respond(self, payload: dict) -> None:
        body = json.dumps(
            self.body_override.decode() if self.body_override else payload
        ).encode()
        self.send_response(self.status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._respond({"result": "get", "id": 42, "message": "hello"})

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length).decode()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"_raw": raw}
        self._respond({"result": "post", "id": 99, "echo": parsed})

    def log_message(self, _format, *_args):
        return


@pytest.fixture()
def http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _EchoHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# LLM mock server（供 LLM 节点调用）
# ---------------------------------------------------------------------------

class _GatewayHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    response_status = 200
    response_body: dict = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length))
        self.__class__.requests.append({
            "path": self.path,
            "authorization": self.headers.get("authorization"),
            "body": body,
        })
        payload = json.dumps(self.__class__.response_body).encode()
        self.send_response(self.__class__.response_status)
        self.send_header("content-type", "application/json")
        self.send_header("x-request-id", "gw-1")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


@pytest.fixture()
def gateway_server():
    _GatewayHandler.requests = []
    _GatewayHandler.response_status = 200
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _create_llm_provider(database_path, base_url: str):
    ModelProviderRepository(database_path).create(ModelProviderRecord(
        id="provider-1", name="Mock", api_key="sk-1",
        base_url=base_url, protocol="OPENAI_COMPATIBLE",
        model_endpoint=f"{base_url}/models",
        models=["model-1"], model_configs={},
    ))


# ===================================================================
# D1: HTTP → SCRIPT
# ===================================================================

def test_http_to_script_passes_variable(tmp_path, monkeypatch, http_server):
    """HTTP 输出变量 → SCRIPT inputs[] 正确接收。"""
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    body = {
        "name": "HTTP → SCRIPT",
        "description": "",
        "nodes": [
            START,
            _node_entry("http-src", "HTTP", {
                "label": "HTTP 源",
                "httpConfig": {
                    "method": "GET",
                    "url": f"http://127.0.0.1:{http_server.server_port}/",
                    "headers": [], "params": [], "bodyType": "none",
                    "bodyText": "", "bodyFields": [],
                },
                "outputVariables": [
                    {"id": "v1", "name": "http_id", "type": "INTEGER",
                     "value": "response.body.id"},
                    {"id": "v2", "name": "http_msg", "type": "STRING",
                     "value": "response.body.message"},
                ],
            }),
            _node_entry("script-sink", "SCRIPT", {
                "label": "SCRIPT 下游",
                "mainPy": 'msg = f"id={inputs[\'http_id\']} msg={inputs[\'http_msg\']}"\nprint(msg, flush=True)\n',
                "outputVariables": [
                    {"id": "out", "name": "result", "type": "STRING",
                     "pythonVariable": "msg"},
                ],
            }),
            END,
        ],
        "edges": [_edge("start", "http-src"), _edge("http-src", "script-sink"),
                   _edge("script-sink", "end")],
        "global_variables": [],
    }
    draft = _create_draft(client, body)

    # 执行 HTTP（GET 返回 message="hello"）
    http_run = _start_node(client, draft, "http-src")
    assert http_run["status"] == "SUCCESS"
    assert http_run["output_variables"]["http_id"] == 42
    assert http_run["output_variables"]["http_msg"] == "hello"

    # 执行 SCRIPT
    script_run = _start_node(client, draft, "script-sink")
    assert script_run["status"] == "SUCCESS"
    assert "id=42 msg=hello" in script_run["stdout"]


# ===================================================================
# D2: SCRIPT → SCRIPT
# ===================================================================

def test_script_to_script_passes_variable(tmp_path, monkeypatch):
    """SCRIPT-A 输出 → SCRIPT-B inputs[] 正确接收。"""
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    body = {
        "name": "SCRIPT → SCRIPT",
        "description": "",
        "nodes": [
            START,
            _node_entry("script-a", "SCRIPT", {
                "label": "SCRIPT-A",
                "mainPy": "msg = 'from-a'\nscore = '100'\n",
                "outputVariables": [
                    {"id": "o1", "name": "message", "type": "STRING",
                     "pythonVariable": "msg"},
                    {"id": "o2", "name": "points", "type": "INTEGER",
                     "pythonVariable": "score"},
                ],
            }),
            _node_entry("script-b", "SCRIPT", {
                "label": "SCRIPT-B",
                "mainPy": 'combined = f"{inputs[\'message\']}:{inputs[\'points\']}"\nprint(combined, flush=True)\n',
                "outputVariables": [
                    {"id": "out", "name": "combined", "type": "STRING",
                     "pythonVariable": "combined"},
                ],
            }),
            END,
        ],
        "edges": [_edge("start", "script-a"), _edge("script-a", "script-b"),
                   _edge("script-b", "end")],
        "global_variables": [],
    }
    draft = _create_draft(client, body)

    _start_node(client, draft, "script-a")
    run_b = _start_node(client, draft, "script-b")

    assert run_b["status"] == "SUCCESS"
    assert run_b["stdout"] == "from-a:100\n"
    assert run_b["output_variables"]["combined"] == "from-a:100"


# ===================================================================
# D3: HTTP → LLM
# ===================================================================

def test_http_to_llm_resolves_variable_in_prompt(
    tmp_path, monkeypatch, http_server, gateway_server
):
    """HTTP 输出变量 → LLM prompt ${var} 正确替换。"""
    database_path = _patch_database(tmp_path, monkeypatch)
    _create_llm_provider(database_path, f"http://127.0.0.1:{gateway_server.server_port}/v1")
    _GatewayHandler.response_body = {
        "choices": [{"message": {"role": "assistant", "content": "收到消息: hello"},
                      "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    client = TestClient(app)

    body = {
        "name": "HTTP → LLM",
        "description": "",
        "nodes": [
            START,
            _node_entry("http-src", "HTTP", {
                "label": "HTTP 源",
                "httpConfig": {
                    "method": "GET",
                    "url": f"http://127.0.0.1:{http_server.server_port}/",
                    "headers": [], "params": [], "bodyType": "none",
                    "bodyText": "", "bodyFields": [],
                },
                "outputVariables": [
                    {"id": "v1", "name": "api_message", "type": "STRING",
                     "value": "response.body.message"},
                ],
            }),
            _node_entry("llm-sink", "LLM", {
                "label": "LLM 下游",
                "providerId": "provider-1",
                "modelName": "model-1",
                "systemPrompt": "",
                "userPrompt": "请处理: ${api_message}",
                "modelParameters": {"max_tokens": 64},
            }),
            END,
        ],
        "edges": [_edge("start", "http-src"), _edge("http-src", "llm-sink"),
                   _edge("llm-sink", "end")],
        "global_variables": [],
    }
    draft = _create_draft(client, body)

    _start_node(client, draft, "http-src")
    llm_run = _start_node(client, draft, "llm-sink")

    assert llm_run["status"] == "SUCCESS"
    # 验证 prompt 中变量已被替换为 "hello"
    req = _GatewayHandler.requests[-1]
    assert "hello" in str(req["body"]["messages"])


# ===================================================================
# D4: SCRIPT → LLM
# ===================================================================

def test_script_to_llm_resolves_variable_in_prompt(
    tmp_path, monkeypatch, gateway_server
):
    """SCRIPT 输出变量 → LLM prompt ${var} 正确替换。"""
    database_path = _patch_database(tmp_path, monkeypatch)
    _create_llm_provider(database_path, f"http://127.0.0.1:{gateway_server.server_port}/v1")
    _GatewayHandler.response_body = {
        "choices": [{"message": {"role": "assistant", "content": "退款是..."},
                      "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }
    client = TestClient(app)

    body = {
        "name": "SCRIPT → LLM",
        "description": "",
        "nodes": [
            START,
            _node_entry("script-a", "SCRIPT", {
                "label": "SCRIPT-A",
                "mainPy": "question = '什么是退款'\n",
                "outputVariables": [
                    {"id": "q", "name": "user_question", "type": "STRING",
                     "pythonVariable": "question"},
                ],
            }),
            _node_entry("llm-b", "LLM", {
                "label": "LLM-B",
                "providerId": "provider-1",
                "modelName": "model-1",
                "systemPrompt": "",
                "userPrompt": "回答问题: ${user_question}",
                "modelParameters": {"max_tokens": 64},
            }),
            END,
        ],
        "edges": [_edge("start", "script-a"), _edge("script-a", "llm-b"),
                   _edge("llm-b", "end")],
        "global_variables": [],
    }
    draft = _create_draft(client, body)
    _start_node(client, draft, "script-a")
    llm_run = _start_node(client, draft, "llm-b")

    assert llm_run["status"] == "SUCCESS"
    req = _GatewayHandler.requests[-1]
    assert "什么是退款" in str(req["body"]["messages"])


# ===================================================================
# D5: LLM → SCRIPT
# ===================================================================

def test_llm_to_script_passes_output_variable(
    tmp_path, monkeypatch, gateway_server
):
    """LLM 输出 → SCRIPT inputs[] 正确接收。"""
    database_path = _patch_database(tmp_path, monkeypatch)
    _create_llm_provider(database_path, f"http://127.0.0.1:{gateway_server.server_port}/v1")
    _GatewayHandler.response_body = {
        "choices": [{"message": {"role": "assistant", "content": "你好"},
                      "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }
    client = TestClient(app)

    body = {
        "name": "LLM → SCRIPT",
        "description": "",
        "nodes": [
            START,
            _node_entry("llm-a", "LLM", {
                "label": "LLM-A",
                "providerId": "provider-1",
                "modelName": "model-1",
                "systemPrompt": "",
                "userPrompt": "用中文说 hello",
                "modelParameters": {"max_tokens": 64},
                "outputVariables": [
                    {"id": "v1", "name": "llm_answer", "type": "STRING",
                     "value": "response.choices[0].message.content"},
                ],
            }),
            _node_entry("script-b", "SCRIPT", {
                "label": "SCRIPT-B",
                "mainPy": 'msg = f"LLM said: {inputs[\'llm_answer\']}"\nprint(msg, flush=True)\n',
                "outputVariables": [
                    {"id": "out", "name": "final", "type": "STRING",
                     "pythonVariable": "msg"},
                ],
            }),
            END,
        ],
        "edges": [_edge("start", "llm-a"), _edge("llm-a", "script-b"),
                   _edge("script-b", "end")],
        "global_variables": [],
    }
    draft = _create_draft(client, body)

    _start_node(client, draft, "llm-a")
    script_run = _start_node(client, draft, "script-b")

    assert script_run["status"] == "SUCCESS"
    assert script_run["stdout"] == "LLM said: 你好\n"
    assert script_run["output_variables"]["final"] == "LLM said: 你好"


# ===================================================================
# D6: 三节点链 HTTP(A) → SCRIPT(B) → LLM(C)
# ===================================================================

def test_three_node_chain_http_script_llm(
    tmp_path, monkeypatch, http_server, gateway_server
):
    """C 同时引用 A（HTTP）和 B（SCRIPT）的输出变量。"""
    database_path = _patch_database(tmp_path, monkeypatch)
    _create_llm_provider(database_path, f"http://127.0.0.1:{gateway_server.server_port}/v1")
    _GatewayHandler.response_body = {
        "choices": [{"message": {"role": "assistant", "content": "评论: OK"},
                      "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
    }
    client = TestClient(app)

    body = {
        "name": "三节点链",
        "description": "",
        "nodes": [
            START,
            _node_entry("http-a", "HTTP", {
                "label": "HTTP-A",
                "httpConfig": {
                    "method": "GET",
                    "url": f"http://127.0.0.1:{http_server.server_port}/",
                    "headers": [], "params": [], "bodyType": "none",
                    "bodyText": "", "bodyFields": [],
                },
                "outputVariables": [
                    {"id": "v1", "name": "api_id", "type": "INTEGER",
                     "value": "response.body.id"},
                    {"id": "v2", "name": "api_msg", "type": "STRING",
                     "value": "response.body.message"},
                ],
            }),
            _node_entry("script-b", "SCRIPT", {
                "label": "SCRIPT-B",
                "mainPy": 'summary = f"[id={inputs[\'api_id\']}] {inputs[\'api_msg\']}"\n',
                "outputVariables": [
                    {"id": "s1", "name": "summary", "type": "STRING",
                     "pythonVariable": "summary"},
                ],
            }),
            _node_entry("llm-c", "LLM", {
                "label": "LLM-C",
                "providerId": "provider-1",
                "modelName": "model-1",
                "systemPrompt": "",
                "userPrompt": "原始消息: ${api_msg}\n摘要: ${summary}\n请评论",
                "modelParameters": {"max_tokens": 64},
            }),
            END,
        ],
        "edges": [_edge("start", "http-a"), _edge("http-a", "script-b"),
                   _edge("script-b", "llm-c"), _edge("llm-c", "end")],
        "global_variables": [],
    }
    draft = _create_draft(client, body)

    _start_node(client, draft, "http-a")
    _start_node(client, draft, "script-b")
    llm_run = _start_node(client, draft, "llm-c")

    assert llm_run["status"] == "SUCCESS"
    req = _GatewayHandler.requests[-1]
    prompt_text = str(req["body"]["messages"])
    assert "hello" in prompt_text          # 来自 A
    assert "[id=42]" in prompt_text         # 来自 B


# ===================================================================
# D7: 并行扇入 HTTP(A) → C, HTTP(B) → C
# ===================================================================

def _make_handler(response_body: dict):
    """创建一个返回固定 JSON 的 handler 类（避免 class 变量共享）。"""
    body_bytes = json.dumps(response_body).encode()

    class _FixedHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)

        def do_POST(self):
            self.do_GET()

        def log_message(self, _format, *_args):
            return

    return _FixedHandler


def test_parallel_fan_in_two_http_nodes_into_script(
    tmp_path, monkeypatch
):
    """两个 HTTP 节点分别输出不同变量，汇聚到同一个 SCRIPT。"""
    _patch_database(tmp_path, monkeypatch)

    server_a = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _make_handler({"message": "from-a", "id": 1}),
    )
    server_b = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _make_handler({"message": "from-b", "id": 99}),
    )
    ta = threading.Thread(target=server_a.serve_forever, daemon=True)
    tb = threading.Thread(target=server_b.serve_forever, daemon=True)
    ta.start()
    tb.start()

    try:
        client = TestClient(app)
        body = {
            "name": "并行扇入",
            "description": "",
            "nodes": [
                START,
                _node_entry("http-a", "HTTP", {
                    "label": "HTTP-A",
                    "httpConfig": {
                        "method": "GET",
                        "url": f"http://127.0.0.1:{server_a.server_port}/",
                        "headers": [], "params": [], "bodyType": "none",
                        "bodyText": "", "bodyFields": [],
                    },
                    "outputVariables": [
                        {"id": "a1", "name": "msg_a", "type": "STRING",
                         "value": "response.body.message"},
                    ],
                }),
                _node_entry("http-b", "HTTP", {
                    "label": "HTTP-B",
                    "httpConfig": {
                        "method": "GET",
                        "url": f"http://127.0.0.1:{server_b.server_port}/",
                        "headers": [], "params": [], "bodyType": "none",
                        "bodyText": "", "bodyFields": [],
                    },
                    "outputVariables": [
                        {"id": "b1", "name": "id_b", "type": "INTEGER",
                         "value": "response.body.id"},
                    ],
                }),
                _node_entry("script-c", "SCRIPT", {
                    "label": "SCRIPT-C",
                    "mainPy": 'combined = f"{inputs[\'msg_a\']}-{inputs[\'id_b\']}"\nprint(combined, flush=True)\n',
                    "outputVariables": [
                        {"id": "c1", "name": "combined", "type": "STRING",
                         "pythonVariable": "combined"},
                    ],
                }),
                END,
            ],
            "edges": [
                _edge("start", "http-a"), _edge("start", "http-b"),
                _edge("http-a", "script-c"), _edge("http-b", "script-c"),
                _edge("script-c", "end"),
            ],
            "global_variables": [],
        }
        draft = _create_draft(client, body)

        _start_node(client, draft, "http-a")
        _start_node(client, draft, "http-b")
        run_c = _start_node(client, draft, "script-c")

        assert run_c["status"] == "SUCCESS"
        assert run_c["stdout"] == "from-a-99\n"
    finally:
        server_a.shutdown()
        server_b.shutdown()
        server_a.server_close()
        server_b.server_close()


# ===================================================================
# D8: 同名变量最近优先
# ===================================================================

def test_duplicate_output_name_nearest_wins(tmp_path, monkeypatch):
    """A(远端)输出 msg="far" → B(近端)输出 msg="near" → C 拿到 "near"。"""
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    body = {
        "name": "同名变量最近优先",
        "description": "",
        "nodes": [
            START,
            _node_entry("far", "SCRIPT", {
                "label": "远端",
                "mainPy": "msg = 'far'\n",
                "outputVariables": [
                    {"id": "f1", "name": "message", "type": "STRING",
                     "pythonVariable": "msg"},
                ],
            }),
            _node_entry("near", "SCRIPT", {
                "label": "近端",
                "mainPy": "msg = 'near'\n",
                "outputVariables": [
                    {"id": "n1", "name": "message", "type": "STRING",
                     "pythonVariable": "msg"},
                ],
            }),
            _node_entry("consumer", "SCRIPT", {
                "label": "消费者",
                "mainPy": "selected = inputs['message']\nprint(selected, flush=True)\n",
                "outputVariables": [
                    {"id": "c1", "name": "selected", "type": "STRING",
                     "pythonVariable": "selected"},
                ],
            }),
            END,
        ],
        "edges": [
            _edge("start", "far"), _edge("far", "near"),
            _edge("near", "consumer"), _edge("consumer", "end"),
        ],
        "global_variables": [],
    }
    draft = _create_draft(client, body)

    _start_node(client, draft, "far")
    _start_node(client, draft, "near")
    run_c = _start_node(client, draft, "consumer")

    assert run_c["status"] == "SUCCESS"
    assert run_c["stdout"] == "near\n"
    assert run_c["output_variables"]["selected"] == "near"


# ===================================================================
# D9: 上游未执行时下游报错
# ===================================================================

def test_downstream_fails_when_upstream_never_ran(tmp_path, monkeypatch):
    """下游引用上游输出变量，但上游从未执行 → KeyError。"""
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    body = {
        "name": "上游从未执行",
        "description": "",
        "nodes": [
            START,
            _node_entry("upstream", "SCRIPT", {
                "label": "上游",
                "mainPy": "msg = 'data'\n",
                "outputVariables": [
                    {"id": "u1", "name": "upstream_data", "type": "STRING",
                     "pythonVariable": "msg"},
                ],
            }),
            _node_entry("downstream", "SCRIPT", {
                "label": "下游",
                "mainPy": "print(inputs['upstream_data'], flush=True)\n",
            }),
            END,
        ],
        "edges": [_edge("start", "upstream"), _edge("upstream", "downstream"),
                   _edge("downstream", "end")],
        "global_variables": [],
    }
    draft = _create_draft(client, body)

    # 直接执行 downstream，跳过 upstream
    run = _start_node(client, draft, "downstream")
    assert run["status"] == "FAILED"
    assert "KeyError" in run["error"].get("message", "")


# ===================================================================
# D10: 上游失败后下游引用其变量
# ===================================================================

def test_downstream_fails_when_upstream_failed(tmp_path, monkeypatch):
    """上游 FAILED → latest_success_run 查不到 → 变量缺失。"""
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    body = {
        "name": "上游失败",
        "description": "",
        "nodes": [
            START,
            _node_entry("bad-upstream", "SCRIPT", {
                "label": "失败上游",
                "mainPy": "raise RuntimeError('boom')\n",
                "outputVariables": [
                    {"id": "b1", "name": "data", "type": "STRING",
                     "pythonVariable": "data"},
                ],
            }),
            _node_entry("downstream", "SCRIPT", {
                "label": "下游",
                "mainPy": "print(inputs['data'], flush=True)\n",
            }),
            END,
        ],
        "edges": [_edge("start", "bad-upstream"),
                   _edge("bad-upstream", "downstream"), _edge("downstream", "end")],
        "global_variables": [],
    }
    draft = _create_draft(client, body)

    up_run = _start_node(client, draft, "bad-upstream")
    assert up_run["status"] == "FAILED"

    down_run = _start_node(client, draft, "downstream")
    assert down_run["status"] == "FAILED"
    assert "KeyError" in down_run["error"].get("message", "")


# ===================================================================
# D11: 全局变量与上游输出同名 → 创建时直接拒绝 (422)
# ===================================================================

def test_global_and_upstream_same_name_rejected_at_creation(
    tmp_path, monkeypatch
):
    """全局变量与上游输出变量同名 → 草稿创建返回 422。"""
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    body = {
        "name": "冲突场景",
        "description": "",
        "nodes": [
            START,
            _node_entry("upstream", "SCRIPT", {
                "label": "上游",
                "mainPy": "theme = 'from-upstream'\n",
                "outputVariables": [
                    {"id": "u1", "name": "theme", "type": "STRING",
                     "pythonVariable": "theme"},
                ],
            }),
            _node_entry("consumer", "SCRIPT", {
                "label": "消费者",
                "mainPy": "print(inputs.get('theme', ''), flush=True)\n",
            }),
            END,
        ],
        "edges": [_edge("start", "upstream"), _edge("upstream", "consumer"),
                   _edge("consumer", "end")],
        "global_variables": [{"name": "theme", "value": "from-global"}],
    }
    status = _create_draft_or_422(client, body)
    assert status == 422


# ===================================================================
# D12: 类型转换失败阻塞
# ===================================================================

def test_type_conversion_failure_on_output_variable(tmp_path, monkeypatch):
    """SCRIPT 输出 "not-a-number" 映射 INTEGER → FAILED。"""
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    body = {
        "name": "类型转换失败",
        "description": "",
        "nodes": [
            START,
            _node_entry("bad-script", "SCRIPT", {
                "label": "输出非数字",
                "mainPy": "value = 'not-a-number'\nprint(value, flush=True)\n",
                "outputVariables": [
                    {"id": "b1", "name": "numeric_value", "type": "INTEGER",
                     "pythonVariable": "value"},
                ],
            }),
            END,
        ],
        "edges": [_edge("start", "bad-script"), _edge("bad-script", "end")],
        "global_variables": [],
    }
    draft = _create_draft(client, body)

    run = _start_node(client, draft, "bad-script")
    assert run["status"] == "FAILED"
    assert "输出变量 numeric_value 转换失败" in run["error"]["message"]
    assert "INTEGER" in run["error"]["message"]
