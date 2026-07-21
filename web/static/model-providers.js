/* Model provider list and connection editor. */
var modelProviderState = {
    providers: [],
    query: '',
    editingId: null,
    discovered: [],
    selected: [],
    protocol: null,
    endpoint: null,
};

function modelProviderName(provider) {
    return provider.name || '未命名供应商';
}

function filteredModelProviders() {
    return modelProviderState.providers.filter(function (provider) {
        var text = [provider.name, provider.website_url, provider.base_url, provider.protocol]
            .concat(provider.models || []).filter(Boolean).join(' ').toLowerCase();
        return !modelProviderState.query || text.includes(modelProviderState.query);
    });
}

function renderModelProviderRows() {
    var body = document.getElementById('model-provider-list-body');
    var count = document.getElementById('model-provider-count');
    if (!body || !count) return;
    var providers = filteredModelProviders();
    count.textContent = modelProviderState.providers.length + ' 个供应商';
    if (!providers.length) {
        body.innerHTML = '<tr><td colspan="6"><div class="execution-empty"><strong>' +
            (modelProviderState.providers.length ? '没有匹配的模型供应商' : '尚未添加模型供应商') +
            '</strong></div></td></tr>';
        return;
    }
    body.innerHTML = providers.map(function (provider) {
        var website = provider.website_url
            ? '<a class="model-provider-website" href="' + escAttr(provider.website_url) + '" target="_blank" rel="noopener noreferrer">官网</a>'
            : '';
        var modelPreview = (provider.models || []).slice(0, 2).map(function (model) {
            return '<span class="model-provider-mini-model">' + esc(model) + '</span>';
        }).join('');
        var remaining = (provider.models || []).length - 2;
        if (remaining > 0) modelPreview += '<span class="model-provider-more">+' + remaining + '</span>';
        return '<tr>' +
            '<td><button class="execution-name-button" type="button" data-provider-edit="' + escAttr(provider.id) + '">' + esc(modelProviderName(provider)) + '</button>' + website +
                '<div class="execution-id">' + esc(provider.id) + '</div></td>' +
            '<td><span class="model-provider-url" title="' + escAttr(provider.base_url) + '">' + esc(provider.base_url) + '</span></td>' +
            '<td><span class="model-provider-protocol is-' + escAttr(provider.protocol.toLowerCase()) + '">' + esc(provider.protocol) + '</span></td>' +
            '<td><div class="model-provider-model-preview">' + modelPreview + '</div></td>' +
            '<td>' + esc(formatDateTime(provider.updated_at)) + '</td>' +
            '<td><div class="execution-row-actions">' +
                '<button class="btn-icon" type="button" data-provider-edit="' + escAttr(provider.id) + '" title="编辑模型供应商" aria-label="编辑模型供应商">' + icon('edit') + '</button>' +
                '<button class="btn-icon" type="button" data-provider-delete="' + escAttr(provider.id) + '" title="删除模型供应商" aria-label="删除模型供应商">' + icon('trash') + '</button>' +
            '</div></td></tr>';
    }).join('');
    body.querySelectorAll('[data-provider-edit]').forEach(function (button) {
        button.addEventListener('click', function () {
            viewModelProviderEditor(button.getAttribute('data-provider-edit'));
        });
    });
    body.querySelectorAll('[data-provider-delete]').forEach(function (button) {
        button.addEventListener('click', function () {
            deleteModelProvider(button.getAttribute('data-provider-delete'));
        });
    });
}

async function loadModelProviders() {
    try {
        var data = await API.get('/api/model-providers');
        modelProviderState.providers = data.providers || [];
        renderModelProviderRows();
    } catch (error) {
        showToast('加载模型供应商失败: ' + error.message, 'error');
    }
}

function viewModelProviders() {
    currentView = 'model-providers';
    modelProviderState.editingId = null;
    contentArea.innerHTML =
        '<section class="execution-page model-provider-page" aria-labelledby="model-provider-title">' +
            '<header class="execution-page-header"><div><h1 id="model-provider-title">模型管理</h1></div><span class="execution-count" id="model-provider-count">0 个供应商</span></header>' +
            '<div class="toolbar execution-toolbar" id="model-provider-toolbar">' +
                '<button class="btn btn-primary" id="btn-model-provider-add" type="button">' + icon('add') + '新增模型</button>' +
                '<button class="btn" id="btn-model-provider-refresh" type="button">' + icon('refresh') + '刷新</button>' +
                '<span class="toolbar-sep"></span>' +
                '<input class="input toolbar-search" id="model-provider-search" type="search" placeholder="搜索供应商、地址或模型..." aria-label="搜索模型供应商" />' +
            '</div>' +
            '<div class="table-wrap execution-table-wrap"><table class="table execution-table model-provider-table">' +
                '<thead><tr><th>供应商</th><th>BASE_URL</th><th>协议</th><th>模型</th><th>更新时间</th><th>操作</th></tr></thead>' +
                '<tbody id="model-provider-list-body"></tbody>' +
            '</table></div>' +
        '</section>';
    document.getElementById('btn-model-provider-add').addEventListener('click', function () {
        viewModelProviderEditor(null);
    });
    document.getElementById('btn-model-provider-refresh').addEventListener('click', loadModelProviders);
    document.getElementById('model-provider-search').addEventListener('input', function () {
        modelProviderState.query = this.value.trim().toLowerCase();
        renderModelProviderRows();
    });
    loadModelProviders();
}

