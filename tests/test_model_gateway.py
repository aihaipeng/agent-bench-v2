import asyncio
import json

import httpx

from execution import (
    DEFAULT_ANTHROPIC_MAX_TOKENS,
    anthropic_messages_url,
    build_anthropic_request,
    build_chat_completion_request,
    chat_completions_url,
    deep_merge_model_request,
    invoke_anthropic,
    invoke_openai_compatible,
    is_internal_ip_url,
    model_http_client_options,
    parse_anthropic_response,
    parse_openai_compatible_response,
)


def test_deep_merge_lets_user_parameters_override_every_request_field():
    base = {
        "model": "model-from-selector",
        "messages": [{"role": "user", "content": "base"}],
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"strict": False, "name": "base"},
        },
        "stop": ["base"],
    }
    defaults = {
        "temperature": 0.7,
        "response_format": {"json_schema": {"strict": True}},
    }
    user = {
        "model": "model-from-user",
        "messages": [{"role": "user", "content": "override"}],
        "stream": True,
        "response_format": {"json_schema": {"name": "user"}},
        "stop": ["user"],
    }

    merged = deep_merge_model_request(base, defaults, user)

    assert merged == {
        "model": "model-from-user",
        "messages": [{"role": "user", "content": "override"}],
        "stream": True,
        "temperature": 0.7,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"strict": True, "name": "user"},
        },
        "stop": ["user"],
    }
    assert base["response_format"]["json_schema"]["name"] == "base"


def test_build_chat_request_keeps_provider_defaults_when_user_does_not_override():
    request = build_chat_completion_request(
        model_name="qwen-plus",
        messages=[{"role": "user", "content": "hello"}],
        model_defaults={
            "temperature": 0.5,
            "thinking": {"enabled": False, "budget": 1024},
        },
        model_parameters={
            "thinking": {"enabled": True},
            "enable_thinking": True,
        },
    )

    assert request == {
        "model": "qwen-plus",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
        "temperature": 0.5,
        "thinking": {"enabled": True, "budget": 1024},
        "enable_thinking": True,
    }
    assert "max_tokens" not in request
    assert "max_completion_tokens" not in request


def test_chat_completions_url_preserves_gateway_base_path():
    assert chat_completions_url("https://api.deepseek.com") == (
        "https://api.deepseek.com/chat/completions"
    )
    assert chat_completions_url(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/"
    ) == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    )
    assert chat_completions_url(
        "https://gateway.example/v1/chat/completions"
    ) == "https://gateway.example/v1/chat/completions"


def test_anthropic_request_uses_required_default_and_user_overrides():
    request = build_anthropic_request(
        model_name="claude-sonnet",
        system_prompt="Follow policy",
        messages=[{"role": "user", "content": "Review this"}],
        model_defaults={"temperature": 0.2, "metadata": {"source": "default"}},
        model_parameters={
            "max_tokens": 16384,
            "thinking": {"type": "enabled", "budget_tokens": 2048},
            "metadata": {"case": "42"},
        },
    )

    assert request == {
        "model": "claude-sonnet",
        "system": "Follow policy",
        "messages": [{"role": "user", "content": "Review this"}],
        "max_tokens": 16384,
        "stream": False,
        "temperature": 0.2,
        "thinking": {"type": "enabled", "budget_tokens": 2048},
        "metadata": {"source": "default", "case": "42"},
    }
    assert DEFAULT_ANTHROPIC_MAX_TOKENS >= 8192
    assert build_anthropic_request(
        model_name="claude-sonnet",
        messages=[{"role": "user", "content": "hello"}],
    )["max_tokens"] == DEFAULT_ANTHROPIC_MAX_TOKENS


