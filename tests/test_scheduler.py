import asyncio
import hashlib
from collections import defaultdict

import httpx
import pytest

from execution import (
    ArtifactStore,
    AttemptRecord,
    BusinessStatus,
    CaseWorkflowExecutor,
    CaseRunRecord,
    ExecutionStatus,
    FastAPIConnector,
    RunRecord,
    RunRepository,
    RunScheduler,
    SchedulerError,
    StepRunRecord,
    StepStage,
    TargetRecord,
    TargetRequestCoordinator,
    WorkflowDefinition,
    WorkflowRecord,
)
from web.agent_runtime import is_python_run_active


def _target(limit=2):
    return TargetRecord(
        id="shared-target",
        name="Shared Target",
        base_url="http://agent.test",
        path="/api/agent/invoke",
        target_total_concurrency=limit,
    )


def _create_run(
    repository,
    target,
    run_id,
    *,
    case_count=6,
    case_concurrency=3,
    status=ExecutionStatus.QUEUED,
):
    run = repository.create_run(
        RunRecord(
            id=run_id,
            testset_filename=f"{run_id}.xlsx",
            sheet_name="Sheet1",
            target_id=target.id,
            status=status,
            parameters={
                "timeout_seconds": 600,
                "case_concurrency": case_concurrency,
                "connection_retry_count": 0,
                "retry_interval_seconds": 0,
            },
            snapshot={
                "target": target.model_dump(mode="json"),
                "request_template": {
                    "question": "${question}",
                    "username": "tester",
                },
                "workflow": {"workflow": {}, "tools": {}},
            },
        )
    )
    cases = []
    for index in range(case_count):
        cases.append(
            repository.create_case_run(
                CaseRunRecord(
                    id=f"{run_id}-case-{index}",
                    run_id=run.id,
                    case_id=f"{run_id}_{index}",
                    row_number=index + 2,
                    question=f"问题 {run_id} {index}",
                )
            )
        )
    return run, cases


class _RecordingCaseExecutor:
    def __init__(self, repository, *, request_delay=0.025, tool_delay=0.025):
        self.repository = repository
        self.request_delay = request_delay
        self.tool_delay = tool_delay
        self.active_cases = defaultdict(int)
        self.max_active_cases = defaultdict(int)
        self.active_requests = 0
        self.max_active_requests = 0
        self.started = []
        self.request_order = []
        self.request_bodies = {}
        self.started_event = asyncio.Event()

    async def execute(
        self,
        *,
        run,
        case_run,
        request_slot,
        request_body,
        **kwargs,
    ):
        self.started.append(case_run.id)
        self.request_bodies[case_run.id] = request_body
        self.active_cases[run.id] += 1
        self.max_active_cases[run.id] = max(
            self.max_active_cases[run.id],
            self.active_cases[run.id],
        )
        self.repository.update_case_run_status(
            case_run.id,
            ExecutionStatus.RUNNING,
            business_status=None,
            error=None,
        )
        if len(self.started) >= 2:
            self.started_event.set()
        try:
            async with request_slot:
                self.active_requests += 1
                self.max_active_requests = max(
                    self.max_active_requests,
                    self.active_requests,
                )
                self.request_order.append(run.id)
                try:
                    await asyncio.sleep(self.request_delay)
                finally:
                    self.active_requests -= 1
            await asyncio.sleep(self.tool_delay)
            self.repository.update_case_run_status(
                case_run.id,
                ExecutionStatus.SUCCEEDED,
                business_status=BusinessStatus.PASS,
                error=None,
            )
        except asyncio.CancelledError:
            self.repository.update_case_run_status(
                case_run.id,
                ExecutionStatus.CANCELLED,
                error="fake executor cancelled",
            )
            raise
        finally:
            self.active_cases[run.id] -= 1


