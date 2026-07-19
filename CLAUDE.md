# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

Agent Bench v2 目前是一个**本机企业 Agent 测试编排工具**：管理 Excel 测试集、Script/Agent 工具和 FastAPI Target，配置受限可视化 Workflow，并创建、启动、恢复和追溯 Run。

注意：git 历史里的 `caller/`、`core/`、`parser/`、`validators/`、`verifier/`、`runner.py` 是**旧的评测流水线，已被删除**。当前执行链位于 `execution/`，Web/API 位于 `web/`；不要参考已删除模块。

## 当前实现状态（截至 2026-07-19）

- 测试集管理、用例浏览、文件级元数据、当前测试集配置均已迁移到当前 FastAPI + 单页前端架构。
- Script / Agent 工具已改为 `tool_registry/{id}/manifest.json + main.py` 的可刷新目录仓储；不再使用 `inputs/.tools.json`，也没有 `tags` 字段或相关业务逻辑。
- 工具支持同名、ZIP 多文件导入、批量 ZIP 导出、手工目录刷新、打开工具目录、独立子进程运行、SSE 流式日志和立即中断。
- Script 与 Agent 均可执行当前虚拟环境中的 Python 标准库、LangChain、Pydantic 和已安装第三方包；运行时不会自动安装依赖。
- Agent 新建时默认给出可直接修改的 `init_chat_model + create_agent` 模板。模板保留注释状态的 `agent.stream(..., stream_mode="messages")` 示例，默认执行 `agent.invoke(...)` 并打印 `response`。
- FAQ 是前端内置的只读一级页面，当前包含 12 个第三方依赖安装、验证、升级和故障处理问题；没有 FAQ 后端接口或页面编辑功能。
- 页面已支持明暗主题：首次进入跟随 `prefers-color-scheme`，手动选择保存到 `localStorage["agent-bench-theme"]`，切换入口位于侧栏底部。当前适配范围是页面背景、表格、表单、弹窗和 FAQ 普通内容；CodeMirror 与运行日志沿用原有深色主题。当前没有“恢复跟随系统”的页面入口。
- Target、Workflow、Run 前端已经完成，包含受限自动布局编排、三种字段映射方式、测试集绑定、QUEUED 创建、SSE、追溯、Artifact 下载和手工恢复。
- 当前公开发布候选在未注入真实模型凭据时的完整回归为 `294 passed, 7 skipped, 1 warning`；6 个跳过项是对应供应商的 Agent live 矩阵，另一个是当前 Windows 账户没有创建目录符号链接的权限，warning 是 Starlette/httpx 弃用提示。此前两个供应商的完整真实模型矩阵均已通过。

## 企业 Agent 批量测试编排

已确认的完整需求基线位于 [`docs/enterprise-agent-test-orchestration.md`](docs/enterprise-agent-test-orchestration.md)。该文档统一记录 Target、Workflow、Run、FastAPI 请求协议、首 Sheet 规则、多 Run 轮询调度、重试/恢复/取消、Parser/Evaluator/Aggregator 契约、SQLite + Artifact 持久化、验收标准和 T1-T12 开发恢复状态。

开始相关任务前必须先通读该文档，不得根据 Git 历史里的旧评测流水线补全逻辑。T1-T10 已完成，包括 Target/Workflow/Run 前端及真实浏览器 E2E；T11 Excel Writer 仍为 deferred。T12 已完成 DeepSeek/DashScope 真实模型工具矩阵，真实内网 FastAPI 联调仍未完成。`config.yaml` 是 Git 忽略的本机状态，只保存当前 Excel 和 Sheet；缺失时使用安全默认值，首次上传后自动创建。

## 工作流程（强制）

### 1. 需求分析（动手前必须完成）

收到需求后，必须结合当前业务场景做结构化需求分析，不得跳过直接 coding：

**1.1 业务背景与目标（Why）**
- 这个需求要解决什么业务问题？在当前系统中处于什么位置？
- 如果需求描述模糊，必须追问澄清。

**1.2 真实场景与用户故事（Who & Where）**
- 谁在什么场景下使用？涉及哪些模块/页面/接口？
- 用一句话描述端到端的用户流程。

**1.3 需求真伪与优先级（What & When）**
- 用户描述的是"症状"还是"根因"？是否存在更简单的解法？
- 当前需求是否依赖其他未完成的功能？是否与现有功能冲突？

**1.4 验收标准与价值验证（How to Measure）**
- 完成后如何验证？具体的可观测结果是什么？
- 在开始 coding 前明确"做到什么程度算做完"。

### 2. 澄清机制约束

- **禁止推测**：未确认的业务逻辑严禁自行补全或假设，必须向我确认。
- **结构化追问**：单次追问不超过 3 个最关键问题，按优先级排序，并提供选项或示例辅助我回答，避免开放式提问。

