from pathlib import Path

from fastapi.testclient import TestClient

from web.app import app


STATIC_DIR = Path(__file__).parents[1] / "web" / "static"


def test_execution_assets_and_navigation_are_registered():
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    execution_js = (STATIC_DIR / "execution.js").read_text(encoding="utf-8")

    for view in ("targets", "workflows"):
        assert f'data-view="{view}"' in index_html
    assert "工作流管理" in index_html
    assert 'data-view="runs"' not in index_html
    assert "运行中心" not in index_html
    assert '<link rel="stylesheet" href="/execution.css" />' in index_html
    assert '<link rel="stylesheet" href="/assets/workflow-canvas.css?v=27" />' in index_html
    assert '<script src="/assets/workflow-canvas.js?v=27"></script>' in index_html
    assert '<script src="/execution.js"></script>' in index_html
    assert 'name="viewport"' not in index_html
    assert "viewTargets();" in app_js
    assert "viewWorkflows();" in app_js
    assert "viewRuns();" not in app_js
    assert "destroyToolCodeEditor" not in execution_js

    client = TestClient(app)
    assert client.get("/execution.css").status_code == 200
    assert client.get("/execution.js").status_code == 200
    assert client.get("/assets/workflow-canvas.css").status_code == 200
    assert client.get("/assets/workflow-canvas.js").status_code == 200
    assert client.get("/execution.css").headers["cache-control"] == (
        "no-cache, no-store, must-revalidate"
    )
    assert client.get("/api/workflows").status_code == 404
    assert client.get("/api/runs").status_code == 404
    assert client.get("/api/workflow-drafts").status_code == 200


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


def test_workflow_list_uses_persistent_drafts_without_legacy_api():
    execution_js = (STATIC_DIR / "execution.js").read_text(encoding="utf-8")
    execution_css = (STATIC_DIR / "execution.css").read_text(encoding="utf-8")

    assert "function viewWorkflows()" in execution_js
    assert "function renderWorkflowTable()" in execution_js
    assert "persistent Workflow Studio" in execution_js
    assert "API.get('/api/workflows')" not in execution_js
    assert "API.post('/api/workflows'" not in execution_js
    assert "API.del('/api/workflows/'" not in execution_js
    assert "API.put('/api/workflows/bindings/'" not in execution_js
    assert "API.del('/api/workflows/bindings/'" not in execution_js
    assert "API.get('/api/workflow-drafts')" in execution_js
    assert "API.get('/api/workflow-drafts/'" in execution_js
    assert "API.post('/api/workflow-drafts', body)" in execution_js
    assert "API.put('/api/workflow-drafts/'" in execution_js
    assert "已持久化" in execution_js
    assert "id=\"workflow-search\"" in execution_js
    assert "id=\"workflow-status-filter\"" in execution_js
    assert "新增工作流" in execution_js
    assert "window.AgentBenchWorkflowCanvas.mount" in execution_js
    assert ".workflow-row-actions" in execution_css
    assert ".workflow-valid" in execution_css
    assert ".workflow-invalid" in execution_css


