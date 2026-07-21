"""Safe ZIP import and export for tool templates."""

from __future__ import annotations

import io
import json
import stat
import zipfile
from collections import defaultdict
from pathlib import PurePosixPath

from web.tool_templates import (
    DEFINITION_FILENAME,
    MAIN_FILENAME,
    MANIFEST_FILENAME,
    ToolTemplate,
    TemplateRepositoryError,
    parse_template_package,
)


MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 300
MAX_COMPRESSION_RATIO = 200
_PACKAGE_FILENAMES = {MANIFEST_FILENAME, DEFINITION_FILENAME, MAIN_FILENAME}


def _validate_member(info: zipfile.ZipInfo) -> tuple[str, str] | None:
    name = info.filename
    if not name or "\\" in name:
        raise TemplateRepositoryError(f"ZIP 路径无效: {name or '<empty>'}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise TemplateRepositoryError(f"ZIP 路径越界: {name}")
    if info.flag_bits & 0x1:
        raise TemplateRepositoryError(f"不支持加密 ZIP 条目: {name}")
    file_mode = (info.external_attr >> 16) & 0o170000
    if file_mode == stat.S_IFLNK:
        raise TemplateRepositoryError(f"ZIP 不允许符号链接: {name}")
    if info.file_size > MAX_UNCOMPRESSED_BYTES:
        raise TemplateRepositoryError(f"ZIP 条目过大: {name}")
    if (
        info.compress_size > 0
        and info.file_size > 1024 * 1024
        and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
    ):
        raise TemplateRepositoryError(f"ZIP 条目压缩比异常: {name}")
    if info.is_dir():
        return None
    if len(path.parts) != 2 or path.parts[1] not in _PACKAGE_FILENAMES:
        raise TemplateRepositoryError(
            f"ZIP 只允许 {{id}}/manifest.json、definition.json 和可选 main.py: {name}"
        )
    return path.parts[0], path.parts[1]


def parse_template_archive(content: bytes) -> list[ToolTemplate]:
    if not content:
        raise TemplateRepositoryError("ZIP 文件为空")
    if len(content) > MAX_ARCHIVE_BYTES:
        raise TemplateRepositoryError("ZIP 文件超过 20 MB 限制")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content), "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise TemplateRepositoryError(f"无效 ZIP 文件: {exc}") from exc

    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise TemplateRepositoryError("ZIP 条目数量超过 300 个限制")
        total_size = sum(info.file_size for info in entries)
        if total_size > MAX_UNCOMPRESSED_BYTES:
            raise TemplateRepositoryError("ZIP 解压后超过 50 MB 限制")

        packages: dict[str, dict[str, bytes]] = defaultdict(dict)
        seen_paths: set[str] = set()
        for info in entries:
            member = _validate_member(info)
            if member is None:
                continue
            if info.filename in seen_paths:
                raise TemplateRepositoryError(f"ZIP 包含重复路径: {info.filename}")
            seen_paths.add(info.filename)
            template_id, filename = member
            if filename in packages[template_id]:
                raise TemplateRepositoryError(
                    f"模板 {template_id} 包含重复文件: {filename}"
                )
            try:
                packages[template_id][filename] = archive.read(info)
            except (RuntimeError, OSError, zipfile.BadZipFile) as exc:
                raise TemplateRepositoryError(f"读取 ZIP 条目失败: {info.filename}") from exc

    if not packages:
        raise TemplateRepositoryError("ZIP 中没有工具模板")

    templates: list[ToolTemplate] = []
    for template_id in sorted(packages):
        files = packages[template_id]
        if MANIFEST_FILENAME not in files:
            raise TemplateRepositoryError(f"模板 {template_id} 缺少 {MANIFEST_FILENAME}")
        if DEFINITION_FILENAME not in files:
            raise TemplateRepositoryError(f"模板 {template_id} 缺少 {DEFINITION_FILENAME}")
        try:
            manifest_content = files[MANIFEST_FILENAME].decode("utf-8-sig")
            definition_content = files[DEFINITION_FILENAME].decode("utf-8-sig")
            main_py = (
                files[MAIN_FILENAME].decode("utf-8")
                if MAIN_FILENAME in files
                else None
            )
        except UnicodeDecodeError as exc:
            raise TemplateRepositoryError(
                f"模板 {template_id} 文件必须使用 UTF-8 编码"
            ) from exc
        templates.append(
            parse_template_package(
                manifest_content,
                definition_content,
                main_py,
                expected_id=template_id,
            )
        )
    return templates


def _json_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def build_template_archive(templates: list[ToolTemplate]) -> bytes:
    if not templates:
        raise TemplateRepositoryError("没有可导出的工具模板")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for template in sorted(templates, key=lambda item: item.manifest.id):
            template_id = template.manifest.id
            archive.writestr(
                f"{template_id}/{MANIFEST_FILENAME}",
                _json_bytes(template.manifest.model_dump(mode="json")),
            )
            archive.writestr(
                f"{template_id}/{DEFINITION_FILENAME}",
                _json_bytes(template.definition.model_dump(mode="json")),
            )
            if template.main_py is not None:
                archive.writestr(f"{template_id}/{MAIN_FILENAME}", template.main_py)
    return buffer.getvalue()
