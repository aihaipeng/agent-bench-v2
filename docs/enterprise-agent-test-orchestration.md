# 企业 Agent 测试编排需求基线

> 状态：T1-T12 为历史实现与验证记录；对应旧 Workflow/Run/工具执行链已在 T13.2 不兼容重构中删除。T13.1 画布原型已完成，T13.2 当前进度以根目录 `PLAN.md` 为准。
> 最后更新：2026-07-20
> 用途：保留企业 Agent 批量测试编排的历史业务边界和验证证据。不得根据本文的“已完成”恢复已删除实现；开始新开发时先读 `AGENTS.md` 和 `PLAN.md`。
> 约束：本文记录已确认业务规则；未写明的业务逻辑不得自行推测。若后续用户确认的新规则与本文冲突，以最新确认结果为准并同步更新本文。

## 1. 业务背景与目标

本历史方案基于两类基础资产：

- 测试集：以 Excel 保存，输入列固定为 `case_id | question`。
- 测试工具：当时的 Script / Agent 工具，保存在旧 `tool_registry/{id}/manifest.json + main.py`；该格式现已被四类大写工具模板包替代。

目标是在两类资产之间增加可持久化、可并发、可追溯、可恢复的测试运行编排能力，用于验证企业 Agent。

企业 Agent 的原始输出是大规模流式数据，但 Agent Bench 不直接消费原始流。另一个独立部署的 FastAPI 项目已经负责清理和提取企业 Agent 流式输出，并以普通 HTTP Response Body 返回 JSON。Agent Bench 首期只对接该 FastAPI；未来可能增加直接对接真实环境的目标连接器。

端到端业务链路：

```text
读取测试集首个 Sheet
  -> 为每条 question 渲染自定义 JSON 请求体
  -> 调用外部 FastAPI
  -> 保存完整响应制品
  -> 顺序执行 Parser
  -> 并行执行各 Check Item 的 Evaluator
  -> 按需执行 Check Aggregator
  -> 按需执行 Case Aggregator
  -> 持久化运行结果
  -> 最终由 Excel Writer 生成结果副本
```

## 2. 当前阶段与明确暂缓项

### 已完成

- 需求分析与核心业务边界澄清。
- 现有测试集、工具仓储、单工具运行和 SSE 日志能力已在当前代码中实现。
- T1 SQLite + Artifact 持久化基础：运行记录模型、事务化 v1 Migration、并发安全 Repository、Artifact 安全路径和原子文件 API。
- T2 Target 后端：v2 Migration、可复用 Target Repository、`/api/targets` CRUD、地址/Header/并发校验。
- T3 Run 输入准备：从同一 Excel 字节版本计算哈希并读取首 Sheet、严格 JSON 模板解析与递归 `${question}` 渲染、Run/CaseRun 原子快照落库。
- T4 FastAPI Connector：实际请求字节快照、异步流式 Response Artifact、独立 Attempt、连接失败重试、读取超时/HTTP/协议/业务错误分类与保留策略。
- T5 Workflow 后端：v3 Migration、固定拓扑模型、RFC 6901 映射校验、Parser 工具输出示例、工具代码快照、Workflow CRUD 和测试集一对一绑定。
- T6 Worker 契约：Script/Agent 顶层 `inputs` 注入、编排严格 JSON 模式、Parser 任意 JSON、Evaluator/Aggregator 原始结果校验与系统标准结果组装。
- T7 Case 执行器：v4 Step 重跑记录、Connector→顺序 Parser→并行 Check/Evaluator→按需 Aggregator、Step/Check/Case Artifact 和错误继续语义。
- T8 Scheduler：Run Case 并发、Target 请求槽按 Run 轮询、多 Run 重叠、取消本地 HTTP/Worker、无自动恢复和手工恢复选择。
- T9 Run API 与实时事件：v5 测试集请求模板配置、QUEUED Run 创建、Run/Case/Attempt/Step/Artifact 查询、手工启动/取消/恢复、安全下载和无回放 SSE。
- T10 运行编排前端：Target CRUD、Workflow 列表/绑定/受限自动布局编排、字段树/分段路径/高级 Pointer、Run 创建/历史/详情、SSE、恢复、追溯和 Artifact 下载。
- T12 真实模型工具矩阵：DeepSeek `deepseek-v4-pro` 和 DashScope `qwen3.7-max` 均已通过单 Script、单 Agent、多 Script、多 Agent、双 Script + 双 Agent 的 Web CRUD/Worker/SSE 链路；Agent 覆盖多 tool、中间件和 Pydantic 结构化输出。
- T13.1 新版 Workflow Studio 前端高保真原型：工作流管理列表进入独立全屏 React Flow 画布，具备拖动、连线、空白区/节点右键菜单、Edge `+` 插入、复制粘贴、小地图和运行状态演示；双击节点打开画布中心的大尺寸编辑器，支持移动和八向拉伸。

### 尚未实现

- T12 的真实内网 FastAPI 联调与最终可复现端到端报告；当前只完成协议等价 mock/本地 stub 链路。

### 明确暂缓

- 移动端适配和移动端测试。系统仅用于桌面浏览器，不保留手机断点、触控专用交互或移动视口声明。
- Excel Writer 的具体列布局和写入实现。这是最后一个开发步骤，在前序运行链路稳定后再单独澄清和设计。
- 定时任务。首期只做人工启动、顺序执行和并发执行。
- 多 Sheet 执行。首期每个测试集只执行工作簿中的第一个 Sheet。
- 新版画布的后端图协议、持久化、校验、快照和 DAG 执行器。T13.1 只完成前端本地状态原型，不得把原型交互宣称为可保存或可执行的新工作流。
- 编排页单节点调试或完整试运行。实际执行、日志和结果统一放在 Run 页面。
- Agent 类型的 Check Aggregator / Case Aggregator。首期 Aggregator 使用 Python Script。

## 3. 术语

- `Target`：可复用的目标环境配置，描述 FastAPI 地址和目标级并发上限。
- `Workflow`：可复用的测试工作流配置；测试集绑定一个 Workflow。
- `Run`：完整执行某个测试集第一个 Sheet 的一次运行。
- `CaseRun`：Run 中一条 `case_id/question` 用例的完整执行。
- `Attempt`：CaseRun 调用 FastAPI 的一次 HTTP 尝试；连接失败重试会产生新的 Attempt。
- `Parser`：顺序执行的数据提取或转换工具，输出可为任意 JSON。
- `Check Item`：业务测试点，例如 `intent`、`i18n`、`tool_use_count`。
- `Evaluator`：Check Item 内的一次 Script 或 Agent 校验工具调用。
- `Check Step`：工作流中配置的一次 Evaluator 调用，使用稳定且唯一的 `step_id`。
- `Check Aggregator`：同一 Check Item 有多个 Evaluator 时，用于合并这些 Evaluator 结果的 Python Script。
- `Check Result`：一个 Check Item 的最终标准结果。
- `Case Aggregator`：一个 CaseRun 有多个 Check Result 时，用于生成最终 Case Result 的 Python Script。
- `Artifact`：请求、响应、Parser 输出、工具日志和聚合结果等文件制品。

`Check Pipeline` 只表示一个 Check Item 的配置分组，不是实际运行节点，不单独记录状态或产生一次执行。

## 4. 测试集和 Excel 边界

