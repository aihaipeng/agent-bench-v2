import json

from fastapi.testclient import TestClient

from web import files, routes_tools
from web.app import app


def _patch_storage(tmp_path, monkeypatch):
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    tools_file = inputs_dir / ".tools.json"
    monkeypatch.setattr(files, "INPUTS_DIR", inputs_dir)
    monkeypatch.setattr(routes_tools, "INPUTS_DIR", inputs_dir)
    monkeypatch.setattr(routes_tools, "TOOLS_FILE", tools_file)
    return tools_file


def test_new_agent_uses_new_schema_and_standard_template(tmp_path, monkeypatch):
    tools_file = _patch_storage(tmp_path, monkeypatch)

    tool = TestClient(app).post(
        "/api/tools",
        json={"type": "agent", "name": "Template Agent", "description": ""},
    ).json()["tool"]
    stored = json.loads(tools_file.read_text(encoding="utf-8"))["tools"][0]

    assert tool["python_code"] == routes_tools.DEFAULT_AGENT_PYTHON_CODE
    assert tool["needs_review"] is False
    assert tool["agent_template_version"] == routes_tools.AGENT_TEMPLATE_VERSION
    python_code = tool["python_code"]
    for parameter in (
        "model",
        "model_provider",
        "api_key",
        "base_url",
        "system_prompt",
        "human_message",
    ):
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
    assert python_code.rstrip().endswith("print(response)")
    assert "additional_components" not in stored
    assert "temperature" not in stored


def test_legacy_agent_without_custom_code_gets_standard_template(tmp_path, monkeypatch):
    tools_file = _patch_storage(tmp_path, monkeypatch)
    tools_file.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "id": "legacy-standard",
                        "type": "agent",
                        "name": "Legacy Standard",
                        "model": "legacy-model",
                        "model_provider": "legacy-provider",
                        "api_key": "legacy-key",
                        "base_url": "https://legacy.example",
                        "prompt": "legacy prompt",
                        "human_message": "legacy message",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    tool = TestClient(app).get("/api/tools/legacy-standard").json()["tool"]

    assert tool["python_code"] == routes_tools.DEFAULT_AGENT_PYTHON_CODE
    assert tool["needs_review"] is False
    assert tool["system_prompt"] == "legacy prompt"
    assert tool["model"] == "legacy-model"


def test_all_legacy_custom_code_is_replaced_by_new_standard_template(tmp_path, monkeypatch):
    tools_file = _patch_storage(tmp_path, monkeypatch)
    legacy_code = "response = agent.invoke(payload)"
    tools_file.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "id": "legacy-custom",
                        "type": "agent",
                        "name": "Legacy Custom",
                        "additional_components": legacy_code,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    tool = TestClient(app).get("/api/tools/legacy-custom").json()["tool"]

    assert tool["python_code"] == routes_tools.DEFAULT_AGENT_PYTHON_CODE
    assert tool["python_code"] != legacy_code
    assert tool["needs_review"] is False


def test_current_template_version_preserves_user_code(tmp_path, monkeypatch):
    tools_file = _patch_storage(tmp_path, monkeypatch)
    user_code = "response = {'custom': True}\nprint(response)"
    tools_file.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "id": "current-agent",
                        "type": "agent",
                        "name": "Current Agent",
                        "python_code": user_code,
                        "agent_template_version": routes_tools.AGENT_TEMPLATE_VERSION,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    tool = TestClient(app).get("/api/tools/current-agent").json()["tool"]

    assert tool["python_code"] == user_code
    assert tool["needs_review"] is False


def test_agent_update_persists_only_new_agent_fields_and_clears_review(tmp_path, monkeypatch):
    tools_file = _patch_storage(tmp_path, monkeypatch)
    tools_file.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "id": "legacy-custom",
                        "type": "agent",
                        "name": "Legacy Custom",
                        "additional_components": "legacy code",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    body = {
        "name": "Migrated Agent",
        "description": "migrated",
        "model": "model-1",
        "model_provider": "provider-1",
        "api_key": "secret-1",
        "base_url": "https://provider.example",
        "system_prompt": "system",
        "human_message": "human",
        "python_code": "response = {'ok': True}",
    }

    response = TestClient(app).put("/api/tools/legacy-custom", json=body)
    stored = json.loads(tools_file.read_text(encoding="utf-8"))["tools"][0]

    assert response.status_code == 200
    assert stored["python_code"] == body["python_code"]
    assert stored["needs_review"] is False
    assert stored["agent_template_version"] == routes_tools.AGENT_TEMPLATE_VERSION
    assert stored["api_key"] == "secret-1"
    assert "additional_components" not in stored
    assert "prompt" not in stored
