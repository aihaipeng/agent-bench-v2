import json
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from web import routes_tools
from web.agent_runtime import is_python_run_active
from web.app import app
from web.run_stream import RunStreamManager


def _patch_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(routes_tools, "TOOL_REGISTRY_ROOT", tmp_path / "tools")
    monkeypatch.setattr(routes_tools, "_registry_instance", None)
    monkeypatch.setattr(routes_tools, "_registry_root", None)
    monkeypatch.setattr(routes_tools, "_run_stream_manager", RunStreamManager())


def _create_tool(client, tool_type):
    return client.post(
        "/api/tools",
        json={"type": tool_type, "name": f"Stream {tool_type}"},
    ).json()["tool"]


def _parse_sse(text):
    events = []
    for block in text.split("\n\n"):
        lines = block.splitlines()
        event_line = next((line for line in lines if line.startswith("event: ")), None)
        data_line = next((line for line in lines if line.startswith("data: ")), None)
        if event_line and data_line:
            events.append(
                {
                    "type": event_line.removeprefix("event: "),
                    "data": json.loads(data_line.removeprefix("data: ")),
                }
            )
    return events


def test_script_start_returns_immediately_and_sse_streams_result(tmp_path, monkeypatch):
    _patch_runtime(tmp_path, monkeypatch)
    client = TestClient(app)
    tool = _create_tool(client, "script")

    started = client.post(
        f"/api/tools/{tool['id']}/run/start",
        json={
            "run_id": "script-sse-success",
            "script_code": "print('first')\nprint('第二行')\nresponse = {'ok': True}",
        },
    )
    response = client.get("/api/tools/runs/script-sse-success/events")
    events = _parse_sse(response.text)

    assert started.status_code == 202
    assert started.json()["run_id"] == "script-sse-success"
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [event["type"] for event in events] == ["log", "log", "complete"]
    assert events[0]["data"] == {"text": "first\n"}
    assert events[1]["data"] == {"text": "第二行\n"}
    assert events[-1]["data"]["ok"] is True
    assert events[-1]["data"]["response"] == {"ok": True}


def test_agent_stream_reports_template_failure_as_events(tmp_path, monkeypatch):
    _patch_runtime(tmp_path, monkeypatch)
    client = TestClient(app)
    tool = _create_tool(client, "agent")

    started = client.post(
        f"/api/tools/{tool['id']}/test/start",
        json={"run_id": "agent-sse-failed", "python_code": "print(${unknown})"},
    )
    response = client.get("/api/tools/runs/agent-sse-failed/events")
    events = _parse_sse(response.text)

    assert started.status_code == 202
    assert [event["type"] for event in events] == ["log", "complete"]
    assert "未知模板参数" in events[0]["data"]["text"]
    assert events[-1]["data"]["ok"] is False


def test_sse_stream_ends_with_interrupted_event(tmp_path, monkeypatch):
    _patch_runtime(tmp_path, monkeypatch)
    starter = TestClient(app)
    reader = TestClient(app)
    tool = _create_tool(starter, "script")
    run_id = "script-sse-interrupted"

    started = starter.post(
        f"/api/tools/{tool['id']}/run/start",
        json={
            "run_id": run_id,
            "script_code": "import time\nprint('started', flush=True)\ntime.sleep(30)",
        },
    )
    deadline = time.monotonic() + 5
    stream = routes_tools._run_stream_manager.get(run_id)
    while (
        stream is not None
        and stream.events.qsize() == 0
        and time.monotonic() < deadline
    ):
        time.sleep(0.02)
    assert stream is not None
    assert stream.events.qsize() > 0

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            reader.get,
            f"/api/tools/runs/{run_id}/events",
        )
        deadline = time.monotonic() + 5
        while not is_python_run_active(run_id) and time.monotonic() < deadline:
            time.sleep(0.02)

        interrupted = starter.post(f"/api/tools/runs/{run_id}/interrupt")
        response = future.result(timeout=5)

    events = _parse_sse(response.text)
    assert started.status_code == 202
    assert interrupted.status_code == 200
    assert interrupted.json()["process_terminated"] is True
    assert [event["type"] for event in events] == ["log", "interrupted"]
    assert events[0]["data"] == {"text": "started\n"}
    assert events[-1]["data"]["interrupted"] is True
