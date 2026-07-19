import asyncio

import pytest

from execution import (
    BusinessStatus,
    CaseRunRecord,
    ExecutionStatus,
    RunRecord,
    RunRepository,
)
from web.run_events import RunEventBroker, monitor_run_events


def test_events_published_before_subscription_are_not_replayed():
    async def scenario():
        broker = RunEventBroker()

        assert await broker.publish(
            "run-1",
            {"type": "run_state", "status": "QUEUED"},
        ) == 0

        async with broker.subscribe("run-1") as subscription:
            events = subscription.iter_events(keepalive_seconds=0.01)
            assert await anext(events) is None

            assert await broker.publish(
                "run-1",
                {"type": "run_state", "status": "RUNNING"},
            ) == 1
            assert await anext(events) == {
                "type": "run_state",
                "status": "RUNNING",
            }
            await events.aclose()

    asyncio.run(scenario())


def test_live_events_are_broadcast_in_order_to_each_subscriber():
    async def scenario():
        broker = RunEventBroker()

        async with broker.subscribe("run-1") as first:
            async with broker.subscribe("run-1") as second:
                assert await broker.subscriber_count("run-1") == 2
                events = [
                    {"type": "case_state", "case_run_id": "case-1"},
                    {"type": "run_state", "status": "RUNNING"},
                    {"type": "run_terminal", "status": "SUCCEEDED"},
                ]
                for event in events:
                    assert await broker.publish("run-1", event) == 2

                assert [event async for event in first.iter_events()] == events
                assert [event async for event in second.iter_events()] == events

        assert await broker.subscriber_count("run-1") == 0

    asyncio.run(scenario())


def test_disconnected_subscriber_is_removed_without_affecting_others():
    async def scenario():
        broker = RunEventBroker()

        async with broker.subscribe("run-1") as remaining:
            async with broker.subscribe("run-1"):
                assert await broker.subscriber_count("run-1") == 2
            assert await broker.subscriber_count("run-1") == 1

            event = {"type": "run_terminal", "status": "CANCELLED"}
            assert await broker.publish("run-1", event) == 1
            assert await anext(remaining.iter_events()) == event

    asyncio.run(scenario())


def test_subscription_wait_can_be_cancelled_cleanly():
    async def scenario():
        broker = RunEventBroker()

        async with broker.subscribe("run-1") as subscription:
            stream = subscription.iter_events(keepalive_seconds=60)
            waiting = asyncio.create_task(anext(stream))
            await asyncio.sleep(0)
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
            await stream.aclose()

        assert await broker.subscriber_count("run-1") == 0

    asyncio.run(scenario())


def test_broker_rejects_invalid_run_id_and_event_type():
    async def scenario():
        broker = RunEventBroker()

        with pytest.raises(ValueError, match="run_id"):
            async with broker.subscribe(" "):
                pass
        with pytest.raises(ValueError, match="run_id"):
            await broker.publish(" ", {"type": "run_state"})
        with pytest.raises(ValueError, match="type"):
            await broker.publish("run-1", {"status": "RUNNING"})

    asyncio.run(scenario())


def test_monitor_publishes_persisted_state_changes_and_terminal_event(tmp_path):
    async def scenario():
        repository = RunRepository(tmp_path / "agent_bench.sqlite3")
        run = repository.create_run(
            RunRecord(
                id="run-1",
                testset_filename="cases.xlsx",
                sheet_name="Sheet1",
            )
        )
        case = repository.create_case_run(
            CaseRunRecord(
                id="case-1",
                run_id=run.id,
                case_id="case_001",
                row_number=2,
                question="问题",
            )
        )
        broker = RunEventBroker()

        async def execute():
            await asyncio.sleep(0.02)
            repository.update_run_status(run.id, ExecutionStatus.RUNNING)
            repository.update_case_run_status(case.id, ExecutionStatus.RUNNING)
            await asyncio.sleep(0.02)
            repository.update_case_run_status(
                case.id,
                ExecutionStatus.SUCCEEDED,
                business_status=BusinessStatus.PASS,
            )
            return repository.update_run_status(
                run.id,
                ExecutionStatus.SUCCEEDED,
                business_status=BusinessStatus.PASS,
            )

        async with broker.subscribe(run.id) as subscription:
            scheduler_task = asyncio.create_task(execute())
            monitor = asyncio.create_task(
                monitor_run_events(
                    repository,
                    broker,
                    run.id,
                    scheduler_task,
                    poll_interval_seconds=0.005,
                )
            )
            events = [event async for event in subscription.iter_events()]
            await monitor

        assert events[-1]["type"] == "run_terminal"
        assert events[-1]["run"]["status"] == "SUCCEEDED"
        assert any(
            event["type"] == "run_state"
            and event["run"]["status"] == "RUNNING"
            for event in events
        )
        assert any(
            event["type"] == "case_state"
            and event["case"]["status"] == "SUCCEEDED"
            for event in events
        )

    asyncio.run(scenario())
