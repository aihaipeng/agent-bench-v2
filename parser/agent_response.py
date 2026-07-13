from core.models import ParsedAgentAnswer, RawAnswer


class ParserError(Exception):
    """Agent 响应结构解析失败。"""


def parse_agent_answer(raw_answer: RawAnswer, case_id: str) -> ParsedAgentAnswer:
    """将目标 Agent 原始响应转换为与校验规则无关的标准结构。"""
    raw_data = raw_answer.raw_data
    data = raw_data.get("data")
    if not isinstance(data, dict):
        raise ParserError(f"[{case_id}] Agent 响应缺少 data 对象")
    cur_answer = data.get("curAnswer")
    if not isinstance(cur_answer, dict):
        raise ParserError(f"[{case_id}] Agent 响应缺少 data.curAnswer 对象")

    content = cur_answer.get("content")
    containers = [content, cur_answer] if isinstance(content, dict) else [cur_answer]
    outputs = next(
        (
            container.get("outputs")
            for container in containers
            if isinstance(container.get("outputs"), dict)
        ),
        None,
    )
    if not isinstance(outputs, dict):
        raise ParserError(f"[{case_id}] Agent 响应缺少 outputs 对象")
    output = outputs.get("output", [])
    if output is None:
        output = []
    if not isinstance(output, list):
        raise ParserError(f"[{case_id}] outputs.output 必须是列表")

    reasoning_answers = outputs.get("reasoning_answers")
    if not isinstance(reasoning_answers, list) or not reasoning_answers:
        raise ParserError(f"[{case_id}] reasoning_answers 为空或不存在")
    intent_message = (
        reasoning_answers[0].get("reasoning", "")
        if isinstance(reasoning_answers[0], dict)
        else ""
    )

    tool_calls: list[dict] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        parts = item.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict) or part.get("type") != "tool":
                continue
            state = part.get("state", {})
            tool_calls.append(
                {
                    "tool": part.get("tool", "unknown"),
                    "input": (
                        state.get("input", {}) if isinstance(state, dict) else {}
                    ),
                }
            )

    return ParsedAgentAnswer(
        intent_message=intent_message,
        reasoning_answers=reasoning_answers,
        tool_calls_used=tool_calls,
        tool_invoke_count=len(tool_calls),
    )
