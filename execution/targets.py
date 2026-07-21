"""Target configuration models and standalone SQLite repository."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "run_storage" / "agent_bench.sqlite3"
)
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_INITIALIZE_LOCKS_GUARD = threading.Lock()
_INITIALIZE_LOCKS: dict[Path, threading.Lock] = {}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class TargetHttpMethod(str, Enum):
    POST = "POST"


class _TargetModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class TargetConfiguration(_TargetModel):
    name: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    path: str = Field(min_length=1)
    method: TargetHttpMethod = TargetHttpMethod.POST
    headers: dict[str, str] = Field(default_factory=dict)
    target_total_concurrency: int = Field(strict=True, ge=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Target 名称不能为空")
        return normalized

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip()
        if any(character.isspace() for character in normalized):
            raise ValueError("Base URL 不能包含空白字符")
        parsed = urlsplit(normalized)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Base URL 必须是完整的 HTTP 或 HTTPS 地址")
        if parsed.query or parsed.fragment:
            raise ValueError("Base URL 不能包含 query 或 fragment")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("Base URL 端口无效") from exc
        return normalized

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/") or normalized.startswith("//"):
            raise ValueError("Target Path 必须以单个 / 开头")
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ValueError("Target Path 不能包含控制字符")
        parsed = urlsplit(normalized)
        if parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Target Path 只能包含 URL 路径")
        return normalized

    @field_validator("headers", mode="before")
    @classmethod
    def validate_headers(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError("Headers 必须是 JSON 对象")
        normalized: dict[str, str] = {}
        for name, header_value in value.items():
            if not isinstance(name, str) or not _HEADER_NAME.fullmatch(name):
                raise ValueError(f"Header 名称无效: {name}")
            if not isinstance(header_value, str):
                raise ValueError(f"Header 值必须是字符串: {name}")
            if any(character in header_value for character in ("\r", "\n", "\x00")):
                raise ValueError(f"Header 值包含非法控制字符: {name}")
            try:
                header_value.encode("ascii")
            except UnicodeEncodeError as exc:
                raise ValueError(f"Header 值必须是 ASCII 字符: {name}") from exc
            normalized[name] = header_value
        return normalized


class TargetRecord(TargetConfiguration):
    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class TargetRepositoryError(RuntimeError):
    pass


def _initialize_lock_for(database_path: Path) -> threading.Lock:
    with _INITIALIZE_LOCKS_GUARD:
        return _INITIALIZE_LOCKS.setdefault(database_path, threading.Lock())


class TargetRepository:
    """Persist only Target records; legacy Workflow and Run tables are ignored."""

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
                    CREATE TABLE IF NOT EXISTS targets (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        base_url TEXT NOT NULL,
                        path TEXT NOT NULL,
                        method TEXT NOT NULL,
                        headers_json TEXT NOT NULL,
                        target_total_concurrency INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.commit()
            self._initialized = True

    def create_target(self, record: TargetRecord) -> TargetRecord:
        values = record.model_dump(mode="json")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO targets(
                        id, name, base_url, path, method, headers_json,
                        target_total_concurrency, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values["id"], values["name"], values["base_url"],
                        values["path"], values["method"],
                        json.dumps(values["headers"], ensure_ascii=False),
                        values["target_total_concurrency"], values["created_at"],
                        values["updated_at"],
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise TargetRepositoryError(f"写入 Target 失败: {exc}") from exc
        return record

    def get_target(self, target_id: str) -> TargetRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM targets WHERE id = ?", (target_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def list_targets(self) -> list[TargetRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM targets ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def update_target(self, record: TargetRecord) -> TargetRecord:
        values = record.model_dump(mode="json")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE targets SET name = ?, base_url = ?, path = ?, method = ?,
                    headers_json = ?, target_total_concurrency = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    values["name"], values["base_url"], values["path"],
                    values["method"], json.dumps(values["headers"], ensure_ascii=False),
                    values["target_total_concurrency"], values["updated_at"], record.id,
                ),
            )
            connection.commit()
        if cursor.rowcount == 0:
            raise TargetRepositoryError(f"Target 不存在: {record.id}")
        return record

    def delete_target(self, target_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM targets WHERE id = ?", (target_id,))
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
    def _from_row(row: sqlite3.Row) -> TargetRecord:
        return TargetRecord(
            id=row["id"], name=row["name"], base_url=row["base_url"],
            path=row["path"], method=row["method"],
            headers=json.loads(row["headers_json"]),
            target_total_concurrency=row["target_total_concurrency"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
