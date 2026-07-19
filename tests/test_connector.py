import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from execution import (
    ArtifactStore,
    CaseRunRecord,
    ConnectorErrorType,
    ExecutionStatus,
    FastAPIConnector,
    FastAPIConnectorError,
    RetentionClass,
    RunRecord,
    RunRepository,
    TargetRecord,
)


def _context(tmp_path, *, base_url="http://agent.test"):
    repository = RunRepository(tmp_path / "run_storage" / "agent_bench.sqlite3")
    store = ArtifactStore(tmp_path / "run_storage" / "artifacts")
    target = repository.create_target(
        TargetRecord(
            id="target-1",
            name="企业 Agent",
            base_url=base_url,
            path="/api/agent/invoke",
            headers={"X-Environment": "internal"},
            target_total_concurrency=4,
        )
    )
    run = repository.create_run(
        RunRecord(
            id="run-1",
            testset_filename="cases.xlsx",
            sheet_name="Sheet1",
            target_id=target.id,
            snapshot={"target": target.model_dump(mode="json")},
        )
    )
    case = repository.create_case_run(
        CaseRunRecord(
            id="case-run-1",
            run_id=run.id,
            case_id="case/with:unsafe-path-characters",
            row_number=2,
            question='包含 "引号"\n和中文',
        )
    )
    return repository, store, target, run, case


def _invoke(connector, *, run, case, target, **overrides):
    options = {
        "run": run,
        "case_run": case,
        "target": target,
        "request_body": {
            "question": case.question,
            "username": "tester",
            "password": "plain-secret",
        },
    }
    options.update(overrides)
    return asyncio.run(connector.invoke(**options))


