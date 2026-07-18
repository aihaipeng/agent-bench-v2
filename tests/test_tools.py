import json

from fastapi.testclient import TestClient

from web import files, routes_tools
from web.app import app


def _patch_tools_storage(tmp_path, monkeypatch):
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    tools_file = inputs_dir / ".tools.json"
    monkeypatch.setattr(files, "INPUTS_DIR", inputs_dir)
    monkeypatch.setattr(routes_tools, "INPUTS_DIR", inputs_dir)
    monkeypatch.setattr(routes_tools, "TOOLS_FILE", tools_file)
    return tools_file


def _agent_body(**overrides):
    body = {
        "name": "Agent",
        "description": "description",
        "model": "model-1",
        "model_provider": "provider-1",
        "api_key": "secret",
        "base_url": "https://provider.example",
        "system_prompt": "system",
        "human_message": "human",
        "python_code": "response = {'ok': True}",
    }
    body.update(overrides)
    return body


def test_create_filter_and_sort_tools(tmp_path, monkeypatch):
    tools_file = _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    script = client.post(
        "/api/tools",
        json={"type": "script", "name": "  B 报告  ", "description": "report"},
    )
    agent = client.post(
        "/api/tools",
        json={"type": "agent", "name": "A Agent", "description": "agent"},
    )

    assert script.status_code == 200
    assert agent.status_code == 200
    assert tools_file.is_file()
    filtered = client.get("/api/tools", params={"type": "script", "q": "报告"})
    assert [tool["name"] for tool in filtered.json()["tools"]] == ["B 报告"]
    sorted_tools = client.get(
        "/api/tools", params={"sort_by": "name", "sort_dir": "asc"}
    )
    assert [tool["name"] for tool in sorted_tools.json()["tools"]] == [
        "A Agent",
        "B 报告",
    ]


