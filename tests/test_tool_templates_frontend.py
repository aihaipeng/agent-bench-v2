from pathlib import Path

from fastapi.testclient import TestClient

from web.app import app


STATIC_DIR = Path(__file__).parents[1] / "web" / "static"


def test_tool_template_navigation_and_asset_are_registered():
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'data-view="tools">🧰 工具模板' in index_html
    assert '<script src="/tool-templates.js"></script>' in index_html
    assert "viewToolTemplates();" in app_js
    response = TestClient(app).get("/tool-templates.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"


def test_tool_template_page_uses_uppercase_types_and_new_api():
    source = (STATIC_DIR / "tool-templates.js").read_text(encoding="utf-8")

    for template_type in ("HTTP", "AGENT", "LLM", "SCRIPT"):
        assert f"<option>{template_type}</option>" in source
    assert "API.get('/api/tool-templates')" in source
    assert "API.post('/api/tool-templates'" in source
    assert "API.put('/api/tool-templates/'" in source
    assert "API.del('/api/tool-templates/'" in source
    assert "execution_mode" in source
    assert "template-inputs" in source
    assert "template-config" in source
    assert "template-outputs" in source
    assert "template-main-py" in source
    assert 'id="btn-tool-template-import"' in source
    assert 'id="btn-tool-template-export-all"' in source
    assert 'data-template-export="' in source
    assert "API.upload('/api/tool-templates/import'" in source
    assert "fetch('/api/tool-templates/export'" in source
    assert "JSON.stringify({template_ids: templateIds})" in source
    assert "导出不会自动清理 config 或 main.py 中的凭据" in source
    assert 'aria-label="模板独立测试"' in source
    assert 'id="template-test-inputs"' in source
    assert 'id="template-test-run"' in source
    assert 'id="template-test-interrupt"' in source
    assert "saveToolTemplate(template, {reload: false, silent: true})" in source
    assert "'/api/tool-templates/' + encodeURIComponent(run.templateId) + '/runs'" in source
    assert "new EventSource('/api/tool-templates/runs/'" in source
    assert "'/interrupt'" in source
    assert "setTemplateRunStatus('RUNNING', performance.now() - run.startedAt)" in source
    assert "finishToolTemplateRun(run, payload.result && payload.result.ok ? 'PASSED' : 'FAILED'" in source
    assert "/api/tools" not in source
