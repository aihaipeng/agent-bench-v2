import math

import pytest

from execution import (
    BusinessStatus,
    ToolResultError,
    standardize_case_result,
    standardize_check_result,
    standardize_evaluator_result,
    validate_aggregator_worker_result,
    validate_case_aggregator_worker_result,
    validate_evaluator_worker_result,
    validate_parser_worker_result,
)
from web.agent_runtime import (
    run_agent_python,
    run_script_python,
    stream_agent_python,
    stream_script_python,
)


PARAMETERS = {
    "model": "model-1",
    "model_provider": "provider",
    "api_key": "secret",
    "base_url": "https://example.test",
    "system_prompt": "system",
    "human_message": "human",
}


def test_script_and_agent_receive_isolated_top_level_inputs_dictionary():
    inputs = {"question": "中文问题", "nested": {"count": 2}}
    script = run_script_python(
        "inputs['nested']['count'] += 1\nresponse = inputs",
        inputs=inputs,
        strict_response_json=True,
    )
    agent = run_agent_python(
        "response = {'model': ${model}, 'question': inputs['question']}",
        PARAMETERS,
        inputs=inputs,
        strict_response_json=True,
    )

    assert script == {
        "ok": True,
        "logs": "",
        "response": {"question": "中文问题", "nested": {"count": 3}},
    }
    assert agent["response"] == {"model": "model-1", "question": "中文问题"}
    assert inputs == {"question": "中文问题", "nested": {"count": 2}}


def test_inputs_default_to_empty_dictionary_for_backward_compatibility():
    result = run_script_python(
        "response = {'input_type': type(inputs).__name__, 'size': len(inputs)}",
        strict_response_json=True,
    )

    assert result["response"] == {"input_type": "dict", "size": 0}


def test_stream_script_and_agent_receive_inputs_before_logs_and_result():
    script_logs = []
    agent_logs = []

    script = stream_script_python(
        "print(inputs['line'])\nresponse = inputs['value']",
        script_logs.append,
        "workflow-script-inputs",
        inputs={"line": "脚本日志", "value": [1, 2]},
        strict_response_json=True,
    )
    agent = stream_agent_python(
        "print(inputs['line'])\nresponse = {'value': inputs['value']}",
        PARAMETERS,
        agent_logs.append,
        "workflow-agent-inputs",
        inputs={"line": "Agent 日志", "value": True},
        strict_response_json=True,
    )

    assert script_logs == ["脚本日志\n"]
    assert script["response"] == [1, 2]
    assert agent_logs == ["Agent 日志\n"]
    assert agent["response"] == {"value": True}


@pytest.mark.parametrize(
    "inputs",
    [
        [],
        {"not_json": {1, 2}},
        {"nan": math.nan},
    ],
)
def test_invalid_inputs_are_rejected_before_worker_start(inputs):
    with pytest.raises(ValueError, match="inputs"):
        run_script_python("response = True", inputs=inputs)


def test_strict_workflow_mode_rejects_repr_fallback_and_nonstandard_nan():
    custom_object_code = "class Custom: pass\nresponse = Custom()"
    loose = run_script_python(custom_object_code)
    strict_object = run_script_python(
        custom_object_code,
        strict_response_json=True,
    )
    strict_nan = run_script_python(
        "response = float('nan')",
        strict_response_json=True,
    )

    assert loose["ok"] is True
    assert isinstance(loose["response"], str)
    assert "Custom object" in loose["response"]
    assert strict_object["ok"] is False
    assert "执行失败" in strict_object["logs"]
    assert strict_nan["ok"] is False
    assert "response 包含 NaN 或 Infinity" in strict_nan["logs"]


@pytest.mark.parametrize("response", [None, True, 7, "text", [], [1, 2], {}, {"a": 1}])
def test_parser_accepts_every_standard_json_shape(response):
    worker_result = {"ok": True, "logs": "", "response": response}

    assert validate_parser_worker_result(worker_result) == response


def test_parser_requires_success_and_explicit_response():
    with pytest.raises(ToolResultError, match="执行失败"):
        validate_parser_worker_result({"ok": False, "logs": "boom"})
    with pytest.raises(ToolResultError, match="顶层 response"):
        validate_parser_worker_result({"ok": True, "logs": ""})