### 3. 多模块任务拆解

涉及多模块联动或跨系统交互的任务，必须拆解为多个子任务：

- 每个子任务需包含：明确目标、输入/输出、验证方法、依赖关系。
- 颗粒度控制在可独立验证的范围内。
- 每完成一个子任务，必须执行对应的验证步骤并记录结果，验证通过后方可进入下一子任务，未通过则暂停并反馈问题。

### 4. 端到端测试与回归

- coding 完成后必须进行端到端测试，确保整个流程能跑通。
- 提供完整的端到端测试方案，覆盖正常路径和关键异常路径。
- 对可能受影响的已有功能进行回归验证。

## 常用命令

```bash
uv sync                 # 安装 Python 依赖
npm ci                  # 安装前端构建依赖（CodeMirror + esbuild）
npm run build:editor    # 构建 CodeMirror Python 编辑器 bundle
uv run python run.py    # 启动 Web 服务（http://127.0.0.1:8010，带 reload）
uv run pytest           # 运行全部测试
uv run pytest tests/test_tools.py::test_create_filter_and_sort_tools   # 运行单个测试
uv run pytest tests/test_agent_live_integration.py -m live             # 运行双供应商 2x5 工具矩阵
```

`pyproject.toml` 已配置 `pythonpath = ["."]` 和 `testpaths = ["tests"]`，pytest 临时目录固定在 `.pytest_tmp`。

真实模型测试固定使用 DeepSeek `deepseek-v4-pro` 和 DashScope `qwen3.7-max`，分别从 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY` 读取凭据，可用同名前缀的 `*_BASE_URL` 覆盖默认官方地址。未提供必要变量时，仅跳过对应供应商中包含 Agent 的矩阵行；Script 行仍真实执行。矩阵覆盖单 Script、单 Agent、多 Script、多 Agent 和双 Script + 双 Agent，全部经过 Web 工具 CRUD、Worker 和 SSE。每个 Agent 内含两个 tool、重试与审计中间件以及 Pydantic 结构化输出；两个模型都显式关闭思考模式以兼容强制 `tool_choice`。密钥只随运行请求进入 Worker，测试断言 manifest 中不含密钥。

默认端口由 `run.py` 固定为 `8010`。T10 浏览器端到端验证使用 `http://127.0.0.1:8012/`，这是临时启动端口，不是代码默认值；后续执行任务时应先查看现有终端启动日志或进程。

### Script / Agent 第三方依赖安装策略

Script 和 Agent 编辑器只使用当前虚拟环境中已经安装的包，运行时不会自动安装缺失依赖。需要新增第三方包时必须人工处理：

1. 确认 import 模块对应的发行包名称，两者可能不同。
2. 将发行包及合理版本范围加入 `pyproject.toml` 的 `dependencies`。
3. 在项目目录执行 `uv sync`。
4. 回到对应编辑器重新运行；如果服务仍使用旧环境状态，则重启 Web 服务后再试。

禁止在 Script 或 Agent 编辑器代码中调用 `pip`、`uv` 或其他包管理命令。缺失依赖时应保留完整 `ModuleNotFoundError`，并按上述流程安装。

`anthropic>=0.75,<1`、`httpx[socks]>=0.28,<1` 和 `langchain-anthropic>=1.0,<2` 已是直接依赖，可供用户代码按需创建兼容 Anthropic 协议的自定义客户端；`python-dotenv` 不是必需依赖，也未直接安装。

## 架构

入口 `run.py` → `web/app.py:create_app()`，聚合 8 个 router：

- `routes_excel.py` — 测试集上传/列表/sheet 探测/刷新/删除 + 测试集文件级元数据（name、description）
- `routes_testcases.py` — 用例分页浏览
- `routes_files.py` — 本机文件操作，当前仅 `POST /api/excel/sets/{filename}/open-dir`（Windows `explorer /select`）
- `routes_tools.py` — 测试工具（Script / Agent）的 CRUD、刷新、导入导出和联调运行
- `routes_config.py` — 读写 `config.yaml` 中当前选中的测试集 + sheet
- `routes_targets.py` — 企业 Agent Target 的 SQLite CRUD 和地址/Header/并发校验
- `routes_workflows.py` — 固定拓扑 Workflow CRUD、实时静态校验和测试集绑定
- `routes_runs.py` — Run 请求模板、创建、启动、取消、恢复、详情、SSE 和 Artifact 下载

Excel 文件路径操作必须经过 `web/files.py`（`get_input_path` / `get_existing_input_path` / `resolve_config_input_path`），这些函数校验文件名不含路径片段、后缀是 `.xlsx/.xlsm`、且解析后仍位于 `inputs/` 内，防止路径穿越。

