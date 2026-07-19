import sqlite3

import pytest
from fastapi.testclient import TestClient

from execution import (
    RunRepository,
    RunRepositoryError,
    TargetHttpMethod,
    TargetRecord,
)
from execution.repository import SCHEMA_VERSION
from web import routes_targets
from web.app import app


def _body(**overrides) -> dict:
    body = {
        "name": "企业 Agent 测试环境",
        "base_url": "http://127.0.0.1:9000",
        "path": "/api/agent/invoke",
        "method": "POST",
        "headers": {"X-Environment": "internal"},
        "target_total_concurrency": 4,
    }
    body.update(overrides)
    return body


def _patch_database(tmp_path, monkeypatch):
    database_path = tmp_path / "run_storage" / "agent_bench.sqlite3"
    monkeypatch.setattr(routes_targets, "DATABASE_PATH", database_path)
    monkeypatch.setattr(routes_targets, "_repository_instance", None)
    monkeypatch.setattr(routes_targets, "_repository_path", None)
    return database_path


def test_v1_database_is_migrated_to_targets_without_losing_runs(tmp_path):
    database_path = tmp_path / "agent_bench.sqlite3"
    with sqlite3.connect(database_path, isolation_level=None) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.execute("BEGIN IMMEDIATE")
        RunRepository._apply_v1(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (1, 'v1')"
        )
        connection.execute(
            """
            INSERT INTO runs(
                id, testset_filename, sheet_name, status, parameters_json,
                snapshot_json, cancel_requested, created_at, updated_at
            ) VALUES ('old-run', 'cases.xlsx', 'Sheet1', 'QUEUED', '{}', '{}', 0,
                      '2026-07-19T00:00:00Z', '2026-07-19T00:00:00Z')
            """
        )
        connection.commit()

    repository = RunRepository(database_path)
    repository.initialize()
    repository.create_target(TargetRecord(**_body(), id="target-after-upgrade"))

    assert repository.schema_version() == SCHEMA_VERSION == 5
    assert repository.get_run("old-run") is not None
    assert repository.get_target("target-after-upgrade") is not None
    with sqlite3.connect(database_path) as connection:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
    assert versions == [1, 2, 3, 4, 5]


def test_target_repository_crud_duplicate_names_and_restart_round_trip(tmp_path):
    database_path = tmp_path / "agent_bench.sqlite3"
    repository = RunRepository(database_path)
    first = repository.create_target(TargetRecord(id="target-1", **_body()))
    second = repository.create_target(
        TargetRecord(id="target-2", **_body(headers={"Authorization": "plain-secret"}))
    )

    restarted = RunRepository(database_path)
    restored = restarted.get_target(first.id)
    assert restored is not None
    assert restored.name == "企业 Agent 测试环境"
    assert restored.headers == {"X-Environment": "internal"}
    assert {target.id for target in restarted.list_targets()} == {
        first.id,
        second.id,
    }

    updated = restarted.update_target(
        TargetRecord(
            id=first.id,
            created_at=first.created_at,
            name="更新后的 Target",
            base_url="https://agent.example.test/internal",
            path="/v2/invoke",
            headers={},
            target_total_concurrency=9,
        )
    )
    assert updated.id == first.id
    assert updated.created_at == first.created_at
    assert updated.method == TargetHttpMethod.POST
    assert updated.target_total_concurrency == 9

    with pytest.raises(RunRepositoryError, match="UNIQUE"):
        restarted.create_target(TargetRecord(id=first.id, **_body()))
    assert restarted.delete_target(first.id) is True
    assert restarted.delete_target(first.id) is False
    assert restarted.get_target(first.id) is None


