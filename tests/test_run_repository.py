import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from execution import (
    ArtifactRecord,
    AttemptRecord,
    BusinessStatus,
    CaseRunRecord,
    ExecutionStatus,
    RetentionClass,
    RunRecord,
    RunRepository,
    RunRepositoryError,
    StepRunRecord,
    StepStage,
)
from execution.repository import SCHEMA_VERSION


def _repository(tmp_path) -> RunRepository:
    return RunRepository(tmp_path / "run_storage" / "agent_bench.sqlite3")


def _run(run_id: str = "run-1") -> RunRecord:
    return RunRecord(
        id=run_id,
        testset_filename="企业智能体用例.xlsx",
        sheet_name="首个 Sheet",
        target_id="target-1",
        workflow_id="workflow-1",
        parameters={"timeout_seconds": 600, "说明": "保留中文"},
        snapshot={"request_template": {"question": "${question}"}},
    )


def test_initialize_creates_versioned_wal_schema_and_survives_restart(tmp_path):
    database_path = tmp_path / "nested" / "agent_bench.sqlite3"
    repository = RunRepository(database_path)

    repository.initialize()
    repository.create_run(_run())
    restarted = RunRepository(database_path)
    restored = restarted.get_run("run-1")

    assert repository.schema_version() == SCHEMA_VERSION
    assert restarted.schema_version() == SCHEMA_VERSION
    assert restored is not None
    assert restored.parameters == {"timeout_seconds": 600, "说明": "保留中文"}
    assert restored.snapshot == {"request_template": {"question": "${question}"}}
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "schema_migrations",
        "runs",
        "case_runs",
        "attempts",
        "step_runs",
        "artifacts",
    } <= tables


def test_concurrent_repository_instances_initialize_once(tmp_path):
    database_path = tmp_path / "shared.sqlite3"

    def initialize(index: int) -> int:
        repository = RunRepository(database_path)
        repository.initialize()
        repository.create_run(_run(f"run-{index}"))
        return repository.schema_version()

    with ThreadPoolExecutor(max_workers=8) as executor:
        versions = list(executor.map(initialize, range(16)))

    repository = RunRepository(database_path)
    assert versions == [SCHEMA_VERSION] * 16
    assert len(repository.list_runs(limit=100)) == 16


def test_repository_round_trip_full_execution_graph_and_cascade_delete(tmp_path):
    repository = _repository(tmp_path)
    run = repository.create_run(_run())
    case = repository.create_case_run(
        CaseRunRecord(
            id="case-run-1",
            run_id=run.id,
            case_id="case_001",
            row_number=2,
            question="请用中文回答：为什么？\n第二行",
        )
    )
    attempt = repository.create_attempt(
        AttemptRecord(
            id="attempt-1",
            case_run_id=case.id,
            attempt_number=1,
            status=ExecutionStatus.SUCCEEDED,
            http_status=200,
            body_code="200",
        )
    )
    step = repository.create_step_run(
        StepRunRecord(
            id="step-run-1",
            case_run_id=case.id,
            stage=StepStage.EVALUATOR,
            sequence=2,
            check_item="intent",
            step_id="intent-evaluator-1",
            tool_id="tool-uuid",
            tool_name="intent-check-agent",
            tool_type="agent",
            tool_code_hash="a" * 64,
        )
    )
    artifact = repository.create_artifact(
        ArtifactRecord(
            id="artifact-1",
            run_id=run.id,
            case_run_id=case.id,
            attempt_id=attempt.id,
            step_run_id=step.id,
            kind="response",
            relative_path="runs/run-1/cases/case_001/response.json",
            size_bytes=123,
            sha256="b" * 64,
            retention_class=RetentionClass.FAILURE_LONG_TERM,
        )
    )

    assert repository.get_run(run.id).id == run.id
    assert repository.get_case_run(case.id).question == case.question
    assert repository.list_case_runs(run.id) == [case]
    assert repository.list_attempts(case.id) == [attempt]
    assert repository.list_step_runs(case.id) == [step]
    assert repository.list_artifacts(run.id) == [artifact]
    assert repository.list_artifacts(run.id, case_run_id=case.id) == [artifact]

    assert repository.delete_run(run.id) is True
    assert repository.delete_run(run.id) is False
    assert repository.get_run(run.id) is None
    assert repository.get_case_run(case.id) is None
    assert repository.list_attempts(case.id) == []
    assert repository.list_step_runs(case.id) == []
    assert repository.list_artifacts(run.id) == []


