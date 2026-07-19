import json

import pytest

from scripts.migrate_tool_registry import MigrationError, migrate_registry


def _legacy_tool(tool_id: str, tool_type: str = "script") -> dict:
    return {
        "schema_version": 1,
        "id": tool_id,
        "type": tool_type,
        "name": "迁移工具",
        "description": "说明",
        "code": "print('migrated')",
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
        "updated_at": "2026-07-19T10:01:00",
    }


def _write_legacy(root, data: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{data['id']}.tool.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def test_migration_preserves_all_fields_and_removes_legacy_files(tmp_path):
    root = tmp_path / "tool_registry"
    script = _legacy_tool("script-one")
    agent = _legacy_tool("agent-one", "agent")
    _write_legacy(root, script)
    _write_legacy(root, agent)

    result = migrate_registry(root)

    assert result.migrated == 2
    assert result.tool_ids == ("agent-one", "script-one")
    assert list(root.glob("*.tool.json")) == []
    for expected in (script, agent):
        directory = root / expected["id"]
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        code = (directory / "main.py").read_text(encoding="utf-8")
        assert manifest == {key: value for key, value in expected.items() if key != "code"}
        assert code == expected["code"]

    repeated = migrate_registry(root)
    assert repeated.migrated == 0


def test_migration_parse_failure_keeps_every_legacy_file(tmp_path):
    root = tmp_path / "tool_registry"
    _write_legacy(root, _legacy_tool("valid"))
    (root / "broken.tool.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(MigrationError, match="broken.tool.json: JSON 格式错误"):
        migrate_registry(root)

    assert (root / "valid.tool.json").is_file()
    assert (root / "broken.tool.json").is_file()
    assert not (root / "valid").exists()


def test_migration_rejects_mixed_old_and_new_storage(tmp_path):
    root = tmp_path / "tool_registry"
    _write_legacy(root, _legacy_tool("legacy"))
    existing = root / "existing"
    existing.mkdir()
    (existing / "manifest.json").write_text("{}", encoding="utf-8")
    (existing / "main.py").write_text("", encoding="utf-8")

    with pytest.raises(MigrationError, match="拒绝混合迁移"):
        migrate_registry(root)

    assert (root / "legacy.tool.json").is_file()
    assert existing.is_dir()
