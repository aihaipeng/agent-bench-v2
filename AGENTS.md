# AGENTS.md

## 项目概述

Agent Bench v2 当前是本机使用的企业 Agent 测试编排工具，用于管理 `inputs/` 目录下的 Excel 测试集、维护测试工具和 Target、配置受限可视化 Workflow，并创建、启动、恢复和追溯 Run。

## 执行任务的强制流程

- 动手前结合当前业务场景确认 Why、Who/Where、What/When 和可观测的验收标准。
- 未确认的业务逻辑不得自行补全；确需澄清时，单次只问最多 3 个最高优先级问题，并提供互斥选项或示例。
- 多模块或跨系统任务必须拆成可独立验证的子任务，写清目标、输入/输出、验证方法和依赖。每个子任务验证通过后才能进入下一项。
- 开发完成后必须给出并执行端到端测试方案，同时运行受影响模块回归；不能只依赖静态字符串测试。
- 工作区可能已有用户改动，禁止回滚或覆盖与当前任务无关的差异。

## 当前进度（截至 2026-07-19）

- 工具仓储、ZIP 导入导出、目录刷新、同名工具、SSE 流式日志和运行中断均已完成。
- Script / Agent 都在独立子进程执行；Script 不支持 `${...}`，Agent 只支持 6 个固定模板参数。
- FAQ 已实现为前端内置的只读一级页面，没有后端 CRUD。
- 页面支持跟随系统且可手动持久化的明暗主题，当前仅适配背景、表格、表单、弹窗和 FAQ；CodeMirror 与日志不切换主题。
- Target、Workflow 和 Run 前端已完成；支持字段树/分段路径/高级 Pointer、QUEUED 创建、SSE 状态更新、Attempt/Step/Artifact 追溯和手工恢复。
- 真实模型工具矩阵已覆盖 DeepSeek `deepseek-v4-pro` 和 DashScope `qwen3.7-max` 的单 Script、单 Agent、多 Script、多 Agent、双 Script + 双 Agent；Agent 内含两个 tool、`ToolRetryMiddleware`、自定义审计中间件和 Pydantic 结构化输出。
- 当前公开发布候选在未注入真实模型凭据时的完整回归：`294 passed, 7 skipped, 1 warning`。6 个跳过项是对应供应商的 Agent live 矩阵，另一个是当前 Windows 账户没有创建目录符号链接的权限；warning 是 Starlette/httpx 弃用提示。此前两个供应商的完整真实模型矩阵均已通过。
- 旧评测流水线、`inputs/.tools.json` 和工具 `tags` 逻辑均已删除，不要从 Git 历史恢复。

## 企业 Agent 批量测试编排

- 已确认的完整业务边界、数据契约、调度规则、验收标准和开发恢复清单统一记录在 [`docs/enterprise-agent-test-orchestration.md`](docs/enterprise-agent-test-orchestration.md)。
- 该文档是此功能的权威事实来源。开始 Target、Workflow、Run、FastAPI Connector、Parser/Evaluator/Aggregator 编排或 Excel Writer 相关任务前必须先通读，并核对其中的“当前阶段”和 T1-T12 状态。
- T1-T10 已完成并通过专项测试和真实浏览器 E2E：持久化、Target、Run 输入、Connector、Workflow、Worker、Case 执行、多 Run Scheduler、Run API、无回放实时事件和 Target/Workflow/Run 前端。T11 Excel Writer 仍为 deferred；T12 已完成真实模型工具矩阵，真实内网 FastAPI 联调仍未完成，未获得完整响应前不得宣称真实环境通过。
- 首期已明确接受 Evaluator 不设工具并发上限的资源放大风险；不得在未重新澄清时擅自增加 `tool_concurrency`。
- `config.yaml` 是被 Git 忽略的本机状态，只保存当前 Excel 和 Sheet；缺失时使用安全默认值，首次上传测试集后自动创建。不得把编排进度、业务配置或凭据写入其中。

## 常用命令

```bash
# 安装依赖
uv sync

# 安装前端构建依赖并重建 CodeMirror bundle
npm ci
npm run build:editor

# 启动本机 Web 服务
uv run python run.py

# 运行测试
uv run pytest

# 前端主题和主要页面回归
uv run pytest tests/test_theme_frontend.py tests/test_agent_frontend.py tests/test_faq_frontend.py tests/test_tool_transfer_frontend.py

# 真实模型测试（Agent 行需要 DEEPSEEK_API_KEY / DASHSCOPE_API_KEY）
uv run pytest tests/test_agent_live_integration.py -m live
```