function modelProviderEditorMarkup(provider) {
    var isEditing = Boolean(provider);
    return '<section class="model-provider-editor" aria-labelledby="model-provider-editor-title">' +
        '<header class="model-provider-editor-header">' +
            '<button class="btn btn-sm" id="model-provider-back" type="button">' + icon('back') + '返回</button>' +
            '<div class="model-provider-editor-heading"><span>MODEL PROVIDER</span><h1 id="model-provider-editor-title">' + (isEditing ? '编辑模型供应商' : '新增模型供应商') + '</h1></div>' +
            '<span class="model-connection-badge is-idle" id="model-connection-badge">未测试</span>' +
        '</header>' +
        '<form id="model-provider-form" class="model-provider-form">' +
            '<label class="model-provider-field"><span>供应商名称 <small>选填</small></span><input class="input" id="model-provider-name" maxlength="120" placeholder="例如：企业模型网关" value="' + escAttr(provider && provider.name || '') + '" /></label>' +
            '<label class="model-provider-field"><span>官网链接 <small>选填</small></span><input class="input" id="model-provider-website" type="url" maxlength="2048" placeholder="https://example.com" value="' + escAttr(provider && provider.website_url || '') + '" /></label>' +
            '<label class="model-provider-field"><span>API Key <b>*</b></span><span class="model-provider-key-wrap"><input class="input" id="model-provider-api-key" type="password" maxlength="4096" autocomplete="off" required placeholder="输入 API Key" value="' + escAttr(provider && provider.api_key || '') + '" /><button id="model-provider-key-toggle" type="button" aria-label="显示 API Key" title="显示 API Key">显示</button></span></label>' +
            '<label class="model-provider-field"><span>BASE_URL <b>*</b></span><input class="input" id="model-provider-base-url" type="url" maxlength="2048" required placeholder="https://api.example.com" value="' + escAttr(provider && provider.base_url || '') + '" /></label>' +
        '</form>' +
        '<div class="model-provider-actions">' +
            '<button id="model-provider-latency" type="button" class="btn" data-default-label="测速">测速</button>' +
            '<button id="model-provider-fetch" type="button" class="btn btn-primary" data-default-label="获取模型">获取模型</button>' +
            '<button id="model-provider-add-model" type="button" class="btn"' + (isEditing ? '' : ' disabled') + '>' + icon('add') + '添加模型</button>' +
            '<span class="model-provider-action-spacer"></span>' +
            '<button id="model-provider-save" type="button" class="btn btn-primary">保存</button>' +
        '</div>' +
        '<section class="model-provider-status" aria-label="连接状态">' +
            '<div class="model-provider-status-main"><span class="model-provider-status-mark" aria-hidden="true"></span><div><span>连接状态</span><strong id="model-provider-status-title">等待测试</strong></div></div>' +
            '<div class="model-provider-metric"><span>访问延迟</span><strong id="model-provider-latency-value">--</strong></div>' +
            '<div class="model-provider-metric model-provider-metric-wide"><span>协议 / 模型端点</span><strong id="model-provider-protocol-value">' + esc(provider && provider.protocol || '--') + '</strong><small id="model-provider-endpoint-value">' + esc(provider && provider.model_endpoint || '尚未获取模型') + '</small></div>' +
            '<div class="model-provider-metric"><span>发现模型</span><strong id="model-provider-model-count">0</strong></div>' +
        '</section>' +
        '<section id="model-provider-chooser" class="model-provider-chooser is-hidden" aria-label="添加模型">' +
            '<label><span>已发现模型</span><select class="input" id="model-provider-discovered" disabled><option value="">暂无可选模型</option></select></label>' +
            '<span class="model-provider-chooser-or">或</span>' +
            '<label><span>手工模型名称</span><input class="input" id="model-provider-manual" maxlength="200" placeholder="例如：deepseek-chat" /></label>' +
            '<button id="model-provider-confirm-model" type="button" class="btn btn-primary">确认添加</button>' +
        '</section>' +
        '<section class="model-provider-selected" aria-labelledby="model-provider-selected-title">' +
            '<header><h2 id="model-provider-selected-title">已添加模型</h2><span id="model-provider-selected-count">0 个</span></header>' +
            '<div id="model-provider-selected-list"></div>' +
        '</section>' +
    '</section>';
}