def test_workflow_editor_uses_fullscreen_react_flow_canvas():
    execution_js = (STATIC_DIR / "execution.js").read_text(encoding="utf-8")
    canvas_jsx = (
        STATIC_DIR.parent / "frontend" / "workflow-canvas.jsx"
    ).read_text(encoding="utf-8")
    canvas_css = (
        STATIC_DIR.parent / "frontend" / "workflow-canvas.css"
    ).read_text(encoding="utf-8")

    assert "function openWorkflowEditor(workflowId)" in execution_js
    assert "window.AgentBenchWorkflowCanvas.mount" in execution_js
    assert "API.get('/api/tools')" not in execution_js[
        execution_js.index("async function openWorkflowEditor(workflowId)"):
    ]
    for token in (
        "ReactFlow",
        "ReactFlowProvider",
        "MiniMap",
        "Controls",
        "onPaneContextMenu",
        "onNodeContextMenu",
        "onNodeDoubleClick",
        "onSelectionChange",
        "onConnect",
        "fitView",
    ):
        assert token in canvas_jsx
    assert "position: fixed" in canvas_css
    assert "min-width: 1180px" in canvas_css
    assert "wf-node-editor-rnd" in canvas_css
    assert "wf-resize-se" in canvas_css
    assert "Math.round(760 * 1.4)" in canvas_jsx
    assert 'selectionKeyCode="Control"' in canvas_jsx
    assert 'multiSelectionKeyCode="Control"' in canvas_jsx
    assert "event.key === 'Delete'" in canvas_jsx
    assert "event.key === 'Backspace'" in canvas_jsx
    assert "copyNodes(selectedIds)" in canvas_jsx
    assert "pasteClipboard()" in canvas_jsx
    assert "const handleNodeClick" in canvas_jsx
    assert 'tabIndex={0}' in canvas_jsx
    assert 'onKeyDown={handleKeyboard}' in canvas_jsx
    assert 'onCopy={handleCopy}' in canvas_jsx
    assert 'onPaste={handlePaste}' in canvas_jsx
    assert 'onPointerDownCapture={handleMarqueeStart}' in canvas_jsx
    assert 'onPointerMoveCapture={handleMarqueeMove}' in canvas_jsx
    assert 'onPointerUpCapture={handleMarqueeEnd}' in canvas_jsx
    assert ".wf-selection-marquee" in canvas_css
    assert "layoutGraph(current, edges)" in canvas_jsx
    assert "dagre.layout(graph)" in canvas_jsx
    assert "undoStack.current" in canvas_jsx
    assert "redoStack.current" in canvas_jsx
    assert "if (control && key === 'z')" in canvas_jsx
    assert 'title="回退"' in canvas_jsx
    assert 'title="前进"' in canvas_jsx
    assert "全局变量" in canvas_jsx
    assert "wf-inspector-footer" not in canvas_jsx
    assert "重试次数" in canvas_jsx
    assert "输出变量" in canvas_jsx
    assert "变量名" in canvas_jsx
    assert "outputVariables: [emptyMappingRow()]" in canvas_jsx
    assert "const legacyOutputVariable = node.data.outputVariable" in canvas_jsx
    assert "const addOutputVariable = ()" in canvas_jsx
    assert "const removeOutputVariable = (id)" in canvas_jsx
    assert 'aria-label={`输出变量名 ${index + 1}`}' in canvas_jsx
    assert "const OUTPUT_VARIABLE_TYPES = ['AUTO', 'STRING', 'INTEGER', 'NUMBER', 'BOOLEAN', 'OBJECT', 'ARRAY']" in canvas_jsx
    assert "return {id: rowId(), name: '', type: 'AUTO', value: ''}" in canvas_jsx
    assert 'aria-label={`输出变量类型 ${index + 1}`}' in canvas_jsx
    assert "value={row.type || 'AUTO'}" in canvas_jsx
    assert 'aria-label={`输出变量 ${index + 1}`}' in canvas_jsx
    assert 'aria-label="添加输出变量"' in canvas_jsx
    assert 'aria-label={`删除输出变量 ${index + 1}`}' in canvas_jsx
    assert "onClick={addOutputVariable}" in canvas_jsx
    assert "onClick={() => removeOutputVariable(row.id)}" in canvas_jsx
    assert "mappingRows('parameters'" not in canvas_jsx
    assert "新增变量名" not in canvas_jsx
    assert "parameterRecords: []" in canvas_jsx
    assert "function parameterDataSummary(value)" in canvas_jsx
    assert "正在接收原始响应…" in canvas_jsx
    assert "text.length > 180" in canvas_jsx
    assert "const NODE_STATUSES = ['PENDING', 'RUNNING', 'PASSED', 'FAILED']" in canvas_jsx
    assert "status: 'PENDING'" in canvas_jsx
    assert "status: 'RUNNING'" in canvas_jsx
    assert "status: 'PASSED'" in canvas_jsx
    assert "function formatExecutionDuration(value)" in canvas_jsx
    assert "executionDurationMs: 0" in canvas_jsx
    assert "Date.now() - startedAtMs" in canvas_jsx
    assert "window.setInterval" in canvas_jsx
    assert 'aria-label={`执行耗时 ${executionDuration}`}' in canvas_jsx
    assert 'className="wf-execution-spinner"' in canvas_jsx
    assert 'aria-label={`运行 ${data.label}`}' in canvas_jsx
    assert 'aria-label={`参数 ${data.label}`}' not in canvas_jsx
    assert "data.onOpenParameters?.()" not in canvas_jsx
    assert 'aria-label="运行当前节点"' in canvas_jsx
    assert 'aria-label="打开当前节点参数"' not in canvas_jsx
    assert 'aria-label="保存当前节点"' in canvas_jsx
    assert "onRun={() => editorNodeId && runNode(editorNodeId)}" in canvas_jsx
    assert "onSave={() => editorNodeId && saveNode(editorNodeId)}" in canvas_jsx
    assert "setNodeSaveNotice" in canvas_jsx
    assert "wf-node-saved-state" in canvas_jsx
    assert "setEditorInitialTab" not in canvas_jsx
    assert "setTab(initialTab)" in canvas_jsx
    assert "const isScript = node.data.nodeType === 'SCRIPT'" in canvas_jsx
    assert "const showParametersTab = !isLlm && !isScript" in canvas_jsx
    assert "showParametersTab && <button type=\"button\" className={tab === 'parameters'" in canvas_jsx
    assert "tab === 'parameters' && showParametersTab" in canvas_jsx
    assert 'role="columnheader">source' in canvas_jsx
    assert 'role="columnheader">name' in canvas_jsx
    assert 'role="columnheader">data' in canvas_jsx
    assert "当前节点尚无运行参数" in canvas_jsx
    assert "parameterDataText(selectedParameter.data, true)" in canvas_jsx
    assert "selectedParameter.artifact?.href" in canvas_jsx
    assert ".wf-node-actions" in canvas_css
    assert ".wf-node-status.is-passed" in canvas_css
    assert "border-top: 3px solid var(--node-accent)" not in canvas_css
    assert ".wf-node.is-selected" in canvas_css
    assert "border-color: #16a34a" in canvas_css
    assert "outline: 2px solid #16a34a" in canvas_css
    assert "linear-gradient(135deg, #eafaf0 0%, #ffffff 52%, #f0fdf4 100%)" in canvas_css
    assert ".wf-node-status.is-failed" in canvas_css
    assert ".wf-node-execution.is-running .wf-execution-spinner" in canvas_css
    assert "animation: wf-execution-spin 0.8s linear infinite" in canvas_css
    assert "@keyframes wf-execution-spin" in canvas_css
    assert ".wf-inspector-actions" in canvas_css
    assert ".wf-node-save-toast" in canvas_css
    assert ".wf-node-log-panel" in canvas_css
    assert ".wf-parameter-table" in canvas_css
    assert ".wf-parameter-detail" in canvas_css
    assert "grid-template-columns: minmax(180px, 0.9fr) minmax(150px, 0.7fr) minmax(0, 2fr)" in canvas_css
    assert ".wf-retry-grid" in canvas_css
    assert ".wf-mapping-value-row" in canvas_css
    assert ".wf-output-variable-row" in canvas_css
    assert ".wf-output-variable-list" in canvas_css
    assert "grid-template-columns: minmax(170px, 0.8fr) minmax(150px, 0.65fr) minmax(260px, 1.4fr) 32px" in canvas_css
    assert "grid-template-columns: 64px minmax(0, 1fr)" in canvas_css
    assert "white-space: nowrap" in canvas_css
    assert "@media" not in canvas_css