def test_overlapping_runs_obey_dual_limits_and_round_robin_target_slots(tmp_path):
    repository = RunRepository(tmp_path / "agent_bench.sqlite3")
    target = repository.create_target(_target(limit=2))
    run_a, cases_a = _create_run(
        repository, target, "run-a", case_count=7, case_concurrency=3
    )
    run_b, cases_b = _create_run(
        repository, target, "run-b", case_count=4, case_concurrency=2
    )
    executor = _RecordingCaseExecutor(repository)
    scheduler = RunScheduler(repository, executor)

    async def scenario():
        task_a = await scheduler.start_run(run_a.id)
        await asyncio.sleep(0.01)
        task_b = await scheduler.start_run(run_b.id)
        return await asyncio.gather(task_a, task_b)

    completed_a, completed_b = asyncio.run(scenario())

    assert completed_a.status == ExecutionStatus.SUCCEEDED
    assert completed_b.status == ExecutionStatus.SUCCEEDED
    assert executor.max_active_cases[run_a.id] <= 3
    assert executor.max_active_cases[run_b.id] <= 2
    assert executor.max_active_requests <= 2
    first_b = executor.request_order.index(run_b.id)
    assert first_b < len(cases_a)
    assert run_b.id in executor.request_order[:4]
    assert all(
        repository.get_case_run(case.id).status == ExecutionStatus.SUCCEEDED
        for case in cases_a + cases_b
    )
    assert executor.request_bodies[cases_a[0].id] == {
        "question": cases_a[0].question,
        "username": "tester",
    }
    assert "case_id" not in executor.request_bodies[cases_a[0].id]


def test_target_coordinator_uses_conservative_limit_across_frozen_run_snapshots():
    coordinator = TargetRequestCoordinator()

    async def scenario():
        await coordinator.register_run("target", "old-run", 5)
        await coordinator.register_run("target", "new-run", 2)
        during = await coordinator.stats("target")
        await coordinator.unregister_run("target", "new-run")
        after = await coordinator.stats("target")
        await coordinator.unregister_run("target", "old-run")
        return during, after

    during, after = asyncio.run(scenario())

    assert during["limit"] == 2
    assert after["limit"] == 5


def test_cancel_stops_dispatch_and_cancels_active_case_tasks(tmp_path):
    repository = RunRepository(tmp_path / "agent_bench.sqlite3")
    target = repository.create_target(_target(limit=1))
    run, cases = _create_run(
        repository,
        target,
        "cancel-run",
        case_count=8,
        case_concurrency=2,
    )
    executor = _RecordingCaseExecutor(
        repository,
        request_delay=5,
        tool_delay=5,
    )
    scheduler = RunScheduler(repository, executor)

    async def scenario():
        task = await scheduler.start_run(run.id)
        await asyncio.wait_for(executor.started_event.wait(), timeout=2)
        was_active = await scheduler.cancel_run(run.id)
        completed = await task
        return was_active, completed

    was_active, completed = asyncio.run(scenario())

    assert was_active is True
    assert completed.status == ExecutionStatus.CANCELLED
    assert completed.cancel_requested is True
    assert len(executor.started) == 2
    restored_cases = repository.list_case_runs(run.id)
    assert all(case.status == ExecutionStatus.CANCELLED for case in restored_cases)
    assert scheduler.is_active(run.id) is False


