/* Four-type tool template management UI. */
var toolTemplateState = {
    templates: [],
    type: '',
    query: '',
};
var activeToolTemplateRun = null;

function templateTypeClass(type) {
    return 'type-' + String(type || '').toLowerCase();
}

function filteredToolTemplates() {
    return toolTemplateState.templates.filter(function (template) {
        var manifest = template.manifest;
        var matchesType = !toolTemplateState.type || manifest.type === toolTemplateState.type;
        var text = (manifest.name + ' ' + (manifest.description || '')).toLowerCase();
        return matchesType && (!toolTemplateState.query || text.includes(toolTemplateState.query));
    });
}

function renderToolTemplateRows() {
    var body = document.getElementById('tool-template-list-body');
    var count = document.getElementById('tool-template-count');
    if (!body || !count) return;
    var templates = filteredToolTemplates();
    count.textContent = toolTemplateState.templates.length + ' 个模板';
    if (!templates.length) {
        body.innerHTML = '<tr><td colspan="6"><div class="execution-empty"><strong>' +
            (toolTemplateState.templates.length ? '没有匹配的工具模板' : '尚未创建工具模板') +
            '</strong></div></td></tr>';
        return;
    }
    body.innerHTML = templates.map(function (template) {
        var manifest = template.manifest;
        return '<tr>' +
            '<td><button type="button" class="execution-name-button" data-template-edit="' + escAttr(manifest.id) + '">' + esc(manifest.name) + '</button>' +
                '<div class="execution-id">' + esc(manifest.id) + '</div></td>' +
            '<td><span class="type-pill ' + templateTypeClass(manifest.type) + '">' + esc(manifest.type) + '</span></td>' +
            '<td>' + esc(manifest.description || '—') + '</td>' +
            '<td><span class="execution-badge execution-badge-neutral">' + esc(template.definition.type === 'HTTP' ? template.definition.execution_mode : 'CODE') + '</span></td>' +
            '<td>' + esc(formatDateTime(manifest.updated_at)) + '</td>' +
            '<td><div class="execution-row-actions">' +
                '<button class="btn-icon" type="button" data-template-edit="' + escAttr(manifest.id) + '" title="编辑工具模板" aria-label="编辑工具模板">' + icon('edit') + '</button>' +
                '<button class="btn-icon" type="button" data-template-export="' + escAttr(manifest.id) + '" title="导出工具模板" aria-label="导出工具模板">' + icon('export') + '</button>' +
                '<button class="btn-icon" type="button" data-template-delete="' + escAttr(manifest.id) + '" title="删除工具模板" aria-label="删除工具模板">' + icon('trash') + '</button>' +
            '</div></td></tr>';
    }).join('');
    body.querySelectorAll('[data-template-edit]').forEach(function (button) {
        button.addEventListener('click', function () { viewToolTemplateEdit(button.getAttribute('data-template-edit')); });
    });
    body.querySelectorAll('[data-template-delete]').forEach(function (button) {
        button.addEventListener('click', function () { deleteToolTemplate(button.getAttribute('data-template-delete')); });
    });
    body.querySelectorAll('[data-template-export]').forEach(function (button) {
        button.addEventListener('click', function () { exportToolTemplates([button.getAttribute('data-template-export')]); });
    });
}

async function loadToolTemplates() {
    try {
        var data = await API.get('/api/tool-templates');
        toolTemplateState.templates = data.templates || [];
        renderToolTemplateRows();
    } catch (error) {
        showToast('加载工具模板失败: ' + error.message, 'error');
    }
}