- Excel 输入格式继续固定为 `case_id | question`，第一行可以是表头。
- 测试执行只读取工作簿中按原始顺序排列的第一个 Sheet。
- 现有测试集浏览页继续允许查看全部 Sheet；“只读第一个 Sheet”只约束新的测试执行模块。
- 若工作簿包含多个 Sheet，运行创建页和运行快照必须记录实际执行的第一个 Sheet 名，并明确提示其他 Sheet 未执行。
- `case_id` 仅用于 Agent Bench 内部关联 Excel 行、CaseRun、制品和最终结果，不得自动注入发送给 FastAPI 的请求体。
- 原始 Excel 不修改。未来 Excel Writer 生成独立结果副本；具体格式暂缓设计。

## 5. Target 与请求协议

### 5.1 Target

Target 是独立、可复用的配置实体。首期至少包含：

- 名称。
- Base URL。
- Path。
- HTTP Method；当前实际接口为 `POST`。
- Headers；当前接口暂时使用默认 Headers，但模型需保留自定义能力。
- 同一 Target 下多个 Run 共享的请求总并发上限 `target_total_concurrency`。

当前已知接口：

```text
POST /api/agent/invoke
Content-Type: application/json
```

### 5.2 请求模板

- 请求体参数不固定，由用户为测试集配置任意合法 JSON 模板。
- 模板目前只提供 `${question}` 用例变量。
- 不提供 `${case_id}`，也不自动注入 `case_id`、`request_id` 或其他业务字段。
- `username`、`password`、`address` 等只是用户可能写入模板的普通字段，不是系统固定字段。
- 系统运行在内网中，请求模板、实际请求和运行快照按原文保存，不做字段脱敏。
- 系统先把模板解析为合法 JSON，再递归遍历字符串值并替换 `${question}`。禁止先对 JSON 源文本做裸字符串拼接。

示例仅表示模板能力，不代表固定 Schema：

```json
{
  "question": "${question}",
  "username": "xxx",
  "password": "xxx",
  "address": "127.0.0.1"
}
```

### 5.3 响应与成功判定

- FastAPI 返回普通 `application/json` 对象，Agent Bench 不解析企业 Agent 原始 SSE/NDJSON 流。
- 响应内部 `data` 可能很大且结构复杂，系统不把它固化成数据库列；完整响应保存为 JSON Artifact。
- 先判断 HTTP 状态码：非 2xx 记为请求阶段 `ERROR`。
- HTTP 2xx 时读取 Response Body，把 `body.code` 统一转换成字符串；只有 `"200"` 视为业务成功并进入 Parser。
- `body.code != "200"` 视为业务失败，记为 `ERROR`，不自动重试。
- JSON 无法解析、缺少必要外层结构等协议错误记为 `ERROR`。
- 当前脱敏成功响应样例经过裁剪，不是可直接解析的完整 JSON。开发连接器端到端测试前仍需准备一份结构完整的脱敏成功响应。

## 6. Run 参数、调度、重试、恢复和取消

### 6.1 Run 定义

- Run 表示执行整个测试集的第一个 Sheet，不表示单条用例。
- CaseRun 表示其中一条用例。
- 多个 Run 可以在不同时间启动并重叠执行，不设置“全系统只能有一个活动 Run”的限制。
- 请求模板作为测试集当前配置持久化；创建 Run 时冻结副本，之后修改测试集模板不影响已有 Run。
- Run 创建后状态固定为 `QUEUED`，不会自动执行；必须由用户手工启动。

### 6.2 Run 启动参数

Run 创建时直接指定：

- 单次 FastAPI Attempt 的超时时间；默认 `600` 秒，允许修改。
- `case_concurrency`：该 Run 同时执行的 Case 数；设为 `1` 即顺序执行。
- 连接失败重试次数。
- 重试间隔。

Target 另外保存 `target_total_concurrency`。多个 Run 共享同一 Target 时，每个 Run 都受自身 `case_concurrency` 和 Target 总并发上限双重约束。

### 6.3 多 Run 调度

- 多个 Run 共享同一 Target 并发槽位时，按 Run 轮询分配，避免早启动的长 Run 长时间独占 Target。
- 不设置 Run 优先级。
- 首期不实现定时任务。

### 6.4 Evaluator 并发边界

- 已明确选择：只限制 Case/FastAPI 并发，不为 Script/Agent Evaluator 设置 `tool_concurrency` 或系统工具总并发上限。
- 不同 Check Item 并行，同一 Check Item 内多个 Evaluator 也并行，因此实际子进程和 Agent 模型调用数量可能按 `Case 数 x Check Item 数 x Evaluator 数` 放大。
- 这是已知且接受的首期风险。后续若出现本机资源或外部模型限流问题，再新增工具并发控制；当前不得自行增加未确认的限制。

### 6.5 重试

- 只对确认尚未建立连接的连接失败按 Run 配置自动重试。
- 每次重试创建独立 Attempt，保留各 Attempt 的时间、错误和日志，不能覆盖前一次记录。
- 读取超时不自动重试。请求可能已经被 FastAPI 接收并触发企业 Agent；自动重试可能造成重复执行。
- 读取超时直接记为 `ERROR`，由用户决定是否手工重跑该 Case。
- HTTP 非 2xx、业务失败和工具业务校验 `FAIL` 均不自动重试。

### 6.6 状态与业务结论分离

系统执行状态与测试业务结论分开保存：

- 执行状态使用 `QUEUED`、`RUNNING`、`SUCCEEDED`、`ERROR`、`CANCELLED`。
- Evaluator / Check / Case 的业务状态使用 `PASS`、`FAIL`、`ERROR`、`SKIP`。
- 一个业务结论为 `FAIL` 的 Case 可以是执行状态 `SUCCEEDED`，恢复 Run 时不得把它当作执行异常自动重跑。

### 6.7 手工恢复

- 服务重启或 Run 中断后保留全部持久化进度，不自动恢复。
- 用户手工恢复 Run。
- 已成功完成的 Case 不重复执行；只继续未开始、取消或执行异常且用户选择重跑的 Case。

### 6.8 取消

- 取消 Run 后停止派发新 Case。
- 取消 Agent Bench 本地正在等待的 HTTP 请求和正在执行的工具子进程；无法保证外部 FastAPI 已触发的企业 Agent 随连接取消而终止。
- 已完成结果保留。
- 未完成 Case 标记 `CANCELLED`，以后可手工恢复。

### 6.9 实时事件与断线恢复

- Run SSE 只推送客户端订阅后产生的 Run/Case 状态变化和 Run 终态，不保存事件历史，也不重放订阅前事件。
- SSE 不承载大型 FastAPI Response、工具日志或完整 Artifact 正文，只作为页面实时刷新提示。
- 客户端首次进入、刷新或断线重连后，通过 Run/Case 详情 API 从 SQLite 读取当前权威状态；不得依赖 SSE 恢复历史。
- 已结束 Run 的事件接口不合成终态重放，客户端直接读取持久化详情。

## 7. 持久化与制品

- SQLite 保存 Target、Workflow、测试集绑定关系、Run、CaseRun、Attempt、StepRun、状态、时间和 Artifact 索引。
- 文件系统保存请求、响应、Parser 输出、Evaluator 日志/结果和聚合结果等大型制品；大型 JSON 不作为数据库 BLOB 保存。
- 运行创建时冻结 Target、Excel 文件哈希和首个 Sheet 名、请求模板、Workflow、工具代码、参数及工具元数据快照。运行中修改原配置或工具不得影响已启动 Run。
- 成功运行的大型中间制品保留天数可配置。
- 失败制品和最终汇总长期保留。
- Artifact 路径必须有独立安全边界校验，不能复用只允许 `inputs/` 的 Excel 路径函数。