def test_workflow_canvas_has_required_context_menus_and_edge_insert():
    canvas_jsx = (
        STATIC_DIR.parent / "frontend" / "workflow-canvas.jsx"
    ).read_text(encoding="utf-8")
    canvas_css = (
        STATIC_DIR.parent / "frontend" / "workflow-canvas.css"
    ).read_text(encoding="utf-8")

    for label in (
        "添加节点",
        "测试运行",
        "粘贴节点",
        "运行此步骤",
        "拷贝",
        "删除",
    ):
        assert label in canvas_jsx
    for node_type in ("START", "HTTP", "AGENT", "LLM", "SCRIPT", "END"):
        assert f"{node_type}:" in canvas_jsx
    assert "const INSERTABLE_TYPES = ['HTTP', 'AGENT', 'LLM', 'SCRIPT']" in canvas_jsx
    assert "Large Language Model" not in canvas_jsx
    assert "Python Script" not in canvas_jsx
    assert "function InsertableEdge" in canvas_jsx
    assert "wf-edge-plus" in canvas_jsx
    assert "onToggleInsert" in canvas_jsx
    assert "onInsert" in canvas_jsx
    assert ".wf-context-menu" in canvas_css
    assert ".wf-edge-picker" in canvas_css


def test_http_node_editor_has_api_import_and_body_controls():
    canvas_jsx = (
        STATIC_DIR.parent / "frontend" / "workflow-canvas.jsx"
    ).read_text(encoding="utf-8")
    canvas_css = (
        STATIC_DIR.parent / "frontend" / "workflow-canvas.css"
    ).read_text(encoding="utf-8")

    assert "type === 'HTTP' ? {httpConfig: defaultHttpConfig()}" in canvas_jsx
    assert "function parseCurlRequest(command)" in canvas_jsx
    assert "parseCurl(normalized)" in canvas_jsx
    assert "splitShellWords(source)" in canvas_jsx
    assert "!explicitMethod && bodyType !== 'none' && parsed.method === 'GET'" in canvas_jsx
    assert "onChange({httpConfig: imported})" in canvas_jsx
    assert "node.data.nodeType === 'HTTP'" in canvas_jsx
    assert 'aria-label="请求方式"' in canvas_jsx
    assert 'aria-label="请求 URL"' in canvas_jsx
    assert 'aria-label="导入 cURL"' in canvas_jsx
    assert '><Upload size={15} /></button>' in canvas_jsx
    assert "['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']" in canvas_jsx
    assert "httpKeyValueSection('HEADERS', 'headers'" in canvas_jsx
    assert "httpKeyValueSection('PARAMS', 'params'" in canvas_jsx
    assert "['none', 'form-data', 'x-www-form-urlencoded', 'raw', 'binary']" in canvas_jsx
    assert "JSON.stringify(JSON.parse(httpConfig.bodyText), null, 2)" in canvas_jsx
    assert "JSON 格式错误" in canvas_jsx
    assert "Beautify" in canvas_jsx
    assert 'aria-label="选择 Binary 文件"' in canvas_jsx
    assert ".wf-http-api-row" in canvas_css
    assert "grid-template-columns: 70px 96px minmax(180px, 1fr) 34px" in canvas_css
    assert "padding-left: 20px" in canvas_css
    assert ".wf-http-kv-heading" in canvas_css
    assert ".wf-http-body-types" in canvas_css
    assert ".wf-http-code-toolbar" in canvas_css
    assert ".wf-http-code-editor" in canvas_css