def test_manual_resume_skips_succeeded_fail_case_and_closes_stale_records(tmp_path):
    repository = RunRepository(tmp_path / "agent_bench.sqlite3")
    target = repository.create_target(_target(limit=2))
    run, cases = _create_run(
        repository,
        target,
        "resume-run",
        case_count=5,
        case_concurrency=2,
        status=ExecutionStatus.RUNNING,
    )
    succeeded, failed, cancelled, stale, queued = cases
    repository.update_case_run_status(
        succeeded.id,
        ExecutionStatus.SUCCEEDED,
        business_status=BusinessStatus.FAIL,
    )
    repository.update_case_run_status(
        failed.id,
        ExecutionStatus.ERROR,
        business_status=BusinessStatus.ERROR,
    )
    repository.update_case_run_status(cancelled.id, ExecutionStatus.CANCELLED)
    repository.update_case_run_status(stale.id, ExecutionStatus.RUNNING)
    attempt = repository.create_attempt(
        AttemptRecord(
            id="stale-attempt",
            case_run_id=stale.id,
            attempt_number=1,
            status=ExecutionStatus.RUNNING,
        )
    )
    step = repository.create_step_run(
        StepRunRecord(
            id="stale-step",
            case_run_id=stale.id,
            stage=StepStage.PARSER,
            step_id="parser",
            status=ExecutionStatus.RUNNING,
        )
    )
    executor = _RecordingCaseExecutor(repository, request_delay=0, tool_delay=0)
    scheduler = RunScheduler(repository, executor)

    assert executor.started == []
    assert repository.get_case_run(stale.id).status == ExecutionStatus.RUNNING

    async def scenario():
        task = await scheduler.resume_run(run.id)
        return await task

    completed = asyncio.run(scenario())

    assert succeeded.id not in executor.started
    assert set(executor.started) == {failed.id, cancelled.id, stale.id, queued.id}
    assert repository.list_attempts(stale.id)[0].id == attempt.id
    assert repository.list_attempts(stale.id)[0].status == ExecutionStatus.ERROR
    assert repository.list_attempts(stale.id)[0].error_type == "service_interrupted"
    assert next(
        item for item in repository.list_step_runs(stale.id) if item.id == step.id
    ).status == ExecutionStatus.ERROR
    assert completed.status == ExecutionStatus.SUCCEEDED
    assert completed.business_status == BusinessStatus.FAIL
    assert completed.cancel_requested is False


def test_resume_selection_rejects_succeeded_cases_and_duplicate_active_run(tmp_path):
    repository = RunRepository(tmp_path / "agent_bench.sqlite3")
    target = repository.create_target(_target())
    run, cases = _create_run(repository, target, "selection-run", case_count=2)
    repository.update_case_run_status(
        cases[0].id,
        ExecutionStatus.SUCCEEDED,
        business_status=BusinessStatus.PASS,
    )
    repository.update_run_status(run.id, ExecutionStatus.ERROR)
    executor = _RecordingCaseExecutor(repository, request_delay=0.1, tool_delay=0.1)
    scheduler = RunScheduler(repository, executor)

    async def invalid_selection():
        with pytest.raises(SchedulerError, match="不可恢复"):
            await scheduler.resume_run(run.id, {cases[0].id})

    asyncio.run(invalid_selection())

    async def duplicate_active():
        task = await scheduler.resume_run(run.id, {cases[1].id})
        with pytest.raises(SchedulerError, match="已在执行"):
            await scheduler.resume_run(run.id, {cases[1].id})
        await task

    asyncio.run(duplicate_active())


def test_invalid_run_parameters_fail_without_starting_cases(tmp_path):
    repository = RunRepository(tmp_path / "agent_bench.sqlite3")
    target = repository.create_target(_target())
    run, cases = _create_run(repository, target, "invalid-run", case_count=1)
    broken = repository.get_run(run.id)
    with repository.transaction() as connection:
        connection.execute(
            "UPDATE runs SET parameters_json = ? WHERE id = ?",
            ('{"case_concurrency":0}', run.id),
        )
    executor = _RecordingCaseExecutor(repository)
    scheduler = RunScheduler(repository, executor)

    async def scenario():
        with pytest.raises(SchedulerError, match="参数无效"):
            await scheduler.start_run(run.id)

    asyncio.run(scenario())

    assert executor.started == []
    assert repository.get_case_run(cases[0].id).status == ExecutionStatus.QUEUED
    assert broken.status == ExecutionStatus.QUEUED


