"""Workflow variable visibility, validation, substitution, and output mapping."""

from __future__ import annotations

import ast
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from execution.llm_node_execution import LlmNodeConfigurationError, resolve_prompt_template


class WorkflowVariableError(LlmNodeConfigurationError):
    pass


OUTPUT_VARIABLE_TYPES = (
    "AUTO",
    "STRING",
    "INTEGER",
    "NUMBER",
    "BOOLEAN",
    "OBJECT",
    "ARRAY",
)


@dataclass(frozen=True)
class _FilterToken:
    field_path: str
    operator: str
    expected: Any


def node_output_mappings(node: dict[str, Any]) -> list[dict[str, str]]:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    raw_mappings = data.get("outputVariables")
    if not isinstance(raw_mappings, list):
        return []
    mappings: list[dict[str, str]] = []
    for raw in raw_mappings:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name").strip() if isinstance(raw.get("name"), str) else ""
        path = raw.get("value").strip() if isinstance(raw.get("value"), str) else ""
        output_type = _normalize_output_type(raw.get("type"))
        if name:
            mappings.append({"name": name, "path": path, "type": output_type})
    return mappings


def ancestor_node_ids(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    node_id: str,
) -> list[str]:
    incoming: dict[str, list[str]] = {}
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if isinstance(source, str) and isinstance(target, str):
            incoming.setdefault(target, []).append(source)
    visited: set[str] = set()
    pending = list(incoming.get(node_id, []))
    while pending:
        current = pending.pop()
        if current == node_id or current in visited:
            continue
        visited.add(current)
        pending.extend(incoming.get(current, []))
    return [node["id"] for node in nodes if node.get("id") in visited]


def validate_visible_variable_names(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    global_variables: list[dict[str, Any]],
) -> None:
    global_sources: list[tuple[str, str]] = []
    seen_global: dict[str, str] = {}
    for record in global_variables:
        if not isinstance(record, dict):
            raise WorkflowVariableError("Workflow 全局变量必须是对象")
        name = record.get("name").strip() if isinstance(record.get("name"), str) else ""
        if not name:
            continue
        if name in seen_global:
            raise WorkflowVariableError(f"全局变量重名: {name}")
        seen_global[name] = "全局变量"
        global_sources.append((name, "全局变量"))

    node_by_id = {node["id"]: node for node in nodes}
    for node in nodes:
        current_id = node["id"]
        visible = list(global_sources)
        for ancestor_id in ancestor_node_ids(nodes, edges, current_id):
            ancestor = node_by_id[ancestor_id]
            label = _node_label(ancestor)
            visible.extend((mapping["name"], label) for mapping in node_output_mappings(ancestor))
        current_label = _node_label(node)
        visible.extend((mapping["name"], current_label) for mapping in node_output_mappings(node))
        sources: dict[str, str] = {}
        for name, source in visible:
            if name in sources:
                raise WorkflowVariableError(
                    f"变量名冲突: {name} ({sources[name]} / {source})"
                )
            sources[name] = source


