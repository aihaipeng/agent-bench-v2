import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from web import routes_tool_templates
from web.app import app
from web.tool_templates import (
    AgentDefinition,
    TemplateManifest,
    TemplateRepositoryError,
    ToolTemplate,
    ToolTemplateRepository,
)


def _patch_root(tmp_path, monkeypatch):
    root = tmp_path / "tool_registry"
    monkeypatch.setattr(routes_tool_templates, "TOOL_TEMPLATE_ROOT", root)
    monkeypatch.setattr(routes_tool_templates, "_repository_instance", None)
    monkeypatch.setattr(routes_tool_templates, "_repository_root", None)
    return root


def _manifest(template_id="template-1", template_type="AGENT"):
    return TemplateManifest(
        id=template_id,
        type=template_type,
        name="Template",
        created_at="2026-07-20T00:00:00Z",
        updated_at="2026-07-20T00:00:00Z",
    )


def test_types_are_strict_uppercase_and_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        TemplateManifest(
            id="lowercase",
            type="agent",
            name="Invalid",
            created_at="now",
            updated_at="now",
        )
    with pytest.raises(ValidationError):
        AgentDefinition(type="AGENT", legacy_parameters={})


@pytest.mark.parametrize(
    ("template_type", "expects_main"),
    [("HTTP", False), ("AGENT", True), ("LLM", True), ("SCRIPT", True)],
)
def test_api_creates_all_four_types_with_new_package_layout(
    tmp_path, monkeypatch, template_type, expects_main
):
    root = _patch_root(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/api/tool-templates",
        json={"type": template_type, "name": f"{template_type} Template"},
    )

    assert response.status_code == 200
    template = response.json()["template"]
    assert template["manifest"]["type"] == template_type
    assert template["definition"]["type"] == template_type
    directory = root / template["manifest"]["id"]
    assert (directory / "manifest.json").is_file()
    assert (directory / "definition.json").is_file()
    assert (directory / "main.py").is_file() is expects_main
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    definition = json.loads((directory / "definition.json").read_text(encoding="utf-8"))
    assert manifest["type"] == definition["type"] == template_type


def test_api_rejects_lowercase_and_old_tools_endpoint(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    client = TestClient(app)

    assert client.post(
        "/api/tool-templates", json={"type": "agent", "name": "Old"}
    ).status_code == 422
    assert client.get("/api/tool-templates", params={"type": "agent"}).status_code == 422
    assert client.get("/api/tools").status_code == 404


def test_http_mode_preserves_code_and_only_requires_it_for_code_mode(
    tmp_path, monkeypatch
):
    _patch_root(tmp_path, monkeypatch)
    client = TestClient(app)
    created = client.post(
        "/api/tool-templates", json={"type": "HTTP", "name": "Request"}
    ).json()["template"]
    template_id = created["manifest"]["id"]
    common = {
        "name": "Request",
        "inputs": [{"name": "order_id", "type": "STRING", "required": True}],
        "outputs": [{"name": "result", "type": "JSON"}],
        "config": {"timeout_seconds": 30},
        "http": {"method": "GET", "url": "https://example.test/orders"},
    }

    missing_code = client.put(
        f"/api/tool-templates/{template_id}",
        json={**common, "execution_mode": "CODE"},
    )
    code_mode = client.put(
        f"/api/tool-templates/{template_id}",
        json={**common, "execution_mode": "CODE", "main_py": "response = inputs\n"},
    )
    config_mode = client.put(
        f"/api/tool-templates/{template_id}",
        json={**common, "execution_mode": "CONFIG"},
    )

    assert missing_code.status_code == 400
    assert code_mode.status_code == 200
    assert config_mode.status_code == 200
    saved = config_mode.json()["template"]
    assert saved["definition"]["execution_mode"] == "CONFIG"
    assert saved["main_py"] == "response = inputs\n"


def test_repository_refresh_rejects_old_layout_and_keeps_valid_templates(
    tmp_path,
):
    root = tmp_path / "tool_registry"
    old = root / "old-tool"
    old.mkdir(parents=True)
    (old / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "old-tool",
                "type": "agent",
                "name": "Old",
                "created_at": "now",
                "updated_at": "now",
            }
        ),
        encoding="utf-8",
    )
    (old / "main.py").write_text("response = None", encoding="utf-8")
    repository = ToolTemplateRepository(root)
    valid = ToolTemplate(
        manifest=_manifest(),
        definition=AgentDefinition(type="AGENT"),
        main_py="response = inputs\n",
    )
    repository.create_template(valid)

    errors = repository.refresh()

    assert [item.manifest.id for item in repository.list_templates()] == ["template-1"]
    assert errors == [{"directory": "old-tool", "error": "缺少 definition.json"}]


