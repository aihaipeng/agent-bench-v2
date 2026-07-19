/* ===== Enterprise Agent execution UI ===== */
var executionState = {
    targets: [],
    workflows: [],
    tools: [],
    sets: [],
    runs: [],
    editingTargetId: null,
    workflowId: null,
    workflowDraft: null,
    workflowSelection: null,
    workflowToolMode: 'parser',
    workflowToolQuery: '',
    workflowMappingModes: {},
    runsTab: 'history',
    runSetContext: null,
    runDetail: null,
    runArtifacts: [],
    runEventSource: null,
    runEventRunId: null,
    selectedCaseIds: {},
    caseTrace: null,
    caseTraceTab: 'attempts',
};

async function executionRequest(method, url, body) {
    var options = {method: method, headers: {'Content-Type': 'application/json'}};
    if (body !== undefined) options.body = JSON.stringify(body);
    var response = await fetch(url, options);
    var data = await response.json().catch(function () { return {}; });
    if (response.ok) return data;
    var detail = data.detail;
    var error;
    if (detail && typeof detail === 'object' && Array.isArray(detail.errors)) {
        error = new Error(detail.message || '请求校验失败');
        error.validationErrors = detail.errors;
    } else if (Array.isArray(detail)) {
        error = new Error(detail.map(function (item) {
            return (item.loc || []).join('.') + '：' + item.msg;
        }).join('；'));
    } else {
        error = new Error(typeof detail === 'string' ? detail : response.statusText || '请求失败');
    }
    throw error;
}

function executionLoading(label) {
    contentArea.innerHTML =
        '<div class="execution-loading" role="status">' + esc(label || '正在加载') + '</div>';
}

function executionEmpty(title, actionLabel, actionId) {
    return '<div class="execution-empty">' +
        '<strong>' + esc(title) + '</strong>' +
        (actionLabel ? '<button class="btn btn-primary btn-sm" id="' + actionId + '">' + icon('add') + esc(actionLabel) + '</button>' : '') +
    '</div>';
}

function executionErrorMessage(error) {
    var message = error && error.message ? error.message : String(error || '请求失败');
    return message === '[object Object]' ? '请求参数校验失败' : message;
}

function ensureExecutionModal() {
    var overlay = document.getElementById('execution-overlay');
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'execution-overlay';
    overlay.className = 'overlay hidden';
    overlay.innerHTML = '<div class="modal execution-modal" role="dialog" aria-modal="true" aria-labelledby="execution-modal-title">' +
        '<div class="modal-header" id="execution-modal-title"></div>' +
        '<div class="modal-body" id="execution-modal-body"></div>' +
        '<div class="modal-footer">' +
            '<button class="btn btn-secondary" id="execution-modal-cancel" type="button">取消</button>' +
            '<button class="btn btn-primary" id="execution-modal-save" type="button">保存</button>' +
        '</div>' +
    '</div>';
    document.body.appendChild(overlay);
    overlay.addEventListener('click', function (event) {
        if (event.target === overlay) closeExecutionModal();
    });
    overlay.querySelector('#execution-modal-cancel').addEventListener('click', closeExecutionModal);
    return overlay;
}

function closeExecutionModal() {
    var overlay = document.getElementById('execution-overlay');
    if (overlay) overlay.classList.add('hidden');
}

function openExecutionModal(title, bodyHtml, onSave, saveLabel) {
    var overlay = ensureExecutionModal();
    overlay.querySelector('#execution-modal-title').textContent = title;
    overlay.querySelector('#execution-modal-body').innerHTML = bodyHtml;
    var save = overlay.querySelector('#execution-modal-save');
    save.textContent = saveLabel || '保存';
    save.disabled = false;
    save.onclick = async function () {
        save.disabled = true;
        try {
            await onSave();
        } finally {
            save.disabled = false;
        }
    };
    overlay.classList.remove('hidden');
    var focusable = overlay.querySelector('input, select, textarea');
    if (focusable) focusable.focus();
}

function targetAddress(target) {
    return String(target.base_url || '').replace(/\/$/, '') + String(target.path || '');
}

function renderTargetTable() {
    var body = document.getElementById('target-list-body');
    var count = document.getElementById('target-count');
    if (!body || !count) return;
    count.textContent = executionState.targets.length + ' 个 Target';
    if (executionState.targets.length === 0) {
        body.innerHTML = '<tr><td colspan="7">' + executionEmpty('尚未配置 Target', '新增 Target', 'target-empty-add') + '</td></tr>';
        var emptyAdd = document.getElementById('target-empty-add');
        if (emptyAdd) emptyAdd.addEventListener('click', function () { openTargetEditor(); });
        return;
    }
    body.innerHTML = executionState.targets.map(function (target) {
        var headerCount = Object.keys(target.headers || {}).length;
        return '<tr>' +
            '<td><button class="execution-name-button" type="button" data-target-edit="' + esc(target.id) + '">' + esc(target.name) + '</button>' +
                '<div class="execution-id">' + esc(target.id) + '</div></td>' +
            '<td><code class="target-address">' + esc(targetAddress(target)) + '</code></td>' +
            '<td><span class="execution-badge execution-badge-neutral">' + esc(target.method) + '</span></td>' +
            '<td>' + headerCount + '</td>' +
            '<td>' + target.target_total_concurrency + '</td>' +
            '<td>' + esc(formatDateTime(target.updated_at)) + '</td>' +
            '<td><div class="execution-row-actions">' +
                '<button class="btn-icon" type="button" data-target-edit="' + esc(target.id) + '" title="编辑 Target" aria-label="编辑 Target">' + icon('edit') + '</button>' +
                '<button class="btn-icon" type="button" data-target-delete="' + esc(target.id) + '" title="删除 Target" aria-label="删除 Target">' + icon('trash') + '</button>' +
            '</div></td>' +
        '</tr>';
    }).join('');
    body.querySelectorAll('[data-target-edit]').forEach(function (button) {
        button.addEventListener('click', function () { openTargetEditor(button.getAttribute('data-target-edit')); });
    });
    body.querySelectorAll('[data-target-delete]').forEach(function (button) {
        button.addEventListener('click', function () { deleteTarget(button.getAttribute('data-target-delete')); });
    });
}

async function loadTargets() {
    try {
        var data = await API.get('/api/targets');
        executionState.targets = data.targets || [];
        renderTargetTable();
    } catch (error) {
        showToast(executionErrorMessage(error), 'error');
        var body = document.getElementById('target-list-body');
        if (body) body.innerHTML = '<tr><td colspan="7"><div class="execution-empty"><strong>Target 加载失败</strong></div></td></tr>';
    }
}

function viewTargets() {
    destroyToolCodeEditor();
    currentView = 'targets';
    contentArea.innerHTML =
        '<section class="execution-page" aria-labelledby="targets-title">' +
            '<header class="execution-page-header">' +
                '<div><h1 id="targets-title">Target 管理</h1><p>企业 Agent FastAPI 环境与共享请求并发</p></div>' +
                '<span class="execution-count" id="target-count">0 个 Target</span>' +
            '</header>' +
            '<div class="toolbar execution-toolbar">' +
                '<button class="btn btn-primary" id="btn-target-add" type="button">' + icon('add') + '新增 Target</button>' +
                '<button class="btn" id="btn-target-refresh" type="button">' + icon('refresh') + '刷新</button>' +
            '</div>' +
            '<div class="table-wrap execution-table-wrap"><table class="table execution-table" id="targets-table">' +
                '<thead><tr><th>名称</th><th>请求地址</th><th>方法</th><th>Headers</th><th>总并发</th><th>更新时间</th><th>操作</th></tr></thead>' +
                '<tbody id="target-list-body"><tr><td colspan="7"><div class="execution-loading">正在加载 Target</div></td></tr></tbody>' +
            '</table></div>' +
        '</section>';
    document.getElementById('btn-target-add').addEventListener('click', function () { openTargetEditor(); });
    document.getElementById('btn-target-refresh').addEventListener('click', loadTargets);
    loadTargets();
}

function targetFormHtml(target) {
    target = target || {
        name: '', base_url: 'http://127.0.0.1:9000', path: '/api/agent/invoke',
        method: 'POST', headers: {}, target_total_concurrency: 1,
    };
    return '<div class="execution-form-grid">' +
        '<label class="form-row"><span class="form-label">名称</span><input class="input" id="target-name" maxlength="120" value="' + esc(target.name) + '" /></label>' +
        '<label class="form-row"><span class="form-label">HTTP 方法</span><select class="input" id="target-method" disabled><option value="POST">POST</option></select></label>' +
        '<label class="form-row form-row-full"><span class="form-label">Base URL</span><input class="input" id="target-base-url" value="' + esc(target.base_url) + '" /></label>' +
        '<label class="form-row form-row-full"><span class="form-label">Path</span><input class="input" id="target-path" value="' + esc(target.path) + '" /></label>' +
        '<label class="form-row"><span class="form-label">Target 总并发</span><input class="input" id="target-concurrency" type="number" min="1" step="1" value="' + target.target_total_concurrency + '" /></label>' +
        '<label class="form-row form-row-full"><span class="form-label">Headers（JSON 对象）</span><textarea class="input execution-code-input" id="target-headers" rows="5">' + esc(JSON.stringify(target.headers || {}, null, 2)) + '</textarea></label>' +
        '<div class="execution-form-error form-row-full hidden" id="target-form-error" role="alert"></div>' +
    '</div>';
}

function readTargetForm() {
    var name = document.getElementById('target-name').value.trim();
    var baseUrl = document.getElementById('target-base-url').value.trim();
    var path = document.getElementById('target-path').value.trim();
    var concurrency = Number(document.getElementById('target-concurrency').value);
    if (!name) throw new Error('名称不能为空');
    if (!baseUrl) throw new Error('Base URL 不能为空');
    if (!path) throw new Error('Path 不能为空');
    if (!Number.isInteger(concurrency) || concurrency < 1) throw new Error('Target 总并发必须是正整数');
    var headers;
    try {
        headers = JSON.parse(document.getElementById('target-headers').value || '{}');
    } catch (error) {
        throw new Error('Headers 必须是合法 JSON 对象');
    }
    if (!headers || Array.isArray(headers) || typeof headers !== 'object') throw new Error('Headers 必须是 JSON 对象');
    Object.keys(headers).forEach(function (key) {
        if (typeof headers[key] !== 'string') throw new Error('Header 值必须是字符串：' + key);
    });
    return {
        name: name,
        base_url: baseUrl,
        path: path,
        method: 'POST',
        headers: headers,
        target_total_concurrency: concurrency,
    };
}

function showTargetFormError(message) {
    var error = document.getElementById('target-form-error');
    error.textContent = message;
    error.classList.remove('hidden');
}

function openTargetEditor(targetId) {
    var target = executionState.targets.find(function (item) { return item.id === targetId; });
    executionState.editingTargetId = target ? target.id : null;
    openExecutionModal(
        target ? '编辑 Target' : '新增 Target',
        targetFormHtml(target),
        async function () {
            var body;
            try {
                body = readTargetForm();
            } catch (error) {
                showTargetFormError(error.message);
                return;
            }
            try {
                if (executionState.editingTargetId) {
                    await API.put('/api/targets/' + encodeURIComponent(executionState.editingTargetId), body);
                } else {
                    await API.post('/api/targets', body);
                }
                closeExecutionModal();
                showToast(target ? 'Target 已更新' : 'Target 已创建', 'success');
                await loadTargets();
            } catch (error) {
                showTargetFormError(executionErrorMessage(error));
            }
        }
    );
}

async function deleteTarget(targetId) {
    var target = executionState.targets.find(function (item) { return item.id === targetId; });
    if (!target || !window.confirm('确定删除 Target“' + target.name + '”吗？')) return;
    try {
        await API.del('/api/targets/' + encodeURIComponent(targetId));
        showToast('Target 已删除', 'success');
        await loadTargets();
    } catch (error) {
        showToast(executionErrorMessage(error), 'error');
    }
}

function workflowStatus(workflow) {
    if (workflow.valid) {
        return '<span class="execution-badge workflow-valid">有效</span>';
    }
    var messages = (workflow.validation_errors || []).map(function (item) {
        return item.location + '：' + item.message;
    }).join('\n');
    return '<span class="execution-badge workflow-invalid" title="' + esc(messages) + '">需修复</span>';
}