function viewToolTemplates() {
    currentView = 'tool-templates';
    contentArea.innerHTML =
        '<section class="execution-page tool-template-page" aria-labelledby="tool-template-title">' +
            '<header class="execution-page-header"><div><h1 id="tool-template-title">工具模板</h1></div><span class="execution-count" id="tool-template-count">0 个模板</span></header>' +
            '<div class="toolbar execution-toolbar">' +
                '<button class="btn btn-primary" id="btn-tool-template-add" type="button">' + icon('add') + '新增模板</button>' +
                '<button class="btn" id="btn-tool-template-refresh" type="button">' + icon('refresh') + '刷新</button>' +
                '<button class="btn" id="btn-tool-template-import" type="button">' + icon('import') + '导入 ZIP</button>' +
                '<input id="tool-template-import-input" type="file" accept=".zip,application/zip" multiple hidden />' +
                '<button class="btn" id="btn-tool-template-export-all" type="button">' + icon('export') + '导出全部</button>' +
                '<select class="input toolbar-control" id="tool-template-type-filter" aria-label="筛选模板类型">' +
                    '<option value="">全部类型</option><option>HTTP</option><option>AGENT</option><option>LLM</option><option>SCRIPT</option>' +
                '</select>' +
                '<input class="input toolbar-search" id="tool-template-search" type="search" placeholder="按名称搜索..." aria-label="搜索工具模板" />' +
            '</div>' +
            '<div class="table-wrap execution-table-wrap"><table class="table execution-table tool-template-table">' +
                '<thead><tr><th>名称</th><th>类型</th><th>说明</th><th>执行模式</th><th>更新时间</th><th>操作</th></tr></thead>' +
                '<tbody id="tool-template-list-body"></tbody>' +
            '</table></div>' +
        '</section>';
    document.getElementById('btn-tool-template-add').addEventListener('click', openToolTemplateCreate);
    document.getElementById('btn-tool-template-refresh').addEventListener('click', async function () {
        await API.post('/api/tool-templates/refresh', {});
        await loadToolTemplates();
    });
    var importInput = document.getElementById('tool-template-import-input');
    document.getElementById('btn-tool-template-import').addEventListener('click', function () { importInput.click(); });
    importInput.addEventListener('change', function () {
        importToolTemplateArchives(Array.from(importInput.files || []));
    });
    document.getElementById('btn-tool-template-export-all').addEventListener('click', function () { exportToolTemplates([]); });
    document.getElementById('tool-template-type-filter').addEventListener('change', function () {
        toolTemplateState.type = this.value;
        renderToolTemplateRows();
    });
    document.getElementById('tool-template-search').addEventListener('input', function () {
        toolTemplateState.query = this.value.trim().toLowerCase();
        renderToolTemplateRows();
    });
    loadToolTemplates();
}

async function importToolTemplateArchives(files) {
    if (!files.length) return;
    var imported = 0;
    var failures = [];
    for (var index = 0; index < files.length; index++) {
        var file = files[index];
        var formData = new FormData();
        formData.append('file', file);
        try {
            var result = await API.upload('/api/tool-templates/import', formData);
            imported += result.imported || 0;
        } catch (error) {
            failures.push(file.name + ': ' + error.message);
        }
    }
    var input = document.getElementById('tool-template-import-input');
    if (input) input.value = '';
    await loadToolTemplates();
    if (failures.length) {
        showToast('已导入 ' + imported + ' 个模板；失败 ' + failures.length + ' 个 ZIP：' + failures.join('；'), 'error');
    } else {
        showToast('已导入 ' + imported + ' 个工具模板', 'success');
    }
}

async function exportToolTemplates(templateIds) {
    if (!window.confirm('导出不会自动清理 config 或 main.py 中的凭据。仅将 ZIP 交给可信接收者，是否继续？')) return;
    try {
        var response = await fetch('/api/tool-templates/export', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({template_ids: templateIds}),
        });
        if (!response.ok) {
            var errorBody = await response.json().catch(function () { return {}; });
            throw new Error(errorBody.detail || '导出失败');
        }
        var blob = await response.blob();
        var url = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = templateIds.length === 1 ? 'tool-template-' + templateIds[0] + '.zip' : 'tool-templates.zip';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        showToast('工具模板 ZIP 已生成', 'success');
    } catch (error) {
        showToast('导出工具模板失败: ' + error.message, 'error');
    }
}

function ensureToolTemplateCreateModal() {
    var overlay = document.getElementById('tool-template-create-overlay');
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'tool-template-create-overlay';
    overlay.className = 'overlay hidden';
    overlay.innerHTML = '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="tool-template-create-title">' +
        '<div class="modal-header" id="tool-template-create-title">新增工具模板</div>' +
        '<div class="modal-body">' +
            '<label class="form-row"><span class="form-label">类型</span><select class="input" id="new-template-type"><option>HTTP</option><option>AGENT</option><option>LLM</option><option>SCRIPT</option></select></label>' +
            '<label class="form-row"><span class="form-label">名称</span><input class="input" id="new-template-name" /></label>' +
            '<label class="form-row"><span class="form-label">说明</span><input class="input" id="new-template-description" /></label>' +
        '</div><div class="modal-footer"><button class="btn" id="new-template-cancel">取消</button><button class="btn btn-primary" id="new-template-save">创建</button></div>' +
    '</div>';
    document.body.appendChild(overlay);
    overlay.querySelector('#new-template-cancel').addEventListener('click', function () { overlay.classList.add('hidden'); });
    overlay.addEventListener('click', function (event) { if (event.target === overlay) overlay.classList.add('hidden'); });
    overlay.querySelector('#new-template-save').addEventListener('click', createToolTemplate);
    return overlay;
}

