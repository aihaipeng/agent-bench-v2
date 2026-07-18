from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from storage.excel import ExcelCaseRepository
from web.files import get_existing_input_path

router = APIRouter(prefix="/api/testcases", tags=["testcases"])

class TestCaseItem(BaseModel):
    """单条用例的 API 响应。"""

    case_id: str
    question: str


class TestCasesResponse(BaseModel):
    """用例列表的 API 响应。"""

    cases: list[TestCaseItem]
    count: int
    total: int
    page: int
    page_size: int
    filename: str
    sheet_name: str


@router.get("", response_model=TestCasesResponse)
def get_testcases(
    filename: str = Query(..., description="Excel 文件名"),
    sheet: str = Query("Sheet1", description="Sheet 名称"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=500, description="每页条数"),
) -> TestCasesResponse:
    """从指定的 Excel + sheet 读取用例（分页）。

    Args:
        filename: ``inputs/`` 下的 Excel 文件名。
        sheet: Sheet 名称。
        page: 页码，从 1 开始。
        page_size: 每页条数，默认 50，上限 500。

    Returns:
        当前页用例列表及分页元信息。

    Raises:
        HTTPException 400: 文件或 sheet 不存在。
    """
    input_path = get_existing_input_path(filename)

    try:
        repo = ExcelCaseRepository(input_path, sheet)
        all_cases = repo.read_cases()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    total = len(all_cases)

    start = (page - 1) * page_size
    end = start + page_size
    page_cases = all_cases[start:end]

    cases = [TestCaseItem(case_id=c.case_id, question=c.question) for c in page_cases]
    return TestCasesResponse(
        cases=cases,
        count=len(cases),
        total=total,
        page=page,
        page_size=page_size,
        filename=input_path.name,
        sheet_name=sheet,
    )
