"""本机文件操作相关的 API 路由。"""

import subprocess

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from web.files import get_existing_input_path

router = APIRouter(prefix="/api", tags=["files"])


@router.post("/excel/sets/{filename}/open-dir")
def open_dir(filename: str) -> JSONResponse:
    """在 Windows 资源管理器中打开测试集所在目录并选中文件。"""
    input_path = get_existing_input_path(filename)
    abs_path = str(input_path.resolve())
    try:
        subprocess.Popen(["explorer", "/select,", abs_path])
    except Exception as exc:
        raise HTTPException(500, "无法打开资源管理器") from exc

    return JSONResponse({"ok": True, "path": abs_path})
