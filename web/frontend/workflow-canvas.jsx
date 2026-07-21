import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import dagre from '@dagrejs/dagre';
import parseCurl from 'parse-curl';
import {Rnd} from 'react-rnd';
import {split as splitShellWords} from 'shellwords';
import {
    Background,
    BaseEdge,
    Controls,
    EdgeLabelRenderer,
    Handle,
    MarkerType,
    MiniMap,
    Position,
    ReactFlow,
    ReactFlowProvider,
    addEdge,
    getBezierPath,
    useEdgesState,
    useNodesState,
    useReactFlow,
} from '@xyflow/react';
import {
    ArrowLeft,
    Bot,
    BrainCircuit,
    Check,
    ChevronRight,
    CirclePlay,
    Clipboard,
    Code2,
    Copy,
    ExternalLink,
    Eye,
    Globe2,
    LayoutGrid,
    LoaderCircle,
    Play,
    Plus,
    Redo2,
    Save,
    ServerCog,
    Settings2,
    SlidersHorizontal,
    Sparkles,
    Trash2,
    Upload,
    WandSparkles,
    Undo2,
    X,
    Zap,
} from 'lucide-react';
import '@xyflow/react/dist/style.css';
import './workflow-canvas.css';

const NODE_TYPES = {
    START: {label: '开始', caption: 'START', icon: CirclePlay, color: '#16803c', executable: false},
    HTTP: {label: 'HTTP', caption: 'HTTP', icon: Globe2, color: '#2563eb', executable: false},
    AGENT: {label: 'AGENT', caption: 'AGENT', icon: Bot, color: '#0f766e', executable: true},
    LLM: {label: 'LLM', caption: 'LLM', icon: BrainCircuit, color: '#7048c6', executable: true},
    SCRIPT: {label: 'SCRIPT', caption: 'SCRIPT', icon: Code2, color: '#c56a12', executable: true},
    END: {label: '结束', caption: 'END', icon: Check, color: '#3f4b5f', executable: false},
};

const INSERTABLE_TYPES = ['HTTP', 'AGENT', 'LLM', 'SCRIPT'];
const NODE_STATUSES = ['PENDING', 'RUNNING', 'PASSED', 'FAILED'];
const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];
const HTTP_BODY_TYPES = ['none', 'form-data', 'x-www-form-urlencoded', 'raw', 'binary'];
const DEFAULT_MAIN_PY = 'response = inputs';

