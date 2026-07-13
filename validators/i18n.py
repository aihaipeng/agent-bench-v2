import asyncio
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from core.models import CheckItem, CheckStatus, ValidationContext
from core.prompts import I18N_CHECK_PROMPT
from core.serializers import extract_text


I18N_CHECK_FIELDS = ("text", "reasoning")
MAX_FORMAT_ATTEMPTS = 2


class I18nValidator:
    name = "i18n"

    def __init__(self, agent: Any):
        """保存负责中文输出合规判定的 LLM Agent。"""
        self.agent = agent

    @classmethod
    def create(cls, model: Any) -> "I18nValidator":
        """使用共享模型和 i18n 提示词创建校验器。"""
        return cls(create_agent(model=model, system_prompt=I18N_CHECK_PROMPT))

    @staticmethod
    def _build_content(reasoning_answers: list[dict]) -> tuple[str, int]:
        """把所有待审查字段合并成带安全边界标签的批量输入。"""
        blocks: list[str] = []
        for index, record in enumerate(reasoning_answers):
            if not isinstance(record, dict):
                continue
            for field in I18N_CHECK_FIELDS:
                value = record.get(field, "")
                content = value if isinstance(value, str) else str(value)
                if content.strip():
                    blocks.append(
                        f'<field id="{field}#{index}">\n{content}\n</field>'
                    )
        return "\n\n".join(blocks), len(blocks)

    def _invoke(self, content: str) -> str:
        """调用 LLM Agent 并提取规范化文本响应。"""
        response = self.agent.invoke(
            {"messages": [HumanMessage(content=content)]}
        )
        return extract_text(response["messages"][-1].content).strip()

    def _validate_sync(self, reasoning_answers: list[dict]) -> CheckItem:
        """同步执行批量中文合规检查和格式异常重试。"""
        content, field_count = self._build_content(reasoning_answers)
        if not field_count:
            return CheckItem(
                status=CheckStatus.PASS,
                detail="无非空内容需要校验",
            )

        raw = ""
        for attempt in range(MAX_FORMAT_ATTEMPTS):
            request = content
            if attempt:
                request += (
                    "\n\n上一次返回格式不合规。请重新审查，并且最终只输出一个单词："
                    "PASS 或 FAILED。"
                )
            raw = self._invoke(request)
            if raw.upper() == "PASS":
                return CheckItem(
                    status=CheckStatus.PASS,
                    detail=f"{field_count} 个字段全部中文合规",
                )
            if raw.upper() == "FAILED":
                return CheckItem(
                    status=CheckStatus.FAILED,
                    detail=f"{field_count} 个字段中至少一个包含英文自然语言句子",
                )

        return CheckItem(
            status=CheckStatus.FAILED,
            detail=f"i18n 校验返回格式异常: {raw or '<empty>'}",
        )

    async def validate(self, context: ValidationContext) -> CheckItem:
        """在线程中执行 i18n LLM 校验，避免阻塞事件循环。"""
        return await asyncio.to_thread(
            self._validate_sync,
            context.parsed.reasoning_answers,
        )