def test_repository_crud_round_trip_and_api_filter(tmp_path, monkeypatch):
    root = _patch_root(tmp_path, monkeypatch)
    client = TestClient(app)
    agent = client.post(
        "/api/tool-templates", json={"type": "AGENT", "name": "Same Name"}
    ).json()["template"]
    script = client.post(
        "/api/tool-templates", json={"type": "SCRIPT", "name": "Same Name"}
    ).json()["template"]

    filtered = client.get("/api/tool-templates", params={"type": "AGENT"})
    fetched = client.get(f"/api/tool-templates/{agent['manifest']['id']}")
    deleted = client.delete(f"/api/tool-templates/{script['manifest']['id']}")

    assert filtered.status_code == 200
    assert [item["manifest"]["id"] for item in filtered.json()["templates"]] == [
        agent["manifest"]["id"]
    ]
    assert fetched.json()["template"] == agent
    assert deleted.status_code == 200
    assert not (root / script["manifest"]["id"]).exists()
    assert client.get(f"/api/tool-templates/{script['manifest']['id']}").status_code == 404


def test_python_template_requires_main_py():
    with pytest.raises(ValidationError, match="必须包含 main.py"):
        ToolTemplate(
            manifest=_manifest(),
            definition=AgentDefinition(type="AGENT"),
            main_py=None,
        )


def test_repository_rejects_duplicate_id(tmp_path):
    repository = ToolTemplateRepository(tmp_path / "tool_registry")
    template = ToolTemplate(
        manifest=_manifest(),
        definition=AgentDefinition(type="AGENT"),
        main_py="response = inputs\n",
    )
    repository.create_template(template)
    with pytest.raises(TemplateRepositoryError, match="ID 已存在"):
        repository.create_template(template)


def test_publish_always_creates_independent_ids_and_clears_config_api_keys(
    tmp_path, monkeypatch
):
    _patch_root(tmp_path, monkeypatch)
    client = TestClient(app)
    body = {
        "type": "AGENT",
        "name": "Published Agent",
        "description": "Canvas copy",
        "definition": {
            "type": "AGENT",
            "inputs": [{"name": "question", "type": "STRING"}],
            "outputs": [{"name": "answer", "type": "STRING"}],
            "config": {
                "api_key": "secret-one",
                "provider": {"apiKey": "secret-two", "model": "custom"},
            },
        },
        "main_py": "response = {'answer': inputs['question']}\n",
    }

    first = client.post("/api/tool-templates/publish", json=body)
    second = client.post("/api/tool-templates/publish", json=body)

    assert first.status_code == second.status_code == 200
    first_template = first.json()["template"]
    second_template = second.json()["template"]
    assert first_template["manifest"]["id"] != second_template["manifest"]["id"]
    assert first_template["manifest"]["name"] == second_template["manifest"]["name"]
    assert first_template["definition"]["config"] == {
        "api_key": "",
        "provider": {"apiKey": "", "model": "custom"},
    }
    assert first_template["main_py"] == body["main_py"]


def test_publish_rejects_mismatched_type(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/api/tool-templates/publish",
        json={
            "type": "SCRIPT",
            "name": "Mismatch",
            "definition": {"type": "AGENT"},
            "main_py": "response = inputs",
        },
    )

    assert response.status_code == 400
    assert client.get("/api/tool-templates").json()["templates"] == []