def test_mock_fastapi_success_sends_exact_snapshot_and_streams_large_response(
    tmp_path,
):
    captured = {}
    large_text = "大型响应-" + "x" * (1024 * 1024)
    app = FastAPI()

    @app.post("/gateway/api/agent/invoke")
    async def invoke_agent(request: Request):
        captured["body"] = await request.body()
        captured["headers"] = dict(request.headers)
        return JSONResponse(
            {"code": 200, "msg": "正常回答", "data": {"payload": large_text}}
        )

    repository, store, target, run, case = _context(
        tmp_path, base_url="http://agent.test/gateway"
    )
    connector = FastAPIConnector(
        repository,
        store,
        transport=httpx.ASGITransport(app=app),
    )

    result = _invoke(connector, run=run, case=case, target=target)

    expected_request = json.dumps(
        {
            "question": case.question,
            "username": "tester",
            "password": "plain-secret",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert captured["body"] == expected_request
    assert captured["headers"]["x-environment"] == "internal"
    assert captured["headers"]["content-type"] == "application/json"
    assert b"case_id" not in captured["body"]
    assert store.read_bytes(result.request_artifact.relative_path) == captured["body"]
    assert store.read_json(result.response_artifact.relative_path) == {
        "code": 200,
        "msg": "正常回答",
        "data": {"payload": large_text},
    }
    assert result.attempt.status == ExecutionStatus.SUCCEEDED
    assert result.attempt.attempt_number == 1
    assert result.attempt.http_status == 200
    assert result.body_code == "200"
    assert result.response_artifact.size_bytes > 1024 * 1024
    assert result.response_artifact.retention_class == RetentionClass.SUCCESS_TEMPORARY
    artifacts = repository.list_artifacts(run.id, case_run_id=case.id)
    assert [artifact.kind for artifact in artifacts] == ["request", "response"]
    assert large_text not in json.dumps(
        repository.get_run(run.id).model_dump(mode="json"), ensure_ascii=False
    )


@pytest.mark.parametrize(
    "response_factory, expected_type, expected_body_code",
    [
        (
            lambda: httpx.Response(503, json={"code": "200", "data": {}}),
            ConnectorErrorType.HTTP_STATUS,
            None,
        ),
        (
            lambda: httpx.Response(200, content=b"{broken"),
            ConnectorErrorType.INVALID_JSON,
            None,
        ),
        (
            lambda: httpx.Response(200, json=[{"code": "200"}]),
            ConnectorErrorType.PROTOCOL_ERROR,
            None,
        ),
        (
            lambda: httpx.Response(200, json={"msg": "missing"}),
            ConnectorErrorType.PROTOCOL_ERROR,
            None,
        ),
        (
            lambda: httpx.Response(200, json={"code": 500, "msg": "failed"}),
            ConnectorErrorType.BUSINESS_ERROR,
            "500",
        ),
    ],
)
def test_response_errors_are_persisted_and_never_retried(
    tmp_path, response_factory, expected_type, expected_body_code
):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return response_factory()

    repository, store, target, run, case = _context(tmp_path)
    connector = FastAPIConnector(
        repository,
        store,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(FastAPIConnectorError) as caught:
        _invoke(
            connector,
            run=run,
            case=case,
            target=target,
            connection_retry_count=4,
        )

    error = caught.value
    assert calls == 1
    assert error.error_type == expected_type
    assert error.attempt.status == ExecutionStatus.ERROR
    assert error.attempt.error_type == expected_type.value
    assert error.attempt.body_code == expected_body_code
    assert error.attempt.finished_at is not None
    assert error.request_artifact.retention_class == RetentionClass.FAILURE_LONG_TERM
    assert error.response_artifact is not None
    assert error.response_artifact.retention_class == RetentionClass.FAILURE_LONG_TERM
    assert len(repository.list_attempts(case.id)) == 1
    assert len(repository.list_artifacts(run.id, case_run_id=case.id)) == 2


def test_connect_failures_create_independent_attempts_then_succeed(tmp_path):
    calls = 0
    sleep_intervals = []

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise httpx.ConnectError(f"connection failed {calls}", request=request)
        assert request.extensions["timeout"]["read"] == 600
        return httpx.Response(200, json={"code": "200", "data": {"ok": True}})

    async def fake_sleep(interval):
        sleep_intervals.append(interval)

    repository, store, target, run, case = _context(tmp_path)
    connector = FastAPIConnector(
        repository,
        store,
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
    )

    result = _invoke(
        connector,
        run=run,
        case=case,
        target=target,
        connection_retry_count=2,
        retry_interval_seconds=0.25,
    )

    attempts = repository.list_attempts(case.id)
    assert calls == 3
    assert sleep_intervals == [0.25, 0.25]
    assert [attempt.attempt_number for attempt in attempts] == [1, 2, 3]
    assert [attempt.status for attempt in attempts] == [
        ExecutionStatus.ERROR,
        ExecutionStatus.ERROR,
        ExecutionStatus.SUCCEEDED,
    ]
    assert [attempt.error_type for attempt in attempts] == [
        "connect_error",
        "connect_error",
        None,
    ]
    assert result.request_artifact.retention_class == RetentionClass.SUCCESS_TEMPORARY
    assert len(
        [
            artifact
            for artifact in repository.list_artifacts(run.id, case_run_id=case.id)
            if artifact.kind == "request"
        ]
    ) == 1


@pytest.mark.parametrize(
    "exception_type, expected_type",
    [
        (httpx.ConnectError, ConnectorErrorType.CONNECT_ERROR),
        (httpx.ConnectTimeout, ConnectorErrorType.CONNECT_TIMEOUT),
    ],
)
def test_exhausted_connection_errors_stop_after_configured_retries(
    tmp_path, exception_type, expected_type
):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        raise exception_type("unavailable", request=request)

    repository, store, target, run, case = _context(tmp_path)
    connector = FastAPIConnector(
        repository,
        store,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(FastAPIConnectorError) as caught:
        _invoke(
            connector,
            run=run,
            case=case,
            target=target,
            connection_retry_count=2,
        )

    assert calls == 3
    assert caught.value.error_type == expected_type
    assert len(repository.list_attempts(case.id)) == 3
    assert all(
        attempt.error_type == expected_type.value
        for attempt in repository.list_attempts(case.id)
    )
    artifacts = repository.list_artifacts(run.id, case_run_id=case.id)
    assert len(artifacts) == 1
    assert artifacts[0].kind == "request"
    assert artifacts[0].retention_class == RetentionClass.FAILURE_LONG_TERM


class _ReadTimeoutStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'{"code":"200","data":'
        raise httpx.ReadTimeout("response took too long")


def test_read_timeout_is_not_retried_and_partial_artifact_is_removed(tmp_path):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, stream=_ReadTimeoutStream())

    repository, store, target, run, case = _context(tmp_path)
    connector = FastAPIConnector(
        repository,
        store,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(FastAPIConnectorError) as caught:
        _invoke(
            connector,
            run=run,
            case=case,
            target=target,
            connection_retry_count=5,
        )

    assert calls == 1
    assert caught.value.error_type == ConnectorErrorType.READ_TIMEOUT
    attempts = repository.list_attempts(case.id)
    assert len(attempts) == 1
    assert attempts[0].http_status == 200
    assert attempts[0].error_type == "read_timeout"
    artifacts = repository.list_artifacts(run.id, case_run_id=case.id)
    assert [artifact.kind for artifact in artifacts] == ["request"]
    attempt_dir = store.root / "runs" / run.id / "cases" / case.id / "attempts"
    assert not list(attempt_dir.rglob("response.json"))
    assert not list(attempt_dir.rglob("*.tmp"))


def test_manual_case_retry_reuses_request_artifact_and_continues_attempt_numbers(
    tmp_path,
):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"code": "500"})
        return httpx.Response(200, json={"code": "200", "data": {}})

    repository, store, target, run, case = _context(tmp_path)
    transport = httpx.MockTransport(handler)

    with pytest.raises(FastAPIConnectorError):
        _invoke(
            FastAPIConnector(repository, store, transport=transport),
            run=run,
            case=case,
            target=target,
        )
    result = _invoke(
        FastAPIConnector(repository, store, transport=transport),
        run=run,
        case=case,
        target=target,
    )

    assert result.attempt.attempt_number == 2
    assert [attempt.attempt_number for attempt in repository.list_attempts(case.id)] == [
        1,
        2,
    ]
    request_artifacts = [
        artifact
        for artifact in repository.list_artifacts(run.id, case_run_id=case.id)
        if artifact.kind == "request"
    ]
    assert len(request_artifacts) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"timeout_seconds": 0},
        {"timeout_seconds": True},
        {"connection_retry_count": -1},
        {"connection_retry_count": 1.5},
        {"retry_interval_seconds": -0.1},
        {"retry_interval_seconds": True},
    ],
)
def test_invalid_run_request_parameters_fail_before_attempt(
    tmp_path, overrides
):
    repository, store, target, run, case = _context(tmp_path)
    connector = FastAPIConnector(
        repository,
        store,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"code": "200"})
        ),
    )

    with pytest.raises(ValueError):
        _invoke(connector, run=run, case=case, target=target, **overrides)

    assert repository.list_attempts(case.id) == []
    assert repository.list_artifacts(run.id, case_run_id=case.id) == []