def test_tool_name_must_be_unique(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    first = client.post(
        "/api/tools", json={"type": "script", "name": "唯一名称", "description": ""}
    ).json()["tool"]
    second = client.post(
        "/api/tools", json={"type": "agent", "name": "其它名称", "description": ""}
    ).json()["tool"]

    duplicate_create = client.post(
        "/api/tools", json={"type": "agent", "name": " 唯一名称 ", "description": ""}
    )
    duplicate_update = client.put(
        f"/api/tools/{second['id']}", json=_agent_body(name="唯一名称")
    )
    same_name = client.put(
        f"/api/tools/{first['id']}",
        json={"name": "唯一名称", "description": "", "script_code": "print('ok')"},
    )

    assert duplicate_create.status_code == 400
    assert duplicate_update.status_code == 400
    assert same_name.status_code == 200


def test_update_agent_and_script_fields(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    agent = client.post(
        "/api/tools", json={"type": "agent", "name": "Old Agent", "description": ""}
    ).json()["tool"]
    script = client.post(
        "/api/tools", json={"type": "script", "name": "Old Script", "description": ""}
    ).json()["tool"]

    agent_response = client.put(
        f"/api/tools/{agent['id']}", json=_agent_body(name="New Agent")
    )
    script_response = client.put(
        f"/api/tools/{script['id']}",
        json={"name": "New Script", "description": "script", "script_code": "print('ok')"},
    )

    assert agent_response.status_code == 200
    saved_agent = agent_response.json()["tool"]
    for field in (
        "model",
        "model_provider",
        "api_key",
        "base_url",
        "system_prompt",
        "human_message",
        "python_code",
    ):
        assert saved_agent[field] == _agent_body(name="New Agent")[field]
    assert script_response.json()["tool"]["script_code"] == "print('ok')"


def test_agent_update_requires_five_parameters_and_python_code(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    agent = client.post(
        "/api/tools", json={"type": "agent", "name": "Required", "description": ""}
    ).json()["tool"]

    missing = client.put(
        f"/api/tools/{agent['id']}",
        json=_agent_body(
            model="", model_provider="", api_key="", base_url="", human_message=""
        ),
    )
    empty_code = client.put(
        f"/api/tools/{agent['id']}", json=_agent_body(python_code="")
    )
    empty_system_prompt = client.put(
        f"/api/tools/{agent['id']}", json=_agent_body(system_prompt="")
    )

    assert missing.status_code == 400
    for field in ("model", "model_provider", "api_key", "base_url", "human_message"):
        assert field in missing.json()["detail"]
    assert empty_code.status_code == 400
    assert empty_system_prompt.status_code == 200


def test_metadata_patch_preserves_agent_configuration(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    agent = client.post(
        "/api/tools", json={"type": "agent", "name": "Original", "description": "old"}
    ).json()["tool"]
    assert client.put(f"/api/tools/{agent['id']}", json=_agent_body(name="Original")).status_code == 200

    response = client.patch(
        f"/api/tools/{agent['id']}", json={"name": "Renamed", "description": "new"}
    )
    saved = client.get(f"/api/tools/{agent['id']}").json()["tool"]

    assert response.status_code == 200
    assert saved["name"] == "Renamed"
    assert saved["description"] == "new"
    assert saved["python_code"] == _agent_body()["python_code"]
    assert saved["api_key"] == "secret"


def test_agent_test_delegates_only_to_python_runtime(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    agent = client.post(
        "/api/tools", json={"type": "agent", "name": "Runtime", "description": ""}
    ).json()["tool"]
    calls = {}

    def fake_run(code, parameters):
        calls["code"] = code
        calls["parameters"] = parameters
        return {"ok": True, "logs": "runtime-output"}

    monkeypatch.setattr(routes_tools, "run_agent_python", fake_run)
    body = _agent_body()
    response = client.post(f"/api/tools/{agent['id']}/test", json=body)

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["logs"] == "runtime-output"
    assert response.json()["latency_ms"] >= 0
    assert calls["code"] == body["python_code"]
    assert calls["parameters"] == {
        "model": "model-1",
        "model_provider": "provider-1",
        "api_key": "secret",
        "base_url": "https://provider.example",
        "system_prompt": "system",
        "human_message": "human",
    }


def test_agent_test_returns_template_error_and_old_llm_route_is_removed(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    agent = client.post(
        "/api/tools", json={"type": "agent", "name": "Compile", "description": ""}
    ).json()["tool"]
    response = client.post(
        f"/api/tools/{agent['id']}/test",
        json=_agent_body(python_code="response = ${unknown}"),
    )
    removed = client.post(f"/api/tools/{agent['id']}/test-llm", json={})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "未知模板参数" in response.json()["logs"]
    assert removed.status_code == 404


def test_agent_api_preserves_emoji_in_worker_logs(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    agent = client.post(
        "/api/tools", json={"type": "agent", "name": "Unicode", "description": ""}
    ).json()["tool"]

    response = client.post(
        f"/api/tools/{agent['id']}/test",
        json=_agent_body(
            python_code="print('中文日志 🍖')\nresponse = {'message': '执行成功 🍖'}\nprint(response)"
        ),
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert "中文日志 🍖" in response.json()["logs"]
    assert "执行成功 🍖" in response.json()["logs"]


def test_script_runtime_remains_restricted(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    script = client.post(
        "/api/tools", json={"type": "script", "name": "Restricted", "description": ""}
    ).json()["tool"]

    ok = client.post(f"/api/tools/{script['id']}/run", json={"script_code": "print('ok')"})
    blocked = client.post(
        f"/api/tools/{script['id']}/run", json={"script_code": "import os"}
    )

    assert ok.json() == {"ok": True, "logs": "ok\n"}
    assert blocked.json()["ok"] is False
    assert "__import__" in blocked.json()["logs"]


def test_rejects_unknown_type_and_migrates_legacy_script(tmp_path, monkeypatch):
    tools_file = _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    assert client.post(
        "/api/tools", json={"type": "shell", "name": "bad", "description": ""}
    ).status_code == 400
    tools_file.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "id": "legacy-script",
                        "type": "python_script",
                        "name": "Legacy Script",
                        "content": "print('legacy')",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    tool = client.get("/api/tools/legacy-script").json()["tool"]
    assert tool["type"] == "script"
    assert tool["script_code"] == "print('legacy')"


def test_load_migrates_and_persists_legacy_agent_placeholders(tmp_path, monkeypatch):
    tools_file = _patch_tools_storage(tmp_path, monkeypatch)
    legacy_code = (
        'response = {"model": {{model}}, '
        '"extra_body": {"thinking": {"type": "disabled"}}}'
    )
    tools_file.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "id": "legacy-agent",
                        "type": "agent",
                        "name": "Legacy Agent",
                        "python_code": legacy_code,
                        "agent_template_version": 2,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    tool = TestClient(app).get("/api/tools/legacy-agent").json()["tool"]
    persisted = json.loads(tools_file.read_text(encoding="utf-8"))["tools"][0]

    assert tool["python_code"] == (
        'response = {"model": ${model}, '
        '"extra_body": {"thinking": {"type": "disabled"}}}'
    )
    assert tool["agent_template_version"] == routes_tools.AGENT_TEMPLATE_VERSION
    assert persisted["python_code"] == tool["python_code"]
    assert persisted["agent_template_version"] == routes_tools.AGENT_TEMPLATE_VERSION
