from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from web.files import PROJECT_ROOT, get_existing_input_path, get_input_path, project_relative, resolve_config_input_path

router = APIRouter(prefix="/api/config", tags=["config"])

CONFIG_PATH = PROJECT_ROOT / "config.yaml"


class CurrentConfigRequest(BaseModel):
    """设置当前测试集和 sheet 的请求体。"""

    filename: str
    sheet_name: str


class CurrentConfigResponse(BaseModel):
    """当前测试集和 sheet 配置。"""

    filename: str
    sheet_name: str


def _load_yaml() -> dict:
    """读取 config.yaml 原始内容。

    Returns:
        解析后的配置字典。

    Raises:
        HTTPException: 配置文件不可读或格式错误。
    """
    if not CONFIG_PATH.is_file():
        raise HTTPException(500, "config.yaml 不存在")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = f.read()
    config = yaml.safe_load(raw)
    if not isinstance(config, dict):
        raise HTTPException(500, "config.yaml 格式错误")
    return config


def _save_yaml(config: dict) -> None:
    """将配置字典写回 config.yaml。

    Args:
        config: 完整配置字典。
    """
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _get_input_path(filename: str) -> Path:
    """解析输入文件的绝对路径。

    Args:
        filename: Excel 文件名。

    Returns:
        指向 ``inputs/{filename}`` 的绝对路径。
    """
    return get_input_path(filename)


@router.get("/current", response_model=CurrentConfigResponse)
def get_current_config() -> CurrentConfigResponse:
    """获取当前使用的测试集文件和 sheet 名。"""
    config = _load_yaml()
    excel = config.get("excel", {})
    input_path = excel.get("input_path", "inputs/testcases.xlsx")
    try:
        filename = resolve_config_input_path(input_path).name
    except HTTPException:
        filename = Path(str(input_path)).name
    sheet_name = excel.get("sheet_name", "Sheet1")
    return CurrentConfigResponse(filename=filename, sheet_name=sheet_name)


@router.post("/current")
def set_current_config(body: CurrentConfigRequest) -> dict:
    """设置当前使用的测试集文件和 sheet 名。

    Args:
        body: 包含 ``filename`` 和 ``sheet_name`` 的请求体。

    Returns:
        确认信息。

    Raises:
        HTTPException 400: 文件或 sheet 不存在。
    """
    input_path = get_existing_input_path(body.filename)

    import openpyxl

    wb = openpyxl.load_workbook(input_path, read_only=True)
    sheet_names = wb.sheetnames
    wb.close()

    if body.sheet_name not in sheet_names:
        raise HTTPException(400, f"Sheet 不存在: {body.sheet_name}。可用: {', '.join(sheet_names)}")

    config = _load_yaml()
    config.setdefault("excel", {})["input_path"] = project_relative(input_path)
    config["excel"]["sheet_name"] = body.sheet_name
    _save_yaml(config)
    return {"ok": True}