def _real_scheduler_context(tmp_path, *, transport, evaluator_code):
    repository = RunRepository(tmp_path / "agent_bench.sqlite3")
    store = ArtifactStore(tmp_path / "artifacts")
    target = repository.create_target(_target(limit=1))
    definition = WorkflowDefinition.model_validate(
        {
            "checks": [
                {
                    "check_item": "intent",
                    "evaluators": [
                        {"step_id": "evaluator", "tool_id": "evaluator-tool"}
                    ],
                }
            ]
        }
    )
    workflow = WorkflowRecord(
        id="workflow-real",
        name="Real",
        definition=definition.model_dump(mode="json"),
    )
    tool = {
        "id": "evaluator-tool",
        "type": "script",
        "name": "Evaluator",
        "code": evaluator_code,
        "code_sha256": hashlib.sha256(evaluator_code.encode("utf-8")).hexdigest(),
        "parameters": {},
    }
    run = repository.create_run(
        RunRecord(
            id="real-run",
            testset_filename="cases.xlsx",
            sheet_name="Sheet1",
            target_id=target.id,
            parameters={"case_concurrency": 1},
            snapshot={
                "target": target.model_dump(mode="json"),
                "request_template": {"question": "${question}"},
                "workflow": {
                    "schema_version": 1,
                    "workflow": workflow.model_dump(mode="json"),
                    "tools": {"evaluator-tool": tool},
                },
            },
        )
    )
    case = repository.create_case_run(
        CaseRunRecord(
            id="real-case",
            run_id=run.id,
            case_id="case_001",
            row_number=2,
            question="问题",
        )
    )
    connector = FastAPIConnector(repository, store, transport=transport)
    case_executor = CaseWorkflowExecutor(repository, store, connector)
    return repository, RunScheduler(repository, case_executor), run, case


class _BlockingResponseStream(httpx.AsyncByteStream):
    def __init__(self, started):
        self.started = started

    async def __aiter__(self):
        self.started.set()
        await asyncio.Event().wait()
        yield b"never"


def test_cancel_interrupts_real_http_response_wait_without_partial_artifact(tmp_path):
    async def scenario():
        response_started = asyncio.Event()

        async def handler(request):
            return httpx.Response(200, stream=_BlockingResponseStream(response_started))

        repository, scheduler, run, case = _real_scheduler_context(
            tmp_path,
            transport=httpx.MockTransport(handler),
            evaluator_code="response = {'status': 'PASS', 'reason': 'unused'}",
        )
        task = await scheduler.start_run(run.id)
        await asyncio.wait_for(response_started.wait(), timeout=2)
        await scheduler.cancel_run(run.id)
        completed = await task
        return repository, completed, case

    repository, completed, case = asyncio.run(scenario())

    assert completed.status == ExecutionStatus.CANCELLED
    attempts = repository.list_attempts(case.id)
    assert len(attempts) == 1
    assert attempts[0].status == ExecutionStatus.CANCELLED
    assert attempts[0].error_type == "cancelled"
    assert [
        artifact.kind
        for artifact in repository.list_artifacts(completed.id, case_run_id=case.id)
    ] == ["request"]


def test_cancel_interrupts_real_script_worker_and_persists_cancelled_step(tmp_path):
    async def handler(request):
        return httpx.Response(200, json={"code": "200", "data": {}})

    evaluator_code = (
        "import time\n"
        "print('worker started', flush=True)\n"
        "time.sleep(30)\n"
        "response = {'status': 'PASS', 'reason': 'finished'}"
    )

    async def scenario():
        repository, scheduler, run, case = _real_scheduler_context(
            tmp_path,
            transport=httpx.MockTransport(handler),
            evaluator_code=evaluator_code,
        )
        task = await scheduler.start_run(run.id)
        deadline = asyncio.get_running_loop().time() + 5
        step = None
        while asyncio.get_running_loop().time() < deadline:
            steps = repository.list_step_runs(case.id)
            if steps and is_python_run_active(steps[0].id):
                step = steps[0]
                break
            await asyncio.sleep(0.02)
        assert step is not None
        await scheduler.cancel_run(run.id)
        completed = await task
        return repository, completed, case, step

    repository, completed, case, step = asyncio.run(scenario())

    assert completed.status == ExecutionStatus.CANCELLED
    restored_step = next(
        item for item in repository.list_step_runs(case.id) if item.id == step.id
    )
    assert restored_step.status == ExecutionStatus.CANCELLED
    assert repository.get_case_run(case.id).status == ExecutionStatus.CANCELLED
    assert is_python_run_active(step.id) is False
