"""将旧的单文件工具仓储一次性迁移为 manifest.json + main.py 目录。"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web.tool_registry import ToolRecord, ToolRegistry, ToolRegistryError


LEGACY_SUFFIX = ".tool.json"
DEFAULT_REGISTRY_ROOT = PROJECT_ROOT / "tool_registry"


@dataclass(frozen=True)
class MigrationResult:
    """一次迁移的可观测结果。"""

    migrated: int
    tool_ids: tuple[str, ...]


class MigrationError(Exception):
    """旧工具迁移失败。"""


def _read_legacy_tool(path: Path) -> ToolRecord:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise MigrationError(
            f"{path.name}: JSON 格式错误（第 {exc.lineno} 行，第 {exc.colno} 列）"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise MigrationError(f"{path.name}: 读取失败: {exc}") from exc
    try:
        record = ToolRecord.model_validate(data)
    except ValidationError as exc:
        raise MigrationError(f"{path.name}: 结构校验失败: {exc}") from exc
    expected_name = f"{record.id}{LEGACY_SUFFIX}"
    if path.name != expected_name:
        raise MigrationError(f"{path.name}: 文件名必须与 id 一致，应为 {expected_name}")
    return record


def _remove_staging_directory(path: Path, expected_parent: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != expected_parent.resolve() or not resolved.name.startswith(
        ".tool_registry_migration_"
    ):
        raise MigrationError("迁移暂存目录超出预期范围")
    if resolved.exists():
        shutil.rmtree(resolved)


def migrate_registry(root: Path = DEFAULT_REGISTRY_ROOT) -> MigrationResult:
    """迁移全部旧文件；验证完成前不删除任何旧数据。"""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    legacy_paths = sorted(root.glob(f"*{LEGACY_SUFFIX}"))
    if not legacy_paths:
        return MigrationResult(migrated=0, tool_ids=())

    existing_directories = [
        path
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    ]
    if existing_directories:
        names = ", ".join(path.name for path in sorted(existing_directories))
        raise MigrationError(f"同时存在旧 JSON 和新工具目录，拒绝混合迁移: {names}")

    records = [_read_legacy_tool(path) for path in legacy_paths]
    ids = [record.id for record in records]
    if len(ids) != len(set(ids)):
        raise MigrationError("旧工具文件中存在重复 ID")

    staging = root.parent / f".tool_registry_migration_{uuid4().hex}"
    moved_directories: list[Path] = []
    renamed_legacy: list[tuple[Path, Path]] = []
    completed = False
    can_rollback = True
    try:
        staging_registry = ToolRegistry(staging)
        for record in records:
            staging_registry.create_tool(record.model_dump())

        staged = {tool["id"]: tool for tool in staging_registry.list_tools()}
        expected = {record.id: record.model_dump() for record in records}
        if staged != expected:
            raise MigrationError("暂存目录回读结果与旧工具不一致")

        for record in records:
            source = staging / record.id
            target = root / record.id
            if target.exists():
                raise MigrationError(f"目标工具目录已存在: {record.id}")
            source.replace(target)
            moved_directories.append(target)

        migrated_registry = ToolRegistry(root)
        result = migrated_registry.refresh()
        migrated = {tool["id"]: tool for tool in migrated_registry.list_tools()}
        if result.errors or migrated != expected:
            raise MigrationError("目标目录回读验证失败")

        for path in legacy_paths:
            backup = root / f".{path.name}.{uuid4().hex}.migration-old"
            path.replace(backup)
            renamed_legacy.append((path, backup))

        can_rollback = False
        for _, backup in renamed_legacy:
            backup.unlink()
        renamed_legacy.clear()
        completed = True
        return MigrationResult(migrated=len(records), tool_ids=tuple(sorted(ids)))
    except (OSError, ToolRegistryError) as exc:
        raise MigrationError(f"迁移写入失败: {exc}") from exc
    finally:
        if not completed and can_rollback:
            for original, backup in reversed(renamed_legacy):
                if backup.exists() and not original.exists():
                    backup.replace(original)
            for path in reversed(moved_directories):
                if path.exists():
                    shutil.rmtree(path)
        if staging.exists():
            _remove_staging_directory(staging, root.parent)


def main() -> None:
    result = migrate_registry()
    if result.migrated == 0:
        print("没有需要迁移的旧工具文件。")
        return
    print(f"迁移完成：{result.migrated} 个工具。")
    for tool_id in result.tool_ids:
        print(f"- {tool_id}")


if __name__ == "__main__":
    main()
