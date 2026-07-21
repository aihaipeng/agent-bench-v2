"""Model provider configuration models and SQLite repository."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from execution.targets import DEFAULT_DATABASE_PATH


_INITIALIZE_LOCKS_GUARD = threading.Lock()
_INITIALIZE_LOCKS: dict[Path, threading.Lock] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ModelProviderProtocol(str, Enum):
    OPENAI_COMPATIBLE = "OPENAI_COMPATIBLE"
    ANTHROPIC = "ANTHROPIC"
    MANUAL = "MANUAL"


class _ModelProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ModelProviderConfiguration(_ModelProviderModel):
    name: str | None = Field(default=None, max_length=120)
    website_url: str | None = Field(default=None, max_length=2048)
    api_key: str = Field(min_length=1, max_length=4096)
    base_url: str = Field(min_length=1, max_length=2048)
    protocol: ModelProviderProtocol
    model_endpoint: str | None = Field(default=None, max_length=2048)
    models: list[str] = Field(min_length=1, max_length=500)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("website_url", "model_endpoint", mode="before")
    @classmethod
    def normalize_optional_url(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().rstrip("/")
        if not normalized:
            return None
        return _validate_http_url(normalized, "URL")

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("API Key 不能为空")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return _validate_http_url(value.strip().rstrip("/"), "BASE_URL")

    @field_validator("models", mode="before")
    @classmethod
    def normalize_models(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("模型必须是数组")
        models: list[str] = []
        seen: set[str] = set()
        for raw_model in value:
            if not isinstance(raw_model, str):
                raise ValueError("模型名称必须是字符串")
            model = raw_model.strip()
            if not model:
                raise ValueError("模型名称不能为空")
            if len(model) > 200:
                raise ValueError("模型名称不能超过 200 个字符")
            if model not in seen:
                seen.add(model)
                models.append(model)
        if not models:
            raise ValueError("至少添加一个模型")
        return models


class ModelProviderRecord(ModelProviderConfiguration):
    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)


class ModelProviderSummary(_ModelProviderModel):
    id: str
    name: str | None
    website_url: str | None
    base_url: str
    protocol: ModelProviderProtocol
    model_endpoint: str | None
    models: list[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: ModelProviderRecord) -> "ModelProviderSummary":
        return cls(**record.model_dump(mode="json", exclude={"api_key"}))


class ModelProviderRepositoryError(RuntimeError):
    pass


def _validate_http_url(value: str, label: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} 必须是有效的 HTTP 或 HTTPS 地址")
    if parsed.username or parsed.password:
        raise ValueError(f"{label} 不能包含用户名或密码")
    if parsed.fragment:
        raise ValueError(f"{label} 不能包含 fragment")
    if parsed.query:
        raise ValueError(f"{label} 不能包含 query")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} 端口无效") from exc
    return value


def _initialize_lock_for(database_path: Path) -> threading.Lock:
    with _INITIALIZE_LOCKS_GUARD:
        return _INITIALIZE_LOCKS.setdefault(database_path, threading.Lock())


class ModelProviderRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH):
        self.database_path = Path(database_path).resolve()
        self._initialize_lock = _initialize_lock_for(self.database_path)
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._initialize_lock:
            if self._initialized:
                return
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect(initialize=False) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS model_providers (
                        id TEXT PRIMARY KEY,
                        name TEXT,
                        website_url TEXT,
                        api_key TEXT NOT NULL,
                        base_url TEXT NOT NULL,
                        protocol TEXT NOT NULL,
                        model_endpoint TEXT,
                        models_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.commit()
            self._initialized = True

    def create(self, record: ModelProviderRecord) -> ModelProviderRecord:
        values = record.model_dump(mode="json")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO model_providers(
                        id, name, website_url, api_key, base_url, protocol,
                        model_endpoint, models_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values["id"], values["name"], values["website_url"],
                        values["api_key"], values["base_url"], values["protocol"],
                        values["model_endpoint"],
                        json.dumps(values["models"], ensure_ascii=False),
                        values["created_at"], values["updated_at"],
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ModelProviderRepositoryError(f"写入模型供应商失败: {exc}") from exc
        return record

    def get(self, provider_id: str) -> ModelProviderRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM model_providers WHERE id = ?", (provider_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def list(self) -> list[ModelProviderRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM model_providers ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def update(self, record: ModelProviderRecord) -> ModelProviderRecord:
        values = record.model_dump(mode="json")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE model_providers
                SET name = ?, website_url = ?, api_key = ?, base_url = ?,
                    protocol = ?, model_endpoint = ?, models_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    values["name"], values["website_url"], values["api_key"],
                    values["base_url"], values["protocol"], values["model_endpoint"],
                    json.dumps(values["models"], ensure_ascii=False),
                    values["updated_at"], values["id"],
                ),
            )
            connection.commit()
        if cursor.rowcount == 0:
            raise ModelProviderRepositoryError(f"模型供应商不存在: {record.id}")
        return record

    def delete(self, provider_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM model_providers WHERE id = ?", (provider_id,)
            )
            connection.commit()
        return cursor.rowcount > 0

    @contextmanager
    def _connect(self, *, initialize: bool = True):
        if initialize:
            self.initialize()
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ModelProviderRecord:
        return ModelProviderRecord(
            id=row["id"], name=row["name"], website_url=row["website_url"],
            api_key=row["api_key"], base_url=row["base_url"],
            protocol=row["protocol"], model_endpoint=row["model_endpoint"],
            models=json.loads(row["models_json"]), created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