def test_anthropic_url_and_internal_network_client_policy():
    assert anthropic_messages_url("https://api.anthropic.com") == (
        "https://api.anthropic.com/v1/messages"
    )
    assert anthropic_messages_url("https://gateway.example/anthropic/v1") == (
        "https://gateway.example/anthropic/v1/messages"
    )
    assert anthropic_messages_url("https://gateway.example/v1/messages") == (
        "https://gateway.example/v1/messages"
    )
    assert is_internal_ip_url("https://10.20.30.40:8443/v1") is True
    assert is_internal_ip_url("http://127.0.0.1:8000") is True
    assert is_internal_ip_url("https://[fd00::1]/v1") is True
    assert is_internal_ip_url("https://api.anthropic.com") is False

    internal = model_http_client_options(
        "https://10.20.30.40:8443/v1", timeout_seconds=120
    )
    public = model_http_client_options(
        "https://api.anthropic.com", timeout_seconds=120
    )
    assert internal == {
        "follow_redirects": True,
        "timeout": 120,
        "trust_env": False,
    }
    assert public == {"follow_redirects": True, "timeout": 120}
    assert model_http_client_options(
        "https://api.anthropic.com",
        timeout_seconds=120,
        proxy_mode="DIRECT",
    ) == {
        "follow_redirects": True,
        "timeout": 120,
        "trust_env": False,
    }
    assert model_http_client_options(
        "https://api.anthropic.com",
        timeout_seconds=120,
        proxy_mode="SYSTEM",
        skip_ssl_verify=True,
    ) == {
        "follow_redirects": True,
        "timeout": 120,
        "verify": False,
    }
    assert model_http_client_options(
        "https://10.20.30.40:8443/v1",
        timeout_seconds=120,
        skip_ssl_verify=True,
    ) == {
        "follow_redirects": True,
        "timeout": 120,
        "trust_env": False,
        "verify": False,
    }
    assert model_http_client_options(
        "https://api.anthropic.com",
        timeout_seconds=120,
        proxy_mode="CUSTOM",
        proxy_url="http://proxy.internal:8080",
        proxy_username="domain user",
        proxy_password="p@ss:word",
        skip_ssl_verify=True,
    ) == {
        "follow_redirects": True,
        "timeout": 120,
        "trust_env": False,
        "proxy": "http://domain%20user:p%40ss%3Aword@proxy.internal:8080",
        "verify": False,
    }
    assert model_http_client_options(
        "https://10.20.30.40:8443/v1",
        timeout_seconds=120,
        proxy_mode="CUSTOM",
        proxy_url="http://proxy.internal:8080",
    ) == internal


def test_openai_compatible_transport_forwards_body_without_parameter_translation():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    async def invoke():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await invoke_openai_compatible(
                base_url="https://gateway.example/v1",
                api_key="test-secret",
                request_body={
                    "model": "custom-model",
                    "messages": [],
                    "enable_thinking": True,
                    "vendor_extension": {"level": "high"},
                },
                client=client,
            )

    response = asyncio.run(invoke())

    assert response.status_code == 200
    assert captured == {
        "url": "https://gateway.example/v1/chat/completions",
        "authorization": "Bearer test-secret",
        "body": {
            "model": "custom-model",
            "messages": [],
            "enable_thinking": True,
            "vendor_extension": {"level": "high"},
        },
    }


def test_anthropic_transport_and_response_parser_keep_native_contract():
    captured = {}
    native_response = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "internal"},
            {"type": "text", "text": "policy "},
            {"type": "text", "text": "failed"},
        ],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers["x-api-key"]
        captured["version"] = request.headers["anthropic-version"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=native_response)

    async def invoke():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await invoke_anthropic(
                base_url="https://gateway.example/anthropic/v1",
                api_key="anthropic-secret",
                request_body={
                    "model": "claude-sonnet",
                    "messages": [{"role": "user", "content": "review"}],
                    "max_tokens": 8192,
                },
                client=client,
            )

    response = asyncio.run(invoke())

    assert captured == {
        "url": "https://gateway.example/anthropic/v1/messages",
        "api_key": "anthropic-secret",
        "version": "2023-06-01",
        "body": {
            "model": "claude-sonnet",
            "messages": [{"role": "user", "content": "review"}],
            "max_tokens": 8192,
        },
    }
    assert parse_anthropic_response(response) == {
        "output": "policy failed",
        "usage": {"input_tokens": 12, "output_tokens": 8},
        "finish_reason": "end_turn",
    }


def test_parse_streaming_response_combines_output_and_usage():
    response = httpx.Response(
        200,
        text=(
            'data: {"choices":[{"delta":{"reasoning_content":"think"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"hello "}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"world"},"finish_reason":"stop"}],'
            '"usage":{"total_tokens":12}}\n\n'
            "data: [DONE]\n\n"
        ),
    )

    assert parse_openai_compatible_response(response, stream=True) == {
        "output": "hello world",
        "usage": {"total_tokens": 12},
        "finish_reason": "stop",
    }
