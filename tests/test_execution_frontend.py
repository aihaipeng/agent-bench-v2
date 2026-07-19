from pathlib import Path

from fastapi.testclient import TestClient

from web.app import app


STATIC_DIR = Path(__file__).parents[1] / "web" / "static"


def test_execution_assets_and_navigation_are_registered():
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    for view in ("targets", "workflows", "runs"):
        assert f'data-view="{view}"' in index_html
    assert "工作流编排" in index_html
    assert "运行中心" in index_html
    assert '<link rel="stylesheet" href="/execution.css" />' in index_html
    assert '<script src="/execution.js"></script>' in index_html
    assert 'name="viewport"' not in index_html
    assert "viewTargets();" in app_js
    assert "viewWorkflows();" in app_js
    assert "viewRuns();" in app_js

    client = TestClient(app)
    assert client.get("/execution.css").status_code == 200
    assert client.get("/execution.js").status_code == 200
    assert client.get("/execution.css").headers["cache-control"] == (
        "no-cache, no-store, must-revalidate"
    )


def test_target_page_uses_complete_crud_api_and_validated_form():
    execution_js = (STATIC_DIR / "execution.js").read_text(encoding="utf-8")
    execution_css = (STATIC_DIR / "execution.css").read_text(encoding="utf-8")

    assert "function viewTargets()" in execution_js
    assert "function openTargetEditor(targetId)" in execution_js
    assert "function readTargetForm()" in execution_js
    assert "function deleteTarget(targetId)" in execution_js
    assert "API.get('/api/targets')" in execution_js
    assert "API.post('/api/targets', body)" in execution_js
    assert "API.put('/api/targets/'" in execution_js
    assert "API.del('/api/targets/'" in execution_js
    for element_id in (
        "target-name",
        "target-base-url",
        "target-path",
        "target-concurrency",
        "target-headers",
    ):
        assert element_id in execution_js
    assert "Headers 必须是合法 JSON 对象" in execution_js
    assert "Target 总并发必须是正整数" in execution_js
    assert ".execution-table-wrap" in execution_css
    assert ".execution-form-grid" in execution_css
    assert "@media (max-width: 760px)" not in execution_css


def test_workflow_list_supports_copy_delete_validation_and_testset_binding():
    execution_js = (STATIC_DIR / "execution.js").read_text(encoding="utf-8")
    execution_css = (STATIC_DIR / "execution.css").read_text(encoding="utf-8")

    assert "function viewWorkflows()" in execution_js
    assert "function renderWorkflowTable()" in execution_js
    assert "function copyWorkflow(workflowId)" in execution_js
    assert "function deleteWorkflow(workflowId)" in execution_js
    assert "function openWorkflowBinding(workflowId)" in execution_js
    assert "API.get('/api/workflows')" in execution_js
    assert "API.post('/api/workflows'" in execution_js
    assert "API.del('/api/workflows/'" in execution_js
    assert "API.put('/api/workflows/bindings/'" in execution_js
    assert "API.del('/api/workflows/bindings/'" in execution_js
    assert "workflow.validation_errors" in execution_js
    assert "workflow.binding_count" in execution_js
    assert "id=\"workflow-search\"" in execution_js
    assert ".workflow-row-actions" in execution_css
    assert ".workflow-valid" in execution_css
    assert ".workflow-invalid" in execution_css


def test_workflow_editor_uses_fixed_topology_tool_rules_and_node_inspector():
    execution_js = (STATIC_DIR / "execution.js").read_text(encoding="utf-8")
    execution_css = (STATIC_DIR / "execution.css").read_text(encoding="utf-8")

    for function_name in (
        "openWorkflowEditor(workflowId)",
        "renderWorkflowCanvas()",
        "renderWorkflowToolLibrary()",
        "renderWorkflowInspector()",
        "clientWorkflowValidation()",
        "saveWorkflowDraft()",
        "moveWorkflowParser(index, offset)",
    ):
        assert f"function {function_name}" in execution_js
    assert "Response" in execution_js
    assert "顺序 Parser" in execution_js
    assert "并行 Checks" in execution_js
    assert "Case Result" in execution_js
    assert "Aggregator 只允许 Script" in execution_js
    assert "多个 Evaluator 需要 Check Aggregator" in execution_js
    assert "多个 Check 需要 Case Aggregator" in execution_js
    assert "tool.output_example_configured" in execution_js
    assert "executionRequest('POST', '/api/workflows'" in execution_js
    assert "executionRequest('PUT', '/api/workflows/'" in execution_js
    assert "data-parser-up" in execution_js
    assert "data-parser-down" in execution_js
    assert ".workflow-editor-grid" in execution_css
    assert 'grid-template-areas:\n        "tools canvas inspector"' in execution_css
    assert ".workflow-flow-grid" in execution_css
    assert ".workflow-check-grid" in execution_css
    assert ".workflow-validation" in execution_css


