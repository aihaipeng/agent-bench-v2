# Agent Bench

Agent Bench 是一个本机运行的企业 Agent 测试编排工具。它用于管理 Excel 测试集、Script/Agent 测试工具和 FastAPI Target，并通过可视化 Workflow 创建、运行、恢复和追溯批量测试。

当前版本支持：

- Excel 测试集上传、分页浏览和首个 Sheet 执行
- Script / Agent 工具 CRUD、ZIP 导入导出、SSE 日志和运行中断
- FastAPI Target、请求模板、连接失败重试和大响应 Artifact
- Parser、Evaluator、Check Aggregator、Case Aggregator 固定工作流
- 多 Run 调度、Case 并发、取消、手工恢复和完整执行追溯
- DeepSeek 与 DashScope 真实模型工具链测试

系统只面向桌面浏览器和本机使用，服务固定绑定 `127.0.0.1`。

## 环境要求

- Windows 10 或 Windows 11
- [uv](https://docs.astral.sh/uv/)
- Git，仅在通过 Git 获取项目时需要
- Node.js 不是运行依赖；只有修改 CodeMirror 编辑器源码时才需要

## 安装与启动

进入项目目录后执行：

```powershell
uv python install 3.14
uv sync --locked --python 3.14
uv run python run.py
```

浏览器打开 [http://127.0.0.1:8010](http://127.0.0.1:8010)。停止服务时在 PowerShell 中按 `Ctrl+C`。

首次启动不需要创建配置文件。系统在缺少 `config.yaml` 时使用安全默认值，并在首次上传测试集后自动创建本机配置。

## 首次使用

1. 在“测试集”页面上传 `.xlsx` 或 `.xlsm` 文件。
2. 测试集前两列使用 `case_id | question`，第一行可以是表头。
3. 在“工具”页面创建 Parser、Evaluator 或 Aggregator 所需的 Script/Agent 工具。
4. 在“Target”页面配置待测 FastAPI 地址和并发上限。
5. 在“Workflow”页面编排工具并绑定测试集。
6. 在“运行中心”创建 Run，设置超时、Case 并发和连接重试参数后手工启动。

仓库不附带真实测试集、API Key、Target、工具 manifest 或运行记录。新用户需要在页面中创建自己的本地数据。

## 开发与测试

```powershell
# 全量测试
uv run pytest -q

# 启动开发服务
uv run python run.py

# 修改 CodeMirror 源码后重新构建
npm ci
npm run build:editor
```

缺少真实模型凭据时，对应 live Agent 用例会跳过，不影响其他功能测试。

## 真实模型测试

真实模型矩阵使用 DeepSeek `deepseek-v4-pro` 和 DashScope `qwen3.7-max`。在当前 PowerShell 进程设置所需环境变量后运行：

```powershell
$env:DEEPSEEK_API_KEY = "<your-key>"
$env:DASHSCOPE_API_KEY = "<your-key>"
uv run pytest tests/test_agent_live_integration.py -m live -q
```

`DEEPSEEK_BASE_URL` 和 `DASHSCOPE_BASE_URL` 为可选覆盖项。测试只把密钥注入单次运行请求，并断言临时工具 manifest 未保存密钥。

## 本地数据与安全

以下内容只保存在本机，并已被 `.gitignore` 排除：

- `config.yaml`：当前选择的测试集和 Sheet
- `inputs/`：Excel 测试集及本地元数据
- `tool_registry/`：工具代码、参数和可能存在的明文 API Key
- `run_storage/`：SQLite、请求响应、日志和运行 Artifact
- `outputs/`、`logs/`：导出结果和本地日志
- `.env*`、证书私钥、虚拟环境、依赖目录和测试缓存

公开仓库只保留 [config.example.yaml](config.example.yaml)、`inputs/.gitkeep` 和 `tool_registry/.gitkeep` 作为安全模板或空目录占位。不要强制添加被忽略的运行数据，也不要发布工具导出 ZIP。

## 项目结构

```text
run.py                     # 本机服务入口
web/                       # FastAPI 路由、工具仓储和单页前端
execution/                 # Target、Workflow、Run、调度、执行和 Artifact
storage/                   # Excel 测试集读取
tests/                     # 单元、集成和真实模型测试
inputs/                    # 本机测试集，内容不提交
tool_registry/             # 本机工具，内容不提交
run_storage/               # 本机运行数据库与 Artifact，不提交
```

更完整的业务边界和执行语义见 [企业 Agent 测试编排需求基线](docs/enterprise-agent-test-orchestration.md)。