function openToolTemplateCreate() {
    var overlay = ensureToolTemplateCreateModal();
    overlay.querySelector('#new-template-type').value = 'HTTP';
    overlay.querySelector('#new-template-name').value = '';
    overlay.querySelector('#new-template-description').value = '';
    overlay.classList.remove('hidden');
    overlay.querySelector('#new-template-name').focus();
}

async function createToolTemplate() {
    var overlay = ensureToolTemplateCreateModal();
    var name = overlay.querySelector('#new-template-name').value.trim();
    if (!name) {
        showToast('名称不能为空', 'error');
        return;
    }
    try {
        var data = await API.post('/api/tool-templates', {
            type: overlay.querySelector('#new-template-type').value,
            name: name,
            description: overlay.querySelector('#new-template-description').value.trim(),
        });
        overlay.classList.add('hidden');
        await loadToolTemplates();
        viewToolTemplateEdit(data.template.manifest.id);
    } catch (error) {
        showToast('创建工具模板失败: ' + error.message, 'error');
    }
}

function templateJsonText(value) {
    return JSON.stringify(value, null, 2);
}

function parseTemplateJson(id, label) {
    try {
        return JSON.parse(document.getElementById(id).value || (id === 'template-config' ? '{}' : '[]'));
    } catch (error) {
        throw new Error(label + '必须是合法 JSON');
    }
}

async function viewToolTemplateEdit(templateId) {
    currentView = 'tool-template-edit';
    try {
        var data = await API.get('/api/tool-templates/' + encodeURIComponent(templateId));
        var template = data.template;
        var manifest = template.manifest;
        var definition = template.definition;
        var isHttp = manifest.type === 'HTTP';
        contentArea.innerHTML =
            '<section class="execution-page tool-template-editor" aria-labelledby="template-edit-title">' +
                '<header class="tool-template-editor-header">' +
                    '<button class="btn btn-sm" id="template-edit-back" type="button">' + icon('back') + '返回</button>' +
                    '<button class="btn btn-sm btn-primary" id="template-edit-save" type="button">' + icon('edit') + '保存</button>' +
                    '<h1 id="template-edit-title">编辑工具模板</h1>' +
                    '<span class="type-pill ' + templateTypeClass(manifest.type) + '">' + esc(manifest.type) + '</span>' +
                '</header>' +
                '<div class="tool-template-editor-grid">' +
                    '<label class="form-row"><span class="form-label">名称</span><input class="input" id="template-name" value="' + escAttr(manifest.name) + '" /></label>' +
                    '<label class="form-row"><span class="form-label">说明</span><input class="input" id="template-description" value="' + escAttr(manifest.description || '') + '" /></label>' +
                    (isHttp ? '<label class="form-row"><span class="form-label">执行模式</span><select class="input" id="template-execution-mode"><option' + (definition.execution_mode === 'CONFIG' ? ' selected' : '') + '>CONFIG</option><option' + (definition.execution_mode === 'CODE' ? ' selected' : '') + '>CODE</option></select></label>' : '') +
                    (isHttp ? '<label class="form-row form-row-full"><span class="form-label">HTTP 配置</span><textarea class="input template-json-editor" id="template-http" spellcheck="false">' + esc(templateJsonText(definition.http)) + '</textarea></label>' : '') +
                    '<label class="form-row form-row-full"><span class="form-label">Inputs</span><textarea class="input template-json-editor" id="template-inputs" spellcheck="false">' + esc(templateJsonText(definition.inputs || [])) + '</textarea></label>' +
                    '<label class="form-row form-row-full"><span class="form-label">Config</span><textarea class="input template-json-editor" id="template-config" spellcheck="false">' + esc(templateJsonText(definition.config || {})) + '</textarea></label>' +
                    '<label class="form-row form-row-full"><span class="form-label">Outputs</span><textarea class="input template-json-editor" id="template-outputs" spellcheck="false">' + esc(templateJsonText(definition.outputs || [])) + '</textarea></label>' +
                    '<label class="form-row form-row-full"><span class="form-label">main.py</span><textarea class="input template-code-editor" id="template-main-py" spellcheck="false">' + esc(template.main_py || '') + '</textarea></label>' +
                '</div>' +
                '<section class="tool-template-test-panel" aria-label="模板独立测试">' +
                    '<header><strong>独立测试</strong><span id="template-test-status" class="template-test-status">PENDING · 0ms</span></header>' +
                    '<div class="tool-template-test-grid">' +
                        '<div class="tool-template-test-inputs">' +
                            '<label for="template-test-inputs">Inputs</label>' +
                            '<textarea class="input" id="template-test-inputs" spellcheck="false">{}</textarea>' +
                            '<div class="tool-template-test-actions">' +
                                '<button class="btn btn-primary" id="template-test-run" type="button">运行</button>' +
                                '<button class="btn btn-danger" id="template-test-interrupt" type="button" disabled>中断</button>' +
                            '</div>' +
                        '</div>' +
                        '<div class="tool-template-test-output">' +
                            '<div class="template-test-log-heading"><span>日志与 response</span><button class="btn btn-sm" id="template-test-clear" type="button">清空</button></div>' +
                            '<pre id="template-test-log" aria-live="polite">等待运行...</pre>' +
                        '</div>' +
                    '</div>' +
                '</section>' +
            '</section>';
        document.getElementById('template-edit-back').addEventListener('click', viewToolTemplates);
        document.getElementById('template-edit-save').addEventListener('click', function () { saveToolTemplate(template); });
        document.getElementById('template-test-run').addEventListener('click', function () { runToolTemplateTest(template); });
        document.getElementById('template-test-interrupt').addEventListener('click', interruptToolTemplateTest);
        document.getElementById('template-test-clear').addEventListener('click', function () {
            document.getElementById('template-test-log').textContent = '';
        });
    } catch (error) {
        showToast('读取工具模板失败: ' + error.message, 'error');
    }
}

