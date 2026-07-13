import asyncio

from core.models import (
    CheckItem,
    CheckStatus,
    ValidationContext,
    VerifiedData,
)
from validators.protocol import Validator


class VerificationEngine:
    """并行调度已注册校验器，不感知具体校验点。"""

    def __init__(self, validators: list[Validator]):
        """保存校验器，并拒绝可能覆盖结果的重复名称。"""
        names = [validator.name for validator in validators]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"校验器名称重复: {', '.join(duplicates)}")
        self.validators = validators

    async def verify(self, context: ValidationContext) -> VerifiedData:
        """并行执行全部校验器，隔离异常并计算整体状态。"""
        raw_results = await asyncio.gather(
            *(validator.validate(context) for validator in self.validators),
            return_exceptions=True,
        )
        checks: dict[str, CheckItem] = {}
        for validator, result in zip(self.validators, raw_results):
            if isinstance(result, BaseException):
                result = CheckItem(
                    status=CheckStatus.ERROR,
                    detail=f"{type(result).__name__}: {result}",
                )
            checks[validator.name] = result

        statuses = {item.status for item in checks.values()}
        if CheckStatus.ERROR in statuses:
            overall = CheckStatus.ERROR
        elif CheckStatus.FAILED in statuses:
            overall = CheckStatus.FAILED
        else:
            overall = CheckStatus.PASS
        return VerifiedData(result=overall, checks=checks)
