from pathlib import Path

import pytest
from openpyxl import Workbook

from storage.excel import ExcelCaseRepository


def _save_workbook(path: Path) -> None:
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Cases"
    sheet.append(["case_id", "question", "old_result"])
    sheet.append(["case_001", "第一个问题", "PASS"])
    sheet.append(["case_002", "第二个问题", "FAILED"])
    sheet.append(["case_002", "重复 ID 应被忽略", "PASS"])
    sheet.append(["", "没有 ID 应被忽略", "PASS"])
    sheet.append(["case_003", "", "PASS"])
    wb.create_sheet("Other")
    wb.save(path)


def test_read_cases_uses_only_case_id_and_question_columns(tmp_path):
    workbook_path = tmp_path / "cases.xlsx"
    _save_workbook(workbook_path)

    cases = ExcelCaseRepository(workbook_path, "Cases").read_cases()

    assert [(case.case_id, case.question) for case in cases] == [
        ("case_001", "第一个问题"),
        ("case_002", "第二个问题"),
    ]


def test_missing_sheet_raises_clear_error(tmp_path):
    workbook_path = tmp_path / "cases.xlsx"
    _save_workbook(workbook_path)

    with pytest.raises(ValueError, match="Sheet 不存在"):
        ExcelCaseRepository(workbook_path, "Missing").read_cases()