async function viewModelProviderEditor(providerId) {
    currentView = 'model-provider-editor';
    var provider = null;
    if (providerId) {
        try {
            provider = (await API.get('/api/model-providers/' + encodeURIComponent(providerId))).provider;
        } catch (error) {
            showToast('读取模型供应商失败: ' + error.message, 'error');
            return;
        }
    }
    modelProviderState.editingId = providerId;
    modelProviderState.discovered = [];
    modelProviderState.selected = provider ? (provider.models || []).slice() : [];
    modelProviderState.protocol = provider ? provider.protocol : null;
    modelProviderState.endpoint = provider ? provider.model_endpoint : null;
    contentArea.innerHTML = modelProviderEditorMarkup(provider);
    bindModelProviderEditor();
    renderSelectedProviderModels();
}

function bindModelProviderEditor() {
    document.getElementById('model-provider-back').addEventListener('click', viewModelProviders);
    document.getElementById('model-provider-key-toggle').addEventListener('click', toggleModelProviderKey);
    document.getElementById('model-provider-latency').addEventListener('click', testModelProviderLatency);
    document.getElementById('model-provider-fetch').addEventListener('click', fetchProviderModels);
    document.getElementById('model-provider-add-model').addEventListener('click', toggleProviderModelChooser);
    document.getElementById('model-provider-confirm-model').addEventListener('click', addSelectedProviderModel);
    document.getElementById('model-provider-save').addEventListener('click', saveModelProvider);
}

function toggleModelProviderKey() {
    var input = document.getElementById('model-provider-api-key');
    var button = document.getElementById('model-provider-key-toggle');
    var visible = input.type === 'text';
    input.type = visible ? 'password' : 'text';
    button.textContent = visible ? '显示' : '隐藏';
    button.setAttribute('aria-label', visible ? '显示 API Key' : '隐藏 API Key');
    button.title = button.getAttribute('aria-label');
}

function readModelProviderConnection() {
    var form = document.getElementById('model-provider-form');
    if (!form.reportValidity()) return null;
    return {
        api_key: document.getElementById('model-provider-api-key').value,
        base_url: document.getElementById('model-provider-base-url').value.trim(),
    };
}

function setModelProviderButtonBusy(button, busy, busyLabel) {
    button.disabled = busy;
    button.textContent = busy ? busyLabel : button.dataset.defaultLabel;
    button.classList.toggle('is-busy', busy);
}

function setModelProviderStatus(label, state, title) {
    var badge = document.getElementById('model-connection-badge');
    badge.textContent = label;
    badge.className = 'model-connection-badge is-' + state;
    document.getElementById('model-provider-status-title').textContent = title;
}

async function testModelProviderLatency() {
    var payload = readModelProviderConnection();
    if (!payload) return;
    var button = document.getElementById('model-provider-latency');
    setModelProviderButtonBusy(button, true, '测速中');
    setModelProviderStatus('测试中', 'idle', '正在访问 BASE_URL');
    try {
        var result = await API.post('/api/model-providers/latency', payload);
        document.getElementById('model-provider-latency-value').textContent = result.latency_ms + ' ms';
        setModelProviderStatus('可连接', 'success', '可达 · HTTP ' + result.status_code);
        showToast('测速完成：' + result.latency_ms + ' ms', 'success');
    } catch (error) {
        document.getElementById('model-provider-latency-value').textContent = '--';
        setModelProviderStatus('连接失败', 'error', '连接失败');
        showToast(error.message, 'error');
    } finally {
        setModelProviderButtonBusy(button, false, '');
    }
}

function renderDiscoveredProviderModels() {
    var select = document.getElementById('model-provider-discovered');
    select.innerHTML = '<option value="">' + (modelProviderState.discovered.length ? '选择一个模型' : '暂无可选模型') + '</option>' +
        modelProviderState.discovered.map(function (model) {
            var label = model.owned_by ? model.id + ' · ' + model.owned_by : model.id;
            return '<option value="' + escAttr(model.id) + '">' + esc(label) + '</option>';
        }).join('');
    select.disabled = modelProviderState.discovered.length === 0;
    document.getElementById('model-provider-model-count').textContent = String(modelProviderState.discovered.length);
}

