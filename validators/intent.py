import asyncio
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from core.models import CheckItem, CheckStatus, ValidationContext
from core.prompts import INTENT_CHECK_PROMPT
from core.serializers import extract_text


class IntentValidator:
    name = "intent"

    def __init__(self, agent: Any):
        """保存负责意图判定的 LLM Agent。

        Args:
            agent: 已配置意图提示词的 LangChain Agent。
        """
        self.agent = agent

    @classmethod
    def create(cls, model: Any) -> "IntentValidator":
        """使用共享模型和意图提示词创建校验器。

        Args:
            model: VerificationFactory 创建的共享聊天模型。

        Returns:
            初始化完成的意图校验器。
        """
        return cls(create_agent(model=model, system_prompt=INTENT_CHECK_PROMPT))

    def _validate_sync(self, intent: str) -> CheckItem:
        """同步调用 Agent 并把文本结果转换为统一校验结果。

        Args:
            intent: Agent 返回的意图消息。

        Returns:
            意图检查结果。
        """
        content = f'Agent 返回的意图识别结果: "{intent}"'
        response = self.agent.invoke(
            {"messages": [HumanMessage(content=content)]}
        )
        raw = extract_text(response["messages"][-1].content).strip()
        if raw.upper() == "PASS":
            return CheckItem(status=CheckStatus.PASS, detail="意图: ASK")
        return CheckItem(
            status=CheckStatus.FAILED,
            detail=f"意图识别结果非ASK (实际: {raw})",
        )

    async def validate(self, context: ValidationContext) -> CheckItem:
        """在线程中执行意图 LLM 校验，避免阻塞事件循环。

        Args:
            context: 当前用例的共享校验上下文。

        Returns:
            意图检查结果。
        """
        return await asyncio.to_thread(
            self._validate_sync,
            context.parsed.intent_message,
        )
