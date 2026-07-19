import json
from pathlib import Path

import pytest

from web.tool_registry import (
    SCHEMA_VERSION,
    ToolRegistry,
    ToolRegistryError,
    _replace_path,
)


def _tool(tool_id: str, tool_type: str = "script", name: str = "同名工具") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "id": tool_id,
        "type": tool_type,
        "name": name,
        "description": "说明",
        "code": "print('ok')",
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


def test_refresh_loads_valid_directories_allows_duplicate_names_and_reports_invalid(
    tmp_path,
):
    root = tmp_path / "tool_registry"
    _write_external(root, _tool("script-one"))
    _write_external(root, _tool("agent-one", "agent"))
    invalid = root / "broken"
    invalid.mkdir()
    (invalid / "manifest.json").write_text("{broken", encoding="utf-8")
    (invalid / "main.py").write_text("print('broken')", encoding="utf-8")

    registry = ToolRegistry(root)
    result = registry.refresh()

    assert result.loaded == 2
    assert [tool["name"] for tool in registry.list_tools()] == ["同名工具", "同名工具"]
    assert len(result.errors) == 1
    assert result.errors[0].file == "broken"
    assert "JSON 格式错误" in result.errors[0].error


def test_external_changes_only_enter_snapshot_after_refresh(tmp_path):
    root = tmp_path / "tool_registry"
    original = _tool("snapshot")
    _write_external(root, original)
    registry = ToolRegistry(root)
    registry.refresh()

    changed = {**original, "name": "外部修改", "code": "print('changed')"}
    _write_external(root, changed)

    assert registry.get_tool("snapshot")["name"] == "同名工具"
    assert registry.get_tool("snapshot")["code"] == "print('ok')"
    registry.refresh()
    assert registry.get_tool("snapshot")["name"] == "外部修改"
    assert registry.get_tool("snapshot")["code"] == "print('changed')"


def test_create_update_delete_each_operate_one_directory(tmp_path):
    root = tmp_path / "tool_registry"
    registry = ToolRegistry(root)
    created = registry.create_tool(_tool("crud"))
    directory = root / "crud"
    manifest_path = directory / "manifest.json"
    main_path = directory / "main.py"

    assert created["id"] == "crud"
    assert directory.is_dir()
    assert manifest_path.is_file()
    assert main_path.read_text(encoding="utf-8") == "print('ok')"
    assert "code" not in json.loads(manifest_path.read_text(encoding="utf-8"))

    updated = {**created, "name": "已修改", "code": "print('updated')"}
    registry.update_tool("crud", updated)
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["name"] == "已修改"
    assert main_path.read_text(encoding="utf-8") == "print('updated')"

    deleted = registry.delete_tool("crud")
    assert deleted["name"] == "已修改"
    assert not directory.exists()
    assert registry.get_tool("crud") is None


def test_directory_name_mismatch_and_missing_main_are_skipped_on_refresh(tmp_path):
    root = tmp_path / "tool_registry"
    _write_external(root, _tool("same-id", "agent"))

    mismatch = _tool("actual-id")
    mismatch_dir = root / "wrong-name"
    mismatch_dir.mkdir()
    manifest = {key: value for key, value in mismatch.items() if key != "code"}
    (mismatch_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (mismatch_dir / "main.py").write_text(mismatch["code"], encoding="utf-8")

    missing_main = root / "missing-main"
    missing_main.mkdir()
    missing_manifest = {
        key: value for key, value in _tool("missing-main").items() if key != "code"
    }
    (missing_main / "manifest.json").write_text(
        json.dumps(missing_manifest), encoding="utf-8"
    )

    registry = ToolRegistry(root)
    result = registry.refresh()

    assert result.loaded == 1
    assert registry.get_tool("same-id")["type"] == "agent"
    assert len(result.errors) == 2
    errors = {item.file: item.error for item in result.errors}
    assert "目录名必须与 id 一致" in errors["wrong-name"]
    assert "缺少 main.py" in errors["missing-main"]


def test_create_rejects_existing_id(tmp_path):
    registry = ToolRegistry(tmp_path / "tool_registry")
    registry.create_tool(_tool("duplicate"))

    with pytest.raises(ToolRegistryError, match="工具 ID 已存在"):
        registry.create_tool(_tool("duplicate", "agent"))


def test_directory_replace_retries_transient_windows_permission_error(
    tmp_path, monkeypatch
):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    original_replace = Path.replace
    attempts = 0

    def flaky_replace(self, destination):
        nonlocal attempts
        if self == source and attempts < 2:
            attempts += 1
            raise PermissionError(5, "transient directory lock")
        return original_replace(self, destination)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    replaced = _replace_path(source, target)

    assert attempts == 2
    assert replaced == target
    assert target.is_dir()