def test_canvas_defines_tool_nodes_only_inside_workflow():
    canvas_jsx = (
        STATIC_DIR.parent / "frontend" / "workflow-canvas.jsx"
    ).read_text(encoding="utf-8")
    canvas_css = (
        STATIC_DIR.parent / "frontend" / "workflow-canvas.css"
    ).read_text(encoding="utf-8")

    assert "const DEFAULT_MAIN_PY = 'response = inputs'" in canvas_jsx
    assert "value={node.data.mainPy ?? DEFAULT_MAIN_PY}" in canvas_jsx
    assert "onChange={(event) => onChange({mainPy: event.target.value})}" in canvas_jsx
    assert "makeNode(type, position)" in canvas_jsx
    assert "type === 'HTTP' ? {httpConfig: defaultHttpConfig()}" in canvas_jsx
    for removed in (
        "/api/tool-templates",
        "工具模板",
        "发布为工具模板",
        "toolTemplates",
        "templateLoadState",
        "templateDefinition",
        "httpConfigFromTemplate",
        "publishNode",
    ):
        assert removed not in canvas_jsx
    assert ".wf-template-popover" not in canvas_css
    assert ".wf-template-list" not in canvas_css


def test_llm_node_uses_saved_models_and_framework_independent_parameters():
    canvas_jsx = (
        STATIC_DIR.parent / "frontend" / "workflow-canvas.jsx"
    ).read_text(encoding="utf-8")
    canvas_css = (
        STATIC_DIR.parent / "frontend" / "workflow-canvas.css"
    ).read_text(encoding="utf-8")

    assert "...(type === 'LLM' ? {" in canvas_jsx
    assert "systemPrompt: ''" in canvas_jsx
    assert "userPrompt: ''" in canvas_jsx
    assert "modelParameters: {}" in canvas_jsx
    assert "fetch('/api/model-providers'" in canvas_jsx
    assert "function ModelSelector(" in canvas_jsx
    assert 'placeholder="搜索供应商或模型"' in canvas_jsx
    assert 'role="option"' in canvas_jsx
    assert "onSelect(provider.id, model)" in canvas_jsx
    assert "模型已失效" in canvas_jsx
    assert 'aria-label="模型高级参数 JSON"' in canvas_jsx
    assert 'aria-label="系统提示词"' in canvas_jsx
    assert 'aria-label="用户提示词"' in canvas_jsx
    assert 'aria-label="插入提示词变量"' not in canvas_jsx
    assert "insertPromptVariable" not in canvas_jsx
    assert "if (!isPlainObject(parsed))" in canvas_jsx
    assert "delete parsed.stream" in canvas_jsx
    assert "onChange({modelParameters: parsed})" in canvas_jsx
    assert "请选择有效模型、填写用户提示词并修正高级参数" in canvas_jsx
    assert "meta.executable && !isLlm" in canvas_jsx
    assert "!isLlm && <button" in canvas_jsx
    assert "<NodeRunHistory runs={node.data.runHistory || []} nodeType={node.data.nodeType} />" in canvas_jsx
    assert ".slice(0, 10)" in canvas_jsx
    assert "formatRunDate(run.finished_at || run.started_at)" in canvas_jsx
    assert "原始响应" in canvas_jsx
    assert "原始 stderr" in canvas_jsx
    assert "run.response_body" in canvas_jsx
    assert "原始请求" in canvas_jsx
    assert "原始 stdout" in canvas_jsx
    assert "原始 response" in canvas_jsx
    assert "原始 stderr" in canvas_jsx
    assert "错误 traceback" in canvas_jsx
    assert "输入快照" not in canvas_jsx
    assert "Token usage" not in canvas_jsx
    assert 'role="switch" aria-label="流式输出"' in canvas_jsx
    assert "checked={streamEnabled}" in canvas_jsx
    assert "setStreamMode(event.target.checked)" in canvas_jsx
    assert "const showOutputVariables = !isLlm || !streamEnabled" in canvas_jsx
    assert "{showOutputVariables && (" in canvas_jsx
    assert "const streaming = targetNode.data.nodeType === 'LLM' && targetNode.data.modelParameters?.stream === true" in canvas_jsx
    assert "const suffix = streaming ? '/runs/stream' : '/runs'" in canvas_jsx
    assert 'aria-label="查看节点变量"' in canvas_jsx
    assert 'aria-label="节点可用变量"' in canvas_jsx
    assert "copyTextToClipboard(parameterDataText(variable.value, true))" in canvas_jsx
    assert "await navigator.clipboard.writeText(text)" in canvas_jsx
    assert "catch (_error)" in canvas_jsx
    assert "textarea.setSelectionRange(0, textarea.value.length)" in canvas_jsx
    assert "document.execCommand('copy')" in canvas_jsx
    assert 'aria-label={`复制变量值 ${variable.name}`}' in canvas_jsx
    assert "disabled={!variable.available}" in canvas_jsx
    assert "全局变量" in canvas_jsx
    assert "/variables`" in canvas_jsx
    assert "persistDraft()" in canvas_jsx
    assert "/api/workflow-drafts/${encodeURIComponent(activeWorkflowId)}/nodes/${encodeURIComponent(id)}/runs" in canvas_jsx
    assert "['HTTP', 'AGENT', 'LLM', 'SCRIPT'].includes(targetNode?.data.nodeType)" in canvas_jsx
    assert "apiKey" not in canvas_jsx
    assert "api_key" not in canvas_jsx
    assert "model_kwargs" not in canvas_jsx
    assert ".wf-model-picker" in canvas_css
    assert ".wf-model-provider-group" in canvas_css
    assert ".wf-model-option.is-selected" in canvas_css
    assert ".wf-llm-prompt-field" in canvas_css
    assert ".wf-llm-stream-switch" in canvas_css
    assert ".wf-llm-stream-field > span" in canvas_css
    assert "min-height: 19px" in canvas_css
    assert "font-weight: 700" in canvas_css
    assert ".wf-llm-stream-control" not in canvas_css
    assert ".wf-llm-run-summary" in canvas_css
    assert ".wf-llm-run-detail" in canvas_css
    assert ".wf-node-variable-panel" in canvas_css
    assert ".wf-node-variable-row button" in canvas_css
    assert "minmax(0, 1.6fr) 28px" in canvas_css
    assert "const [editorScale, setEditorScale] = useState(1)" in canvas_jsx
    assert "const editorBaseSizeRef = useRef(null)" in canvas_jsx
    assert "const updateEditorScale = (_event, _direction, ref)" in canvas_jsx
    assert "onResize={updateEditorScale}" in canvas_jsx
    assert "onResizeStop={updateEditorScale}" in canvas_jsx
    assert "className=\"wf-inspector-scale-shell\"" in canvas_jsx
    assert "transform: `scale(${editorScale})`" in canvas_jsx
    assert ".wf-inspector-scale-shell" in canvas_css
    assert "@media" not in canvas_css