function filteredWorkflows() {
    var input = document.getElementById('workflow-search');
    var query = input ? input.value.trim().toLowerCase() : '';
    if (!query) return executionState.workflows;
    return executionState.workflows.filter(function (workflow) {
        return (workflow.name + ' ' + (workflow.description || '')).toLowerCase().includes(query);
    });
}

function renderWorkflowTable() {
    var body = document.getElementById('workflow-list-body');
    var count = document.getElementById('workflow-count');
    if (!body || !count) return;
    var workflows = filteredWorkflows();
    count.textContent = executionState.workflows.length + ' 个 Workflow';
    if (workflows.length === 0) {
        body.innerHTML = '<tr><td colspan="7">' + executionEmpty(
            executionState.workflows.length ? '没有匹配的 Workflow' : '尚未创建 Workflow',
            executionState.workflows.length ? '' : '新建 Workflow',
            'workflow-empty-add'
        ) + '</td></tr>';
        var emptyAdd = document.getElementById('workflow-empty-add');
        if (emptyAdd) emptyAdd.addEventListener('click', function () { openWorkflowEditor(); });
        return;
    }
    body.innerHTML = workflows.map(function (workflow) {
        var errors = workflow.valid ? '' : '<div class="workflow-error-summary">' +
            esc((workflow.validation_errors || []).map(function (item) { return item.message; }).join('；')) + '</div>';
        return '<tr>' +
            '<td><button class="execution-name-button" type="button" data-workflow-edit="' + esc(workflow.id) + '">' + esc(workflow.name) + '</button>' +
                '<div class="execution-id">' + esc(workflow.id) + '</div>' + errors + '</td>' +
            '<td class="workflow-description-cell">' + esc(workflow.description || '—') + '</td>' +
            '<td>' + workflowStatus(workflow) + '</td>' +
            '<td>' + Number(workflow.binding_count || 0) + '</td>' +
            '<td>' + workflowParserCount(workflow) + '</td>' +
            '<td>' + esc(formatDateTime(workflow.updated_at)) + '</td>' +
            '<td><div class="workflow-row-actions">' +
                '<button class="btn-icon" type="button" data-workflow-edit="' + esc(workflow.id) + '" title="编辑 Workflow" aria-label="编辑 Workflow">' + icon('edit') + '</button>' +
                '<button class="btn btn-sm" type="button" data-workflow-copy="' + esc(workflow.id) + '" title="复制 Workflow">复制</button>' +
                '<button class="btn btn-sm" type="button" data-workflow-bind="' + esc(workflow.id) + '" title="绑定测试集">绑定</button>' +
                '<button class="btn-icon" type="button" data-workflow-delete="' + esc(workflow.id) + '" title="删除 Workflow" aria-label="删除 Workflow">' + icon('trash') + '</button>' +
            '</div></td>' +
        '</tr>';
    }).join('');
    body.querySelectorAll('[data-workflow-edit]').forEach(function (button) {
        button.addEventListener('click', function () { openWorkflowEditor(button.getAttribute('data-workflow-edit')); });
    });
    body.querySelectorAll('[data-workflow-copy]').forEach(function (button) {
        button.addEventListener('click', function () { copyWorkflow(button.getAttribute('data-workflow-copy')); });
    });
    body.querySelectorAll('[data-workflow-bind]').forEach(function (button) {
        button.addEventListener('click', function () { openWorkflowBinding(button.getAttribute('data-workflow-bind')); });
    });
    body.querySelectorAll('[data-workflow-delete]').forEach(function (button) {
        button.addEventListener('click', function () { deleteWorkflow(button.getAttribute('data-workflow-delete')); });
    });
}

function workflowParserCount(workflow) {
    return (((workflow || {}).definition || {}).parsers || []).length;
}

async function loadWorkflows() {
    try {
        var data = await API.get('/api/workflows');
        executionState.workflows = data.workflows || [];
        renderWorkflowTable();
    } catch (error) {
        showToast(executionErrorMessage(error), 'error');
        var body = document.getElementById('workflow-list-body');
        if (body) body.innerHTML = '<tr><td colspan="7"><div class="execution-empty"><strong>Workflow 加载失败</strong></div></td></tr>';
    }
}

function viewWorkflows() {
    destroyToolCodeEditor();
    currentView = 'workflows';
    contentArea.innerHTML =
        '<section class="execution-page" aria-labelledby="workflows-title">' +
            '<header class="execution-page-header">' +
                '<div><h1 id="workflows-title">工作流编排</h1><p>固定拓扑的 Parser、Check 与 Aggregator 配置</p></div>' +
                '<span class="execution-count" id="workflow-count">0 个 Workflow</span>' +
            '</header>' +
            '<div class="toolbar execution-toolbar">' +
                '<button class="btn btn-primary" id="btn-workflow-add" type="button">' + icon('add') + '新建 Workflow</button>' +
                '<button class="btn" id="btn-workflow-refresh" type="button">' + icon('refresh') + '刷新</button>' +
                '<span class="toolbar-sep"></span>' +
                '<input type="search" class="input toolbar-search" id="workflow-search" placeholder="搜索名称或说明" aria-label="搜索 Workflow" />' +
            '</div>' +
            '<div class="table-wrap execution-table-wrap"><table class="table execution-table workflow-table" id="workflows-table">' +
                '<thead><tr><th>名称</th><th>说明</th><th>状态</th><th>绑定测试集</th><th>Parser</th><th>更新时间</th><th>操作</th></tr></thead>' +
                '<tbody id="workflow-list-body"><tr><td colspan="7"><div class="execution-loading">正在加载 Workflow</div></td></tr></tbody>' +
            '</table></div>' +
        '</section>';
    document.getElementById('btn-workflow-add').addEventListener('click', function () { openWorkflowEditor(); });
    document.getElementById('btn-workflow-refresh').addEventListener('click', loadWorkflows);
    document.getElementById('workflow-search').addEventListener('input', renderWorkflowTable);
    loadWorkflows();
}

async function copyWorkflow(workflowId) {
    var workflow = executionState.workflows.find(function (item) { return item.id === workflowId; });
    if (!workflow) return;
    try {
        await API.post('/api/workflows', {
            name: workflow.name + ' 副本',
            description: workflow.description || '',
            definition: workflow.definition,
        });
        showToast('Workflow 已复制', 'success');
        await loadWorkflows();
    } catch (error) {
        showToast(executionErrorMessage(error), 'error');
    }
}

async function deleteWorkflow(workflowId) {
    var workflow = executionState.workflows.find(function (item) { return item.id === workflowId; });
    if (!workflow || !window.confirm('确定删除 Workflow“' + workflow.name + '”吗？当前测试集绑定会同时解除。')) return;
    try {
        await API.del('/api/workflows/' + encodeURIComponent(workflowId));
        showToast('Workflow 已删除', 'success');
        await loadWorkflows();
    } catch (error) {
        showToast(executionErrorMessage(error), 'error');
    }
}

async function loadAllTestsets() {
    var page = 1;
    var files = [];
    var total = 0;
    do {
        var data = await API.get('/api/excel/sets?page=' + page + '&page_size=200&sort_by=updated_at&sort_dir=desc');
        files = files.concat(data.files || []);
        total = Number(data.total || 0);
        page += 1;
    } while (files.length < total);
    executionState.sets = files;
    return files;
}

async function refreshBindingState() {
    var select = document.getElementById('workflow-binding-set');
    var status = document.getElementById('workflow-binding-current');
    var unbind = document.getElementById('workflow-binding-unbind');
    if (!select || !status || !unbind) return;
    if (!select.value) {
        status.textContent = '请选择测试集';
        unbind.disabled = true;
        return;
    }
    status.textContent = '正在读取当前绑定';
    try {
        var data = await API.get('/api/workflows/bindings/' + encodeURIComponent(select.value));
        status.textContent = '当前绑定：' + data.workflow.name;
        unbind.disabled = false;
    } catch (error) {
        status.textContent = '当前未绑定 Workflow';
        unbind.disabled = true;
    }
}

async function openWorkflowBinding(workflowId) {
    var workflow = executionState.workflows.find(function (item) { return item.id === workflowId; });
    if (!workflow) return;
    try {
        var files = await loadAllTestsets();
        if (files.length === 0) {
            showToast('请先导入测试集', 'error');
            return;
        }
        var options = files.map(function (file) {
            return '<option value="' + esc(file.filename) + '">' + esc(file.name || file.filename) + ' · ' + esc(file.filename) + '</option>';
        }).join('');
        openExecutionModal(
            '绑定测试集',
            '<div class="form-row"><span class="form-label">Workflow</span><div class="execution-readonly-value">' + esc(workflow.name) + '</div></div>' +
            '<label class="form-row"><span class="form-label">测试集</span><select class="input" id="workflow-binding-set">' + options + '</select></label>' +
            '<div class="workflow-binding-status" id="workflow-binding-current"></div>' +
            '<button class="btn btn-danger btn-sm" id="workflow-binding-unbind" type="button" disabled>解除当前绑定</button>' +
            '<div class="execution-form-error hidden" id="workflow-binding-error" role="alert"></div>',
            async function () {
                var filename = document.getElementById('workflow-binding-set').value;
                try {
                    await API.put('/api/workflows/bindings/' + encodeURIComponent(filename), {workflow_id: workflow.id});
                    closeExecutionModal();
                    showToast('测试集已绑定到 ' + workflow.name, 'success');
                    await loadWorkflows();
                } catch (error) {
                    var message = document.getElementById('workflow-binding-error');
                    message.textContent = executionErrorMessage(error);
                    message.classList.remove('hidden');
                }
            },
            '绑定'
        );
        var setSelect = document.getElementById('workflow-binding-set');
        setSelect.addEventListener('change', refreshBindingState);
        document.getElementById('workflow-binding-unbind').addEventListener('click', async function () {
            try {
                await API.del('/api/workflows/bindings/' + encodeURIComponent(setSelect.value));
                showToast('测试集绑定已解除', 'success');
                await refreshBindingState();
                await loadWorkflows();
            } catch (error) {
                showToast(executionErrorMessage(error), 'error');
            }
        });
        refreshBindingState();
    } catch (error) {
        showToast(executionErrorMessage(error), 'error');
    }
}

function newWorkflowDraft() {
    return {
        name: '未命名 Workflow',
        description: '',
        definition: {
            parsers: [],
            checks: [{check_item: 'check_1', evaluators: [], aggregator: null}],
            case_aggregator: null,
        },
    };
}

function workflowTool(toolId) {
    return executionState.tools.find(function (tool) { return tool.id === toolId; });
}

function workflowToolName(toolId) {
    var tool = workflowTool(toolId);
    return tool ? tool.name : toolId;
}

function workflowNodeTypeLabel(kind) {
    if (kind === 'parser') return 'Parser';
    if (kind === 'evaluator') return 'Evaluator';
    if (kind === 'check_aggregator') return 'Check Aggregator';
    if (kind === 'case_aggregator') return 'Case Aggregator';
    return 'Check Item';
}

function workflowUniqueStepId(prefix) {
    var definition = executionState.workflowDraft.definition;
    var used = {};
    definition.parsers.forEach(function (step) { used[step.step_id] = true; });
    definition.checks.forEach(function (check) {
        check.evaluators.forEach(function (step) { used[step.step_id] = true; });
        if (check.aggregator) used[check.aggregator.step_id] = true;
    });
    if (definition.case_aggregator) used[definition.case_aggregator.step_id] = true;
    var base = String(prefix || 'step').replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '').toLowerCase() || 'step';
    var candidate = base;
    var index = 2;
    while (used[candidate]) candidate = base + '_' + index++;
    return candidate;
}

function workflowUniqueCheckItem() {
    var used = {};
    executionState.workflowDraft.definition.checks.forEach(function (check) { used[check.check_item] = true; });
    var index = 1;
    while (used['check_' + index]) index += 1;
    return 'check_' + index;
}

function createWorkflowStep(kind, tool) {
    var prefix = kind + '_' + (tool.id || 'tool');
    return {
        step_id: workflowUniqueStepId(prefix),
        tool_id: tool.id,
        inputs: {},
        parameters: {},
    };
}

