import json

from fastapi.testclient import TestClient

from web import routes_tools
from web.app import app


def _patch_storage(tmp_path, monkeypatch):
    registry_root = tmp_path / "tool_registry"
    monkeypatch.setattr(routes_tools, "TOOL_REGISTRY_ROOT", registry_root)
    monkeypatch.setattr(routes_tools, "_registry_instance", None)
    monkeypatch.setattr(routes_tools, "_registry_root", None)
    return registry_root


def test_new_agent_uses_standard_template_and_portable_file_schema(tmp_path, monkeypatch):
    registry_root = _patch_storage(tmp_path, monkeypatch)

    tool = TestClient(app).post(
        "/api/tools",
        json={"type": "agent", "name": "Template Agent", "description": ""},
    ).json()["tool"]
    directories = [path for path in registry_root.iterdir() if path.is_dir()]
    manifest = json.loads(
        (directories[0] / "manifest.json").read_text(encoding="utf-8")
    )
    code = (directories[0] / "main.py").read_text(encoding="utf-8")

    assert len(directories) == 1
    assert directories[0].name == tool["id"]
    assert manifest["schema_version"] == 1
    assert manifest["id"] == tool["id"]
    assert manifest["type"] == "agent"
    assert "code" not in manifest
    assert code == routes_tools.DEFAULT_AGENT_PYTHON_CODE
    assert set(manifest["parameters"]) == {
        "model",
        "model_provider",
        "api_key",
        "base_url",
        "system_prompt",
        "human_message",
    }
    assert tool["python_code"] == routes_tools.DEFAULT_AGENT_PYTHON_CODE
    assert tool["needs_review"] is False
    assert tool["agent_template_version"] == routes_tools.AGENT_TEMPLATE_VERSION

    python_code = tool["python_code"]
    for parameter in manifest["parameters"]:
        assert f"${{{parameter}}}" in python_code
    expected_steps = (
        "from langchain.chat_models import init_chat_model",
        "from langchain.agents import create_agent",
        "from rich import print",
        "model = init_chat_model(",
        "agent = create_agent(",
        "response = agent.invoke({",
        "print(response)",
    )
    positions = [python_code.index(step) for step in expected_steps]
    assert positions == sorted(positions)
    assert "# 流式输出" in python_code
    assert "# for chunk, _ in agent.stream(" in python_code
    assert '#     stream_mode="messages",' in python_code
    assert '#         print(chunk.content, end="", flush=True)' in python_code
    assert "# 阻塞式输出" in python_code
    assert python_code.rstrip().endswith("print(response)")


def test_agent_update_persists_code_parameters_and_secret_in_single_file(tmp_path, monkeypatch):
    registry_root = _patch_storage(tmp_path, monkeypatch)
    client = TestClient(app)
    tool = client.post(
        "/api/tools",
        json={"type": "agent", "name": "Agent", "description": ""},
    ).json()["tool"]
    body = {
        "name": "Agent",
        "description": "updated",
        "model": "model-1",
        "model_provider": "provider-1",
        "api_key": "secret-1",
        "base_url": "https://provider.example",
        "system_prompt": "system",
        "human_message": "human",
        "python_code": "response = {'ok': True}",
    }

    response = client.put(f"/api/tools/{tool['id']}", json=body)
    directory = registry_root / tool["id"]
    stored = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    code = (directory / "main.py").read_text(encoding="utf-8")

    assert response.status_code == 200
    assert code == body["python_code"]
    assert stored["parameters"]["api_key"] == "secret-1"
    assert stored["parameters"]["model"] == "model-1"
    assert "code" not in stored
    assert "python_code" not in stored
    assert "needs_review" not in stored
