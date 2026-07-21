(() => {
  const form = document.getElementById('provider-form');
  const apiKeyInput = document.getElementById('api-key');
  const baseUrlInput = document.getElementById('base-url');
  const toggleKeyButton = document.getElementById('toggle-key');
  const latencyButton = document.getElementById('latency-button');
  const modelsButton = document.getElementById('models-button');
  const addModelButton = document.getElementById('add-model-button');
  const confirmModelButton = document.getElementById('confirm-model-button');
  const chooser = document.getElementById('model-chooser');
  const modelSelect = document.getElementById('discovered-model-select');
  const manualModelInput = document.getElementById('manual-model');
  const selectedModelsElement = document.getElementById('selected-models');
  const toast = document.getElementById('toast');

  let discoveredModels = [];
  let selectedModels = [];
  let detectedProtocol = null;
  let toastTimer = null;

  // Never retain a credential restored by the browser after a reload.
  apiKeyInput.value = '';

  const refreshIcons = () => {
    if (window.lucide) {
      window.lucide.createIcons({attrs: {'stroke-width': 1.8}});
    }
  };

  const showToast = (message, type = 'success') => {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.toggle('is-error', type === 'error');
    toast.classList.add('is-visible');
    toastTimer = window.setTimeout(() => toast.classList.remove('is-visible'), 3200);
  };

  const setBadge = (label, state) => {
    const badge = document.getElementById('connection-badge');
    badge.className = `connection-badge is-${state}`;
    badge.querySelector('span').textContent = label;
  };

  const setButtonBusy = (button, busy) => {
    const label = button.querySelector('.button-label');
    if (!button.dataset.defaultLabel) {
      button.dataset.defaultLabel = label.textContent;
    }
    button.classList.toggle('is-loading', busy);
    button.disabled = busy;
    label.textContent = busy ? button.dataset.loadingLabel : button.dataset.defaultLabel;
  };

  const getPayload = () => {
    if (!form.reportValidity()) {
      return null;
    }
    return {
      api_key: apiKeyInput.value,
      base_url: baseUrlInput.value,
    };
  };

  const apiRequest = async (path, payload) => {
    const response = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : '请求失败';
      throw new Error(detail);
    }
    return data;
  };

  const renderDiscoveredModels = () => {
    modelSelect.replaceChildren();
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = discoveredModels.length ? '选择一个模型' : '暂无可选模型';
    modelSelect.appendChild(placeholder);
    discoveredModels.forEach((model) => {
      const option = document.createElement('option');
      option.value = model.id;
      option.textContent = model.owned_by ? `${model.id} · ${model.owned_by}` : model.id;
      modelSelect.appendChild(option);
    });
    modelSelect.disabled = discoveredModels.length === 0;
    document.getElementById('model-count').textContent = String(discoveredModels.length);
  };

  const renderSelectedModels = () => {
    selectedModelsElement.replaceChildren();
    document.getElementById('selected-count').textContent = `${selectedModels.length} 个`;
    if (!selectedModels.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      const icon = document.createElement('i');
      icon.dataset.lucide = 'box';
      const text = document.createElement('span');
      text.textContent = '暂无已添加模型';
      empty.append(icon, text);
      selectedModelsElement.appendChild(empty);
      refreshIcons();
      return;
    }

    selectedModels.forEach((model) => {
      const row = document.createElement('div');
      row.className = 'selected-model-row';

      const mark = document.createElement('span');
      mark.className = 'model-mark';
      const markIcon = document.createElement('i');
      markIcon.dataset.lucide = 'cpu';
      mark.appendChild(markIcon);

      const name = document.createElement('span');
      name.className = 'model-name';
      name.textContent = model.id;

      const source = document.createElement('span');
      source.className = 'model-source';
      source.textContent = model.source;

      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'remove-model';
      remove.title = `移除 ${model.id}`;
      remove.setAttribute('aria-label', `移除 ${model.id}`);
      const removeIcon = document.createElement('i');
      removeIcon.dataset.lucide = 'x';
      remove.appendChild(removeIcon);
      remove.addEventListener('click', () => {
        selectedModels = selectedModels.filter((item) => item.id !== model.id);
        renderSelectedModels();
      });

      row.append(mark, name, source, remove);
      selectedModelsElement.appendChild(row);
    });
    refreshIcons();
  };

  toggleKeyButton.addEventListener('click', () => {
    const visible = apiKeyInput.type === 'text';
    apiKeyInput.type = visible ? 'password' : 'text';
    toggleKeyButton.title = visible ? '显示 API Key' : '隐藏 API Key';
    toggleKeyButton.setAttribute('aria-label', toggleKeyButton.title);
    toggleKeyButton.replaceChildren();
    const icon = document.createElement('i');
    icon.dataset.lucide = visible ? 'eye' : 'eye-off';
    toggleKeyButton.appendChild(icon);
    refreshIcons();
  });

  latencyButton.addEventListener('click', async () => {
    const payload = getPayload();
    if (!payload) return;
    setButtonBusy(latencyButton, true);
    setBadge('测试中', 'idle');
    document.getElementById('status-title').textContent = '正在访问 BASE_URL';
    try {
      const result = await apiRequest('/api/latency', payload);
      document.getElementById('latency-value').textContent = `${result.latency_ms} ms`;
      document.getElementById('status-title').textContent = `可达 · HTTP ${result.status_code}`;
      setBadge('可连接', 'success');
      showToast(`测速完成：${result.latency_ms} ms`);
    } catch (error) {
      document.getElementById('latency-value').textContent = '--';
      document.getElementById('status-title').textContent = '连接失败';
      setBadge('连接失败', 'error');
      showToast(error.message, 'error');
    } finally {
      setButtonBusy(latencyButton, false);
    }
  });

  modelsButton.addEventListener('click', async () => {
    const payload = getPayload();
    if (!payload) return;
    setButtonBusy(modelsButton, true);
    addModelButton.disabled = true;
    setBadge('探测中', 'idle');
    document.getElementById('status-title').textContent = '正在探测模型协议';
    try {
      const result = await apiRequest('/api/models', payload);
      discoveredModels = result.models;
      detectedProtocol = result.protocol;
      renderDiscoveredModels();
      document.getElementById('protocol-value').textContent = result.protocol;
      document.getElementById('endpoint-value').textContent = result.endpoint;
      document.getElementById('latency-value').textContent = `${result.latency_ms} ms`;
      document.getElementById('status-title').textContent = '模型列表已获取';
      setBadge('已连接', 'success');
      addModelButton.disabled = false;
      showToast(`已获取 ${result.models.length} 个模型`);
    } catch (error) {
      discoveredModels = [];
      detectedProtocol = null;
      renderDiscoveredModels();
      document.getElementById('protocol-value').textContent = '手工模式';
      document.getElementById('endpoint-value').textContent = '自动获取失败';
      document.getElementById('status-title').textContent = '可手工添加模型';
      setBadge('需手工配置', 'error');
      addModelButton.disabled = false;
      showToast(error.message, 'error');
    } finally {
      setButtonBusy(modelsButton, false);
    }
  });

  addModelButton.addEventListener('click', () => {
    chooser.classList.toggle('is-hidden');
    const opening = !chooser.classList.contains('is-hidden');
    addModelButton.querySelector('.button-chevron').style.transform = opening ? 'rotate(180deg)' : '';
    if (opening) {
      (discoveredModels.length ? modelSelect : manualModelInput).focus();
    }
  });

  confirmModelButton.addEventListener('click', () => {
    const manualModel = manualModelInput.value.trim();
    const modelId = manualModel || modelSelect.value;
    if (!modelId) {
      showToast('请选择或输入模型名称', 'error');
      return;
    }
    if (selectedModels.some((model) => model.id === modelId)) {
      showToast('该模型已经添加', 'error');
      return;
    }
    const discovered = discoveredModels.find((model) => model.id === modelId);
    selectedModels.push({
      id: modelId,
      source: discovered ? (detectedProtocol || '自动发现') : '手工添加',
    });
    manualModelInput.value = '';
    modelSelect.value = '';
    renderSelectedModels();
    showToast(`已添加模型 ${modelId}`);
  });

  window.addEventListener('load', refreshIcons);
  renderSelectedModels();
})();
