from langchain.chat_models import init_chat_model

from validators import build_validators
from verifier.engine import VerificationEngine


def create_verification_engine(config: dict) -> VerificationEngine:
    """集中创建共享 LLM 及已注册校验器。

    Args:
        config: 包含 ``llm`` 节点的完整项目配置。

    Returns:
        可直接执行校验的调度引擎。
    """
    llm_cfg = config.get("llm", {})
    model = init_chat_model(
        model=llm_cfg.get("model"),
        model_provider=llm_cfg.get("provider"),
        api_key=llm_cfg.get("api_key"),
        base_url=llm_cfg.get("base_url"),
    )
    return VerificationEngine(build_validators(model))