def test_foreign_keys_and_unique_execution_keys_are_enforced(tmp_path):
    repository = _repository(tmp_path)

    with pytest.raises(RunRepositoryError, match="FOREIGN KEY"):
        repository.create_case_run(
            CaseRunRecord(
                run_id="missing-run",
                case_id="case_001",
                row_number=2,
                question="question",
            )
        )

    run = repository.create_run(_run())
    case = repository.create_case_run(
        CaseRunRecord(
            id="case-run-1",
            run_id=run.id,
            case_id="case_001",
            row_number=2,
            question="question",
        )
    )
    with pytest.raises(RunRepositoryError, match="UNIQUE"):
        repository.create_case_run(
            CaseRunRecord(
                run_id=run.id,
                case_id="case_001",
                row_number=3,
                question="duplicate",
            )
        )

    repository.create_attempt(
        AttemptRecord(case_run_id=case.id, attempt_number=1)
    )
    with pytest.raises(RunRepositoryError, match="UNIQUE"):
        repository.create_attempt(
            AttemptRecord(case_run_id=case.id, attempt_number=1)
        )
    with pytest.raises(RunRepositoryError, match="FOREIGN KEY"):
        repository.create_artifact(
            ArtifactRecord(
                run_id="missing-run",
                kind="response",
                relative_path="runs/missing/response.json",
                size_bytes=0,
                sha256="0" * 64,
                retention_class=RetentionClass.SUCCESS_TEMPORARY,
            )
        )


def test_artifact_execution_links_must_belong_to_same_run_and_case(tmp_path):
    repository = _repository(tmp_path)
    repository.create_run(_run("run-1"))
    repository.create_run(_run("run-2"))
    first_case = repository.create_case_run(
        CaseRunRecord(
            id="case-run-1",
            run_id="run-1",
            case_id="case_001",
            row_number=2,
            question="first",
        )
    )
    second_case = repository.create_case_run(
        CaseRunRecord(
            id="case-run-2",
            run_id="run-2",
            case_id="case_002",
            row_number=2,
            question="second",
        )
    )
    attempt = repository.create_attempt(
        AttemptRecord(
            id="attempt-2", case_run_id=second_case.id, attempt_number=1
        )
    )
    step = repository.create_step_run(
        StepRunRecord(
            id="step-run-2",
            case_run_id=second_case.id,
            stage=StepStage.PARSER,
            step_id="parser-1",
        )
    )

    base = {
        "run_id": "run-1",
        "kind": "response",
        "size_bytes": 2,
        "sha256": "c" * 64,
        "retention_class": RetentionClass.FAILURE_LONG_TERM,
    }
    invalid_links = [
        {"case_run_id": second_case.id},
        {"case_run_id": first_case.id, "attempt_id": attempt.id},
        {"case_run_id": first_case.id, "step_run_id": step.id},
    ]
    for index, links in enumerate(invalid_links):
        record = ArtifactRecord(
            **base,
            **links,
            relative_path=f"runs/run-1/invalid-{index}.json",
        )
        with pytest.raises(RunRepositoryError, match="does not belong"):
            repository.create_artifact(record)


def test_concurrent_case_inserts_are_serialized_without_data_loss(tmp_path):
    repository = _repository(tmp_path)
    repository.create_run(_run())

    def insert_case(index: int) -> str:
        record = CaseRunRecord(
            run_id="run-1",
            case_id=f"case_{index:03d}",
            row_number=index + 2,
            question=f"问题 {index}",
        )
        return repository.create_case_run(record).id

    with ThreadPoolExecutor(max_workers=12) as executor:
        inserted_ids = list(executor.map(insert_case, range(60)))

    cases = repository.list_case_runs("run-1")
    assert len(inserted_ids) == len(set(inserted_ids)) == 60
    assert [case.row_number for case in cases] == list(range(2, 62))


def test_status_updates_preserve_omitted_values_and_allow_explicit_clear(tmp_path):
    repository = _repository(tmp_path)
    repository.create_run(
        _run().model_copy(
            update={"business_status": BusinessStatus.FAIL, "error": "old error"}
        )
    )
    case = repository.create_case_run(
        CaseRunRecord(
            id="case-run-1",
            run_id="run-1",
            case_id="case_001",
            row_number=2,
            question="question",
            business_status=BusinessStatus.FAIL,
            error="case error",
        )
    )
    step = repository.create_step_run(
        StepRunRecord(
            id="step-run-1",
            case_run_id=case.id,
            stage=StepStage.EVALUATOR,
            step_id="evaluator-1",
            business_status=BusinessStatus.ERROR,
            error="tool error",
        )
    )

    preserved_run = repository.update_run_status("run-1", ExecutionStatus.RUNNING)
    preserved_case = repository.update_case_run_status(
        case.id, ExecutionStatus.RUNNING
    )
    preserved_step = repository.update_step_run_status(
        step.id, ExecutionStatus.RUNNING
    )
    assert (preserved_run.business_status, preserved_run.error) == (
        BusinessStatus.FAIL,
        "old error",
    )
    assert (preserved_case.business_status, preserved_case.error) == (
        BusinessStatus.FAIL,
        "case error",
    )
    assert (preserved_step.business_status, preserved_step.error) == (
        BusinessStatus.ERROR,
        "tool error",
    )

    cleared = repository.update_run_status(
        "run-1",
        ExecutionStatus.SUCCEEDED,
        business_status=None,
        error=None,
    )
    assert cleared.business_status is None
    assert cleared.error is None
    with pytest.raises(RunRepositoryError, match="记录不存在"):
        repository.update_run_status("missing", ExecutionStatus.ERROR)


