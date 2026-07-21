from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).with_name("server.py")
REAL_ASYNC_CLIENT = httpx.AsyncClient
SPEC = importlib.util.spec_from_file_location("model_provider_demo_server", MODULE_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class MockAsyncClient:
    def __init__(self, handler, *args, **kwargs):
        self._client = REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, exc_type, exc, traceback):
        await self._client.aclose()


def test_build_model_candidates_handles_root_version_and_full_endpoint():
    assert server.build_model_candidates("https://api.example.com") == [
        "https://api.example.com/v1/models",
        "https://api.example.com/models",
    ]
    assert server.build_model_candidates("https://api.example.com/v1") == [
        "https://api.example.com/v1/models"
    ]
    assert server.build_model_candidates(
        "https://api.example.com/v1/chat/completions"
    ) == ["https://api.example.com/v1/models"]


def test_models_uses_openai_bearer_and_sorts_results(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models" and request.headers.get("authorization") == "Bearer key":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "qwen-max", "owned_by": "dashscope"},
                        {"id": "deepseek-chat", "owned_by": "deepseek"},
                    ]
                },
            )
        return httpx.Response(401, json={"error": "unauthorized"})

    monkeypatch.setattr(
        server.httpx,
        "AsyncClient",
        lambda *args, **kwargs: MockAsyncClient(handler),
    )
    response = TestClient(server.app).post(
        "/api/models",
        json={"base_url": "https://api.example.com", "api_key": "key"},
    )
    assert response.status_code == 200
    assert response.json()["protocol"] == "OPENAI_COMPATIBLE"
    assert [model["id"] for model in response.json()["models"]] == [
        "deepseek-chat",
        "qwen-max",
    ]


def test_models_falls_back_to_anthropic_headers(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.url.path == "/v1/models"
            and request.headers.get("x-api-key") == "anthropic-key"
            and request.headers.get("anthropic-version") == server.ANTHROPIC_VERSION
        ):
            return httpx.Response(200, json={"data": [{"id": "claude-sonnet"}]})
        return httpx.Response(401, json={"error": "unauthorized"})

    monkeypatch.setattr(
        server.httpx,
        "AsyncClient",
        lambda *args, **kwargs: MockAsyncClient(handler),
    )
    response = TestClient(server.app).post(
        "/api/models",
        json={"base_url": "https://api.anthropic.test", "api_key": "anthropic-key"},
    )
    assert response.status_code == 200
    assert response.json()["protocol"] == "ANTHROPIC"
    assert response.json()["models"] == [{"id": "claude-sonnet", "owned_by": None}]


def test_models_failure_does_not_expose_key(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "secret-key-leaked"})

    monkeypatch.setattr(
        server.httpx,
        "AsyncClient",
        lambda *args, **kwargs: MockAsyncClient(handler),
    )
    response = TestClient(server.app).post(
        "/api/models",
        json={"base_url": "https://api.example.com", "api_key": "secret-key"},
    )
    assert response.status_code == 502
    assert "secret-key" not in response.text
