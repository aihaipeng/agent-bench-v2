import asyncio
import json

import httpx

from execution import (
    build_chat_completion_request,
    chat_completions_url,
    deep_merge_model_request,
    invoke_openai_compatible,
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
