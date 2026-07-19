import re
from pathlib import Path


STATIC_DIR = Path(__file__).parents[1] / "web" / "static"


def test_faq_is_a_top_level_read_only_view():
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'data-view="faq"' in index_html
    assert "❓ FAQ" in index_html
    assert "else if (view === 'faq')" in app_js
    assert "function viewFaq()" in app_js
    assert '<details class="faq-item">' in app_js
    assert "btn-faq-save" not in app_js
    assert "faq-editor" not in app_js
    assert "/api/faq" not in app_js


def test_faq_supports_search_categories_and_dependency_lifecycle_content():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert len(re.findall(r"\n\s*question: '", app_js)) == 12
    assert "document.getElementById('faq-search').addEventListener('input'" in app_js
    assert "document.getElementById('faq-category').addEventListener('change'" in app_js
    assert "faqSearchText(item).includes(query)" in app_js

    for category in ("安装", "验证", "管理", "故障", "安全"):
        assert f'<option value="{category}">{category}</option>' in app_js

    for required_content in (
        "ModuleNotFoundError",
        "pyproject.toml",
        "uv sync",
        "uv add",
        "uv remove",
        "升级或降级",
        "如何回滚",
        "不需要关闭页面",
        "uv run pytest",
        "Python 3.14",
    ):
        assert required_content in app_js


def test_faq_styles_keep_long_commands_scrollable_without_mobile_breakpoints():
    style_css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

    for selector in (
        ".faq-page",
        ".faq-toolbar",
        ".faq-item summary",
        ".faq-answer pre",
        ".faq-table-wrap",
        ".faq-empty",
    ):
        assert selector in style_css
    assert "overflow-x: auto" in style_css
    assert "@media (max-width: 720px)" not in style_css
