import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from web.tool_runtime import (
    interrupt_tool_run,
    is_tool_run_active,
    stream_tool_worker,
)


def _python_payload(code: str, config=None, inputs=None) -> dict:
    return {
        "mode": "PYTHON",
        "code": code,
        "inputs": inputs or {},
        "config": config or {},
    }


def test_python_worker_shares_inputs_config_response_protocol():
    logs = []
    payload = _python_payload(
        'print("working", end="", flush=True)\nresponse = {"value": inputs["value"] + config["suffix"]}',
        config={"suffix": "!"},
        inputs={"value": "Workflow"},
    )

    result = stream_tool_worker(payload, logs.append, "run-python")

    assert result == {
        "ok": True,
        "response": {"value": "Workflow!"},
        "stdout": "working",
        "stderr": "",
    }
    assert "".join(logs) == "working"


def test_python_worker_rejects_non_json_response_and_reports_traceback():
    logs = []

    result = stream_tool_worker(
        _python_payload("response = float('nan')"),
        logs.append,
        "run-invalid-json",
    )

    assert result["ok"] is False
    assert "NaN" in result["error"]
    assert "Infinity" in result["error"]
    assert "Traceback" in "".join(logs)
    assert "Traceback" in result["stderr"]


def test_python_worker_timeout_terminates_process():
    logs = []

    result = stream_tool_worker(
        _python_payload("import time\ntime.sleep(10)\nresponse = {}"),
        logs.append,
        "run-timeout",
        timeout_seconds=0.2,
    )

    assert result == {
        "ok": False,
        "timed_out": True,
        "stdout": "",
        "stderr": "执行超时，已终止子进程（0.2 秒）\n",
    }
    assert "执行超时" in "".join(logs)
    assert not is_tool_run_active("run-timeout")


def test_python_worker_can_be_interrupted():
    holder = {}
    thread = threading.Thread(
        target=lambda: holder.setdefault(
            "result",
            stream_tool_worker(
                _python_payload("import time\ntime.sleep(10)\nresponse = {}"),
                lambda _text: None,
                "run-interrupt",
            ),
        )
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not is_tool_run_active("run-interrupt") and time.monotonic() < deadline:
        time.sleep(0.01)

    assert is_tool_run_active("run-interrupt")
    assert interrupt_tool_run("run-interrupt") is True
    thread.join(timeout=5)

    assert holder["result"] == {
        "ok": False,
        "interrupted": True,
        "stdout": "",
        "stderr": "",
    }
    assert not is_tool_run_active("run-interrupt")


def test_http_worker_executes_real_request():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(length))
            payload = json.dumps(
                {
                    "path": self.path,
                    "body": body,
                    "header": self.headers.get("x-workflow"),
                }
            ).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = stream_tool_worker(
            {
                "mode": "HTTP_CONFIG",
                "inputs": {},
                "config": {},
                "http": {
                    "method": "POST",
                    "url": f"http://127.0.0.1:{server.server_port}/execute?mode=test",
                    "headers": {"x-workflow": "yes"},
                    "params": {},
                    "body_type": "RAW",
                    "body": {"question": "hello"},
                },
            },
            lambda _text: None,
            "run-http-config",
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result["ok"] is True
    assert result["response"]["status_code"] == 200
    assert result["response"]["body"] == {
        "path": "/execute?mode=test",
        "body": {"question": "hello"},
        "header": "yes",
    }