def test_attempt_update_validation_and_transaction_rollback(tmp_path):
    repository = _repository(tmp_path)
    repository.create_run(_run())
    case = repository.create_case_run(
        CaseRunRecord(
            id="case-run-1",
            run_id="run-1",
            case_id="case_001",
            row_number=2,
            question="question",
        )
    )
    attempt = repository.create_attempt(
        AttemptRecord(id="attempt-1", case_run_id=case.id, attempt_number=1)
    )

    updated = repository.update_attempt_status(
        attempt.id,
        ExecutionStatus.ERROR,
        error_type="read_timeout",
        error="600 秒读取超时",
    )
    assert updated.status == ExecutionStatus.ERROR
    assert updated.error_type == "read_timeout"
    with pytest.raises(RunRepositoryError, match="不可更新字段"):
        repository.update_attempt_status(
            attempt.id, ExecutionStatus.ERROR, case_run_id="other"
        )

    with pytest.raises(RuntimeError, match="rollback"):
        with repository.transaction() as connection:
            connection.execute("DELETE FROM runs WHERE id = ?", ("run-1",))
            raise RuntimeError("rollback")
    assert repository.get_run("run-1") is not None
    assert repository.get_case_run(case.id) is not None


def test_newer_database_schema_is_rejected(tmp_path):
    database_path = tmp_path / "future.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, "
            "applied_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION + 1, "future"),
        )

    with pytest.raises(RunRepositoryError, match="高于当前程序支持范围"):
        RunRepository(database_path).initialize()


def test_v4_database_migrates_to_testset_execution_configs(tmp_path):
    database_path = tmp_path / "v4.sqlite3"
    with sqlite3.connect(database_path, isolation_level=None) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, "
            "applied_at TEXT NOT NULL)"
        )
        connection.execute("BEGIN IMMEDIATE")
        RunRepository._apply_v1(connection)
        RunRepository._apply_v2(connection)
        RunRepository._apply_v3(connection)
        RunRepository._apply_v4(connection)
        connection.execute(
            "INSERT INTO schema_migrations VALUES "
            "(1, 'v1'), (2, 'v2'), (3, 'v3'), (4, 'v4')"
        )
        connection.commit()

    repository = RunRepository(database_path)
    config = repository.set_testset_execution_config(
        "cases.xlsx",
        {"question": "${question}", "options": [True, None, 3]},
    )

    assert repository.schema_version() == SCHEMA_VERSION == 5
    assert repository.get_testset_execution_config("cases.xlsx") == config
    with sqlite3.connect(database_path) as connection:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
    assert versions == [1, 2, 3, 4, 5]


@pytest.mark.parametrize(
    "request_template",
    [
        {"question": "${question}", "nested": {"items": [1, "x"]}},
        ["${question}", 1, False, None],
        "${question}",
        42,
        True,
        None,
    ],
)
def test_testset_execution_config_round_trip_restart_and_delete(
    tmp_path,
    request_template,
):
    database_path = tmp_path / "agent_bench.sqlite3"
    repository = RunRepository(database_path)
    saved = repository.set_testset_execution_config(
        "企业用例.xlsx",
        request_template,
    )

    restarted = RunRepository(database_path)
    restored = restarted.get_testset_execution_config("企业用例.xlsx")

    assert restored == saved
    assert restored is not None
    assert restored.request_template == request_template
    assert restarted.delete_testset_execution_config("企业用例.xlsx") is True
    assert restarted.delete_testset_execution_config("企业用例.xlsx") is False
    assert restarted.get_testset_execution_config("企业用例.xlsx") is None


@pytest.mark.parametrize(
    "request_template",
    [float("nan"), float("inf"), {"value": float("-inf")}, {1, 2}],
)
def test_testset_execution_config_rejects_non_json_values(
    tmp_path,
    request_template,
):
    repository = _repository(tmp_path)

    with pytest.raises(ValidationError, match="必须是合法 JSON"):
        repository.set_testset_execution_config("cases.xlsx", request_template)

    assert repository.get_testset_execution_config("cases.xlsx") is None
