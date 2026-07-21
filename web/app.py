from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.routes_config import router as config_router
from web.routes_excel import router as excel_router
from web.routes_files import router as files_router
from web.routes_testcases import router as testcases_router
from web.routes_targets import router as targets_router
from web.routes_tool_templates import router as tool_templates_router

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。

    Returns:
        已注册路由、中间件和静态文件的应用实例。
    """
    app = FastAPI(title="Agent Bench")

    app.include_router(excel_router)
    app.include_router(config_router)
    app.include_router(files_router)
    app.include_router(testcases_router)
    app.include_router(targets_router)
    app.include_router(tool_templates_router)
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    # 静态文件 — 显式路由，避免 StaticFiles mount 拦截 API 的 PUT/DELETE
    # 添加 Cache-Control 头，防止浏览器缓存旧版文件
    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    @app.get("/")
    async def index():
        """返回首页 HTML。"""
        return FileResponse(STATIC_DIR / "index.html", headers=_NO_CACHE)

    @app.get("/style.css")
    async def style_css():
        """返回样式表。"""
        return FileResponse(STATIC_DIR / "style.css", headers=_NO_CACHE)

    @app.get("/app.js")
    async def app_js():
        """返回前端 JS。"""
        return FileResponse(STATIC_DIR / "app.js", headers=_NO_CACHE)

    @app.get("/execution.css")
    async def execution_css():
        """返回运行编排样式表。"""
        return FileResponse(STATIC_DIR / "execution.css", headers=_NO_CACHE)

    @app.get("/execution.js")
    async def execution_js():
        """返回运行编排前端逻辑。"""
        return FileResponse(STATIC_DIR / "execution.js", headers=_NO_CACHE)

    @app.get("/tool-templates.js")
    async def tool_templates_js():
        """返回工具模板管理前端逻辑。"""
        return FileResponse(STATIC_DIR / "tool-templates.js", headers=_NO_CACHE)

    return app


app = create_app()
