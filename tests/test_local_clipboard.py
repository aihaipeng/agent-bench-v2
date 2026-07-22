from fastapi.testclient import TestClient

from web.app import app


def test_local_clipboard_endpoint_copies_plain_text(monkeypatch) -> None:
    copied: list[str] = []
    monkeypatch.setattr(
        "web.routes_local_clipboard.copy_text_to_system_clipboard",
        copied.append,
    )

    response = TestClient(app).post(
        "/api/local/clipboard",
        json={"text": "stdout\nstderr\n"},
    )

    assert response.status_code == 200
    assert response.json() == {"copied": True}
    assert copied == ["stdout\nstderr\n"]


def test_local_clipboard_endpoint_rejects_unknown_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        "web.routes_local_clipboard.copy_text_to_system_clipboard",
        lambda _text: None,
    )

    response = TestClient(app).post(
        "/api/local/clipboard",
        json={"text": "log", "format": "html"},
    )

    assert response.status_code == 422
