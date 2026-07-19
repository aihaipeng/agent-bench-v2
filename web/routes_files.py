"""本机文件操作相关的 API 路由。"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from web.files import get_existing_input_path, open_file_in_explorer

router = APIRouter(prefix="/api", tags=["files"])


@router.post("/excel/sets/{filename}/open-dir")
def open_dir(filename: str) -> JSONResponse:
    """在 Windows 资源管理器中打开测试集所在目录并选中文件。"""
    input_path = get_existing_input_path(filename)
    abs_path = open_file_in_explorer(input_path)
    return JSONResponse({"ok": True, "path": abs_path})