数据层：`storage/excel.py` 的 `ExcelCaseRepository` 只读 Excel 前两列 `case_id | question`，自动跳过表头、空行、空值和重复 ID。

执行持久化：`execution/` 提供 v5 SQLite Migration、Target/Workflow/绑定/Run/CaseRun/Attempt/StepRun/Artifact Repository、固定拓扑和 RFC 6901 校验、工具代码快照、原子文件制品存储、Run 输入快照、FastAPI Connector、单 Case 执行器，以及按 Run 轮询 Target 请求槽的多 Run Scheduler。`run_storage/` 不提交到 Git。

工具仓储：`web/tool_registry.py` 管理 `tool_registry/{id}/` 下的 `manifest.json + main.py`，负责结构校验、目录写入和进程内快照。

前端：`web/static/` 单页应用以 `app.js` 处理测试集/工具/FAQ，以 `execution.js` 处理 Target/Workflow/Run，样式分别在 `style.css` 和 `execution.css`。Workflow 支持字段树/分段路径/高级 Pointer，Run 支持 SSE 状态、Attempt/Step/Artifact 追溯和恢复。产品只支持桌面浏览器，不保留移动端断点或移动端测试。

### Agent 执行架构（子进程模型）

Script 和 Agent 工具的 Python 代码**不在 Web 进程内执行**，而是通过子进程隔离：

1. `web/agent_runtime.py` — 模板编译 + 子进程调度
   - `compile_agent_template(code, params)` 把 `${model}` 等占位符替换为 `repr()` 转义后的 Python 字面量（字符串用引号包裹，空 system_prompt 替换为 `None`）
   - `run_agent_python(code, params)` 先替换 Agent 模板参数，再将代码发送给 Worker
   - `run_script_python(code)` 不替换模板参数，直接将 Script 代码发送给同一个 Worker
   - 页面运行请求携带唯一 `run_id`；执行器用 `Popen` 登记活动 Worker，`POST /api/tools/runs/{run_id}/interrupt` 会终止 Worker 及其派生子进程
   - 中断可以先于 Worker 启动到达，执行器会保留短期中断标记以避免竞态；中断结果不返回部分日志
   - 流式运行使用 `POST /{id}/{test|run}/start` 启动，再通过 `GET /api/tools/runs/{run_id}/events` 接收 SSE；事件类型为 `log`、`complete`、`interrupted`
   - 执行超时 120 秒，超时后 kill 子进程
   - 日志按子进程输出原文返回，不做自动脱敏
2. `web/agent_worker.py` — 子进程入口（`python -m web.agent_worker`）
   - 从 stdin 读取 JSON `{"code": "..."}`
   - 流式模式把完整行或显式 `flush()` 的文本编码为独立日志事件，最终 `response` 使用结果事件返回；普通同步协议继续兼容现有调用
   - Workflow 模式额外注入顶层 `inputs` 字典并启用严格 JSON response；工具编辑页沿用宽松兼容模式
   - 编译用户代码时不继承 Worker 模块的 `__future__` 标志，避免普通类型注解意外变成延迟注解
   - `exec()` Script 或 Agent 用户代码；可使用当前虚拟环境内已安装的 LangChain、Pydantic、第三方包和 Python 标准库，不自动安装缺失依赖
   - Agent 工具保存时只有名称必填，允许保存空参数和空代码草稿；点击运行时才校验代码非空及实际引用的 `${...}` 参数
   - 只有 Python 代码实际引用的 `${...}` 参数才要求对应参数值非空；未使用占位符的普通代码无需填写模型参数
   - 顶层变量 `response` 可选；存在时转换为 JSON 结构随 API 返回，不存在时仅返回日志
   - 结果以 JSON 写回 stdout
3. `web/run_stream.py` — 进程内运行事件管理
   - 为每个 `run_id` 保存有序事件队列，允许 SSE 初次连接消费启动后立即产生的日志
   - 单次最多保留和展示 5 MB 日志，超限后只发送一次截断提示，Worker 继续运行并正常返回 `response`
   - 页面刷新不查询或恢复活动运行；已结束但无人消费的事件最多保留 5 分钟

### Script vs Agent 两种工具类型

| 特性 | Script | Agent |
|------|--------|-------|
| 执行方式 | 独立子进程，无限制 | 独立子进程，无限制 |
| 占位符 | 无 | `${model}`, `${api_key}` 等 6 个参数 |
| 代码编辑器 | CodeMirror | CodeMirror + 占位符语法高亮 |
| 联调入口 | `POST /{id}/run` | `POST /{id}/test` |
| 结果要求 | `response` 可选；存在时返回结构化结果 | `response` 可选；存在时返回结构化结果 |

