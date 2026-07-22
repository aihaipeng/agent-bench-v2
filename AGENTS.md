# AGENTS.md

## 项目概述

Agent Bench v2 当前是本机使用的企业 Agent 测试编排工具，用于管理 `inputs/` 目录下的 Excel 测试集、维护测试工具和 Target、配置受限可视化 Workflow，并创建、启动、恢复和追溯 Run。

## 执行任务的强制流程

- 动手前结合当前业务场景确认 Why、Who/Where、What/When 和可观测的验收标准。
- 未确认的业务逻辑不得自行补全；确需澄清时，单次只问最多 3 个最高优先级问题，并提供互斥选项或示例。
- 多模块或跨系统任务必须拆成可独立验证的子任务，写清目标、输入/输出、验证方法和依赖。每个子任务验证通过后才能进入下一项。
- 开发完成后必须给出并执行端到端测试方案，同时运行受影响模块回归；不能只依赖静态字符串测试。
- 工作区可能已有用户改动，禁止回滚或覆盖与当前任务无关的差异。

## 当前进度（截至 2026-07-22）

- 旧 Script/Agent 工具、旧固定 Workflow/Run 页面/API/执行链已按不兼容重构永久删除，不得从 Git 历史恢复。
- 一级“工具模板”页面统一管理大写 `HTTP / AGENT / LLM / SCRIPT`；目录包为 `{id}/manifest.json + definition.json + 可选 main.py`，支持 CRUD、刷新、安全 ZIP 导入导出、同名模板和同 ID 拒绝覆盖。
- 四类模板支持独立测试；AGENT/LLM/SCRIPT 与 HTTP CODE 使用统一顶层 `inputs / config / response` Python Worker，HTTP CONFIG 使用同一可中断子进程发起真实请求。运行通过 SSE 流式传输日志与严格 JSON response，支持 120 秒超时、5 MB 日志上限和进程树中断。
- 模板深拷贝到画布后无来源引用；画布节点可右键发布为新 ID 的独立模板。发布时清空 `config` 中明确的 API Key，但不会扫描或改写 Python 代码中的秘密。
- FAQ 已实现为前端内置的只读一级页面，没有后端 CRUD。
- 页面支持跟随系统且可手动持久化的明暗主题；独立测试日志区固定使用深色运行日志样式。
- Target CRUD 保留。新版 Workflow Studio 当前仍是前端会话草稿，尚未定义或接入新版 Workflow 持久化、DAG 执行和 Run 追溯协议。
- 一级“模型管理”支持 OpenAI 与 Anthropic 两种协议；协议、`SYSTEM / DIRECT / CUSTOM` 代理、自定义代理认证、正向 `verify_ssl` 开关、模型默认 Body、上下文元数据、最大输出能力和单模型可用性测试均只在供应商详情维护，不进入画布。请求不根据公网/内网 IP 自动改路由；三种代理模式严格执行，CUSTOM 始终使用显式代理，关闭“验证 SSL 证书”时才设置 `verify=False`。
- Workflow LLM 节点只引用模型并保存节点高级参数。后端按“平台基础请求 < 模型默认 Body < 节点高级参数”递归合并，支持 OpenAI-compatible 与 Anthropic 原生阻塞/流式执行；流式响应保留原始 SSE 且不提取输出变量。
- 新版 Workflow Studio 前端高保真原型已完成：工作流管理页进入独立全屏 React Flow 画布，`START / END` 为可选系统节点，新建画布默认只创建业务节点 `HTTP / AGENT / LLM / SCRIPT`；右键画布可添加全部六类节点，Edge `+` 仅插入业务节点。支持拖动、连线、连线选中高亮、Delete/Backspace 删除连线或节点、连线右键删除、空白区/节点右键菜单、小地图和测试运行状态演示。画布保存/运行允许隐式起点和终点，拒绝完全游离节点和循环依赖并显示 Toast；单节点运行独立于整图校验。进入画布时使用 Dagre 自动布局；最多保留 50 步图结构历史，`Ctrl+Z`、`Ctrl+Shift+Z`、`Ctrl+Y` 及左上角回退/前进按钮均可用。支持 Ctrl 点击/框选多选、Ctrl+C/Ctrl+V 保留节点配置及选区内部连线。双击节点在画布中心打开可移动、八向拉伸的编辑器；节点配置页标题栏提供运行/中断/保存/关闭，保存只在显式保存时执行图校验。画布右上角保留运行/全局变量/中断/保存。
- 画布节点轮廓默认统一为中性灰，不使用节点类型色或运行状态色；当前选中节点使用 `1px` 绿色边框叠加 `2px` 绿色 outline、浅绿到白色的内侧渐变和绿色光环，且选中前后节点尺寸不变。节点成功状态文案统一为 `SUCCESS`，失败为 `FAILED`。
- 旧协议历史真实模型矩阵曾覆盖 DeepSeek `deepseek-v4-pro` 和 DashScope `qwen3.7-max`，但对应测试已随旧协议删除；不得把历史结果解释为新模板 Worker 的 live 验证。
- 当前全量回归：`203 passed, 6 skipped, 1 warning`；6 项跳过为未向本轮进程注入真实供应商环境变量的 live 用例，warning 为既有 Starlette/httpx 弃用提示。
- 旧评测流水线、`inputs/.tools.json` 和工具 `tags` 逻辑均已删除，不要从 Git 历史恢复。

