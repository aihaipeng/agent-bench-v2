from typing import Protocol

from core.models import CheckItem, ValidationContext


class Validator(Protocol):
    """所有校验点必须实现的最小接口。"""

    name: str

    async def validate(self, context: ValidationContext) -> CheckItem:
        """校验一个 Agent 响应并返回单项结果。"""
        ...
