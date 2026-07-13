from typing import Any

from validators.i18n import I18nValidator
from validators.intent import IntentValidator
from validators.protocol import Validator
from validators.tool_choice import ToolChoiceValidator


# 新增校验点时，只需实现统一接口并在这里注册一行。
VALIDATOR_TYPES = (
    IntentValidator,
    I18nValidator,
    ToolChoiceValidator,
)


def build_validators(model: Any) -> list[Validator]:
    """使用共享模型实例化所有显式注册的校验器。"""
    return [validator_type.create(model) for validator_type in VALIDATOR_TYPES]
