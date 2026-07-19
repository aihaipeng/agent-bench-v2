import pytest
from fastapi import HTTPException

from web import files
from web.files import (
    get_input_path,
    normalize_excel_filename,
    open_directory_in_explorer,
    open_file_in_explorer,
)


def test_normalize_excel_filename_rejects_path_segments():
    with pytest.raises(HTTPException):
        normalize_excel_filename("../outside.xlsx")

    with pytest.raises(HTTPException):
        normalize_excel_filename("nested\\outside.xlsx")


def test_normalize_excel_filename_defaults_to_xlsx():
    assert normalize_excel_filename("cases") == "cases.xlsx"


def test_get_input_path_stays_inside_inputs():
    path = get_input_path("cases.xlsx")

    assert path.name == "cases.xlsx"
    assert path.parent.name == "inputs"


def test_open_file_in_explorer_selects_existing_file(tmp_path, monkeypatch):
    target = tmp_path / "example.tool.json"
    target.write_text("{}", encoding="utf-8")
    calls = []
    monkeypatch.setattr(files.subprocess, "Popen", lambda args: calls.append(args))

    resolved = open_file_in_explorer(target)

    assert resolved == str(target.resolve())
    assert calls == [["explorer", "/select,", str(target.resolve())]]


def test_open_file_in_explorer_rejects_missing_file(tmp_path):
    with pytest.raises(HTTPException, match="文件不存在") as exc_info:
        open_file_in_explorer(tmp_path / "missing.tool.json")

    assert exc_info.value.status_code == 404


def test_open_directory_in_explorer_opens_existing_directory(tmp_path, monkeypatch):
    target = tmp_path / "tool-id"
    target.mkdir()
    calls = []
    monkeypatch.setattr(files.subprocess, "Popen", lambda args: calls.append(args))

    resolved = open_directory_in_explorer(target)

    assert resolved == str(target.resolve())
    assert calls == [["explorer", str(target.resolve())]]


def test_open_directory_in_explorer_rejects_missing_directory(tmp_path):
    with pytest.raises(HTTPException, match="目录不存在") as exc_info:
        open_directory_in_explorer(tmp_path / "missing")

    assert exc_info.value.status_code == 404