## 企业 Agent 批量测试编排

- 已确认的完整业务边界、数据契约、调度规则、验收标准和开发恢复清单统一记录在 [`docs/enterprise-agent-test-orchestration.md`](docs/enterprise-agent-test-orchestration.md)。
- 该文档保留 T1-T12 的历史边界和验证记录；T13.2 的最新不可兼容决策以 `PLAN.md` 为权威事实来源。旧 Workflow/Run 实现已删除，不得按历史完成状态恢复。
- 首期已明确接受 Evaluator 不设工具并发上限的资源放大风险；不得在未重新澄清时擅自增加 `tool_concurrency`。
- `config.yaml` 是被 Git 忽略的本机状态，只保存当前 Excel 和 Sheet；缺失时使用安全默认值，首次上传测试集后自动创建。不得把编排进度、业务配置或凭据写入其中。

## 常用命令

```bash
# 安装依赖
uv sync

# 安装前端依赖并重建 Workflow bundle
npm ci
npm run build

# 启动本机 Web 服务
uv run python run.py

# 运行测试
uv run pytest

# 前端与工具模板专项回归
uv run pytest tests/test_theme_frontend.py tests/test_faq_frontend.py tests/test_tool_templates_frontend.py tests/test_execution_frontend.py
```

新模板协议当前没有真实模型 live 测试。API Key 只允许注入运行进程，不得写入代码、测试、文档或提交内容。

`run.py` 默认服务地址是 `http://127.0.0.1:8010`。2026-07-19 的 T10 浏览器 E2E 使用 `http://127.0.0.1:8012/`，因为当时 `8011` 被未重载新路由的旧进程占用；这些都是临时端口，下次任务应先检查现有终端启动日志。

## 架构

```text
run.py
  └── web/app.py
        ├── web/routes_excel.py      # 测试集上传、列表、sheet、刷新、删除
        ├── web/routes_testcases.py  # 用例分页浏览
        ├── web/routes_files.py      # 打开本机文件目录
        ├── web/routes_tool_templates.py # 四类模板 CRUD、ZIP、发布和独立运行
        ├── web/routes_config.py     # 当前测试集配置
        └── web/routes_targets.py    # Target CRUD 与输入校验

web/files.py                          # 文件路径安全校验（防止路径穿越）
storage/excel.py                      # 读取 case_id + question 格式的 Excel
execution/targets.py                  # 独立 Target SQLite Repository
web/tool_templates.py                 # 四类模板模型、目录仓储和原子批量写入
web/tool_template_archives.py         # 安全 ZIP 内存解析与生成
web/tool_execution.py                 # 四类模板执行分派
web/tool_runtime.py                   # Worker 调度、超时与进程树中断
web/tool_worker.py                    # Python/HTTP CONFIG 子进程入口
web/run_stream.py                     # 运行事件队列、日志上限与 SSE 数据源
web/frontend/workflow-canvas.jsx      # React Flow Studio 源码
web/static/tool-templates.js          # 工具模板管理、ZIP 和独立测试 UI
web/static/app.js                     # 测试集、FAQ 与一级导航
web/static/execution.js               # Target 与前端草稿 Workflow 入口
web/static/execution.css              # 执行页面桌面样式

tool_registry/                        # {id}/manifest.json + definition.json + 可选 main.py
```

## 工具模板仓储

- HTTP / AGENT / LLM / SCRIPT 模板统一保存在 `tool_registry/`，不按类型拆分目录；类型在 API、文件和画布中只接受大写。
- `manifest.json` 保存身份和展示元数据，`definition.json` 保存 inputs/outputs/config 和类型配置；AGENT/LLM/SCRIPT 及 HTTP CODE 必须有 `main.py`，HTTP CONFIG 可无。
- 模板只以 `id` 区分，允许同名；导入同 ID 整包拒绝覆盖，不产生部分写入。
- 页面 CRUD 立即更新目录和内存快照；直接修改目录后必须在工具模板页点击“刷新”。旧 `manifest.json + main.py` 包因缺少 `definition.json` 明确拒绝。
- ZIP 可包含一个或多个 `{id}/...` 模板；导入只在内存解析，拒绝路径穿越、符号链接、加密条目、未知文件、重复路径和超限归档。
- 独立运行请求使用 `run_id`；启动立即返回，页面通过 SSE 接收日志和严格 JSON 结果。
- 没有换行的输出在用户代码调用 `flush()` 后推送。单次运行最多展示 5 MB 日志，超限时提示截断但程序继续执行；刷新页面后不恢复本次日志。
- 编辑页可终止 Worker 及其派生子进程。测试 inputs、状态、耗时和日志不持久化。
- 导出不会自动清理 `config` 或 `main.py` 中的全部秘密，只能交给可信接收者；画布发布仅保证清空明确命名的 API Key 配置。
- `tool_registry/*/` 不得提交到 Git，仓库只保留根目录的 `.gitkeep`。
- 额外字段会被 Pydantic 拒绝；模板类型和 ID 创建后不可修改。

