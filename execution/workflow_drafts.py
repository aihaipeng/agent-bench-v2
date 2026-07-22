"""Persistent Workflow Studio drafts and per-node run history."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from execution.targets import DEFAULT_DATABASE_PATH, utc_now_iso
from execution.workflow_variables import validate_visible_variable_names


_INITIALIZE_LOCKS_GUARD = threading.Lock()
_INITIALIZE_LOCKS: dict[Path, threading.Lock] = {}
NODE_RUN_HISTORY_LIMIT = 10


class _WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class WorkflowDraftConfiguration(_WorkflowModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    nodes: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)
    edges: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    global_variables: list[dict[str, Any]] = Field(default_factory=list, max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Workflow 名称不能为空")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_graph_identity(self):
        node_ids: set[str] = set()
        for node in self.nodes:
            node_id = node.get("id")
            if not isinstance(node_id, str) or not node_id.strip():
                raise ValueError("Workflow 节点必须包含非空 id")
            if node_id in node_ids:
                raise ValueError(f"Workflow 节点 id 重复: {node_id}")
            if not isinstance(node.get("data"), dict):
                raise ValueError(f"Workflow 节点 data 必须是对象: {node_id}")
            node_ids.add(node_id)
        edge_ids: set[str] = set()
        for edge in self.edges:
            edge_id = edge.get("id")
            if not isinstance(edge_id, str) or not edge_id.strip():
                raise ValueError("Workflow 连线必须包含非空 id")
            if edge_id in edge_ids:
                raise ValueError(f"Workflow 连线 id 重复: {edge_id}")
            source, target = edge.get("source"), edge.get("target")
            if source not in node_ids or target not in node_ids:
                raise ValueError(f"Workflow 连线引用不存在的节点: {edge_id}")
            edge_ids.add(edge_id)
        validate_visible_variable_names(self.nodes, self.edges, self.global_variables)
        return self


class WorkflowDraftRecord(WorkflowDraftConfiguration):
    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class WorkflowNodeRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


def validate_workflow_graph(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> None:
    """Validate a DAG while allowing implicit sources and sinks.

    This is intentionally separate from the Pydantic draft model so existing
    drafts can still be opened. Callers invoke it at save and execution time.
    """
    node_by_id = {node.get("id"): node for node in nodes}
    if not node_by_id:
        raise ValueError("Workflow 至少需要一个节点")
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_by_id}
    degree: dict[str, int] = {node_id: 0 for node_id in node_by_id}
    indegree: dict[str, int] = {node_id: 0 for node_id in node_by_id}
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source in adjacency and target in adjacency:
            if target not in adjacency[source]:
                adjacency[source].add(target)
                indegree[target] += 1
            degree[source] += 1
            degree[target] += 1
    orphaned = [] if len(nodes) == 1 else [
        node for node in nodes if degree[node["id"]] == 0
    ]
    if orphaned:
        labels = [
            str((node.get("data") or {}).get("label") or node["id"])
            for node in orphaned
        ]
        raise ValueError(f"Workflow 存在游离节点: {', '.join(labels)}")

    pending = [node_id for node_id, count in indegree.items() if count == 0]
    processed: set[str] = set()
    while pending:
        current = pending.pop()
        processed.add(current)
        for target in adjacency[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                pending.append(target)
    if len(processed) != len(nodes):
        labels = [
            str((node.get("data") or {}).get("label") or node["id"])
            for node in nodes if node["id"] not in processed
        ]
        raise ValueError(f"Workflow 存在循环依赖: {', '.join(labels)}")


class WorkflowNodeRunRecord(_WorkflowModel):
    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    workflow_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    status: WorkflowNodeRunStatus = WorkflowNodeRunStatus.RUNNING
    started_at: str = Field(default_factory=utc_now_iso)
    finished_at: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    provider_name: str = ""
    model_name: str = ""
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    request_body: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    output: Any = None
    stdout: str = ""
    stderr: str = ""
    console: str = ""
    response_body: str = ""
    output_variables: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    request_id: str | None = None


class WorkflowDraftRepositoryError(RuntimeError):
    pass


def _initialize_lock_for(database_path: Path) -> threading.Lock:
    with _INITIALIZE_LOCKS_GUARD:
        return _INITIALIZE_LOCKS.setdefault(database_path, threading.Lock())


class WorkflowDraftRepository:
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
                    CREATE TABLE IF NOT EXISTS workflow_drafts (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        nodes_json TEXT NOT NULL,
                        edges_json TEXT NOT NULL,
                        global_variables_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workflow_node_runs (
                        id TEXT PRIMARY KEY,
                        workflow_id TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        finished_at TEXT,
                        duration_ms INTEGER NOT NULL,
                        provider_name TEXT NOT NULL,
                        model_name TEXT NOT NULL,
                        input_snapshot_json TEXT NOT NULL,
                        request_body_json TEXT NOT NULL,
                        events_json TEXT NOT NULL,
                        output_json TEXT NOT NULL,
                        stdout_body TEXT NOT NULL DEFAULT '',
                        stderr_body TEXT NOT NULL DEFAULT '',
                        console_body TEXT NOT NULL DEFAULT '',
                        response_body TEXT NOT NULL DEFAULT '',
                        output_variables_json TEXT NOT NULL DEFAULT '{}',
                        usage_json TEXT,
                        error_json TEXT,
                        http_status INTEGER,
                        request_id TEXT,
                        FOREIGN KEY(workflow_id) REFERENCES workflow_drafts(id)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS workflow_node_runs_lookup
                    ON workflow_node_runs(workflow_id, node_id, started_at DESC, id DESC)
                    """
                )
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(workflow_node_runs)"
                    ).fetchall()
                }
                if "response_body" not in columns:
                    connection.execute(
                        "ALTER TABLE workflow_node_runs "
                        "ADD COLUMN response_body TEXT NOT NULL DEFAULT ''"
                    )
                if "stdout_body" not in columns:
                    connection.execute(
                        "ALTER TABLE workflow_node_runs "
                        "ADD COLUMN stdout_body TEXT NOT NULL DEFAULT ''"
                    )
                if "stderr_body" not in columns:
                    connection.execute(
                        "ALTER TABLE workflow_node_runs "
                        "ADD COLUMN stderr_body TEXT NOT NULL DEFAULT ''"
                    )
                if "console_body" not in columns:
                    connection.execute(
                        "ALTER TABLE workflow_node_runs "
                        "ADD COLUMN console_body TEXT NOT NULL DEFAULT ''"
                    )
                if "output_variables_json" not in columns:
                    connection.execute(
                        "ALTER TABLE workflow_node_runs "
                        "ADD COLUMN output_variables_json TEXT NOT NULL DEFAULT '{}'"
                    )
                connection.execute(
                    "UPDATE workflow_node_runs SET status = 'SUCCESS' "
                    "WHERE status = 'PASSED'"
                )
                connection.commit()
            self._initialized = True

    def create_draft(self, record: WorkflowDraftRecord) -> WorkflowDraftRecord:
        values = record.model_dump(mode="json")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO workflow_drafts(
                        id, name, description, nodes_json, edges_json,
                        global_variables_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values["id"], values["name"], values["description"],
                        _json_dump(values["nodes"]), _json_dump(values["edges"]),
                        _json_dump(values["global_variables"]), values["created_at"],
                        values["updated_at"],
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise WorkflowDraftRepositoryError(f"写入 Workflow 草稿失败: {exc}") from exc
        return record

    def get_draft(self, workflow_id: str) -> WorkflowDraftRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_drafts WHERE id = ?", (workflow_id,)
            ).fetchone()
        return self._draft_from_row(row) if row else None

    def list_drafts(self) -> list[WorkflowDraftRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workflow_drafts ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [self._draft_from_row(row) for row in rows]

    def update_draft(self, record: WorkflowDraftRecord) -> WorkflowDraftRecord:
        values = record.model_dump(mode="json")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE workflow_drafts
                SET name = ?, description = ?, nodes_json = ?, edges_json = ?,
                    global_variables_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    values["name"], values["description"],
                    _json_dump(values["nodes"]), _json_dump(values["edges"]),
                    _json_dump(values["global_variables"]), values["updated_at"],
                    values["id"],
                ),
            )
            connection.commit()
        if cursor.rowcount == 0:
            raise WorkflowDraftRepositoryError(f"Workflow 草稿不存在: {record.id}")
        return record

    def update_metadata(
        self,
        workflow_id: str,
        *,
        name: str,
        description: str,
    ) -> WorkflowDraftRecord:
        """只更新 Workflow 名称和说明，不重新校验或改写画布图。"""
        updated_at = utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE workflow_drafts
                SET name = ?, description = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, description, updated_at, workflow_id),
            )
            if cursor.rowcount == 0:
                raise WorkflowDraftRepositoryError(
                    f"Workflow 草稿不存在: {workflow_id}"
                )
            row = connection.execute(
                "SELECT * FROM workflow_drafts WHERE id = ?", (workflow_id,)
            ).fetchone()
            connection.commit()
        return self._draft_from_row(row)

    def delete_draft(self, workflow_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM workflow_drafts WHERE id = ?", (workflow_id,)
            )
            connection.commit()
        return cursor.rowcount > 0

    def create_run(self, record: WorkflowNodeRunRecord) -> WorkflowNodeRunRecord:
        values = record.model_dump(mode="json")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO workflow_node_runs(
                        id, workflow_id, node_id, status, started_at, finished_at,
                        duration_ms, provider_name, model_name, input_snapshot_json,
                        request_body_json, events_json, output_json,
                        stdout_body, stderr_body, console_body, response_body,
                        output_variables_json, usage_json, error_json, http_status,
                        request_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._run_values(values),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise WorkflowDraftRepositoryError(f"写入节点运行失败: {exc}") from exc
        return record

    def finish_run(self, record: WorkflowNodeRunRecord) -> WorkflowNodeRunRecord:
        if record.status == WorkflowNodeRunStatus.RUNNING:
            raise WorkflowDraftRepositoryError("终态运行不能保持 RUNNING")
        values = record.model_dump(mode="json")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE workflow_node_runs SET
                    status = ?, finished_at = ?, duration_ms = ?, provider_name = ?,
                    model_name = ?, input_snapshot_json = ?, request_body_json = ?,
                    events_json = ?, output_json = ?, stdout_body = ?,
                    stderr_body = ?, console_body = ?, response_body = ?,
                    output_variables_json = ?, usage_json = ?, error_json = ?,
                    http_status = ?, request_id = ?
                WHERE id = ? AND workflow_id = ? AND node_id = ?
                """,
                (
                    values["status"], values["finished_at"], values["duration_ms"],
                    values["provider_name"], values["model_name"],
                    _json_dump(values["input_snapshot"]),
                    _json_dump(values["request_body"]), _json_dump(values["events"]),
                    _json_dump(values["output"]), values["stdout"], values["stderr"],
                    values["console"], values["response_body"],
                    _json_dump(values["output_variables"]),
                    _json_dump_optional(values["usage"]),
                    _json_dump_optional(values["error"]), values["http_status"],
                    values["request_id"], values["id"], values["workflow_id"],
                    values["node_id"],
                ),
            )
            if cursor.rowcount == 0:
                raise WorkflowDraftRepositoryError(f"节点运行不存在: {record.id}")
            connection.execute(
                """
                DELETE FROM workflow_node_runs
                WHERE id IN (
                    SELECT id FROM workflow_node_runs
                    WHERE workflow_id = ? AND node_id = ?
                    ORDER BY started_at DESC, id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (record.workflow_id, record.node_id, NODE_RUN_HISTORY_LIMIT),
            )
            connection.commit()
        return record

    def list_node_runs(
        self, workflow_id: str, node_id: str
    ) -> list[WorkflowNodeRunRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM workflow_node_runs
                WHERE workflow_id = ? AND node_id = ?
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (workflow_id, node_id, NODE_RUN_HISTORY_LIMIT),
            ).fetchall()
        return [self._run_from_row(row) for row in rows]

    def latest_success_run(
        self, workflow_id: str, node_id: str
    ) -> WorkflowNodeRunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM workflow_node_runs
                WHERE workflow_id = ? AND node_id = ? AND status = 'SUCCESS'
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """,
                (workflow_id, node_id),
            ).fetchone()
        return self._run_from_row(row) if row else None

    @contextmanager
    def _connect(self, *, initialize: bool = True):
        if initialize:
            self.initialize()
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _draft_from_row(row: sqlite3.Row) -> WorkflowDraftRecord:
        # Persisted drafts may predate the current node contract. Restore them
        # without revalidating so users can open and correct them; all writes
        # and executions still pass through current validation.
        return WorkflowDraftRecord.model_construct(
            id=row["id"], name=row["name"], description=row["description"],
            nodes=json.loads(row["nodes_json"]), edges=json.loads(row["edges_json"]),
            global_variables=json.loads(row["global_variables_json"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _run_values(values: dict[str, Any]) -> tuple[Any, ...]:
        return (
            values["id"], values["workflow_id"], values["node_id"],
            values["status"], values["started_at"], values["finished_at"],
            values["duration_ms"], values["provider_name"], values["model_name"],
            _json_dump(values["input_snapshot"]), _json_dump(values["request_body"]),
            _json_dump(values["events"]), _json_dump(values["output"]),
            values["stdout"], values["stderr"], values["console"],
            values["response_body"],
            _json_dump(values["output_variables"]),
            _json_dump_optional(values["usage"]), _json_dump_optional(values["error"]),
            values["http_status"], values["request_id"],
        )

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> WorkflowNodeRunRecord:
        return WorkflowNodeRunRecord(
            id=row["id"], workflow_id=row["workflow_id"], node_id=row["node_id"],
            status=row["status"], started_at=row["started_at"],
            finished_at=row["finished_at"], duration_ms=row["duration_ms"],
            provider_name=row["provider_name"], model_name=row["model_name"],
            input_snapshot=json.loads(row["input_snapshot_json"]),
            request_body=json.loads(row["request_body_json"]),
            events=json.loads(row["events_json"]), output=json.loads(row["output_json"]),
            stdout=row["stdout_body"], stderr=row["stderr_body"],
            console=row["console_body"],
            response_body=row["response_body"],
            output_variables=json.loads(row["output_variables_json"]),
            usage=_json_load_optional(row["usage_json"]),
            error=_json_load_optional(row["error_json"]),
            http_status=row["http_status"], request_id=row["request_id"],
        )


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _json_dump_optional(value: Any) -> str | None:
    return None if value is None else _json_dump(value)


def _json_load_optional(value: str | None) -> Any:
    return None if value is None else json.loads(value)
