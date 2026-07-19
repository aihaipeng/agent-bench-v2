"""基于 SQLite 的 Run 状态与 Artifact 索引仓储。"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from execution.models import (
    ArtifactRecord,
    AttemptRecord,
    BusinessStatus,
    CaseRunRecord,
    ExecutionStatus,
    RetentionClass,
    RunRecord,
    StepRunRecord,
    TargetRecord,
    TestsetExecutionConfig,
    TestsetWorkflowBinding,
    WorkflowRecord,
    utc_now_iso,
)


SCHEMA_VERSION = 5
DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "run_storage" / "agent_bench.sqlite3"
)


class _UnsetType:
    pass


_UNSET = _UnsetType()
_INITIALIZE_LOCKS_GUARD = threading.Lock()
_INITIALIZE_LOCKS: dict[Path, threading.Lock] = {}


def _initialize_lock_for(database_path: Path) -> threading.Lock:
    with _INITIALIZE_LOCKS_GUARD:
        return _INITIALIZE_LOCKS.setdefault(database_path, threading.Lock())


class RunRepositoryError(RuntimeError):
    """运行仓储操作失败。"""


def _dump_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_json(value: str) -> dict[str, Any]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise RunRepositoryError("持久化 JSON 必须是对象")
    return decoded


def _dump_json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _load_json_value(value: str) -> Any:
    return json.loads(value)


class RunRepository:
    """为并发 Run 提供短连接、事务化的 SQLite Repository。"""

    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH):
        self.database_path = Path(database_path).resolve()
        self._initialize_lock = _initialize_lock_for(self.database_path)
        self._initialized = False

    def initialize(self) -> None:
        """创建数据库目录并执行未应用的 Schema Migration。"""
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
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    applied = {
                        row["version"]
                        for row in connection.execute(
                            "SELECT version FROM schema_migrations"
                        )
                    }
                    unsupported = {version for version in applied if version > SCHEMA_VERSION}
                    if unsupported:
                        raise RunRepositoryError(
                            "数据库版本高于当前程序支持范围: "
                            f"{max(unsupported)} > {SCHEMA_VERSION}"
                        )
                    migrations = (
                        (1, self._apply_v1),
                        (2, self._apply_v2),
                        (3, self._apply_v3),
                        (4, self._apply_v4),
                        (5, self._apply_v5),
                    )
                    for version, apply_migration in migrations:
                        if version in applied:
                            continue
                        apply_migration(connection)
                        connection.execute(
                            "INSERT INTO schema_migrations(version, applied_at) "
                            "VALUES (?, ?)",
                            (version, utc_now_iso()),
                        )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
            self._initialized = True

    def schema_version(self) -> int:
        """返回数据库当前 Schema 版本。"""
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
            ).fetchone()
        return int(row["version"])

    def create_target(self, record: TargetRecord) -> TargetRecord:
        """创建可复用 Target。"""
        values = record.model_dump(mode="json")
        self._execute_write(
            """
            INSERT INTO targets(
                id, name, base_url, path, method, headers_json,
                target_total_concurrency, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["id"],
                values["name"],
                values["base_url"],
                values["path"],
                values["method"],
                _dump_json(values["headers"]),
                values["target_total_concurrency"],
                values["created_at"],
                values["updated_at"],
            ),
        )
        return record

    def get_target(self, target_id: str) -> TargetRecord | None:
        """按 ID 读取 Target。"""
        row = self._fetch_one("SELECT * FROM targets WHERE id = ?", (target_id,))
        return self._target_from_row(row) if row else None

    def list_targets(self) -> list[TargetRecord]:
        """按最近更新时间列出 Target。"""
        rows = self._fetch_all(
            "SELECT * FROM targets ORDER BY updated_at DESC, id DESC",
            (),
        )
        return [self._target_from_row(row) for row in rows]

    def update_target(self, record: TargetRecord) -> TargetRecord:
        """完整更新一个 Target 配置。"""
        values = record.model_dump(mode="json")
        self._update_record(
            "targets",
            record.id,
            {
                "name": values["name"],
                "base_url": values["base_url"],
                "path": values["path"],
                "method": values["method"],
                "headers_json": _dump_json(values["headers"]),
                "target_total_concurrency": values["target_total_concurrency"],
                "updated_at": values["updated_at"],
            },
        )
        updated = self.get_target(record.id)
        if updated is None:
            raise RunRepositoryError(f"Target 不存在: {record.id}")
        return updated

    def delete_target(self, target_id: str) -> bool:
        """删除 Target 配置。"""
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM targets WHERE id = ?",
                (target_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    def create_workflow(self, record: WorkflowRecord) -> WorkflowRecord:
        """创建 Workflow。"""
        values = record.model_dump(mode="json")
        self._execute_write(
            """
            INSERT INTO workflows(
                id, name, description, definition_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                values["id"],
                values["name"],
                values["description"],
                _dump_json(values["definition"]),
                values["created_at"],
                values["updated_at"],
            ),
        )
        return record

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        """按 ID 读取 Workflow。"""
        row = self._fetch_one(
            "SELECT * FROM workflows WHERE id = ?",
            (workflow_id,),
        )
        return self._workflow_from_row(row) if row else None

    def list_workflows(self) -> list[WorkflowRecord]:
        """按最近更新时间列出 Workflow。"""
        rows = self._fetch_all(
            "SELECT * FROM workflows ORDER BY updated_at DESC, id DESC",
            (),
        )
        return [self._workflow_from_row(row) for row in rows]

    def update_workflow(self, record: WorkflowRecord) -> WorkflowRecord:
        """完整更新 Workflow。"""
        values = record.model_dump(mode="json")
        self._update_record(
            "workflows",
            record.id,
            {
                "name": values["name"],
                "description": values["description"],
                "definition_json": _dump_json(values["definition"]),
                "updated_at": values["updated_at"],
            },
        )
        updated = self.get_workflow(record.id)
        if updated is None:
            raise RunRepositoryError(f"Workflow 不存在: {record.id}")
        return updated

    def delete_workflow(self, workflow_id: str) -> bool:
        """删除 Workflow，当前测试集绑定由外键级联移除。"""
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM workflows WHERE id = ?",
                (workflow_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    def bind_testset_workflow(
        self,
        testset_filename: str,
        workflow_id: str,
    ) -> TestsetWorkflowBinding:
        """创建或替换一个测试集的当前 Workflow 绑定。"""
        binding = TestsetWorkflowBinding(
            testset_filename=testset_filename,
            workflow_id=workflow_id,
        )
        try:
            with self.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO testset_workflow_bindings(
                        testset_filename, workflow_id, updated_at
                    ) VALUES (?, ?, ?)
                    ON CONFLICT(testset_filename) DO UPDATE SET
                        workflow_id = excluded.workflow_id,
                        updated_at = excluded.updated_at
                    """,
                    (
                        binding.testset_filename,
                        binding.workflow_id,
                        binding.updated_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise RunRepositoryError(f"写入运行仓储失败: {exc}") from exc
        return binding

    def get_testset_workflow_binding(
        self,
        testset_filename: str,
    ) -> TestsetWorkflowBinding | None:
        """读取测试集的当前 Workflow 绑定。"""
        row = self._fetch_one(
            """
            SELECT testset_filename, workflow_id, updated_at
            FROM testset_workflow_bindings
            WHERE testset_filename = ?
            """,
            (testset_filename,),
        )
        return TestsetWorkflowBinding.model_validate(dict(row)) if row else None

    def delete_testset_workflow_binding(self, testset_filename: str) -> bool:
        """解除一个测试集的 Workflow 绑定。"""
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM testset_workflow_bindings WHERE testset_filename = ?",
                (testset_filename,),
            )
            connection.commit()
        return cursor.rowcount > 0

    def count_workflow_bindings(self, workflow_id: str) -> int:
        """统计当前绑定到 Workflow 的测试集数量。"""
        row = self._fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM testset_workflow_bindings
            WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        return int(row["count"]) if row else 0

    def set_testset_execution_config(
        self,
        testset_filename: str,
        request_template: Any,
    ) -> TestsetExecutionConfig:
        """创建或替换测试集请求模板。"""
        config = TestsetExecutionConfig(
            testset_filename=testset_filename,
            request_template=request_template,
        )
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO testset_execution_configs(
                    testset_filename, request_template_json, updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(testset_filename) DO UPDATE SET
                    request_template_json = excluded.request_template_json,
                    updated_at = excluded.updated_at
                """,
                (
                    config.testset_filename,
                    _dump_json_value(config.request_template),
                    config.updated_at,
                ),
            )
        return config

    def get_testset_execution_config(
        self,
        testset_filename: str,
    ) -> TestsetExecutionConfig | None:
        """读取测试集当前请求模板。"""
        row = self._fetch_one(
            """
            SELECT testset_filename, request_template_json, updated_at
            FROM testset_execution_configs
            WHERE testset_filename = ?
            """,
            (testset_filename,),
        )
        if row is None:
            return None
        data = dict(row)
        data["request_template"] = _load_json_value(
            data.pop("request_template_json")
        )
        return TestsetExecutionConfig.model_validate(data)

    def delete_testset_execution_config(self, testset_filename: str) -> bool:
        """删除测试集请求模板配置。"""
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM testset_execution_configs WHERE testset_filename = ?",
                (testset_filename,),
            )
            connection.commit()
        return cursor.rowcount > 0

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """提供可组合多个写操作的显式事务。"""
        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_run(self, record: RunRecord) -> RunRecord:
        """创建 Run。"""
        values = record.model_dump(mode="json")
        self._execute_write(
            """
            INSERT INTO runs(
                id, testset_filename, sheet_name, target_id, workflow_id,
                status, business_status, parameters_json, snapshot_json,
                cancel_requested, error, created_at, updated_at, started_at,
                finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["id"],
                values["testset_filename"],
                values["sheet_name"],
                values["target_id"],
                values["workflow_id"],
                values["status"],
                values["business_status"],
                _dump_json(values["parameters"]),
                _dump_json(values["snapshot"]),
                int(values["cancel_requested"]),
                values["error"],
                values["created_at"],
                values["updated_at"],
                values["started_at"],
                values["finished_at"],
            ),
        )
        return record

    def create_run_with_cases(
        self,
        run: RunRecord,
        cases: list[CaseRunRecord] | tuple[CaseRunRecord, ...],
    ) -> RunRecord:
        """在同一事务中创建 Run 及其全部初始 CaseRun。"""
        for case in cases:
            if case.run_id != run.id:
                raise RunRepositoryError(
                    f"CaseRun {case.id} 不属于待创建 Run {run.id}"
                )
        try:
            with self.transaction() as connection:
                run_values = run.model_dump(mode="json")
                connection.execute(
                    """
                    INSERT INTO runs(
                        id, testset_filename, sheet_name, target_id, workflow_id,
                        status, business_status, parameters_json, snapshot_json,
                        cancel_requested, error, created_at, updated_at, started_at,
                        finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_values["id"],
                        run_values["testset_filename"],
                        run_values["sheet_name"],
                        run_values["target_id"],
                        run_values["workflow_id"],
                        run_values["status"],
                        run_values["business_status"],
                        _dump_json(run_values["parameters"]),
                        _dump_json(run_values["snapshot"]),
                        int(run_values["cancel_requested"]),
                        run_values["error"],
                        run_values["created_at"],
                        run_values["updated_at"],
                        run_values["started_at"],
                        run_values["finished_at"],
                    ),
                )
                for case in cases:
                    values = case.model_dump(mode="json")
                    connection.execute(
                        """
                        INSERT INTO case_runs(
                            id, run_id, case_id, row_number, question, status,
                            business_status, error, created_at, updated_at,
                            started_at, finished_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        tuple(
                            values[key]
                            for key in (
                                "id",
                                "run_id",
                                "case_id",
                                "row_number",
                                "question",
                                "status",
                                "business_status",
                                "error",
                                "created_at",
                                "updated_at",
                                "started_at",
                                "finished_at",
                            )
                        ),
                    )
        except sqlite3.IntegrityError as exc:
            raise RunRepositoryError(f"写入运行仓储失败: {exc}") from exc
        return run

    def get_run(self, run_id: str) -> RunRecord | None:
        """按 ID 读取 Run。"""
        row = self._fetch_one("SELECT * FROM runs WHERE id = ?", (run_id,))
        return self._run_from_row(row) if row else None

    def list_runs(self, limit: int = 100) -> list[RunRecord]:
        """按创建时间倒序列出 Run。"""
        rows = self._fetch_all(
            "SELECT * FROM runs ORDER BY created_at DESC, id DESC LIMIT ?",
            (max(1, limit),),
        )
        return [self._run_from_row(row) for row in rows]

    def update_run_status(
        self,
        run_id: str,
        status: ExecutionStatus,
        *,
        business_status: BusinessStatus | None | _UnsetType = _UNSET,
        error: str | None | _UnsetType = _UNSET,
        started_at: str | None = None,
        finished_at: str | None = None,
        cancel_requested: bool | None = None,
    ) -> RunRecord:
        """更新 Run 状态并返回最新记录。"""
        fields: dict[str, Any] = {
            "status": status.value,
            "updated_at": utc_now_iso(),
        }
        if business_status is not _UNSET:
            fields["business_status"] = (
                business_status.value if isinstance(business_status, BusinessStatus) else None
            )
        if error is not _UNSET:
            fields["error"] = error
        if started_at is not None:
            fields["started_at"] = started_at
        if finished_at is not None:
            fields["finished_at"] = finished_at
        if cancel_requested is not None:
            fields["cancel_requested"] = int(cancel_requested)
        self._update_record("runs", run_id, fields)
        record = self.get_run(run_id)
        if record is None:
            raise RunRepositoryError(f"Run 不存在: {run_id}")
        return record

    def create_case_run(self, record: CaseRunRecord) -> CaseRunRecord:
        """创建 CaseRun。"""
        values = record.model_dump(mode="json")
        self._execute_write(
            """
            INSERT INTO case_runs(
                id, run_id, case_id, row_number, question, status,
                business_status, error, created_at, updated_at, started_at,
                finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(values[key] for key in (
                "id", "run_id", "case_id", "row_number", "question", "status",
                "business_status", "error", "created_at", "updated_at",
                "started_at", "finished_at",
            )),
        )
        return record

    def get_case_run(self, case_run_id: str) -> CaseRunRecord | None:
        """按 ID 读取 CaseRun。"""
        row = self._fetch_one(
            "SELECT * FROM case_runs WHERE id = ?",
            (case_run_id,),
        )
        return CaseRunRecord.model_validate(dict(row)) if row else None

    def list_case_runs(self, run_id: str) -> list[CaseRunRecord]:
        """按 Excel 行号列出 Run 下的 CaseRun。"""
        rows = self._fetch_all(
            """
            SELECT * FROM case_runs
            WHERE run_id = ?
            ORDER BY row_number ASC, id ASC
            """,
            (run_id,),
        )
        return [CaseRunRecord.model_validate(dict(row)) for row in rows]

    def update_case_run_status(
        self,
        case_run_id: str,
        status: ExecutionStatus,
        *,
        business_status: BusinessStatus | None | _UnsetType = _UNSET,
        error: str | None | _UnsetType = _UNSET,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> CaseRunRecord:
        """更新 CaseRun 状态。"""
        fields: dict[str, Any] = {
            "status": status.value,
            "updated_at": utc_now_iso(),
        }
        if business_status is not _UNSET:
            fields["business_status"] = (
                business_status.value if isinstance(business_status, BusinessStatus) else None
            )
        if error is not _UNSET:
            fields["error"] = error
        if started_at is not None:
            fields["started_at"] = started_at
        if finished_at is not None:
            fields["finished_at"] = finished_at
        self._update_record("case_runs", case_run_id, fields)
        record = self.get_case_run(case_run_id)
        if record is None:
            raise RunRepositoryError(f"CaseRun 不存在: {case_run_id}")
        return record

    def create_attempt(self, record: AttemptRecord) -> AttemptRecord:
        """创建一次 HTTP Attempt。"""
        values = record.model_dump(mode="json")
        self._execute_write(
            """
            INSERT INTO attempts(
                id, case_run_id, attempt_number, status, http_status,
                body_code, error_type, error, created_at, updated_at,
                started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(values[key] for key in (
                "id", "case_run_id", "attempt_number", "status", "http_status",
                "body_code", "error_type", "error", "created_at", "updated_at",
                "started_at", "finished_at",
            )),
        )
        return record

    def list_attempts(self, case_run_id: str) -> list[AttemptRecord]:
        """按尝试序号列出 CaseRun 的 Attempt。"""
        rows = self._fetch_all(
            """
            SELECT * FROM attempts
            WHERE case_run_id = ?
            ORDER BY attempt_number ASC
            """,
            (case_run_id,),
        )
        return [AttemptRecord.model_validate(dict(row)) for row in rows]

    def update_attempt_status(
        self,
        attempt_id: str,
        status: ExecutionStatus,
        **changes: Any,
    ) -> AttemptRecord:
        """更新 Attempt 状态和 HTTP 结果字段。"""
        allowed = {
            "http_status",
            "body_code",
            "error_type",
            "error",
            "started_at",
            "finished_at",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise RunRepositoryError(
                f"Attempt 包含不可更新字段: {', '.join(sorted(unknown))}"
            )
        fields = {"status": status.value, "updated_at": utc_now_iso(), **changes}
        self._update_record("attempts", attempt_id, fields)
        row = self._fetch_one("SELECT * FROM attempts WHERE id = ?", (attempt_id,))
        if row is None:
            raise RunRepositoryError(f"Attempt 不存在: {attempt_id}")
        return AttemptRecord.model_validate(dict(row))

    def mark_case_interrupted(self, case_run_id: str, reason: str) -> CaseRunRecord:
        """手工恢复前关闭服务中断遗留的 RUNNING Attempt/Step/Case。"""
        now = utc_now_iso()
        try:
            with self.transaction() as connection:
                connection.execute(
                    """
                    UPDATE attempts
                    SET status = ?, error_type = ?, error = ?,
                        updated_at = ?, finished_at = ?
                    WHERE case_run_id = ? AND status = ?
                    """,
                    (
                        ExecutionStatus.ERROR.value,
                        "service_interrupted",
                        reason,
                        now,
                        now,
                        case_run_id,
                        ExecutionStatus.RUNNING.value,
                    ),
                )
                connection.execute(
                    """
                    UPDATE step_runs
                    SET status = ?, business_status = ?, error = ?,
                        updated_at = ?, finished_at = ?
                    WHERE case_run_id = ? AND status = ?
                    """,
                    (
                        ExecutionStatus.ERROR.value,
                        BusinessStatus.ERROR.value,
                        reason,
                        now,
                        now,
                        case_run_id,
                        ExecutionStatus.RUNNING.value,
                    ),
                )
                cursor = connection.execute(
                    """
                    UPDATE case_runs
                    SET status = ?, business_status = ?, error = ?,
                        updated_at = ?, finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        ExecutionStatus.ERROR.value,
                        BusinessStatus.ERROR.value,
                        reason,
                        now,
                        now,
                        case_run_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise RunRepositoryError(f"CaseRun 不存在: {case_run_id}")
        except sqlite3.IntegrityError as exc:
            raise RunRepositoryError(f"写入运行仓储失败: {exc}") from exc
        restored = self.get_case_run(case_run_id)
        if restored is None:
            raise RunRepositoryError(f"CaseRun 不存在: {case_run_id}")
        return restored

    def create_step_run(self, record: StepRunRecord) -> StepRunRecord:
        """创建工具 StepRun。"""
        values = record.model_dump(mode="json")
        self._execute_write(
            """
            INSERT INTO step_runs(
                id, case_run_id, stage, sequence, execution_number,
                check_item, step_id,
                tool_id, tool_name, tool_type, tool_code_hash, status,
                business_status, error, created_at, updated_at, started_at,
                finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(values[key] for key in (
                "id", "case_run_id", "stage", "sequence", "execution_number",
                "check_item", "step_id", "tool_id", "tool_name", "tool_type",
                "tool_code_hash", "status", "business_status", "error",
                "created_at", "updated_at", "started_at", "finished_at",
            )),
        )
        return record

    def next_step_execution_number(
        self,
        case_run_id: str,
        stage: str,
        step_id: str,
    ) -> int:
        """返回同一 Case/Stage/Workflow Step 的下一个执行序号。"""
        row = self._fetch_one(
            """
            SELECT COALESCE(MAX(execution_number), 0) + 1 AS next_number
            FROM step_runs
            WHERE case_run_id = ? AND stage = ? AND step_id = ?
            """,
            (case_run_id, stage, step_id),
        )
        return int(row["next_number"]) if row else 1

    def list_step_runs(self, case_run_id: str) -> list[StepRunRecord]:
        """按阶段顺序列出 CaseRun 的 StepRun。"""
        rows = self._fetch_all(
            """
            SELECT * FROM step_runs
            WHERE case_run_id = ?
            ORDER BY sequence ASC, created_at ASC, id ASC
            """,
            (case_run_id,),
        )
        return [StepRunRecord.model_validate(dict(row)) for row in rows]

    def update_step_run_status(
        self,
        step_run_id: str,
        status: ExecutionStatus,
        *,
        business_status: BusinessStatus | None | _UnsetType = _UNSET,
        error: str | None | _UnsetType = _UNSET,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> StepRunRecord:
        """更新 StepRun 状态。"""
        fields: dict[str, Any] = {
            "status": status.value,
            "updated_at": utc_now_iso(),
        }
        if business_status is not _UNSET:
            fields["business_status"] = (
                business_status.value if isinstance(business_status, BusinessStatus) else None
            )
        if error is not _UNSET:
            fields["error"] = error
        if started_at is not None:
            fields["started_at"] = started_at
        if finished_at is not None:
            fields["finished_at"] = finished_at
        self._update_record("step_runs", step_run_id, fields)
        row = self._fetch_one("SELECT * FROM step_runs WHERE id = ?", (step_run_id,))
        if row is None:
            raise RunRepositoryError(f"StepRun 不存在: {step_run_id}")
        return StepRunRecord.model_validate(dict(row))

    def create_artifact(self, record: ArtifactRecord) -> ArtifactRecord:
        """创建 Artifact 索引。"""
        values = record.model_dump(mode="json")
        self._execute_write(
            """
            INSERT INTO artifacts(
                id, run_id, case_run_id, attempt_id, step_run_id, kind,
                relative_path, size_bytes, sha256, retention_class,
                expires_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(values[key] for key in (
                "id", "run_id", "case_run_id", "attempt_id", "step_run_id",
                "kind", "relative_path", "size_bytes", "sha256",
                "retention_class", "expires_at", "created_at",
            )),
        )
        return record

    def list_artifacts(
        self,
        run_id: str,
        *,
        case_run_id: str | None = None,
    ) -> list[ArtifactRecord]:
        """列出 Run 或指定 CaseRun 的 Artifact。"""
        if case_run_id is None:
            rows = self._fetch_all(
                "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at, id",
                (run_id,),
            )
        else:
            rows = self._fetch_all(
                """
                SELECT * FROM artifacts
                WHERE run_id = ? AND case_run_id = ?
                ORDER BY created_at, id
                """,
                (run_id, case_run_id),
            )
        return [ArtifactRecord.model_validate(dict(row)) for row in rows]

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        """按 ID 读取 Artifact 索引。"""
        row = self._fetch_one(
            "SELECT * FROM artifacts WHERE id = ?",
            (artifact_id,),
        )
        return ArtifactRecord.model_validate(dict(row)) if row else None

    def update_artifact_retention(
        self,
        artifact_id: str,
        retention_class: RetentionClass,
        *,
        expires_at: str | None = None,
    ) -> ArtifactRecord:
        """更新 Artifact 保留分类。"""
        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE artifacts
                SET retention_class = ?, expires_at = ?
                WHERE id = ?
                """,
                (retention_class.value, expires_at, artifact_id),
            )
            if cursor.rowcount == 0:
                connection.rollback()
                raise RunRepositoryError(f"Artifact 不存在: {artifact_id}")
            connection.commit()
        updated = self.get_artifact(artifact_id)
        if updated is None:
            raise RunRepositoryError(f"Artifact 不存在: {artifact_id}")
        return updated

    def delete_run(self, run_id: str) -> bool:
        """删除 Run，并依靠外键级联删除其子记录索引。"""
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            connection.commit()
        return cursor.rowcount > 0

    def _connect(self, *, initialize: bool = True) -> sqlite3.Connection:
        if initialize:
            self.initialize()
        connection = sqlite3.connect(
            self.database_path,
            timeout=5,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _execute_write(self, sql: str, parameters: tuple[Any, ...]) -> None:
        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(sql, parameters)
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise RunRepositoryError(f"写入运行仓储失败: {exc}") from exc

    def _fetch_one(
        self,
        sql: str,
        parameters: tuple[Any, ...],
    ) -> sqlite3.Row | None:
        self.initialize()
        with self._connect() as connection:
            return connection.execute(sql, parameters).fetchone()

    def _fetch_all(
        self,
        sql: str,
        parameters: tuple[Any, ...],
    ) -> list[sqlite3.Row]:
        self.initialize()
        with self._connect() as connection:
            return list(connection.execute(sql, parameters).fetchall())

    def _update_record(
        self,
        table: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> None:
        allowed_tables = {
            "targets",
            "workflows",
            "runs",
            "case_runs",
            "attempts",
            "step_runs",
        }
        if table not in allowed_tables:
            raise RunRepositoryError(f"不允许更新的数据表: {table}")
        assignments = ", ".join(f"{name} = ?" for name in fields)
        parameters = (*fields.values(), record_id)
        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                f"UPDATE {table} SET {assignments} WHERE id = ?",
                parameters,
            )
            if cursor.rowcount == 0:
                connection.rollback()
                raise RunRepositoryError(f"记录不存在: {record_id}")
            connection.commit()

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> RunRecord:
        data = dict(row)
        data["parameters"] = _load_json(data.pop("parameters_json"))
        data["snapshot"] = _load_json(data.pop("snapshot_json"))
        data["cancel_requested"] = bool(data["cancel_requested"])
        return RunRecord.model_validate(data)

    @staticmethod
    def _target_from_row(row: sqlite3.Row) -> TargetRecord:
        data = dict(row)
        data["headers"] = _load_json(data.pop("headers_json"))
        return TargetRecord.model_validate(data)

    @staticmethod
    def _workflow_from_row(row: sqlite3.Row) -> WorkflowRecord:
        data = dict(row)
        data["definition"] = _load_json(data.pop("definition_json"))
        return WorkflowRecord.model_validate(data)

    @staticmethod
    def _apply_v1(connection: sqlite3.Connection) -> None:
        statements = (
            """
            CREATE TABLE runs (
                id TEXT PRIMARY KEY,
                testset_filename TEXT NOT NULL,
                sheet_name TEXT NOT NULL,
                target_id TEXT,
                workflow_id TEXT,
                status TEXT NOT NULL,
                business_status TEXT,
                parameters_json TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            )
            """,
            """
            CREATE TABLE case_runs (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                case_id TEXT NOT NULL,
                row_number INTEGER NOT NULL,
                question TEXT NOT NULL,
                status TEXT NOT NULL,
                business_status TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(run_id, case_id)
            )
            """,
            """
            CREATE TABLE attempts (
                id TEXT PRIMARY KEY,
                case_run_id TEXT NOT NULL REFERENCES case_runs(id) ON DELETE CASCADE,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                http_status INTEGER,
                body_code TEXT,
                error_type TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(case_run_id, attempt_number)
            )
            """,
            """
            CREATE TABLE step_runs (
                id TEXT PRIMARY KEY,
                case_run_id TEXT NOT NULL REFERENCES case_runs(id) ON DELETE CASCADE,
                stage TEXT NOT NULL,
                sequence INTEGER NOT NULL DEFAULT 0,
                check_item TEXT,
                step_id TEXT,
                tool_id TEXT,
                tool_name TEXT,
                tool_type TEXT,
                tool_code_hash TEXT,
                status TEXT NOT NULL,
                business_status TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(case_run_id, stage, step_id)
            )
            """,
            """
            CREATE TABLE artifacts (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                case_run_id TEXT REFERENCES case_runs(id) ON DELETE CASCADE,
                attempt_id TEXT REFERENCES attempts(id) ON DELETE CASCADE,
                step_run_id TEXT REFERENCES step_runs(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                relative_path TEXT NOT NULL UNIQUE,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                retention_class TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX idx_case_runs_run_status
                ON case_runs(run_id, status, row_number)
            """,
            """
            CREATE INDEX idx_attempts_case_number
                ON attempts(case_run_id, attempt_number)
            """,
            """
            CREATE INDEX idx_step_runs_case_sequence
                ON step_runs(case_run_id, sequence)
            """,
            """
            CREATE INDEX idx_artifacts_run_case
                ON artifacts(run_id, case_run_id, created_at)
            """,
            """
            CREATE TRIGGER validate_artifact_case_run
            BEFORE INSERT ON artifacts
            WHEN NEW.case_run_id IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1 FROM case_runs
                    WHERE id = NEW.case_run_id AND run_id = NEW.run_id
                 )
            BEGIN
                SELECT RAISE(ABORT, 'artifact case_run does not belong to run');
            END
            """,
            """
            CREATE TRIGGER validate_artifact_attempt
            BEFORE INSERT ON artifacts
            WHEN NEW.attempt_id IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1
                    FROM attempts
                    JOIN case_runs ON case_runs.id = attempts.case_run_id
                    WHERE attempts.id = NEW.attempt_id
                      AND case_runs.run_id = NEW.run_id
                      AND (
                        NEW.case_run_id IS NULL
                        OR NEW.case_run_id = attempts.case_run_id
                      )
                 )
            BEGIN
                SELECT RAISE(ABORT, 'artifact attempt does not belong to run/case');
            END
            """,
            """
            CREATE TRIGGER validate_artifact_step_run
            BEFORE INSERT ON artifacts
            WHEN NEW.step_run_id IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1
                    FROM step_runs
                    JOIN case_runs ON case_runs.id = step_runs.case_run_id
                    WHERE step_runs.id = NEW.step_run_id
                      AND case_runs.run_id = NEW.run_id
                      AND (
                        NEW.case_run_id IS NULL
                        OR NEW.case_run_id = step_runs.case_run_id
                      )
                 )
            BEGIN
                SELECT RAISE(ABORT, 'artifact step_run does not belong to run/case');
            END
            """,
        )
        for statement in statements:
            connection.execute(statement)

    @staticmethod
    def _apply_v2(connection: sqlite3.Connection) -> None:
        statements = (
            """
            CREATE TABLE targets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                base_url TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL CHECK(method = 'POST'),
                headers_json TEXT NOT NULL,
                target_total_concurrency INTEGER NOT NULL
                    CHECK(target_total_concurrency >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX idx_targets_updated_at
                ON targets(updated_at DESC, id DESC)
            """,
        )
        for statement in statements:
            connection.execute(statement)

    @staticmethod
    def _apply_v3(connection: sqlite3.Connection) -> None:
        statements = (
            """
            CREATE TABLE workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                definition_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE testset_workflow_bindings (
                testset_filename TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL
                    REFERENCES workflows(id) ON DELETE CASCADE,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX idx_workflows_updated_at
                ON workflows(updated_at DESC, id DESC)
            """,
            """
            CREATE INDEX idx_testset_bindings_workflow
                ON testset_workflow_bindings(workflow_id)
            """,
        )
        for statement in statements:
            connection.execute(statement)

    @staticmethod
    def _apply_v4(connection: sqlite3.Connection) -> None:
        statements = (
            """
            CREATE TABLE step_runs_v4 (
                id TEXT PRIMARY KEY,
                case_run_id TEXT NOT NULL REFERENCES case_runs(id) ON DELETE CASCADE,
                stage TEXT NOT NULL,
                sequence INTEGER NOT NULL DEFAULT 0,
                execution_number INTEGER NOT NULL DEFAULT 1,
                check_item TEXT,
                step_id TEXT,
                tool_id TEXT,
                tool_name TEXT,
                tool_type TEXT,
                tool_code_hash TEXT,
                status TEXT NOT NULL,
                business_status TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(case_run_id, stage, step_id, execution_number)
            )
            """,
            """
            INSERT INTO step_runs_v4(
                id, case_run_id, stage, sequence, execution_number,
                check_item, step_id, tool_id, tool_name, tool_type,
                tool_code_hash, status, business_status, error, created_at,
                updated_at, started_at, finished_at
            )
            SELECT
                id, case_run_id, stage, sequence, 1,
                check_item, step_id, tool_id, tool_name, tool_type,
                tool_code_hash, status, business_status, error, created_at,
                updated_at, started_at, finished_at
            FROM step_runs
            """,
            """
            CREATE TABLE artifacts_v4 (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                case_run_id TEXT REFERENCES case_runs(id) ON DELETE CASCADE,
                attempt_id TEXT REFERENCES attempts(id) ON DELETE CASCADE,
                step_run_id TEXT REFERENCES step_runs_v4(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                relative_path TEXT NOT NULL UNIQUE,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                retention_class TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL
            )
            """,
            """
            INSERT INTO artifacts_v4(
                id, run_id, case_run_id, attempt_id, step_run_id, kind,
                relative_path, size_bytes, sha256, retention_class,
                expires_at, created_at
            )
            SELECT
                id, run_id, case_run_id, attempt_id, step_run_id, kind,
                relative_path, size_bytes, sha256, retention_class,
                expires_at, created_at
            FROM artifacts
            """,
            "DROP TABLE artifacts",
            "DROP TABLE step_runs",
            "ALTER TABLE step_runs_v4 RENAME TO step_runs",
            "ALTER TABLE artifacts_v4 RENAME TO artifacts",
            """
            CREATE INDEX idx_step_runs_case_sequence
                ON step_runs(case_run_id, sequence, execution_number)
            """,
            """
            CREATE INDEX idx_artifacts_run_case
                ON artifacts(run_id, case_run_id, created_at)
            """,
            """
            CREATE TRIGGER validate_artifact_case_run
            BEFORE INSERT ON artifacts
            WHEN NEW.case_run_id IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1 FROM case_runs
                    WHERE id = NEW.case_run_id AND run_id = NEW.run_id
                 )
            BEGIN
                SELECT RAISE(ABORT, 'artifact case_run does not belong to run');
            END
            """,
            """
            CREATE TRIGGER validate_artifact_attempt
            BEFORE INSERT ON artifacts
            WHEN NEW.attempt_id IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1
                    FROM attempts
                    JOIN case_runs ON case_runs.id = attempts.case_run_id
                    WHERE attempts.id = NEW.attempt_id
                      AND case_runs.run_id = NEW.run_id
                      AND (
                        NEW.case_run_id IS NULL
                        OR NEW.case_run_id = attempts.case_run_id
                      )
                 )
            BEGIN
                SELECT RAISE(ABORT, 'artifact attempt does not belong to run/case');
            END
            """,
            """
            CREATE TRIGGER validate_artifact_step_run
            BEFORE INSERT ON artifacts
            WHEN NEW.step_run_id IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1
                    FROM step_runs
                    JOIN case_runs ON case_runs.id = step_runs.case_run_id
                    WHERE step_runs.id = NEW.step_run_id
                      AND case_runs.run_id = NEW.run_id
                      AND (
                        NEW.case_run_id IS NULL
                        OR NEW.case_run_id = step_runs.case_run_id
                      )
                 )
            BEGIN
                SELECT RAISE(ABORT, 'artifact step_run does not belong to run/case');
            END
            """,
        )
        for statement in statements:
            connection.execute(statement)

    @staticmethod
    def _apply_v5(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE testset_execution_configs (
                testset_filename TEXT PRIMARY KEY,
                request_template_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
