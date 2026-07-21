from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from execution import ModelProviderRecord, ModelProviderRepository
from web import routes_model_providers
from web.app import app


def _body(**overrides) -> dict:
    body = {
        "name": "DeepSeek",
        "website_url": "https://www.deepseek.com",
        "api_key": "local-secret",
        "base_url": "https://api.deepseek.com",
        "protocol": "OPENAI_COMPATIBLE",
        "model_endpoint": "https://api.deepseek.com/v1/models",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    }
    body.update(overrides)
    return body


def _patch_database(tmp_path, monkeypatch):
    database_path = tmp_path / "run_storage" / "agent_bench.sqlite3"
    monkeypatch.setattr(routes_model_providers, "DATABASE_PATH", database_path)
    monkeypatch.setattr(routes_model_providers, "_repository_instance", None)
    monkeypatch.setattr(routes_model_providers, "_repository_path", None)
    return database_path


def test_model_provider_repository_restart_round_trip(tmp_path):
    database_path = tmp_path / "agent_bench.sqlite3"
    repository = ModelProviderRepository(database_path)
    created = repository.create(ModelProviderRecord(id="provider-1", **_body()))

    restored = ModelProviderRepository(database_path).get(created.id)
    assert restored is not None
    assert restored.api_key == "local-secret"
    assert restored.models == ["deepseek-chat", "deepseek-reasoner"]

    updated = ModelProviderRecord(
        id=created.id,
        created_at=created.created_at,
        **_body(name="更新供应商", models=["deepseek-chat"]),
    )
    assert repository.update(updated).name == "更新供应商"
    assert repository.delete(created.id) is True
    assert repository.delete(created.id) is False


def test_model_provider_api_crud_and_list_hides_api_key(tmp_path, monkeypatch):
    database_path = _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    created_response = client.post("/api/model-providers", json=_body())
    assert created_response.status_code == 200
    created = created_response.json()["provider"]
    assert created["api_key"] == "local-secret"

    listed = client.get("/api/model-providers").json()["providers"]
    assert len(listed) == 1
    assert "api_key" not in listed[0]
    assert client.get(f"/api/model-providers/{created['id']}").json()["provider"] == created

    updated_response = client.put(
        f"/api/model-providers/{created['id']}",
        json=_body(name="  企业模型网关  ", api_key="changed-secret", models=["m-1"]),
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()["provider"]
    assert updated["name"] == "企业模型网关"
    assert updated["api_key"] == "changed-secret"
    assert ModelProviderRepository(database_path).get(created["id"]).api_key == "changed-secret"

    deleted = client.delete(f"/api/model-providers/{created['id']}")
    assert deleted.status_code == 200
    assert "api_key" not in deleted.json()["provider"]
    assert client.get(f"/api/model-providers/{created['id']}").status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"api_key": "   "},
        {"base_url": "not-a-url"},
        {"base_url": "https://user:password@example.com"},
        {"website_url": "ftp://example.com"},
        {"models": []},
        {"models": ["ok", "  "]},
        {"models": [123]},
        {"protocol": "UNKNOWN"},
    ],
)
def test_model_provider_api_rejects_invalid_records(tmp_path, monkeypatch, overrides):
    _patch_database(tmp_path, monkeypatch)
    assert TestClient(app).post(
        "/api/model-providers", json=_body(**overrides)
    ).status_code == 422


def test_model_endpoint_candidates_and_payload_shapes():
    assert routes_model_providers.build_model_candidates("https://api.example.com") == [
        "https://api.example.com/v1/models",
        "https://api.example.com/models",
    ]
    assert routes_model_providers.build_model_candidates(
        "https://api.example.com/compatible-mode/v1"
    ) == ["https://api.example.com/compatible-mode/v1/models"]
    assert routes_model_providers.build_model_candidates(
        "https://api.example.com/v1/chat/completions"
    ) == ["https://api.example.com/v1/models"]
    assert routes_model_providers.extract_models(
        {"data": [{"id": "z"}, {"name": "a", "ownedBy": "vendor"}, "m"]}
    ) == [
        {"id": "a", "owned_by": "vendor"},
        {"id": "m", "owned_by": None},
        {"id": "z", "owned_by": None},
    ]


def test_latency_and_openai_compatible_model_discovery(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    seen_authorization = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/v1/models":
                seen_authorization.append(self.headers.get("Authorization"))
                payload = json.dumps({"data": [{"id": "model-b"}, {"id": "model-a"}]})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload.encode())))
                self.end_headers()
                self.wfile.write(payload.encode())
                return
            self.send_response(401)
            self.end_headers()

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    client = TestClient(app)
    try:
        latency = client.post(
            "/api/model-providers/latency",
            json={"base_url": base_url, "api_key": "secret-never-echo"},
        )
        models = client.post(
            "/api/model-providers/models",
            json={"base_url": base_url, "api_key": "secret-never-echo"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert latency.status_code == 200
    assert latency.json()["status_code"] == 401
    assert models.status_code == 200
    assert models.json()["protocol"] == "OPENAI_COMPATIBLE"
    assert [item["id"] for item in models.json()["models"]] == ["model-a", "model-b"]
    assert seen_authorization == ["Bearer secret-never-echo"]
    assert "secret-never-echo" not in models.text


def test_model_discovery_error_never_echoes_api_key(tmp_path, monkeypatch):
    _patch_database(tmp_path, monkeypatch)
    response = TestClient(app).post(
        "/api/model-providers/models",
        json={"base_url": "http://127.0.0.1:1", "api_key": "secret-never-echo"},
    )
    assert response.status_code == 502
    assert "secret-never-echo" not in response.text