建议的逻辑目录结构：

```text
runs/{run_id}/
  snapshot/
  cases/{case_id}/
    request.json
    attempts/{attempt_id}/
    response.json
    parsers/
    checks/
    case_result.json
```

目录名和具体根路径属于实现细节；实现时必须保持在项目批准的运行制品目录内并加入 Git 忽略。

## 8. Workflow 模型

### 8.1 所有权与快照

- Workflow 是独立、可复用的配置实体。
- 每个测试集绑定一个 Workflow。
- Run 启动时保存 Workflow 和相关工具的完整快照。

### 8.2 固定执行结构

首期不做任意 DAG，固定为：

```text
Parser 1 -> Parser 2 -> ...
  -> 多个 Check Item 并行
       -> 每个 Check Item 的多个 Evaluator 并行
       -> 多 Evaluator 时执行 Check Aggregator
  -> 多个 Check Result 时执行 Case Aggregator
```

- 多个 Parser 按配置顺序执行。
- 后一个 Parser 可通过 JSON Pointer 读取原始响应和之前 Parser 的输出。
- 不同 Check Item 并行执行。
- 同一 Check Item 内多个 Evaluator 并行执行。
- 同一 Check Item 只有一个 Evaluator 时，Evaluator 结果直接成为 Check Result，不执行 Check Aggregator。
- 同一 Check Item 有多个 Evaluator 时，必须配置 Python Script Check Aggregator。
- 一个 Case 只有一个 Check Result 时，直接成为 Case Result，不执行 Case Aggregator。
- 一个 Case 有多个 Check Result 时，必须配置 Python Script Case Aggregator。
- `Check Pipeline` 不是执行节点，不产生额外运行记录。

### 8.3 输入映射

- 工具之间使用 RFC 6901 JSON Pointer 读取上游 JSON。
- JSON Pointer 只负责取值，不执行 Python 表达式或隐式转换。
- 复杂提取和转换必须由 Parser 完成。
- 大型响应优先通过 Artifact 引用传递，避免在多个工具输入中反复复制。
- JSON Pointer 是系统内部存储和运行协议，不是普通用户的默认输入方式。
- 常规工作流必须能够在用户不了解 JSON Pointer 的情况下完成配置。

### 8.4 Parser 输出声明与字段选择器

- 工作流由测试人员和工具开发人员共同配置，默认交互必须面向不了解 JSON Pointer 的用户。
- 每个 Parser 必须在工具配置中提供一份合法的 JSON 输出示例；该示例只描述输出结构，不参与实际运行。
- 工作流编辑器根据上游 Parser 的输出示例生成可展开的字段树。
- Evaluator 的 `status`、`reason`、`data` 等标准字段由系统内置结构直接生成字段树。
- 用户先选择来源节点，再从字段树点击字段；页面显示易读变量路径，系统内部转换并保存为 RFC 6901 JSON Pointer。
- 字段树无法覆盖的复杂路径可使用分段路径编辑器，例如 `[tool_calls] > [0] > [name]`。
- 页面保留原始 JSON Pointer 高级模式，用于复杂字段和故障排查，但不得作为默认配置入口。
- 编排页只做结构编辑、Pointer 生成和静态校验，不运行样例、不测试单节点，也不展示实际运行日志。

### 8.5 工具运行契约

- 系统向 Script / Agent 用户代码注入顶层 `inputs` 字典。
- 工具继续通过顶层 `response` 返回结果，兼容现有 Worker 的运行方式。
- Parser 的 `response` 可为任意 JSON。
- Evaluator 的工具原始返回值固定为：

```json
{
  "status": "FAIL",
  "reason": "意图识别不准确",
  "data": {
    "optional": "可选结构化数据"
  }
}
```

- `status` 必须是 `PASS`、`FAIL`、`ERROR`、`SKIP`。
- `reason` 是字符串。
- `data` 是可选任意 JSON，用于给 Check Aggregator 提供可靠的机器可读依据。

### 8.6 系统标准 EvaluatorResult

工具不负责生成 `case_id`、`check_item` 或 `step_id`。系统根据 CaseRun 和 Workflow 配置补充：

```json
{
  "case_id": "case_001",
  "check_item": "intent",
  "step_id": "intent_semantic_agent",
  "status": "FAIL",
  "reason": "意图识别不准确",
  "data": {}
}
```

- `step_id` 是 Workflow 内稳定且唯一的步骤标识，不是工具 UUID。同一个工具可在不同步骤重复使用。
- `evaluator_id`、`evaluator_name`、`evaluator_type` 不放入业务结果，避免重复和耦合。
- 这些工具元数据必须保存在 StepRun：工具 UUID、运行时名称快照、工具类型、代码哈希、开始/结束时间和日志引用。名称允许重复且可修改，不能作为身份依据。

### 8.7 Evaluator 异常

- 某个 Evaluator 异常时，系统为该 Step 生成 `status=ERROR` 和错误原因。
- 同一 Check Item 的其他 Evaluator 继续。
- 其他 Check Item 继续。
- Check Aggregator 仍然接收全部 Step 结果，包括 `ERROR`。
- Case Aggregator 仍然执行。

### 8.8 Check Aggregator

- 仅在一个 Check Item 有多个 Evaluator 时执行。
- 首期只允许 Python Script。
- 每个 Evaluator 都先返回标准 `status/reason/data`，Check Aggregator 再汇总。
- 输出最终 `status/reason`，并保留全部 `step_results`：

```json
{
  "case_id": "case_001",
  "check_item": "intent",
  "status": "FAIL",
  "reason": "意图识别不准确",
  "step_results": {
    "intent_rule_script": {
      "status": "PASS",
      "reason": "规则检查通过",
      "data": {}
    },
    "intent_semantic_agent": {
      "status": "FAIL",
      "reason": "语义判断失败",
      "data": {}
    }
  }
}
```

### 8.9 Case Aggregator

- 仅在一个 Case 有多个 Check Result 时执行。
- 首期只允许 Python Script。
- 根据用户 Python 代码判断并合并多个 Check Result，输出顶层 `status` 和完整检查项：

```json
{
  "case_id": "case_001",
  "status": "FAIL",
  "check_items": {
    "intent": {
      "status": "FAIL",
      "reason": "意图识别不准确"
    },
    "i18n": {
      "status": "PASS",
      "reason": "未出现非预期英文"
    },
    "tool_use_count": {
      "status": "FAIL",
      "reason": "tool_use_count = 11 > 10"
    }
  }
}
```

完整 Step、Check 和 Case 聚合输出都作为 Artifact 保留。Excel Writer 如何消费这些结构暂缓设计。

## 9. UI 用户故事

目标用户是企业 Agent 测试人员或开发人员。首期完整用户流程：

1. 创建 Target，配置 FastAPI 地址和 Target 总并发上限。
2. 创建或编辑可复用 Workflow，配置顺序 Parser、Check Item、Evaluator、按需 Aggregator 和可视化输入映射；系统内部保存为 JSON Pointer。
3. 将测试集绑定到一个 Workflow。
4. 创建 Run，选择测试集和 Target，填写超时、Case 并发、连接重试次数和重试间隔。
5. 系统读取第一个 Sheet，生成 CaseRun，并在 Target 总并发约束下与其他 Run 轮询调度。
6. 用户查看 Run、Case、Attempt 和 Step 的实时状态及制品。
7. 用户可取消 Run；服务重启或取消后可手工恢复未完成 Case。
8. 前序链路稳定后再设计和实现结果 Excel 导出。

