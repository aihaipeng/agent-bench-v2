from fastapi.testclient import TestClient

from web.app import app


def test_index_serves_frontend():
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Agent Bench" in response.text


def test_testcases_rejects_path_traversal_filename():
    response = TestClient(app).get(
        "/api/testcases",
        params={"filename": "../config", "sheet": "Sheet1"},
    )

    assert response.status_code == 400
