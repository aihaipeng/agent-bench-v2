from typing import Any

from core.models import CheckItem, CheckStatus, ValidationContext


class ToolChoiceValidator:
    name = "tool_choice"

    @classmethod
    def create(cls, model: Any) -> "ToolChoiceValidator":
        """创建不依赖 LLM 的工具选择校验器。"""
        return cls()

    @staticmethod
    def _extract_name(item: Any) -> str:
        """从标准工具调用对象或字符串中提取实际工具名。"""
        if isinstance(item, dict):
            tool_input = item.get("input", {})
            if isinstance(tool_input, dict):
                return tool_input.get("name", item.get("tool", "unknown"))
            return item.get("tool", "unknown")
        return str(item)

    async def validate(self, context: ValidationContext) -> CheckItem:
        """校验工具调用次数及期望工具覆盖情况。"""
        parsed = context.parsed
        expected_tools = context.testcase.tools
        tool_names = [self._extract_name(item) for item in parsed.tool_calls_used]
        failed_reasons: list[str] = []

        if parsed.tool_invoke_count > 10:
            failed_reasons.append(
                f"工具调用次数过多: {parsed.tool_invoke_count} > 10"
            )

        if expected_tools:
            missing = set(expected_tools) - set(tool_names)
            if missing:
                failed_reasons.append(f"期望工具未被调用: {', '.join(missing)}")

        if failed_reasons:
            return CheckItem(
                status=CheckStatus.FAILED,
                detail="; ".join(failed_reasons),
            )
        return CheckItem(
            status=CheckStatus.PASS,
            detail=(
                f"工具覆盖: {', '.join(expected_tools) if expected_tools else '无'}, "
                f"调用次数: {parsed.tool_invoke_count}"
            ),
        )