### 9.1 Workflow 列表与编辑器

- Workflow 管理页布局参考工具管理页，提供新增、刷新、搜索、状态筛选和列表操作。
- 点击新增或编辑后进入独立全屏 Studio；画布采用 React Flow，支持缩放、平移、拖动、连线、小地图和 Edge `+` 快速插入；每次进入画布时使用 Dagre 按从左到右的拓扑自动布局。
- `Start / End` 是系统固定节点，不出现在新增菜单中。用户可新增的节点类型只有 `HTTP / AGENT / LLM / SCRIPT`，页面不得展开成 `Large Language Model` 或 `Python Script`。
- 空白区右键菜单固定包含“添加节点、测试运行、粘贴节点”；节点右键菜单固定包含“运行此步骤、拷贝、删除”。菜单接近视口边缘时必须自动收回到可见范围。
- 单击节点只选中，不打开配置。双击节点在画布中心打开大尺寸编辑器；编辑器可拖动，并支持上、下、左、右和四个对角共八个方向拉伸。
- 支持 Ctrl 点击与 Ctrl 左键拖动框选；选区可用 Ctrl+C/Ctrl+V 复制粘贴，节点名称、说明、运行配置、变量、参数等信息和选区内部连线必须保留。Delete 与 Backspace 都可删除选区，输入框聚焦时不得误触快捷键。
- 图结构编辑最多保留 50 步历史；`Ctrl+Z` 回退，`Ctrl+Shift+Z` 或 `Ctrl+Y` 前进，左上角回退/前进按钮执行相同操作。添加、删除、粘贴、连线、Edge 插入、节点拖动和手工自动布局均进入历史。
- 所有画布节点卡片右上角只保留运行按钮。用户双击节点进入编辑器后，通过独立“参数”页签查看只读运行参数；参数页不得展开或编辑设置页的输出变量。节点配置页标题栏提供运行、保存和关闭；保存只写入前端会话状态并在节点卡片持续显示“已保存”，不调用旧 Workflow API。画布右上角只保留运行、全局变量、保存。
- 节点运行参数页固定使用 `source / name / data` 三列，只展示当前节点执行时可见的“当前节点 + 此前节点实际传入”参数；执行层通过只读 `parameterRecords[]` 提供记录。`source` 格式固定为 `节点名称.input / 节点名称.output`。执行前显示空状态；大 `data` 在列表中只显示摘要，用户按需打开完整详情或对应 Artifact。T13.1 不伪造运行数据，真实记录由后续新版执行协议接入。
- 节点编辑器默认在 1440x900 视口中使用 `1064x814`。节点普通填写字段每行并排两个，每个字段内部统一为标签在左、输入框在右；名称/说明和四个超时重试字段均采用该布局。公共配置模块命名为“输出变量”，每行包含“变量名 + 变量”；第一行显示加号用于追加，新增行显示删除按钮，列表至少保留一行。运行参数追溯页不受此配置影响；编辑器底部不再提供“运行此步骤”。
- HTTP 节点在名称和说明下方单独显示 API 模块：请求方式、URL 和 cURL 导入位于同一行；Headers 与 Params 使用可折叠的 key/value 列表；Body 支持 `none / form-data / x-www-form-urlencoded / raw / binary`。raw 使用 JSON 代码框，并在右上角提供 Beautify。上述配置仅保存在 T13.1 前端会话状态，复制节点时一并保留，不接入旧 Workflow API 或真实 HTTP 执行。
- cURL 导入在浏览器本地解析 Method、URL、查询参数、Headers 和常见 Body，不向外部服务上传命令；导入结果只更新当前 HTTP 节点前端状态。
- T13.1 的保存和测试运行是前端状态演示，不调用旧固定 Workflow API；新版后端保存、执行和字段协议需要下一阶段重新澄清与设计。

### 9.2 字段映射交互

默认交互示例：

```text
来源节点：Parser / response_parser
字段树：tool_calls > 0 > name
页面变量：response_parser.tool_calls[0].name
内部存储：/tool_calls/0/name
```

- 普通用户不需要理解 `/tool_calls/0/name` 的语法。
- 工具开发者可展开高级模式查看和编辑内部 Pointer。
- 输出示例变更后，编辑器必须重新校验所有引用该 Parser 的映射，并明确标记失效字段。

## 10. 验收标准

### 测试集与请求

- 多 Sheet Excel 只执行首个 Sheet，页面明确显示实际 Sheet 和被忽略数量。
- 请求体只包含用户模板渲染结果；系统不注入 `case_id`。
- 含引号、换行和中文的 question 不会破坏 JSON。
- 实际请求快照按原文保存，不脱敏。

### FastAPI 调用

- HTTP 非 2xx、无效 JSON和 `body.code != "200"` 都产生可追踪的 `ERROR`。
- 连接失败按照 Run 参数产生多个独立 Attempt。
- 读取超时不自动重试。
- 业务失败不自动重试。
- 大响应只保存一份完整响应 Artifact，不在数据库和工具上下文中无边界复制。

### 多 Run 调度

- 多个 Run 可以重叠执行。
- 每个 Run 不超过自身 `case_concurrency`。
- 同一 Target 的请求总数不超过 `target_total_concurrency`。
- 多个 Run 按轮询方式获得 Target 槽位，后启动 Run 不会长期饥饿。
- Evaluator 不受工具并发上限约束；压力测试需记录该已知风险的实际资源表现。

### 工作流

- Parser 严格按配置顺序执行。
- 每个 Parser 都有可解析的 JSON 输出示例，缺失或非法时不能保存到 Workflow。
- 用户可以通过来源选择和字段树完成常规输入映射，不需要手工输入 JSON Pointer。
- 字段树选择、分段路径和高级 Pointer 三种方式生成的内部 Pointer 结果一致。
- 上游输出示例删除或变更字段后，引用该字段的节点在保存前被标记为无效。
- Check Item 和其内部 Evaluator 按确认规则并行。
- 单 Evaluator / 单 Check 时没有多余 Aggregator 运行节点。
- 多 Evaluator / 多 Check 时缺少对应 Aggregator 配置会在保存 Workflow 时被拒绝。
- Evaluator 结果结构、状态枚举和系统补充字段均被验证。
- 单个 Evaluator `ERROR` 不阻止其他 Evaluator、其他 Check 和最终 Aggregator。

### 恢复、取消与追溯

- 服务重启后 Run 状态和全部已完成结果仍可读取。
- 手工恢复不会重复执行已完成的业务 `PASS/FAIL/SKIP` Case。
- 取消停止新 Case，终止本地请求等待和工具进程，保留已完成结果。
- 任一结果可追溯到 Target、请求模板、Excel 哈希、Workflow、工具 UUID、工具名称快照、工具类型和代码哈希。

## 11. 开发子任务与恢复进度

每完成一项必须在本文更新状态和验证结果，通过后才能进入下一项。当前 T1-T10 已完成；T11 仍 deferred，下一项为 T12。