@pytest.mark.parametrize("status", ["PASS", "FAIL", "ERROR", "SKIP"])
def test_evaluator_accepts_confirmed_status_enum_and_defaults_data(status):
    result = validate_evaluator_worker_result(
        {
            "ok": True,
            "logs": "",
            "response": {"status": status, "reason": "判断说明"},
        }
    )

    assert result == {"status": status, "reason": "判断说明", "data": {}}


@pytest.mark.parametrize(
    "response",
    [
        {"status": "pass", "reason": "wrong case"},
        {"status": "PASS"},
        {"status": "PASS", "reason": 123},
        {"status": "PASS", "reason": "ok", "case_id": "forbidden"},
        {"status": "PASS", "reason": "ok", "evaluator_id": "forbidden"},
        ["PASS", "reason"],
    ],
)
def test_evaluator_rejects_invalid_enum_fields_and_system_context(response):
    with pytest.raises(ToolResultError, match="结构错误"):
        validate_evaluator_worker_result(
            {"ok": True, "logs": "", "response": response}
        )


def test_real_worker_evaluator_response_is_validated_end_to_end():
    worker = run_agent_python(
        "response = {'status': 'FAIL', 'reason': inputs['reason'], "
        "'data': {'score': inputs['score']}}",
        PARAMETERS,
        inputs={"reason": "意图不准确", "score": 0.2},
        strict_response_json=True,
    )

    assert validate_evaluator_worker_result(worker) == {
        "status": "FAIL",
        "reason": "意图不准确",
        "data": {"score": 0.2},
    }


def test_aggregator_contracts_distinguish_check_and_case_reason():
    check = validate_aggregator_worker_result(
        {
            "ok": True,
            "response": {"status": "FAIL", "reason": "一个步骤失败"},
        }
    )
    case = validate_case_aggregator_worker_result(
        {"ok": True, "response": {"status": "FAIL"}}
    )

    assert check == {"status": "FAIL", "reason": "一个步骤失败"}
    assert case == {"status": "FAIL", "reason": ""}
    with pytest.raises(ToolResultError, match="结构错误"):
        validate_aggregator_worker_result(
            {"ok": True, "response": {"status": "FAIL"}}
        )


def test_system_standardization_adds_context_and_preserves_all_details():
    intent_step = standardize_evaluator_result(
        {"status": "FAIL", "reason": "意图错误", "data": {"score": 0.1}},
        case_id="case_001",
        check_item="intent",
        step_id="intent_agent",
    )
    rule_step = standardize_evaluator_result(
        {"status": "PASS", "reason": "规则通过", "data": {}},
        case_id="case_001",
        check_item="intent",
        step_id="intent_rule",
    )
    intent_check = standardize_check_result(
        {"status": "FAIL", "reason": "语义步骤失败"},
        case_id="case_001",
        check_item="intent",
        step_results={
            "intent_agent": intent_step,
            "intent_rule": rule_step,
        },
    )
    i18n_check = standardize_check_result(
        {"status": "PASS", "reason": "语言检查通过"},
        case_id="case_001",
        check_item="i18n",
        step_results={
            "i18n_agent": standardize_evaluator_result(
                {"status": "PASS", "reason": "中文", "data": {}},
                case_id="case_001",
                check_item="i18n",
                step_id="i18n_agent",
            )
        },
    )
    case_result = standardize_case_result(
        {"status": "FAIL"},
        case_id="case_001",
        check_results={"intent": intent_check, "i18n": i18n_check},
    )

    assert intent_step == {
        "case_id": "case_001",
        "check_item": "intent",
        "step_id": "intent_agent",
        "status": "FAIL",
        "reason": "意图错误",
        "data": {"score": 0.1},
    }
    assert set(intent_check["step_results"]) == {"intent_agent", "intent_rule"}
    assert case_result["status"] == BusinessStatus.FAIL
    assert set(case_result["check_items"]) == {"intent", "i18n"}
    assert case_result["check_items"]["intent"]["step_results"][
        "intent_agent"
    ]["reason"] == "意图错误"
    assert "evaluator_id" not in str(case_result)