前端 CodeMirror 编辑器由 `web/frontend/python-editor.js` 源码经 esbuild 打包为 `web/static/assets/codemirror-python.js`。运行 `npm run build:editor` 重新构建。

不要直接编辑打包后的 `web/static/assets/codemirror-python.js`；编辑器行为或主题变化应修改 `web/frontend/python-editor.js` 后重新构建。当前 CodeMirror 始终使用深色主题，不随页面明暗主题切换。

Script / Agent 编辑页的执行操作统一显示“运行”和“中断”。运行时摘要显示绿色旋转状态和秒级计时；成功显示绿色 `SUCCESS`，失败显示红色 `FAILED`，用户中断显示灰色 `Interrupted`。日志通过 SSE 实时追加在按钮行下方，中断时清空已显示的部分日志。

### 工具目录仓储

- 每个 Script / Agent 工具独立保存为 `tool_registry/{id}/`，不再按类型拆分目录；`manifest.json` 包含 `schema_version`、`id`、`type`、名称、说明、参数和时间字段，`main.py` 保存 Python 代码。
- 工具唯一性只由 `id` 决定，名称允许重复；导入文件与现有工具同 ID 时直接拒绝，不覆盖原工具。
- 页面 CRUD 会同时修改工具目录和当前进程快照。用户从项目目录手工新增、修改或删除目录内容后，必须在工具管理页点击“刷新”才会重读目录。
- 刷新只扫描 `tool_registry/` 下一级 `{id}/` 目录；Web 运行时不兼容旧 `.tool.json`。无效目录会被跳过，有效工具仍正常加载，页面持续展示目录名和具体错误原因。
- 导入和导出只支持 ZIP，统一结构为 `{id}/manifest.json + {id}/main.py`；一个 ZIP 可包含一个或多个工具，页面可一次选择多个 ZIP。勾选工具时直接导出所选工具，未勾选时确认后导出全部工具。
- ZIP 导入会拒绝路径穿越、缺少必需文件、目录名与 ID 不一致及重复 ID；有效 ZIP 和无效 ZIP 可在同一次上传中分别返回结果。
- 工具行提供“打开目录”按钮，直接进入对应 `{id}/` 目录。导出的 manifest 保留全部参数及明文密钥，只能传递给可信接收方。
- 工具目录可能包含明文密钥，`tool_registry/*/` 必须保持在 Git 忽略列表中；仓库只提交根目录的 `.gitkeep`。
- 旧单文件仓储已通过 `uv run python scripts/migrate_tool_registry.py` 一次性迁移；该脚本不属于 Web 兼容路径。

## 关键约定与易错点

- **静态文件用显式 `@app.get` 路由**（`/`、`/style.css`、`/app.js`），而不是 `StaticFiles` mount 到根。这是刻意为之：根 mount 会拦截 API 的 `PUT`/`DELETE`。`/assets` 下的小图标用 `StaticFiles` mount，因为它们只有 GET。
- **测试集元数据存在 `inputs/.sets_meta.json`**，不是数据库；读取时会过滤掉指向已不存在文件的记录。工具不再使用 `inputs/.tools.json`，统一由 `web/tool_registry.py` 管理目录仓储。
- **`config.yaml` 只保存"当前选中"**（`excel.input_path` + `excel.sheet_name`），不是通用配置，并且不得提交到 Git。缺失时后端使用 `config.example.yaml` 对应的安全默认值；删除当前选中的测试集时，`routes_excel.py` 会自动切换到剩余文件或回退默认值。
- **测试工具 API 时必须 monkeypatch `web.routes_tools.TOOL_REGISTRY_ROOT` 并清空模块级仓储缓存**。参考 `tests/test_tools.py` 的 `_patch_tools_storage`；测试集元数据仍按 `tests/test_set_meta.py` 的 `_patch_inputs` 处理。
- **Agent 工具的 `api_key` 以明文存在对应 `manifest.json`，运行日志也按原文返回**。工具目录已被 Git 忽略；导出 ZIP 或分享日志前必须自行检查敏感信息。
- **工具 manifest 不包含 `tags`**，Pydantic 模型使用 `extra="forbid"`；不要重新引入名称唯一约束或 tags 兼容逻辑，除非用户重新确认业务需求和迁移方案。
- **主题偏好是纯前端状态**，键名固定为 `agent-bench-theme`，值只接受 `light` / `dark`。修改主题时至少回归桌面端测试集表格、工具表格、工具编辑表单、FAQ 和弹窗；不要新增移动端测试，也不要顺带改变 CodeMirror 或日志主题。
- 服务绑定 `127.0.0.1`，仅面向本机；接口无鉴权，符合本机工具定位。

## 语言约定

代码注释、docstring（Google 风格）、AGENTS.md 均为中文。新增代码请保持中文注释与既有风格一致。