| ID | 状态 | 目标 | 输入 | 输出 | 验证方法 | 依赖 |
|---|---|---|---|---|---|---|
| T1 | completed | 建立 SQLite 与 Artifact 基础设施 | 本文状态模型和路径约束 | 数据库迁移、Repository、Artifact 安全路径 API | Repository 单测、路径穿越测试、重启回读测试 | 无 |
| T2 | completed | 实现 Target CRUD 和并发配置 | T1、Target 字段 | Target API、持久化和校验 | CRUD/API 测试、URL/并发边界测试 | T1 |
| T3 | completed | 实现首 Sheet 读取、模板渲染和运行快照 | Excel、`${question}` 规则 | Case 快照和合法 JSON 请求 | 多 Sheet、特殊字符、无 `case_id` 请求测试 | T1 |
| T4 | completed | 实现 FastAPI Connector 与 Attempt | T2、T3、响应协议 | 请求/响应 Artifact、超时和重试记录 | mock FastAPI 覆盖 2xx/非2xx/code/连接失败/读取超时/大响应 | T1-T3 |
| T5 | completed | 实现 Workflow CRUD、绑定、Parser 输出示例和快照 | 工具仓储、固定编排模型 | 可复用 Workflow、测试集绑定、输出结构与映射校验 | 单/多 Evaluator、单/多 Check、输出示例和 JSON Pointer 校验测试 | T1、现有工具仓储 |
| T6 | completed | 扩展 Worker 支持 `inputs` 和标准结果验证 | 现有 `agent_runtime/agent_worker` | Parser/Evaluator/Aggregator 运行契约 | Script/Agent inputs、任意 Parser JSON、Evaluator 枚举/异常测试 | T5 |
| T7 | completed | 实现 Case 工作流执行器 | T4-T6 | Parser、Check、Check Aggregator、Case Aggregator 执行 | 顺序/并行、错误继续、无冗余节点、Artifact 追溯测试 | T4-T6 |
| T8 | completed | 实现多 Run 轮询调度、取消和恢复 | T1、T2、T7 | Scheduler、Target/Run 槽位、取消令牌、手工恢复 | 多 Run 公平性、双重并发上限、重启/取消/恢复测试 | T1、T2、T7 |
| T9 | completed | 实现 Run API 与实时事件 | T8、现有 SSE 模式 | Run/Case/Step 查询、启动、取消、恢复、事件流 | API 集成测试、断线后持久状态读取测试 | T8 |
| T10 | completed | 实现 Target、受限可视化 Workflow、字段选择器和 Run 前端 | T2、T5、T9 | 自动布局编排器、字段树/分段路径/高级 Pointer、运行详情 | 浏览器端到端测试，覆盖映射、校验、正常和异常路径 | T2、T5、T9 |
| T11 | deferred | 澄清并实现 Excel Writer | 稳定的 Case Result 和用户后续决策 | 结果 Excel 副本 | 格式、长文本、原文件不变、打开回读测试 | T7-T10、需再次需求澄清 |
| T12 | in_progress | 完整端到端与回归 | T1-T10 | 测试报告和可复现实验数据 | 真实模型工具矩阵、mock FastAPI 全链路、真实脱敏 FastAPI 联调、现有 `uv run pytest` 回归 | T1-T10 |
| T13.1 | completed | 重做 Workflow 管理入口和全屏高保真画布原型 | 最新 UI 决策、现有桌面前端 | React Flow Studio、四类可新增节点、菜单、Edge 插入、居中八向拉伸编辑器 | 前端专项测试、1440x900 浏览器拖动/菜单/拉伸/视觉检查、全量回归 | T10 |
| T13.2 | pending | 澄清并设计新版画布后端协议和执行边界 | T13.1 原型、后续用户决策 | 可持久化和可执行的新版工作流设计 | 另行拆分，未确认前不得实现 | T13.1、需再次需求澄清 |

### T1 验证记录（2026-07-19）

- 专项测试：`uv run pytest tests/test_run_repository.py tests/test_artifact_store.py -q -rs`，结果 `27 passed, 1 skipped`。
- 全量回归：`uv run pytest`，结果 `133 passed, 3 skipped, 1 warning`。
- 两个既有跳过项是缺少 `AGENT_TEST_*` 凭据的真实模型测试；新增跳过项是 Windows 当前账户没有创建目录符号链接所需权限（WinError 1314）。符号链接逃逸防护代码已实现，普通路径穿越、绝对路径、盘符、UNC、冒号和空字符边界均已执行通过。
- 静态验证：新增 Python 文件通过 `py_compile`，`git diff --check` 和尾随空格扫描通过。
- 结论：T1 可独立验收通过；T2 可以开始。

### T2 验证记录（2026-07-19）

- 专项测试：`uv run pytest tests/test_targets.py tests/test_run_repository.py -q`，结果 `37 passed, 1 warning`。
- 验证范围：v1 到 v2 原地迁移且旧 Run 保留；Target Repository 重启回读；同名不同 UUID；API 创建、列表、详情、更新、删除；HTTP/HTTPS Base URL、单 Host Path、字符串 Headers 和正整数总并发边界。
- 全量回归：`uv run pytest`，结果 `162 passed, 3 skipped, 1 warning`；跳过原因与 T1 相同。
- 静态验证：T2 Python 文件通过 `py_compile`，`git diff --check` 和尾随空格扫描通过。
- 结论：T2 可独立验收通过；T3 可以开始。Target 页面仍按计划留在 T10。

### T3 验证记录（2026-07-19）

- 专项测试：`uv run pytest tests/test_run_preparation.py tests/test_excel_repository.py tests/test_run_repository.py -q`，结果 `24 passed`。
- 验证范围：只读原始顺序首 Sheet并记录忽略列表；Excel 字节哈希、真实行号和用例来自同一版本；引号、换行、中文递归替换后仍为合法 JSON；不替换键名、不注入 `case_id`；拒绝重复 JSON 字段、NaN/Infinity 和非 JSON Python 值。
- 持久化验证：Target、模板、Workflow 占位快照、参数和 Excel 元数据在源对象变化后保持不变；Run 与全部 CaseRun 单事务创建，任一 Case 约束失败时整体回滚；服务重建后可完整回读。
- 全量回归：`uv run pytest`，结果 `175 passed, 3 skipped, 1 warning`；跳过原因与 T1 相同。
- 静态验证：T3 Python 文件通过 `py_compile`，`git diff --check` 和尾随空格扫描通过。
- 结论：T3 可独立验收通过；T4 可以开始。

### T4 验证记录（2026-07-19）

- 专项测试：`uv run pytest tests/test_connector.py tests/test_artifact_store.py tests/test_run_repository.py tests/test_targets.py -q`，结果 `74 passed, 1 skipped, 1 warning`；跳过项仍是 Windows 符号链接权限。
- 成功链路：以内存 ASGI FastAPI 运行完整 `POST /api/agent/invoke`，确认 HTTP 实际发送字节与未脱敏 `request.json` 完全一致，整数 `code: 200` 被规范为字符串，并将超过 1 MB 的完整响应流式保存为唯一 Response Artifact。
- 错误链路：mock 逐项覆盖非 2xx、非法 JSON、非对象/缺少 `code`、业务 `code != 200`、连接失败、连接超时、读取超时；只有连接阶段错误按配置重试，每次生成独立 Attempt，读取超时和业务失败均只调用一次。
- 恢复与制品：手工重跑同一 Case 复用完全相同的 Request Artifact 并延续 Attempt 序号；异步流失败不留下部分 Response 或临时文件；失败请求/响应转为长期保留分类。
- T2 回补：专项测试发现 `httpx` 不接受非 ASCII Header 值，Target 模型现已在保存前拒绝并返回校验错误，相关 T2/T3 夹具已回归通过。
- 全量回归首次运行因两个旧 T3 夹具仍使用中文 Header 而出现 `192 passed, 2 failed, 3 skipped`；修正夹具并执行受影响联合测试 `59 passed` 后，最终全量结果为 `194 passed, 3 skipped, 1 warning`。
- 静态验证：T4 Python 文件通过 `py_compile`，`git diff --check` 和尾随空格扫描通过。
- 限制：用户提供的成功响应附件被截断，不能作为完整 JSON 解析；因此当前只完成协议等价 mock FastAPI 联调，尚未宣称真实内网 FastAPI 联调通过。获得完整脱敏成功响应后需在 T12 补测。
- 结论：T4 的可重复验收范围通过；T5 可以开始。

