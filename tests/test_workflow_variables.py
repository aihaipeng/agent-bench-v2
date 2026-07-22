import pytest

from execution import (
    OUTPUT_VARIABLE_TYPES,
    WorkflowVariableError,
    convert_output_value,
    extract_output_variables,
    extract_script_output_variables,
    extract_path_expression,
    nearest_ancestor_output_sources,
)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("response.usage.total_tokens", 42),
        ('response.usage["total_tokens"]', 42),
        ("response.usage['total_tokens']", 42),
        ("response.usage[total_tokens]", 42),
        ("response.choices[0].message.content", "完成"),
        ("response.choices[-1].message.content", "完成"),
        ("request.messages[0][content]", "请判断"),
        ("response.data[id==3].name", "目标"),
        ('response.data[status=="PASSED"].id', 3),
        ("response.data[meta.id==3].name", "目标"),
        ("response.data[id<3].name", "其他"),
        ("response.data[id<=2].name", "其他"),
        ("response.data[id>3].name", "最后"),
        ("response.data[id>=4].name", "最后"),
        ('response.data[risk!="LOW"].id', 2),
        ('response.data[name contain "目标"].id', 3),
    ],
)
def test_safe_python_style_path_extraction(expression, expected):
    context = {
        "request": {"messages": [{"content": "请判断"}]},
        "response": {
            "usage": {"total_tokens": 42},
            "choices": [{"message": {"content": "完成"}}],
            "data": [
                {
                    "id": 2,
                    "name": "其他",
                    "status": "FAILED",
                    "risk": "HIGH",
                    "meta": {"id": 2},
                },
                {"id": 3, "name": "目标", "status": "PASSED", "meta": {"id": 3}},
                {"id": 4, "name": "最后", "status": "REVIEW", "meta": {"id": 4}},
            ],
        },
    }

    assert extract_path_expression(context, expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "payload.value",
        "response.get('usage')",
        "response.items[0:1]",
        "response.items[missing-key]",
        "response.items[]",
        "response.data[id=3]",
        "response.data[id==]",
        "response.data[name contain 3]",
        "response.data[id between 1]",
    ],
)
def test_path_extraction_rejects_unsupported_python(expression):
    with pytest.raises(WorkflowVariableError):
        extract_path_expression({"request": {}, "response": {}}, expression)


def test_missing_path_reports_full_expression():
    expression = "response.choices[1].message.content"

    with pytest.raises(WorkflowVariableError, match=r"response\.choices\[1\]"):
        extract_path_expression(
            {"request": {}, "response": {"choices": []}}, expression
        )


@pytest.mark.parametrize(
    "response",
    [
        {"data": []},
        {"data": [{"id": 3}, {"id": 3}]},
    ],
)
def test_filter_requires_exactly_one_match(response):
    with pytest.raises(WorkflowVariableError, match="不是唯一"):
        extract_path_expression(
            {"request": {}, "response": response},
            "response.data[id==3]",
        )


@pytest.mark.parametrize("node_type", ["HTTP", "LLM", "AGENT"])
def test_output_mapping_contract_is_shared_by_every_node_type(node_type):
    node = {
        "data": {
            "nodeType": node_type,
            "outputVariables": [
                {"name": "sent_model", "type": "STRING", "value": "request.model"},
                {"name": "answer", "value": "response.result[answer]"},
            ],
        }
    }

    assert extract_output_variables(
        node,
        request={"model": "model-1"},
        response={"result": {"answer": "通过"}},
    ) == {"sent_model": "model-1", "answer": "通过"}


def test_script_output_mapping_uses_python_top_level_variables_and_aliases():
    node = {
        "data": {
            "nodeType": "SCRIPT",
            "outputVariables": [
                {
                    "name": "message",
                    "pythonVariable": "msg",
                    "type": "STRING",
                },
                {
                    "name": "quality_score",
                    "pythonVariable": "score",
                    "type": "INTEGER",
                },
            ],
        }
    }

    assert extract_script_output_variables(
        node, {"msg": "介绍一下自己", "score": "95"}
    ) == {"message": "介绍一下自己", "quality_score": 95}


