"""基于 manifest.json + main.py 目录的工具仓储与内存快照。"""

from __future__ import annotations

import json
import re
import shutil
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


SCHEMA_VERSION = 1
MANIFEST_FILENAME = "manifest.json"
MAIN_FILENAME = "main.py"
TOOL_TYPES = {"script", "agent"}
AGENT_PARAMETER_NAMES = {
    "model",
    "model_provider",
    "api_key",
    "base_url",
    "system_prompt",
    "human_message",
}
_TOOL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_REPLACE_RETRY_DELAYS = (0.02, 0.05, 0.1)


def _replace_path(source: Path, target: Path) -> Path:
    """缓解 Windows 杀毒或索引进程短暂占用目录导致的 WinError 5。"""
    for attempt in range(len(_REPLACE_RETRY_DELAYS) + 1):
        try:
            return source.replace(target)
        except PermissionError:
            if attempt == len(_REPLACE_RETRY_DELAYS):
                raise
            time.sleep(_REPLACE_RETRY_DELAYS[attempt])
    raise RuntimeError("目录替换重试未产生结果")


class ToolManifest(BaseModel):
    """工具目录中的 manifest.json 结构。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    id: str
    type: Literal["script", "agent"]
    name: str
    description: str = ""
    parameters: dict[str, str] = Field(default_factory=dict)
    output_example: Any = None
    created_at: str = ""
    updated_at: str = ""

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        """限制 ID 字符，确保它可以安全地用作目录名。"""
        normalized = value.strip()
        if not _TOOL_ID_PATTERN.fullmatch(normalized):
            raise ValueError("仅允许 1-128 位字母、数字、下划线或连字符")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """名称只要求非空，允许不同工具使用相同名称。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("不能为空")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        """清理说明两端的空白。"""
        return value.strip()

    @model_validator(mode="after")
    def validate_parameters(self) -> ToolManifest:
        """校验当前两类工具支持的参数定义。"""
        if self.type == "script" and self.parameters:
            raise ValueError("Script 工具的 parameters 必须为空对象")
        unknown = set(self.parameters) - AGENT_PARAMETER_NAMES
        if unknown:
            raise ValueError(f"parameters 包含未知字段: {', '.join(sorted(unknown))}")
        return self

    @field_validator("output_example")
    @classmethod
    def validate_output_example(cls, value: Any) -> Any:
        try:
            json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError(f"output_example 必须是合法 JSON: {exc}") from exc
        return value


class ToolRecord(ToolManifest):
    """仓储内部使用的完整工具结构，代码来自 main.py。"""

    code: str = ""
    output_example_configured: bool = False

    @model_validator(mode="before")
    @classmethod
    def infer_output_example_presence(cls, value):
        if isinstance(value, dict) and "output_example_configured" not in value:
            value = {
                **value,
                "output_example_configured": "output_example" in value,
            }
        return value


@dataclass(frozen=True)
class RegistryError:
    """刷新时单个工具目录的校验错误。"""

    file: str
    error: str


@dataclass(frozen=True)
class RefreshResult:
    """一次目录刷新产生的有效快照和错误。"""

    loaded: int
    errors: tuple[RegistryError, ...]


class ToolRegistryError(Exception):
    """工具仓储操作失败。"""


