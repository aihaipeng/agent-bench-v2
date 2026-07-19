import json
import re
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from web import routes_tools
from web.app import app


def _patch_registry(tmp_path, monkeypatch):
    root = tmp_path / "tool_registry"
    monkeypatch.setattr(routes_tools, "TOOL_REGISTRY_ROOT", root)
    monkeypatch.setattr(routes_tools, "_registry_instance", None)
    monkeypatch.setattr(routes_tools, "_registry_root", None)
    return root


def _portable_tool(tool_id: str, tool_type: str = "script", name: str = "工具") -> dict:
    return {
        "schema_version": 1,
        "id": tool_id,
        "type": tool_type,
        "name": name,
        "description": "imported",
        "code": "response = {'ok': True}",
        "parameters": (
            {
                "model": "model-1",
                "model_provider": "provider-1",
                "api_key": "secret",
                "base_url": "https://example.test",
                "system_prompt": "system",
                "human_message": "human",
            }
            if tool_type == "agent"
            else {}
        ),
        "created_at": "2026-07-19T10:00:00",
        "updated_at": "2026-07-19T10:00:00",
    }


def _write_external(root, data: dict) -> None:
    directory = root / data["id"]
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {key: value for key, value in data.items() if key != "code"}
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "main.py").write_text(data["code"], encoding="utf-8")


def _tool_zip(*tools: dict, extra_entries: dict[str, str] | None = None) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for tool in tools:
            manifest = {key: value for key, value in tool.items() if key != "code"}
            archive.writestr(
                f"{tool['id']}/manifest.json",
                json.dumps(manifest, ensure_ascii=False),
            )
            archive.writestr(f"{tool['id']}/main.py", tool["code"])
        for path, content in (extra_entries or {}).items():
            archive.writestr(path, content)
    return output.getvalue()


def test_refresh_applies_external_directories_and_reports_invalid(tmp_path, monkeypatch):
    root = _patch_registry(tmp_path, monkeypatch)
    client = TestClient(app)
    assert client.get("/api/tools").json()["tools"] == []

    _write_external(root, _portable_tool("external"))
    broken = root / "broken"
    broken.mkdir()
    (broken / "manifest.json").write_text("{broken", encoding="utf-8")
    (broken / "main.py").write_text("print('broken')", encoding="utf-8")

    assert client.get("/api/tools").json()["tools"] == []
    refreshed = client.post("/api/tools/refresh")

    assert refreshed.status_code == 200
    assert refreshed.json()["loaded"] == 1
    assert refreshed.json()["errors"][0]["file"] == "broken"
    assert "JSON 格式错误" in refreshed.json()["errors"][0]["error"]
    assert client.get("/api/tools").json()["tools"][0]["id"] == "external"


