"""Four-type tool template models and directory repository."""

from __future__ import annotations

import json
import re
import shutil
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)


SCHEMA_VERSION = 1
MANIFEST_FILENAME = "manifest.json"
DEFINITION_FILENAME = "definition.json"
MAIN_FILENAME = "main.py"
TEMPLATE_TYPES = {"HTTP", "AGENT", "LLM", "SCRIPT"}
PYTHON_TEMPLATE_TYPES = {"AGENT", "LLM", "SCRIPT"}
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _validate_json(value: Any, field_name: str) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{field_name} 必须是合法 JSON: {exc}") from exc
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TemplateManifest(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    id: str
    type: Literal["HTTP", "AGENT", "LLM", "SCRIPT"]
    name: str
    description: str = ""
    created_at: str
    updated_at: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not _ID_PATTERN.fullmatch(normalized):
            raise ValueError("仅允许 1-128 位字母、数字、下划线或连字符")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("不能为空")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()


class TemplateField(StrictModel):
    name: str
    type: Literal["STRING", "NUMBER", "INTEGER", "BOOLEAN", "JSON"] = "JSON"
    required: bool = False
    description: str = ""
    example: Any = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not _FIELD_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("必须是合法的字段标识符")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("example")
    @classmethod
    def validate_example(cls, value: Any) -> Any:
        return _validate_json(value, "example")


class DefinitionBase(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    inputs: list[TemplateField] = Field(default_factory=list)
    outputs: list[TemplateField] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json(value, "config")

    @model_validator(mode="after")
    def validate_unique_fields(self):
        for label, fields in (("inputs", self.inputs), ("outputs", self.outputs)):
            names = [field.name for field in fields]
            if len(names) != len(set(names)):
                raise ValueError(f"{label} 字段名称不能重复")
        return self


class HttpConfig(StrictModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)
    body_type: Literal["NONE", "FORM_DATA", "FORM_URLENCODED", "RAW", "BINARY"] = "NONE"
    body: Any = None

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: Any) -> Any:
        return _validate_json(value, "HTTP body")


class HttpDefinition(DefinitionBase):
    type: Literal["HTTP"]
    execution_mode: Literal["CONFIG", "CODE"] = "CONFIG"
    http: HttpConfig = Field(default_factory=HttpConfig)


class AgentDefinition(DefinitionBase):
    type: Literal["AGENT"]


class LlmDefinition(DefinitionBase):
    type: Literal["LLM"]


class ScriptDefinition(DefinitionBase):
    type: Literal["SCRIPT"]


TemplateDefinition = Annotated[
    HttpDefinition | AgentDefinition | LlmDefinition | ScriptDefinition,
    Field(discriminator="type"),
]
_DEFINITION_ADAPTER = TypeAdapter(TemplateDefinition)


class ToolTemplate(StrictModel):
    manifest: TemplateManifest
    definition: TemplateDefinition
    main_py: str | None = None

    @model_validator(mode="after")
    def validate_package(self):
        if self.manifest.type != self.definition.type:
            raise ValueError("manifest.type 必须与 definition.type 一致")
        if self.manifest.type in PYTHON_TEMPLATE_TYPES and self.main_py is None:
            raise ValueError(f"{self.manifest.type} 模板必须包含 main.py")
        if (
            self.manifest.type == "HTTP"
            and self.definition.execution_mode == "CODE"
            and self.main_py is None
        ):
            raise ValueError("HTTP CODE 模式必须包含 main.py")
        return self


class TemplateRepositoryError(RuntimeError):
    pass


def _format_validation_error(exc: ValidationError) -> str:
    messages = []
    for item in exc.errors(include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "文件"
        messages.append(f"{location}: {item['msg']}")
    return "；".join(messages)


def parse_template_package(
    manifest_content: str,
    definition_content: str,
    main_py: str | None,
    *,
    expected_id: str | None = None,
) -> ToolTemplate:
    try:
        manifest_data = json.loads(manifest_content)
        definition_data = json.loads(definition_content)
    except json.JSONDecodeError as exc:
        raise TemplateRepositoryError(
            f"JSON 格式错误（第 {exc.lineno} 行，第 {exc.colno} 列）: {exc.msg}"
        ) from exc
    try:
        template = ToolTemplate(
            manifest=TemplateManifest.model_validate(manifest_data),
            definition=_DEFINITION_ADAPTER.validate_python(definition_data),
            main_py=main_py,
        )
    except ValidationError as exc:
        raise TemplateRepositoryError(_format_validation_error(exc)) from exc
    if expected_id is not None and template.manifest.id != expected_id:
        raise TemplateRepositoryError(
            f"目录名必须与模板 id 一致，应为 {template.manifest.id}"
        )
    return template


class ToolTemplateRepository:
    """Maintain an explicit-refresh snapshot of template directories."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._templates: dict[str, ToolTemplate] = {}
        self._lock = RLock()
        self._initialized = False

    def refresh(self) -> list[dict[str, str]]:
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            loaded: dict[str, ToolTemplate] = {}
            errors: list[dict[str, str]] = []
            for path in sorted(self.root.iterdir()):
                if not path.is_dir() or path.name.startswith("."):
                    continue
                try:
                    template = self._read_directory(path)
                except TemplateRepositoryError as exc:
                    errors.append({"directory": path.name, "error": str(exc)})
                    continue
                loaded[template.manifest.id] = template
            self._templates = loaded
            self._initialized = True
            return errors

    def list_templates(self) -> list[ToolTemplate]:
        with self._lock:
            self._ensure_initialized()
            return [template.model_copy(deep=True) for template in self._templates.values()]

    def get_template(self, template_id: str) -> ToolTemplate | None:
        with self._lock:
            self._ensure_initialized()
            template = self._templates.get(template_id)
            return template.model_copy(deep=True) if template else None

    def create_template(self, template: ToolTemplate) -> ToolTemplate:
        with self._lock:
            self._ensure_initialized()
            template_id = template.manifest.id
            if template_id in self._templates or (self.root / template_id).exists():
                raise TemplateRepositoryError(f"工具模板 ID 已存在: {template_id}")
            self._write_directory(self.root / template_id, template)
            self._templates[template_id] = template.model_copy(deep=True)
            return template.model_copy(deep=True)

    def create_templates(self, templates: list[ToolTemplate]) -> list[ToolTemplate]:
        with self._lock:
            self._ensure_initialized()
            template_ids = [template.manifest.id for template in templates]
            if len(template_ids) != len(set(template_ids)):
                raise TemplateRepositoryError("导入包中的工具模板 ID 不能重复")
            conflicts = [
                template_id
                for template_id in template_ids
                if template_id in self._templates or (self.root / template_id).exists()
            ]
            if conflicts:
                raise TemplateRepositoryError(
                    f"工具模板 ID 已存在: {', '.join(sorted(conflicts))}"
                )

            created_ids: list[str] = []
            try:
                for template in templates:
                    template_id = template.manifest.id
                    self._write_directory(self.root / template_id, template)
                    self._templates[template_id] = template.model_copy(deep=True)
                    created_ids.append(template_id)
            except Exception:
                for template_id in created_ids:
                    shutil.rmtree(self.root / template_id, ignore_errors=True)
                    self._templates.pop(template_id, None)
                raise
            return [template.model_copy(deep=True) for template in templates]

    def update_template(self, template_id: str, template: ToolTemplate) -> ToolTemplate:
        with self._lock:
            self._ensure_initialized()
            current = self._templates.get(template_id)
            if current is None:
                raise TemplateRepositoryError(f"工具模板不存在: {template_id}")
            if template.manifest.id != template_id:
                raise TemplateRepositoryError("工具模板 ID 不允许修改")
            if template.manifest.type != current.manifest.type:
                raise TemplateRepositoryError("工具模板类型不允许修改")
            self._write_directory(self.root / template_id, template)
            self._templates[template_id] = template.model_copy(deep=True)
            return template.model_copy(deep=True)

    def delete_template(self, template_id: str) -> ToolTemplate | None:
        with self._lock:
            self._ensure_initialized()
            template = self._templates.get(template_id)
            if template is None:
                return None
            shutil.rmtree(self.root / template_id)
            self._templates.pop(template_id, None)
            return template.model_copy(deep=True)

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.refresh()

    def _read_directory(self, path: Path) -> ToolTemplate:
        manifest_path = path / MANIFEST_FILENAME
        definition_path = path / DEFINITION_FILENAME
        main_path = path / MAIN_FILENAME
        if not manifest_path.is_file():
            raise TemplateRepositoryError(f"缺少 {MANIFEST_FILENAME}")
        if not definition_path.is_file():
            raise TemplateRepositoryError(f"缺少 {DEFINITION_FILENAME}")
        try:
            manifest_content = manifest_path.read_text(encoding="utf-8-sig")
            definition_content = definition_path.read_text(encoding="utf-8-sig")
            main_py = main_path.read_text(encoding="utf-8") if main_path.is_file() else None
        except (OSError, UnicodeError) as exc:
            raise TemplateRepositoryError(f"读取失败: {exc}") from exc
        return parse_template_package(
            manifest_content, definition_content, main_py, expected_id=path.name
        )

    def _write_directory(self, path: Path, template: ToolTemplate) -> None:
        temporary = self.root / f".{template.manifest.id}.tmp"
        backup = self.root / f".{template.manifest.id}.bak"
        shutil.rmtree(temporary, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
        temporary.mkdir(parents=True)
        try:
            (temporary / MANIFEST_FILENAME).write_text(
                json.dumps(template.manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (temporary / DEFINITION_FILENAME).write_text(
                json.dumps(template.definition.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            if template.main_py is not None:
                (temporary / MAIN_FILENAME).write_text(template.main_py, encoding="utf-8")
            if path.exists():
                path.replace(backup)
            temporary.replace(path)
            shutil.rmtree(backup, ignore_errors=True)
        except OSError as exc:
            if backup.exists() and not path.exists():
                backup.replace(path)
            raise TemplateRepositoryError(f"写入工具模板失败: {exc}") from exc
        finally:
            shutil.rmtree(temporary, ignore_errors=True)


def template_to_dict(template: ToolTemplate) -> dict[str, Any]:
    return deepcopy(template.model_dump(mode="json"))
