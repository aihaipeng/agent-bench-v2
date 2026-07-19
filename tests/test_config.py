from io import BytesIO

import yaml
from fastapi.testclient import TestClient
from openpyxl import Workbook

from web import files, routes_config, routes_excel
from web.app import app


def _workbook_bytes() -> bytes:
    output = BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Cases"
    sheet.append(["case_id", "question"])
    sheet.append(["case_001", "示例问题"])
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _patch_local_state(tmp_path, monkeypatch):
    inputs_dir = tmp_path / "inputs"
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(files, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(files, "INPUTS_DIR", inputs_dir)
    monkeypatch.setattr(routes_excel, "INPUTS_DIR", inputs_dir)
    monkeypatch.setattr(routes_excel, "SETS_META_FILE", inputs_dir / ".sets_meta.json")
    monkeypatch.setattr(routes_config, "CONFIG_PATH", config_path)
    return inputs_dir, config_path


def test_missing_local_config_uses_safe_defaults(tmp_path, monkeypatch):
    _, config_path = _patch_local_state(tmp_path, monkeypatch)

    response = TestClient(app).get("/api/config/current")

    assert response.status_code == 200
    assert response.json() == {"filename": "testcases.xlsx", "sheet_name": "Sheet1"}
    assert not config_path.exists()


def test_first_upload_creates_local_config(tmp_path, monkeypatch):
    inputs_dir, config_path = _patch_local_state(tmp_path, monkeypatch)

    response = TestClient(app).post(
        "/api/excel/upload",
        files={
            "file": (
                "public-sample.xlsx",
                _workbook_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    assert (inputs_dir / "public-sample.xlsx").is_file()
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == {
        "excel": {
            "input_path": "inputs\\public-sample.xlsx",
            "sheet_name": "Cases",
        }
    }