function encodeJsonPointer(segments) {
    if (!segments.length) return '';
    return '/' + segments.map(function (segment) {
        return String(segment).replace(/~/g, '~0').replace(/\//g, '~1');
    }).join('/');
}

function decodeJsonPointer(pointer) {
    if (pointer === '') return [];
    if (typeof pointer !== 'string' || pointer.charAt(0) !== '/') throw new Error('Pointer 必须为空或以 / 开头');
    return pointer.slice(1).split('/').map(function (token) {
        if (/~(?![01])/g.test(token)) throw new Error('Pointer 只允许 ~0 和 ~1 转义');
        return token.replace(/~1/g, '/').replace(/~0/g, '~');
    });
}

function resolveExamplePointer(value, pointer) {
    var current = value;
    decodeJsonPointer(pointer).forEach(function (segment) {
        if (Array.isArray(current)) {
            if (!/^\d+$/.test(segment) || Number(segment) >= current.length) throw new Error('数组索引不存在：' + segment);
            current = current[Number(segment)];
        } else if (current !== null && typeof current === 'object' && Object.prototype.hasOwnProperty.call(current, segment)) {
            current = current[segment];
        } else {
            throw new Error('字段不存在：' + segment);
        }
    });
    return current;
}

function displayMappingPath(source, pointer) {
    return decodeJsonPointer(pointer).reduce(function (text, segment) {
        if (/^\d+$/.test(segment)) return text + '[' + segment + ']';
        if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(segment)) return text + '.' + segment;
        return text + '[' + JSON.stringify(segment) + ']';
    }, source);
}

function workflowAvailableSources(kind, step) {
    var definition = executionState.workflowDraft.definition;
    var sources = [{id: 'response', label: 'FastAPI Response'}];
    var parserLimit = definition.parsers.length;
    if (kind === 'parser') {
        parserLimit = definition.parsers.indexOf(step);
    }
    definition.parsers.slice(0, Math.max(0, parserLimit)).forEach(function (parser) {
        sources.push({id: parser.step_id, label: 'Parser / ' + parser.step_id});
    });
    return sources;
}

function workflowSourceExample(source) {
    if (source === 'response') return {configured: false, value: undefined};
    var parser = executionState.workflowDraft.definition.parsers.find(function (step) { return step.step_id === source; });
    if (!parser) return {configured: false, value: undefined};
    var tool = workflowTool(parser.tool_id);
    return {
        configured: Boolean(tool && tool.output_example_configured),
        value: tool ? tool.output_example : undefined,
    };
}

function workflowMappingKey(step, inputName) {
    return step.step_id + '::' + inputName;
}

function workflowMappingMode(step, inputName) {
    return executionState.workflowMappingModes[workflowMappingKey(step, inputName)] || 'tree';
}

function setWorkflowMappingMode(step, inputName, mode) {
    executionState.workflowMappingModes[workflowMappingKey(step, inputName)] = mode;
}

function jsonValueType(value) {
    if (value === null) return 'null';
    if (Array.isArray(value)) return 'array';
    return typeof value === 'object' ? 'object' : typeof value;
}

function renderJsonFieldTree(value, segments, depth) {
    var pointer = encodeJsonPointer(segments);
    var label = segments.length ? String(segments[segments.length - 1]) : '$ root';
    var type = jsonValueType(value);
    var children = '';
    if (depth < 10 && value !== null && typeof value === 'object') {
        var entries = Array.isArray(value)
            ? value.map(function (item, index) { return [String(index), item]; })
            : Object.keys(value).map(function (key) { return [key, value[key]]; });
        children = entries.map(function (entry) {
            return renderJsonFieldTree(entry[1], segments.concat([entry[0]]), depth + 1);
        }).join('');
    }
    return '<li><button type="button" data-field-pointer="' + esc(pointer) + '" style="--tree-depth:' + depth + '">' +
        '<span>' + esc(label) + '</span><small>' + type + '</small></button>' +
        (children ? '<ul>' + children + '</ul>' : '') + '</li>';
}

function workflowMappingControlHtml(step, inputName, reference) {
    var mode = workflowMappingMode(step, inputName);
    var source = reference.source || 'response';
    var pointer = reference.pointer || '';
    var sources = workflowAvailableSources(selectedWorkflowEntity().kind, step);
    var sourceOptions = sources.map(function (item) {
        return '<option value="' + esc(item.id) + '"' + (item.id === source ? ' selected' : '') + '>' + esc(item.label) + '</option>';
    }).join('');
    var example = workflowSourceExample(source);
    var content = '';
    if (mode === 'tree') {
        content = example.configured
            ? '<ul class="workflow-field-tree">' + renderJsonFieldTree(example.value, [], 0) + '</ul>'
            : '<div class="workflow-mapping-empty">该来源没有输出示例，请使用分段路径或高级 Pointer</div>';
    } else if (mode === 'segments') {
        var segments;
        try { segments = decodeJsonPointer(pointer); } catch (error) { segments = []; }
        content = '<div class="workflow-segment-list">' + (segments.length ? segments.map(function (segment, index) {
            return '<span><code>' + esc(segment) + '</code><button type="button" data-segment-remove="' + index + '" aria-label="删除路径段">×</button></span>';
        }).join('') : '<small>当前选择根值</small>') + '</div>' +
        '<div class="workflow-segment-add"><input class="input workflow-segment-value" placeholder="字段名或数组索引" /><button class="btn btn-sm workflow-segment-add-button" type="button">添加</button></div>';
    } else {
        content = '<label class="form-row workflow-pointer-row"><span class="form-label">JSON Pointer</span><input class="input execution-code-input workflow-pointer-value" value="' + esc(pointer) + '" placeholder="/tool_calls/0/name" /></label>';
    }
    var preview;
    try { preview = displayMappingPath(source, pointer); } catch (error) { preview = source + ' · Pointer 无效'; }
    return '<section class="workflow-mapping" data-input-name="' + esc(inputName) + '">' +
        '<div class="workflow-mapping-header"><input class="input workflow-input-name" value="' + esc(inputName) + '" aria-label="输入参数名" /><button class="btn-icon" type="button" data-input-delete="' + esc(inputName) + '" title="删除输入映射" aria-label="删除输入映射">' + icon('trash') + '</button></div>' +
        '<label class="form-row"><span class="form-label">来源</span><select class="input workflow-source-select">' + sourceOptions + '</select></label>' +
        '<div class="workflow-mapping-modes"><button type="button" data-mapping-mode="tree"' + (mode === 'tree' ? ' class="is-active"' : '') + '>字段树</button><button type="button" data-mapping-mode="segments"' + (mode === 'segments' ? ' class="is-active"' : '') + '>分段路径</button><button type="button" data-mapping-mode="pointer"' + (mode === 'pointer' ? ' class="is-active"' : '') + '>高级 Pointer</button></div>' +
        '<div class="workflow-mapping-body">' + content + '</div>' +
        '<div class="workflow-mapping-preview" title="' + esc(pointer) + '">' + esc(preview) + '</div>' +
    '</section>';
}

function renderWorkflowInputEditor(kind, step) {
    var container = document.getElementById('workflow-input-editor');
    if (!container) return;
    if (kind === 'check_aggregator' || kind === 'case_aggregator') {
        container.innerHTML = '<div class="workflow-mapping-empty">Aggregator 输入由系统注入，不配置字段映射</div>';
        return;
    }
    var names = Object.keys(step.inputs || {});
    container.innerHTML = names.map(function (name) {
        return workflowMappingControlHtml(step, name, step.inputs[name]);
    }).join('') + '<button class="btn btn-sm workflow-add-input" id="workflow-add-input" type="button">+ 输入映射</button>';
    bindWorkflowInputEditor(kind, step);
}

function bindWorkflowInputEditor(kind, step) {
    var container = document.getElementById('workflow-input-editor');
    document.getElementById('workflow-add-input').addEventListener('click', function () {
        var index = 1;
        while (Object.prototype.hasOwnProperty.call(step.inputs, 'input_' + index)) index += 1;
        step.inputs['input_' + index] = {source: 'response', pointer: ''};
        renderWorkflowInspector();
        renderWorkflowValidation();
    });
    container.querySelectorAll('.workflow-mapping').forEach(function (mapping) {
        var inputName = mapping.getAttribute('data-input-name');
        var reference = step.inputs[inputName];
        var nameInput = mapping.querySelector('.workflow-input-name');
        nameInput.addEventListener('input', function (event) {
            var next = event.target.value.trim();
            if (!next || (next !== inputName && Object.prototype.hasOwnProperty.call(step.inputs, next))) {
                event.target.setCustomValidity(!next ? '输入参数名不能为空' : '输入参数名不能重复');
                return;
            }
            event.target.setCustomValidity('');
            if (next === inputName) return;
            var rebuilt = {};
            Object.keys(step.inputs).forEach(function (name) { rebuilt[name === inputName ? next : name] = step.inputs[name]; });
            step.inputs = rebuilt;
            var oldKey = workflowMappingKey(step, inputName);
            executionState.workflowMappingModes[workflowMappingKey(step, next)] = executionState.workflowMappingModes[oldKey] || 'tree';
            delete executionState.workflowMappingModes[oldKey];
            inputName = next;
            mapping.setAttribute('data-input-name', next);
            mapping.querySelector('[data-input-delete]').setAttribute('data-input-delete', next);
            renderWorkflowValidation();
        });
        nameInput.addEventListener('blur', function (event) {
            if (event.target.checkValidity()) return;
            event.target.reportValidity();
        });
        mapping.querySelector('[data-input-delete]').addEventListener('click', function () {
            delete step.inputs[inputName];
            renderWorkflowInspector();
            renderWorkflowValidation();
        });
        mapping.querySelector('.workflow-source-select').addEventListener('change', function (event) {
            reference.source = event.target.value;
            reference.pointer = '';
            renderWorkflowInspector();
            renderWorkflowValidation();
        });
        mapping.querySelectorAll('[data-mapping-mode]').forEach(function (button) {
            button.addEventListener('click', function () {
                setWorkflowMappingMode(step, inputName, button.getAttribute('data-mapping-mode'));
                renderWorkflowInspector();
            });
        });
        mapping.querySelectorAll('[data-field-pointer]').forEach(function (button) {
            button.addEventListener('click', function () {
                reference.pointer = button.getAttribute('data-field-pointer');
                renderWorkflowInspector();
                renderWorkflowValidation();
            });
        });
        mapping.querySelectorAll('[data-segment-remove]').forEach(function (button) {
            button.addEventListener('click', function () {
                var segments = decodeJsonPointer(reference.pointer);
                segments.splice(Number(button.getAttribute('data-segment-remove')), 1);
                reference.pointer = encodeJsonPointer(segments);
                renderWorkflowInspector();
                renderWorkflowValidation();
            });
        });
        var addSegment = mapping.querySelector('.workflow-segment-add-button');
        if (addSegment) addSegment.addEventListener('click', function () {
            var input = mapping.querySelector('.workflow-segment-value');
            if (!input.value) return;
            reference.pointer = encodeJsonPointer(decodeJsonPointer(reference.pointer).concat([input.value]));
            renderWorkflowInspector();
            renderWorkflowValidation();
        });
        var pointerInput = mapping.querySelector('.workflow-pointer-value');
        if (pointerInput) pointerInput.addEventListener('change', function () {
            try {
                decodeJsonPointer(pointerInput.value);
                reference.pointer = pointerInput.value;
                pointerInput.setCustomValidity('');
                renderWorkflowInspector();
                renderWorkflowValidation();
            } catch (error) {
                pointerInput.setCustomValidity(error.message);
                pointerInput.reportValidity();
            }
        });
    });
}

function workflowSelectedCheckIndex() {
    var selection = executionState.workflowSelection;
    if (selection && Number.isInteger(selection.checkIndex)) return selection.checkIndex;
    return 0;
}

function selectWorkflowNode(kind, checkIndex, itemIndex) {
    executionState.workflowSelection = {
        kind: kind,
        checkIndex: Number.isInteger(checkIndex) ? checkIndex : null,
        itemIndex: Number.isInteger(itemIndex) ? itemIndex : null,
    };
    renderWorkflowCanvas();
    renderWorkflowInspector();
}

