import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from web import routes_tool_templates
from web.app import app
from web.tool_template_archives import build_template_archive, parse_template_archive
from web.tool_templates import (
    AgentDefinition,
    HttpDefinition,
    TemplateManifest,
    TemplateRepositoryError,
    ToolTemplate,
    ToolTemplateRepository,
)


def _template(template_id: str, template_type: str = "AGENT") -> ToolTemplate:
    manifest = TemplateManifest(
        id=template_id,
        type=template_type,
        name=f"{template_type} Template",
        created_at="2026-07-20T00:00:00Z",
        updated_at="2026-07-20T00:00:00Z",
    )
    if template_type == "HTTP":
        definition = HttpDefinition(type="HTTP", execution_mode="CONFIG")
        main_py = None
    else:
        definition = AgentDefinition(type="AGENT")
        main_py = "response = inputs\n"
    return ToolTemplate(manifest=manifest, definition=definition, main_py=main_py)


def _zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _patch_root(tmp_path, monkeypatch, name="tool_registry"):
    root = tmp_path / name
    monkeypatch.setattr(routes_tool_templates, "TOOL_TEMPLATE_ROOT", root)
    monkeypatch.setattr(routes_tool_templates, "_repository_instance", None)
    monkeypatch.setattr(routes_tool_templates, "_repository_root", None)
    return root


def test_archive_round_trip_preserves_multiple_template_packages():
    source = [_template("agent-one"), _template("http-one", "HTTP")]

    content = build_template_archive(source)
    imported = parse_template_archive(content)

    assert imported == source
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert sorted(archive.namelist()) == [
            "agent-one/definition.json",
            "agent-one/main.py",
            "agent-one/manifest.json",
            "http-one/definition.json",
            "http-one/manifest.json",
        ]


@pytest.mark.parametrize(
    "entries",
    [
        {"../manifest.json": "{}"},
        {"template/../../manifest.json": "{}"},
        {"manifest.json": "{}", "main.py": "response = None"},
        {"template/manifest.json": "{}", "template/extra.txt": "unexpected"},
    ],
)
def test_archive_rejects_traversal_old_layout_and_unexpected_files(entries):
    with pytest.raises(TemplateRepositoryError):
        parse_template_archive(_zip(entries))


def test_bulk_create_rejects_conflicts_without_partial_write(tmp_path):
    repository = ToolTemplateRepository(tmp_path / "tool_registry")
    repository.create_template(_template("existing"))

    with pytest.raises(TemplateRepositoryError, match="ID 已存在"):
        repository.create_templates([_template("new-template"), _template("existing")])

    assert [item.manifest.id for item in repository.list_templates()] == ["existing"]
    assert not (repository.root / "new-template").exists()


def test_old_package_missing_definition_is_rejected_before_repository_write(tmp_path):
    manifest = _template("old-agent").manifest.model_dump(mode="json")
    archive = _zip(
        {
            "old-agent/manifest.json": json.dumps(manifest),
            "old-agent/main.py": "response = inputs\n",
        }
    )
    repository = ToolTemplateRepository(tmp_path / "tool_registry")

    with pytest.raises(TemplateRepositoryError, match="缺少 definition.json"):
        repository.create_templates(parse_template_archive(archive))

    assert repository.list_templates() == []


def test_api_exports_selected_templates_and_imports_them_into_an_empty_repository(
    tmp_path, monkeypatch
):
    _patch_root(tmp_path, monkeypatch, "source")
    client = TestClient(app)
    agent = client.post(
        "/api/tool-templates", json={"type": "AGENT", "name": "Agent"}
    ).json()["template"]
    client.post("/api/tool-templates", json={"type": "HTTP", "name": "HTTP"})

    exported = client.post(
        "/api/tool-templates/export",
        json={"template_ids": [agent["manifest"]["id"]]},
    )

    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert archive.namelist() == [
            f"{agent['manifest']['id']}/manifest.json",
            f"{agent['manifest']['id']}/definition.json",
            f"{agent['manifest']['id']}/main.py",
        ]

    target = _patch_root(tmp_path, monkeypatch, "target")
    imported = client.post(
        "/api/tool-templates/import",
        files={"file": ("agent.zip", exported.content, "application/zip")},
    )

    assert imported.status_code == 200
    assert imported.json()["imported"] == 1
    assert imported.json()["templates"][0] == agent
    assert (target / agent["manifest"]["id"] / "definition.json").is_file()


def test_api_import_rejects_duplicate_id_without_importing_other_templates(
    tmp_path, monkeypatch
):
    root = _patch_root(tmp_path, monkeypatch)
    client = TestClient(app)
    existing = client.post(
        "/api/tool-templates", json={"type": "AGENT", "name": "Existing"}
    ).json()["template"]
    content = build_template_archive(
        [_template("new-template"), ToolTemplate.model_validate(existing)]
    )

    response = client.post(
        "/api/tool-templates/import",
        files={"file": ("templates.zip", content, "application/zip")},
    )

    assert response.status_code == 400
    assert "ID 已存在" in response.json()["detail"]
    assert not (root / "new-template").exists()
    assert len(client.get("/api/tool-templates").json()["templates"]) == 1


def test_api_rejects_old_zip_and_non_zip_without_writing(tmp_path, monkeypatch):
    root = _patch_root(tmp_path, monkeypatch)
    client = TestClient(app)
    old_zip = _zip({"manifest.json": "{}", "main.py": "response = None"})

    old_response = client.post(
        "/api/tool-templates/import",
        files={"file": ("old.zip", old_zip, "application/zip")},
    )
    wrong_extension = client.post(
        "/api/tool-templates/import",
        files={"file": ("old.json", old_zip, "application/json")},
    )

    assert old_response.status_code == 400
    assert wrong_extension.status_code == 400
    assert not root.exists() or not any(path.is_dir() for path in root.iterdir())