def test_script_output_mapping_defaults_missing_source_to_output_name():
    missing = {
        "data": {
            "nodeType": "SCRIPT",
            "outputVariables": [
                {"name": "message", "pythonVariable": "msg", "type": "STRING"}
            ],
        }
    }
    assert extract_script_output_variables(missing, {}) == {"message": None}

    legacy = {
        "data": {
            "nodeType": "SCRIPT",
            "outputVariables": [
                {"name": "message", "value": "response.stdout"}
            ],
        }
    }
    assert extract_script_output_variables(legacy, {"message": "ok"}) == {
        "message": "ok"
    }


def test_nearest_ancestor_output_source_overrides_farther_source():
    def node(node_id, output_name=None):
        mappings = [] if output_name is None else [
            {"name": output_name, "value": "response.value"}
        ]
        return {
            "id": node_id,
            "data": {"nodeType": "HTTP", "label": node_id, "outputVariables": mappings},
        }

    nodes = [node("far", "message"), node("near", "message"), node("current")]
    edges = [
        {"source": "far", "target": "near"},
        {"source": "near", "target": "current"},
    ]

    assert nearest_ancestor_output_sources(nodes, edges, "current") == {
        "message": "near"
    }


def test_equal_distance_output_sources_are_rejected_as_ambiguous():
    nodes = [
        {
            "id": node_id,
            "data": {
                "nodeType": "HTTP",
                "label": node_id,
                "outputVariables": [
                    {"name": "message", "value": "response.value"}
                ] if node_id != "current" else [],
            },
        }
        for node_id in ("left", "right", "current")
    ]
    edges = [
        {"source": "left", "target": "current"},
        {"source": "right", "target": "current"},
    ]

    with pytest.raises(WorkflowVariableError, match="变量名等距冲突: message"):
        nearest_ancestor_output_sources(nodes, edges, "current")


@pytest.mark.parametrize(
    ("value", "output_type", "expected"),
    [
        ({"id": 3}, "AUTO", {"id": 3}),
        ({"id": 3}, "STRING", '{"id": 3}'),
        ("42", "INTEGER", 42),
        (42.0, "INTEGER", 42),
        ("1.25", "NUMBER", 1.25),
        ("2e3", "NUMBER", 2000.0),
        ("false", "BOOLEAN", False),
        (1, "BOOLEAN", True),
        ('{"id": 3}', "OBJECT", {"id": 3}),
        ("[1, 2]", "ARRAY", [1, 2]),
    ],
)
def test_output_value_conversion(value, output_type, expected):
    assert convert_output_value(value, output_type, variable_name="result") == expected


@pytest.mark.parametrize("output_type", OUTPUT_VARIABLE_TYPES)
def test_null_remains_null_for_every_output_type(output_type):
    assert convert_output_value(None, output_type, variable_name="result") is None


@pytest.mark.parametrize(
    ("value", "output_type"),
    [
        ("3.1", "INTEGER"),
        (True, "NUMBER"),
        ("yes", "BOOLEAN"),
        ("[]", "OBJECT"),
        ("{}", "ARRAY"),
    ],
)
def test_output_value_conversion_failure_names_variable_and_type(value, output_type):
    with pytest.raises(
        WorkflowVariableError,
        match=rf"输出变量 result 转换失败.*{output_type}",
    ):
        convert_output_value(value, output_type, variable_name="result")


def test_output_mapping_rejects_unknown_type():
    node = {
        "data": {
            "outputVariables": [
                {"name": "result", "type": "DATE", "value": "response.result"}
            ]
        }
    }

    with pytest.raises(WorkflowVariableError, match="不支持的输出变量类型: DATE"):
        extract_output_variables(node, request={}, response={"result": "2026-07-22"})
