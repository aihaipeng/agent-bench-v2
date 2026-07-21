"""Active execution-domain exports."""

from execution.targets import (
    DEFAULT_DATABASE_PATH,
    TargetConfiguration,
    TargetHttpMethod,
    TargetRecord,
    TargetRepository,
    TargetRepositoryError,
)
from execution.model_providers import (
    ModelProviderConfiguration,
    ModelProviderProtocol,
    ModelProviderRecord,
    ModelProviderRepository,
    ModelProviderRepositoryError,
    ModelProviderSummary,
)
from execution.model_gateway import (
    build_chat_completion_request,
    chat_completions_url,
    deep_merge_model_request,
    invoke_openai_compatible,
)

__all__ = [
    "DEFAULT_DATABASE_PATH",
    "ModelProviderConfiguration",
    "ModelProviderProtocol",
    "ModelProviderRecord",
    "ModelProviderRepository",
    "ModelProviderRepositoryError",
    "ModelProviderSummary",
    "build_chat_completion_request",
    "chat_completions_url",
    "deep_merge_model_request",
    "invoke_openai_compatible",
    "TargetConfiguration",
    "TargetHttpMethod",
    "TargetRecord",
    "TargetRepository",
    "TargetRepositoryError",
]