function workflowSelectionMatches(kind, checkIndex, itemIndex) {
    var selection = executionState.workflowSelection;
    return Boolean(selection && selection.kind === kind &&
        selection.checkIndex === (Number.isInteger(checkIndex) ? checkIndex : null) &&
        selection.itemIndex === (Number.isInteger(itemIndex) ? itemIndex : null));
}

function workflowNodeHtml(kind, step, checkIndex, itemIndex) {
    var tool = workflowTool(step.tool_id);
    var selected = workflowSelectionMatches(kind, checkIndex, itemIndex) ? ' is-selected' : '';
    var invalid = tool ? '' : ' is-invalid';
    return '<button class="workflow-node' + selected + invalid + '" type="button" data-node-kind="' + kind + '"' +
        (Number.isInteger(checkIndex) ? ' data-check-index="' + checkIndex + '"' : '') +
        (Number.isInteger(itemIndex) ? ' data-item-index="' + itemIndex + '"' : '') + '>' +
        '<span class="workflow-node-type">' + workflowNodeTypeLabel(kind) + '</span>' +
        '<strong>' + esc(tool ? tool.name : '工具已删除') + '</strong>' +
        '<code>' + esc(step.step_id) + '</code>' +
        '<span class="workflow-node-tool-type">' + esc(tool ? tool.type : step.tool_id) + '</span>' +
    '</button>';
}

function workflowSlotHtml(kind, checkIndex, label) {
    return '<button class="workflow-slot" type="button" data-slot-kind="' + kind + '"' +
        (Number.isInteger(checkIndex) ? ' data-check-index="' + checkIndex + '"' : '') + '>' +
        '<span>+</span>' + esc(label) +
    '</button>';
}

function renderWorkflowCanvas() {
    var canvas = document.getElementById('workflow-canvas');
    if (!canvas || !executionState.workflowDraft) return;
    var definition = executionState.workflowDraft.definition;
    var parserHtml = definition.parsers.length ? definition.parsers.map(function (step, index) {
        return '<div class="workflow-sequence-item">' +
            workflowNodeHtml('parser', step, null, index) +
            '<div class="workflow-sequence-actions">' +
                '<button type="button" data-parser-up="' + index + '" aria-label="上移 Parser" title="上移"' + (index === 0 ? ' disabled' : '') + '>↑</button>' +
                '<button type="button" data-parser-down="' + index + '" aria-label="下移 Parser" title="下移"' + (index === definition.parsers.length - 1 ? ' disabled' : '') + '>↓</button>' +
                '<button type="button" data-parser-delete="' + index + '" aria-label="删除 Parser" title="删除">×</button>' +
            '</div></div>';
    }).join('') : '<div class="workflow-lane-empty">从左侧添加 Parser</div>';

    var checksHtml = definition.checks.map(function (check, checkIndex) {
        var selected = workflowSelectionMatches('check', checkIndex, null) ? ' is-selected' : '';
        var evaluators = check.evaluators.length ? check.evaluators.map(function (step, evaluatorIndex) {
            return workflowNodeHtml('evaluator', step, checkIndex, evaluatorIndex);
        }).join('') : workflowSlotHtml('evaluator', checkIndex, '添加 Evaluator');
        var aggregator = '';
        if (check.evaluators.length > 1) {
            aggregator = check.aggregator
                ? workflowNodeHtml('check_aggregator', check.aggregator, checkIndex, null)
                : workflowSlotHtml('check_aggregator', checkIndex, '选择 Check Aggregator');
        }
        return '<section class="workflow-check-group' + selected + '">' +
            '<button class="workflow-check-header" type="button" data-check-select="' + checkIndex + '">' +
                '<span>Check Item</span><strong>' + esc(check.check_item) + '</strong><small>' + check.evaluators.length + ' Evaluator</small>' +
            '</button>' +
            '<div class="workflow-evaluator-list">' + evaluators + '</div>' +
            (aggregator ? '<div class="workflow-aggregator-row">' + aggregator + '</div>' : '') +
        '</section>';
    }).join('');
    var caseAggregator = '';
    if (definition.checks.length > 1) {
        caseAggregator = definition.case_aggregator
            ? workflowNodeHtml('case_aggregator', definition.case_aggregator, null, null)
            : workflowSlotHtml('case_aggregator', null, '选择 Case Aggregator');
    }
    canvas.innerHTML =
        '<div class="workflow-flow-grid">' +
            '<section class="workflow-lane workflow-response-lane"><div class="workflow-lane-title">输入</div><div class="workflow-system-node"><span>Response</span><strong>FastAPI Body</strong></div></section>' +
            '<section class="workflow-lane workflow-parser-lane"><div class="workflow-lane-title">顺序 Parser</div><div class="workflow-parser-list">' + parserHtml + '</div></section>' +
            '<section class="workflow-lane workflow-check-lane"><div class="workflow-lane-title">并行 Checks <button type="button" id="btn-check-add">+ Check</button></div><div class="workflow-check-grid">' + checksHtml + '</div></section>' +
            '<section class="workflow-lane workflow-result-lane"><div class="workflow-lane-title">汇总</div>' +
                (caseAggregator ? '<div class="workflow-case-aggregator">' + caseAggregator + '</div>' : '') +
                '<div class="workflow-system-node workflow-result-node"><span>Case Result</span><strong>标准结果</strong></div>' +
            '</section>' +
        '</div>';
    bindWorkflowCanvasEvents();
}

function bindWorkflowCanvasEvents() {
    var canvas = document.getElementById('workflow-canvas');
    canvas.querySelectorAll('[data-node-kind]').forEach(function (node) {
        node.addEventListener('click', function () {
            var check = node.hasAttribute('data-check-index') ? Number(node.getAttribute('data-check-index')) : null;
            var item = node.hasAttribute('data-item-index') ? Number(node.getAttribute('data-item-index')) : null;
            selectWorkflowNode(node.getAttribute('data-node-kind'), check, item);
        });
    });
    canvas.querySelectorAll('[data-check-select]').forEach(function (button) {
        button.addEventListener('click', function () { selectWorkflowNode('check', Number(button.getAttribute('data-check-select')), null); });
    });
    canvas.querySelectorAll('[data-slot-kind]').forEach(function (slot) {
        slot.addEventListener('click', function () {
            var check = slot.hasAttribute('data-check-index') ? Number(slot.getAttribute('data-check-index')) : null;
            executionState.workflowToolMode = slot.getAttribute('data-slot-kind') === 'evaluator' ? 'evaluator' : 'aggregator';
            executionState.workflowSelection = {kind: slot.getAttribute('data-slot-kind'), checkIndex: check, itemIndex: null};
            renderWorkflowToolLibrary();
            renderWorkflowCanvas();
            renderWorkflowInspector();
        });
    });
    canvas.querySelector('#btn-check-add').addEventListener('click', addWorkflowCheck);
    canvas.querySelectorAll('[data-parser-up]').forEach(function (button) {
        button.addEventListener('click', function () { moveWorkflowParser(Number(button.getAttribute('data-parser-up')), -1); });
    });
    canvas.querySelectorAll('[data-parser-down]').forEach(function (button) {
        button.addEventListener('click', function () { moveWorkflowParser(Number(button.getAttribute('data-parser-down')), 1); });
    });
    canvas.querySelectorAll('[data-parser-delete]').forEach(function (button) {
        button.addEventListener('click', function () { deleteWorkflowParser(Number(button.getAttribute('data-parser-delete'))); });
    });
}

function workflowToolAllowed(tool, mode) {
    if (mode === 'parser') return Boolean(tool.output_example_configured);
    if (mode === 'aggregator') return tool.type === 'script';
    return tool.type === 'script' || tool.type === 'agent';
}

function renderWorkflowToolLibrary() {
    var list = document.getElementById('workflow-tool-list');
    if (!list) return;
    document.querySelectorAll('[data-workflow-tool-mode]').forEach(function (button) {
        button.classList.toggle('is-active', button.getAttribute('data-workflow-tool-mode') === executionState.workflowToolMode);
    });
    var query = executionState.workflowToolQuery.toLowerCase();
    var tools = executionState.tools.filter(function (tool) {
        return (!query || (tool.name + ' ' + tool.id).toLowerCase().includes(query));
    });
    if (!tools.length) {
        list.innerHTML = '<div class="workflow-tool-empty">没有匹配工具</div>';
        return;
    }
    list.innerHTML = tools.map(function (tool) {
        var allowed = workflowToolAllowed(tool, executionState.workflowToolMode);
        var reason = executionState.workflowToolMode === 'parser' && !tool.output_example_configured
            ? '缺少输出示例，不能作为 Parser' :
            (executionState.workflowToolMode === 'aggregator' && tool.type !== 'script' ? 'Aggregator 只允许 Script' : '');
        return '<button class="workflow-tool-item" type="button" data-tool-add="' + esc(tool.id) + '"' + (allowed ? '' : ' disabled') + ' title="' + esc(reason || '添加到编排') + '">' +
            '<span class="execution-badge ' + (tool.type === 'agent' ? 'tool-agent-badge' : 'tool-script-badge') + '">' + esc(tool.type) + '</span>' +
            '<strong>' + esc(tool.name) + '</strong><code>' + esc(tool.id) + '</code>' +
        '</button>';
    }).join('');
    list.querySelectorAll('[data-tool-add]:not(:disabled)').forEach(function (button) {
        button.addEventListener('click', function () { addWorkflowTool(button.getAttribute('data-tool-add')); });
    });
}

function addWorkflowTool(toolId) {
    var tool = workflowTool(toolId);
    if (!tool) return;
    var definition = executionState.workflowDraft.definition;
    var mode = executionState.workflowToolMode;
    var checkIndex = workflowSelectedCheckIndex();
    if (mode === 'parser') {
        definition.parsers.push(createWorkflowStep('parser', tool));
        selectWorkflowNode('parser', null, definition.parsers.length - 1);
        return;
    }
    if (mode === 'evaluator') {
        if (!definition.checks[checkIndex]) checkIndex = 0;
        definition.checks[checkIndex].evaluators.push(createWorkflowStep('evaluator', tool));
        selectWorkflowNode('evaluator', checkIndex, definition.checks[checkIndex].evaluators.length - 1);
        return;
    }
    if (tool.type !== 'script') return;
    var selection = executionState.workflowSelection;
    if (selection && selection.kind === 'check_aggregator' && definition.checks[selection.checkIndex] && definition.checks[selection.checkIndex].evaluators.length > 1) {
        definition.checks[selection.checkIndex].aggregator = createWorkflowStep('check_aggregator', tool);
        selectWorkflowNode('check_aggregator', selection.checkIndex, null);
    } else if (definition.checks.length > 1) {
        definition.case_aggregator = createWorkflowStep('case_aggregator', tool);
        selectWorkflowNode('case_aggregator', null, null);
    } else {
        showToast('当前拓扑不需要 Aggregator', 'error');
    }
}

function addWorkflowCheck() {
    var checks = executionState.workflowDraft.definition.checks;
    checks.push({check_item: workflowUniqueCheckItem(), evaluators: [], aggregator: null});
    selectWorkflowNode('check', checks.length - 1, null);
}

function moveWorkflowParser(index, offset) {
    var parsers = executionState.workflowDraft.definition.parsers;
    var target = index + offset;
    if (target < 0 || target >= parsers.length) return;
    var item = parsers.splice(index, 1)[0];
    parsers.splice(target, 0, item);
    selectWorkflowNode('parser', null, target);
}

function deleteWorkflowParser(index) {
    var parsers = executionState.workflowDraft.definition.parsers;
    parsers.splice(index, 1);
    executionState.workflowSelection = null;
    renderWorkflowEditorBody();
}