## 工具模板运行边界

| 类型 | 执行方式 | 运行变量 | 输出 |
|------|----------|----------|------|
| HTTP CONFIG | 独立子进程中的 httpx | `inputs`、持久 `config`、HTTP definition | `status_code / headers / body` |
| HTTP CODE | 独立 Python 子进程 | 顶层 `inputs / config / response` | 严格 JSON `response` |
| AGENT | 独立 Python 子进程 | 顶层 `inputs / config / response` | 严格 JSON `response` |
| LLM | 独立 Python 子进程 | 顶层 `inputs / config / response` | 严格 JSON `response` |
| SCRIPT | 独立 Python 子进程 | 顶层 `inputs / config / response` | 严格 JSON `response` |

- Worker 使用当前 `.venv`，支持其中已安装的标准库、LangChain、Pydantic 和第三方包，不自动安装依赖。
- 缺包时人工修改 `pyproject.toml` 后执行 `uv sync`；禁止在编辑器用户代码中调用 `pip` 或 `uv`。
- `anthropic`、`httpx` 和 `langchain-anthropic` 已直接安装，可供用户代码按需创建兼容 Anthropic 协议的自定义客户端；`python-dotenv` 不在必需依赖中。
- 页面用 `run_id` 启动任务并通过 SSE 接收 `log`、`complete`、`interrupted` 事件；中断会终止 Worker 及其派生进程。
- 所有 Python 模板始终启用严格 JSON response，不存在 `repr()` 回退；NaN/Infinity、循环引用和不可序列化对象均作为执行错误拒绝。
- 单次运行日志上限为 5 MB，执行超时默认为 120 秒；刷新页面不会恢复活动运行或历史日志。

## 前端状态

- 一级导航包含测试集、Target、工具模板、Workflow 和 FAQ，不包含运行中心。Target 支持 CRUD；Workflow 管理页进入全屏 React Flow Studio，但保存、运行和状态仍是前端会话演示，尚未接入新版 Workflow API。
- 工具模板页面支持四类大写模板 CRUD、刷新、ZIP 导入导出、独立测试和中断。画布可从模板深拷贝节点，也可右键发布为新 ID 的独立模板。
- 前端只支持桌面浏览器，不提供移动端或触控专用布局；禁止新增手机断点、移动视口适配和移动端回归测试。桌面宽表仍在各自 table-wrap 内滚动。
- 空白 AGENT/LLM/SCRIPT 节点默认代码为 `response = inputs`；模板编辑页直接编辑 `main.py` 文本。
- FAQ 数据在 `web/static/app.js`，为只读页面；不要新增保存按钮或 `/api/faq`，除非业务规则重新确认。
- 主题状态使用 `localStorage["agent-bench-theme"]`。无显式偏好时跟随 `prefers-color-scheme`；手动切换后保存 `light` 或 `dark`，当前没有恢复跟随系统的页面入口。
- 主题按钮固定在桌面侧栏底部。修改主题时只执行桌面页面回归，不需要移动端测试。

## Excel 格式

只支持固定两列输入：

```text
case_id | question
```

第一行可以是表头。第三列及之后允许存在历史结果或人工备注，但 Web 读取用例时只读取前两列。

## 配置

`config.example.yaml` 提供公开安全的配置示例。运行时 `config.yaml` 被 Git 忽略，只保留 Web 当前选择：

```yaml
excel:
  input_path: inputs/testcases.xlsx
  sheet_name: Sheet1
```

## 约束

- Web 服务只面向本机使用，入口绑定 `127.0.0.1`。
- Excel 文件操作只能发生在项目 `inputs/` 目录内，工具文件操作只能发生在 `tool_registry/` 内。
- 删除或上传测试集时要保持当前配置一致。
- 用户仍可能把 API Key 或其他秘密写入模板 `config`、`main.py` 和运行日志；ZIP 导出不自动全面脱敏。不得把真实密钥写入代码、测试、文档、模板包或提交内容。
- 静态首页、CSS 和 JS 使用显式 GET 路由，`/assets` 才使用 `StaticFiles`；不要把根路径改为 StaticFiles mount，以免拦截 API 的 PUT/DELETE。
