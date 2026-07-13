import json
import re
from enum import StrEnum
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

from core.models import ExcelRowResult, TestCase, VerifiedData


HEADER_NAMES = {
    "case_id",
    "case id",
    "用例id",
    "用例编号",
    "question",
    "问题",
}
RESULT_VALUES = {"PASS", "FAILED", "ERROR"}
RESULT_PREFIXES = ("PASS:", "FAILED:", "ERROR:")


class ExcelLayout(StrEnum):
    TWO_COLUMN = "two_column"
    THREE_COLUMN = "three_column"


def _as_text(value) -> str:
    """把 Excel 单元格值转换为去除首尾空白的文本。

    Args:
        value: 原始单元格值。

    Returns:
        规范化文本；空单元格返回空字符串。
    """
    return "" if value is None else str(value).strip()


def _split_tools(value) -> list[str]:
    """按常见中英文分隔符拆分工具名称列表。

    Args:
        value: 工具列表单元格值。

    Returns:
        去除空白和空项后的工具名称列表。
    """
    text = _as_text(value)
    return [part.strip() for part in re.split(r"[,，;；\n]", text) if part.strip()]


class ExcelCaseRepository:
    """统一管理测试用例 Excel 的布局识别、读取和结果写回。"""

    def __init__(self, file_path: str | Path, sheet_name: str = "Sheet1"):
        """绑定一个测试用例工作簿及目标工作表。

        Args:
            file_path: Excel 文件路径。
            sheet_name: 首选工作表名称。
        """
        self.path = Path(file_path)
        self.sheet_name = sheet_name
        self.layout: ExcelLayout | None = None

    def _select_sheet(self, workbook):
        """选择指定工作表，缺失时回退到首个非保留工作表。

        Args:
            workbook: 已打开的 openpyxl 工作簿。

        Returns:
            选中的工作表对象。

        Raises:
            ValueError: 工作簿中没有可用工作表。
        """
        if self.sheet_name in workbook.sheetnames:
            return workbook[self.sheet_name]
        usable = [
            name for name in workbook.sheetnames if not name.startswith("WpsReserved")
        ]
        if not usable:
            raise ValueError("Excel 文件中没有可用的工作表")
        return workbook[usable[0]]

    @staticmethod
    def _detect_layout(sheet) -> ExcelLayout:
        """根据列宽和结果列内容识别两列或三列输入布局。

        Args:
            sheet: 待读取的工作表。

        Returns:
            识别出的 Excel 输入布局。
        """
        width = sheet.max_column
        rows = list(
            sheet.iter_rows(min_col=1, max_col=min(3, width), values_only=True)
        )
        third_column_is_result = any(
            len(row) >= 3
            and (
                _as_text(row[2]).upper() in RESULT_VALUES
                or _as_text(row[2]).upper().startswith(RESULT_PREFIXES)
            )
            for row in rows
        )
        if width >= 3 and not third_column_is_result:
            return ExcelLayout.THREE_COLUMN
        return ExcelLayout.TWO_COLUMN

    def read_cases(self) -> list[TestCase]:
        """读取工作簿中的有效测试用例并记录已识别布局。

        Returns:
            去除空行、表头和重复 ID 后的测试用例列表。

        Raises:
            FileNotFoundError: Excel 文件不存在。
            ValueError: 工作簿中没有可用工作表。
        """
        if not self.path.is_file():
            raise FileNotFoundError(f"Excel 文件不存在: {self.path}")

        workbook = load_workbook(self.path, read_only=True, data_only=True)
        sheet = self._select_sheet(workbook)
        self.layout = self._detect_layout(sheet)
        rows = list(
            sheet.iter_rows(
                min_col=1,
                max_col=3 if self.layout is ExcelLayout.THREE_COLUMN else 2,
                values_only=True,
            )
        )
        workbook.close()

        testcases: list[TestCase] = []
        seen_ids: set[str] = set()
        for row_number, row in enumerate(rows, start=1):
            values = list(row) + [None] * (3 - len(row))
            if self.layout is ExcelLayout.THREE_COLUMN:
                case_id = _as_text(values[0])
                question = _as_text(values[1])
                tool_value = values[2]
            else:
                case_id = f"case_{row_number}"
                question = _as_text(values[0])
                tool_value = values[1]

            if row_number == 1 and (
                case_id.casefold() in HEADER_NAMES
                or question.casefold() in HEADER_NAMES
            ):
                continue
            if not question:
                continue
            if not case_id:
                case_id = f"case_{row_number}"
            if case_id in seen_ids:
                continue
            seen_ids.add(case_id)
            testcases.append(
                TestCase(
                    case_id=case_id,
                    question=question,
                    tools=_split_tools(tool_value),
                )
            )
        return testcases

    @staticmethod
    def _find_row(sheet, case_id: str, layout: ExcelLayout) -> int | None:
        """根据显式 ID 或两列布局生成的 case_N 定位原始行。

        Args:
            sheet: 待查找的工作表。
            case_id: 需要定位的用例 ID。
            layout: 当前 Excel 输入布局。

        Returns:
            从一开始的 Excel 行号；未找到时返回 ``None``。
        """
        if layout is ExcelLayout.THREE_COLUMN:
            for row in range(1, sheet.max_row + 1):
                value = sheet.cell(row=row, column=1).value
                if value is not None and str(value).strip() == case_id:
                    return row
            return None
        generated_id = re.fullmatch(r"case_(\d+)", case_id)
        if generated_id:
            row = int(generated_id.group(1))
            if 1 <= row <= sheet.max_row:
                return row
        return None

    def write_results(
        self,
        results: list[tuple[str, ExcelRowResult, VerifiedData | None]],
    ) -> None:
        """批量写入每条用例最后一次的状态及 VerifiedData JSON。

        Args:
            results: case_id、Excel 状态和可选校验结果组成的列表。

        Raises:
            FileNotFoundError: Excel 文件不存在。
            ValueError: 工作表不可用或无法定位某条用例。
        """
        if not results:
            return
        if not self.path.is_file():
            raise FileNotFoundError(f"Excel 文件不存在: {self.path}")

        workbook = load_workbook(self.path)
        sheet = self._select_sheet(workbook)
        layout = self.layout or self._detect_layout(sheet)
        first_result_column = 4 if layout is ExcelLayout.THREE_COLUMN else 3
        colors = {
            ExcelRowResult.PASS: ("006100", "C6EFCE"),
            ExcelRowResult.FAILED: ("9C0006", "FFC7CE"),
            ExcelRowResult.ERROR: ("404040", "D9E1F2"),
        }

        for case_id, result, verified in results:
            row = self._find_row(sheet, case_id, layout)
            if row is None:
                workbook.close()
                raise ValueError(f"Excel 中找不到用例行: {case_id}")

            result_cell = sheet.cell(row=row, column=first_result_column)
            result_cell.value = result.value
            font_color, fill_color = colors[result]
            result_cell.font = Font(bold=True, color=font_color)
            result_cell.fill = PatternFill("solid", fgColor=fill_color)

            verified_cell = sheet.cell(row=row, column=first_result_column + 1)
            verified_cell.value = (
                json.dumps(verified.model_dump(), ensure_ascii=False)
                if verified is not None
                else None
            )
            verified_cell.font = Font()
            verified_cell.fill = PatternFill()

            for column in range(first_result_column + 2, first_result_column + 4):
                detail_cell = sheet.cell(row=row, column=column)
                detail_cell.value = None
                detail_cell.font = Font()
                detail_cell.fill = PatternFill()

        workbook.save(self.path)
        workbook.close()