真实模型固定使用 DeepSeek `deepseek-v4-pro` 和 DashScope `qwen3.7-max`。`DEEPSEEK_BASE_URL`、`DASHSCOPE_BASE_URL` 可选；缺省时使用测试中声明的官方地址。API Key 只允许注入 pytest 进程，不得写入代码、文档或工具 manifest。

`run.py` 默认服务地址是 `http://127.0.0.1:8010`。2026-07-19 的 T10 浏览器 E2E 使用 `http://127.0.0.1:8012/`，因为当时 `8011` 被未重载新路由的旧进程占用；这些都是临时端口，下次任务应先检查现有终端启动日志。

## 架构

```text
run.py
  └── web/app.py
        ├── web/routes_excel.py      # 测试集上传、列表、sheet、刷新、删除
        ├── web/routes_testcases.py  # 用例分页浏览
        ├── web/routes_files.py      # 打开本机文件目录
        ├── web/routes_tools.py      # 工具 CRUD、Agent 联调
        ├── web/routes_config.py     # 当前测试集配置
        ├── web/routes_targets.py    # Target CRUD 与输入校验
        ├── web/routes_workflows.py  # Workflow CRUD、校验与测试集绑定
        └── web/routes_runs.py       # Run 创建、启动、取消、恢复、追溯与下载

web/files.py                          # 文件路径安全校验（防止路径穿越）
storage/excel.py                      # 读取 case_id + question 格式的 Excel
execution/models.py                   # Target、Run、Case、Attempt、Step、Artifact 模型
execution/repository.py               # SQLite Migration 与执行数据 Repository
execution/artifacts.py                # 大型运行制品安全、原子文件存储
execution/preparation.py              # 首 Sheet、请求模板渲染、Run 输入快照
execution/connector.py                # FastAPI 请求、Attempt、响应流式 Artifact
execution/workflows.py                # 固定拓扑、JSON Pointer、工具快照
execution/case_executor.py            # 单 Case 固定工作流执行与完整 Artifact
execution/scheduler.py                # 多 Run 公平 Target 槽、取消与手工恢复
web/agent_runtime.py                  # 模板编译、Worker 调度、超时与进程中断
web/agent_worker.py                   # 子进程 exec 入口、日志/response 协议
web/tool_registry.py                  # manifest + main.py 目录仓储、校验与刷新快照
web/run_stream.py                     # 运行事件队列、日志上限与 SSE 数据源
web/run_events.py                     # Run/Case 状态事件广播
web/frontend/python-editor.js         # CodeMirror 源码；修改后需重新构建
web/static/app.js                     # 测试集、工具、FAQ 与一级导航
web/static/execution.js               # Target、Workflow、Run 前端交互
web/static/execution.css              # 执行编排页面与响应式样式

tool_registry/                        # {id}/manifest.json + main.py 格式的工具目录
```

## 工具仓储

- Script / Agent 工具统一保存在 `tool_registry/`，不按类型拆分目录；每个工具对应一个 `{id}/` 目录，其中 `manifest.json` 保存元数据和参数，`main.py` 保存代码。
- 工具只以 `id` 区分，允许同名；导入同 ID 文件时拒绝覆盖。
- 页面 CRUD 立即更新工具目录和内存快照；直接修改项目目录后，必须在工具管理页点击“刷新”才会生效。
- 刷新只扫描一级 `{id}/` 工具目录，不读取旧 `.tool.json`；无效目录会被跳过并在页面展示目录名和错误原因。
- Script / Agent 运行请求使用 `run_id` 标识活动 Worker；启动接口立即返回，页面再通过 SSE 按行接收日志和最终结构化结果。
- 没有换行的输出在用户代码调用 `flush()` 后推送。单次运行最多展示 5 MB 日志，超限时提示截断但程序继续执行；刷新页面后不恢复本次日志。
- 编辑页可通过中断接口终止 Worker 及其派生子进程，中断后清空已展示的部分日志。
- 导入和导出只支持 ZIP。每个 ZIP 统一使用 `{id}/manifest.json + {id}/main.py`，可包含一个或多个工具；页面支持一次选择多个 ZIP 并逐包反馈结果。勾选工具时直接导出所选工具，未勾选时确认后导出全部工具。
- 工具行的“打开目录”按钮直接进入对应 `{id}/` 目录。
- 导出包含全部参数和明文密钥，只能传递给可信接收方。
- `tool_registry/*/` 不得提交到 Git，仓库只保留根目录的 `.gitkeep`。
- `manifest.json` 不包含 `tags`，额外字段会被 Pydantic 拒绝；工具类型和 ID 创建后不可修改。