def resolve_templates(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return resolve_prompt_template(value, variables) if "${" in value else value
    if isinstance(value, list):
        return [resolve_templates(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: resolve_templates(item, variables) for key, item in value.items()}
    return value


def extract_output_variables(
    node: dict[str, Any],
    *,
    request: Any,
    response: Any,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    context = {"request": request, "response": response}
    for mapping in node_output_mappings(node):
        path = mapping["path"]
        if not path:
            raise WorkflowVariableError(
                f"输出变量缺少路径: {mapping['name']}"
            )
        extracted = extract_path_expression(context, path)
        values[mapping["name"]] = convert_output_value(
            extracted,
            mapping["type"],
            variable_name=mapping["name"],
        )
    return values


def convert_output_value(
    value: Any,
    output_type: str,
    *,
    variable_name: str = "",
) -> Any:
    """Convert an extracted value using the shared strict output contract."""

    target = _normalize_output_type(output_type)
    if value is None or target == "AUTO":
        return value
    try:
        if target == "STRING":
            return variable_text(value)
        if target == "INTEGER":
            if isinstance(value, bool):
                raise ValueError
            if isinstance(value, int):
                return value
            if isinstance(value, float) and math.isfinite(value) and value.is_integer():
                return int(value)
            if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
                return int(value.strip())
            raise ValueError
        if target == "NUMBER":
            if isinstance(value, bool):
                raise ValueError
            if isinstance(value, (int, float)) and math.isfinite(value):
                return value
            if isinstance(value, str):
                source = value.strip()
                if re.fullmatch(
                    r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?",
                    source,
                ):
                    converted = float(source) if any(mark in source for mark in ".eE") else int(source)
                    if math.isfinite(converted):
                        return converted
            raise ValueError
        if target == "BOOLEAN":
            if isinstance(value, bool):
                return value
            if isinstance(value, int) and value in {0, 1}:
                return bool(value)
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"true", "1"}:
                    return True
                if normalized in {"false", "0"}:
                    return False
            raise ValueError
        if target in {"OBJECT", "ARRAY"}:
            converted = json.loads(value) if isinstance(value, str) else value
            expected_type = dict if target == "OBJECT" else list
            if isinstance(converted, expected_type):
                return converted
            raise ValueError
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise WorkflowVariableError(
            _conversion_error_message(variable_name, value, target)
        ) from exc
    raise WorkflowVariableError(f"不支持的输出变量类型: {target}")


def _normalize_output_type(value: Any) -> str:
    if value is None or value == "":
        return "AUTO"
    if not isinstance(value, str):
        raise WorkflowVariableError("输出变量类型必须是字符串")
    normalized = value.strip().upper()
    if normalized not in OUTPUT_VARIABLE_TYPES:
        raise WorkflowVariableError(f"不支持的输出变量类型: {normalized}")
    return normalized


def _conversion_error_message(variable_name: str, value: Any, target: str) -> str:
    source = variable_text(value)
    if len(source) > 160:
        source = f"{source[:157]}..."
    label = f"输出变量 {variable_name}" if variable_name else "输出变量"
    return f"{label} 转换失败：无法将 {source!r} 转换为 {target}"


def extract_path_expression(context: dict[str, Any], expression: str) -> Any:
    """Resolve a restricted Python-style request/response path without eval()."""

    path = expression.strip()
    if not path:
        raise WorkflowVariableError("提取表达式不能为空")
    root, tokens = _parse_path_expression(path)
    if root not in {"request", "response"}:
        raise WorkflowVariableError(
            f"提取表达式必须以 request 或 response 开头: {path}"
        )
    if root not in context:
        raise WorkflowVariableError(f"提取根对象不存在: {root} ({path})")
    current = context[root]
    for token in tokens:
        if isinstance(token, _FilterToken):
            if not isinstance(current, list):
                raise WorkflowVariableError(
                    f"提取过滤器只能用于数组: {path}"
                )
            matches = [
                item
                for item in current
                if isinstance(item, dict)
                and _filter_matches(item, token)
            ]
            if len(matches) != 1:
                raise WorkflowVariableError(
                    f"提取过滤器匹配结果不是唯一: {path}，匹配 {len(matches)} 条"
                )
            current = matches[0]
            continue
        if isinstance(current, dict):
            if token not in current:
                raise WorkflowVariableError(
                    f"提取路径不存在: {path}，缺少键 {token!r}"
                )
            current = current[token]
            continue
        if isinstance(current, (list, tuple)) and isinstance(token, int):
            if -len(current) <= token < len(current):
                current = current[token]
                continue
            raise WorkflowVariableError(
                f"提取路径不存在: {path}，下标 {token} 越界"
            )
        raise WorkflowVariableError(
            f"提取路径不可继续访问: {path}，当前值类型为 {type(current).__name__}"
        )
    return current


def _parse_path_expression(
    expression: str,
) -> tuple[str, list[str | int | _FilterToken]]:
    length = len(expression)
    cursor = 0
    while cursor < length and (expression[cursor] == "_" or expression[cursor].isalnum()):
        cursor += 1
    root = expression[:cursor]
    if not root or not root.isidentifier():
        raise WorkflowVariableError(f"提取表达式无效: {expression}")
    tokens: list[str | int | _FilterToken] = []
    while cursor < length:
        character = expression[cursor]
        if character == ".":
            cursor += 1
            start = cursor
            while cursor < length and expression[cursor] not in ".[":
                cursor += 1
            key = expression[start:cursor].strip()
            if not key or not key.isidentifier():
                raise WorkflowVariableError(f"提取表达式无效: {expression}")
            tokens.append(key)
            continue
        if character == "[":
            end = _find_bracket_end(expression, cursor)
            content = expression[cursor + 1 : end].strip()
            tokens.append(_parse_bracket_token(content, expression))
            cursor = end + 1
            continue
        raise WorkflowVariableError(f"提取表达式无效: {expression}")
    return root, tokens


def _find_bracket_end(expression: str, start: int) -> int:
    quote: str | None = None
    escaped = False
    for cursor in range(start + 1, len(expression)):
        character = expression[cursor]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "]":
            return cursor
    raise WorkflowVariableError(f"提取表达式缺少 ]: {expression}")


def _parse_bracket_token(content: str, expression: str) -> str | int | _FilterToken:
    if not content:
        raise WorkflowVariableError(f"提取表达式包含空下标: {expression}")
    field_pattern = r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
    filter_match = re.fullmatch(
        rf"{field_pattern}\s*(==|!=|<=|>=|<|>)\s*(.+)", content
    )
    if filter_match is None:
        filter_match = re.fullmatch(
            rf"{field_pattern}\s+(contain)\s+(.+)", content
        )
    if filter_match:
        expected = _parse_filter_literal(filter_match.group(3).strip(), expression)
        operator = filter_match.group(2)
        if operator == "contain" and not isinstance(expected, str):
            raise WorkflowVariableError(
                f"contain 只支持字符串比较: {expression}"
            )
        return _FilterToken(
            field_path=filter_match.group(1),
            operator=operator,
            expected=expected,
        )
    if content[0] in {"'", '"'}:
        try:
            value = ast.literal_eval(content)
        except (SyntaxError, ValueError) as exc:
            raise WorkflowVariableError(f"提取字符串键无效: {expression}") from exc
        if not isinstance(value, str):
            raise WorkflowVariableError(f"提取下标只支持字符串或整数: {expression}")
        return value
    if content.lstrip("-").isdigit():
        return int(content)
    if content.isidentifier():
        return content
    raise WorkflowVariableError(f"提取下标无效: {expression}")


_MISSING = object()


def _read_filter_field(item: dict[str, Any], field_path: str) -> Any:
    current: Any = item
    for field in field_path.split("."):
        if not isinstance(current, dict) or field not in current:
            return _MISSING
        current = current[field]
    return current


def _filter_matches(item: dict[str, Any], token: _FilterToken) -> bool:
    actual = _read_filter_field(item, token.field_path)
    if actual is _MISSING:
        return False
    if token.operator == "==":
        return _filter_values_equal(actual, token.expected)
    if token.operator == "!=":
        return not _filter_values_equal(actual, token.expected)
    if token.operator == "contain":
        return isinstance(actual, str) and token.expected in actual
    comparable = _filter_comparable_values(actual, token.expected)
    if comparable is None:
        return False
    left, right = comparable
    if token.operator == "<":
        return left < right
    if token.operator == ">":
        return left > right
    if token.operator == "<=":
        return left <= right
    if token.operator == ">=":
        return left >= right
    return False


def _filter_values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _filter_comparable_values(left: Any, right: Any) -> tuple[Any, Any] | None:
    if isinstance(left, bool) or isinstance(right, bool):
        return None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left, right
    if isinstance(left, str) and isinstance(right, str):
        return left, right
    return None


def _parse_filter_literal(value: str, expression: str) -> Any:
    if not value:
        raise WorkflowVariableError(f"过滤条件缺少比较值: {expression}")
    if value[0] in {"'", '"'}:
        try:
            literal = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise WorkflowVariableError(f"过滤条件字符串无效: {expression}") from exc
        if not isinstance(literal, str):
            raise WorkflowVariableError(f"过滤条件只支持标量值: {expression}")
        return literal
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None"}:
        return None
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        if value.isidentifier():
            return value
        raise WorkflowVariableError(f"过滤条件值无效: {expression}")


def variable_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _node_label(node: dict[str, Any]) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    label = data.get("label")
    return label.strip() if isinstance(label, str) and label.strip() else node["id"]