### T5 验证记录（2026-07-19）

- 专项测试：`uv run pytest tests/test_workflows.py tests/test_tool_registry.py tests/test_tool_transfer.py tests/test_run_repository.py -q`，最终结果 `38 passed, 1 warning`。
- 持久化：v2 数据库原地升级到 v3，新增 Workflow 与测试集一对一绑定；重启回读、完整更新、无效外键拒绝、删除 Workflow 自动解除当前绑定均通过。
- 拓扑：单 Evaluator/单 Check 不允许冗余 Aggregator；多 Evaluator/多 Check 缺少对应 Script Aggregator 时拒绝；全局 `step_id`、`check_item` 重复、工具缺失和 Agent Aggregator 均能定位到具体节点。
- 映射：RFC 6901 根值、`~0/~1`、对象字段和数组索引通过；Parser 只能读取原响应或更早 Parser，Evaluator 可读取全部 Parser；Parser 示例字段删除后 Workflow 实时显示无效并禁止更新/新绑定。
- 快照：Run 可冻结 Workflow、引用工具完整代码/参数/明文密钥/元数据和 SHA-256；工具后续修改不影响已生成快照。Parser `output_example` 支持任意 JSON（包括显式 `null`）并随 ZIP manifest 保留。
- 稳定性修复：v3 首轮迁移测试发现多个 Repository 实例同时首次设置 WAL 的路径级初始化竞争，已改为同进程按数据库路径共享锁。两次 Windows 工具目录重命名出现瞬时 WinError 5，已增加有限重试和确定性测试，ZIP 漏导入回归通过。
- 全量回归首次为 `211 passed, 1 failed, 3 skipped`（瞬时目录重命名导致一个 ZIP 工具未导入）；加入重试后最终为 `213 passed, 3 skipped, 1 warning`。
- 静态验证：T5 Python 文件通过 `py_compile`，`git diff --check` 和尾随空格扫描通过。
- 结论：T5 可独立验收通过；T6 可以开始。Workflow 页面仍按计划留在 T10。

### T6 验证记录（2026-07-19）

- 专项测试：`uv run pytest tests/test_workflow_runtime.py tests/test_agent_runtime.py tests/test_tool_streaming.py tests/test_tools.py -q`，最终结果 `76 passed, 1 warning`。
- Worker：Script/Agent 的同步和 SSE 流式协议均可注入隔离的顶层 `inputs` 字典；无 inputs 时保持空字典兼容；非法顶层类型、set、NaN 在启动子进程前拒绝；既有超时、中断、子进程树终止和编辑页接口未回归。
- 严格 JSON：正式编排可关闭旧 `repr()` 回退，自定义对象等不可序列化 response 产生明确执行错误；专项首轮发现 Pydantic 会把 NaN 静默转换为 `null`，现已在序列化前递归拒绝 NaN/Infinity，重跑通过。
- 结果契约：Parser 接受 null、标量、数组和对象等任意标准 JSON；Evaluator 只接受 `PASS/FAIL/ERROR/SKIP + reason + 可选 data`，拒绝工具自行返回 `case_id/check_item/step_id/evaluator_id`；系统函数统一补充上下文并保留全部 Step/Check 明细。
- Aggregator：Check Aggregator 必须返回 `status/reason`；Case Aggregator 必须返回 `status` 且 reason 可选，Evaluator/Check 明细由系统组装，不能因用户代码遗漏而丢失。
- 全量回归：`uv run pytest`，结果 `243 passed, 3 skipped, 1 warning`；跳过原因与 T1 相同。
- 静态验证：T6 Python 文件通过 `py_compile`，`git diff --check` 和尾随空格扫描通过。
- 结论：T6 可独立验收通过；T7 可以开始。

### T7 验证记录（2026-07-19）

- 专项测试：`uv run pytest tests/test_case_executor.py tests/test_connector.py tests/test_workflow_runtime.py tests/test_run_repository.py -q`，结果 `63 passed`。
- v4 Migration：StepRun 新增 `execution_number`，同一 Case/Stage/`step_id` 可按 1、2…追加执行；从含旧 Step 与 Artifact 外键的 v3 数据库升级后记录和关联完整保留，失败 Case 重跑不会覆盖历史。
- 顺序与并行：Parser 严格串行且后一个可读取前一个输出；不同 Check 并行，同一 Check 内 Evaluator 并行，可控 Runner 实测同时活动数达到 3；Aggregator 在扇入之后运行。
- 错误继续：Evaluator 进程/结构错误转成标准 `ERROR` 且同组和其他 Check 继续；Check Aggregator 错误生成保留全部 Step 的 `ERROR` Check Result，Case Aggregator 仍执行；Case Aggregator 自身错误则 Case 执行状态为 `ERROR` 并保留已有 Check 明细。
- 状态语义：最终业务 `FAIL` 的 Case 执行状态为 `SUCCEEDED`、业务状态为 `FAIL`；单 Evaluator/单 Check 只有一个实际 StepRun，无冗余 Aggregator；Parser/Connector 致命错误停止后续步骤。
- 追溯：真实 Script 子进程链路验证 inputs 映射与日志；每个实际工具节点记录 UUID/名称/类型/代码哈希、日志和结果 Artifact，Check/Case 结果另存，超过 1 MB 的原响应仍只有一个完整 Response Artifact。
- 保留：最终 `FAIL/ERROR` 会把请求、响应和成功 Parser 等临时制品提升为失败长期保留，Case 最终结果始终为 `FINAL_LONG_TERM`。
- 全量回归：`uv run pytest`，结果 `251 passed, 3 skipped, 1 warning`；跳过原因与 T1 相同。
- 静态验证：T7 Python 文件通过 `py_compile`，`git diff --check` 和尾随空格扫描通过。
- 结论：T7 可独立验收通过；T8 可以开始。

### T8 验证记录（2026-07-19）