function selectedWorkflowEntity() {
    var selection = executionState.workflowSelection;
    var definition = executionState.workflowDraft.definition;
    if (!selection) return {kind: 'workflow', value: executionState.workflowDraft};
    if (selection.kind === 'parser') return {kind: 'parser', value: definition.parsers[selection.itemIndex]};
    if (selection.kind === 'check') return {kind: 'check', value: definition.checks[selection.checkIndex]};
    if (selection.kind === 'evaluator') return {kind: 'evaluator', value: definition.checks[selection.checkIndex].evaluators[selection.itemIndex]};
    if (selection.kind === 'check_aggregator') return {kind: 'check_aggregator', value: definition.checks[selection.checkIndex].aggregator};
    if (selection.kind === 'case_aggregator') return {kind: 'case_aggregator', value: definition.case_aggregator};
    return {kind: 'workflow', value: executionState.workflowDraft};
}

function workflowToolOptions(kind, selectedId) {
    return executionState.tools.filter(function (tool) {
        if (kind === 'parser') return tool.output_example_configured;
        if (kind.includes('aggregator')) return tool.type === 'script';
        return true;
    }).map(function (tool) {
        return '<option value="' + esc(tool.id) + '"' + (tool.id === selectedId ? ' selected' : '') + '>' + esc(tool.name) + ' · ' + esc(tool.type) + '</option>';
    }).join('');
}

function renderWorkflowInspector() {
    var inspector = document.getElementById('workflow-inspector');
    if (!inspector || !executionState.workflowDraft) return;
    var entity = selectedWorkflowEntity();
    if (entity.kind === 'workflow' || !entity.value) {
        inspector.innerHTML = '<div class="workflow-panel-title">Workflow 设置</div>' +
            '<label class="form-row"><span class="form-label">名称</span><input class="input" id="workflow-name" maxlength="120" value="' + esc(executionState.workflowDraft.name) + '" /></label>' +
            '<label class="form-row"><span class="form-label">说明</span><textarea class="input" id="workflow-description" rows="4">' + esc(executionState.workflowDraft.description || '') + '</textarea></label>';
        document.getElementById('workflow-name').addEventListener('input', function (event) { executionState.workflowDraft.name = event.target.value; });
        document.getElementById('workflow-description').addEventListener('input', function (event) { executionState.workflowDraft.description = event.target.value; });
        return;
    }
    if (entity.kind === 'check') {
        inspector.innerHTML = '<div class="workflow-panel-title">Check Item</div>' +
            '<label class="form-row"><span class="form-label">check_item</span><input class="input" id="workflow-check-item" value="' + esc(entity.value.check_item) + '" /></label>' +
            '<div class="workflow-inspector-meta">' + entity.value.evaluators.length + ' 个 Evaluator</div>' +
            '<button class="btn btn-danger btn-sm" id="workflow-delete-check" type="button"' + (executionState.workflowDraft.definition.checks.length === 1 ? ' disabled' : '') + '>删除 Check</button>';
        document.getElementById('workflow-check-item').addEventListener('change', function (event) {
            entity.value.check_item = event.target.value.trim();
            renderWorkflowCanvas();
            renderWorkflowValidation();
        });
        document.getElementById('workflow-delete-check').addEventListener('click', deleteSelectedWorkflowCheck);
        return;
    }
    var step = entity.value;
    var tool = workflowTool(step.tool_id);
    var parameterField = tool && tool.type === 'agent' && entity.kind === 'evaluator'
        ? '<label class="form-row"><span class="form-label">节点参数（JSON 字符串对象）</span><textarea class="input execution-code-input" id="workflow-step-parameters" rows="5">' + esc(JSON.stringify(step.parameters || {}, null, 2)) + '</textarea></label>'
        : '<div class="workflow-inspector-meta">' + (tool && tool.type === 'script' ? 'Script 节点不配置参数' : '参数由工具快照提供') + '</div>';
    inspector.innerHTML = '<div class="workflow-panel-title">' + workflowNodeTypeLabel(entity.kind) + '</div>' +
        '<label class="form-row"><span class="form-label">step_id</span><input class="input" id="workflow-step-id" value="' + esc(step.step_id) + '" /></label>' +
        '<label class="form-row"><span class="form-label">工具</span><select class="input" id="workflow-step-tool">' + workflowToolOptions(entity.kind, step.tool_id) + '</select></label>' +
        parameterField +
        '<div class="workflow-input-summary"><span>输入映射</span><strong>' + Object.keys(step.inputs || {}).length + '</strong></div>' +
        '<div id="workflow-input-editor"></div>' +
        '<button class="btn btn-danger btn-sm" id="workflow-delete-step" type="button">删除节点</button>';
    renderWorkflowInputEditor(entity.kind, step);
    document.getElementById('workflow-step-id').addEventListener('change', function (event) {
        step.step_id = event.target.value.trim();
        renderWorkflowCanvas();
        renderWorkflowValidation();
    });
    document.getElementById('workflow-step-tool').addEventListener('change', function (event) {
        step.tool_id = event.target.value;
        step.parameters = {};
        renderWorkflowEditorBody();
    });
    var parameters = document.getElementById('workflow-step-parameters');
    if (parameters) parameters.addEventListener('change', function () {
        try {
            var parsed = JSON.parse(parameters.value || '{}');
            if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object' || Object.values(parsed).some(function (value) { return typeof value !== 'string'; })) {
                throw new Error('节点参数必须是字符串值对象');
            }
            step.parameters = parsed;
            parameters.setCustomValidity('');
        } catch (error) {
            parameters.setCustomValidity(error.message || '节点参数不是合法 JSON');
            parameters.reportValidity();
        }
    });
    document.getElementById('workflow-delete-step').addEventListener('click', deleteSelectedWorkflowStep);
}

function deleteSelectedWorkflowCheck() {
    var selection = executionState.workflowSelection;
    var definition = executionState.workflowDraft.definition;
    if (!selection || definition.checks.length <= 1) return;
    definition.checks.splice(selection.checkIndex, 1);
    if (definition.checks.length <= 1) definition.case_aggregator = null;
    executionState.workflowSelection = null;
    renderWorkflowEditorBody();
}

function deleteSelectedWorkflowStep() {
    var selection = executionState.workflowSelection;
    var definition = executionState.workflowDraft.definition;
    if (!selection) return;
    if (selection.kind === 'parser') definition.parsers.splice(selection.itemIndex, 1);
    if (selection.kind === 'evaluator') {
        var check = definition.checks[selection.checkIndex];
        check.evaluators.splice(selection.itemIndex, 1);
        if (check.evaluators.length <= 1) check.aggregator = null;
    }
    if (selection.kind === 'check_aggregator') definition.checks[selection.checkIndex].aggregator = null;
    if (selection.kind === 'case_aggregator') definition.case_aggregator = null;
    executionState.workflowSelection = null;
    renderWorkflowEditorBody();
}

function clientWorkflowValidation() {
    var draft = executionState.workflowDraft;
    var definition = draft.definition;
    var errors = [];
    if (!draft.name.trim()) errors.push({location: 'name', message: 'Workflow 名称不能为空'});
    if (!definition.checks.length) errors.push({location: 'definition.checks', message: '至少需要一个 Check'});
    var stepIds = {};
    var checkItems = {};
    function validateStep(step, location, requireScript, allowedSources) {
        if (!step || !step.step_id) errors.push({location: location + '.step_id', message: 'step_id 不能为空'});
        else if (stepIds[step.step_id]) errors.push({location: location + '.step_id', message: 'step_id 必须全局唯一'});
        else stepIds[step.step_id] = true;
        var tool = step && workflowTool(step.tool_id);
        if (!tool) errors.push({location: location + '.tool_id', message: '工具不存在'});
        else if (requireScript && tool.type !== 'script') errors.push({location: location + '.tool_id', message: 'Aggregator 只允许 Script'});
        Object.keys((step && step.inputs) || {}).forEach(function (inputName) {
            var reference = step.inputs[inputName];
            var inputLocation = location + '.inputs.' + inputName;
            if (!inputName.trim()) errors.push({location: inputLocation, message: '输入参数名不能为空'});
            if (allowedSources && !allowedSources.includes(reference.source)) errors.push({location: inputLocation + '.source', message: '来源节点不可用或执行顺序不合法'});
            try {
                decodeJsonPointer(reference.pointer);
                var example = workflowSourceExample(reference.source);
                if (example.configured) resolveExamplePointer(example.value, reference.pointer);
            } catch (error) {
                errors.push({location: inputLocation + '.pointer', message: error.message});
            }
        });
    }
    definition.parsers.forEach(function (step, index) {
        var allowedSources = ['response'].concat(definition.parsers.slice(0, index).map(function (parser) { return parser.step_id; }));
        validateStep(step, 'parsers[' + index + ']', false, allowedSources);
        var tool = workflowTool(step.tool_id);
        if (tool && !tool.output_example_configured) errors.push({location: 'parsers[' + index + '].tool_id', message: 'Parser 工具缺少输出示例'});
    });
    definition.checks.forEach(function (check, checkIndex) {
        var location = 'checks[' + checkIndex + ']';
        if (!check.check_item) errors.push({location: location + '.check_item', message: 'check_item 不能为空'});
        else if (checkItems[check.check_item]) errors.push({location: location + '.check_item', message: 'check_item 必须唯一'});
        else checkItems[check.check_item] = true;
        if (!check.evaluators.length) errors.push({location: location + '.evaluators', message: '至少需要一个 Evaluator'});
        var evaluatorSources = ['response'].concat(definition.parsers.map(function (parser) { return parser.step_id; }));
        check.evaluators.forEach(function (step, index) { validateStep(step, location + '.evaluators[' + index + ']', false, evaluatorSources); });
        if (check.evaluators.length > 1 && !check.aggregator) errors.push({location: location + '.aggregator', message: '多个 Evaluator 需要 Check Aggregator'});
        if (check.evaluators.length === 1 && check.aggregator) errors.push({location: location + '.aggregator', message: '单 Evaluator 不允许 Aggregator'});
        if (check.aggregator) validateStep(check.aggregator, location + '.aggregator', true, []);
    });
    if (definition.checks.length > 1 && !definition.case_aggregator) errors.push({location: 'case_aggregator', message: '多个 Check 需要 Case Aggregator'});
    if (definition.checks.length === 1 && definition.case_aggregator) errors.push({location: 'case_aggregator', message: '单 Check 不允许 Case Aggregator'});
    if (definition.case_aggregator) validateStep(definition.case_aggregator, 'case_aggregator', true, []);
    return errors;
}

function renderWorkflowValidation(serverErrors) {
    var panel = document.getElementById('workflow-validation');
    if (!panel) return;
    var errors = serverErrors || clientWorkflowValidation();
    if (!errors.length) {
        panel.innerHTML = '<div class="workflow-validation-ok"><strong>结构校验通过</strong><span>可保存当前 Workflow</span></div>';
        return;
    }
    panel.innerHTML = '<div class="workflow-validation-title">' + errors.length + ' 个问题</div><ul>' + errors.map(function (error) {
        return '<li><code>' + esc(error.location || 'workflow') + '</code><span>' + esc(error.message || String(error)) + '</span></li>';
    }).join('') + '</ul>';
}

function renderWorkflowEditorBody() {
    renderWorkflowToolLibrary();
    renderWorkflowCanvas();
    renderWorkflowInspector();
    renderWorkflowValidation();
}

function bindWorkflowEditorShell() {
    document.getElementById('btn-workflow-back').addEventListener('click', viewWorkflows);
    document.getElementById('btn-workflow-save').addEventListener('click', saveWorkflowDraft);
    document.querySelectorAll('[data-workflow-tool-mode]').forEach(function (button) {
        button.addEventListener('click', function () {
            executionState.workflowToolMode = button.getAttribute('data-workflow-tool-mode');
            renderWorkflowToolLibrary();
        });
    });
    document.getElementById('workflow-tool-search').addEventListener('input', function (event) {
        executionState.workflowToolQuery = event.target.value.trim();
        renderWorkflowToolLibrary();
    });
}

