from enum import StrEnum

from pydantic import BaseModel, Field


class TestCase(BaseModel):
    """Agent 测试用例。"""

    case_id: str = Field(description="用例唯一标识")
    question: str = Field(description="发送给目标 Agent 的问题")
    tools: list[str] = Field(
        default_factory=list,
        description="期望目标 Agent 使用的工具列表",
    )


class RawAnswer(BaseModel):
    """目标 Agent 的原始响应。"""

    raw_data: dict = Field(description="目标 Agent 返回的原始数据")
    extra_data: dict = Field(description="响应中用于辅助校验的扩展数据")


class ParsedAgentAnswer(BaseModel):
    """从 Agent 原始响应中解析出的标准数据。"""

    intent_message: str = Field(description="Agent 返回的意图消息")
    reasoning_answers: list[dict] = Field(description="推理过程中的回答列表")
    tool_calls_used: list = Field(description="实际发起的工具调用列表")
    tool_invoke_count: int = Field(description="实际工具调用次数")


class ValidationContext(BaseModel):
    """所有校验器共享的稳定输入上下文。"""

    testcase: TestCase = Field(description="当前测试用例")
    raw_answer: RawAnswer = Field(description="目标 Agent 的原始响应")
    parsed: ParsedAgentAnswer = Field(description="标准化后的 Agent 响应")


class CheckStatus(StrEnum):
    """单项及整体校验状态。"""

    PASS = "PASS"
    FAILED = "FAILED"
    ERROR = "ERROR"


class CheckItem(BaseModel):
    """单项校验结果。"""

    status: CheckStatus = Field(description="该项校验状态")
    detail: str = Field(description="该项校验的说明信息")


class VerifiedData(BaseModel):
    """可扩展的完整校验结果。"""

    result: CheckStatus = Field(description="所有校验项的整体状态")
    checks: dict[str, CheckItem] = Field(description="以校验器名称索引的校验结果")


class ExcelRowResult(StrEnum):
    """写入 Excel 的最终执行状态。"""

    PASS = "PASS"
    FAILED = "FAILED"
    ERROR = "ERROR"
