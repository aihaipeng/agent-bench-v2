import json
import os
from datetime import datetime

from fastapi.testclient import TestClient

from web import files, routes_excel
from web.app import app


def _patch_inputs(tmp_path, monkeypatch):
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    monkeypatch.setattr(files, "INPUTS_DIR", inputs_dir)
    monkeypatch.setattr(routes_excel, "INPUTS_DIR", inputs_dir)
    monkeypatch.setattr(routes_excel, "SETS_META_FILE", inputs_dir / ".sets_meta.json")
    return inputs_dir


def test_set_description_is_saved_and_returned_in_set_list(tmp_path, monkeypatch):
    inputs_dir = _patch_inputs(tmp_path, monkeypatch)
    (inputs_dir / "cases.xlsx").touch()

    client = TestClient(app)
    response = client.put(
        "/api/excel/sets/cases.xlsx/meta",
        json={"description": "  冒烟测试集  "},
    )

    assert response.status_code == 200
    assert response.json()["description"] == "冒烟测试集"

    list_response = client.get("/api/excel/sets")
    assert list_response.status_code == 200
    assert list_response.json()["files"][0]["description"] == "冒烟测试集"
    assert list_response.json()["files"][0]["name"] == "cases"


def test_set_display_name_is_saved_without_overwriting_description(tmp_path, monkeypatch):
    inputs_dir = _patch_inputs(tmp_path, monkeypatch)
    (inputs_dir / "cases.xlsx").touch()

    client = TestClient(app)
    desc_response = client.put(
        "/api/excel/sets/cases.xlsx/meta",
        json={"description": "说明"},
    )
    name_response = client.put(
        "/api/excel/sets/cases.xlsx/meta",
        json={"name": "自定义名称"},
    )

    assert desc_response.status_code == 200
    assert name_response.status_code == 200
    assert name_response.json()["name"] == "自定义名称"
    assert name_response.json()["description"] == "说明"

    file_data = client.get("/api/excel/sets").json()["files"][0]
    assert file_data["name"] == "自定义名称"
    assert file_data["description"] == "说明"


def test_set_display_name_must_be_unique(tmp_path, monkeypatch):
    inputs_dir = _patch_inputs(tmp_path, monkeypatch)
    (inputs_dir / "a.xlsx").touch()
    (inputs_dir / "b.xlsx").touch()

    client = TestClient(app)
    response = client.put("/api/excel/sets/b.xlsx/meta", json={"name": "a"})

    assert response.status_code == 400
    assert response.json()["detail"] == "名称已存在: a"


def test_delete_set_removes_description_metadata(tmp_path, monkeypatch):
    inputs_dir = _patch_inputs(tmp_path, monkeypatch)
    (inputs_dir / "cases.xlsx").touch()
    routes_excel.SETS_META_FILE.write_text(
        json.dumps({"cases.xlsx": {"description": "待清理"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    response = TestClient(app).delete("/api/excel/sets/cases.xlsx")

    assert response.status_code == 200
    assert json.loads(routes_excel.SETS_META_FILE.read_text(encoding="utf-8")) == {}


def test_list_sets_can_sort_by_updated_at(tmp_path, monkeypatch):
    inputs_dir = _patch_inputs(tmp_path, monkeypatch)
    old_file = inputs_dir / "old.xlsx"
    new_file = inputs_dir / "new.xlsx"
    old_file.touch()
    new_file.touch()
    old_ts = datetime(2026, 1, 1, 8, 0, 0).timestamp()
    new_ts = datetime(2026, 1, 2, 8, 0, 0).timestamp()
    os.utime(old_file, (old_ts, old_ts))
    os.utime(new_file, (new_ts, new_ts))

    client = TestClient(app)
    asc = client.get("/api/excel/sets", params={"sort_by": "updated_at", "sort_dir": "asc"})
    desc = client.get("/api/excel/sets", params={"sort_by": "updated_at", "sort_dir": "desc"})

    assert [item["filename"] for item in asc.json()["files"]] == ["old.xlsx", "new.xlsx"]
    assert [item["filename"] for item in desc.json()["files"]] == ["new.xlsx", "old.xlsx"]


def test_list_sets_filters_by_display_name(tmp_path, monkeypatch):
    inputs_dir = _patch_inputs(tmp_path, monkeypatch)
    (inputs_dir / "alpha.xlsx").touch()
    (inputs_dir / "beta.xlsx").touch()
    routes_excel.SETS_META_FILE.write_text(
        json.dumps({"beta.xlsx": {"name": "回归测试"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    client = TestClient(app)
    default_name = client.get("/api/excel/sets", params={"name_query": "alp"})
    custom_name = client.get("/api/excel/sets", params={"name_query": "回归"})

    assert [item["filename"] for item in default_name.json()["files"]] == ["alpha.xlsx"]
    assert [item["filename"] for item in custom_name.json()["files"]] == ["beta.xlsx"]