def test_target_api_complete_crud_and_duplicate_names(tmp_path, monkeypatch):
    database_path = _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    created_response = client.post("/api/targets", json=_body())
    duplicate_name_response = client.post("/api/targets", json=_body())
    assert created_response.status_code == 200
    assert duplicate_name_response.status_code == 200
    created = created_response.json()["target"]
    duplicate = duplicate_name_response.json()["target"]
    assert created["id"] != duplicate["id"]
    assert created["name"] == duplicate["name"]
    assert created["method"] == "POST"

    listed = client.get("/api/targets")
    fetched = client.get(f"/api/targets/{created['id']}")
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()["targets"]} == {
        created["id"],
        duplicate["id"],
    }
    assert fetched.json()["target"] == created

    update_body = _body(
        name="  预发布环境  ",
        base_url="  https://agent.example.test:9443/internal  ",
        path="  /api/v2/invoke  ",
        headers={"Authorization": "Bearer secret"},
        target_total_concurrency=12,
    )
    updated_response = client.put(
        f"/api/targets/{created['id']}",
        json=update_body,
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()["target"]
    assert updated["name"] == "预发布环境"
    assert updated["base_url"] == "https://agent.example.test:9443/internal"
    assert updated["path"] == "/api/v2/invoke"
    assert updated["headers"] == {"Authorization": "Bearer secret"}
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] >= created["updated_at"]

    routes_targets._repository_instance = None
    routes_targets._repository_path = None
    assert RunRepository(database_path).get_target(created["id"]).headers == {
        "Authorization": "Bearer secret"
    }
    assert client.get(f"/api/targets/{created['id']}").json()["target"] == updated

    deleted = client.delete(f"/api/targets/{created['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["target"] == updated
    assert client.get(f"/api/targets/{created['id']}").status_code == 404
    assert client.put(f"/api/targets/{created['id']}", json=_body()).status_code == 404
    assert client.delete(f"/api/targets/{created['id']}").status_code == 404


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "agent.example.test",
        "ftp://agent.example.test",
        "http://",
        "https://agent.example.test/query?x=1",
        "https://agent.example.test/path#fragment",
        "https://agent example.test",
        "https://agent.example.test:99999",
    ],
)
def test_target_api_rejects_invalid_base_url(
    tmp_path, monkeypatch, base_url
):
    _patch_database(tmp_path, monkeypatch)

    response = TestClient(app).post(
        "/api/targets",
        json=_body(base_url=base_url),
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    ["", "api/invoke", "//other-host/invoke", "/api?debug=1", "/api#part", "/api\nbad"],
)
def test_target_api_rejects_invalid_path(tmp_path, monkeypatch, path):
    _patch_database(tmp_path, monkeypatch)

    response = TestClient(app).post("/api/targets", json=_body(path=path))

    assert response.status_code == 422


@pytest.mark.parametrize("concurrency", [0, -1, True, 1.5, "2"])
def test_target_api_requires_positive_strict_integer_concurrency(
    tmp_path, monkeypatch, concurrency
):
    _patch_database(tmp_path, monkeypatch)

    response = TestClient(app).post(
        "/api/targets",
        json=_body(target_total_concurrency=concurrency),
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "headers",
    [
        [],
        {"Bad Header": "value"},
        {"X-Count": 2},
        {"X-Test": "valid\r\nInjected: yes"},
        {"X-Test": "null\x00value"},
        {"X-Test": "中文"},
    ],
)
def test_target_api_rejects_invalid_headers(tmp_path, monkeypatch, headers):
    _patch_database(tmp_path, monkeypatch)

    response = TestClient(app).post(
        "/api/targets",
        json=_body(headers=headers),
    )

    assert response.status_code == 422


def test_target_api_only_accepts_post_and_requires_all_core_fields(
    tmp_path, monkeypatch
):
    _patch_database(tmp_path, monkeypatch)
    client = TestClient(app)

    assert client.post("/api/targets", json=_body(method="GET")).status_code == 422
    for required_field in (
        "name",
        "base_url",
        "path",
        "target_total_concurrency",
    ):
        body = _body()
        body.pop(required_field)
        assert client.post("/api/targets", json=body).status_code == 422