def test_workflow_input_mapping_supports_tree_segments_and_advanced_pointer():
    execution_js = (STATIC_DIR / "execution.js").read_text(encoding="utf-8")
    execution_css = (STATIC_DIR / "execution.css").read_text(encoding="utf-8")

    for function_name in (
        "encodeJsonPointer(segments)",
        "decodeJsonPointer(pointer)",
        "resolveExamplePointer(value, pointer)",
        "displayMappingPath(source, pointer)",
        "renderJsonFieldTree(value, segments, depth)",
        "renderWorkflowInputEditor(kind, step)",
        "workflowAvailableSources(kind, step)",
    ):
        assert f"function {function_name}" in execution_js
    assert "字段树" in execution_js
    assert "分段路径" in execution_js
    assert "高级 Pointer" in execution_js
    assert "replace(/~/g, '~0').replace(/\\//g, '~1')" in execution_js
    assert "Parser / " in execution_js
    assert "Aggregator 输入由系统注入" in execution_js
    assert "来源节点不可用或执行顺序不合法" in execution_js
    assert "resolveExamplePointer(example.value, reference.pointer)" in execution_js
    assert ".workflow-field-tree" in execution_css
    assert ".workflow-segment-list" in execution_css
    assert ".workflow-mapping-preview" in execution_css
    assert 'id="workflow-segment-add"' not in execution_js
    assert 'id="workflow-segment-value"' not in execution_js
    assert 'id="workflow-pointer-value"' not in execution_js
    assert "nameInput.addEventListener('input'" in execution_js
    assert "mapping.setAttribute('data-input-name', next)" in execution_js


def test_run_center_supports_history_template_context_and_queued_creation():
    execution_js = (STATIC_DIR / "execution.js").read_text(encoding="utf-8")
    execution_css = (STATIC_DIR / "execution.css").read_text(encoding="utf-8")

    for function_name in (
        "viewRuns()",
        "renderRunHistory()",
        "loadRunSetContext()",
        "validateRunTemplate()",
        "readRunParameters()",
        "createQueuedRun()",
    ):
        assert f"function {function_name}" in execution_js
    assert "API.get('/api/runs?limit=500')" in execution_js
    assert "'/api/excel/sheets?filename='" in execution_js
    assert "'/api/workflows/bindings/'" in execution_js
    assert "'/request-template'" in execution_js
    assert "executionRequest('PUT', '/api/runs/testsets/'" in execution_js
    assert "executionRequest('POST', '/api/runs'" in execution_js
    assert "data.run.status !== 'QUEUED'" in execution_js
    assert "超时必须大于 0" in execution_js
    assert "Case 并发必须是正整数" in execution_js
    assert "忽略 " in execution_js and "个 Sheet" in execution_js
    assert ".run-history-table" in execution_css
    assert ".run-create-layout" in execution_css
    assert ".run-template-panel" in execution_css
    assert ".run-status-running" in execution_css


def test_run_detail_uses_live_events_persisted_recovery_and_artifact_downloads():
    execution_js = (STATIC_DIR / "execution.js").read_text(encoding="utf-8")
    execution_css = (STATIC_DIR / "execution.css").read_text(encoding="utf-8")

    for function_name in (
        "connectRunEvents(runId)",
        "disconnectRunEvents()",
        "openRunDetail(runId)",
        "refreshRunDetail(runId)",
        "startRunFromDetail(runId)",
        "cancelRunFromDetail(runId)",
        "resumeRunFromDetail(runId, caseRunIds)",
        "loadCaseTrace(caseRunId)",
        "renderCaseTrace()",
    ):
        assert f"function {function_name}" in execution_js
    assert "new EventSource('/api/runs/'" in execution_js
    assert "source.addEventListener('run_state'" in execution_js
    assert "source.addEventListener('case_state'" in execution_js
    assert "source.addEventListener('run_terminal'" in execution_js
    assert execution_js.index("await connectRunEvents(runId)") < execution_js.index("'/start'")
    assert "caseRun.status === 'SUCCEEDED'" in execution_js
    assert "['QUEUED', 'ERROR', 'CANCELLED', 'RUNNING']" in execution_js
    assert "'/cases/' + encodeURIComponent(caseRunId)" in execution_js
    assert "encodeURIComponent(trace.case.run_id)" in execution_js
    assert "encodeURIComponent(artifact.id)" in execution_js
    assert "/download" in execution_js
    assert "Attempts " in execution_js
    assert "Steps " in execution_js
    assert "Artifacts " in execution_js
    assert ".run-detail-summary" in execution_css
    assert ".run-case-table" in execution_css
    assert ".run-trace-tabs" in execution_css
