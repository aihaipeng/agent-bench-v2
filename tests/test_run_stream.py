from web.run_stream import LOG_TRUNCATED_MESSAGE, RunStreamError, RunStreamManager


def test_run_stream_preserves_log_order_and_terminal_result():
    manager = RunStreamManager()

    def runner(on_log):
        on_log("one\n")
        on_log("第二行\n")
        return {"ok": True, "logs": "", "response": {"answer": 42}}

    manager.start("ordered-run", runner)
    events = list(manager.iter_events("ordered-run", keepalive_seconds=0.1))

    assert events[0:2] == [
        {"type": "log", "text": "one\n"},
        {"type": "log", "text": "第二行\n"},
    ]
    assert events[-1]["type"] == "complete"
    assert events[-1]["result"]["ok"] is True
    assert events[-1]["result"]["response"] == {"answer": 42}
    assert events[-1]["result"]["logs_truncated"] is False
    assert manager.get("ordered-run") is None


def test_run_stream_truncates_at_limit_and_program_continues():
    limit = 256
    manager = RunStreamManager(max_log_bytes=limit)

    def runner(on_log):
        on_log("你" * 200)
        on_log("this must not be retained\n")
        return {"ok": True, "response": {"continued": True}}

    manager.start("truncated-run", runner)
    events = list(manager.iter_events("truncated-run", keepalive_seconds=0.1))
    displayed = "".join(
        event["text"] for event in events if event and event["type"] == "log"
    )
    terminal = events[-1]

    assert len(displayed.encode("utf-8")) <= limit
    assert LOG_TRUNCATED_MESSAGE in displayed
    assert "this must not be retained" not in displayed
    assert terminal["result"]["logs_truncated"] is True
    assert terminal["result"]["response"] == {"continued": True}


def test_run_stream_rejects_duplicate_ids_and_second_consumer():
    manager = RunStreamManager()
    release = __import__("threading").Event()

    def runner(on_log):
        release.wait(timeout=2)
        return {"ok": True}

    manager.start("single-run", runner)
    try:
        manager.start("single-run", runner)
    except RunStreamError as exc:
        assert "运行任务已存在" in str(exc)
    else:
        raise AssertionError("duplicate run id was accepted")
    release.set()
    list(manager.iter_events("single-run", keepalive_seconds=0.1))