## Script / Agent 运行边界

| 特性 | Script | Agent |
|------|--------|-------|
| Python 执行 | 独立子进程 | 独立子进程 |
| 模板参数 | 不支持 | `model`、`model_provider`、`api_key`、`base_url`、`system_prompt`、`human_message` |
| Workflow 输入 | 顶层 `inputs` 字典 | 顶层 `inputs` 字典 |
| 保存校验 | 名称必填，代码可空 | 名称必填，参数和代码可空 |
| 运行校验 | 代码非空 | 代码非空，只校验代码实际引用的参数 |
| 输出 | stdout/stderr 流式日志，顶层 `response` 可选 | stdout/stderr 流式日志，顶层 `response` 可选 |

- Worker 使用当前 `.venv`，支持其中已安装的标准库、LangChain、Pydantic 和第三方包，不自动安装依赖。
- 缺包时人工修改 `pyproject.toml` 后执行 `uv sync`；禁止在编辑器用户代码中调用 `pip` 或 `uv`。
- `anthropic`、`httpx` 和 `langchain-anthropic` 已直接安装，可供用户代码按需创建兼容 Anthropic 协议的自定义客户端；`python-dotenv` 不在必需依赖中。
- 页面用 `run_id` 启动任务并通过 SSE 接收 `log`、`complete`、`interrupted` 事件；中断会终止 Worker 及其派生进程并清空页面上的部分日志。
- Workflow 调用启用严格 JSON response，禁用编辑页兼容使用的 `repr()` 回退；NaN/Infinity 也会作为执行错误拒绝。
- 单次运行日志上限为 5 MB，执行超时默认为 120 秒；刷新页面不会恢复活动运行或历史日志。

## 前端状态

- 一级导航包含测试集、Target、工具、Workflow、运行中心和 FAQ。Target 支持 CRUD；Workflow 支持列表、复制、删除、绑定和受限自动布局编排；Run 支持模板/参数配置、历史、详情、SSE、恢复和 Artifact 下载。
- Workflow 输入映射提供字段树、分段路径和高级 JSON Pointer；页面内部统一保存 RFC 6901 Pointer。多个 Evaluator/Check 需要按后端规则配置对应 Script Aggregator。
- 前端只支持桌面浏览器，不提供移动端或触控专用布局；禁止新增手机断点、移动视口适配和移动端回归测试。桌面宽表仍在各自 table-wrap 内滚动。
- 新建 Agent 默认代码定义在 `web/routes_tools.py::DEFAULT_AGENT_PYTHON_CODE`，包含注释状态的标准流式示例和默认启用的阻塞式 `invoke` 示例。
- API Key 默认以密码框显示，可通过眼睛按钮切换明文；代码区和日志区都有复制按钮。
- FAQ 数据在 `web/static/app.js`，为只读页面；不要新增保存按钮或 `/api/faq`，除非业务规则重新确认。
- 主题状态使用 `localStorage["agent-bench-theme"]`。无显式偏好时跟随 `prefers-color-scheme`；手动切换后保存 `light` 或 `dark`，当前没有恢复跟随系统的页面入口。
- 主题按钮固定在桌面侧栏底部。修改主题时只执行桌面页面回归，不需要移动端测试。
- CodeMirror 源码在 `web/frontend/python-editor.js`，构建产物在 `web/static/assets/codemirror-python.js`；禁止直接编辑构建产物。

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
- `api_key` 会明文写入工具 manifest，导出 ZIP 和运行日志也不自动脱敏；不得把密钥写入测试、文档或提交内容。
- 静态首页、CSS 和 JS 使用显式 GET 路由，`/assets` 才使用 `StaticFiles`；不要把根路径改为 StaticFiles mount，以免拦截 API 的 PUT/DELETE。
