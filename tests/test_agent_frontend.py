from pathlib import Path


STATIC_DIR = Path(__file__).parents[1] / "web" / "static"


def test_agent_editor_contains_only_six_parameters_python_code_and_run_action():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    for element_id in (
        "tool-model",
        "tool-model-provider",
        "tool-api-key",
        "btn-api-key-visibility",
        "tool-base-url",
        "tool-agent-prompt",
        "tool-human-message",
        "tool-python-editor",
        "btn-tool-agent-test",
        "btn-tool-agent-interrupt",
        "btn-tool-script-interrupt",
        "btn-agent-code-copy",
        "btn-script-code-copy",
    ):
        assert element_id in app_js
    assert "参数定义" in app_js
    assert "Python 代码" in app_js
    assert "运行 Agent" not in app_js
    assert app_js.count('type="button">运行</button>') == 2
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


def test_python_tool_runs_render_optional_structured_response():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "Object.prototype.hasOwnProperty.call(result, 'response')" in app_js
    assert "JSON.stringify(result.response, null, 2)" in app_js
    assert "function appendToolRunResult(run, result)" in app_js
    assert "appendToolRunLog(run, separator + 'response:" in app_js
    assert "script-test-status" in app_js
    assert "正在独立子进程执行 Python 代码" in app_js
    assert "placeholderPattern.test(body.python_code) && !body[field]" in app_js


def test_agent_save_only_validates_name_while_run_validates_agent_fields():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "Object.assign(body, readAgentForm());" in app_js
    assert "function validateAgentRun(body)" in app_js
    assert "if (!validateAgentRun(body)) return;" in app_js
    assert "if (!agentParams) return;" not in app_js


def test_api_key_visibility_toggle_defaults_hidden_and_preserves_field_value():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    style_css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

    assert 'type="password" class="input" id="tool-api-key"' in app_js
    assert 'aria-label="显示 API Key"' in app_js
    assert 'aria-pressed="false"' in app_js
    assert "function toggleApiKeyVisibility()" in app_js
    assert "event.key === 'Enter' || event.key === ' '" in app_js
    assert "event.preventDefault()" in app_js
    assert "input.type = visible ? 'text' : 'password'" in app_js
    assert "button.classList.toggle('is-visible', visible)" in app_js
    assert "button.setAttribute('aria-pressed', String(visible))" in app_js
    assert ".api-key-input-wrap" in style_css
    assert ".api-key-visibility-btn.is-visible .api-key-eye-slash" in style_css


def test_python_tool_run_controls_support_interrupt_and_timed_summaries():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    style_css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

    assert "function interruptActiveToolRun()" in app_js
    assert "body.run_id = run.runId" in app_js
    assert "run_id: run.runId" in app_js
    assert "run.controller.abort()" in app_js
    assert "Interrupted" in app_js
    assert "FAILED" in app_js
    assert "SUCCESS" in app_js
    assert "status.querySelector('.tool-run-elapsed')" in app_js
    assert "elapsedNode.textContent = elapsed" in app_js
    assert "toFixed(1) + ' S'" in app_js
    assert "tool-run-spinner" in app_js
    assert "@keyframes tool-run-spin" in style_css
    assert ".agent-test-status.status-running" in style_css
    assert ".agent-test-status.status-interrupted" in style_css
    assert app_js.count('class="btn agent-log-copy-btn"') == 2
    assert "background: #dcfce7" in style_css
    assert "color: #166534" in style_css


def test_python_tool_runs_consume_sse_log_and_terminal_events():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/test/start" in app_js
    assert "/run/start" in app_js
    assert "new EventSource(" in app_js
    assert "source.addEventListener('log'" in app_js
    assert "source.addEventListener('complete'" in app_js
    assert "source.addEventListener('interrupted'" in app_js
    assert "run.log.appendChild(document.createTextNode(text))" in app_js
    assert "run.log.scrollTop = run.log.scrollHeight" in app_js


def test_agent_and_script_code_editors_have_matching_copy_actions():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    style_css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

    assert 'id="btn-agent-code-copy"' in app_js
    assert 'id="btn-script-code-copy"' in app_js
    assert app_js.count('class="btn agent-log-copy-btn code-copy-btn"') == 2
    assert app_js.count("copyTextToClipboard(getToolCodeValue())") == 2
    assert "function copyTextToClipboard(text)" in app_js
    assert ".edit-section-title-row" in style_css
    assert ".edit-section-title-row .code-copy-btn" in style_css


def test_tool_edit_header_centers_title_and_updates_uuid_time_metadata():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    style_css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

    assert 'class="breadcrumb tool-edit-header"' in app_js
    assert 'class="tool-edit-header-left"' in app_js
    assert 'class="breadcrumb-title tool-edit-header-title">编辑工具</span>' in app_js
    assert "tool-edit-header-type" in app_js
    assert 'id="tool-edit-file-meta"' in app_js
    assert "tool.updated_at !== tool.created_at" in app_js
    assert "tool.id + (timestamp ? ' · ' + formatDateTime(timestamp) : '')" in app_js
    assert "var data = await API.put('/api/tools/'" in app_js
    assert "updateToolEditFileMeta(tool)" in app_js

    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)" in style_css
    assert ".tool-edit-header-title" in style_css
    assert "justify-self: center" in style_css
    assert ".tool-edit-header-type" in style_css
    assert "justify-self: end" in style_css
