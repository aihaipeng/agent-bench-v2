import json
import time

from fastapi.testclient import TestClient

from web import routes_tool_templates
from web.app import app
from web.run_stream import RunStreamManager
from web.tool_runtime import is_tool_run_active


def _patch_runtime(tmp_path, monkeypatch):
    root = tmp_path / "tool_registry"
    monkeypatch.setattr(routes_tool_templates, "TOOL_TEMPLATE_ROOT", root)
    monkeypatch.setattr(routes_tool_templates, "_repository_instance", None)
    monkeypatch.setattr(routes_tool_templates, "_repository_root", None)
    monkeypatch.setattr(routes_tool_templates, "_run_stream_manager", RunStreamManager())
    return TestClient(app)


def _create_script(client, code):
    template = client.post(
        "/api/tool-templates", json={"type": "SCRIPT", "name": "Runnable"}
    ).json()["template"]
    template_id = template["manifest"]["id"]
    response = client.put(
        f"/api/tool-templates/{template_id}",
        json={
            "name": "Runnable",
            "inputs": [{"name": "question", "type": "STRING", "required": True}],
            "outputs": [{"name": "answer", "type": "STRING"}],
            "config": {"prefix": "answer"},
            "main_py": code,
        },
    )
    assert response.status_code == 200
    return template_id


def _sse_events(text):
    events = []
    for block in text.split("\n\n"):
        data_line = next(
            (line[6:] for line in block.splitlines() if line.startswith("data: ")),
            None,
        )
        if data_line:
            events.append(json.loads(data_line))
    return events


def test_template_run_streams_logs_and_strict_response(tmp_path, monkeypatch):
    client = _patch_runtime(tmp_path, monkeypatch)
    template_id = _create_script(
        client,
        'print("started", flush=True)\nresponse = {"answer": config["prefix"] + ":" + inputs["question"]}',
    )

    started = client.post(
        f"/api/tool-templates/{template_id}/runs",
        json={"run_id": "api-success", "inputs": {"question": "hello"}},
    )
    streamed = client.get("/api/tool-templates/runs/api-success/events")
    events = _sse_events(streamed.text)

    assert started.status_code == 200
    assert started.json() == {"run_id": "api-success", "status": "RUNNING"}
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert events[0] == {"type": "log", "text": "started\n"}
    assert events[-1]["type"] == "complete"
    assert events[-1]["result"]["ok"] is True
    assert events[-1]["result"]["response"] == {"answer": "answer:hello"}
    assert events[-1]["result"]["latency_ms"] >= 0


def test_template_run_reports_failure_without_repr_fallback(tmp_path, monkeypatch):
    client = _patch_runtime(tmp_path, monkeypatch)
    template_id = _create_script(client, "response = float('nan')")

    assert client.post(
        f"/api/tool-templates/{template_id}/runs",
        json={"run_id": "api-failure", "inputs": {}},
    ).status_code == 200
    events = _sse_events(
        client.get("/api/tool-templates/runs/api-failure/events").text
    )

    assert any(event["type"] == "log" and "Traceback" in event["text"] for event in events)
    assert events[-1]["result"]["ok"] is False
    assert "NaN" in events[-1]["result"]["error"]


def test_template_run_rejects_duplicate_id_and_supports_interrupt(tmp_path, monkeypatch):
    client = _patch_runtime(tmp_path, monkeypatch)
    template_id = _create_script(
        client, "import time\ntime.sleep(10)\nresponse = {}"
    )
    start_url = f"/api/tool-templates/{template_id}/runs"

    first = client.post(start_url, json={"run_id": "api-interrupt", "inputs": {}})
    duplicate = client.post(start_url, json={"run_id": "api-interrupt", "inputs": {}})
    deadline = time.monotonic() + 5
    while not is_tool_run_active("api-interrupt") and time.monotonic() < deadline:
        time.sleep(0.01)
    interrupted = client.post(
        "/api/tool-templates/runs/api-interrupt/interrupt"
    )
    events = _sse_events(
        client.get("/api/tool-templates/runs/api-interrupt/events").text
    )

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert interrupted.status_code == 200
    assert interrupted.json()["interrupted"] is True
    assert events[-1]["type"] == "interrupted"
    assert events[-1]["result"]["interrupted"] is True
    assert client.get("/api/tool-templates/runs/missing/events").status_code == 404
