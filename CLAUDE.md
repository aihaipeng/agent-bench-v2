# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

Agent Bench v2 目前是一个**本机 Web 工具**，用于管理 `inputs/` 下的 Excel 测试集：浏览 sheet 用例、维护测试集/工具的元数据、配置当前测试集，以及创建并联调测试工具（Script / Agent）。

注意：git 历史里的 `caller/`、`core/`、`parser/`、`validators/`、`verifier/`、`runner.py` 是**旧的评测流水线，已被删除**。当前活跃代码只有 `run.py`、`web/`、`storage/`、`tests/`。不要参考已删除模块。

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
```

`pyproject.toml` 已配置 `pythonpath = ["."]` 和 `testpaths = ["tests"]`，pytest 临时目录固定在 `.pytest_tmp`。

## 架构

入口 `run.py` → `web/app.py:create_app()`，聚合 5 个 router：

- `routes_excel.py` — 测试集上传/列表/sheet 探测/刷新/删除 + 测试集文件级元数据（name、description）
- `routes_testcases.py` — 用例分页浏览
- `routes_files.py` — 本机文件操作，当前仅 `POST /api/excel/sets/{filename}/open-dir`（Windows `explorer /select`）
- `routes_tools.py` — 测试工具（Script / Agent）的 CRUD、联调运行
- `routes_config.py` — 读写 `config.yaml` 中当前选中的测试集 + sheet

所有文件路径操作必须经过 `web/files.py`（`get_input_path` / `get_existing_input_path` / `resolve_config_input_path`），这些函数校验文件名不含路径片段、后缀是 `.xlsx/.xlsm`、且解析后仍位于 `inputs/` 内，防止路径穿越。

数据层：`storage/excel.py` 的 `ExcelCaseRepository` 只读 Excel 前两列 `case_id | question`，自动跳过表头、空行、空值和重复 ID。

前端：`web/static/` 单页应用（`app.js` 约 2500 行 + `index.html` + `style.css`），静态资源在 `/assets`。

### Agent 执行架构（子进程模型）

Agent 工具的 Python 代码**不在 Web 进程内执行**，而是通过子进程隔离：

1. `web/agent_runtime.py` — 模板编译 + 子进程调度
   - `compile_agent_template(code, params)` 把 `${model}` 等占位符替换为 `repr()` 转义后的 Python 字面量（字符串用引号包裹，空 system_prompt 替换为 `None`）
   - `run_agent_python(code, params)` 将编译后的代码通过 stdin JSON 发给子进程，捕获 stdout 结果
   - 执行超时 120 秒，超时后 kill 子进程
   - 日志中的 `api_key` 自动替换为 `***`
2. `web/agent_worker.py` — 子进程入口（`python -m web.agent_worker`）
   - 从 stdin 读取 JSON `{"code": "..."}`
   - `exec()` 用户代码，要求顶层变量 `response` 必须被赋值
   - 结果以 JSON 写回 stdout

### Script vs Agent 两种工具类型

| 特性 | Script | Agent |
|------|--------|-------|
| 执行方式 | 进程内 `exec()` + 受限 builtins | 独立子进程，无限制 |
| 占位符 | 无 | `${model}`, `${api_key}` 等 6 个参数 |
| 代码编辑器 | CodeMirror | CodeMirror + 占位符语法高亮 |
| 联调入口 | `POST /{id}/run` | `POST /{id}/test` |
| 结果要求 | 无（stdout 即为日志） | 必须赋值 `response` 变量 |

前端 CodeMirror 编辑器由 `web/frontend/python-editor.js` 源码经 esbuild 打包为 `web/static/assets/codemirror-python.js`。运行 `npm run build:editor` 重新构建。

## 关键约定与易错点

- **静态文件用显式 `@app.get` 路由**（`/`、`/style.css`、`/app.js`），而不是 `StaticFiles` mount 到根。这是刻意为之：根 mount 会拦截 API 的 `PUT`/`DELETE`。`/assets` 下的小图标用 `StaticFiles` mount，因为它们只有 GET。
- **元数据存在 `inputs/` 下的 dotfile**，不是数据库：`.tools.json`（工具定义，顶层键为 `tools`）、`.sets_meta.json`（测试集 name/description）。每个都有对应的 `_load_*` / `_save_*` 辅助函数；测试集元数据读取时会过滤掉指向已不存在文件的记录。改动存储格式要同步这些函数。
- **`config.yaml` 只保存"当前选中"**（`excel.input_path` + `excel.sheet_name`），不是通用配置。删除当前选中的测试集时，`routes_excel.py` 会自动切换到剩余文件或回退默认值。
- **写测试时必须同时 monkeypatch 多个模块的 `INPUTS_DIR`**。因为 `INPUTS_DIR`、`SETS_META_FILE`、`TOOLS_FILE` 等是各模块的模块级常量，patch 一处不够。参考 `tests/test_set_meta.py` 的 `_patch_inputs` 和 `tests/test_tools.py` 的 `_patch_tools_storage` 辅助函数。
- **Agent 工具的 `api_key` 以明文存在 `.tools.json`**。这是本机工具的现状，处理相关代码时注意不要把密钥回显到日志或响应里（`.tools.json` 应保持在 `inputs/`，勿提交含真实密钥的文件）。
- 服务绑定 `127.0.0.1`，仅面向本机；接口无鉴权，符合本机工具定位。

## 语言约定

代码注释、docstring（Google 风格）、AGENTS.md 均为中文。新增代码请保持中文注释与既有风格一致。
