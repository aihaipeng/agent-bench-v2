import pytest
from fastapi import HTTPException

from web.files import get_input_path, normalize_excel_filename


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