function renderWorkflowEditor() {
    var draft = executionState.workflowDraft;
    contentArea.innerHTML =
        '<section class="workflow-editor" aria-labelledby="workflow-editor-title">' +
            '<header class="workflow-editor-header">' +
                '<button class="btn btn-sm" id="btn-workflow-back" type="button">' + icon('back') + '返回</button>' +
                '<div><h1 id="workflow-editor-title">' + esc(draft.name) + '</h1><p>' + (executionState.workflowId ? esc(executionState.workflowId) : '新建 Workflow') + '</p></div>' +
                '<button class="btn btn-primary" id="btn-workflow-save" type="button">保存 Workflow</button>' +
            '</header>' +
            '<div class="workflow-editor-grid">' +
                '<aside class="workflow-tool-panel"><div class="workflow-panel-title">工具库</div>' +
                    '<div class="workflow-mode-switch"><button type="button" data-workflow-tool-mode="parser">Parser</button><button type="button" data-workflow-tool-mode="evaluator">Evaluator</button><button type="button" data-workflow-tool-mode="aggregator">Aggregator</button></div>' +
                    '<input type="search" class="input" id="workflow-tool-search" placeholder="搜索工具" aria-label="搜索工具" />' +
                    '<div class="workflow-tool-list" id="workflow-tool-list"></div>' +
                '</aside>' +
                '<main class="workflow-canvas" id="workflow-canvas"></main>' +
                '<aside class="workflow-inspector" id="workflow-inspector"></aside>' +
                '<footer class="workflow-validation" id="workflow-validation"></footer>' +
            '</div>' +
        '</section>';
    bindWorkflowEditorShell();
    renderWorkflowEditorBody();
}

async function openWorkflowEditor(workflowId) {
    destroyToolCodeEditor();
    currentView = 'workflows';
    executionLoading('正在加载 Workflow 编辑器');
    try {
        var requests = [API.get('/api/tools')];
        if (workflowId) requests.push(API.get('/api/workflows/' + encodeURIComponent(workflowId)));
        var results = await Promise.all(requests);
        executionState.tools = results[0].tools || [];
        executionState.workflowId = workflowId || null;
        executionState.workflowDraft = workflowId ? {
            name: results[1].workflow.name,
            description: results[1].workflow.description || '',
            definition: JSON.parse(JSON.stringify(results[1].workflow.definition)),
        } : newWorkflowDraft();
        executionState.workflowSelection = null;
        executionState.workflowToolMode = 'parser';
        executionState.workflowToolQuery = '';
        executionState.workflowMappingModes = {};
        renderWorkflowEditor();
    } catch (error) {
        showToast(executionErrorMessage(error), 'error');
        viewWorkflows();
    }
}

async function saveWorkflowDraft() {
    var errors = clientWorkflowValidation();
    if (errors.length) {
        renderWorkflowValidation(errors);
        showToast('请先修复 Workflow 配置问题', 'error');
        return;
    }
    var button = document.getElementById('btn-workflow-save');
    button.disabled = true;
    try {
        var body = {
            name: executionState.workflowDraft.name.trim(),
            description: executionState.workflowDraft.description.trim(),
            definition: executionState.workflowDraft.definition,
        };
        var data = executionState.workflowId
            ? await executionRequest('PUT', '/api/workflows/' + encodeURIComponent(executionState.workflowId), body)
            : await executionRequest('POST', '/api/workflows', body);
        executionState.workflowId = data.workflow.id;
        executionState.workflowDraft.name = data.workflow.name;
        renderWorkflowValidation();
        showToast('Workflow 已保存', 'success');
        renderWorkflowEditor();
    } catch (error) {
        renderWorkflowValidation(error.validationErrors || [{location: 'workflow', message: executionErrorMessage(error)}]);
        showToast(executionErrorMessage(error), 'error');
    } finally {
        var currentButton = document.getElementById('btn-workflow-save');
        if (currentButton) currentButton.disabled = false;
    }
}

function runStatusBadge(status) {
    var normalized = String(status || 'UNKNOWN').toLowerCase();
    return '<span class="execution-badge run-status run-status-' + esc(normalized) + '">' + esc(status || 'UNKNOWN') + '</span>';
}

function runBusinessBadge(status) {
    if (!status) return '<span class="run-business-empty">—</span>';
    return '<span class="execution-badge run-business run-business-' + esc(String(status).toLowerCase()) + '">' + esc(status) + '</span>';
}

function filteredRuns() {
    var status = document.getElementById('run-status-filter');
    var search = document.getElementById('run-search');
    var selectedStatus = status ? status.value : '';
    var query = search ? search.value.trim().toLowerCase() : '';
    return executionState.runs.filter(function (run) {
        var matchesStatus = !selectedStatus || run.status === selectedStatus;
        var haystack = (run.id + ' ' + run.testset_filename + ' ' + (run.target_id || '') + ' ' + (run.workflow_id || '')).toLowerCase();
        return matchesStatus && (!query || haystack.includes(query));
    });
}

function renderRunHistoryTable() {
    var body = document.getElementById('run-history-body');
    var count = document.getElementById('run-count');
    if (!body || !count) return;
    var runs = filteredRuns();
    count.textContent = executionState.runs.length + ' 个 Run';
    if (!runs.length) {
        body.innerHTML = '<tr><td colspan="9">' + executionEmpty(
            executionState.runs.length ? '没有匹配的 Run' : '尚未创建 Run',
            executionState.runs.length ? '' : '新建 Run',
            'run-empty-create'
        ) + '</td></tr>';
        var create = document.getElementById('run-empty-create');
        if (create) create.addEventListener('click', function () { switchRunsTab('create'); });
        return;
    }
    body.innerHTML = runs.map(function (run) {
        return '<tr>' +
            '<td><button class="execution-name-button" type="button" data-run-detail="' + esc(run.id) + '">' + esc(run.testset_filename) + '</button><div class="execution-id">' + esc(run.id) + '</div></td>' +
            '<td>' + esc(run.sheet_name) + '</td>' +
            '<td>' + runStatusBadge(run.status) + '</td>' +
            '<td>' + runBusinessBadge(run.business_status) + '</td>' +
            '<td><code class="run-reference">' + esc(run.target_id || '—') + '</code></td>' +
            '<td><code class="run-reference">' + esc(run.workflow_id || '—') + '</code></td>' +
            '<td>' + esc(formatDateTime(run.created_at)) + '</td>' +
            '<td>' + (run.active ? '<span class="run-live-indicator">运行中</span>' : '—') + '</td>' +
            '<td><button class="btn btn-sm" type="button" data-run-detail="' + esc(run.id) + '">详情</button></td>' +
        '</tr>';
    }).join('');
    body.querySelectorAll('[data-run-detail]').forEach(function (button) {
        button.addEventListener('click', function () { openRunDetail(button.getAttribute('data-run-detail')); });
    });
}

async function loadRuns() {
    try {
        var data = await API.get('/api/runs?limit=500');
        executionState.runs = data.runs || [];
        renderRunHistoryTable();
    } catch (error) {
        showToast(executionErrorMessage(error), 'error');
    }
}

function renderRunHistory() {
    var panel = document.getElementById('runs-panel');
    panel.innerHTML =
        '<div class="toolbar execution-toolbar runs-toolbar">' +
            '<button class="btn" id="btn-runs-refresh" type="button">' + icon('refresh') + '刷新</button>' +
            '<span class="toolbar-sep"></span>' +
            '<select class="input toolbar-control" id="run-status-filter"><option value="">全部状态</option><option>QUEUED</option><option>RUNNING</option><option>SUCCEEDED</option><option>ERROR</option><option>CANCELLED</option></select>' +
            '<input type="search" class="input toolbar-search" id="run-search" placeholder="搜索测试集、Run ID、Target" aria-label="搜索 Run" />' +
        '</div>' +
        '<div class="table-wrap execution-table-wrap"><table class="table execution-table run-history-table">' +
            '<thead><tr><th>测试集 / Run</th><th>Sheet</th><th>执行状态</th><th>业务结论</th><th>Target</th><th>Workflow</th><th>创建时间</th><th>活动</th><th>操作</th></tr></thead>' +
            '<tbody id="run-history-body"><tr><td colspan="9"><div class="execution-loading">正在加载运行记录</div></td></tr></tbody>' +
        '</table></div>';
    document.getElementById('btn-runs-refresh').addEventListener('click', loadRuns);
    document.getElementById('run-status-filter').addEventListener('change', renderRunHistoryTable);
    document.getElementById('run-search').addEventListener('input', renderRunHistoryTable);
    loadRuns();
}

function runSetOptions() {
    return executionState.sets.map(function (file) {
        return '<option value="' + esc(file.filename) + '">' + esc(file.name || file.filename) + ' · ' + esc(file.filename) + '</option>';
    }).join('');
}

function runTargetOptions() {
    return executionState.targets.map(function (target) {
        return '<option value="' + esc(target.id) + '">' + esc(target.name) + ' · ' + esc(targetAddress(target)) + '</option>';
    }).join('');
}

function defaultRequestTemplate() {
    return {question: '${question}'};
}

async function loadRunSetContext() {
    var filename = document.getElementById('run-testset').value;
    var sheetInfo = document.getElementById('run-sheet-info');
    var bindingInfo = document.getElementById('run-binding-info');
    var template = document.getElementById('run-request-template');
    var create = document.getElementById('btn-run-create');
    if (!filename) return;
    sheetInfo.textContent = '正在读取首个 Sheet';
    bindingInfo.textContent = '正在读取 Workflow 绑定';
    create.disabled = true;
    var context = {filename: filename, binding: null, sheets: [], templateConfigured: false};
    var results = await Promise.allSettled([
        API.get('/api/excel/sheets?filename=' + encodeURIComponent(filename)),
        API.get('/api/workflows/bindings/' + encodeURIComponent(filename)),
        API.get('/api/runs/testsets/' + encodeURIComponent(filename) + '/request-template'),
    ]);
    if (results[0].status === 'fulfilled') {
        context.sheets = results[0].value.sheets || [];
        var first = context.sheets[0];
        sheetInfo.innerHTML = first
            ? '<strong>' + esc(first.name) + '</strong><span>' + first.rows + ' 条用例 · 忽略 ' + Math.max(0, context.sheets.length - 1) + ' 个 Sheet</span>'
            : '<strong>工作簿没有 Sheet</strong>';
    } else {
        sheetInfo.textContent = 'Sheet 读取失败';
    }
    if (results[1].status === 'fulfilled') {
        context.binding = results[1].value;
        bindingInfo.innerHTML = '<strong>' + esc(context.binding.workflow.name) + '</strong><span>' + (context.binding.workflow.valid ? '结构有效' : 'Workflow 当前无效') + '</span>';
    } else {
        bindingInfo.innerHTML = '<strong>未绑定 Workflow</strong><span>请先在工作流编排页完成绑定</span>';
    }
    if (results[2].status === 'fulfilled') {
        context.templateConfigured = true;
        template.value = JSON.stringify(results[2].value.config.request_template, null, 2);
    } else {
        template.value = JSON.stringify(defaultRequestTemplate(), null, 2);
    }
    executionState.runSetContext = context;
    create.disabled = !(context.binding && context.binding.workflow && context.binding.workflow.valid && context.sheets.length);
}

function runCreateFormHtml() {
    return '<div class="run-create-layout">' +
        '<section class="run-create-main">' +
            '<div class="execution-form-grid run-create-grid">' +
                '<label class="form-row form-row-full"><span class="form-label">测试集</span><select class="input" id="run-testset">' + runSetOptions() + '</select></label>' +
                '<div class="run-context-block"><span>实际执行 Sheet</span><div id="run-sheet-info">请选择测试集</div></div>' +
                '<div class="run-context-block"><span>Workflow 绑定</span><div id="run-binding-info">请选择测试集</div></div>' +
                '<label class="form-row form-row-full"><span class="form-label">Target</span><select class="input" id="run-target">' + runTargetOptions() + '</select></label>' +
                '<label class="form-row"><span class="form-label">超时（秒）</span><input class="input" id="run-timeout" type="number" min="0.1" step="0.1" value="600" /></label>' +
                '<label class="form-row"><span class="form-label">Case 并发</span><input class="input" id="run-case-concurrency" type="number" min="1" step="1" value="1" /></label>' +
                '<label class="form-row"><span class="form-label">连接重试次数</span><input class="input" id="run-retry-count" type="number" min="0" step="1" value="0" /></label>' +
                '<label class="form-row"><span class="form-label">重试间隔（秒）</span><input class="input" id="run-retry-interval" type="number" min="0" step="0.1" value="0" /></label>' +
            '</div>' +
        '</section>' +
        '<aside class="run-template-panel"><div class="workflow-panel-title">请求模板</div>' +
            '<textarea class="input execution-code-input" id="run-request-template" spellcheck="false"></textarea>' +
            '<div class="run-template-status" id="run-template-status"></div>' +
        '</aside>' +
        '<footer class="run-create-footer"><div class="execution-form-error hidden" id="run-create-error" role="alert"></div><button class="btn btn-primary" id="btn-run-create" type="button" disabled>创建 QUEUED Run</button></footer>' +
    '</div>';
}