- 专项测试：`uv run pytest tests/test_scheduler.py tests/test_case_executor.py tests/test_connector.py tests/test_run_repository.py -q`，结果 `42 passed`。
- 双重并发：两个不同时刻启动的 Run 实测各自整 Case 峰值不超过 `case_concurrency`，同一 Target 的 HTTP 请求峰值不超过 `target_total_concurrency`；Target 槽位只包围 Connector，工具阶段不占槽且没有新增 Evaluator 限制。
- 公平性：先启动长 Run 后再启动短 Run，Target 等待队列按 Run 轮询，后启动 Run 在前一 Run 全部请求完成前获得槽位。若同一 Target 的重叠 Run 冻结了不同并发值，活动期间采用两者最小值，确保不突破任何 Run 快照的上限；低上限 Run 结束后恢复较高值。
- 取消：停止派发未开始 Case、取消活动 asyncio 任务；真实 Response 流等待取消后 Attempt=`CANCELLED` 且无部分响应文件，真实 Script Worker 睡眠取消后子进程终止、Step/Case/Run 均为 `CANCELLED`。外部 FastAPI 已触发的企业 Agent 仍无法保证远端终止。
- 恢复：Scheduler 构造后不自动扫描或启动；手工恢复选择 `QUEUED/ERROR/CANCELLED` 和服务中断遗留 `RUNNING`，跳过所有执行 `SUCCEEDED` Case，包括业务 `FAIL`；旧 RUNNING Attempt/Step 收口为 `service_interrupted` 后追加执行记录。
- Run 结论：全部 Case 执行成功时 Run=`SUCCEEDED`，业务结论按 ERROR/FAIL/PASS/SKIP 汇总；仍含未成功 Case 时 Run 执行和业务状态均为 `ERROR`。
- 全量回归：`uv run pytest`，结果 `259 passed, 3 skipped, 1 warning`；跳过原因与 T1 相同。
- 静态验证：T8 Python 文件通过 `py_compile`，`git diff --check` 和尾随空格扫描通过。
- 结论：T8 可独立验收通过；T9 可以开始。

### T9 验证记录（2026-07-19）

- 持久化专项：v4 数据库原地升级到 v5；测试集请求模板支持对象、数组、字符串、数字、布尔值和 `null` 等任意标准 JSON 根值，重启回读和删除通过，NaN/Infinity/非 JSON Python 值在落库前拒绝。T9.1 联合测试结果 `73 passed`。
- 实时事件专项：每个 SSE 订阅者使用独立临时队列；订阅前事件直接丢弃，多订阅者按序广播，断开即释放，终态自动结束，keepalive 与取消等待均通过；原有工具 SSE 联合回归结果 `11 passed`。
- API 与端到端：创建 Run 保持 `QUEUED` 且没有 Attempt；冻结首 Sheet/Excel 哈希、Target、请求模板、Workflow 和工具代码；真实 Scheduler 通过内存 ASGI FastAPI 完成两条 Case 的 HTTP 调用和真实 Script Evaluator 子进程，确认请求不含 `case_id`，Run 最终为 `SUCCEEDED/PASS`。
- 追溯与恢复：Run/Case 详情可读取 Attempt、Step 和 Artifact；Artifact 下载经过 SQLite 归属校验与 ArtifactStore 安全路径；终态 SSE 不重放，服务对象重建后详情仍从 SQLite 完整回读；指定一个异常 Case 手工恢复只追加该 Case 的 Attempt/Step，不重复执行已成功 Case。
- 跨模块专项：`uv run pytest tests/test_run_repository.py tests/test_run_preparation.py tests/test_workflows.py tests/test_connector.py tests/test_case_executor.py tests/test_scheduler.py tests/test_artifact_store.py tests/test_run_events.py tests/test_runs_api.py -q`，结果 `111 passed, 1 skipped, 1 warning`；跳过项是 Windows 符号链接权限。
- 全量回归：`uv run pytest -q`，结果 `283 passed, 3 skipped, 1 warning`；两个跳过项缺少 `AGENT_TEST_*` 真实模型凭据，另一个是 Windows 当前账户没有创建目录符号链接权限。
- 静态验证：T9 Python 文件通过 `py_compile -W error`，`git diff --check` 通过；仅有 Git 对既有 `web/app.py` 行尾格式的 CRLF 提示，不是代码错误。
- 限制：真实内网 FastAPI 仍未提供可解析的完整脱敏成功响应，本阶段通过协议等价的内存 ASGI FastAPI 验证，不宣称真实环境联调完成；该项继续留在 T12。
- 结论：T9 可独立验收通过；T10 可以开始。

### T10 验证记录（2026-07-19）

- 子任务按 Target、Workflow 列表、编排器、字段映射、Run 创建、Run 详情和浏览器 E2E 顺序独立验证；T10.1-T10.5 的阶段结果依次为 `37 passed`、`48 passed`、`26 passed`、`50 passed`、`23 passed`，T10.6 Run 详情联合测试为 `27 passed`。
- Target：真实页面完成创建、编辑、读取和删除；Base URL、Path、Headers 数量和 Target 总并发持久化正确。
- Workflow：真实页面完成 Parser、两个 Evaluator、自动出现的 Check Aggregator 插槽和 Script Aggregator；Parser 使用分段路径生成 `/data/answer`，Evaluator 从 Parser `output_example` 字段树选择 `/answer`；保存、复制、删除副本和测试集绑定均通过。
- Run 正常链：请求模板只发送 `question/username`，不注入 `case_id`；超时、Case 并发、连接重试和间隔均在创建时指定；创建后保持 `QUEUED`，启动前先连接无回放 SSE。
- Run 异常与恢复链：本地 FastAPI stub 停止后 10 个 Case 全部进入可恢复 `ERROR`；恢复服务后页面“恢复全部未完成”把 Run 收口为 `SUCCEEDED/PASS`。`case_001` 显示 `Attempts 2`，第一次为 `connect_error`，第二次 HTTP/body.code 均为 200；Parser、两个 Evaluator 和 Check Aggregator 全部 `SUCCEEDED/PASS`。
- 追溯：业务 `ERROR` 但执行 `SUCCEEDED` 的 Case 不进入恢复集合；Attempt/Step/Artifact 标签、Artifact 安全下载和 SSE 终态更新均在真实浏览器验证。
- 浏览器回补：E2E 发现输入映射参数名只依赖 `change` 且重绘后回退，已改为 `input` 时增量更新草稿键；同时清理三个重复 DOM ID。桌面 1440×900 下 Run 详情和 Workflow 编辑器无重叠、页面级横向溢出或重复 ID。后续业务决策明确系统不支持移动端，相关断点和移动端测试已删除。
- 专项回归：`uv run pytest tests/test_execution_frontend.py tests/test_targets.py tests/test_workflows.py tests/test_runs_api.py tests/test_scheduler.py tests/test_case_executor.py -q`，结果 `72 passed, 1 warning`；`node --check` 和 `git diff --check` 通过。
- 全量回归：`uv run pytest -q`，结果 `287 passed, 3 skipped, 1 warning`。跳过和 warning 原因与 T9 相同。
- 限制：浏览器 E2E 使用本地协议等价 FastAPI stub，临时 Target/Workflow/工具/Run/Artifact 已清理；真实内网 FastAPI 仍未完成联调，不宣称真实环境通过。
- 结论：T10 可独立验收通过；T11 保持 deferred，下一项为 T12。

### T12 真实模型工具矩阵验证记录（2026-07-19）

