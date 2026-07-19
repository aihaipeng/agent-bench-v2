from fastapi.testclient import TestClient

from web import routes_tools
from web.app import app


def _patch_tools_storage(tmp_path, monkeypatch):
    registry_root = tmp_path / "tool_registry"
    monkeypatch.setattr(routes_tools, "TOOL_REGISTRY_ROOT", registry_root)
    monkeypatch.setattr(routes_tools, "_registry_instance", None)
    monkeypatch.setattr(routes_tools, "_registry_root", None)
    return registry_root


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
    registry_root = _patch_tools_storage(tmp_path, monkeypatch)
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
    stored_directories = [path for path in registry_root.iterdir() if path.is_dir()]
    assert len(stored_directories) == 2
    assert {path.name for path in stored_directories} == {
        script.json()["tool"]["id"],
        agent.json()["tool"]["id"],
    }
    for directory in stored_directories:
        assert (directory / "manifest.json").is_file()
        assert (directory / "main.py").is_file()
    filtered = client.get("/api/tools", params={"type": "script", "q": "报告"})
    assert [tool["name"] for tool in filtered.json()["tools"]] == ["B 报告"]
    sorted_tools = client.get(
        "/api/tools", params={"sort_by": "name", "sort_dir": "asc"}
    )
    assert [tool["name"] for tool in sorted_tools.json()["tools"]] == [
        "A Agent",
        "B 报告",
    ]


def test_tool_names_may_repeat_and_ids_remain_distinct(tmp_path, monkeypatch):
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

    assert duplicate_create.status_code == 200
    assert duplicate_update.status_code == 200
    assert same_name.status_code == 200
    tools = client.get("/api/tools").json()["tools"]
    same_names = [tool for tool in tools if tool["name"] == "唯一名称"]
    assert len(same_names) == 3
    assert len({tool["id"] for tool in same_names}) == 3


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


def test_agent_update_only_requires_a_name(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    agent = client.post(
        "/api/tools", json={"type": "agent", "name": "Draft", "description": ""}
    ).json()["tool"]

    draft = client.put(
        f"/api/tools/{agent['id']}",
        json=_agent_body(
            name="Saved Draft",
            model="",
            model_provider="",
            api_key="",
            base_url="",
            system_prompt="",
            human_message="",
            python_code="",
        ),
    )
    placeholder_draft = client.put(
        f"/api/tools/{agent['id']}",
        json=_agent_body(
            name="Saved Draft",
            model="",
            model_provider="",
            api_key="",
            base_url="",
            human_message="",
            python_code="response = [${model}, ${api_key}]",
        ),
    )
    empty_name = client.put(
        f"/api/tools/{agent['id']}", json=_agent_body(name="   ", python_code="")
    )

    assert draft.status_code == 200
    saved = draft.json()["tool"]
    assert saved["name"] == "Saved Draft"
    for field in (
        "model",
        "model_provider",
        "api_key",
        "base_url",
        "system_prompt",
        "human_message",
        "python_code",
    ):
        assert saved[field] == ""
    assert placeholder_draft.status_code == 200
    assert empty_name.status_code == 400
    assert empty_name.json()["detail"] == "名称不能为空"


def test_agent_run_requires_python_code_and_referenced_parameters(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    agent = client.post(
        "/api/tools", json={"type": "agent", "name": "Required", "description": ""}
    ).json()["tool"]

    missing = client.post(
        f"/api/tools/{agent['id']}/test",
        json=_agent_body(
            model="",
            model_provider="",
            api_key="",
            base_url="",
            human_message="",
            python_code=(
                "response = [${model}, ${model_provider}, ${api_key}, "
                "${base_url}, ${human_message}]"
            ),
        ),
    )
    empty_code = client.post(
        f"/api/tools/{agent['id']}/test", json=_agent_body(python_code="")
    )

    assert missing.status_code == 400
    for field in ("model", "model_provider", "api_key", "base_url", "human_message"):
        assert field in missing.json()["detail"]
    assert empty_code.status_code == 400
    assert empty_code.json()["detail"] == "Python 代码不能为空"


def test_agent_update_allows_empty_unused_parameters(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    agent = client.post(
        "/api/tools", json={"type": "agent", "name": "General Python", "description": ""}
    ).json()["tool"]

    response = client.put(
        f"/api/tools/{agent['id']}",
        json=_agent_body(
            model="",
            model_provider="",
            api_key="",
            base_url="",
            human_message="",
            python_code="import statistics\nprint(statistics.mean([2, 4, 6]))",
        ),
    )

    assert response.status_code == 200


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

    def fake_run(code, parameters, run_id=None):
        calls["code"] = code
        calls["parameters"] = parameters
        calls["run_id"] = run_id
        return {
            "ok": True,
            "logs": "runtime-output",
            "response": {"answer": 42},
        }

    monkeypatch.setattr(routes_tools, "run_agent_python", fake_run)
    body = _agent_body(run_id="agent-api-run")
    response = client.post(f"/api/tools/{agent['id']}/test", json=body)

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["logs"] == "runtime-output"
    assert response.json()["response"] == {"answer": 42}
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
    assert calls["run_id"] == "agent-api-run"


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


def test_script_run_delegates_to_unrestricted_python_worker(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    script = client.post(
        "/api/tools", json={"type": "script", "name": "Runtime", "description": ""}
    ).json()["tool"]
    calls = {}

    def fake_run(code, run_id=None):
        calls["code"] = code
        calls["run_id"] = run_id
        return {
            "ok": True,
            "logs": "script-output",
            "response": {"answer": 42},
        }

    monkeypatch.setattr(routes_tools, "run_script_python", fake_run)
    code = "import langchain\nresponse = {'answer': 42}"
    response = client.post(
        f"/api/tools/{script['id']}/run",
        json={"script_code": code, "run_id": "script-api-run"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["logs"] == "script-output"
    assert response.json()["response"] == {"answer": 42}
    assert response.json()["latency_ms"] >= 0
    assert calls["code"] == code
    assert calls["run_id"] == "script-api-run"


def test_interrupt_run_delegates_idempotently(monkeypatch):
    client = TestClient(app)
    calls = []

    def fake_interrupt(run_id):
        calls.append(run_id)
        return len(calls) == 1

    monkeypatch.setattr(routes_tools, "interrupt_python_run", fake_interrupt)

    first = client.post("/api/tools/runs/current-run/interrupt")
    repeated = client.post("/api/tools/runs/current-run/interrupt")

    assert first.status_code == 200
    assert first.json() == {
        "ok": True,
        "run_id": "current-run",
        "process_terminated": True,
    }
    assert repeated.status_code == 200
    assert repeated.json()["process_terminated"] is False
    assert calls == ["current-run", "current-run"]


def test_rejects_unknown_type(tmp_path, monkeypatch):
    _patch_tools_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    assert client.post(
        "/api/tools", json={"type": "shell", "name": "bad", "description": ""}
    ).status_code == 400
