import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from web.tool_execution import execute_tool_template
from web.tool_runtime import interrupt_tool_run, is_tool_run_active
from web.tool_templates import (
    AgentDefinition,
    HttpConfig,
    HttpDefinition,
    LlmDefinition,
    ScriptDefinition,
    TemplateManifest,
    ToolTemplate,
)


def _manifest(template_id: str, template_type: str) -> TemplateManifest:
    return TemplateManifest(
        id=template_id,
        type=template_type,
        name=f"{template_type} Template",
        created_at="2026-07-20T00:00:00Z",
        updated_at="2026-07-20T00:00:00Z",
    )


def _python_template(template_type: str, code: str, config=None) -> ToolTemplate:
    definition_class = {
        "AGENT": AgentDefinition,
        "LLM": LlmDefinition,
        "SCRIPT": ScriptDefinition,
    }[template_type]
    return ToolTemplate(
        manifest=_manifest(f"{template_type.lower()}-template", template_type),
        definition=definition_class(type=template_type, config=config or {}),
        main_py=code,
    )


@pytest.mark.parametrize("template_type", ["AGENT", "LLM", "SCRIPT"])
def test_python_templates_share_inputs_config_response_protocol(template_type):
    logs = []
    template = _python_template(
        template_type,
        'print("working", end="", flush=True)\nresponse = {"value": inputs["value"] + config["suffix"]}',
        {"suffix": "!"},
    )

    result = execute_tool_template(
        template,
        {"value": template_type},
        logs.append,
        f"run-{template_type.lower()}",
    )

    assert result == {"ok": True, "response": {"value": f"{template_type}!"}}
    assert "".join(logs) == "working"


def test_python_template_rejects_non_json_response_and_reports_traceback():
    logs = []
    template = _python_template("SCRIPT", "response = float('nan')")

    result = execute_tool_template(template, {}, logs.append, "run-invalid-json")

    assert result["ok"] is False
    assert "NaN" in result["error"]
    assert "Infinity" in result["error"]
    assert "Traceback" in "".join(logs)


def test_python_template_timeout_terminates_worker():
    template = _python_template("SCRIPT", "import time\ntime.sleep(10)\nresponse = {}")
    logs = []

    result = execute_tool_template(
        template,
        {},
        logs.append,
        "run-timeout",
        timeout_seconds=0.2,
    )

    assert result == {"ok": False, "timed_out": True}
    assert "执行超时" in "".join(logs)
    assert not is_tool_run_active("run-timeout")


def test_python_template_can_be_interrupted():
    template = _python_template("AGENT", "import time\ntime.sleep(10)\nresponse = {}")
    holder = {}

    thread = threading.Thread(
        target=lambda: holder.setdefault(
            "result",
            execute_tool_template(template, {}, lambda _text: None, "run-interrupt"),
        )
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not is_tool_run_active("run-interrupt") and time.monotonic() < deadline:
        time.sleep(0.01)

    assert is_tool_run_active("run-interrupt")
    assert interrupt_tool_run("run-interrupt") is True
    thread.join(timeout=5)

    assert holder["result"] == {"ok": False, "interrupted": True}
    assert not is_tool_run_active("run-interrupt")


def test_http_config_template_executes_real_request():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(length))
            payload = json.dumps(
                {
                    "path": self.path,
                    "body": body,
                    "header": self.headers.get("x-template"),
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
        template = ToolTemplate(
            manifest=_manifest("http-template", "HTTP"),
            definition=HttpDefinition(
                type="HTTP",
                execution_mode="CONFIG",
                http=HttpConfig(
                    method="POST",
                    url=f"http://127.0.0.1:{server.server_port}/execute?mode=test",
                    headers={"x-template": "yes"},
                    body_type="RAW",
                    body={"question": "hello"},
                ),
            ),
        )

        result = execute_tool_template(
            template, {}, lambda _text: None, "run-http-config"
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