def test_single_zip_export_delete_import_round_trip_preserves_code_and_secret(
    tmp_path, monkeypatch
):
    _patch_registry(tmp_path, monkeypatch)
    client = TestClient(app)
    tool = client.post(
        "/api/tools",
        json={"type": "agent", "name": "可分享 Agent", "description": ""},
    ).json()["tool"]
    update = {
        "name": "可分享 Agent",
        "description": "保留全部参数",
        "model": "model-1",
        "model_provider": "provider-1",
        "api_key": "real-secret",
        "base_url": "https://provider.example",
        "system_prompt": "system",
        "human_message": "human",
        "python_code": "response = {'shared': True}",
    }
    assert client.put(f"/api/tools/{tool['id']}", json=update).status_code == 200

    exported = client.get(f"/api/tools/{tool['id']}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"
    assert exported.headers["content-disposition"] == (
        f'attachment; filename="{tool["id"]}.zip"'
    )
    with ZipFile(BytesIO(exported.content)) as archive:
        assert archive.namelist() == [
            f"{tool['id']}/manifest.json",
            f"{tool['id']}/main.py",
        ]
        manifest = json.loads(archive.read(f"{tool['id']}/manifest.json"))
        code = archive.read(f"{tool['id']}/main.py").decode("utf-8")
    assert "code" not in manifest
    assert manifest["parameters"]["api_key"] == "real-secret"
    assert code == update["python_code"]

    assert client.delete(f"/api/tools/{tool['id']}").status_code == 200
    imported = client.post(
        "/api/tools/import",
        files={"files": (f"{tool['id']}.zip", exported.content, "application/zip")},
    )

    assert imported.status_code == 200
    assert imported.json()["errors"] == []
    assert imported.json()["imported"][0]["tool"]["id"] == tool["id"]
    saved = client.get(f"/api/tools/{tool['id']}").json()["tool"]
    assert saved["python_code"] == update["python_code"]
    assert saved["api_key"] == "real-secret"

    duplicate = client.post(
        "/api/tools/import",
        files={"files": ("duplicate.zip", exported.content, "application/zip")},
    )
    assert duplicate.json()["imported"] == []
    assert "工具 ID 已存在" in duplicate.json()["errors"][0]["error"]


def test_multiple_zip_import_keeps_valid_archives_and_all_tools(tmp_path, monkeypatch):
    _patch_registry(tmp_path, monkeypatch)
    client = TestClient(app)
    first = _tool_zip(_portable_tool("first", name="同名工具"))
    second = _tool_zip(
        _portable_tool("second", name="同名工具"),
        _portable_tool("third", "agent", name="Agent"),
    )

    response = client.post(
        "/api/tools/import",
        files=[
            ("files", ("first.zip", first, "application/zip")),
            ("files", ("broken.zip", b"not-a-zip", "application/zip")),
            ("files", ("second.zip", second, "application/zip")),
            ("files", ("notes.txt", b"ignored", "text/plain")),
        ],
    )
    data = response.json()

    assert response.status_code == 200
    assert [item["tool"]["id"] for item in data["imported"]] == [
        "first",
        "second",
        "third",
    ]
    assert [item["file"] for item in data["errors"]] == ["broken.zip", "notes.txt"]
    assert "ZIP 文件损坏" in data["errors"][0]["error"]
    assert data["errors"][1]["error"] == "仅支持 .zip 文件"


def test_import_rejects_unsafe_or_incomplete_zip_without_partial_writes(
    tmp_path, monkeypatch
):
    _patch_registry(tmp_path, monkeypatch)
    client = TestClient(app)
    valid = _portable_tool("valid")
    unsafe = _tool_zip(valid, extra_entries={"../outside.txt": "unsafe"})

    incomplete_output = BytesIO()
    with ZipFile(incomplete_output, "w", ZIP_DEFLATED) as archive:
        manifest = {key: value for key, value in valid.items() if key != "code"}
        archive.writestr("valid/manifest.json", json.dumps(manifest))

    response = client.post(
        "/api/tools/import",
        files=[
            ("files", ("unsafe.zip", unsafe, "application/zip")),
            (
                "files",
                ("incomplete.zip", incomplete_output.getvalue(), "application/zip"),
            ),
        ],
    )

    assert response.json()["imported"] == []
    assert "不安全路径" in response.json()["errors"][0]["error"]
    assert "缺少文件: main.py" in response.json()["errors"][1]["error"]
    assert client.get("/api/tools").json()["tools"] == []


def test_batch_export_packages_selected_or_all_tools_with_complete_parameters(
    tmp_path, monkeypatch
):
    _patch_registry(tmp_path, monkeypatch)
    client = TestClient(app)
    agent = client.post(
        "/api/tools", json={"type": "agent", "name": "Agent", "description": ""}
    ).json()["tool"]
    script = client.post(
        "/api/tools", json={"type": "script", "name": "Script", "description": ""}
    ).json()["tool"]
    update = {
        "name": "Agent",
        "description": "",
        "model": "model-1",
        "model_provider": "provider-1",
        "api_key": "zip-secret",
        "base_url": "https://provider.example",
        "system_prompt": "system",
        "human_message": "human",
        "python_code": "response = {'zip': True}",
    }
    assert client.put(f"/api/tools/{agent['id']}", json=update).status_code == 200

    selected = client.get("/api/tools/export", params=[("ids", agent["id"])])
    assert selected.status_code == 200
    assert selected.headers["content-type"] == "application/zip"
    assert re.fullmatch(
        r'attachment; filename="tools-\d{8}-\d{6}\.zip"',
        selected.headers["content-disposition"],
    )
    with ZipFile(BytesIO(selected.content)) as archive:
        assert archive.namelist() == [
            f"{agent['id']}/manifest.json",
            f"{agent['id']}/main.py",
        ]
        manifest = json.loads(archive.read(f"{agent['id']}/manifest.json"))
    assert manifest["parameters"]["api_key"] == "zip-secret"

    exported_all = client.get("/api/tools/export")
    with ZipFile(BytesIO(exported_all.content)) as archive:
        assert set(archive.namelist()) == {
            f"{agent['id']}/manifest.json",
            f"{agent['id']}/main.py",
            f"{script['id']}/manifest.json",
            f"{script['id']}/main.py",
        }


def test_batch_export_rejects_missing_id_and_empty_registry(tmp_path, monkeypatch):
    _patch_registry(tmp_path, monkeypatch)
    client = TestClient(app)

    assert client.get("/api/tools/export", params={"ids": "missing"}).status_code == 404
    empty = client.get("/api/tools/export")
    assert empty.status_code == 400
    assert empty.json()["detail"] == "没有可导出的工具"


def test_open_tool_directory_opens_id_directory(tmp_path, monkeypatch):
    root = _patch_registry(tmp_path, monkeypatch)
    client = TestClient(app)
    tool = client.post(
        "/api/tools", json={"type": "script", "name": "定位目录", "description": ""}
    ).json()["tool"]
    opened_paths = []

    def fake_open(path):
        opened_paths.append(path)
        return str(path.resolve())

    monkeypatch.setattr(routes_tools, "open_directory_in_explorer", fake_open)
    response = client.post(f"/api/tools/{tool['id']}/open-dir")

    assert response.status_code == 200
    assert opened_paths == [root.resolve() / tool["id"]]
    assert response.json()["path"] == str(opened_paths[0])
