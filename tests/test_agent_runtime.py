import pytest

from web.agent_runtime import (
    AgentTemplateError,
    compile_agent_template,
    migrate_legacy_agent_template,
    run_agent_python,
)


PARAMETERS = {
    "model": 'model-"quoted"',
    "model_provider": "provider",
    "api_key": "secret-key",
    "base_url": "https://example.test/v1",
    "system_prompt": "",
    "human_message": "line 1\nline 2",
}


def test_compile_agent_template_uses_python_literals_and_none():
    compiled = compile_agent_template(
        "values = [${model}, ${system_prompt}, ${human_message}]",
        PARAMETERS,
    )

    namespace = {}
    exec(compiled, namespace)
    assert namespace["values"] == ['model-"quoted"', None, "line 1\nline 2"]


def test_literal_values_override_fields_and_commented_placeholders_do_not_execute():
    compiled = compile_agent_template(
        'model = "hard-coded"\n# ignored = ${model}\nresponse = model',
        PARAMETERS,
    )

    namespace = {}
    exec(compiled, namespace)
    assert namespace["response"] == "hard-coded"
    assert "# ignored = 'model-\"quoted\"'" in compiled


def test_compile_agent_template_rejects_unknown_placeholder():
    with pytest.raises(AgentTemplateError, match="unknown_value"):
        compile_agent_template("response = ${unknown_value}", PARAMETERS)


def test_compile_agent_template_rejects_malformed_placeholder():
    with pytest.raises(AgentTemplateError, match="无法识别"):
        compile_agent_template("response = ${model", PARAMETERS)


def test_compile_agent_template_allows_nested_python_dicts():
    compiled = compile_agent_template(
        'response = {"model": ${model}, "extra_body": {"thinking": {"type": "disabled"}}}',
        PARAMETERS,
    )

    namespace = {}
    exec(compiled, namespace)
    assert namespace["response"] == {
        "model": 'model-"quoted"',
        "extra_body": {"thinking": {"type": "disabled"}},
    }


def test_compile_agent_template_allows_sets_and_nested_json():
    compiled = compile_agent_template(
        'import json\nresponse = {"values": {"one", "two"}, "payload": '
        'json.loads(\'{"outer": {"items": [{"enabled": true}]}}\'), "model": ${model}}',
        PARAMETERS,
    )

    namespace = {}
    exec(compiled, namespace)
    assert namespace["response"]["values"] == {"one", "two"}
    assert namespace["response"]["payload"] == {
        "outer": {"items": [{"enabled": True}]}
    }
    assert namespace["response"]["model"] == 'model-"quoted"'


def test_migrate_legacy_agent_template_only_changes_placeholders():
    legacy = (
        'response = {"model": {{model}}, '
        '"extra_body": {"thinking": {"type": "disabled"}}}'
    )

    assert migrate_legacy_agent_template(legacy) == (
        'response = {"model": ${model}, '
        '"extra_body": {"thinking": {"type": "disabled"}}}'
    )


def test_worker_supports_imports_and_only_returns_user_print_output():
    result = run_agent_python(
        "import math\nprint('sqrt', math.sqrt(81))\nresponse = {'ok': True}",
        PARAMETERS,
    )

    assert result["ok"] is True
    assert "sqrt 9.0" in result["logs"]
    assert "'ok': True" not in result["logs"]


def test_worker_allows_user_editable_rich_print():
    result = run_agent_python(
        "from rich import print\nresponse = {'ok': True}\nprint(response)",
        PARAMETERS,
    )

    assert result["ok"] is True
    assert "'ok': True" in result["logs"]


def test_worker_success_can_have_empty_logs():
    result = run_agent_python("response = {'ok': True}", PARAMETERS)

    assert result == {"ok": True, "logs": ""}


def test_worker_requires_response_and_returns_traceback():
    result = run_agent_python("print('before failure')", PARAMETERS)

    assert result["ok"] is False
    assert "before failure" in result["logs"]
    assert "必须给顶层变量 response 赋值" in result["logs"]
    assert "Traceback" in result["logs"]


def test_worker_times_out_and_terminates_process():
    result = run_agent_python(
        "import time\ntime.sleep(5)\nresponse = None",
        PARAMETERS,
        timeout_seconds=0.2,
    )

    assert result["ok"] is False
    assert "执行超时" in result["logs"]


def test_worker_redacts_api_key_from_logs():
    result = run_agent_python(
        "print(${api_key})\nraise RuntimeError(${api_key})",
        PARAMETERS,
    )

    assert result["ok"] is False
    assert "secret-key" not in result["logs"]
    assert "***" in result["logs"]


def test_worker_protocol_preserves_unicode_outside_gbk():
    result = run_agent_python(
        "print('中文日志 🍖')\nresponse = {'message': '执行成功 🍖'}\nprint(response)",
        PARAMETERS,
    )

    assert result["ok"] is True
    assert "中文日志 🍖" in result["logs"]
    assert "执行成功 🍖" in result["logs"]