async function fetchProviderModels() {
    var payload = readModelProviderConnection();
    if (!payload) return;
    var button = document.getElementById('model-provider-fetch');
    var addButton = document.getElementById('model-provider-add-model');
    setModelProviderButtonBusy(button, true, '获取中');
    addButton.disabled = true;
    setModelProviderStatus('探测中', 'idle', '正在探测模型协议');
    try {
        var result = await API.post('/api/model-providers/models', payload);
        modelProviderState.discovered = result.models || [];
        modelProviderState.protocol = result.protocol;
        modelProviderState.endpoint = result.endpoint;
        renderDiscoveredProviderModels();
        document.getElementById('model-provider-protocol-value').textContent = result.protocol;
        document.getElementById('model-provider-endpoint-value').textContent = result.endpoint;
        document.getElementById('model-provider-latency-value').textContent = result.latency_ms + ' ms';
        setModelProviderStatus('已连接', 'success', '模型列表已获取');
        showToast('已获取 ' + modelProviderState.discovered.length + ' 个模型', 'success');
    } catch (error) {
        modelProviderState.discovered = [];
        modelProviderState.protocol = null;
        modelProviderState.endpoint = null;
        renderDiscoveredProviderModels();
        document.getElementById('model-provider-protocol-value').textContent = '手工模式';
        document.getElementById('model-provider-endpoint-value').textContent = '自动获取失败';
        setModelProviderStatus('需手工配置', 'error', '可手工添加模型');
        showToast(error.message, 'error');
    } finally {
        setModelProviderButtonBusy(button, false, '');
        addButton.disabled = false;
    }
}

function toggleProviderModelChooser() {
    document.getElementById('model-provider-chooser').classList.toggle('is-hidden');
}

function addSelectedProviderModel() {
    var manual = document.getElementById('model-provider-manual').value.trim();
    var discovered = document.getElementById('model-provider-discovered').value;
    var modelId = manual || discovered;
    if (!modelId) {
        showToast('请选择或输入模型名称', 'error');
        return;
    }
    if (modelProviderState.selected.includes(modelId)) {
        showToast('该模型已经添加', 'error');
        return;
    }
    modelProviderState.selected.push(modelId);
    document.getElementById('model-provider-manual').value = '';
    document.getElementById('model-provider-discovered').value = '';
    renderSelectedProviderModels();
    showToast('已添加模型 ' + modelId, 'success');
}

function renderSelectedProviderModels() {
    var list = document.getElementById('model-provider-selected-list');
    document.getElementById('model-provider-selected-count').textContent = modelProviderState.selected.length + ' 个';
    if (!modelProviderState.selected.length) {
        list.innerHTML = '<div class="model-provider-empty">暂无已添加模型</div>';
        return;
    }
    list.innerHTML = modelProviderState.selected.map(function (model) {
        return '<div class="model-provider-selected-row"><span class="model-provider-model-mark">M</span><strong>' + esc(model) + '</strong>' +
            '<span>' + esc(modelProviderState.protocol || 'MANUAL') + '</span>' +
            '<button type="button" data-remove-provider-model="' + escAttr(model) + '" title="移除 ' + escAttr(model) + '" aria-label="移除 ' + escAttr(model) + '">×</button></div>';
    }).join('');
    list.querySelectorAll('[data-remove-provider-model]').forEach(function (button) {
        button.addEventListener('click', function () {
            var model = button.getAttribute('data-remove-provider-model');
            modelProviderState.selected = modelProviderState.selected.filter(function (item) { return item !== model; });
            renderSelectedProviderModels();
        });
    });
}

async function saveModelProvider() {
    var connection = readModelProviderConnection();
    if (!connection) return;
    if (!modelProviderState.selected.length) {
        showToast('至少添加一个模型', 'error');
        return;
    }
    var body = {
        name: document.getElementById('model-provider-name').value.trim() || null,
        website_url: document.getElementById('model-provider-website').value.trim() || null,
        api_key: connection.api_key,
        base_url: connection.base_url,
        protocol: modelProviderState.protocol || 'MANUAL',
        model_endpoint: modelProviderState.endpoint,
        models: modelProviderState.selected.slice(),
    };
    var button = document.getElementById('model-provider-save');
    button.disabled = true;
    try {
        if (modelProviderState.editingId) {
            await API.put('/api/model-providers/' + encodeURIComponent(modelProviderState.editingId), body);
        } else {
            await API.post('/api/model-providers', body);
        }
        showToast(modelProviderState.editingId ? '模型供应商已更新' : '模型供应商已创建', 'success');
        viewModelProviders();
    } catch (error) {
        showToast('保存模型供应商失败: ' + error.message, 'error');
        button.disabled = false;
    }
}

async function deleteModelProvider(providerId) {
    var provider = modelProviderState.providers.find(function (item) { return item.id === providerId; });
    if (!provider || !window.confirm('确定删除模型供应商“' + modelProviderName(provider) + '”吗？')) return;
    try {
        await API.del('/api/model-providers/' + encodeURIComponent(providerId));
        showToast('模型供应商已删除', 'success');
        await loadModelProviders();
    } catch (error) {
        showToast('删除模型供应商失败: ' + error.message, 'error');
    }
}
