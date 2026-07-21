"""Framework-independent model request composition and HTTP transport."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


def deep_merge_model_request(
    *layers: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge request layers recursively, with later layers taking precedence."""

    merged: dict[str, Any] = {}
    for layer in layers:
        if layer is None:
            continue
        if not isinstance(layer, Mapping):
            raise TypeError("模型请求参数必须是 JSON 对象")
        merged = _merge_objects(merged, layer)
    return merged


def _merge_objects(
    base: Mapping[str, Any], override: Mapping[str, Any]
) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            result[key] = _merge_objects(current, value)
        else:
            result[key] = deepcopy(value)
    return result


def build_chat_completion_request(
    *,
    model_name: str,
    messages: Sequence[Mapping[str, Any]],
    model_defaults: Mapping[str, Any] | None = None,
    model_parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a chat request where model defaults and node parameters may override all fields."""

    base_request = {
        "model": model_name,
        "messages": [deepcopy(dict(message)) for message in messages],
        "stream": False,
    }
    return deep_merge_model_request(
        base_request,
        model_defaults,
        model_parameters,
    )


def chat_completions_url(base_url: str) -> str:
    parsed = urlsplit(base_url.strip().rstrip("/"))
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("BASE_URL 必须是有效的 HTTP 或 HTTPS 地址")
    path = parsed.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        path = f"{path}/chat/completions"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


async def invoke_openai_compatible(
    *,
    base_url: str,
    api_key: str,
    request_body: Mapping[str, Any],
    timeout_seconds: float = 120,
    client: httpx.AsyncClient | None = None,
) -> httpx.Response:
    """Send a prepared request without translating provider-specific parameters."""

    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout_seconds,
    )
    try:
        return await active_client.post(
            chat_completions_url(base_url),
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json=deepcopy(dict(request_body)),
        )
    finally:
        if owns_client:
            await active_client.aclose()