- 供应商与模型：DeepSeek `deepseek-v4-pro`、DashScope `qwen3.7-max`；中转站按最新业务确认不测试。DashScope 账号的只读模型列表确认 `qwen3.7-max` 为有效 ID，原候选 `qwen-3.7-max` 不存在。
- 场景矩阵：两个供应商分别通过单 Script、单 Agent、多 Script、多 Agent、双 Script + 双 Agent，共 10 个场景行。每个工具均经过 `/api/tools` 创建、更新、读取、流式启动、SSE 完成事件和删除清理。
- Agent 能力：每个 Agent 包含两个本地 LangChain tool；`inspect_candidate` 首次固定失败并由 `ToolRetryMiddleware` 重试；自定义 `AuditMiddleware` 记录调用前、异常和成功；最终结果由 Pydantic + `ToolStrategy` 约束为标准 `status/reason/data`。DeepSeek 与 Qwen 均显式关闭思考模式，避免思考模式拒绝结构化输出所需的强制 `tool_choice`。
- 密钥边界：只从 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY` 读取并注入单次运行请求，不写测试代码、项目配置或工具 manifest；失败上下文中的凭据对象固定显示为 `***`，每个 Agent 运行后还会读取 manifest 断言真实 key 不存在。
- 分阶段验证：矩阵/模板静态测试 `1 passed`；双 Script `2 passed`；双 Agent `2 passed`；双 Script + 双 Agent `2 passed`；DeepSeek/DashScope 单 Agent 分别通过。
- 带两组真实凭据的全量回归：`uv run pytest -q` 结果 `298 passed, 1 skipped, 1 warning`，耗时 87.66 秒。跳过项为 Windows 符号链接权限，warning 为既有 Starlette/httpx 弃用提示。
- 限制：本记录证明真实模型工具管理与联调链路通过，不等同于企业 Agent 的真实 FastAPI 目标链路通过。真实内网 FastAPI 尚未植入当前系统，也没有完整可解析的脱敏成功响应，因此 T12 保持 `in_progress`，不得宣称真实环境端到端完成。

### T13.1 新版 Workflow Studio 前端原型验证记录（2026-07-20）

- 架构：现有页面不整体迁移框架，只为全屏画布新增隔离的 React 18 + React Flow 子应用；工作流管理列表仍由原生页面负责。画布依赖 `@xyflow/react`、`lucide-react`、`react-rnd`、`parse-curl` 和 `shellwords`，通过 esbuild 输出独立 JS/CSS bundle。
- 节点与菜单：`Start / End` 作为系统固定节点；空白区“添加节点”和 Edge `+` 均只展示 `HTTP / AGENT / LLM / SCRIPT`。空白区和节点右键菜单逐项实际点击通过，复制后粘贴由禁用变为可用，Edge 插入后节点与边数量均按预期增加。
- 节点视觉：6 个初始节点默认均为 `1px` 中性灰轮廓，不使用类型色；点击后只有当前选中节点显示 `1px` 绿色边框、`2px` 绿色 outline、浅绿到白色的内侧渐变和绿色光环。浏览器计算样式确认选中前后宽高完全一致。Agent 运行完成后左下角显示 `SUCCESS`，取消选中后保持成功文案但轮廓恢复中性灰，证明轮廓只表达选中态。
- 画布交互：真实浏览器验证节点拖动、连线、小地图、自动布局和测试运行状态；测试运行最终 10 个演示节点全部进入完成态。菜单会限制在桌面视口内，底部右键不会裁切二级节点列表。
- 节点编辑：单击不弹窗、双击打开；默认编辑器为 `1064x814`，中心点在桌面视口的画布中心，受较小视口可用高度约束时自动收缩。8 个方向拉伸手柄均存在，窗口保持在画布边界内；底部“运行此步骤”已删除。
- 名称与说明并排，节点类型字段删除。普通填写字段统一为左侧 `64px` 标签加右侧自适应输入框，每行并排两个字段；重试区 4 个输入均使用相同布局。“输出变量”固定为同一行的变量名和变量两个输入，不含参数行和增删按钮。
- 输出变量：HTTP 与 Agent 节点真实浏览器初始均为一行两个输入和一个加号。HTTP 首行填写 `response / $.data` 后点击加号，变为两行四个输入、一个加号和一个删除按钮；删除新增行后恢复一行且首行值完整保留。编辑器内容区无横向溢出，浏览器控制台错误为 0。
- HTTP API 模块：1440x900 浏览器实测 API 与 HEADERS 文字起点均为 `x=225`；请求方式下拉为 `96x34`、左边界 `x=284`，仅图标的 cURL 导入按钮为 `34x34`，URL 输入宽度 `803px`。导入带 Method、查询参数、重复 Headers 和 JSON Body 的 cURL 后，PATCH、URL、Headers、Params 与 raw Body 均正确回填；Headers 折叠后输入行移除，重新展开后恢复。Beautify 能格式化合法 JSON，非法 JSON 显示行内错误；复制粘贴 HTTP 节点后全部 API 配置保持一致。编辑器内容区和页面横向溢出均为 0，浏览器控制台错误为 0。
- 选区与快捷键：Ctrl 点击多选两个节点通过；Ctrl+C/Ctrl+V 后节点数 `6 -> 8`、选区内部边数 `6 -> 7`，两个节点名称各保留两份；Backspace 后恢复 `6/6`，再用 Delete 删除一个节点后为 `5/4`。浏览器自动化无法在拖拽过程中持续发送 Ctrl 修饰键，因此 Ctrl 框选分支完成代码与静态回归，但本轮未完成自动化实拖覆盖。
- 分层操作：6 个初始画布节点卡片各自只保留运行按钮。节点配置页标题栏显示运行/保存/关闭；配置页运行实际完成当前节点演示执行，独立“参数”页签打开只读参数列表，保存后标题栏按钮进入已保存态且节点卡片持续显示“已保存”。画布保留运行/全局变量/保存，全局变量面板可打开。
- 布局与历史：首次进入画布后 6 个初始节点经 Dagre 自动布局且无重叠；删除节点后 `Ctrl+Z` 恢复，左上角前进再次删除、回退再次恢复，按钮禁用状态与历史栈一致。
- 自动化与视觉：`uv run pytest tests/test_execution_frontend.py -q` 结果 `8 passed, 1 warning`；桌面浏览器检查无控制台错误、页面横向溢出为 0，节点类型和编辑器边界正确。
- 表单布局回归：1440x900 浏览器实测编辑器为 `1064x814`；名称/说明和重试次数/重试间隔/延迟执行/重复执行均为标签左、输入框右且垂直居中，编辑器内容区横向溢出为 0。每行输出变量保持变量名和值两个输入框及一个操作位，浏览器控制台错误为 0。
- 运行参数页回归：双击 HTTP 节点打开编辑器后，“参数”页签展示 `source / name / data` 三列表头和执行前空状态。1440x900 下表格、编辑器和页面横向溢出均为 0，返回设置页后 HTTP 配置及输出变量仍独立保留；浏览器控制台错误为 0。真实运行记录、详情和 Artifact 跳转需等待新版执行协议后补端到端验证。
- 全量回归：`npm run build` 成功；`uv run pytest -q` 结果 `295 passed, 7 skipped, 1 warning`；`node --check` 和 `git diff --check` 通过。跳过项和 warning 与项目既有基线相同。
- 限制：画布保存、测试运行和节点配置当前均为前端本地演示，尚未接入新版后端协议；不能用于实际 Run，也不能据此宣称新版工作流端到端通过。
- 结论：T13.1 可独立验收通过；进入 T13.2 前必须重新澄清后端持久化、节点执行和数据传递边界。

## 12. 下一次任务的起点

1. 先检查 Git 状态，保留当前所有用户改动。
2. 通读本文和当前代码，确认本文是否仍是最新业务事实来源。
3. 若继续新版画布，下一步是 `T13.2`，必须先澄清后端持久化、节点执行和数据传递边界；不得把 T13.1 的前端本地状态直接套入旧固定 WorkflowDefinition。若转回真实环境联调，则继续 `T12`。
4. 每完成一个子任务，立即执行表格中的验证方法，并把状态、结果和遗留问题写回本文。
5. Excel Writer 仍为 `deferred`，不得在没有新一轮需求澄清时自行设计。
