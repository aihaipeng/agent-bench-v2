from pathlib import Path


STATIC_DIR = Path(__file__).parents[1] / "web" / "static"


def test_tool_management_exposes_refresh_import_batch_export_and_open_directory():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    export_icon = STATIC_DIR / "assets" / "icons" / "export.png"

    for element_id in (
        "btn-tool-import",
        "tool-import-file",
        "btn-tool-refresh",
        "btn-tool-export-batch",
        "tool-registry-errors",
    ):
        assert element_id in app_js
    assert 'accept=".zip,application/zip" multiple' in app_js
    assert 'accept=".tool.json,application/json"' not in app_js
    assert "API.post('/api/tools/refresh', {})" in app_js
    assert "API.upload('/api/tools/import', formData)" in app_js
    assert "var url = '/api/tools/export'" in app_js
    assert "await downloadToolArchive(checkedIds)" in app_js
    assert "await downloadToolArchive([])" in app_js
    assert "response.blob()" in app_js
    assert 'class="list-meta-link tool-id-link"' in app_js
    assert "if (toolId) openToolDir(toolId)" in app_js
    assert 'data-action="export"' not in app_js
    assert "encodeURIComponent(toolId) + '/open-dir'" in app_js
    assert "export: '/assets/icons/export.png'" in app_js
    toolbar = app_js[app_js.index("id=\"tools-toolbar\"") :]
    assert toolbar.index('id="btn-tool-import"') < toolbar.index(
        'id="btn-tool-export-batch"'
    )
    assert 'id="tool-export-overlay"' in index_html
    assert "当前未勾选工具，将导出全部工具" in index_html
    assert 'id="btn-tool-export-cancel"' in index_html
    assert 'id="btn-tool-export-confirm"' in index_html
    assert export_icon.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_tool_file_errors_remain_visible_with_filename_and_reason():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    style_css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

    assert "function renderToolRegistryErrors(title, errors)" in app_js
    assert "item.file || '未命名文件'" in app_js
    assert "item.error || '未知错误'" in app_js
    assert "以下文件未能加载" in app_js
    assert "以下文件未能导入" in app_js
    assert ".tool-registry-errors" in style_css
    assert ".tool-registry-errors.hidden {\n    display: none;\n}" in style_css
    assert "overflow-wrap: anywhere" in style_css
