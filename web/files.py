import subprocess
from pathlib import Path, PureWindowsPath

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUTS_DIR = PROJECT_ROOT / "inputs"
EXCEL_SUFFIXES = (".xlsx", ".xlsm")


def normalize_excel_filename(filename: str) -> str:
    """校验并规范化 Excel 文件名。

    只允许 `inputs/` 目录下的单个文件名，不允许路径片段。
    """
    raw = (filename or "").strip()
    if not raw:
        raise HTTPException(400, "文件名不能为空")
    if raw != Path(raw).name or raw != PureWindowsPath(raw).name:
        raise HTTPException(400, "文件名不能包含路径")

    suffix = Path(raw).suffix
    if suffix:
        if suffix.lower() not in EXCEL_SUFFIXES:
            raise HTTPException(400, "仅支持 .xlsx 和 .xlsm 文件")
        return raw
    return f"{raw}.xlsx"


def get_input_path(filename: str) -> Path:
    """返回位于 `inputs/` 下的安全 Excel 路径。"""
    normalized = normalize_excel_filename(filename)
    path = (INPUTS_DIR / normalized).resolve()
    base = INPUTS_DIR.resolve()
    if path.parent != base:
        raise HTTPException(400, "文件必须位于 inputs 目录")
    return path


def get_existing_input_path(filename: str) -> Path:
    """返回已存在的安全 Excel 路径。"""
    path = get_input_path(filename)
    if not path.is_file():
        raise HTTPException(404, f"文件不存在: {path.name}")
    return path


def resolve_config_input_path(input_path: str | Path) -> Path:
    """把配置中的 Excel 路径解析为受限于 `inputs/` 的绝对路径。"""
    path = Path(input_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    base = INPUTS_DIR.resolve()
    if resolved.parent != base or resolved.suffix.lower() not in EXCEL_SUFFIXES:
        raise HTTPException(400, "当前配置的 Excel 文件必须位于 inputs 目录")
    return resolved


def project_relative(path: Path) -> str:
    """返回适合写入配置文件的项目相对路径。"""
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def open_file_in_explorer(path: Path) -> str:
    """在 Windows 资源管理器中打开文件所在目录并选中文件。"""
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise HTTPException(404, f"文件不存在: {resolved.name}")
    try:
        subprocess.Popen(["explorer", "/select,", str(resolved)])
    except Exception as exc:
        raise HTTPException(500, "无法打开资源管理器") from exc
    return str(resolved)


def open_directory_in_explorer(path: Path) -> str:
    """在 Windows 资源管理器中直接打开指定目录。"""
    resolved = Path(path).resolve()
    if not resolved.is_dir():
        raise HTTPException(404, f"目录不存在: {resolved.name}")
    try:
        subprocess.Popen(["explorer", str(resolved)])
    except Exception as exc:
        raise HTTPException(500, "无法打开资源管理器") from exc
    return str(resolved)