async function loadRunCreateResources() {
    var panel = document.getElementById('runs-panel');
    panel.innerHTML = '<div class="execution-loading">正在加载测试集和 Target</div>';
    try {
        var results = await Promise.all([loadAllTestsets(), API.get('/api/targets')]);
        executionState.targets = results[1].targets || [];
        if (!executionState.sets.length || !executionState.targets.length) {
            panel.innerHTML = executionEmpty(
                !executionState.sets.length ? '请先导入测试集' : '请先创建 Target',
                '',
                ''
            );
            return;
        }
        panel.innerHTML = runCreateFormHtml();
        document.getElementById('run-testset').addEventListener('change', loadRunSetContext);
        document.getElementById('run-request-template').addEventListener('input', validateRunTemplate);
        document.getElementById('btn-run-create').addEventListener('click', createQueuedRun);
        await loadRunSetContext();
        validateRunTemplate();
    } catch (error) {
        panel.innerHTML = executionEmpty('Run 创建资源加载失败', '', '');
        showToast(executionErrorMessage(error), 'error');
    }
}

function validateRunTemplate() {
    var textarea = document.getElementById('run-request-template');
    var status = document.getElementById('run-template-status');
    if (!textarea || !status) return null;
    try {
        var parsed = JSON.parse(textarea.value);
        status.className = 'run-template-status is-valid';
        status.textContent = 'JSON 有效';
        return parsed;
    } catch (error) {
        status.className = 'run-template-status is-invalid';
        status.textContent = 'JSON 无效：' + error.message;
        return null;
    }
}

function readRunParameters() {
    var timeout = Number(document.getElementById('run-timeout').value);
    var concurrency = Number(document.getElementById('run-case-concurrency').value);
    var retries = Number(document.getElementById('run-retry-count').value);
    var interval = Number(document.getElementById('run-retry-interval').value);
    if (!(timeout > 0)) throw new Error('超时必须大于 0');
    if (!Number.isInteger(concurrency) || concurrency < 1) throw new Error('Case 并发必须是正整数');
    if (!Number.isInteger(retries) || retries < 0) throw new Error('连接重试次数必须是非负整数');
    if (!(interval >= 0)) throw new Error('重试间隔不能小于 0');
    return {
        timeout_seconds: timeout,
        case_concurrency: concurrency,
        connection_retry_count: retries,
        retry_interval_seconds: interval,
    };
}

function showRunCreateError(message) {
    var error = document.getElementById('run-create-error');
    error.textContent = message;
    error.classList.remove('hidden');
}

async function createQueuedRun() {
    var filename = document.getElementById('run-testset').value;
    var targetId = document.getElementById('run-target').value;
    var template = validateRunTemplate();
    if (template === null) {
        showRunCreateError('请求模板必须是合法 JSON');
        return;
    }
    var parameters;
    try {
        parameters = readRunParameters();
    } catch (error) {
        showRunCreateError(error.message);
        return;
    }
    var button = document.getElementById('btn-run-create');
    button.disabled = true;
    try {
        await executionRequest('PUT', '/api/runs/testsets/' + encodeURIComponent(filename) + '/request-template', {request_template: template});
        var data = await executionRequest('POST', '/api/runs', {
            testset_filename: filename,
            target_id: targetId,
            parameters: parameters,
        });
        if (data.run.status !== 'QUEUED') throw new Error('Run 创建后状态异常：' + data.run.status);
        showToast('QUEUED Run 已创建', 'success');
        openRunDetail(data.run.id);
    } catch (error) {
        showRunCreateError(executionErrorMessage(error));
        button.disabled = false;
    }
}

function switchRunsTab(tab) {
    executionState.runsTab = tab;
    document.querySelectorAll('[data-runs-tab]').forEach(function (button) {
        button.classList.toggle('is-active', button.getAttribute('data-runs-tab') === tab);
    });
    if (tab === 'create') loadRunCreateResources();
    else renderRunHistory();
}

function viewRuns() {
    destroyToolCodeEditor();
    disconnectRunEvents();
    currentView = 'runs';
    contentArea.innerHTML =
        '<section class="execution-page runs-page" aria-labelledby="runs-title">' +
            '<header class="execution-page-header">' +
                '<div><h1 id="runs-title">运行中心</h1><p>创建、启动、恢复并追溯测试集运行</p></div>' +
                '<span class="execution-count" id="run-count">0 个 Run</span>' +
            '</header>' +
            '<div class="runs-tabs"><button type="button" data-runs-tab="history" class="is-active">运行历史</button><button type="button" data-runs-tab="create">新建 Run</button></div>' +
            '<div id="runs-panel"></div>' +
        '</section>';
    document.querySelectorAll('[data-runs-tab]').forEach(function (button) {
        button.addEventListener('click', function () { switchRunsTab(button.getAttribute('data-runs-tab')); });
    });
    switchRunsTab(executionState.runsTab || 'history');
}

function disconnectRunEvents() {
    if (executionState.runEventSource) executionState.runEventSource.close();
    executionState.runEventSource = null;
    executionState.runEventRunId = null;
}

function parseRunEvent(event) {
    try { return JSON.parse(event.data); } catch (error) { return null; }
}

function connectRunEvents(runId) {
    if (executionState.runEventSource && executionState.runEventRunId === runId) return Promise.resolve();
    disconnectRunEvents();
    return new Promise(function (resolve, reject) {
        var source = new EventSource('/api/runs/' + encodeURIComponent(runId) + '/events');
        var settled = false;
        executionState.runEventSource = source;
        executionState.runEventRunId = runId;
        source.onopen = function () {
            settled = true;
            resolve();
        };
        source.addEventListener('run_state', function (event) {
            var payload = parseRunEvent(event);
            if (!payload || !payload.run || !executionState.runDetail) return;
            executionState.runDetail.run = payload.run;
            executionState.runDetail.active = payload.run.status === 'RUNNING';
            renderRunDetailHeader();
        });
        source.addEventListener('case_state', function (event) {
            var payload = parseRunEvent(event);
            if (!payload || !payload.case || !executionState.runDetail) return;
            var index = executionState.runDetail.cases.findIndex(function (item) { return item.id === payload.case.id; });
            if (index >= 0) executionState.runDetail.cases[index] = payload.case;
            renderRunCases();
        });
        source.addEventListener('run_terminal', async function (event) {
            var payload = parseRunEvent(event);
            if (payload && payload.run && executionState.runDetail) executionState.runDetail.run = payload.run;
            disconnectRunEvents();
            await refreshRunDetail(runId);
        });
        source.onerror = function () {
            source.close();
            if (executionState.runEventSource === source) disconnectRunEvents();
            if (!settled) reject(new Error('实时事件连接失败'));
            else if (executionState.runDetail && executionState.runDetail.run.id === runId) refreshRunDetail(runId);
        };
    });
}

function runDuration(record) {
    if (!record.started_at) return '—';
    var end = record.finished_at ? new Date(record.finished_at) : new Date();
    var seconds = Math.max(0, (end.getTime() - new Date(record.started_at).getTime()) / 1000);
    if (seconds < 60) return seconds.toFixed(1) + 's';
    return Math.floor(seconds / 60) + 'm ' + Math.floor(seconds % 60) + 's';
}

function recoverableCase(run, caseRun) {
    if (run.active || caseRun.status === 'SUCCEEDED') return false;
    return ['QUEUED', 'ERROR', 'CANCELLED', 'RUNNING'].includes(caseRun.status);
}

function runCaseCounts(cases) {
    return cases.reduce(function (counts, caseRun) {
        counts[caseRun.status] = (counts[caseRun.status] || 0) + 1;
        return counts;
    }, {});
}

function renderRunDetailHeader() {
    var detail = executionState.runDetail;
    if (!detail) return;
    var run = detail.run;
    var header = document.getElementById('run-detail-header');
    var summary = document.getElementById('run-detail-summary');
    var actions = document.getElementById('run-detail-actions');
    if (!header || !summary || !actions) return;
    header.querySelector('.run-detail-title').textContent = run.testset_filename;
    header.querySelector('.run-detail-id').textContent = run.id;
    header.querySelector('.run-detail-statuses').innerHTML = runStatusBadge(run.status) + runBusinessBadge(run.business_status);
    var excel = run.snapshot.excel || {};
    summary.innerHTML =
        '<div><span>首个 Sheet</span><strong>' + esc(run.sheet_name) + '</strong><small>忽略 ' + ((excel.ignored_sheet_names || []).length) + ' 个 Sheet</small></div>' +
        '<div><span>Target</span><strong title="' + esc(run.target_id || '') + '">' + esc(((run.snapshot.target || {}).name) || run.target_id || '—') + '</strong><small>总并发 ' + esc(String(((run.snapshot.target || {}).target_total_concurrency) || '—')) + '</small></div>' +
        '<div><span>Workflow</span><strong title="' + esc(run.workflow_id || '') + '">' + esc((((run.snapshot.workflow || {}).workflow || {}).name) || run.workflow_id || '—') + '</strong><small>' + esc(run.workflow_id || '') + '</small></div>' +
        '<div><span>Case 并发</span><strong>' + esc(String(run.parameters.case_concurrency || 1)) + '</strong><small>超时 ' + esc(String(run.parameters.timeout_seconds || 600)) + 's</small></div>' +
        '<div><span>耗时</span><strong>' + runDuration(run) + '</strong><small>' + esc(formatDateTime(run.created_at)) + '</small></div>' +
        '<div><span>Artifacts</span><strong>' + executionState.runArtifacts.length + '</strong><small>完整请求、响应和结果</small></div>';
    var html = '<button class="btn" type="button" id="btn-run-detail-refresh">' + icon('refresh') + '刷新</button>';
    if (run.status === 'QUEUED' && !detail.active) html += '<button class="btn btn-primary" type="button" id="btn-run-start">启动 Run</button>';
    if (detail.active || run.status === 'QUEUED') html += '<button class="btn btn-danger" type="button" id="btn-run-cancel">取消 Run</button>';
    if (!detail.active && ['ERROR', 'CANCELLED', 'RUNNING'].includes(run.status)) html += '<button class="btn btn-primary" type="button" id="btn-run-resume-all">恢复全部未完成</button>';
    actions.innerHTML = html;
    document.getElementById('btn-run-detail-refresh').addEventListener('click', function () { refreshRunDetail(run.id); });
    var start = document.getElementById('btn-run-start');
    if (start) start.addEventListener('click', function () { startRunFromDetail(run.id); });
    var cancel = document.getElementById('btn-run-cancel');
    if (cancel) cancel.addEventListener('click', function () { cancelRunFromDetail(run.id); });
    var resume = document.getElementById('btn-run-resume-all');
    if (resume) resume.addEventListener('click', function () { resumeRunFromDetail(run.id, null); });
}

function runCaseFilter() {
    var search = document.getElementById('run-case-search');
    var status = document.getElementById('run-case-status');
    return {
        query: search ? search.value.trim().toLowerCase() : '',
        status: status ? status.value : '',
    };
}