async function saveToolTemplate(template, options) {
    options = options || {};
    try {
        var body = {
            name: document.getElementById('template-name').value.trim(),
            description: document.getElementById('template-description').value.trim(),
            inputs: parseTemplateJson('template-inputs', 'Inputs'),
            config: parseTemplateJson('template-config', 'Config'),
            outputs: parseTemplateJson('template-outputs', 'Outputs'),
            main_py: document.getElementById('template-main-py').value,
        };
        if (template.manifest.type === 'HTTP') {
            body.execution_mode = document.getElementById('template-execution-mode').value;
            body.http = parseTemplateJson('template-http', 'HTTP 配置');
        }
        var data = await API.put('/api/tool-templates/' + encodeURIComponent(template.manifest.id), body);
        if (!options.silent) showToast('工具模板已保存', 'success');
        if (options.reload !== false) await viewToolTemplateEdit(template.manifest.id);
        return data.template;
    } catch (error) {
        showToast('保存工具模板失败: ' + error.message, 'error');
        return null;
    }
}

function createTemplateRunId() {
    if (window.crypto && window.crypto.randomUUID) return 'template-' + window.crypto.randomUUID();
    return 'template-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
}

function formatTemplateRunDuration(value) {
    var elapsed = Math.max(0, Math.round(value || 0));
    return elapsed < 1000 ? elapsed + 'ms' : (elapsed / 1000).toFixed(1) + 's';
}

function setTemplateRunStatus(status, elapsedMs) {
    var element = document.getElementById('template-test-status');
    if (!element) return;
    element.textContent = status + ' · ' + formatTemplateRunDuration(elapsedMs);
    element.className = 'template-test-status is-' + status.toLowerCase();
}

function appendTemplateRunLog(text) {
    var log = document.getElementById('template-test-log');
    if (log && text) log.textContent += text;
}