function nodeId(type) {
    return `${type}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function rowId() {
    return `row_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function formatExecutionDuration(value) {
    const durationMs = Math.max(0, Math.round(Number(value) || 0));
    return durationMs < 1000 ? `${durationMs}ms` : `${(durationMs / 1000).toFixed(1)}s`;
}

function cloneValue(value) {
    return JSON.parse(JSON.stringify(value));
}

function objectRows(value) {
    return Object.entries(value || {}).map(([key, item]) => ({id: rowId(), key, value: String(item)}));
}

function httpConfigFromTemplate(definition) {
    const config = definition?.http || {};
    return {
        ...defaultHttpConfig(),
        method: config.method || 'GET',
        url: config.url || '',
        headers: objectRows(config.headers),
        params: objectRows(config.params),
        bodyType: ({NONE: 'none', FORM_DATA: 'form-data', FORM_URLENCODED: 'x-www-form-urlencoded', RAW: 'raw', BINARY: 'binary'})[config.body_type] || 'none',
        bodyText: config.body == null ? '' : (typeof config.body === 'string' ? config.body : JSON.stringify(config.body, null, 2)),
    };
}

function objectFromRows(rows) {
    return Object.fromEntries(
        (rows || [])
            .filter((row) => String(row.key || '').trim())
            .map((row) => [String(row.key).trim(), String(row.value ?? '')]),
    );
}

function templateDefinitionFromNode(node) {
    const existing = node.data.templateDefinition
        ? cloneValue(node.data.templateDefinition)
        : {schema_version: 1, type: node.data.nodeType, inputs: [], outputs: [], config: {}};
    const definition = {
        ...existing,
        type: node.data.nodeType,
        inputs: existing.inputs || [],
        outputs: existing.outputs || [],
        config: existing.config || {},
    };
    if (node.data.nodeType !== 'HTTP') return definition;
    const httpConfig = {...defaultHttpConfig(), ...(node.data.httpConfig || {})};
    return {
        ...definition,
        execution_mode: existing.execution_mode || 'CONFIG',
        http: {
            method: httpConfig.method,
            url: httpConfig.url,
            headers: objectFromRows(httpConfig.headers),
            params: objectFromRows(httpConfig.params),
            body_type: ({none: 'NONE', 'form-data': 'FORM_DATA', 'x-www-form-urlencoded': 'FORM_URLENCODED', raw: 'RAW', binary: 'BINARY'})[httpConfig.bodyType] || 'NONE',
            body: httpConfig.bodyType === 'form-data' || httpConfig.bodyType === 'x-www-form-urlencoded'
                ? objectFromRows(httpConfig.bodyFields)
                : (httpConfig.bodyText || null),
        },
    };
}

function parameterDataText(value, pretty = false) {
    if (typeof value === 'string') return value;
    try {
        const serialized = JSON.stringify(value, null, pretty ? 2 : 0);
        return serialized === undefined ? String(value) : serialized;
    } catch (_error) {
        return String(value);
    }
}

function parameterDataSummary(value) {
    const text = parameterDataText(value).replace(/\s+/g, ' ').trim();
    return text.length > 180 ? `${text.slice(0, 177)}...` : text;
}

function emptyMappingRow() {
    return {id: rowId(), name: '', value: ''};
}

function emptyKeyValueRow(key = '', value = '') {
    return {id: rowId(), key, value};
}

function defaultHttpConfig() {
    return {
        method: 'POST',
        url: '',
        headers: [],
        params: [],
        bodyType: 'none',
        bodyText: '',
        bodyFields: [],
        binaryFileName: '',
    };
}

function optionValues(args, names) {
    const values = [];
    args.forEach((arg, index) => {
        if (names.includes(arg) && args[index + 1] !== undefined) values.push(args[index + 1]);
        const matchedName = names.find((name) => arg.startsWith(`${name}=`));
        if (matchedName) values.push(arg.slice(matchedName.length + 1));
    });
    return values;
}

function splitKeyValue(value, separator) {
    const index = value.indexOf(separator);
    return index < 0
        ? emptyKeyValueRow(value, '')
        : emptyKeyValueRow(value.slice(0, index), value.slice(index + separator.length));
}

function parseCurlRequest(command) {
    const source = command.trim().replace(/^\$\s+/, '');
    if (!/^curl(?:\.exe)?\s/i.test(source)) throw new Error('请输入有效的 cURL 命令');
    const args = splitShellWords(source);
    const normalized = source
        .replace(/--data-raw(?=\s|=)/g, '--data')
        .replace(/--data-binary(?=\s|=)/g, '--data')
        .replace(/--data-urlencode(?=\s|=)/g, '--data');
    const parsed = parseCurl(normalized);
    if (!parsed?.url) throw new Error('cURL 命令缺少有效的 HTTP URL');

    let url;
    try {
        url = new URL(parsed.url);
    } catch {
        throw new Error('cURL URL 无效');
    }
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('cURL 仅支持 HTTP 或 HTTPS URL');

    const params = Array.from(url.searchParams.entries(), ([key, value]) => emptyKeyValueRow(key, value));
    url.search = '';
    url.hash = '';

    const explicitHeaders = optionValues(args, ['-H', '--header'])
        .map((value) => splitKeyValue(value, ':'))
        .map((row) => ({...row, key: row.key.trim(), value: row.value.trim()}));
    const headers = [...explicitHeaders];
    Object.entries(parsed.header || {}).forEach(([key, value]) => {
        if (!headers.some((row) => row.key.toLowerCase() === key.toLowerCase())) {
            headers.push(emptyKeyValueRow(key, String(value)));
        }
    });

    const contentType = headers.find((row) => row.key.toLowerCase() === 'content-type')?.value.toLowerCase() || '';
    const formValues = optionValues(args, ['-F', '--form', '--form-string']);
    const binaryValues = optionValues(args, ['--data-binary']);
    const explicitMethods = optionValues(args, ['-X', '--request']);
    const compactMethod = args.find((arg) => /^-X[^-]/.test(arg))?.slice(2);
    const rawBody = parsed.body || '';
    let bodyType = 'none';
    let bodyText = '';
    let bodyFields = [];
    let binaryFileName = '';

    if (formValues.length) {
        bodyType = 'form-data';
        bodyFields = formValues.map((value) => splitKeyValue(value, '='));
    } else if (binaryValues.some((value) => value.startsWith('@'))) {
        bodyType = 'binary';
        binaryFileName = binaryValues.find((value) => value.startsWith('@')).slice(1);
    } else if (rawBody && contentType.includes('application/x-www-form-urlencoded')) {
        bodyType = 'x-www-form-urlencoded';
        bodyFields = Array.from(new URLSearchParams(rawBody).entries(), ([key, value]) => emptyKeyValueRow(key, value));
    } else if (rawBody) {
        bodyType = 'raw';
        bodyText = rawBody;
    }

    const explicitMethod = explicitMethods[explicitMethods.length - 1] || compactMethod;
    const inferredMethod = !explicitMethod && bodyType !== 'none' && parsed.method === 'GET'
        ? 'POST'
        : parsed.method;
    return {
        method: String(explicitMethod || inferredMethod || 'GET').toUpperCase(),
        url: url.toString(),
        headers,
        params,
        bodyType,
        bodyText,
        bodyFields,
        binaryFileName,
    };
}

function makeNode(type, position, overrides = {}) {
    const meta = NODE_TYPES[type];
    return {
        id: nodeId(type),
        type: 'workflowNode',
        position,
        data: {
            nodeType: type,
            label: meta.label,
            description: '',
            status: 'PENDING',
            executionDurationMs: 0,
            retryCount: 0,
            retryInterval: 0,
            delayExecution: 0,
            repeatExecution: 1,
            outputVariables: [emptyMappingRow()],
            parameterRecords: [],
            ...(type === 'HTTP' ? {httpConfig: defaultHttpConfig()} : {}),
            ...(meta.executable ? {mainPy: DEFAULT_MAIN_PY} : {}),
            ...overrides,
        },
    };
}

function makeEdge(source, target, overrides = {}) {
    return {
        id: `edge_${source}_${target}_${Math.random().toString(36).slice(2, 7)}`,
        source,
        target,
        type: 'insertable',
        markerEnd: {type: MarkerType.ArrowClosed, width: 16, height: 16, color: '#9aa8ba'},
        ...overrides,
    };
}

function layoutGraph(nodes, edges) {
    const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
    graph.setGraph({rankdir: 'LR', ranksep: 78, nodesep: 56, marginx: 40, marginy: 40});
    nodes.forEach((node) => graph.setNode(node.id, {width: 236, height: 112}));
    edges.forEach((edge) => graph.setEdge(edge.source, edge.target));
    dagre.layout(graph);
    return nodes.map((node) => {
        const point = graph.node(node.id);
        return {
            ...node,
            position: {x: point.x - 118, y: point.y - 56},
        };
    });
}

function initialGraph() {
    const start = makeNode('START', {x: 60, y: 280}, {label: '开始'});
    const request = makeNode('HTTP', {x: 360, y: 280}, {label: '调用业务接口'});
    const agent = makeNode('AGENT', {x: 675, y: 280}, {label: '执行企业 Agent'});
    const llm = makeNode('LLM', {x: 990, y: 100}, {label: '模型质量判断'});
    const script = makeNode('SCRIPT', {x: 990, y: 420}, {label: '规则校验'});
    const end = makeNode('END', {x: 1305, y: 260}, {label: '完成'});
    return {
        nodes: [start, request, agent, llm, script, end],
        edges: [
            makeEdge(start.id, request.id),
            makeEdge(request.id, agent.id),
            makeEdge(agent.id, llm.id),
            makeEdge(agent.id, script.id),
            makeEdge(llm.id, end.id),
            makeEdge(script.id, end.id),
        ],
    };
}

function WorkflowNode({data, selected}) {
    const meta = NODE_TYPES[data.nodeType] || NODE_TYPES.SCRIPT;
    const Icon = meta.icon;
    const status = NODE_STATUSES.includes(data.status) ? data.status : 'PENDING';
    const statusClass = status.toLowerCase();
    const executionDuration = formatExecutionDuration(data.executionDurationMs);
    return (
        <article className={`wf-node ${selected ? 'is-selected' : ''} is-${statusClass}`} style={{'--node-accent': meta.color}}>
            {data.nodeType !== 'START' && <Handle type="target" position={Position.Left} className="wf-handle" />}
            <header className="wf-node-header">
                <span className="wf-node-icon"><Icon size={17} strokeWidth={2} /></span>
                <span className="wf-node-caption">{meta.caption}</span>
                <span className="wf-node-actions">
                    <button type="button" title="运行" aria-label={`运行 ${data.label}`} onClick={(event) => {event.stopPropagation(); data.onRun?.();}}><Play size={13} /></button>
                </span>
            </header>
            <strong className="wf-node-title">{data.label}</strong>
            <footer className="wf-node-footer">
                <span className={`wf-node-status is-${statusClass}`}><i />{status}</span>
                <span className="wf-node-meta">
                    {meta.executable && <span className="wf-node-runtime">Python</span>}
                    {data.savedAt && !data.isDirty && <span className="wf-node-saved-state"><Check size={10} />已保存</span>}
                    <span className={`wf-node-execution is-${statusClass}`} aria-label={`执行耗时 ${executionDuration}`}>
                        <LoaderCircle className="wf-execution-spinner" size={12} />
                        <span>{executionDuration}</span>
                    </span>
                </span>
            </footer>
            {data.nodeType !== 'END' && <Handle type="source" position={Position.Right} className="wf-handle" />}
        </article>
    );
}

function NodePicker({onSelect, compact = false}) {
    const types = INSERTABLE_TYPES;
    return (
        <div className={`wf-node-picker ${compact ? 'is-compact' : ''}`} role="menu">
            {types.map((type) => {
                const meta = NODE_TYPES[type];
                const Icon = meta.icon;
                return (
                    <button type="button" key={type} onClick={() => onSelect(type)} role="menuitem">
                        <span style={{'--picker-accent': meta.color}}><Icon size={16} /></span>
                        <span><strong>{meta.label}</strong>{meta.caption !== meta.label && <small>{meta.caption}</small>}</span>
                    </button>
                );
            })}
        </div>
    );
}

function InsertableEdge({id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, data}) {
    const [path, labelX, labelY] = getBezierPath({sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition});
    return (
        <>
            <BaseEdge id={id} path={path} markerEnd={markerEnd} className="wf-edge-path" />
            <EdgeLabelRenderer>
                <div className="wf-edge-action" style={{transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`}}>
                    <button type="button" className="wf-edge-plus nodrag nopan" title="快速插入节点" aria-label="快速插入节点" onClick={(event) => {event.stopPropagation(); data.onToggleInsert(id);}}>
                        <Plus size={14} />
                    </button>
                    {data.insertOpen && (
                        <div className="wf-edge-picker nodrag nopan">
                            <NodePicker compact onSelect={(type) => data.onInsert(id, type)} />
                        </div>
                    )}
                </div>
            </EdgeLabelRenderer>
        </>
    );
}

const nodeTypes = {workflowNode: WorkflowNode};
const edgeTypes = {insertable: InsertableEdge};

function ContextMenu({menu, canPaste, canPublish, onAction, onAdd}) {
    const [submenuOpen, setSubmenuOpen] = useState(false);
    useEffect(() => setSubmenuOpen(false), [menu?.kind, menu?.x, menu?.y]);
    if (!menu) return null;
    if (menu.kind === 'node') {
        return (
            <div className="wf-context-menu" style={{left: menu.x, top: menu.y}} role="menu" data-testid="node-context-menu">
                <button type="button" onClick={() => onAction('run-node')}><Play size={15} /><span>运行此步骤</span></button>
                <button type="button" onClick={() => onAction('copy-node')}><Copy size={15} /><span>拷贝</span></button>
                {canPublish && <button type="button" onClick={() => onAction('publish-node')}><Upload size={15} /><span>发布为工具模板</span></button>}
                <div className="wf-menu-separator" />
                <button type="button" className="is-danger" onClick={() => onAction('delete-node')}><Trash2 size={15} /><span>删除</span></button>
            </div>
        );
    }
    return (
        <div className="wf-context-menu" style={{left: menu.x, top: menu.y}} role="menu" data-testid="pane-context-menu">
            <div className={`wf-context-submenu-trigger ${submenuOpen ? 'is-open' : ''}`}>
                <button type="button" aria-expanded={submenuOpen} onClick={() => setSubmenuOpen((open) => !open)}><Plus size={15} /><span>添加节点</span><ChevronRight size={14} /></button>
                <div className="wf-context-submenu"><NodePicker onSelect={onAdd} /></div>
            </div>
            <button type="button" onClick={() => onAction('test-run')}><Zap size={15} /><span>测试运行</span></button>
            <button type="button" disabled={!canPaste} onClick={() => onAction('paste-node')}><Clipboard size={15} /><span>粘贴节点</span></button>
        </div>
    );
}

function Inspector({node, initialTab = 'settings', onChange, onRun, onSave, onClose}) {
    const [tab, setTab] = useState(initialTab);
    const [retryOpen, setRetryOpen] = useState(false);
    const [mappingOpen, setMappingOpen] = useState(false);
    const [selectedParameterIndex, setSelectedParameterIndex] = useState(null);
    const [curlPanelOpen, setCurlPanelOpen] = useState(false);
    const [curlText, setCurlText] = useState('');
    const [curlError, setCurlError] = useState('');
    const [headersOpen, setHeadersOpen] = useState(true);
    const [paramsOpen, setParamsOpen] = useState(true);
    const [bodyMessage, setBodyMessage] = useState('');
    useEffect(() => {
        setCurlPanelOpen(false);
        setCurlText('');
        setCurlError('');
        setHeadersOpen(true);
        setParamsOpen(true);
        setBodyMessage('');
        setSelectedParameterIndex(null);
    }, [node?.id]);
    if (!node) return null;
    const meta = NODE_TYPES[node.data.nodeType] || NODE_TYPES.SCRIPT;
    const Icon = meta.icon;
    const isHttp = node.data.nodeType === 'HTTP';
    const httpConfig = {...defaultHttpConfig(), ...(node.data.httpConfig || {})};
    const width = Math.min(Math.round(760 * 1.4), window.innerWidth - 56);
    const height = Math.min(Math.round(640 * 1.4), window.innerHeight - 58 - 28);
    const legacyOutputVariable = node.data.outputVariable
        || (Array.isArray(node.data.variables) ? node.data.variables[0] : null)
        || emptyMappingRow();
    const outputVariables = Array.isArray(node.data.outputVariables) && node.data.outputVariables.length
        ? node.data.outputVariables
        : [legacyOutputVariable];
    const parameterRecords = Array.isArray(node.data.parameterRecords)
        ? node.data.parameterRecords
        : [];
    const selectedParameter = selectedParameterIndex === null
        ? null
        : parameterRecords[selectedParameterIndex] || null;
    const resizeHandleClasses = {
        top: 'wf-resize-handle wf-resize-top',
        right: 'wf-resize-handle wf-resize-right',
        bottom: 'wf-resize-handle wf-resize-bottom',
        left: 'wf-resize-handle wf-resize-left',
        topRight: 'wf-resize-handle wf-resize-ne',
        bottomRight: 'wf-resize-handle wf-resize-se',
        bottomLeft: 'wf-resize-handle wf-resize-sw',
        topLeft: 'wf-resize-handle wf-resize-nw',
    };
    const updateHttpConfig = (patch) => onChange({httpConfig: {...httpConfig, ...patch}});
    const updateHttpRow = (collection, id, patch) => {
        updateHttpConfig({
            [collection]: httpConfig[collection].map((row) => row.id === id ? {...row, ...patch} : row),
        });
    };
    const addHttpRow = (collection) => updateHttpConfig({
        [collection]: httpConfig[collection].concat(emptyKeyValueRow()),
    });
    const removeHttpRow = (collection, id) => updateHttpConfig({
        [collection]: httpConfig[collection].filter((row) => row.id !== id),
    });
    const updateOutputVariable = (id, patch) => onChange({
        outputVariables: outputVariables.map((row) => row.id === id ? {...row, ...patch} : row),
    });
    const addOutputVariable = () => onChange({
        outputVariables: outputVariables.concat(emptyMappingRow()),
    });
    const removeOutputVariable = (id) => {
        const remaining = outputVariables.filter((row) => row.id !== id);
        onChange({outputVariables: remaining.length ? remaining : [emptyMappingRow()]});
    };
    const httpKeyValueSection = (label, collection, open, setOpen) => (
        <section className="wf-http-kv-section">
            <div className="wf-http-kv-heading">
                <button type="button" className="wf-http-collapse-button" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
                    <ChevronRight className={open ? 'is-open' : ''} size={14} /><strong>{label}</strong>
                </button>
                <span>key</span>
                <span>value</span>
                <button type="button" className="wf-inline-icon-button" onClick={() => {setOpen(true); addHttpRow(collection);}} title={`新增 ${label}`} aria-label={`新增 ${label}`}><Plus size={14} /></button>
            </div>
            {open && (
                <div className="wf-http-kv-rows">
                    {httpConfig[collection].map((row, index) => (
                        <div className="wf-http-kv-row" key={row.id}>
                            <span aria-hidden="true" />
                            <input aria-label={`${label} key ${index + 1}`} value={row.key} onChange={(event) => updateHttpRow(collection, row.id, {key: event.target.value})} />
                            <input aria-label={`${label} value ${index + 1}`} value={row.value} onChange={(event) => updateHttpRow(collection, row.id, {value: event.target.value})} />
                            <button type="button" className="wf-inline-icon-button is-danger" onClick={() => removeHttpRow(collection, row.id)} title={`删除 ${label}`} aria-label={`删除 ${label} ${index + 1}`}><Trash2 size={14} /></button>
                        </div>
                    ))}
                </div>
            )}
        </section>
    );
    const applyCurlImport = () => {
        try {
            const imported = parseCurlRequest(curlText);
            onChange({httpConfig: imported});
            setCurlError('');
            setCurlPanelOpen(false);
        } catch (error) {
            setCurlError(error instanceof Error ? error.message : 'cURL 导入失败');
        }
    };
    const beautifyJsonBody = () => {
        try {
            const formatted = JSON.stringify(JSON.parse(httpConfig.bodyText), null, 2);
            updateHttpConfig({bodyText: formatted});
            setBodyMessage('');
        } catch (error) {
            setBodyMessage(`JSON 格式错误：${error instanceof Error ? error.message : '无法解析'}`);
        }
    };
    const bodyFieldRows = () => (
        <div className="wf-http-body-fields">
            <div className="wf-http-kv-heading is-body">
                <span />
                <span>key</span>
                <span>value</span>
                <button type="button" className="wf-inline-icon-button" onClick={() => addHttpRow('bodyFields')} title="新增 Body 字段" aria-label="新增 Body 字段"><Plus size={14} /></button>
            </div>
            {httpConfig.bodyFields.map((row, index) => (
                <div className="wf-http-kv-row" key={row.id}>
                    <span aria-hidden="true" />
                    <input aria-label={`Body key ${index + 1}`} value={row.key} onChange={(event) => updateHttpRow('bodyFields', row.id, {key: event.target.value})} />
                    <input aria-label={`Body value ${index + 1}`} value={row.value} onChange={(event) => updateHttpRow('bodyFields', row.id, {value: event.target.value})} />
                    <button type="button" className="wf-inline-icon-button is-danger" onClick={() => removeHttpRow('bodyFields', row.id)} title="删除 Body 字段" aria-label={`删除 Body 字段 ${index + 1}`}><Trash2 size={14} /></button>
                </div>
            ))}
        </div>
    );
    return (
        <Rnd
            className="wf-node-editor-rnd"
            default={{x: (window.innerWidth - width) / 2, y: (window.innerHeight - 58 - height) / 2, width, height}}
            minWidth={560}
            minHeight={420}
            maxWidth="calc(100% - 28px)"
            maxHeight="calc(100% - 28px)"
            bounds="parent"
            dragHandleClassName="wf-node-editor-drag-handle"
            cancel="button,input,textarea,.wf-inspector-tabs,.wf-inspector-body"
            resizeHandleClasses={resizeHandleClasses}
        >
            <aside className="wf-inspector" aria-label="节点配置">
                <header className="wf-node-editor-drag-handle">
                    <span className="wf-inspector-icon" style={{'--node-accent': meta.color}}><Icon size={18} /></span>
                    <div className="wf-inspector-title"><strong>{node.data.label}</strong><small>{meta.caption}</small></div>
                    <div className="wf-inspector-actions">
                        <button type="button" onClick={onRun} title="运行" aria-label="运行当前节点"><Play size={15} /></button>
                        <button type="button" className={node.data.savedAt && !node.data.isDirty ? 'is-saved' : ''} onClick={onSave} title={node.data.savedAt && !node.data.isDirty ? `已保存 ${node.data.savedAt}` : '保存'} aria-label="保存当前节点"><Save size={15} /></button>
                        <button type="button" onClick={onClose} title="关闭" aria-label="关闭"><X size={17} /></button>
                    </div>
                </header>
                <div className="wf-inspector-tabs">
                    <button type="button" className={tab === 'settings' ? 'is-active' : ''} onClick={() => setTab('settings')}>设置</button>
                    {meta.executable && <button type="button" className={tab === 'code' ? 'is-active' : ''} onClick={() => setTab('code')}>代码</button>}
                    <button type="button" className={tab === 'parameters' ? 'is-active' : ''} onClick={() => setTab('parameters')}>参数</button>
                    <button type="button" className={tab === 'logs' ? 'is-active' : ''} onClick={() => setTab('logs')}>日志</button>
                </div>
                {tab === 'settings' ? (
                    <div className="wf-inspector-body">
                        <div className="wf-editor-form-grid">
                            <label><span>名称</span><input value={node.data.label} onChange={(event) => onChange({label: event.target.value})} /></label>
                            <label><span>说明</span><input value={node.data.description || ''} onChange={(event) => onChange({description: event.target.value})} placeholder="添加节点说明" /></label>
                            {isHttp && (
                                <section className="wf-http-api-section wf-editor-full-row">
                                    <div className="wf-http-api-row">
                                        <strong>API</strong>
                                        <select aria-label="请求方式" value={httpConfig.method} onChange={(event) => updateHttpConfig({method: event.target.value})}>
                                            {!HTTP_METHODS.includes(httpConfig.method) && <option value={httpConfig.method}>{httpConfig.method}</option>}
                                            {HTTP_METHODS.map((method) => <option key={method} value={method}>{method}</option>)}
                                        </select>
                                        <input aria-label="请求 URL" value={httpConfig.url} onChange={(event) => updateHttpConfig({url: event.target.value})} placeholder="https://" />
                                        <button type="button" className="wf-http-import-button" title="导入 cURL" aria-label="导入 cURL" aria-expanded={curlPanelOpen} onClick={() => {setCurlPanelOpen((open) => !open); setCurlError('');}}><Upload size={15} /></button>
                                    </div>
                                    {curlPanelOpen && (
                                        <div className="wf-curl-import-panel">
                                            <textarea aria-label="cURL 命令" value={curlText} onChange={(event) => {setCurlText(event.target.value); setCurlError('');}} spellCheck="false" placeholder="curl https://api.example.com" />
                                            <div className="wf-curl-import-actions">
                                                {curlError && <span role="alert">{curlError}</span>}
                                                <button type="button" onClick={() => setCurlPanelOpen(false)}>取消</button>
                                                <button type="button" className="is-primary" onClick={applyCurlImport}>应用</button>
                                            </div>
                                        </div>
                                    )}
                                    {httpKeyValueSection('HEADERS', 'headers', headersOpen, setHeadersOpen)}
                                    {httpKeyValueSection('PARAMS', 'params', paramsOpen, setParamsOpen)}
                                    <section className="wf-http-body-section">
                                        <div className="wf-http-body-heading">
                                            <strong>BODY</strong>
                                            <div className="wf-http-body-types" role="radiogroup" aria-label="Body 类型">
                                                {HTTP_BODY_TYPES.map((type) => (
                                                    <label key={type}>
                                                        <input type="radio" name={`http-body-${node.id}`} value={type} checked={httpConfig.bodyType === type} onChange={() => {updateHttpConfig({bodyType: type}); setBodyMessage('');}} />
                                                        <i />
                                                        <span>{type}</span>
                                                    </label>
                                                ))}
                                            </div>
                                        </div>
                                        {(httpConfig.bodyType === 'form-data' || httpConfig.bodyType === 'x-www-form-urlencoded') && bodyFieldRows()}
                                        {httpConfig.bodyType === 'raw' && (
                                            <div className="wf-http-code-editor">
                                                <div className="wf-http-code-toolbar">
                                                    <span>JSON</span>
                                                    <button type="button" onClick={beautifyJsonBody} title="格式化 JSON"><WandSparkles size={13} />Beautify</button>
                                                </div>
                                                <textarea aria-label="Raw Body" value={httpConfig.bodyText} onChange={(event) => {updateHttpConfig({bodyText: event.target.value}); setBodyMessage('');}} spellCheck="false" />
                                                {bodyMessage && <span className="wf-http-body-error" role="alert">{bodyMessage}</span>}
                                            </div>
                                        )}
                                        {httpConfig.bodyType === 'binary' && (
                                            <label className="wf-http-binary-input">
                                                <span>文件</span>
                                                <input type="file" aria-label="选择 Binary 文件" onChange={(event) => updateHttpConfig({binaryFileName: event.target.files?.[0]?.name || ''})} />
                                                {httpConfig.binaryFileName && <small>{httpConfig.binaryFileName}</small>}
                                            </label>
                                        )}
                                    </section>
                                </section>
                            )}
                            <section className="wf-config-section wf-editor-full-row">
                                <div className="wf-config-title"><Settings2 size={15} /><strong>运行配置</strong></div>
                                <button type="button" aria-expanded={retryOpen} onClick={() => setRetryOpen((open) => !open)}><span>超时与重试</span><ChevronRight className={retryOpen ? 'is-open' : ''} size={15} /></button>
                                {retryOpen && (
                                    <div className="wf-config-panel wf-retry-grid">
                                        <label><span>重试次数</span><input type="number" min="0" value={node.data.retryCount ?? 0} onChange={(event) => onChange({retryCount: Number(event.target.value)})} /></label>
                                        <label><span>重试间隔</span><input type="number" min="0" value={node.data.retryInterval ?? 0} onChange={(event) => onChange({retryInterval: Number(event.target.value)})} /></label>
                                        <label><span>延迟执行</span><input type="number" min="0" value={node.data.delayExecution ?? 0} onChange={(event) => onChange({delayExecution: Number(event.target.value)})} /></label>
                                        <label><span>重复执行</span><input type="number" min="1" value={node.data.repeatExecution ?? 1} onChange={(event) => onChange({repeatExecution: Number(event.target.value)})} /></label>
                                    </div>
                                )}
                                <button type="button" aria-expanded={mappingOpen} onClick={() => setMappingOpen((open) => !open)}><span>输出变量</span><ChevronRight className={mappingOpen ? 'is-open' : ''} size={15} /></button>
                                {mappingOpen && (
                                    <div className="wf-config-panel wf-output-variable-list">
                                        {outputVariables.map((row, index) => (
                                            <div className="wf-output-variable-row" key={row.id}>
                                                <label><span>变量名</span><input aria-label={`输出变量名 ${index + 1}`} value={row.name} onChange={(event) => updateOutputVariable(row.id, {name: event.target.value})} /></label>
                                                <label><span>变量</span><input aria-label={`输出变量 ${index + 1}`} value={row.value} onChange={(event) => updateOutputVariable(row.id, {value: event.target.value})} /></label>
                                                {index === 0 ? (
                                                    <button type="button" className="wf-inline-icon-button" onClick={addOutputVariable} title="添加输出变量" aria-label="添加输出变量"><Plus size={15} /></button>
                                                ) : (
                                                    <button type="button" className="wf-inline-icon-button is-danger" onClick={() => removeOutputVariable(row.id)} title="删除输出变量" aria-label={`删除输出变量 ${index + 1}`}><Trash2 size={15} /></button>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </section>
                        </div>
                    </div>
                ) : tab === 'code' ? (
                    <div className="wf-inspector-body wf-code-panel">
                        <div className="wf-code-meta"><span>main.py</span><span>Python</span></div>
                        <textarea aria-label="main.py" spellCheck="false" value={node.data.mainPy ?? DEFAULT_MAIN_PY} onChange={(event) => onChange({mainPy: event.target.value})} />
                    </div>
                ) : tab === 'parameters' ? (
                    <div className="wf-inspector-body wf-parameter-panel">
                        <div className="wf-parameter-table" role="table" aria-label="节点运行参数">
                            <div className="wf-parameter-row wf-parameter-heading" role="row">
                                <span role="columnheader">source</span>
                                <span role="columnheader">name</span>
                                <span role="columnheader">data</span>
                            </div>
                            {parameterRecords.map((record, index) => (
                                <div className="wf-parameter-row" role="row" key={record.id || `${record.source}:${record.name}:${index}`}>
                                    <code role="cell">{record.source || '—'}</code>
                                    <span role="cell">{record.name || '—'}</span>
                                    <div className="wf-parameter-data-cell" role="cell">
                                        <code title={parameterDataSummary(record.data)}>{parameterDataSummary(record.data) || '—'}</code>
                                        <button type="button" onClick={() => setSelectedParameterIndex(index)} title="查看完整数据" aria-label={`查看 ${record.source || '未知来源'} ${record.name || '未命名参数'} 完整数据`}><Eye size={14} /></button>
                                    </div>
                                </div>
                            ))}
                            {!parameterRecords.length && <div className="wf-parameter-empty">当前节点尚无运行参数</div>}
                        </div>
                        {selectedParameter && (
                            <section className="wf-parameter-detail" aria-label="参数完整数据">
                                <header>
                                    <div><strong>{selectedParameter.source || '未知来源'}</strong><span>{selectedParameter.name || '未命名参数'}</span></div>
                                    <div>
                                        {selectedParameter.artifact?.href && (
                                            <a href={selectedParameter.artifact.href} target="_blank" rel="noreferrer" title="打开完整 Artifact"><ExternalLink size={14} />Artifact</a>
                                        )}
                                        <button type="button" onClick={() => setSelectedParameterIndex(null)} title="关闭详情" aria-label="关闭参数详情"><X size={15} /></button>
                                    </div>
                                </header>
                                <pre>{parameterDataText(selectedParameter.data, true)}</pre>
                            </section>
                        )}
                    </div>
                ) : (
                    <div className="wf-inspector-body wf-node-log-panel">
                        {(node.data.runHistory || []).length ? node.data.runHistory.map((entry) => (
                            <div key={entry.id}><time>{entry.time}</time><strong>{entry.status}</strong><span>{entry.message}</span></div>
                        )) : <div className="wf-node-log-empty">暂无日志</div>}
                    </div>
                )}
            </aside>
        </Rnd>
    );
}

function WorkflowStudio({options}) {
    const graph = useMemo(initialGraph, []);
    const [nodes, setNodes, onNodesChange] = useNodesState(graph.nodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(graph.edges);
    const [selectedNodeIds, setSelectedNodeIds] = useState([]);
    const [editorNodeId, setEditorNodeId] = useState(null);
    const [contextMenu, setContextMenu] = useState(null);
    const [insertEdgeId, setInsertEdgeId] = useState(null);
    const [clipboard, setClipboard] = useState(null);
    const [headerPanel, setHeaderPanel] = useState(null);
    const [toolTemplates, setToolTemplates] = useState([]);
    const [templateLoadState, setTemplateLoadState] = useState('idle');
    const [marquee, setMarquee] = useState(null);
    const [globalVariables, setGlobalVariables] = useState([emptyMappingRow()]);
    const [nodeSaveNotice, setNodeSaveNotice] = useState(null);
    const [workflowName, setWorkflowName] = useState(options.name || '未命名工作流');
    const [saveState, setSaveState] = useState('本地草稿');
    const timers = useRef([]);
    const pasteSequence = useRef(0);
    const marqueeRef = useRef(null);
    const initialLayoutDone = useRef(false);
    const undoStack = useRef([]);
    const redoStack = useRef([]);
    const [historyTick, setHistoryTick] = useState(0);
    const {screenToFlowPosition, fitView} = useReactFlow();

    const closeMenus = useCallback(() => {
        setContextMenu(null);
        setInsertEdgeId(null);
    }, []);

    const recordHistory = useCallback(() => {
        undoStack.current.push({nodes: cloneValue(nodes), edges: cloneValue(edges)});
        if (undoStack.current.length > 50) undoStack.current.shift();
        redoStack.current = [];
        setHistoryTick((value) => value + 1);
    }, [edges, nodes]);

    const undo = useCallback(() => {
        const previous = undoStack.current.pop();
        if (!previous) return;
        redoStack.current.push({nodes: cloneValue(nodes), edges: cloneValue(edges)});
        setNodes(previous.nodes);
        setEdges(previous.edges);
        setEditorNodeId((current) => previous.nodes.some((node) => node.id === current) ? current : null);
        closeMenus();
        setHistoryTick((value) => value + 1);
    }, [closeMenus, edges, nodes, setEdges, setNodes]);

    const redo = useCallback(() => {
        const next = redoStack.current.pop();
        if (!next) return;
        undoStack.current.push({nodes: cloneValue(nodes), edges: cloneValue(edges)});
        setNodes(next.nodes);
        setEdges(next.edges);
        setEditorNodeId((current) => next.nodes.some((node) => node.id === current) ? current : null);
        closeMenus();
        setHistoryTick((value) => value + 1);
    }, [closeMenus, edges, nodes, setEdges, setNodes]);

    const addNodeAt = useCallback((type, position) => {
        recordHistory();
        const next = {...makeNode(type, position), selected: true};
        setNodes((current) => current.map((node) => ({...node, selected: false})).concat(next));
        closeMenus();
        return next;
    }, [closeMenus, recordHistory, setNodes]);

    const openTemplatePanel = useCallback(async () => {
        if (headerPanel === 'templates') {
            setHeaderPanel(null);
            return;
        }
        setHeaderPanel('templates');
        setTemplateLoadState('loading');
        try {
            const response = await fetch('/api/tool-templates');
            if (!response.ok) throw new Error('工具模板加载失败');
            const data = await response.json();
            setToolTemplates(data.templates || []);
            setTemplateLoadState('ready');
        } catch (error) {
            setToolTemplates([]);
            setTemplateLoadState('error');
        }
    }, [headerPanel]);

    const addTemplateNode = useCallback((template) => {
        const type = template?.manifest?.type;
        if (!INSERTABLE_TYPES.includes(type)) return;
        const position = screenToFlowPosition({x: window.innerWidth / 2, y: window.innerHeight / 2});
        const definition = cloneValue(template.definition);
        const overrides = {
            label: template.manifest.name,
            description: template.manifest.description || '',
            templateDefinition: definition,
            mainPy: template.main_py,
            ...(type === 'HTTP' ? {httpConfig: httpConfigFromTemplate(definition)} : {}),
        };
        recordHistory();
        const next = {...makeNode(type, position, overrides), selected: true};
        setNodes((current) => current.map((node) => ({...node, selected: false})).concat(next));
        setHeaderPanel(null);
    }, [recordHistory, screenToFlowPosition, setNodes]);

    const runNode = useCallback((id) => {
        const startedAt = new Date().toLocaleTimeString('zh-CN', {hour12: false});
        const startedAtMs = Date.now();
        const executionId = rowId();
        setNodes((current) => current.map((node) => node.id === id ? {
            ...node,
            data: {
                ...node.data,
                status: 'RUNNING',
                executionId,
                executionDurationMs: 0,
                runHistory: (node.data.runHistory || []).concat({id: rowId(), time: startedAt, status: 'RUNNING', message: '开始运行'}),
            },
        } : node));
        const elapsedTimer = window.setInterval(() => {
            const executionDurationMs = Date.now() - startedAtMs;
            setNodes((current) => current.map((node) => node.id === id && node.data.executionId === executionId ? {
                ...node,
                data: {...node.data, executionDurationMs},
            } : node));
        }, 100);
        const timer = window.setTimeout(() => {
            window.clearInterval(elapsedTimer);
            const finishedAt = new Date().toLocaleTimeString('zh-CN', {hour12: false});
            const executionDurationMs = Date.now() - startedAtMs;
            setNodes((current) => current.map((node) => node.id === id && node.data.executionId === executionId ? {
                ...node,
                data: {
                    ...node.data,
                    status: 'PASSED',
                    executionId: null,
                    executionDurationMs,
                    runHistory: (node.data.runHistory || []).concat({id: rowId(), time: finishedAt, status: 'PASSED', message: '运行完成'}),
                },
            } : node));
        }, 900);
        timers.current.push(elapsedTimer, timer);
    }, [setNodes]);

    const saveNode = useCallback((id) => {
        const savedAt = new Date().toLocaleTimeString('zh-CN', {hour12: false});
        const node = nodes.find((item) => item.id === id);
        if (!node) return;
        const noticeId = rowId();
        setNodes((current) => current.map((item) => item.id === id ? {
            ...item,
            data: {...item.data, savedAt, isDirty: false},
        } : item));
        setNodeSaveNotice({id: noticeId, label: node.data.label, savedAt});
        const timer = window.setTimeout(() => {
            setNodeSaveNotice((current) => current?.id === noticeId ? null : current);
        }, 2400);
        timers.current.push(timer);
    }, [nodes, setNodes]);

    const runAll = useCallback(() => {
        closeMenus();
        nodes.slice().sort((a, b) => a.position.x - b.position.x).forEach((node, index) => {
            const startTimer = window.setTimeout(() => runNode(node.id), index * 260);
            timers.current.push(startTimer);
        });
    }, [closeMenus, nodes, runNode]);

    const deleteNodes = useCallback((ids) => {
        const idSet = new Set(ids);
        if (!idSet.size) return;
        recordHistory();
        setNodes((current) => current.filter((node) => !idSet.has(node.id)));
        setEdges((current) => current.filter((edge) => !idSet.has(edge.source) && !idSet.has(edge.target)));
        setEditorNodeId((current) => idSet.has(current) ? null : current);
        setSelectedNodeIds((current) => current.filter((id) => !idSet.has(id)));
        closeMenus();
    }, [closeMenus, recordHistory, setEdges, setNodes]);

    const deleteNode = useCallback((id) => deleteNodes([id]), [deleteNodes]);

    const copyNodes = useCallback((ids) => {
        const idSet = new Set(ids);
        const copiedNodes = nodes.filter((node) => idSet.has(node.id)).map((node) => ({
            ...node,
            position: {...node.position},
            data: cloneValue(node.data),
            selected: false,
        }));
        if (!copiedNodes.length) return;
        const copiedEdges = edges.filter((edge) => idSet.has(edge.source) && idSet.has(edge.target)).map((edge) => cloneValue(edge));
        setClipboard({nodes: copiedNodes, edges: copiedEdges});
        pasteSequence.current = 0;
        closeMenus();
    }, [closeMenus, edges, nodes]);

    const copyNode = useCallback((id) => copyNodes([id]), [copyNodes]);

    const publishNode = useCallback(async (id) => {
        const node = nodes.find((item) => item.id === id);
        if (!node || !INSERTABLE_TYPES.includes(node.data.nodeType)) return;
        if (!window.confirm(`将“${node.data.label}”发布为独立新模板？config 中的 API Key 会清空，代码中的秘密不会自动修改。`)) return;
        try {
            const response = await fetch('/api/tool-templates/publish', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    type: node.data.nodeType,
                    name: node.data.label,
                    description: node.data.description || '',
                    definition: templateDefinitionFromNode(node),
                    main_py: node.data.mainPy ?? null,
                }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || '发布失败');
            setToolTemplates((current) => [data.template].concat(current));
            if (window.showToast) window.showToast('已发布为独立工具模板', 'success');
        } catch (error) {
            if (window.showToast) window.showToast(`发布工具模板失败: ${error instanceof Error ? error.message : '未知错误'}`, 'error');
        }
    }, [nodes]);

    const pasteClipboard = useCallback((origin = null) => {
        if (!clipboard?.nodes?.length) return;
        recordHistory();
        pasteSequence.current += 1;
        const minX = Math.min(...clipboard.nodes.map((node) => node.position.x));
        const minY = Math.min(...clipboard.nodes.map((node) => node.position.y));
        const offsetX = origin ? origin.x - minX : pasteSequence.current * 42;
        const offsetY = origin ? origin.y - minY : pasteSequence.current * 42;
        const idMap = new Map();
        const pastedNodes = clipboard.nodes.map((source) => {
            const newId = nodeId(source.data.nodeType);
            idMap.set(source.id, newId);
            const {measured, dragging, ...rest} = source;
            return {
                ...rest,
                id: newId,
                position: {x: source.position.x + offsetX, y: source.position.y + offsetY},
                data: cloneValue(source.data),
                selected: true,
            };
        });
        const pastedEdges = clipboard.edges.map((source) => {
            const {id, source: oldSource, target: oldTarget, ...edgeOptions} = cloneValue(source);
            return makeEdge(idMap.get(oldSource), idMap.get(oldTarget), edgeOptions);
        });
        setNodes((current) => current.map((node) => ({...node, selected: false})).concat(pastedNodes));
        setEdges((current) => current.concat(pastedEdges));
        setSelectedNodeIds(pastedNodes.map((node) => node.id));
        closeMenus();
    }, [clipboard, closeMenus, recordHistory, setEdges, setNodes]);

    const pasteNode = useCallback(() => {
        if (contextMenu?.flowPosition) pasteClipboard(contextMenu.flowPosition);
    }, [contextMenu, pasteClipboard]);

    const insertNode = useCallback((edgeId, type) => {
        const edge = edges.find((item) => item.id === edgeId);
        if (!edge) return;
        const source = nodes.find((node) => node.id === edge.source);
        const target = nodes.find((node) => node.id === edge.target);
        if (!source || !target) return;
        recordHistory();
        const next = makeNode(type, {
            x: (source.position.x + target.position.x) / 2,
            y: (source.position.y + target.position.y) / 2 + 130,
        });
        next.selected = true;
        setNodes((current) => current.map((node) => ({...node, selected: false})).concat(next));
        setEdges((current) => current.filter((item) => item.id !== edgeId).concat(
            makeEdge(source.id, next.id),
            makeEdge(next.id, target.id),
        ));
        setInsertEdgeId(null);
    }, [edges, nodes, recordHistory, setEdges, setNodes]);

    const decoratedEdges = useMemo(() => edges.map((edge) => ({
        ...edge,
        data: {
            ...edge.data,
            insertOpen: insertEdgeId === edge.id,
            onToggleInsert: (id) => setInsertEdgeId((current) => current === id ? null : id),
            onInsert: insertNode,
        },
    })), [edges, insertEdgeId, insertNode]);

    const decoratedNodes = useMemo(() => nodes.map((node) => ({
        ...node,
        data: {
            ...node.data,
            onRun: () => runNode(node.id),
        },
    })), [nodes, runNode]);

    const editorNode = nodes.find((node) => node.id === editorNodeId) || null;

    const handleNodeClick = useCallback((event, node) => {
        closeMenus();
        if (!event.ctrlKey && !event.metaKey) return;
        const nextSelection = new Set(selectedNodeIds);
        if (nextSelection.has(node.id)) nextSelection.delete(node.id);
        else nextSelection.add(node.id);
        setNodes((current) => current.map((item) => ({
            ...item,
            selected: nextSelection.has(item.id),
        })));
    }, [closeMenus, selectedNodeIds, setNodes]);

    const handleKeyboard = useCallback((event) => {
        const target = event.target;
        const isTextEntry = target instanceof HTMLElement && (
            target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
        );
        if (isTextEntry) return;
        const selectedIds = nodes.filter((node) => node.selected).map((node) => node.id);
        const control = event.ctrlKey || event.metaKey;
        const key = event.key.toLowerCase();
        if (control && key === 'z') {
            event.preventDefault();
            if (event.shiftKey) redo();
            else undo();
            return;
        }
        if (control && key === 'y') {
            event.preventDefault();
            redo();
            return;
        }
        if (control && key === 'c' && selectedIds.length) {
            event.preventDefault();
            copyNodes(selectedIds);
            return;
        }
        if (control && key === 'v' && clipboard?.nodes?.length) {
            event.preventDefault();
            pasteClipboard();
            return;
        }
        if ((event.key === 'Delete' || event.key === 'Backspace') && selectedIds.length) {
            event.preventDefault();
            deleteNodes(selectedIds);
        }
    }, [clipboard, copyNodes, deleteNodes, nodes, pasteClipboard, redo, undo]);

    const handleCopy = useCallback((event) => {
        const target = event.target;
        if (target instanceof HTMLElement && (
            target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
        )) return;
        const selectedIds = nodes.filter((node) => node.selected).map((node) => node.id);
        if (!selectedIds.length) return;
        event.preventDefault();
        event.clipboardData?.setData('text/plain', 'agent-bench-workflow-nodes');
        copyNodes(selectedIds);
    }, [copyNodes, nodes]);

    const handlePaste = useCallback((event) => {
        const target = event.target;
        if (target instanceof HTMLElement && (
            target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
        )) return;
        if (!clipboard?.nodes?.length) return;
        event.preventDefault();
        pasteClipboard();
    }, [clipboard, pasteClipboard]);

    const handleMarqueeStart = useCallback((event) => {
        if ((!event.ctrlKey && !event.metaKey) || event.button !== 0) return;
        if (!(event.target instanceof HTMLElement) || !event.target.classList.contains('react-flow__pane')) return;
        const canvas = event.currentTarget.querySelector('.wf-canvas-wrap');
        if (!canvas) return;
        const canvasRect = canvas.getBoundingClientRect();
        const next = {
            pointerId: event.pointerId,
            startClientX: event.clientX,
            startClientY: event.clientY,
            clientX: event.clientX,
            clientY: event.clientY,
            canvasLeft: canvasRect.left,
            canvasTop: canvasRect.top,
        };
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.setPointerCapture?.(event.pointerId);
        marqueeRef.current = next;
        setMarquee(next);
    }, []);

    const handleMarqueeMove = useCallback((event) => {
        if (!marqueeRef.current || marqueeRef.current.pointerId !== event.pointerId) return;
        event.preventDefault();
        const next = {...marqueeRef.current, clientX: event.clientX, clientY: event.clientY};
        marqueeRef.current = next;
        setMarquee(next);
    }, []);

    const handleMarqueeEnd = useCallback((event) => {
        const current = marqueeRef.current;
        if (!current || current.pointerId !== event.pointerId) return;
        event.preventDefault();
        event.stopPropagation();
        const left = Math.min(current.startClientX, event.clientX);
        const right = Math.max(current.startClientX, event.clientX);
        const top = Math.min(current.startClientY, event.clientY);
        const bottom = Math.max(current.startClientY, event.clientY);
        const matched = new Set();
        if (right - left >= 4 && bottom - top >= 4) {
            document.querySelectorAll('.react-flow__node').forEach((element) => {
                const rect = element.getBoundingClientRect();
                if (rect.right >= left && rect.left <= right && rect.bottom >= top && rect.top <= bottom) {
                    const id = element.getAttribute('data-id');
                    if (id) matched.add(id);
                }
            });
        }
        setNodes((items) => items.map((node) => ({...node, selected: node.selected || matched.has(node.id)})));
        event.currentTarget.releasePointerCapture?.(event.pointerId);
        marqueeRef.current = null;
        setMarquee(null);
    }, [setNodes]);

    const contextAction = useCallback((action) => {
        if (action === 'test-run') runAll();
        if (action === 'paste-node') pasteNode();
        if (action === 'run-node' && contextMenu?.nodeId) runNode(contextMenu.nodeId);
        if (action === 'copy-node' && contextMenu?.nodeId) copyNode(contextMenu.nodeId);
        if (action === 'publish-node' && contextMenu?.nodeId) publishNode(contextMenu.nodeId);
        if (action === 'delete-node' && contextMenu?.nodeId) deleteNode(contextMenu.nodeId);
        if (action !== 'paste-node') setContextMenu(null);
    }, [contextMenu, copyNode, deleteNode, pasteNode, publishNode, runAll, runNode]);

    const autoLayout = useCallback(() => {
        recordHistory();
        setNodes((current) => layoutGraph(current, edges));
        window.setTimeout(() => fitView({padding: 0.16, duration: 450}), 0);
    }, [edges, fitView, recordHistory, setNodes]);

    useEffect(() => {
        if (initialLayoutDone.current) return;
        initialLayoutDone.current = true;
        setNodes((current) => layoutGraph(current, edges));
        window.setTimeout(() => fitView({padding: 0.16, duration: 0}), 0);
    }, [edges, fitView, setNodes]);

    const save = useCallback(() => {
        setSaveState('正在保存');
        window.setTimeout(() => {
            setSaveState('已保存');
            if (options.onSave) options.onSave({name: workflowName});
        }, 480);
    }, [options, workflowName]);

    const close = useCallback(() => {
        timers.current.forEach((timer) => {
            window.clearTimeout(timer);
            window.clearInterval(timer);
        });
        if (options.onClose) options.onClose();
    }, [options]);

    const canUndo = historyTick >= 0 && undoStack.current.length > 0;
    const canRedo = historyTick >= 0 && redoStack.current.length > 0;

    return (
        <div className="workflow-studio-shell" tabIndex={0} aria-label="工作流画布" onKeyDown={handleKeyboard} onCopy={handleCopy} onPaste={handlePaste} onPointerDownCapture={handleMarqueeStart} onPointerMoveCapture={handleMarqueeMove} onPointerUpCapture={handleMarqueeEnd} onContextMenu={(event) => event.preventDefault()}>
            <header className="wf-studio-header">
                <div className="wf-header-left">
                    <button type="button" className="wf-icon-button" onClick={close} title="返回工作流管理" aria-label="返回工作流管理"><ArrowLeft size={18} /></button>
                    <span className="wf-header-divider" />
                    <span className="wf-workflow-mark"><Sparkles size={17} /></span>
                    <input value={workflowName} onChange={(event) => {setWorkflowName(event.target.value); setSaveState('未保存');}} aria-label="工作流名称" />
                    <span className="wf-save-state"><i />{saveState}</span>
                </div>
                <div className="wf-header-actions">
                    <button type="button" className="wf-secondary-button" onClick={runAll}><Play size={15} />运行</button>
                    <button type="button" className={headerPanel === 'templates' ? 'is-active' : ''} onClick={openTemplatePanel}><ServerCog size={15} />工具模板</button>
                    <button type="button" className={headerPanel === 'variables' ? 'is-active' : ''} onClick={() => setHeaderPanel((current) => current === 'variables' ? null : 'variables')}><SlidersHorizontal size={15} />全局变量</button>
                    <button type="button" className="wf-primary-button" onClick={save}><Save size={15} />保存</button>
                </div>
            </header>
            <main className="wf-canvas-wrap">
                {marquee && (
                    <div className="wf-selection-marquee" style={{
                        left: Math.min(marquee.startClientX, marquee.clientX) - marquee.canvasLeft,
                        top: Math.min(marquee.startClientY, marquee.clientY) - marquee.canvasTop,
                        width: Math.abs(marquee.clientX - marquee.startClientX),
                        height: Math.abs(marquee.clientY - marquee.startClientY),
                    }} />
                )}
                {nodeSaveNotice && (
                    <div className="wf-node-save-toast" role="status"><Check size={15} /><span>{nodeSaveNotice.label} 已保存</span><time>{nodeSaveNotice.savedAt}</time></div>
                )}
                {headerPanel === 'variables' && (
                    <aside className="wf-header-popover" aria-label="工作流全局变量">
                        <header>
                            <strong>全局变量</strong>
                            <button type="button" onClick={() => setHeaderPanel(null)} title="关闭" aria-label="关闭顶部面板"><X size={16} /></button>
                        </header>
                        <div className="wf-global-parameters">
                                <div className="wf-mapping-label-row"><span>变量名</span><span>变量</span><span /></div>
                                {globalVariables.map((row, index) => (
                                    <div className="wf-mapping-value-row" key={row.id}>
                                        <input aria-label={`全局变量名 ${index + 1}`} value={row.name} onChange={(event) => setGlobalVariables((current) => current.map((item) => item.id === row.id ? {...item, name: event.target.value} : item))} />
                                        <input aria-label={`全局变量 ${index + 1}`} value={row.value} onChange={(event) => setGlobalVariables((current) => current.map((item) => item.id === row.id ? {...item, value: event.target.value} : item))} />
                                        {index === 0 ? (
                                            <button type="button" className="wf-inline-icon-button" onClick={() => setGlobalVariables((current) => current.concat(emptyMappingRow()))} title="新增全局变量" aria-label="新增全局变量"><Plus size={15} /></button>
                                        ) : (
                                            <button type="button" className="wf-inline-icon-button is-danger" onClick={() => setGlobalVariables((current) => current.filter((item) => item.id !== row.id))} title="删除全局变量" aria-label={`删除全局变量 ${index + 1}`}><Trash2 size={15} /></button>
                                        )}
                                    </div>
                                ))}
                        </div>
                    </aside>
                )}
                {headerPanel === 'templates' && (
                    <aside className="wf-header-popover wf-template-popover" aria-label="工具模板">
                        <header>
                            <strong>工具模板</strong>
                            <button type="button" onClick={() => setHeaderPanel(null)} title="关闭" aria-label="关闭工具模板"><X size={16} /></button>
                        </header>
                        <div className="wf-template-list">
                            {templateLoadState === 'loading' && <span className="wf-template-empty">正在加载</span>}
                            {templateLoadState === 'error' && <span className="wf-template-empty is-error">加载失败</span>}
                            {templateLoadState === 'ready' && !toolTemplates.length && <span className="wf-template-empty">暂无工具模板</span>}
                            {toolTemplates.map((template) => {
                                const meta = NODE_TYPES[template.manifest.type] || NODE_TYPES.SCRIPT;
                                const Icon = meta.icon;
                                return (
                                    <button type="button" key={template.manifest.id} onClick={() => addTemplateNode(template)}>
                                        <span className="wf-template-icon" style={{'--template-accent': meta.color}}><Icon size={16} /></span>
                                        <span><strong>{template.manifest.name}</strong><small>{template.manifest.type}</small></span>
                                    </button>
                                );
                            })}
                        </div>
                    </aside>
                )}
                <ReactFlow
                    nodes={decoratedNodes}
                    edges={decoratedEdges}
                    nodeTypes={nodeTypes}
                    edgeTypes={edgeTypes}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={(connection) => {
                        recordHistory();
                        setEdges((current) => addEdge(makeEdge(connection.source, connection.target, connection), current));
                    }}
                    onNodeDragStart={recordHistory}
                    onPaneClick={closeMenus}
                    onNodeClick={handleNodeClick}
                    onSelectionChange={({nodes: selectedNodes}) => setSelectedNodeIds(selectedNodes.map((node) => node.id))}
                    onNodeDoubleClick={(event, node) => {
                        event.preventDefault();
                        closeMenus();
                        setEditorNodeId(node.id);
                    }}
                    onPaneContextMenu={(event) => {
                        event.preventDefault();
                        const flowPosition = screenToFlowPosition({x: event.clientX, y: event.clientY});
                        setContextMenu({
                            kind: 'pane',
                            x: Math.max(8, Math.min(event.clientX, window.innerWidth - 480)),
                            y: Math.max(66, Math.min(event.clientY, window.innerHeight - 235)),
                            flowPosition,
                        });
                        setInsertEdgeId(null);
                    }}
                    onNodeContextMenu={(event, node) => {
                        event.preventDefault();
                        if (!node.selected) {
                            setNodes((current) => current.map((item) => ({...item, selected: item.id === node.id})));
                        }
                        setContextMenu({
                            kind: 'node',
                            nodeId: node.id,
                            x: Math.max(8, Math.min(event.clientX, window.innerWidth - 205)),
                            y: Math.max(66, Math.min(event.clientY, window.innerHeight - 155)),
                        });
                        setInsertEdgeId(null);
                    }}
                    fitView
                    fitViewOptions={{padding: 0.16}}
                    minZoom={0.35}
                    maxZoom={1.8}
                    selectionOnDrag={false}
                    selectionKeyCode="Control"
                    multiSelectionKeyCode="Control"
                    panOnScroll
                    zoomOnDoubleClick={false}
                    deleteKeyCode={null}
                    proOptions={{hideAttribution: true}}
                >
                    <Background color="#c8d1de" gap={20} size={1.2} />
                    <MiniMap pannable zoomable nodeColor={(node) => NODE_TYPES[node.data.nodeType]?.color || '#64748b'} maskColor="rgba(238, 242, 247, 0.76)" />
                    <Controls showInteractive={false} />
                    <div className="wf-floating-toolbar">
                        <button type="button" disabled={!canUndo} onClick={undo} title="回退" aria-label="回退"><Undo2 size={16} /></button>
                        <button type="button" disabled={!canRedo} onClick={redo} title="前进" aria-label="前进"><Redo2 size={16} /></button>
                        <span />
                        <button type="button" onClick={autoLayout} title="自动布局" aria-label="自动布局"><LayoutGrid size={16} /></button>
                    </div>
                </ReactFlow>
                <ContextMenu
                    menu={contextMenu}
                    canPaste={Boolean(clipboard?.nodes?.length)}
                    canPublish={Boolean(contextMenu?.nodeId && INSERTABLE_TYPES.includes(nodes.find((node) => node.id === contextMenu.nodeId)?.data.nodeType))}
                    onAction={contextAction}
                    onAdd={(type) => contextMenu?.flowPosition && addNodeAt(type, contextMenu.flowPosition)}
                />
                <Inspector
                    key={editorNodeId || 'none'}
                    node={editorNode}
                    onRun={() => editorNodeId && runNode(editorNodeId)}
                    onSave={() => editorNodeId && saveNode(editorNodeId)}
                    onClose={() => setEditorNodeId(null)}
                    onChange={(patch) => setNodes((current) => current.map((node) => node.id === editorNodeId ? {...node, data: {...node.data, ...patch, isDirty: true}} : node))}
                />
            </main>
        </div>
    );
}

let activeRoot = null;
let activeContainer = null;

function unmount() {
    if (activeRoot) activeRoot.unmount();
    if (activeContainer) activeContainer.remove();
    activeRoot = null;
    activeContainer = null;
    document.body.classList.remove('workflow-studio-open');
}

function mount(options = {}) {
    unmount();
    activeContainer = document.createElement('div');
    activeContainer.id = 'workflow-studio-root';
    document.body.appendChild(activeContainer);
    document.body.classList.add('workflow-studio-open');
    activeRoot = createRoot(activeContainer);
    activeRoot.render(
        <React.StrictMode>
            <ReactFlowProvider><WorkflowStudio options={options} /></ReactFlowProvider>
        </React.StrictMode>,
    );
}

window.AgentBenchWorkflowCanvas = {mount, unmount};