def _format_validation_error(exc: ValidationError) -> str:
    """将 Pydantic 错误压缩成适合页面展示的字段信息。"""
    messages: list[str] = []
    for item in exc.errors(include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "文件"
        messages.append(f"{location}: {item['msg']}")
    return "；".join(messages)


def manifest_from_record(data: dict) -> dict:
    """从包含 code 的完整工具结构生成 manifest 数据。"""
    try:
        record = ToolRecord.model_validate(data)
    except ValidationError as exc:
        raise ToolRegistryError(_format_validation_error(exc)) from exc
    manifest = record.model_dump(exclude={"code", "output_example_configured"})
    if not record.output_example_configured:
        manifest.pop("output_example", None)
    return manifest


def parse_tool_package(
    manifest_content: str,
    code: str,
    expected_id: str | None = None,
) -> ToolRecord:
    """解析目录或 ZIP 中的一组 manifest.json 与 main.py。"""
    try:
        data = json.loads(manifest_content)
    except json.JSONDecodeError as exc:
        raise ToolRegistryError(
            f"JSON 格式错误（第 {exc.lineno} 行，第 {exc.colno} 列）: {exc.msg}"
        ) from exc
    try:
        manifest = ToolManifest.model_validate(data)
        record = ToolRecord.model_validate(
            {
                **manifest.model_dump(),
                "code": code,
                "output_example_configured": "output_example" in data,
            }
        )
    except ValidationError as exc:
        raise ToolRegistryError(_format_validation_error(exc)) from exc
    if expected_id is not None and record.id != expected_id:
        raise ToolRegistryError(f"目录名必须与 id 一致，应为 {record.id}")
    return record


class ToolRegistry:
    """维护工具目录与显式刷新生效的进程内快照。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._tools: dict[str, ToolRecord] = {}
        self._paths: dict[str, Path] = {}
        self._lock = RLock()
        self._initialized = False

    def ensure_directories(self) -> None:
        """创建统一工具仓储目录。"""
        self.root.mkdir(parents=True, exist_ok=True)

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.refresh()

    def _expected_directory(self, tool: ToolRecord) -> Path:
        return self.root / tool.id

    def _read_tool_directory(self, path: Path) -> ToolRecord:
        manifest_path = path / MANIFEST_FILENAME
        main_path = path / MAIN_FILENAME
        if not manifest_path.is_file():
            raise ToolRegistryError(f"缺少 {MANIFEST_FILENAME}")
        if not main_path.is_file():
            raise ToolRegistryError(f"缺少 {MAIN_FILENAME}")
        try:
            manifest_content = manifest_path.read_text(encoding="utf-8-sig")
            code = main_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ToolRegistryError(f"读取失败: {exc}") from exc

        return parse_tool_package(manifest_content, code, expected_id=path.name)

    def refresh(self) -> RefreshResult:
        """重新扫描一级工具目录，并以所有有效目录替换当前快照。"""
        with self._lock:
            self.ensure_directories()
            tools: dict[str, ToolRecord] = {}
            paths: dict[str, Path] = {}
            errors: list[RegistryError] = []
            candidates = [
                path
                for path in sorted(self.root.iterdir())
                if path.is_dir() and not path.name.startswith(".")
            ]
            for path in candidates:
                relative_path = path.relative_to(self.root).as_posix()
                try:
                    tool = self._read_tool_directory(path)
                except ToolRegistryError as exc:
                    errors.append(RegistryError(file=relative_path, error=str(exc)))
                    continue
                tools[tool.id] = tool
                paths[tool.id] = path
            self._tools = tools
            self._paths = paths
            self._initialized = True
            return RefreshResult(loaded=len(tools), errors=tuple(errors))

    def list_tools(self) -> list[dict]:
        """返回与内部快照隔离的工具列表。"""
        with self._lock:
            self._ensure_initialized()
            return [deepcopy(tool.model_dump()) for tool in self._tools.values()]

    def get_tool(self, tool_id: str) -> dict | None:
        """按 ID 读取快照中的工具。"""
        with self._lock:
            self._ensure_initialized()
            tool = self._tools.get(tool_id)
            return deepcopy(tool.model_dump()) if tool else None

    def get_tool_directory(self, tool_id: str) -> Path | None:
        """返回指定工具的目录路径。"""
        with self._lock:
            self._ensure_initialized()
            path = self._paths.get(tool_id)
            return Path(path) if path else None

    def create_tool(self, data: dict) -> dict:
        """创建一个工具目录并立即更新快照。"""
        try:
            tool = ToolRecord.model_validate(data)
        except ValidationError as exc:
            raise ToolRegistryError(_format_validation_error(exc)) from exc
        with self._lock:
            self._ensure_initialized()
            if tool.id in self._tools:
                raise ToolRegistryError(f"工具 ID 已存在: {tool.id}")
            path = self._expected_directory(tool)
            if path.exists():
                raise ToolRegistryError(f"工具目录已存在: {path.name}")
            self._write_tool_directory(path, tool)
            self._tools[tool.id] = tool
            self._paths[tool.id] = path
            return deepcopy(tool.model_dump())

    def update_tool(self, tool_id: str, data: dict) -> dict:
        """整体替换指定 ID 工具目录并立即更新快照。"""
        try:
            tool = ToolRecord.model_validate(data)
        except ValidationError as exc:
            raise ToolRegistryError(_format_validation_error(exc)) from exc
        if tool.id != tool_id:
            raise ToolRegistryError("工具 ID 不允许修改")
        with self._lock:
            self._ensure_initialized()
            current = self._tools.get(tool_id)
            if current is None:
                raise ToolRegistryError(f"工具不存在: {tool_id}")
            if current.type != tool.type:
                raise ToolRegistryError("工具类型不允许修改")
            path = self._paths[tool_id]
            self._write_tool_directory(path, tool)
            self._tools[tool_id] = tool
            return deepcopy(tool.model_dump())

    def delete_tool(self, tool_id: str) -> dict | None:
        """删除指定工具目录并立即移出快照。"""
        with self._lock:
            self._ensure_initialized()
            tool = self._tools.get(tool_id)
            if tool is None:
                return None
            path = self._paths[tool_id]
            try:
                self._remove_directory(path)
            except OSError as exc:
                raise ToolRegistryError(f"删除工具目录失败: {exc}") from exc
            self._tools.pop(tool_id, None)
            self._paths.pop(tool_id, None)
            return deepcopy(tool.model_dump())

    def _remove_directory(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved.parent != self.root.resolve():
            raise OSError("工具目录超出仓储范围")
        shutil.rmtree(resolved)

    def _write_directory_contents(self, path: Path, tool: ToolRecord) -> None:
        path.mkdir()
        manifest = manifest_from_record(tool.model_dump())
        (path / MANIFEST_FILENAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (path / MAIN_FILENAME).write_text(tool.code, encoding="utf-8")

    def _write_tool_directory(self, path: Path, tool: ToolRecord) -> None:
        """先写临时目录，再以目录替换完成一次工具更新。"""
        self.ensure_directories()
        temporary = self.root / f".{tool.id}.{uuid4().hex}.tmp"
        backup = self.root / f".{tool.id}.{uuid4().hex}.bak"
        replaced_current = False
        try:
            self._write_directory_contents(temporary, tool)
            if path.exists():
                _replace_path(path, backup)
                replaced_current = True
            _replace_path(temporary, path)
        except OSError as exc:
            if replaced_current and not path.exists() and backup.exists():
                _replace_path(backup, path)
            raise ToolRegistryError(f"写入工具目录失败: {exc}") from exc
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