function finishToolTemplateRun(run, status, result) {
    if (activeToolTemplateRun !== run) return;
    if (run.source) run.source.close();
    if (run.timer) window.clearInterval(run.timer);
    var elapsedMs = result && result.latency_ms !== undefined
        ? result.latency_ms
        : performance.now() - run.startedAt;
    if (result && Object.prototype.hasOwnProperty.call(result, 'response')) {
        appendTemplateRunLog('\nresponse:\n' + JSON.stringify(result.response, null, 2) + '\n');
    }
    if (result && result.error) appendTemplateRunLog('\n' + result.error + '\n');
    setTemplateRunStatus(status, elapsedMs);
    var runButton = document.getElementById('template-test-run');
    var interruptButton = document.getElementById('template-test-interrupt');
    if (runButton) runButton.disabled = false;
    if (interruptButton) interruptButton.disabled = true;
    activeToolTemplateRun = null;
}

async function runToolTemplateTest(template) {
    if (activeToolTemplateRun) {
        showToast('已有工具模板正在运行', 'error');
        return;
    }
    var inputs;
    try {
        inputs = JSON.parse(document.getElementById('template-test-inputs').value || '{}');
        if (!inputs || Array.isArray(inputs) || typeof inputs !== 'object') throw new Error('Inputs 必须是 JSON 对象');
    } catch (error) {
        showToast('测试 Inputs 必须是合法 JSON 对象', 'error');
        return;
    }
    var saved = await saveToolTemplate(template, {reload: false, silent: true});
    if (!saved) return;

    var run = {
        runId: createTemplateRunId(),
        templateId: template.manifest.id,
        startedAt: performance.now(),
        source: null,
        timer: null,
    };
    activeToolTemplateRun = run;
    var log = document.getElementById('template-test-log');
    var runButton = document.getElementById('template-test-run');
    var interruptButton = document.getElementById('template-test-interrupt');
    log.textContent = '';
    runButton.disabled = true;
    interruptButton.disabled = false;
    setTemplateRunStatus('RUNNING', 0);
    run.timer = window.setInterval(function () {
        if (activeToolTemplateRun === run) setTemplateRunStatus('RUNNING', performance.now() - run.startedAt);
    }, 100);

    try {
        await API.post('/api/tool-templates/' + encodeURIComponent(run.templateId) + '/runs', {
            run_id: run.runId,
            inputs: inputs,
        });
        var source = new EventSource('/api/tool-templates/runs/' + encodeURIComponent(run.runId) + '/events');
        run.source = source;
        source.addEventListener('log', function (event) {
            if (activeToolTemplateRun !== run) return;
            var payload = JSON.parse(event.data);
            appendTemplateRunLog(String(payload.text || ''));
        });
        source.addEventListener('complete', function (event) {
            if (activeToolTemplateRun !== run) return;
            var payload = JSON.parse(event.data);
            finishToolTemplateRun(run, payload.result && payload.result.ok ? 'PASSED' : 'FAILED', payload.result || {});
        });
        source.addEventListener('interrupted', function (event) {
            if (activeToolTemplateRun !== run) return;
            var payload = JSON.parse(event.data);
            finishToolTemplateRun(run, 'FAILED', payload.result || {});
        });
        source.onerror = function () {
            if (activeToolTemplateRun === run) {
                appendTemplateRunLog('\n实时日志连接失败\n');
                finishToolTemplateRun(run, 'FAILED', {});
            }
        };
    } catch (error) {
        appendTemplateRunLog(error.message + '\n');
        finishToolTemplateRun(run, 'FAILED', {});
    }
}

async function interruptToolTemplateTest() {
    var run = activeToolTemplateRun;
    if (!run) return;
    var button = document.getElementById('template-test-interrupt');
    if (button) button.disabled = true;
    try {
        await API.post('/api/tool-templates/runs/' + encodeURIComponent(run.runId) + '/interrupt', {});
    } catch (error) {
        appendTemplateRunLog('\n中断失败: ' + error.message + '\n');
        if (button && activeToolTemplateRun === run) button.disabled = false;
    }
}

async function deleteToolTemplate(templateId) {
    var template = toolTemplateState.templates.find(function (item) { return item.manifest.id === templateId; });
    if (!template || !window.confirm('确定删除工具模板“' + template.manifest.name + '”吗？')) return;
    try {
        await API.del('/api/tool-templates/' + encodeURIComponent(templateId));
        showToast('工具模板已删除', 'success');
        await loadToolTemplates();
    } catch (error) {
        showToast('删除工具模板失败: ' + error.message, 'error');
    }
}
