/* Target management and the frontend-local Workflow Studio. */
var executionState = {
    targets: [],
    workflows: [],
    editingTargetId: null,
};

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

function openExecutionModal(title, bodyHtml, onSave) {
    var overlay = ensureExecutionModal();
    overlay.querySelector('#execution-modal-title').textContent = title;
    overlay.querySelector('#execution-modal-body').innerHTML = bodyHtml;
    var save = overlay.querySelector('#execution-modal-save');
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
    if (!executionState.targets.length) {
        body.innerHTML = '<tr><td colspan="7">' + executionEmpty('尚未配置 Target', '新增 Target', 'target-empty-add') + '</td></tr>';
        var emptyAdd = document.getElementById('target-empty-add');
        if (emptyAdd) emptyAdd.addEventListener('click', function () { openTargetEditor(); });
        return;
    }
    body.innerHTML = executionState.targets.map(function (target) {
        return '<tr>' +
            '<td><button class="execution-name-button" type="button" data-target-edit="' + esc(target.id) + '">' + esc(target.name) + '</button>' +
                '<div class="execution-id">' + esc(target.id) + '</div></td>' +
            '<td><code class="target-address">' + esc(targetAddress(target)) + '</code></td>' +
            '<td><span class="execution-badge execution-badge-neutral">' + esc(target.method) + '</span></td>' +
            '<td>' + Object.keys(target.headers || {}).length + '</td>' +
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
    }
}

function viewTargets() {
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
                '<tbody id="target-list-body"></tbody>' +
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
        name: name, base_url: baseUrl, path: path, method: 'POST', headers: headers,
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
    openExecutionModal(target ? '编辑 Target' : '新增 Target', targetFormHtml(target), async function () {
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
    });
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

function filteredWorkflows() {
    var search = document.getElementById('workflow-search');
    var query = search ? search.value.trim().toLowerCase() : '';
    return executionState.workflows.filter(function (workflow) {
        return !query || (workflow.name + ' ' + (workflow.description || '')).toLowerCase().includes(query);
    });
}

function renderWorkflowTable() {
    var body = document.getElementById('workflow-list-body');
    var count = document.getElementById('workflow-count');
    if (!body || !count) return;
    var workflows = filteredWorkflows();
    count.textContent = executionState.workflows.length + ' 个 Workflow';
    if (!workflows.length) {
        body.innerHTML = '<tr><td colspan="5">' + executionEmpty(
            executionState.workflows.length ? '没有匹配的 Workflow' : '尚未创建 Workflow',
            executionState.workflows.length ? '' : '新建 Workflow', 'workflow-empty-add'
        ) + '</td></tr>';
        var emptyAdd = document.getElementById('workflow-empty-add');
        if (emptyAdd) emptyAdd.addEventListener('click', function () { openWorkflowEditor(); });
        return;
    }
    body.innerHTML = workflows.map(function (workflow) {
        return '<tr><td><button class="execution-name-button" type="button" data-workflow-edit="' + esc(workflow.id) + '">' + esc(workflow.name) + '</button>' +
            '<div class="execution-id">' + esc(workflow.id) + '</div></td>' +
            '<td>' + esc(workflow.description || '—') + '</td>' +
            '<td><span class="execution-badge workflow-invalid">前端草稿</span></td>' +
            '<td>' + esc(formatDateTime(workflow.updated_at)) + '</td>' +
            '<td><button class="btn-icon" type="button" data-workflow-edit="' + esc(workflow.id) + '" title="编辑 Workflow">' + icon('edit') + '</button></td></tr>';
    }).join('');
    body.querySelectorAll('[data-workflow-edit]').forEach(function (button) {
        button.addEventListener('click', function () { openWorkflowEditor(button.getAttribute('data-workflow-edit')); });
    });
}

async function loadWorkflows() {
    // T13.2 uses frontend-local Studio state until the new DAG protocol is frozen.
    renderWorkflowTable();
}

function viewWorkflows() {
    currentView = 'workflows';
    contentArea.innerHTML =
        '<section class="execution-page workflow-management-page" aria-label="工作流管理">' +
            '<div class="toolbar execution-toolbar" id="workflows-toolbar">' +
                '<button class="btn btn-sm btn-primary" id="btn-workflow-add" type="button">' + icon('add') + '新增工作流</button>' +
                '<button class="btn btn-sm" id="btn-workflow-refresh" type="button">' + icon('refresh') + '刷新</button>' +
                '<input type="search" class="input toolbar-search" id="workflow-search" placeholder="按名称搜索..." aria-label="搜索工作流" />' +
                '<select class="input toolbar-control" id="workflow-status-filter" aria-label="筛选工作流状态" disabled><option>前端草稿</option></select>' +
                '<span class="toolbar-sep"></span><span class="execution-count workflow-list-count" id="workflow-count">0 个 Workflow</span>' +
            '</div>' +
            '<div class="table-wrap" id="workflows-table-wrap"><table class="table workflow-table" id="workflows-table">' +
                '<thead><tr><th>名称</th><th>说明</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead>' +
                '<tbody id="workflow-list-body"></tbody>' +
            '</table></div>' +
        '</section>';
    document.getElementById('btn-workflow-add').addEventListener('click', function () { openWorkflowEditor(); });
    document.getElementById('btn-workflow-refresh').addEventListener('click', loadWorkflows);
    document.getElementById('workflow-search').addEventListener('input', renderWorkflowTable);
    loadWorkflows();
}

async function openWorkflowEditor(workflowId) {
    currentView = 'workflows';
    if (!window.AgentBenchWorkflowCanvas) {
        showToast('工作流画布资源加载失败', 'error');
        return;
    }
    var workflow = workflowId
        ? executionState.workflows.find(function (item) { return item.id === workflowId; })
        : null;
    window.AgentBenchWorkflowCanvas.mount({
        id: workflowId || null,
        name: workflow ? workflow.name : '未命名工作流',
        onSave: function () {
            if (!workflow) {
                workflow = {
                    id: 'local-' + Date.now(), name: '未命名工作流', description: '',
                    updated_at: new Date().toISOString(),
                };
                executionState.workflows.unshift(workflow);
            } else {
                workflow.updated_at = new Date().toISOString();
            }
            showToast('画布草稿已保存到当前前端会话', 'success');
        },
        onClose: function () {
            window.setTimeout(function () {
                window.AgentBenchWorkflowCanvas.unmount();
                viewWorkflows();
            }, 0);
        },
    });
}

async function saveWorkflowDraft() {
    showToast('新版 DAG 持久化协议尚未建立，当前只保存前端会话', 'success');
}
