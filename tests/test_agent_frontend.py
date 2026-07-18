from pathlib import Path


STATIC_DIR = Path(__file__).parents[1] / "web" / "static"


def test_agent_editor_contains_only_six_parameters_python_code_and_run_action():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    for element_id in (
        "tool-model",
        "tool-model-provider",
        "tool-api-key",
        "tool-base-url",
        "tool-agent-prompt",
        "tool-human-message",
        "tool-python-editor",
        "btn-tool-agent-test",
    ):
        assert element_id in app_js
    assert "参数定义" in app_js
    assert "Python 代码" in app_js
    assert "运行 Agent" in app_js
    assert "旧自定义代码已迁移" in app_js


def test_python_editor_is_loaded_for_agent_and_script_without_textareas():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert "/assets/codemirror-python.js?v=1" in index_html
    assert index_html.index("codemirror-python.js") < index_html.index("app.js")
    assert "window.PythonCodeEditor.create" in app_js
    assert 'id="tool-python-editor"' in app_js
    assert 'id="tool-script-editor"' in app_js
    assert 'id="tool-python-code"' not in app_js
    assert 'id="tool-script-code"' not in app_js


def test_removed_agent_concepts_have_no_frontend_controls_or_logic():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    style_css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
    combined = "\n".join((app_js, index_html, style_css)).lower()

    for removed in (
        "print format",
        "print-format",
        "additional components",
        "additional-components",
        "test-llm",
        "tool-temperature",
        "tool-extra-body",
        "tool-max-tokens",
        "tool-request-timeout",
        "btn-llm-test",
    ):
        assert removed not in combined