function renderRunCases() {
    var detail = executionState.runDetail;
    var body = document.getElementById('run-case-body');
    var count = document.getElementById('run-case-counts');
    if (!detail || !body || !count) return;
    var filter = runCaseFilter();
    var cases = detail.cases.filter(function (caseRun) {
        var matchesStatus = !filter.status || caseRun.status === filter.status;
        var text = (caseRun.case_id + ' ' + caseRun.question).toLowerCase();
        return matchesStatus && (!filter.query || text.includes(filter.query));
    });
    var counts = runCaseCounts(detail.cases);
    count.textContent = detail.cases.length + ' Cases · ' + Object.keys(counts).map(function (status) { return status + ' ' + counts[status]; }).join(' · ');
    body.innerHTML = cases.map(function (caseRun) {
        var canRecover = recoverableCase(detail, caseRun);
        return '<tr data-case-row="' + esc(caseRun.id) + '">' +
            '<td class="run-case-select"><input type="checkbox" data-case-select="' + esc(caseRun.id) + '"' + (canRecover ? '' : ' disabled') + (executionState.selectedCaseIds[caseRun.id] ? ' checked' : '') + ' aria-label="选择恢复 ' + esc(caseRun.case_id) + '" /></td>' +
            '<td><button class="execution-name-button" type="button" data-case-detail="' + esc(caseRun.id) + '">' + esc(caseRun.case_id) + '</button><div class="execution-id">Excel 行 ' + caseRun.row_number + '</div></td>' +
            '<td class="run-question-cell" title="' + esc(caseRun.question) + '">' + esc(caseRun.question) + '</td>' +
            '<td>' + runStatusBadge(caseRun.status) + '</td>' +
            '<td>' + runBusinessBadge(caseRun.business_status) + '</td>' +
            '<td class="run-error-cell" title="' + esc(caseRun.error || '') + '">' + esc(caseRun.error || '—') + '</td>' +
            '<td>' + runDuration(caseRun) + '</td>' +
            '<td><button class="btn btn-sm" type="button" data-case-detail="' + esc(caseRun.id) + '">追溯</button></td>' +
        '</tr>';
    }).join('') || '<tr><td colspan="8"><div class="execution-empty"><strong>没有匹配的 Case</strong></div></td></tr>';
    body.querySelectorAll('[data-case-select]').forEach(function (checkbox) {
        checkbox.addEventListener('change', function () {
            if (checkbox.checked) executionState.selectedCaseIds[checkbox.getAttribute('data-case-select')] = true;
            else delete executionState.selectedCaseIds[checkbox.getAttribute('data-case-select')];
            updateResumeSelectedButton();
        });
    });
    body.querySelectorAll('[data-case-detail]').forEach(function (button) {
        button.addEventListener('click', function () { loadCaseTrace(button.getAttribute('data-case-detail')); });
    });
    updateResumeSelectedButton();
}

function updateResumeSelectedButton() {
    var button = document.getElementById('btn-run-resume-selected');
    if (!button) return;
    var count = Object.keys(executionState.selectedCaseIds).length;
    button.disabled = count === 0;
    button.textContent = count ? '恢复所选 ' + count + ' 个 Case' : '恢复所选 Case';
}

function traceTable(headers, rows) {
    return '<div class="table-wrap run-trace-table-wrap"><table class="table run-trace-table"><thead><tr>' + headers.map(function (header) { return '<th>' + esc(header) + '</th>'; }).join('') + '</tr></thead><tbody>' + (rows || '<tr><td colspan="8">暂无记录</td></tr>') + '</tbody></table></div>';
}

function renderCaseTraceBody() {
    var trace = executionState.caseTrace;
    var body = document.getElementById('run-trace-body');
    if (!trace || !body) return;
    if (executionState.caseTraceTab === 'steps') {
        body.innerHTML = traceTable(
            ['阶段', 'Check', 'Step / 工具', '执行序号', '执行状态', '业务结论', '耗时', '错误'],
            trace.steps.map(function (step) {
                return '<tr><td>' + esc(step.stage) + '</td><td>' + esc(step.check_item || '—') + '</td><td><strong>' + esc(step.step_id || '—') + '</strong><div class="execution-id">' + esc(step.tool_name || step.tool_id || '') + '</div></td><td>' + step.execution_number + '</td><td>' + runStatusBadge(step.status) + '</td><td>' + runBusinessBadge(step.business_status) + '</td><td>' + runDuration(step) + '</td><td>' + esc(step.error || '—') + '</td></tr>';
            }).join('')
        );
    } else if (executionState.caseTraceTab === 'artifacts') {
        body.innerHTML = traceTable(
            ['类型', '大小', '保留策略', 'Attempt', 'Step', '创建时间', '下载'],
            trace.artifacts.map(function (artifact) {
                return '<tr><td><strong>' + esc(artifact.kind) + '</strong></td><td>' + formatSize(artifact.size_bytes) + '</td><td>' + esc(artifact.retention_class) + '</td><td><code>' + esc(artifact.attempt_id || '—') + '</code></td><td><code>' + esc(artifact.step_run_id || '—') + '</code></td><td>' + esc(formatDateTime(artifact.created_at)) + '</td><td><a class="btn btn-sm" href="/api/runs/' + encodeURIComponent(trace.case.run_id) + '/artifacts/' + encodeURIComponent(artifact.id) + '/download">下载</a></td></tr>';
            }).join('')
        );
    } else {
        body.innerHTML = traceTable(
            ['序号', '执行状态', 'HTTP', 'body.code', '错误类型', '错误', '耗时', '开始时间'],
            trace.attempts.map(function (attempt) {
                return '<tr><td>' + attempt.attempt_number + '</td><td>' + runStatusBadge(attempt.status) + '</td><td>' + esc(String(attempt.http_status || '—')) + '</td><td>' + esc(attempt.body_code || '—') + '</td><td>' + esc(attempt.error_type || '—') + '</td><td>' + esc(attempt.error || '—') + '</td><td>' + runDuration(attempt) + '</td><td>' + esc(formatDateTime(attempt.started_at)) + '</td></tr>';
            }).join('')
        );
    }
}

function renderCaseTrace() {
    var trace = executionState.caseTrace;
    var panel = document.getElementById('run-case-trace');
    if (!trace || !panel) return;
    panel.classList.remove('hidden');
    panel.innerHTML = '<header class="run-trace-header"><div><span>Case 追溯</span><strong>' + esc(trace.case.case_id) + '</strong></div><button class="btn-icon" id="btn-trace-close" type="button" aria-label="关闭 Case 追溯" title="关闭">×</button></header>' +
        '<div class="run-trace-tabs"><button type="button" data-trace-tab="attempts">Attempts ' + trace.attempts.length + '</button><button type="button" data-trace-tab="steps">Steps ' + trace.steps.length + '</button><button type="button" data-trace-tab="artifacts">Artifacts ' + trace.artifacts.length + '</button></div>' +
        '<div id="run-trace-body"></div>';
    panel.querySelectorAll('[data-trace-tab]').forEach(function (button) {
        button.classList.toggle('is-active', button.getAttribute('data-trace-tab') === executionState.caseTraceTab);
        button.addEventListener('click', function () {
            executionState.caseTraceTab = button.getAttribute('data-trace-tab');
            renderCaseTrace();
        });
    });
    document.getElementById('btn-trace-close').addEventListener('click', function () {
        executionState.caseTrace = null;
        panel.classList.add('hidden');
        panel.innerHTML = '';
    });
    renderCaseTraceBody();
    panel.scrollIntoView({behavior: 'smooth', block: 'start'});
}

async function loadCaseTrace(caseRunId) {
    var runId = executionState.runDetail.run.id;
    var panel = document.getElementById('run-case-trace');
    panel.classList.remove('hidden');
    panel.innerHTML = '<div class="execution-loading">正在加载 Case 追溯</div>';
    try {
        executionState.caseTrace = await API.get('/api/runs/' + encodeURIComponent(runId) + '/cases/' + encodeURIComponent(caseRunId));
        executionState.caseTraceTab = 'attempts';
        renderCaseTrace();
    } catch (error) {
        panel.innerHTML = '<div class="execution-empty"><strong>Case 追溯加载失败</strong></div>';
        showToast(executionErrorMessage(error), 'error');
    }
}

function renderRunDetail() {
    var detail = executionState.runDetail;
    var run = detail.run;
    contentArea.innerHTML = '<section class="run-detail-page">' +
        '<header class="run-detail-header" id="run-detail-header">' +
            '<button class="btn btn-sm" id="btn-run-detail-back" type="button">' + icon('back') + '返回运行中心</button>' +
            '<div class="run-detail-heading"><div><h1 class="run-detail-title"></h1><code class="run-detail-id"></code></div><div class="run-detail-statuses"></div></div>' +
            '<div class="run-detail-actions" id="run-detail-actions"></div>' +
        '</header>' +
        '<div class="run-detail-summary" id="run-detail-summary"></div>' +
        '<div class="run-case-toolbar"><div><strong>Case Runs</strong><span id="run-case-counts"></span></div><span class="toolbar-sep"></span>' +
            '<select class="input toolbar-control" id="run-case-status"><option value="">全部状态</option><option>QUEUED</option><option>RUNNING</option><option>SUCCEEDED</option><option>ERROR</option><option>CANCELLED</option></select>' +
            '<input type="search" class="input toolbar-search" id="run-case-search" placeholder="搜索 case_id 或问题" aria-label="搜索 Case" />' +
            '<button class="btn btn-primary" id="btn-run-resume-selected" type="button" disabled>恢复所选 Case</button>' +
        '</div>' +
        '<div class="table-wrap run-case-table-wrap"><table class="table run-case-table"><thead><tr><th></th><th>Case</th><th>Question</th><th>执行状态</th><th>业务结论</th><th>错误</th><th>耗时</th><th>追溯</th></tr></thead><tbody id="run-case-body"></tbody></table></div>' +
        '<section class="run-case-trace hidden" id="run-case-trace"></section>' +
    '</section>';
    document.getElementById('btn-run-detail-back').addEventListener('click', function () {
        disconnectRunEvents();
        executionState.runsTab = 'history';
        viewRuns();
    });
    document.getElementById('run-case-status').addEventListener('change', renderRunCases);
    document.getElementById('run-case-search').addEventListener('input', renderRunCases);
    document.getElementById('btn-run-resume-selected').addEventListener('click', function () {
        resumeRunFromDetail(run.id, Object.keys(executionState.selectedCaseIds));
    });
    renderRunDetailHeader();
    renderRunCases();
    if (executionState.caseTrace) renderCaseTrace();
}

async function refreshRunDetail(runId) {
    try {
        var results = await Promise.all([
            API.get('/api/runs/' + encodeURIComponent(runId)),
            API.get('/api/runs/' + encodeURIComponent(runId) + '/artifacts'),
        ]);
        executionState.runDetail = results[0];
        executionState.runArtifacts = results[1].artifacts || [];
        renderRunDetail();
        if (executionState.runDetail.active && !executionState.runEventSource) {
            connectRunEvents(runId).catch(function () { showToast('实时事件连接失败，已保留持久状态', 'error'); });
        }
    } catch (error) {
        showToast(executionErrorMessage(error), 'error');
    }
}

async function openRunDetail(runId) {
    disconnectRunEvents();
    executionState.selectedCaseIds = {};
    executionState.caseTrace = null;
    executionState.runDetail = null;
    executionLoading('正在加载 Run ' + runId);
    await refreshRunDetail(runId);
}

async function startRunFromDetail(runId) {
    var button = document.getElementById('btn-run-start');
    if (button) button.disabled = true;
    try {
        await connectRunEvents(runId);
        var data = await executionRequest('POST', '/api/runs/' + encodeURIComponent(runId) + '/start', {});
        executionState.runDetail = data;
        renderRunDetail();
    } catch (error) {
        disconnectRunEvents();
        showToast(executionErrorMessage(error), 'error');
        await refreshRunDetail(runId);
    }
}

async function cancelRunFromDetail(runId) {
    if (!window.confirm('确定取消当前 Run 吗？已发送到外部 FastAPI 的请求不保证远端终止。')) return;
    try {
        var data = await executionRequest('POST', '/api/runs/' + encodeURIComponent(runId) + '/cancel', {});
        executionState.runDetail = data;
        if (!data.was_active) disconnectRunEvents();
        renderRunDetail();
    } catch (error) {
        showToast(executionErrorMessage(error), 'error');
    }
}

async function resumeRunFromDetail(runId, caseRunIds) {
    try {
        await connectRunEvents(runId);
        var data = await executionRequest('POST', '/api/runs/' + encodeURIComponent(runId) + '/resume', {case_run_ids: caseRunIds});
        executionState.runDetail = data;
        executionState.selectedCaseIds = {};
        renderRunDetail();
    } catch (error) {
        disconnectRunEvents();
        showToast(executionErrorMessage(error), 'error');
        await refreshRunDetail(runId);
    }
}
