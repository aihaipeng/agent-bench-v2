# Workflow Studio 节点内聚与执行协议计划（T13.2）

## T13.11 Workflow 创建元数据与顶部说明（已完成）

### 业务背景与目标

- Workflow 作者需要在进入画布前明确名称和整体说明，并在编排过程中持续看到这两项元数据。
- 说明只描述整个 Workflow，不承担画布分区注释职责，因此不引入说明节点、连线、复制粘贴或 DAG 特例。

### 已确认边界

- 点击“新增工作流”先打开名称/说明弹窗；名称必填且最长 120 字符，说明可空且最长 2000 字符。
- 画布顶部左侧显示名称，中间显示单行说明摘要，右侧保留运行、全局变量、中断和保存操作。
- 名称和说明均为展示态，双击后进入编辑；名称使用单行输入，说明使用轻量多行浮层。
- 名称按 Enter 或失焦、说明失焦时，通过独立元数据接口立即持久化；该接口不接收或改写节点、连线和全局变量，也不触发完整 DAG 校验。
- 暗色主题下 Workflow 顶栏仍固定使用浅色控件；名称悬停和说明编辑器不得继承全局深色输入背景，也不显示原生黑色提示框。

### 验收与验证（2026-07-23）

- API 专项覆盖名称/说明规范化、空名称拒绝、缺失 Workflow、图数据保持不变，以及不完整图仍可独立更新元数据。
- 浏览器 E2E 覆盖新增弹窗、名称必填、创建后自动落库、名称双击编辑、说明双击编辑、失焦保存及刷新后列表回读；临时 Workflow 已删除。
- 暗色主题真实页面计算样式：说明编辑器与 textarea 背景均为 `rgb(255, 255, 255)`，文字为 `rgb(23, 32, 51)`，`color-scheme` 为 `light`；名称悬停不再出现黑色背景或原生黑色提示框。
- 浏览器控制台错误和警告均为 0；前端构建、Python 编译、JavaScript 语法检查和 `git diff --check` 均通过；受影响回归为 `102 passed, 1 warning`，全量回归为 `222 passed, 6 skipped, 1 warning`。

> 状态：T13.1 前端高保真原型和回归已完成；T13.2 Step 11 已完成验收并推送到 GitHub。按最新业务决策，工具管理/工具模板体系及所有画布耦合已彻底删除，工具节点完全在 Workflow 中定义；LLM 节点已接入模型管理引用、任意 JSON 高级参数和框架无关的 OpenAI-compatible 网关内核。新版 Workflow 持久化与 DAG 真实执行 API 仍尚待单独确认和实现。
>
> 更新时间：2026-07-23
>
> 范围：新版全屏 Workflow Studio 和新的工具模板体系。旧固定 Workflow、旧 Run 页面/API/执行链以及当前 Script / Agent 工具协议将被删除，不提供兼容迁移。
>
> 事实来源优先级：用户最新确认 > 本计划的“已确认决策” > `docs/enterprise-agent-test-orchestration.md` 中的既有规则。未列为“已确认”的内容不得直接实现。

## T13.10 LLM 日志 Token 与模型行布局（已完成）

### 业务背景与目标

- Workflow 作者需要在不展开日志详情的情况下比较单次 LLM 调用成本，同时快速扫描时间、状态、耗时和最终结果概览。
- LLM 设置页需要把模型选择与流式开关放在同一视觉层级，减少纵向占用并明确流式模式属于当前模型调用配置。

### 已确认边界

- 仅 LLM 日志摘要行新增 Token 列，顺序固定为“时间 / 状态 / 耗时 / Token / 概览”；HTTP、AGENT、SCRIPT 保持原五列布局。
- Token 优先读取 `usage.total_tokens`；缺失时依次兼容 OpenAI 的 `prompt_tokens + completion_tokens` 和 Anthropic 的 `input_tokens + output_tokens`。无 usage、失败、中断以及不解析 usage 的流式响应统一显示 `-- tokens`。
- Token 列固定为 `112px`，概览继续使用剩余宽度并在过长时省略，动态内容不得推动时间、状态和耗时列。
- LLM 设置页使用同一行两列布局：左侧为模型字段，右侧为“流式输出 + 开关”；开关固定 `34x19`，系统提示词从下一行开始。流式执行、usage 持久化和输出变量规则不变。

### 验收与验证（2026-07-23）

- 真实持久化日志：复用本机 Workflow“HTTP GET 9000 验证”的 DeepSeek LLM 记录，4 条摘要依次显示 `-- tokens / 166 tokens / -- tokens / 162 tokens`，未发起新的供应商调用，也未保存或修改 Workflow。
- 日志布局：真实成功行计算网格为 `18px 130px 66px 80px 112px 562px`；Token 位于耗时和概览之间，日志面板及页面横向溢出均为 0，浏览器控制台错误为 0。
- 设置布局：1440x900 下模型选择器和流式开关处于同一行，间距 `24px`；开关为 `34x19`，两者垂直中心偏差为 0，设置面板和页面横向溢出均为 0。
- 构建与回归：`npm run build`、Python `compileall`、Workflow bundle `node --check` 和 `git diff --check` 均通过；`uv run pytest tests/test_execution_frontend.py tests/test_llm_node_runs.py tests/test_model_gateway.py -q` 结果 `25 passed, 1 warning`；全量 `uv run pytest -q` 结果 `221 passed, 6 skipped, 1 warning`。6 项跳过为未注入真实供应商环境变量的 live 用例，warning 为既有 Starlette/httpx 弃用提示。

## T13.6 HTTP 节点界面与日志收敛（已完成）

### 业务目标与场景

- Workflow 编排人员通过系统 HTTP 执行器配置并运行标准请求，不需要在 HTTP 节点中查看或维护 Python 代码。
- HTTP 节点用于对接 FastAPI 或真实企业 Agent 环境；排查调用问题时只关注实际发出的请求和收到的响应，不在日志详情中混入执行器 stdout、stderr、traceback 或其他运行元信息。

### 已确认边界

- HTTP 节点配置页只保留“设置 / 日志”两个页签，删除 HTTP 的“代码 / 参数”页签；AGENT、LLM、SCRIPT 的页签规则不受影响。
- “设置”继续承载 Method、URL、Headers、Params、Body、运行配置和输出变量；本次不删除 HTTP 请求本身的 Query Params，也不改变输出变量提取协议。
- 日志列表摘要继续显示状态、运行时间和耗时；展开详情只显示“原始请求 / 原始响应”。底层运行记录和变量提取所需数据继续持久化，不因界面收敛而丢失。
- 原始请求和原始响应保持原有深色原始文本块样式，每个模块标题右侧各提供一个整段复制按钮；不拆成 JSON 字段表，也不提供逐字段复制按钮。
- 原始日志文本显式允许鼠标选中。存在浏览器文本选区时，原生 `Ctrl+C` 优先于画布节点复制；没有文本选区时继续执行既有节点复制。
- HTTP 原始请求采用 Postman 式可读布局，分为请求行、Headers、Params 和 Body。RAW Body 是合法 JSON 字符串时解析并缩进显示，不再把 JSON 作为字符串二次转义；非 JSON Body 保持原文。
- “复制原始请求”复制 Postman 式格式化文本，而不是持久化层的 JSON 包装文本；实际发出的请求、持久化记录和输出变量提取仍使用原始结构，不受展示格式影响。
- HTTP 仍由标准 HTTP 执行器执行，不支持或恢复 HTTP Python 代码模式。
- 新建 HTTP 节点的 Headers 默认包含可编辑、可删除的 `Content-Type: application/json`。该默认值只在创建节点时写入；已有节点、cURL 导入结果和用户手工删除后保存的空 Headers 均不自动补回。

### 子任务与验证

1. **HTTP 编辑器页签收敛**（已完成，2026-07-22）
   - 输出：HTTP 只显示“设置 / 日志”。
   - 验证结果：`uv run pytest tests/test_execution_frontend.py -q` -> `8 passed, 1 warning`。
2. **HTTP 日志详情收敛**（已完成，2026-07-22）
   - 输出：HTTP 展开详情只渲染原始请求和原始响应。
   - 验证结果：`uv run pytest tests/test_execution_frontend.py tests/test_workflow_node_runs.py -q` -> `18 passed, 1 warning`；成功、非 2xx 和配置失败的既有执行记录行为均通过。
3. **真实 GET 端到端验收**（已完成，2026-07-22）
   - 在桌面画布保存并运行 `GET http://127.0.0.1:9000/chat/1`，节点状态为 `SUCCESS`，响应 HTTP 200，返回订单 `ORD-20260722-0001`。
   - 展开日志确认页签仅为“设置 / 日志”，详情标题恰好为“原始请求 / 原始响应”，请求 Method 和 URL 正确；页面横向溢出为 0，浏览器控制台错误为 0。
   - 验收 Workflow 名称为“HTTP GET 9000 验证”，保留在本机数据库供人工查看。
4. **完整回归**（已完成，2026-07-22）
   - `npm run build`、`uv run python -m compileall -q execution web tests` 和 `git diff --check` 均成功。
   - `uv run pytest -q` -> `219 passed, 6 skipped, 1 warning`；6 项为未注入真实供应商凭据的 live 测试，warning 为既有 Starlette/httpx 弃用提示。
5. **HTTP 日志复制**（已完成，2026-07-22）
   - 输出：原始请求和原始响应各一个模块复制按钮；原始文本可由用户鼠标选中后执行原生 `Ctrl+C`；恢复原有文本块视觉，不保留试验性的逐字段表格。
   - 专项验证：`uv run pytest tests/test_execution_frontend.py tests/test_workflow_node_runs.py -q` -> `19 passed, 1 warning`；`npm run build` 成功。
   - 浏览器验证：两个模块复制按钮均唯一，复制内容分别保留完整请求和响应；页面显示仍只有原始请求和原始响应两个模块。
   - 未覆盖：内置浏览器自动化无法合成原生文本拖选，未自动读取鼠标选区；已验证日志块计算样式为 `user-select: text`，且键盘和 copy 事件在存在文本选区时不会触发节点复制。需要人工鼠标拖选完成最终体验确认。
6. **HTTP 请求 Postman 分区展示**（历史完成，已被第 10 项替代）
   - 输出：请求行、Headers、Params、Body 分区；JSON RAW Body 解析为格式化 JSON；模块按钮复制格式化后的可读请求。
   - 真实历史记录验证：复用既有 `POST http://127.0.0.1:9000/admin/users` 运行记录，页面显示 `POST`、Headers、空 Params 和 `BODY · RAW`；Body 为缩进后的 `{"username": "users"}`，不存在 `\"`。
   - 复制验证：剪贴板首行为 `POST http://127.0.0.1:9000/admin/users`，包含 Headers、Params、Body 三段及可读 JSON，不包含转义引号。
   - 页面横向溢出为 0，浏览器控制台错误为 0；专项 `19 passed, 1 warning`，最终全量 `219 passed, 6 skipped, 1 warning`。
7. **新建节点默认 JSON Header 与 API Mock 全面验证**（已完成，2026-07-22）
   - 输出：`defaultHttpConfig()` 新建 Headers 为 `Content-Type: application/json`，源码契约纳入 `tests/test_execution_frontend.py`；cURL 导入和已有节点加载路径不变。
   - Mock 基线：确认 PID `28208` 监听 `127.0.0.1:9000`，按 OpenAPI 真实执行 18 个请求，覆盖 GET/POST/PUT/PATCH/DELETE、Query、JSON Body、Bearer Header、401/422、业务 `code=404` 和慢响应，全部符合 Mock 契约。
   - 节点 API：通过 `127.0.0.1:8010` 创建临时 Workflow 并执行 14 个 HTTP 节点场景，覆盖 `${变量名}` 在 URL/Header/Params/Body 中替换、输出变量提取、原始错误响应、连接失败、空 URL、慢响应和中断；结果全部符合预期，临时 Workflow 已删除。
   - 根因对照：同一 `POST /orders` RAW JSON 带默认 Header 时 HTTP 200、节点 `SUCCESS`；删除 Header 后 FastAPI 将 Body 识别为字符串并返回 HTTP 422、节点 `FAILED`。
   - 浏览器 E2E：新建节点默认项可编辑；真实 POST 日志按请求行、Headers、Params、格式化 Body 展示且两个模块复制正确；删除默认项并保存、退出、重新打开后 Headers 仍为空，未自动回填；验收临时 Workflow 已删除。
   - 最终回归：HTTP/前端专项 `19 passed, 1 warning`；`npm run build`、Python `compileall`、Workflow bundle 语法检查和 `git diff --check` 均成功；全量 `219 passed, 6 skipped, 1 warning`。
   - 未覆盖与已知缺口：当前 API Mock 的 `/upload` 仍声明 JSON Body，不能作为 form-data、x-www-form-urlencoded 或 binary 成功链路；`retryCount / retryInterval / delayExecution / repeatExecution` 当前只由前端保存，节点执行后端尚未消费，本阶段不擅自补定义执行语义。
8. **设置字段与 HTTP 日志标题可见性**（已完成，2026-07-23）
   - 业务目标：节点编辑器固定为白色设置面板；无论全局亮暗主题，名称、说明、模型、HTTP、运行配置和输出变量等所有字段标题都必须清晰可见。
   - 修复：设置页章节标题、标签页、字段名、HTTP key/value、Body 类型、折叠项及输出变量标签统一使用 `--wf-heading: #111827`；删除暗色主题将该变量覆盖为浅色的规则，避免白底白字。
   - 日志：HTTP “原始请求 / 原始响应”标题统一为 `12px / 700`，正文和深色日志内容区保持原样。
   - 浏览器 E2E：在 `data-theme=dark` 且编辑器背景 `rgb(255, 255, 255)` 的真实页面中，HTTP、LLM、重试和输出变量字段计算颜色均为 `rgb(17, 24, 39)`；两个日志标题均为 `12px / 700`，页面及面板横向溢出为 0，控制台错误为 0。
   - 回归：主题与前端专项 `13 passed, 1 warning`；`npm run build`、Python `compileall`、Workflow bundle 语法检查和 `git diff --check` 均成功；全量 `220 passed, 6 skipped, 1 warning`。
9. **HTTP 原始日志正文放大 30%**（已完成，2026-07-23）
   - 范围：只放大原始请求与原始响应正文；日志列表摘要和“原始请求 / 原始响应”标题保持原字号。
   - 字号：请求 Method `14px -> 18.2px`，URL、键值、Body 和响应正文 `13px -> 16.9px`，Headers/Params/Body 分组标签 `9px -> 11.7px`，均为精确 1.3 倍。
   - 布局：Method 列宽由 `58px` 扩为 `76px`，避免 DELETE 等较长方法名放大后挤压 URL；日志内容区继续独立滚动。
   - 浏览器 E2E：真实 HTTP 日志计算字号与上述值一致；主标题仍为 `12px`、列表摘要仍为 `10px`，页面及编辑器横向溢出为 0，控制台错误为 0。
   - 回归：主题与前端专项 `13 passed, 1 warning`；`npm run build`、Python `compileall`、Workflow bundle 语法检查和 `git diff --check` 均成功；全量 `220 passed, 6 skipped, 1 warning`。
   - 后续变化：第 10 项删除请求分区后，原始请求改为与原始响应一致的单一 `pre` 文本块，请求正文统一使用 `16.9px`；原始响应的 30% 放大保持不变。
10. **Postman 式完整 HTTP 原始请求**（已完成，2026-07-23）
   - 格式：单一原始文本块按“请求行、已记录 Headers、空行、原始 Body”排列；请求行为 `METHOD URL HTTP/1.1`，Query Params 使用 `URLSearchParams` 合并进 URL。
   - 数据真实性：只展示运行记录中实际保存的 Headers，不伪造未持久化的 Host、User-Agent、Accept 或 Content-Length；RAW Body 保持原字符串且不进行 JSON 美化，表单 Body 按 URL 编码文本展示。
   - 交互：删除 Postman 的 Headers/Params/Body 分区组件和对应 CSS；原始请求与原始响应使用相同日志容器、`16.9px` 正文和可选择文本；“复制原始请求”复制与页面相同的报文文本。
   - 浏览器 E2E：真实 `POST /orders?source=raw+log` 展示请求行、两条 Header、空行和紧凑 JSON Body，不包含旧分区标签；Windows 剪贴板与页面内容一致，仅按系统规范使用 CRLF，页面横向溢出为 0，控制台错误为 0；临时 Workflow 已删除。
   - 回归：主题、前端及节点运行专项 `24 passed, 1 warning`；`npm run build`、Python `compileall` 和 `git diff --check` 均成功；全量 `220 passed, 6 skipped, 1 warning`。
11. **RAW JSON 请求体字段提取**（已完成，2026-07-23）
   - 业务目标：Workflow 编排人员可用 `request.body.username` 提取 HTTP RAW JSON 请求体字段，供下游节点引用，不需要把整个请求体当作字符串再次处理。
   - 数据契约：真实发送请求和运行日志继续保留变量替换后的 RAW 原字符串；仅输出变量提取上下文在 RAW Body 为合法 JSON 时使用 `json.loads` 解析。非 JSON RAW Body 保持字符串，不做隐式转换。
   - 端到端验证：节点向本地 HTTP 服务发送包含 `username / password / email / question` 的多行 RAW JSON；服务收到的原文和 `request_body.body` 与编辑内容逐字符一致，`request.body.username` 成功提取为 `test`，响应字段提取同时通过。
   - 真实页面复核：首次修复后 `8010` 仍由 2026-07-22 23:34 启动且不带 `--reload` 的旧 Uvicorn 进程提供服务，因此用户节点继续得到旧错误；重启到当前代码后，既有 `POST /register` 节点连续两次运行均为 HTTP 200 / `SUCCESS`，输出变量 `abc` 为 `test`，原始请求日志仍保存字符串。历史 `FAILED` 记录按追溯要求保留。
   - 回归：变量解析与节点运行专项 `69 passed, 1 warning`；`npm run build`、Python `compileall` 和 `git diff --check` 均成功；全量 `220 passed, 6 skipped, 1 warning`。
12. **游离节点可用变量解耦**（已完成，2026-07-23）
   - 业务目标：可用变量面板只负责展示全局变量、当前节点可见的上游输出和当前节点自身输出，不因 Workflow 尚未连线完成而拒绝加载。
   - 边界：变量面板同步草稿时使用与单节点运行相同的 `for_node_run` 不完整图模式；保存按钮和整图运行继续执行游离节点与循环依赖校验，不放宽图规则。
   - API 验证：创建无任何连线的 HTTP 节点并真实运行后，变量 API 返回 `全局变量 / 游离 HTTP` 两组，当前节点的 `username = test` 可用；既有正常连线 LLM 用例继续覆盖上游节点输出展示。
   - 浏览器 E2E：在用户既有单节点 Workflow 中打开游离 HTTP 节点变量面板，页面显示当前节点 `abc = test`，不再显示 `Workflow 存在游离节点: HTTP`，顶栏保持“已保存”，控制台错误为 0。
   - 回归：Workflow、LLM、节点运行和前端专项 `47 passed, 1 warning`；`npm run build`、Python `compileall`、Workflow bundle 语法和 `git diff --check` 均成功；全量 `221 passed, 6 skipped, 1 warning`。

## T13.3 Script 顶层变量输出（已完成）

### 业务目标与场景

- Workflow 编排人员在 Script 节点中直接编写普通 Python 顶层变量，不再为了向下游传值额外构造 `response`。
- `print()`、stdout、stderr 和 traceback 始终属于原始运行日志，不参与业务变量提取；用户继续依据真实日志定位代码错误。
- 一个 Script 可以配置多个输出，每行将一个 Python 顶层变量映射成供后续节点使用的 `${变量名}`，并可设置不同的对外名称和目标类型。

### 已确认数据契约

```text
Python 顶层变量 --输出映射--> 对外变量名 --${变量名}--> 后续节点
```

- Script 输出配置只包含：对外变量名、Python 顶层变量名、类型。
- Script 不再支持从 `request` 或 `response` 路径提取输出变量，不提供旧配置兼容。
- Python 变量不存在、变量无法 JSON 序列化或类型转换失败时，节点状态为 `FAILED`，stdout/stderr 和具体错误原因必须完整保留。
- 不同节点可以声明同名对外变量。当前节点引用变量时，唯一距离最近的上游来源覆盖更远来源。
- 两个或更多等距上游节点声明同名变量时结果存在歧义，保存和执行均应明确报错，不按画布位置或完成时间随机选择。
- 全局变量与节点输出同名时仍属于不同层级冲突；本子任务不擅自定义覆盖关系，继续沿用现有校验规则。
- HTTP、LLM、Agent 的 `request / response` 原始对象和路径提取规则不变。

### 子任务与逐步验证

1. **数据契约与图距离解析**（已完成，2026-07-22）
   - 输入：Workflow 节点、边、全局变量和输出映射。
   - 输出：Script 映射规范；唯一最近上游解析；等距歧义错误。
   - 验证结果：`uv run pytest tests/test_workflow_variables.py tests/test_workflow_drafts.py -q` -> `75 passed, 1 warning`。warning 为既有 Starlette/httpx 弃用提示。
2. **Script Worker 顶层变量采集**（已完成，2026-07-22）
   - 输入：Script 代码、`inputs`、`config`、配置的 Python 变量名。
   - 输出：只返回已声明顶层变量的 JSON 快照；缺失或不可序列化时返回真实 traceback。
   - 验证结果：`uv run pytest tests/test_tool_execution.py tests/test_workflow_node_runs.py -q` -> `17 passed, 1 warning`。覆盖多变量、别名、缺失变量、不可序列化、类型转换失败、原始日志、超时与中断。
3. **Script 节点编辑 UI**（已完成，2026-07-22）
   - 输入：Script 节点 `outputVariables`。
   - 输出：对外变量名、Python 变量、类型三列；移除 Script 的提取表达式；默认代码不再构造 `response`。
   - 验证结果：`npm run build` 成功；`uv run pytest tests/test_execution_frontend.py -q` -> `8 passed, 1 warning`。桌面浏览器交互合并到子任务 4 E2E。
4. **完整工作流回归**（已完成，2026-07-22）
   - 输入：包含多变量、别名、同名远近覆盖和等距冲突的实际 DAG。
   - 输出：后续节点可通过 `${变量名}` 使用确定值；失败/日志/中断行为不回归。
   - API 验证：三段 Script 串行 DAG 使用同名 `message`，节点数组顺序被刻意打乱；下游仍稳定取得唯一最近上游值。等距分支同名变量在保存时明确报错。
   - 浏览器 E2E：在 `http://127.0.0.1:8010/` 新建 Workflow，打开 Script 节点，确认“变量名 / Python 变量 / 类型”三列和默认 `msg` 代码；配置 `message <- msg / STRING` 后单节点运行状态为 `SUCCESS`，变量面板显示 `message = 介绍一下自己`，展开日志同时显示原始 stdout 和原始变量快照。临时 Workflow 已删除。
   - 历史草稿验证：旧 Script `response` 映射可以被列表和详情读取以供人工修正，但保存和执行均按新协议拒绝，不继续提供旧提取兼容。
   - 最终回归：`uv run pytest -q` -> `214 passed, 6 skipped, 1 warning`；6 项为未注入真实模型凭据的 live 测试，warning 为既有 Starlette/httpx 弃用提示。
   - 静态与构建：`uv run python -m compileall -q execution web tests` 成功；`npm run build` 成功。

### T13.3 验收结论

- 简单 Script 只需声明普通顶层变量并在输出区映射一次，无需构造 `response`。
- 支持一个节点映射多个变量、同名或别名输出及严格类型转换。
- 缺失变量、不可序列化值和类型转换失败均使节点 `FAILED`，同时保留原始 stdout、stderr、变量快照和 traceback。
- 后续节点继续使用 `${变量名}`；重名来源按唯一最近上游解析，等距歧义不会产生随机结果。
- HTTP、LLM、Agent 的既有 `request / response` 路径提取未改变。

## T13.4 Script 原始控制台与可选输出（已完成）

### 业务背景与目标

- Script 作者以 PyCharm 等 Python IDE 的控制台为心智模型，需要按真实发生顺序查看 `print()`、stderr、Python traceback 和系统警告，而不是在日志页阅读经过 JSON 解析或字段拆分的内容。
- 日志只负责复现执行过程，不参与变量提取；节点间传参继续使用 T13.3 的 Python 顶层变量映射。
- 条件分支没有生成某个已配置输出时，不应把已经正常完成的脚本误判为失败。

### 已确认规则

- Script 日志显示单一原始控制台，不解析 JSON、不从日志提取字段、不把请求或变量快照混入控制台正文。
- 底层继续分别保存 stdout、stderr；同时按接收顺序保存合并后的 `console`，用于还原控制台。
- 配置的 Python 顶层变量不存在时，该对外变量输出 `null`，控制台追加明确 `[WARNING]`，节点保持 `SUCCESS`。
- 真实 Python 异常、超时、进程中断、不可序列化值和已配置类型转换失败仍按既有规则处理；本阶段不擅自放宽。
- HTTP、LLM、Agent 日志布局和 `request / response` 提取不变。

## T13.5 Script 普通 Python 兼容性（已完成）

### 业务背景与缺陷

- 用户需要将在 PyCharm 中可执行的普通非交互 Python 代码直接放入 Script，包括常见的 `response = requests.get(...)` 写法。
- 当前通用 Worker 仍为 Agent 兼容保留顶层 `response`，并在 Script 完成后强制序列化它；当 `response` 是 `requests.Response` 等普通 Python 对象时，业务代码本身成功却被平台错误判为失败。
- 历史 Workflow 仍可能保存 `response.stdout` 等旧 Script 提取配置。当前新协议在保存前拒绝这些记录，导致新代码根本没有写入和运行，页面只能看到旧失败日志。

### 已确认目标与验收

- Script 中 `response` 与其他变量名完全等价，不具备平台保留语义；只有 Agent 继续使用顶层 `response` 作为结构化结果。
- Script 只序列化明确配置的 Python 输出变量，不扫描或序列化其他局部/全局对象。
- 历史 Script 输出行缺少 `pythonVariable` 时，自动以对外变量名作为可选 Python 变量来源；不存在则按 T13.4 输出 `null` 和警告，不阻止保存或执行。
- 真实验收使用用户代码访问 `http://127.0.0.1:9000/chat/1`：HTTP 200、JSON 正常打印、节点 `SUCCESS`，且 `requests.Response` 不触发序列化错误。
- 交互式 stdin、桌面 GUI、未安装依赖和超出 Worker 进程权限的代码不属于“PyCharm 可执行即平台必然可执行”的承诺范围。

## T13.9 全节点原始日志视觉契约（已完成）

### 业务背景与目标

- Workflow 编排人员需要在 HTTP、AGENT、LLM、SCRIPT 节点中用同一种控制台视觉阅读真实请求、响应、stdout、stderr 和 traceback，避免切换节点类型后字体大小、行距和背景发生跳变。
- Script 原始控制台是本阶段的基准；日志只展示和复制真实原文，不改变底层日志结构、变量提取、最近 10 次记录或错误语义。

### Script 基准契约

- 适用范围：节点日志页中展开后的原始日志正文；不包含历史摘要行、模块标题、Provider 元信息、状态色、复制按钮和 Python 编辑器。
- 字体：`Consolas, "SFMono-Regular", monospace`。
- 字号：`14.3px`。
- 行高：`1.6`。
- 背景：纯黑 `#000000`。
- 正文：浅色 `#e3e8ef`。
- 交互：保留原始换行、独立滚动、鼠标选区、原生 `Ctrl+C` 和整段复制；不得解析或重组日志正文。
- 优先级：本节是四类节点原始日志正文的最新统一约定，覆盖 T13.6 第 9-10 项和 T13.8 中不同节点使用独立正文字号的历史记录。

### 四类节点扫描结果（2026-07-23）

| 节点 | 当前渲染 | 字体/背景 | 与 Script 契约差异 |
|---|---|---|---|
| SCRIPT | 只读控制台 `textarea` | Consolas / 14.3px / 1.6 / `#000000` / `#e3e8ef` | 基准，已符合 |
| HTTP | 原始请求、原始响应 `pre` | Consolas / 16.9px / 1.55 / `#000000` / `#dbe6f5` | 字号、行高、正文色不同 |
| LLM | 原始请求、stdout、response、stderr、traceback `pre` | Consolas / 16.9px / 1.55 / `#000000` / `#dbe6f5` | 字号、行高、正文色不同 |
| AGENT | 与 LLM 共用原始日志 `pre` | Consolas / 16.9px / 1.55 / `#000000` / `#dbe6f5` | 字号、行高、正文色不同 |

### 子任务与验收

1. **契约与差异扫描**（已完成，2026-07-23）
   - 输出：上述 Script 基准、适用边界和四类节点差异矩阵。
2. **共享样式改造**（已完成，2026-07-23）
   - 输出：`.wf-inspector` 定义 `--wf-raw-log-*` 字体、字号、行高、背景和正文色变量；Script `textarea` 与 HTTP/AGENT/LLM `pre` 共同引用。
   - 结果：四类节点统一为 Consolas / 14.3px / 1.6 / `#000000` / `#e3e8ef`，历史摘要、模块标题、状态色和复制交互不变。
   - 验证：`npm run build` 成功；`uv run pytest tests/test_execution_frontend.py tests/test_workflow_node_runs.py -q` -> `20 passed, 1 warning`。
3. **浏览器与完整回归**（已完成，2026-07-23）
   - SCRIPT 与 LLM 的浏览器计算样式均为 `rgb(0, 0, 0)` 背景、`rgb(227, 232, 239)` 正文、Consolas 字体、14.3px 字号和 22.88px 行高。
   - HTTP 真实原始请求/响应以及临时 AGENT 的请求、stdout、response、stderr 均显示同一黑底控制台；历史摘要继续使用浅色背景，长内容保留独立滚动。
   - 临时 AGENT Workflow `3e1fd08557b446b793d80faa9cc0700c` 执行 `SUCCESS` 后已删除，列表恢复为 2 个原有 Workflow。
   - 最终回归：`uv run pytest -q` -> `220 passed, 6 skipped, 1 warning`；6 项为未注入真实模型凭据的 live 测试，warning 为既有 Starlette/httpx 弃用提示。
   - `npm run build`、`uv run python -m compileall -q execution web tests` 和 `git diff --check` 均成功。

## T13.8 Workflow Studio 字体与节点编辑器视觉调整（已完成）

### 已确认边界

- 最新决策：Script / Agent 的 Python CodeMirror 编辑器与日志统一使用 `Consolas, "SFMono-Regular", monospace`；Workflow Studio、节点设置和其他页面保持各自默认字体。
- 已下载的 Droid 字体资产继续保留但不应用到界面，避免改变本任务之外的静态资源状态。
- 只有展开后的原始日志内容使用纯黑背景，日志历史摘要行继续使用浅色背景。
- Python 编辑器可视高度由 360px 增加 50% 至 540px。
- 节点设置页中的节点名、页签、字段标签和配置分组标题使用深黑色；状态、错误和操作按钮保留语义色。

### 子任务与验证

1. **本地字体资产与作用域**（已完成，2026-07-23，最终不启用 Droid）
   - 引入 `DroidSansMonoSlashed.ttf`、OFL 1.1 文本和来源/哈希记录；字体通过 `/assets/fonts/` 由本机服务提供。
   - esbuild 将 `/assets/*` 保持为运行时静态 URL；`npm run build` 成功。
   - `uv run pytest tests/test_execution_frontend.py -q` 覆盖字体静态资源、缓存版本，以及 Python 编辑器与日志使用相同 Consolas 字体栈的最终规则。
2. **日志、编辑器高度和标题颜色**（已完成，2026-07-23）
   - Script 控制台、LLM/Agent 原始响应和 HTTP 原始请求/响应内容区使用纯黑背景；历史摘要行保持浅色。
   - 原始日志正文在既有字号上放大 30%：Script 控制台为 14.3px，HTTP/LLM/Agent 原始文本为 13px；历史摘要字号不变。
   - Python 编辑器固定内容高度由 360px 调整为 540px；设置页通过既有滚动容器访问后续运行配置。
   - 节点名、页签、字段标签、变量标题以及 LLM/HTTP/运行配置分组统一使用 `--wf-heading: #111827`；状态和错误语义色不变。
   - `npm run build` 成功；`uv run pytest tests/test_execution_frontend.py -q` -> `9 passed, 1 warning`。
3. **桌面浏览器和完整回归**（已完成，2026-07-23）
   - 浏览器确认 Python CodeMirror 与日志统一使用 Consolas 等宽字体，节点界面继续使用 Inter/Segoe UI。
   - 编辑器网格行为 `32.5px 540px`，设置容器可滚动访问运行配置；节点名、页签和字段标签计算色为 `rgb(17, 24, 39)`。
   - Script 日志历史行保持浅色，展开控制台为纯黑背景、浅色正文；放大后的 traceback 保留完整横向和纵向滚动。HTTP/LLM/Agent 黑底和 13px 正文由同一专项测试覆盖。
   - 最终回归：`uv run pytest -q` -> `220 passed, 6 skipped, 1 warning`；6 项为未注入真实模型凭据的 live 测试，warning 为既有 Starlette/httpx 弃用提示。
   - `npm run build`、`uv run python -m compileall -q execution web tests` 和 `git diff --check` 均成功。

## T13.7 Python 编辑器与控制台复制（已完成）

### 业务目标与验收

- Script / Agent 的 `main.py` 使用 Python 语法高亮，提升长脚本的阅读、修改和排错效率；节点数据仍保存纯字符串，不改变执行协议。
- Script / Agent 不再提供独立“代码”页签；Python 编辑器嵌入“设置”页并位于运行配置上方，配置、代码和输出映射在同一滚动工作面完成。
- 用户在 Script 原始控制台拖选文本后按 `Ctrl+C`，必须复制浏览器文本选区，不能触发画布节点复制。
- 原始控制台提供独立复制按钮，一次复制本次控制台的全部原文，并显示成功或失败反馈。
- Script / Agent 代码编辑器使用适合桌面节点编辑器的 16px 字号；行号、代码和光标同步缩放。
- 日志摘要中的执行时间、耗时和最终结果概览统一为 14px，并加宽固定列；长结果继续单行省略显示。
- 画布节点多选复制、代码编辑器自身快捷键、最近 10 次日志和其他节点日志布局不得回归。

### 实施子任务

1. **现状确认**（已完成，2026-07-22）
   - 代码区为普通 textarea，项目没有可复用 CodeMirror 资产。
   - 画布已存在 `hasBrowserTextSelection()` 保护，文本选区不会被节点复制逻辑主动覆盖；仍需真实浏览器验证。
2. **CodeMirror Python 编辑器**（已完成，2026-07-22）
   - 引入 CodeMirror 6、Python language 和 one-dark 主题，`mainPy` 仍为受控字符串。
   - `npm run build` 成功；前端专项 `8 passed, 1 warning`。
3. **控制台复制按钮与反馈**（已完成，2026-07-22）
   - Script 原始控制台支持鼠标选区，并提供独立的一键复制按钮、成功状态和错误提示。
   - 普通 Clipboard API 和 `execCommand` 均不可用时，调用仅绑定本机应用的 Windows 系统剪贴板回退，确保内置浏览器仍能一键复制；最大文本与单次日志上限一致为 5 MB。
   - `npm run build` 成功；前端专项 `uv run pytest tests/test_execution_frontend.py -q` -> `8 passed, 1 warning`。
4. **构建、测试和浏览器回归**（已完成，2026-07-22）
   - 自动回归：`npm run build`、`uv run python -m compileall -q execution web tests` 和 `git diff --check` 均成功；`uv run pytest -q` -> `219 passed, 6 skipped, 1 warning`。
   - 浏览器验收：Script 设置页仅显示“设置 / 日志”，16px CodeMirror 位于运行配置上方；Python 关键字、字符串、函数、参数和常量使用不同颜色，行号与代码同步缩放，无文本遮挡。
   - 控制台验收：日志同时显示原始 stdout `stdout copy target` 和 stderr `stderr copy target`；一键复制显示“控制台已复制”，Windows 剪贴板内容与两行原文完全一致。
   - 日志正文改为只读文本控制台，浏览器原生维护鼠标选区和 `Ctrl+C`；其 `copy` 事件在组件内停止传播，画布节点复制不会覆盖日志文本。内置浏览器自动化对原生拖选合成不稳定，未将该工具限制误报为页面失败。
   - 临时验收 Workflow `ded6732203754d1ebfe73c5615462548` 已删除，列表恢复为 2 个原有 Workflow。

### 子任务

1. **解除 Script `response` 保留语义并放宽旧映射**（已完成，2026-07-22）
   - Script 模式不再预置、读取或序列化顶层 `response`；Agent 协议不变。
   - 旧 Script 输出行缺少 `pythonVariable` 时以对外变量名为可选来源，不再阻止保存。
2. **专项和真实 HTTP 运行验证**（已完成，2026-07-22）
   - 专项结果：`uv run pytest tests/test_tool_execution.py tests/test_workflow_variables.py tests/test_workflow_drafts.py tests/test_workflow_node_runs.py -q` -> `97 passed, 1 warning`。
   - 真实结果：用户提供的 `requests` 代码原样访问 `http://127.0.0.1:9000/chat/1`，Worker `ok: true`，HTTP 200 JSON 完整进入 stdout/console，顶层 `response` 未被序列化。
3. **前端历史映射归一化与浏览器回归**（已完成，2026-07-22）
   - 已完成：旧 Script 行 `name + value=response.xxx` 加载后归一化为 `pythonVariable=name` 并移除旧 value；`npm run build` 成功，前端专项 `8 passed, 1 warning`。
   - 浏览器结果：用户原代码在旧映射 Workflow 中保存并运行成功，节点 `SUCCESS`，控制台打印真实订单 JSON，遗留 `msg` 为 `null` 警告；临时 Workflow 已删除。
4. **全量回归与服务检查**（已完成，2026-07-22）
   - `uv run pytest -q` -> `217 passed, 6 skipped, 1 warning`；跳过项为未注入真实模型凭据的 live 测试，warning 为既有 Starlette/httpx 弃用提示。
   - `uv run python -m compileall -q execution web tests`、`npm run build`、`git diff --check` 均成功。

### T13.5 验收结论

- 用户提供的 `requests` 代码无需改名即可执行，顶层 `response` 可以保存任意普通 Python 对象且不会被 Script 平台隐式序列化。
- Script 仅序列化输出区明确绑定的 Python 变量；未绑定的模块、客户端、响应对象、函数和其他运行时对象不会影响节点成功状态。
- 历史 `response.xxx` Script 映射不再阻止保存和执行，加载后自动转为同名可选顶层变量；缺失时输出 `null` 和控制台警告。
- 真实 `9000/chat/1` 与桌面浏览器两条链路均验证节点 `SUCCESS` 和完整控制台 JSON 输出。

### 子任务与验证

1. **协议记录**（已完成，2026-07-22）
   - 输出：上述可观测行为和数据边界写入计划。
   - 验证结果：用户确认日志不做字段提取，并选择缺失顶层变量输出 `null`、控制台警告、节点保持 `SUCCESS`。
2. **Worker 与持久化**（已完成，2026-07-22）
   - 输出：缺失变量补 `null` 和警告；有序 `console` 持久化及历史库迁移。
   - 验证结果：`uv run pytest tests/test_tool_execution.py tests/test_workflow_variables.py tests/test_workflow_drafts.py tests/test_workflow_node_runs.py -q` -> `95 passed, 1 warning`。覆盖 stdout/stderr 顺序、缺失变量 `null`、警告、数据库迁移、真实异常、类型失败和中断。
3. **Script 控制台 UI**（已完成，2026-07-22）
   - 输出：Script 运行详情只显示单一控制台，其他节点不回归。
   - 验证结果：`npm run build` 成功；`uv run pytest tests/test_execution_frontend.py -q` -> `8 passed, 1 warning`。桌面浏览器 E2E 合并到子任务 4。
4. **完整回归**（已完成，2026-07-22）
   - 最终回归：`uv run pytest -q` -> `215 passed, 6 skipped, 1 warning`；6 项为未注入真实模型凭据的 live 测试，warning 为既有 Starlette/httpx 弃用提示。
   - 静态与构建：`uv run python -m compileall -q execution web tests`、`git diff --check`、`npm run build` 均成功。
   - 浏览器 E2E：临时 Workflow 的 Script 依次打印 stdout、stderr，并配置一个不存在的顶层变量；节点状态为 `SUCCESS`，结果包含 `missing: null`，展开日志只显示一个 `Script 原始控制台`，正文顺序为 stdout、stderr、`[WARNING]`，没有请求、响应或变量字段分区。
   - 清理与服务：临时 Workflow 已删除；`http://127.0.0.1:8010/` 保持单一监听端口并恢复到用户原工作流列表。

### T13.4 验收结论

- Script 日志不做字段提取，控制台原样保留 stdout、stderr、Python traceback 和系统警告的接收顺序。
- 顶层 Python 变量映射继续作为唯一节点间传参方式，控制台文本不参与传参。
- 缺失顶层变量输出 `null` 并警告，不再把正常完成的 Script 误判为失败。
- 真实执行错误仍为 `FAILED`；HTTP、LLM、Agent 的日志和输出协议未改变。

## 1. 业务背景与目标（Why）

Agent Bench v2 没有成熟的插件体系，也没有专门团队持续适配各模型厂商的协议、SDK、流式格式、结构化输出、Tool Calling、推理模式和中间件差异。现有 Agent 工具包含较多 Python 硬编码，是为了让工具作者能够直接处理供应商差异和特殊业务场景，而不是依赖平台先完成深度适配。

新版 Studio 的目标不是建设一个类似大型厂商市场的插件生态，而是解决以下实际问题：

- 新手不会从零编写完整 HTTP、LLM、Agent 或 Script 工具。
- 工具作者需要提供完整、可运行、可导入导出的起始模板。
- Workflow 编排人员需要在模板基础上修改少量代码或配置，快速得到当前 Workflow 的个性化工具。
- 画布中验证成熟的工具需要能够沉淀回模板库，供其他人再次使用。
- Workflow 必须自包含；模板被修改、删除或未随环境迁移时，已经保存的新版 Workflow 仍应可恢复和执行。
- 平台不能假装拥有并不存在的统一模型适配能力。LLM 和 Agent 必须保留完整 Python 修改能力。

本阶段的核心产品定位是：

```text
工具模板库负责提供完整起点
        ↓ 深拷贝
画布工具负责当前 Workflow 的个性化实现
        ↓ 可选发布
产生新的独立工具模板
```

## 2. 目标用户与真实场景（Who & Where）

### 2.1 工具模板作者

- 在工具模板库创建完整的 HTTP、LLM、Agent 或 Script 模板。
- 为模板提供可运行代码、类型配置、输入输出说明和安全默认值。
- 在模板库中独立测试模板。
- 通过模板包将工具交给其他 Agent Bench 用户。

### 2.2 Workflow 编排人员

- 在全屏 Studio 中新增空白工具，或从模板库选择现成模板。
- 将模板复制到画布后修改少量业务代码、Prompt、请求配置或输出处理。
- 配置当前 Workflow 特有的上游输入、下游输出、重试、延迟和重复执行。
- 不需要理解或管理模板与节点之间的版本引用关系。

### 2.3 模板接收者

- 导入其他人提供的工具模板包。
- 在模板库中独立测试导入的模板。
- 将模板复制到自己的 Workflow 中继续个性化。
- 不接收发布者的真实 API Key。

## 3. 需求真实性与优先级（What & When）

该需求来自明确的用户使用目标，不是为了抽象而抽象。工具模板化、画布工具所有权和执行自由度是 T13.2 的 P0 架构前置项，优先级高于继续细化 Agent / LLM 编辑器视觉布局。

原因如下：

- 如果所有权不明确，保存、复制、导出、删除和发布都会产生歧义。
- 如果先做 UI，后续确定深拷贝或引用模型时会整体返工。
- 如果先做“平台原生 LLM 执行器”，会形成无法持续维护的供应商适配层。
- 如果沿用旧固定 WorkflowDefinition，会把 T13.1 的任意画布原型错误套入旧执行拓扑。

## 4. 已确认的核心决策

### 4.1 新旧系统范围

- 新的“模板深拷贝到画布”模型只用于新版 Workflow Studio。
- 旧固定 Workflow、历史 Run 页面、相关 API 和固定拓扑执行链路全部删除。
- 旧 Script / Agent 工具定义、旧 ZIP 和旧 `manifest.json + main.py` 协议不提供导入或运行兼容。
- 旧本机工具数据由用户明确选择永久删除，不备份、不迁移。
- T13.2 不得直接复用旧 `WorkflowDefinition` 作为新版 DAG 协议。

### 4.2 模板与画布工具没有运行时引用关系

- 工具模板库中的对象是完整、可运行的起始模板。
- 从模板库拖入或选择模板时，系统将模板定义深拷贝为画布工具。
- 深拷贝完成后，画布工具不再引用来源模板。
- 修改模板不影响已经创建的画布工具。
- 修改画布工具不影响来源模板。
- 删除模板不影响已经保存的新版 Workflow。
- 新版 Workflow 保存和导出时包含画布工具的完整定义，不依赖目标环境仍存在来源模板。
- 不建设模板版本升级、自动传播、回滚或依赖影响分析机制。

### 4.3 画布保留工具构建能力

- 画布必须允许直接新建 HTTP、LLM、Agent 和 Script 工具。
- 用户可以从空白定义开始，也可以从模板库复制完整模板开始。
- 画布中的工具可以发布到工具模板库。
- 发布后的模板与当前画布工具相互独立，后续修改不自动同步。
- 画布不是第二套共享仓库；画布只维护当前 Workflow 内嵌的工具定义。

### 4.4 四类执行工具进入同一个工具模板体系

页面名称统一使用“工具模板”，并统一管理以下四种类型：

```text
HTTP
LLM
AGENT
SCRIPT
```

- `Start / End` 是 Workflow 系统控制节点，不是工具，不进入模板库。
- 四类工具共享模板创建、测试、搜索、筛选、导入、导出和发布生命周期。
- 四类工具不要求使用相同执行器；统一的是资产生命周期，不是运行实现。
- 类型在前端、API、`manifest.json`、`definition.json`、画布节点和运行快照中一律使用大写 `HTTP / AGENT / LLM / SCRIPT`，不接受或输出旧小写类型。

### 4.5 包结构采用 manifest + definition + 可选代码

已确认目标包结构为：

```text
{template_id}/
├── manifest.json
├── definition.json
└── main.py          # 按类型决定是否必需
```

- `manifest.json` 保存模板身份、类型、格式版本和展示元数据。
- `definition.json` 保存类型配置、输入输出、凭据要求、测试示例等结构化定义。
- `main.py` 对 LLM、Agent、Script 必需。
- `main.py` 对 HTTP 可选。
- 不再为没有 Python 实现的 HTTP 配置模式生成无意义的空 `main.py`。
- 旧 `manifest.json + main.py` Script / Agent ZIP 不再兼容；导入时必须作为无效旧格式拒绝。

### 4.6 模板必须支持独立测试

- 工具模板库继续提供独立测试运行能力。
- 模板发布或导出前应能使用测试输入验证基本可执行性。
- 测试运行不得依赖某个 Workflow 的画布位置、连线或运行历史。
- 测试使用的输入样例、凭据绑定和日志是否保存，需要在数据协议子任务中继续确认。

### 4.7 发布时移除真实 API Key

- 从画布发布模板时，自动移除真实 API Key。
- 模板只保留“需要某类凭据”的声明、安全占位或空值。
- API Key 不得从画布工具泄漏到新模板。
- 旧工具 ZIP 导入导出能力随旧协议删除，不保留明文密钥导出行为。
- Authorization Header、Cookie、自定义 Token 和代码中硬编码密钥的识别与处理尚未确认，列入开放问题。

### 4.8 统一 Python 运行数据协议

- LLM、AGENT、SCRIPT 以及 HTTP 代码模式统一使用 `inputs / config / response`。
- `inputs` 是本次运行由 Start、上游节点或运行参数传入的动态数据；模板和 Workflow 只保存映射，不保存某次运行的实际值。
- `config` 是随工具模板或画布节点保存的持久配置；凭据是否只保存引用仍需单独确认。
- `response` 是当前节点本次执行产生的标准 JSON 输出，供下游节点、运行追溯和 Artifact 使用，不写回工具模板。
- 不继续使用旧 Agent 六个固定模板参数，也不把节点配置混入 `inputs`。

## 5. 工具模板与画布工具的白话边界

```text
模板库中的工具：一份完整参考答案
画布中的工具：把参考答案复制过来后，为当前 Workflow 改出的个人版本
```

双方的职责如下：

| 工具模板库 | 画布工具 |
|---|---|
| 提供完整起始代码与配置 | 保存当前 Workflow 的完整个性化实现 |
| 可以独立测试 | 可以在 Workflow 中运行和追溯 |
| 可以导入、导出 | 随 Workflow 保存和导出 |
| 不保存画布坐标和连线 | 保存位置、连线和输入绑定 |
| 不保存 Workflow 运行状态 | 保存节点状态、耗时、日志和运行参数引用 |
| 发布后供下次复制 | 修改不回写来源模板 |

模板拖入画布是复制，不是引用：

```text
模板 A
  └── 深拷贝 → 画布工具 A'

之后：
修改模板 A   ≠ 修改画布工具 A'
修改画布 A'  ≠ 修改模板 A
```

## 6. 四类工具的职责与执行自由度

### 6.1 HTTP

HTTP 工具支持两种使用方式：

```text
配置模式
  Method / URL / Headers / Params / Body / 超时等
  由系统标准 HTTP 执行器执行

代码模式
  使用 main.py 完整接管特殊 HTTP 调用
  通过现有或新版通用 Worker 执行
```

已确认：

- 标准场景优先使用可视化配置。
- 特殊场景允许使用完整 Python。
- HTTP 的 `main.py` 可选。

尚未确认：

- 配置模式和代码模式是否通过分段控件切换。
- 切换时是否永久保留另一模式的内容。
- 配置模式如何引用上游输入和凭据。
- HTTP 代码模式已确认使用统一的 `inputs / config / response` Worker 契约。

### 6.2 LLM

LLM 不采用需要平台持续适配供应商的封闭原生执行器。

已确认：

- LLM 必须包含可完整编辑的 `main.py`。
- 用户可以修改 Client、SDK、Base URL、请求头、模型参数、推理模式、流式处理、结构化输出和响应解析。
- 模板只提供面向“一次模型调用”的默认代码结构，不限制用户最终代码能力。
- 平台不负责维护覆盖所有模型厂商的深度适配层。

### 6.3 Agent

已确认：

- Agent 必须包含可完整编辑的 `main.py`。
- 默认模板面向多步决策、Tool Calling、Middleware、状态、上下文和多轮执行。
- 允许继续使用 Python 硬编码处理供应商差异和特殊 Agent 逻辑。
- 平台不尝试把所有 Agent 行为抽象成固定表单或插件协议。

### 6.4 Script

已确认：

- Script 必须包含可完整编辑的 `main.py`。
- Script 用于通用 Python 数据处理、转换、校验和聚合等场景。
- 新版协议需决定是否支持 `${...}`；旧 Script 行为不再构成兼容约束。

### 6.5 LLM 与 Agent 只做语义分类

LLM 与 Agent 的区别用于：

- 模板分类。
- 默认代码结构。
- 编辑器布局。
- 用户意图表达。
- 后续统计和筛选。

已确认不做运行时强制限制：

- LLM Python 可以调用工具。
- Agent Python 可以只执行一次模型调用。
- 平台不通过静态扫描或沙箱规则强制两者能力边界。
- 两类代码都在受控 Worker 进程边界内执行，但用户 Python 本身保持高自由度。

## 7. 结构化定义的目标边界

`definition.json` 的目的不是封装所有供应商，而是让模板和画布能够描述、校验和渲染工具。

目标职责：

```text
definition.json
├── 输入字段或端口
├── 输出字段或端口
├── 普通配置项
├── 凭据要求
├── 类型专属配置
├── 测试输入示例
└── 输出示例或结构说明

main.py
└── 真正的自定义执行逻辑
```

尚未确认的协议细节：

- 输入输出使用简化字段表还是完整 JSON Schema。
- 输入类型集合和嵌套对象表达方式。
- 必填、默认值、说明、固定值、上游映射和全局变量如何区分。
- 多输出端口与单一 JSON `response` 如何兼容。
- 模板测试输入是否属于 `definition.json`。
- HTTP 配置与 Python 代码之间的数据传递格式。
- LLM / Agent 的普通配置是否继续使用 6 个固定模板参数，或改用结构化配置对象。

在这些字段确认前，不得直接扩展现有 `ToolManifest`。

## 8. 画布工具生命周期

### 8.1 创建

目标入口：

```text
新增 HTTP / LLM / AGENT / SCRIPT
        ↓
选择空白定义或工具模板
        ↓
深拷贝为画布独立工具
```

空白定义必须提供可理解的最小起始内容，尤其是 LLM、Agent 和 Script 的完整示例代码。

### 8.2 编辑

- 画布工具的代码和配置可以直接修改。
- 修改只影响当前 Workflow。
- 不提供“升级来源模板”“同步模板修改”或“分离副本”，因为深拷贝后本来就没有引用关系。
- 复制粘贴节点必须继续深拷贝工具定义和选区内部连线。

### 8.3 发布

发布的业务含义：从当前画布工具提取可复用部分，创建一个新的独立模板。

当前已落地的发布内容：

- 名称、说明和类型。
- `manifest.json` 身份及格式信息。
- `definition.json` 输入输出和类型配置。
- `main.py` 完整代码（适用类型）。
- 安全默认值和测试示例。

不得发布的 Workflow 实例信息：

- 画布坐标、尺寸和连线。
- 上游节点 ID、下游节点 ID和当前 Workflow 专属映射。
- 节点运行状态、执行耗时、日志和运行历史。
- 当前 Workflow 名称、Run、Case、Attempt、Artifact 数据。
- 已确认不得发布的真实 API Key。

发布始终由后端生成新模板 ID，不覆盖同 ID；同名模板允许并按各自 ID 展示。发布完成后不向画布节点写回模板引用。

### 8.4 删除

- 删除模板不影响已经复制到新版 Workflow 的画布工具。
- 删除画布工具不影响模板库。
- 旧仓储和旧 Workflow 引用规则整体删除，不进入新版生命周期。

## 9. 导入、导出与可移植性

### 9.1 模板包

- 四类模板使用同一包格式和格式版本。
- LLM、Agent、Script 包含 `main.py`。
- HTTP 配置模板可以没有 `main.py`；HTTP 代码模板包含 `main.py`。
- 导入后模板进入同一个工具模板库并可独立测试。
- 旧 Script / Agent ZIP 不兼容，并通过专项测试确认被明确拒绝且不会产生部分写入。

### 9.2 Workflow 包

- 新版 Workflow 导出包含全部画布工具定义和图结构。
- 导入目标环境不需要预先安装来源模板。
- 导入后不建立对来源模板 ID 的运行时引用。
- Workflow 是否复用模板包目录结构、是否将工具按节点逐个内嵌、如何处理重复工具定义，尚待协议设计。

### 9.3 凭据

- 从画布发布模板时移除真实 API Key，这是已确认规则。
- n8n 等项目采用凭据 Stub 和导入后重新绑定；该模式可作为参考，但尚未被确认成 Agent Bench 的最终方案。
- 新版 Workflow 导出是否保留明文密钥、改为凭据声明或要求导入后绑定，仍需单独确认。
- 当前新模板 ZIP 不会自动清理 `config` 或 `main.py` 中的全部秘密，页面导出前必须保留可信接收者警告；凭据规则确认前不得宣称可安全公开分享。

## 10. 当前 Studio UI 基线（不得回归）

以下是 T13.1 已完成并在后续布局中需要保留的行为：

- `Start / End` 为系统节点；可新增工具类型为 `HTTP / AGENT / LLM / SCRIPT`。
- 所有画布节点卡片右上角只保留运行按钮。
- 节点状态统一为 `PENDING / RUNNING / PASSED / FAILED`。
- 节点右下角显示加载圆环和本次执行耗时。
- 每次执行从 `0ms` 重新计时，`RUNNING` 期间累加，结束后固定本次耗时。
- 加载圆环只在 `RUNNING` 状态旋转。
- `FAILED` 已有状态和样式能力；T13.1 不随机制造失败。
- 单击节点只选中，双击打开可移动、八向拉伸的节点编辑器。
- 节点编辑器标题栏保留运行、保存和关闭。
- 参数通过独立“参数”页签查看，标题栏不提供参数快捷按钮。
- 参数页按 `source / name / data` 展示只读实际运行参数；大数据使用摘要、详情或 Artifact。
- 画布右上角保留运行、全局变量和保存。
- Ctrl 多选、框选、复制粘贴、Delete / Backspace、Undo / Redo 和 Dagre 自动布局继续有效。
- 系统只支持桌面浏览器，不增加移动端设计或测试。

四类工具的编辑器详细信息架构尚未确认。不得因为类型统一进入模板库而强行使用同一编辑表单。

### 10.1 当前落地状态

- 成功状态已在源码、专项测试、前端构建产物、`AGENTS.md` 和 `docs/enterprise-agent-test-orchestration.md` 中统一为 `PASSED`。
- 桌面浏览器已验证节点从 `PENDING` 进入 `RUNNING` 后结束为 `PASSED`；失败能力继续使用 `FAILED`。

## 11. 行业调研结论与适用范围

调研项目：n8n、Node-RED、Dify、Langflow、Apache NiFi。

### 11.1 可借鉴内容

- n8n：社区节点包注册节点类型，Workflow 实例保存类型、版本、参数、凭据引用和位置；新 n8n Package 使用凭据 Stub，而不是导出秘密。
- Node-RED：节点包可携带 example flows；Subflow 是可复用定义，实例保存每次使用的属性。
- Dify：Tool Plugin 将 provider、tool 参数、输出 Schema、代码和凭据声明分层，工具安装后可直接作为 Workflow 节点使用。
- Langflow：组件类声明输入输出和类型，编辑器据此生成端口和校验连接。
- Apache NiFi：版本化 Flow 与本地 Process Group 分离，支持改变版本和停止版本控制。

### 11.2 不直接照搬的内容

- Agent Bench 当前不采用 n8n / NiFi 的长期引用和版本升级模型。
- Langflow 的 `replacement` 只是显式推荐并过滤候选组件，不会自动迁移配置和连线。
- 不根据字段名称和类型自动推断任意两个工具可以无损替换。
- 不建设需要持续团队维护的统一模型供应商插件层。
- 不把设计工具中的 Detach / Variant 概念引入当前深拷贝模型；模板复制后天然独立。

### 11.3 参考资料

- n8n 节点示例：<https://github.com/n8n-io/n8n-nodes-starter/blob/master/nodes/Example/Example.node.ts>
- n8n 节点标准参数：<https://docs.n8n.io/connect/create-nodes/build-your-node/reference/base-files/standard-parameters/>
- n8n Packages：<https://docs.n8n.io/build/manage-workflows/export-and-import/n8n-packages/>
- Node-RED 节点打包：<https://nodered.org/docs/creating-nodes/packaging>
- Node-RED Example Flows：<https://nodered.org/docs/creating-nodes/examples>
- Node-RED Subflows：<https://nodered.org/docs/user-guide/editor/workspace/subflows>
- Dify Tool Plugin：<https://docs.dify.ai/en/develop-plugin/dev-guides-and-walkthroughs/tool-plugin>
- Langflow 自定义组件：<https://docs.langflow.org/components-custom-components>
- Langflow replacement 源码：<https://github.com/langflow-ai/langflow/blob/main/src/frontend/src/CustomNodes/GenericNode/components/NodeLegacyComponent/index.tsx>
- Apache NiFi Versioning：<https://nifi.apache.org/docs/nifi-docs/html/user-guide.html#versioning_dataflow>

## 12. 端到端目标流程

### 12.1 从模板创建工具

```text
进入 Workflow Studio
  → 添加 HTTP / LLM / AGENT / SCRIPT
  → 选择空白定义或工具模板
  → 系统深拷贝模板
  → 用户修改少量代码或配置
  → 配置输入输出与连线
  → 保存 Workflow
  → 创建 Run 时冻结画布工具完整快照
  → 执行、追溯和恢复
```

### 12.2 从画布发布模板

```text
在画布完成工具配置和测试
  → 点击“发布为模板”
  → 系统提取可复用定义
  → 移除真实 API Key 和实例运行数据
  → 用户确认模板名称、说明和测试示例
  → 在模板库创建独立模板
  → 原画布工具保持不变
```

### 12.3 模板跨用户复用

```text
用户 A 导出模板包
  → 用户 B 导入模板包
  → 在模板库独立测试
  → 复制到用户 B 的画布
  → 绑定本机凭据并个性化
  → 保存为自包含 Workflow
```

## 13. 可独立验证的开发子任务

每个子任务必须在验证通过后才能进入依赖任务。任何失败都暂停下游任务并记录结果。

| ID | 目标 | 输入 | 输出 | 验证方法 | 依赖 |
|---|---|---|---|---|---|
| T13.2.1 | 冻结新版术语、所有权和未决业务规则 | 本计划、现有 T13.1 原型 | 经用户确认的数据契约决策记录 | 逐项需求评审；确认所有开放问题有明确结论 | T13.1 |
| T13.2.2 | 定义四类模板和画布内嵌工具模型 | T13.2.1 | Pydantic 模型、格式版本、类型判别联合、迁移边界 | 模型单测覆盖四类型、非法额外字段、JSON 严格性和往返序列化 | T13.2.1 |
| T13.2.3 | 重建模板仓储和包格式 | T13.2.2、空 `tool_registry/` | 四类型 CRUD、刷新、导入、导出；拒绝旧 ZIP | 仓储和 ZIP 单测；路径穿越、重复 ID、无效包、旧包拒绝且无部分写入 | T13.2.2 |
| T13.2.4 | 实现模板独立测试 | T13.2.2、现有 Worker / SSE | 四类型测试启动、中断、日志、结果协议 | 每类型成功、失败、超时、中断、非法 JSON 和日志上限测试 | T13.2.2、T13.2.3 |
| T13.2.5 | 实现画布工具深拷贝与空白创建 | T13.2.2、T13.1 画布 | 四类型内嵌定义、来源模板深拷贝、复制粘贴保持 | 前端状态测试和真实浏览器 E2E；修改模板/节点互不影响 | T13.2.2、T13.2.3 |
| T13.2.6 | 实现从画布发布模板 | T13.2.3、T13.2.5 | 发布提取、实例字段剥离、API Key 清除、新模板创建 | 发布前后深比较；密钥扫描；模板独立运行；原节点不变 | T13.2.3-T13.2.5 |
| T13.2.7 | 设计并实现新版 Workflow 持久化 | T13.2.2、T13.2.5 | 图结构、内嵌工具、事务保存、更新、删除和校验 | Repository 重启回读、并发更新、无效边/节点/定义拒绝 | T13.2.2、T13.2.5 |
| T13.2.8 | 实现四类工具执行器 | T13.2.4、T13.2.7 | HTTP 配置/代码、LLM Python、AGENT Python、SCRIPT Python 执行 | 每类型真实子进程/HTTP 测试；inputs、config、response、日志、取消和超时 | T13.2.4、T13.2.7 |
| T13.2.9 | 接入 Run 快照和 DAG 调度 | T13.2.7、T13.2.8 | 新版 Workflow 快照、节点状态、依赖调度、Artifact 追溯 | 单链、分支、汇合、失败、取消、恢复、快照不变性测试 | T13.2.7、T13.2.8 |
| T13.2.10 | 完成四类节点编辑器布局 | 已确认类型协议、T13.1 UI 基线 | HTTP / LLM / Agent / Script 类型化编辑器 | 1440x900 浏览器 E2E；无溢出/重叠；代码和配置完整保存 | T13.2.5、T13.2.8 |
| T13.2.11 | 完成模板与 Workflow 导入导出 | T13.2.3、T13.2.7、凭据规则 | 跨环境模板包和自包含 Workflow 包 | A 环境导出、B 环境导入、无来源模板恢复、凭据缺失提示 | T13.2.3、T13.2.7 |
| T13.2.12 | 完整回归和文档收口 | 全部前序任务 | E2E 报告、迁移说明、风险清单、权威文档更新 | 单测、静态检查、构建、桌面完整流程和受影响模块全量回归 | T13.2.1-T13.2.11 |

## 14. 总体验收标准与价值验证（How to Measure）

### 14.1 模板独立性

- 从任意模板创建画布工具后，修改或删除模板不改变画布工具。
- 修改画布工具不改变模板。
- 新版 Workflow 在没有来源模板的环境中仍能恢复完整定义。

### 14.2 新手效率

- 新手可从四类完整模板创建节点，不需要从空文件编写完整代码。
- 模板复制后只修改少量代码或配置即可完成最小可运行流程。
- 模板库独立测试能够在进入 Workflow 前发现缺包、配置和执行错误。

### 14.3 发布复用

- 画布工具可以发布为独立模板。
- 发布不改变当前节点和任何已有模板。
- 新模板可独立测试、导出、导入并再次复制到画布。

### 14.4 安全

- 发布模板包不包含真实 API Key。
- 测试、日志、错误和 Artifact 不意外写入模板包。
- 文件导入导出继续受 `tool_registry/` 路径边界和 ZIP 安全校验约束。

### 14.5 执行与追溯

- LLM、Agent、Script 的完整 Python 在独立子进程执行。
- HTTP 配置模式和 Python 模式均可追踪输入、输出、日志、耗时和错误。
- Run 创建后冻结 Workflow 和全部内嵌工具，后续编辑不影响历史 Run。
- 节点状态和耗时遵守 `PENDING → RUNNING → PASSED / FAILED` 展示规则。

### 14.6 不兼容替换边界

- 旧固定 Workflow/Run 页面、API 和执行链不可访问且不再出现在导航中。
- 旧 Script / Agent 工具 CRUD、SSE、ZIP 和小写类型协议不可访问。
- 新工具模板只接受并输出 `HTTP / AGENT / LLM / SCRIPT`，不存在旧协议兼容层。
- 测试集、Target、FAQ、主题和新版 Workflow Studio 等保留功能不得因删除旧链路回归。

## 15. 已知风险

- 深拷贝会产生代码重复；模板修复不会自动传播到已有 Workflow。
- 没有模板引用后，无法统计哪些 Workflow 源自某个模板。
- 任意 Python 使 LLM / Agent 分类无法成为安全边界。
- 用户代码可能硬编码密钥，单纯清空结构化 API Key 字段不足以保证发布包无秘密。
- HTTP 双模式会带来配置与代码的优先级、切换和回显复杂度。
- 不兼容删除会使旧工具包、旧 Workflow 和历史 Run 无法恢复，这是用户已确认接受的永久数据损失。
- 自包含 Workflow 包可能显著增大，重复节点代码需要确定去重策略。
- 新版任意 DAG 的执行、取消、恢复和 Artifact 传播不能直接套用旧固定拓扑。
- 缺少成熟插件生态意味着依赖兼容和第三方 SDK 仍需人工维护 `pyproject.toml`。

## 16. 实现前仍需确认的开放问题

以下问题没有得到用户确认，不得自行补全：

1. HTTP CONFIG 的上游字段引用、动态 URL/Header/Body 映射和在 Workflow 中的标准 `response` 使用规则。
2. 除 API Key 外，Authorization、Cookie、Token 和代码硬编码秘密的处理范围。
3. 新版 Workflow 导出时的凭据保存、Stub 和导入后绑定规则。
4. 新版 Workflow 图结构、端口、分支、汇合、循环和失败传播规则。
5. 四类节点编辑器下一阶段的字段分组、标签页和默认展开状态。
6. 从导入模板替换已有画布节点时，是否需要保留位置、连线和输入绑定；当前只有新增深拷贝，没有自动替换协议。

## 17. 执行纪律

- 每次只实现一个可独立验证的子任务。
- 子任务开始前重新检查本计划、权威编排文档和当前 Git 差异。
- 每个子任务必须明确目标、输入、输出、验证方法和依赖。
- 验证失败时停止所有依赖任务，不得继续堆叠实现。
- 每完成一个子任务立即记录测试命令、结果、未覆盖范围和已知风险。
- 开发完成后必须运行相关单元测试、静态检查、完整构建、桌面 E2E 和受影响模块全量回归。
- 不覆盖或回滚与当前任务无关的用户改动。

## 18. 当前工作区与验证基线（2026-07-20）

### 18.1 已落地的 T13.1 原型能力

- Workflow 管理页可进入独立全屏 React Flow Studio；当前保存、测试运行、参数数据和节点运行状态均为前端本地演示，不调用旧 Workflow API，不能用于实际 Run。
- 画布支持节点拖动、连线、Dagre 自动布局、Edge `+` 插入、空白区与节点右键菜单、小地图和测试运行演示。
- 图结构历史最多保留 50 步；支持 `Ctrl+Z`、`Ctrl+Shift+Z`、`Ctrl+Y`、Ctrl 多选、框选、复制粘贴内部连线和 Delete / Backspace 删除。
- 双击节点打开默认 `1064x814`、可移动、八向缩放的编辑器；编辑器包含设置、参数和节点日志，普通字段每行两个，输出变量可动态增删。
- 节点卡片右上角只保留运行按钮；参数入口保留在编辑器“参数”页签，按 `source / name / data` 展示只读运行参数，大数据预留摘要、详情和 Artifact 入口。
- 节点右下角已显示加载圆环和本次执行耗时；每次运行从 `0ms` 开始，`RUNNING` 期间持续累加，完成后冻结，圆环仅在执行中旋转。
- HTTP 编辑器已有 Method、URL、Headers、Params、Body、cURL 导入、JSON Beautify 和 Binary 文件等前端配置能力；这些字段尚未形成新版后端执行协议。

### 18.2 当前修改和新增文件

工作区存在未提交修改，其中可能包含用户在本任务前或并行完成的改动。后续不得假定全部差异属于 T13.2，也不得回滚无关内容。

- `PLAN.md`：T13.2 业务分析、已确认决策、行业调研、开发拆解、验收标准、风险和开放问题。
- `web/frontend/workflow-canvas.jsx`：React Flow Studio 源码、节点编辑器、HTTP 配置、前端状态和执行耗时演示。
- `web/frontend/workflow-canvas.css`：Studio、节点、编辑器、参数表、耗时圆环和上下文菜单的桌面样式。
- `web/static/assets/workflow-canvas.js`：由 `npm run build:workflow` 生成的 JavaScript 构建产物，禁止绕过源文件直接修改。
- `web/static/assets/workflow-canvas.css`：Studio 静态样式资源。
- `tests/test_execution_frontend.py`：Studio 资源注册、画布交互、编辑器、HTTP、参数、状态和耗时的前端专项回归。
- `package.json`、`package-lock.json`：React、React Flow、Dagre、Lucide、react-rnd、cURL 解析和 `build:workflow` 构建依赖。
- `web/static/execution.js`、`web/static/execution.css`：Workflow 管理入口、Studio 挂载逻辑和管理页样式。
- `web/static/index.html`：Studio JavaScript/CSS 资源注册和 Workflow 导航文案。
- `docs/enterprise-agent-test-orchestration.md`：T13.1 状态、验证记录、当前限制和旧编排边界。
- `AGENTS.md`：项目当前进度、Studio 基线和 `PASSED` 成功状态。

### 18.3 最近一次已记录验证

- Studio 专项：`uv run pytest tests/test_execution_frontend.py -q`，结果 `8 passed, 1 warning`。
- 前端构建：`npm run build` 成功；构建脚本依次执行 `build:editor` 和 `build:workflow`。
- 静态检查：`node --check` 和 `git diff --check` 通过。
- 桌面浏览器 E2E：在 `1440x900` 下验证拖动、菜单、编辑器缩放、参数页、HTTP 配置和状态演示；页面横向溢出为 0，浏览器控制台错误为 0。
- 全量回归：`uv run pytest -q`，结果 `295 passed, 7 skipped, 1 warning`。
- 7 个跳过项包括 6 个缺少供应商凭据的 Agent live 矩阵和 1 个 Windows 符号链接权限测试；warning 为既有 Starlette/httpx 弃用提示。
- 真实模型历史矩阵已覆盖 DeepSeek `deepseek-v4-pro` 和 DashScope `qwen3.7-max`；真实内网 FastAPI 联调仍未完成，不得宣称真实环境全链路通过。
- 上述结果是最近一次已记录基线；后续改动不能仅引用旧结果，必须重新执行受影响验证。

> 基线更新：上述 `295 passed` 是删除旧 Workflow/Run 链路前的历史结果。Step 2 删除对应实现和测试后，当前剩余测试基线更新为 `153 passed, 6 skipped, 1 warning`，详见第 21 节。

## 19. 下一步具体执行计划

### 19.1 当前已完成批次

- 旧工具与旧 Workflow/Run 不兼容删除。
- 四类大写模板模型、仓储、CRUD、安全 ZIP、独立测试和统一执行 Worker。
- 工具模板页面、画布深拷贝、节点代码映射和发布为独立新模板。
- `definition.json` 使用简化字段列表；HTTP 使用 `CONFIG / CODE` 并只执行当前模式；测试 inputs 和日志不持久化。

### 19.2 下一批必须确认的三个问题

1. 新版 Workflow 是否禁止循环，以及分支、汇合和多入边节点的执行条件。
2. 节点端口和边是否只表达控制流，还是同时携带命名数据映射。
3. 节点失败、超时或中断后，下游是全部跳过、按边策略继续，还是允许节点级容错配置。

在这三项确认前不得建立 Workflow 持久化模型或 DAG 调度器，因为它们会直接决定图 Schema、校验规则、运行快照和恢复语义。

### 19.3 当前验证基线

- `npm run build`、Python `py_compile`、JavaScript `node --check` 和 `git diff --check` 通过。
- `uv run pytest -q`：`106 passed, 1 warning`。
- 桌面浏览器覆盖模板 CRUD/ZIP 回读、独立运行成功/中断、模板深拷贝和画布发布；临时模板均已清理。

### 19.4 后续依赖顺序

严格按以下顺序推进，不跨越未验证依赖：

```text
T13.2.1-T13.2.6 已完成
  → T13.2.7 Workflow 持久化
  → T13.2.8 四类执行器（模板独立执行部分已提前完成）
  → T13.2.9 DAG 调度、Run 快照与追溯
  → T13.2.10 四类节点编辑器
  → T13.2.11 模板与 Workflow 导入导出
  → T13.2.12 全量回归、迁移说明和文档收口
```

每项完成后立即执行第 13 节定义的验证并记录命令、结果、未覆盖范围和风险。最终必须覆盖模型单测、仓储与 ZIP 安全、真实子进程和 HTTP、Repository 重启回读、DAG 单链/分支/汇合/失败/取消/恢复、Run 快照不变性、桌面 `1440x900` E2E、前端完整构建、静态检查和全量 pytest 回归。

## 20. 持续有效的项目约束

- `docs/enterprise-agent-test-orchestration.md` 只作为已完成旧实现的历史记录；其中要求保留旧 Workflow/Run/工具链路的内容已被用户最新决策覆盖。
- 新版 Studio 不得直接复用旧 `WorkflowDefinition`、旧 Run 快照或旧工具协议作为任意 DAG 协议。
- 系统只支持桌面浏览器；不得增加移动端断点、触控专用逻辑或移动端回归测试。
- 不恢复旧评测流水线、`inputs/.tools.json` 或工具 `tags` 逻辑。
- Excel 文件操作限制在 `inputs/`，工具文件操作限制在 `tool_registry/`；导入导出必须继续执行路径穿越和 ZIP 安全校验。
- `config.yaml` 只保存当前 Excel 和 Sheet，不得保存业务配置、编排进度或凭据。
- API Key 只可注入测试或运行进程，不得写入代码、测试、文档或提交内容；旧工具 ZIP 明文密钥导出行为随旧链路删除。
- 用户代码继续使用当前 `.venv`，不自动安装依赖；缺包时人工修改 `pyproject.toml` 后执行 `uv sync`，禁止在编辑器用户代码中调用 `pip` 或 `uv`。
- 工作区可能包含用户未提交改动；后续修改必须先检查差异，不覆盖或回滚与当前子任务无关的内容。

## 21. 分步执行记录

### Step 1：永久删除旧本机工具数据（completed，2026-07-20）

- 目标：在不建立兼容层的前提下清空旧 Script / Agent 工具数据，为四类大写工具模板重建空仓储。
- 输入：`tool_registry/` 下 6 个旧 UUID 工具目录；用户明确选择 `1A` 永久删除且不备份。
- 输出：6 个一级工具目录及其中旧 `manifest.json + main.py` 已永久删除；`tool_registry/` 根目录和 `.gitkeep` 保留。
- 路径安全：删除前解析 `tool_registry/` 绝对路径，并逐项校验所有删除目标的父目录严格等于该根目录；未对工作区其他路径执行删除。
- 验证：删除命令退出码为 0；删除后 `Get-ChildItem -Force tool_registry` 只返回 `.gitkeep`。
- 依赖结论：Step 1 已通过，可以开始 Step 2 拆除旧固定 Workflow/Run 页面、API 注册和执行链。

### Step 2：拆除旧固定 Workflow/Run 页面、API 和执行链（completed，2026-07-20）

- 目标：彻底移除旧固定拓扑 Workflow、旧 Run 中心及其后端执行链，同时保留测试集、Target、新版 Workflow Studio、工具模板入口和 FAQ。
- 前端输出：侧栏删除“运行中心”；`web/static/execution.js` 重建为仅包含 Target CRUD 和前端本地 Workflow Studio，不再包含旧 Run、固定 Workflow 编辑器、测试集绑定或旧 API 请求。
- API 输出：FastAPI 不再注册 `web/routes_workflows.py` 和 `web/routes_runs.py`；`GET /api/workflows` 与 `GET /api/runs` 均返回 404。
- 后端删除：删除旧 `routes_workflows.py`、`routes_runs.py`、`run_events.py`，以及旧 Artifact、Connector、Preparation、Workflow、Case Executor、Scheduler、Results、Run Repository 和 Run Models 模块。
- Target 保留：新增 `execution/targets.py`，以独立 `TargetRepository` 管理现有 `targets` 表；旧 Workflow/Run 表即使仍存在于本机 SQLite，也不再被程序读取或通过 API 暴露。
- 测试清理：删除只验证旧 Artifact、Connector、Run Repository、Preparation、固定 Workflow、Case Executor、Scheduler、Run API 和 Run Events 的测试；Target 测试改为验证独立仓储初始化、重启回读和 CRUD。
- 专项验证：`uv run pytest tests/test_targets.py tests/test_execution_frontend.py tests/test_web_app.py -q`，结果 `37 passed, 1 warning`。
- 静态验证：保留 Python 文件通过 `py_compile`；`node --check web/static/execution.js` 和 `git diff --check` 通过。
- 引用验证：在 `web/` 和 `execution/` 生产源码中扫描 `/api/runs`、`/api/workflows`、旧路由、`RunRepository`、`RunScheduler`、`WorkflowService` 和 `CaseWorkflowExecutor`，结果为零命中。
- 全量回归：`uv run pytest -q`，结果 `153 passed, 6 skipped, 1 warning`，耗时 11.41 秒；6 个跳过项为未注入真实模型凭据的 live 测试，warning 仍为既有 Starlette/httpx 弃用提示。
- 依赖结论：Step 2 已通过；下一步必须先确认 `definition.json`、HTTP 双模式和凭据规则，再建立四类大写工具模板模型。

### Step 3：冻结首批新模板协议（completed，2026-07-20）

- `definition.json`：选择简化字段列表，不实现完整 JSON Schema。输入输出字段使用 `name / type / required / description / example`；复杂对象在当前迭代统一声明为 `JSON`。
- HTTP 双模式：使用大写 `CONFIG / CODE` 作为明确执行模式；切换时保留配置和代码两边内容，但运行时只执行当前模式。
- Python 数据协议：继续遵守已确认的 `inputs / config / response`；`inputs` 是动态上游数据，`config` 是节点持久配置，`response` 是本次标准 JSON 输出。
- 凭据决策：独立凭据仓储、凭据槽、Workflow 默认绑定、节点覆盖、运行时秘密解析和导入后重新绑定全部延后，写入待优化清单，不阻塞当前快速迭代。
- 当前迭代边界：新模板模型不增加 `credential_id`、凭据仓储表或绑定 API/UI；`config` 保持通用 JSON。不得因此宣称模板导出已具备完整秘密保护能力。
- 安全风险：用户仍可能把 API Key、Authorization、Cookie、Token 或密码写入 `config` 或 `main.py`。发布/导出前的已知字段清理、代码秘密扫描和日志脱敏仍未实现，相关功能完成前不得宣称模板包可安全公开分享。
- 验证：逐项对照用户选择 `1A / 2A` 和“凭据功能待优化、当前跳过”的最新决定，本计划已移除凭据功能对 T13.2.2/T13.2.3 的阻塞依赖；`git diff --check -- PLAN.md` 必须通过。
- 依赖结论：Step 3 已完成，可以开始 Step 4 建立四类大写工具模板模型和空仓储。

### Step 4：建立四类大写工具模板模型、仓储和 CRUD API（completed，2026-07-20）

- 目标：在空 `tool_registry/` 上建立不兼容旧协议的四类工具模板数据层，为后续前端、导入导出、独立测试和画布深拷贝提供唯一事实模型。
- 模块替换：删除旧 `web/tool_registry.py` 和 `web/routes_tools.py`；新增 `web/tool_templates.py` 和 `web/routes_tool_templates.py`。
- API：新入口为 `/api/tool-templates`；旧 `/api/tools` 不再注册并返回 404。
- 类型：`manifest.json`、`definition.json` 和 API 只接受 `HTTP / AGENT / LLM / SCRIPT`；小写 `http / agent / llm / script` 由 Pydantic 直接拒绝，不做规范化。
- 包结构：每个模板目录必须包含 `manifest.json + definition.json`；AGENT、LLM、SCRIPT 必须包含 `main.py`；HTTP `CONFIG` 模式可无 `main.py`，HTTP `CODE` 模式必须包含。
- 简化字段：输入输出使用 `name / type / required / description / example`，字段类型当前限定为 `STRING / NUMBER / INTEGER / BOOLEAN / JSON`；重复字段名和非法 JSON example 被拒绝。
- 通用配置：`definition.config` 保存严格 JSON 对象；当前不包含凭据引用或绑定字段。
- HTTP：`execution_mode` 只接受 `CONFIG / CODE`；配置结构包含 Method、URL、Headers、Params、Body Type 和 Body；从 CODE 切回 CONFIG 时已保存的 `main.py` 继续保留。
- 仓储：支持显式刷新、列表、读取、创建、整体更新和删除；模板 ID 与目录名一致，ID 和类型创建后不可修改，同 ID 拒绝覆盖。
- 不兼容验证：旧目录只有 `manifest.json + main.py` 时刷新结果明确报告“缺少 definition.json”，不会加载到有效快照；旧 `/api/tools` 返回 404。
- 测试清理：删除旧工具迁移、旧小写类型、六参数 Agent、旧 `/api/tools`、旧 SSE、旧 ZIP 和旧真实模型工具矩阵测试，新增 `tests/test_tool_templates.py`。
- 专项验证：`uv run pytest tests/test_tool_templates.py -q`，结果 `11 passed, 1 warning`。
- 静态验证：`web/tool_templates.py`、`web/routes_tool_templates.py`、`web/app.py` 通过 `py_compile`；`git diff --check` 通过。
- 未覆盖：本步未实现 ZIP 导入导出、模板独立执行、SSE/中断、工具模板前端、画布深拷贝、发布模板和凭据保护，不得把 CRUD 通过解释为完整模板流程通过。
- 依赖结论：Step 4 已通过，可以进入 Step 5 工具模板前端和画布深拷贝；独立执行需要在后续执行器子任务单独验证。

### Step 5：工具模板前端、画布深拷贝和大写状态统一（completed，2026-07-20）

- 目标：提供四类大写工具模板的桌面管理入口，并验证模板复制到画布后成为不依赖来源模板的完整节点副本。
- 前端输出：一级导航改为“工具模板”，提供 `HTTP / AGENT / LLM / SCRIPT` 大写类型创建、筛选、编辑和删除；旧运行中心入口已移除。
- 画布输出：Studio 顶部新增工具模板面板，从 `/api/tool-templates` 加载模板；选择模板时深拷贝 `definition` 和 `main_py`，节点不保存来源模板 ID。
- 节点协议：节点类型统一为 `START / HTTP / AGENT / LLM / SCRIPT / END`；运行状态统一为 `PENDING / RUNNING / PASSED / FAILED`。
- 代码编辑：真实浏览器首次验证发现模板 `main.py` 虽已进入节点对象，但编辑器仍显示旧默认代码；现已改为受控读取和写回节点 `mainPy`，空白 Python 节点默认使用 `response = inputs`，符合 `inputs / config / response` 新协议。
- 独立性验证：通过 UI 创建并保存一个临时 AGENT 模板，复制到画布后确认名称、说明和 `main.py` 正确；在画布中把代码修改为节点专属内容并保存，再通过新 API 删除仓库模板。删除后模板面板显示为空，但画布节点、专属代码和已保存状态仍保留，证明没有运行时来源引用。
- 状态与耗时 E2E：临时画布节点从 `PENDING` 经运行后进入 `PASSED`，耗时从 `0ms` 累加并在完成后冻结为本次实测的 `907ms`；节点右上角只有运行按钮。桌面视口为 `1440x900`，页面横向溢出为 `0px`，截图未发现控件重叠或文本越界。
- 数据清理：E2E 临时模板已通过 `DELETE /api/tool-templates/{id}` 删除；`tool_registry/` 已恢复为只包含 `.gitkeep`。
- 专项验证：`uv run pytest tests/test_tool_templates.py tests/test_tool_templates_frontend.py tests/test_execution_frontend.py tests/test_targets.py tests/test_web_app.py -q`，结果 `51 passed, 1 warning`。
- 构建与静态验证：`npm run build` 成功；`node --check` 覆盖 `app.js`、`tool-templates.js`、`execution.js` 和 Workflow bundle；`git diff --check` 通过。
- 全量回归：`uv run pytest -q`，结果 `85 passed, 1 warning`；warning 为既有 Starlette/httpx 弃用提示。旧真实模型测试已随不兼容旧工具执行协议删除，因此本轮没有 live 跳过项，也不得用本结果宣称新执行器已通过真实模型验证。
- 未覆盖：模板 ZIP 导入导出、模板独立执行、SSE/中断、HTTP CONFIG 执行器、Workflow 持久化、画布发布模板和凭据保护均尚未实现。`web/static/app.js` 中仍有不可达的旧工具管理前端代码，旧 Worker 模块当前也未通过 API 暴露；应在对应替换步骤删除，不能把不可达解释为兼容支持。
- 依赖结论：Step 5 已通过，可以进入 Step 6 四类工具模板 ZIP 导入导出；凭据仓储与绑定继续保留在第 22 节，不作为后续实现前置条件。

### Step 6：四类工具模板 ZIP 导入导出（completed，2026-07-20）

#### Step 6.1：安全归档层与批量原子写入（completed）

- 目标：在不把 ZIP 解压到文件系统的前提下解析和生成统一模板包，并确保任一模板无效或 ID 冲突时整批不写入。
- 输入格式：只允许 `{id}/manifest.json + {id}/definition.json + 可选 {id}/main.py`；一个 ZIP 可以包含一个或多个模板。
- 安全边界：拒绝绝对路径、`..`、反斜杠路径、符号链接、加密条目、重复路径、未知文件、超过 300 个条目、压缩包超过 20 MB、解压后超过 50 MB以及异常压缩比。
- 不兼容规则：根目录旧 `manifest.json + main.py` 和缺少 `definition.json` 的旧 Script / Agent 包均明确拒绝。
- 仓储输出：新增批量创建操作；写入前统一检查包内重复 ID 和仓储现有 ID，写入中异常时删除本批已创建目录并同步回滚内存快照。同名模板仍允许，模板 ID 冲突拒绝覆盖。
- 专项验证：`uv run pytest tests/test_tool_template_archives.py tests/test_tool_templates.py -q`，结果 `18 passed, 1 warning`；覆盖多模板往返、HTTP CONFIG 无 `main.py`、路径穿越、旧布局、未知文件、同 ID 冲突和无部分写入。
- 静态验证：`web/tool_templates.py`、`web/tool_template_archives.py` 通过 `py_compile`；相关文件 `git diff --check` 通过。
- 依赖结论：Step 6.1 已通过，可以开始 Step 6.2 导入导出 API；尚未接入 Web API 和前端按钮。

#### Step 6.2：模板 ZIP 导入导出 API（completed）

- 导入 API：`POST /api/tool-templates/import` 接收单个 `.zip` 文件；先限制读取到 20 MB，再调用安全归档层整包解析和批量原子写入。成功返回导入数量和完整模板列表。
- 导出 API：`POST /api/tool-templates/export` 接收 `template_ids`；非空时只导出指定模板，空列表导出全部。重复请求 ID 去重，任一 ID 不存在时拒绝请求，不生成不完整包。
- ID 规则：导入保留包内模板 ID；目标仓储已有同 ID 时整包返回 400，不覆盖、不自动换 ID。同名但不同 ID 仍允许。
- 往返验证：在源仓储创建 AGENT 和 HTTP 模板，仅导出指定 AGENT 后切换到新的空仓储导入，模板对象与 `manifest.json / definition.json / main.py` 内容保持一致并可由仓储回读。
- 失败验证：含“一个新模板 + 一个冲突模板”的 ZIP 导入返回 400，新模板目录没有产生；旧根目录包和非 `.zip` 文件均返回 400，仓储保持为空。
- 专项验证：`uv run pytest tests/test_tool_template_archives.py tests/test_tool_templates.py -q`，结果 `21 passed, 1 warning`。
- 静态验证：`web/routes_tool_templates.py`、归档层和仓储通过 `py_compile`，相关文件 `git diff --check` 通过。
- 依赖结论：Step 6.2 已通过，可以开始 Step 6.3 工具模板页面导入导出和桌面 E2E。

#### Step 6.3：工具模板页面与 ZIP 往返 E2E（completed）

- 前端输出：工具模板页新增“导入 ZIP”“导出全部”，每行新增仅图标的“导出工具模板”；文件输入支持一次选择多个 ZIP，并逐包累计导入数量和失败原因。
- 安全提示：每次导出前明确提示当前不会自动清理 `config` 或 `main.py` 中的凭据，只能交给可信接收者；凭据仓储、自动剥离和脱敏仍属于第 22 节待优化项。
- 真实流程：在新启动的 8013 服务中通过页面创建 SCRIPT 模板，填写 Inputs、Config、Outputs 和 `main.py`；调用同一真实导出 API 生成标准 ZIP，删除源模板，再调用真实导入 API恢复模板。浏览器刷新后名称、说明、大写类型和四段完整内容均与导出前一致。
- UI 验证：页面显示多 ZIP 导入、导出全部和单模板导出三个入口；`1440x900` 桌面截图未发现控件重叠或文本越界，页面横向溢出小于等于 `0px`。
- 自动化限制：当前浏览器控制层不提供本地文件输入能力，无法自动执行隐藏 `<input type="file">` 的文件选择；真实 ZIP 上传改由同一 8013 服务 API执行，随后由浏览器完成页面回读。文件选择事件绑定由前端专项测试和 JavaScript 语法检查覆盖。
- 数据清理：E2E 模板、临时 ZIP 和 8013 测试服务均已清理；`tool_registry/` 恢复为只含 `.gitkeep`。
- 专项验证：`uv run pytest tests/test_tool_template_archives.py tests/test_tool_templates.py tests/test_tool_templates_frontend.py -q`，结果 `23 passed, 1 warning`。
- 构建与静态验证：`npm run build` 成功；Python `py_compile`、四个相关 JavaScript `node --check` 和 `git diff --check` 均通过。
- 全量回归：`uv run pytest -q`，结果 `95 passed, 1 warning`；warning 仍为既有 Starlette/httpx 弃用提示。
- 未覆盖：模板独立执行、SSE/中断、HTTP CONFIG 执行器、Workflow 持久化、画布发布模板和凭据保护尚未实现。
- 依赖结论：Step 6 已完成，可以进入 Step 7 模板独立执行；ZIP 包格式不再阻塞后续跨环境模板测试。

### Step 7：工具模板独立执行（completed，2026-07-20）

#### Step 7.1：统一可中断执行内核（completed）

- 目标：彻底替换旧 Agent 六参数和 `${...}` 编译协议，让四类模板在进入 Workflow 前即可按新协议真实运行。
- 模块替换：删除 `web/agent_runtime.py` 和 `web/agent_worker.py`；新增通用 `tool_runtime.py`、`tool_worker.py` 和 `tool_execution.py`。
- Python 协议：AGENT、LLM、SCRIPT 以及 HTTP CODE 在独立子进程顶层获得 `inputs`、`config`，并通过顶层 `response` 返回严格 JSON；不再执行旧固定模板参数替换。
- HTTP CONFIG：同样在可终止子进程内使用 httpx 发起真实请求；支持 Method、URL、Headers、Params、RAW、FORM_DATA、FORM_URLENCODED 和 BINARY body，标准 response 包含 `status_code / headers / body`，非 2xx 作为执行失败。
- 运行控制：统一 120 秒默认超时、运行 ID 占用、预中断、进程树终止、stdout/stderr 流式日志和显式 flush；NaN、Infinity、循环引用及不可 JSON 序列化 response 均拒绝。
- 修复记录：首轮测试发现 Windows 子进程协议中文受系统代码页影响，已改为 ASCII JSON 转义传输并在解析后恢复 Unicode；同时修复空 Params 覆盖 URL 原有查询串的问题。
- 专项验证：`uv run pytest tests/test_tool_execution.py tests/test_run_stream.py -q`，结果 `10 passed`；覆盖三类 Python 成功、config 合并、无换行 flush、严格 JSON 失败、超时、中断、真实 HTTP CONFIG 请求、日志顺序/上限和单消费者。
- 静态验证：三个新执行模块通过 `py_compile`，相关文件 `git diff --check` 通过。
- 依赖结论：Step 7.1 已通过，可以开始 Step 7.2 启动、SSE 和中断 API；尚未提供模板页面运行入口。

#### Step 7.2：模板运行启动、SSE 和中断 API（completed）

- 启动：`POST /api/tool-templates/{template_id}/runs` 接收本次 `run_id / inputs / timeout_seconds`，快照当前模板对象后立即返回 `RUNNING`；测试 inputs 和超时不写回模板。
- 日志与结果：`GET /api/tool-templates/runs/{run_id}/events` 使用无回放、单消费者 SSE，按序发送 `log`，终态发送 `complete` 或 `interrupted`；终态包含严格 JSON response、latency 和日志截断标志。
- 中断：`POST /api/tool-templates/runs/{run_id}/interrupt` 调用统一进程树终止；不存在的运行返回 404，重复运行 ID 返回 409。
- 失败协议：用户代码异常、NaN/Infinity 等 response 序列化错误保留 Traceback 日志并以 `ok: false` 完成，不使用旧 `repr()` 回退。
- 专项验证：`uv run pytest tests/test_tool_template_runs.py tests/test_tool_execution.py tests/test_run_stream.py -q`，结果 `13 passed, 1 warning`；覆盖真实 API启动、SSE 日志、成功 response、严格失败、重复 ID、中断和缺失运行。
- 静态验证：路由、事件流和执行模块通过 `py_compile`；相关文件 `git diff --check` 通过。
- 依赖结论：Step 7.2 已通过，可以开始 Step 7.3 模板编辑页独立测试面板和桌面 E2E。

#### Step 7.3：模板独立测试页面、旧执行链清理和 E2E（completed）

- 页面输出：模板编辑页新增“独立测试”区，包含本次 Inputs JSON、运行/中断、`PENDING / RUNNING / PASSED / FAILED` 状态、100ms 累计耗时、实时日志、response 和清空按钮。
- 运行语义：点击运行先保存当前编辑内容但不刷新页面，再启动新 Worker，确保执行眼前版本；测试 Inputs、状态、耗时和日志均不写入模板，刷新后消失。
- 浏览器成功流程：真实 SCRIPT 模板输出 `stream-log`，使用持久 `config.prefix` 和本次 `inputs.question` 生成 `response.answer`；页面实测 `RUNNING → PASSED`，终态耗时 240ms，日志与 response 完整显示。
- 浏览器中断流程：把同一模板改为输出日志后休眠 10 秒，运行中点击中断；页面进入 `FAILED`，耗时冻结约 2.1 秒，运行按钮恢复，中断按钮禁用，Worker 及进程树已终止。
- 桌面布局：`1440x900` 截图确认测试 Inputs 和日志区并排、按钮和状态无重叠，页面横向溢出小于等于 `0px`。
- 彻底清理：删除不可达的旧 `/api/tools` 前端管理、旧 Agent/Script SSE UI、旧工具弹窗、旧 Agent Worker/Runtime；删除只服务旧工具编辑器的 CodeMirror 源码、bundle、测试、npm 依赖和构建步骤。生产源码扫描 `/api/tools`、`agent_runtime`、`agent_worker` 均为零命中。
- E2E 清理：临时模板和 8013 测试服务已删除，`tool_registry/` 只保留 `.gitkeep`。
- 专项验证：执行内核/运行 API/事件流/前端面板结果 `15 passed, 1 warning`；清理后的前端专项结果 `16 passed, 1 warning`。
- 构建与静态验证：`npm run build` 现只构建 Workflow bundle并成功；Python 编译、JavaScript 语法和 `git diff --check` 通过。
- 全量回归：`uv run pytest -q`，结果 `103 passed, 1 warning`；warning 为既有 Starlette/httpx 弃用提示。
- 未覆盖：本步没有真实供应商 API Key，因此只证明新 Python Worker 和本地 HTTP CONFIG 真实请求；不得宣称 DeepSeek/Qwen 新协议 live 矩阵已通过。画布发布模板、Workflow 持久化、DAG 调度、Run 追溯和凭据保护尚未实现。
- 依赖结论：Step 7 已完成，可以开始 Step 8 画布工具发布为独立新模板。

### Step 8：画布工具发布为独立模板（completed，2026-07-20）

#### Step 8.1：独立发布 API 与 API Key 清理（completed）

- 发布契约：`POST /api/tool-templates/publish` 接收完整大写类型、名称、说明、definition 和可选 `main.py`；后端每次生成新的模板 ID，不接受来源模板 ID，不覆盖现有模板，同名允许。
- 独立性：重复发布同一请求生成两个不同 ID 的完整模板，发布对象与当前画布节点及任何来源模板均无运行时引用。
- 秘密处理：发布时递归清空 `config` 中明确命名为 `api_key / apiKey` 的值，保留配置结构；不猜测性修改 Python 代码中的字符串。Authorization、Cookie、Token、其他密码和日志脱敏仍属于待优化范围。
- 校验：请求 `type` 必须与 `definition.type` 一致，Python 类型和 HTTP CODE 继续由 ToolTemplate 模型强制要求 `main.py`。
- 专项验证：`uv run pytest tests/test_tool_templates.py -q`，结果 `13 passed, 1 warning`；覆盖不同 ID、同名、嵌套 API Key 清理、代码保留和类型不匹配无写入。
- 静态验证：发布路由通过 `py_compile`，相关文件 `git diff --check` 通过。
- 依赖结论：Step 8.1 已通过，可以开始 Step 8.2 画布节点定义转换、右键发布和桌面 E2E。

#### Step 8.2：画布右键发布与桌面 E2E（completed）

- 入口：HTTP、AGENT、LLM、SCRIPT 节点右键菜单新增“发布为工具模板”；Start/End 系统节点不显示该命令。节点卡片右上角仍只有运行，编辑器标题栏仍只有运行/保存/关闭。
- 定义转换：模板来源节点优先深拷贝其内嵌 definition；空白节点生成简化 inputs/outputs/config。HTTP 节点把 Headers、Params、Body Type 和 Body 行转换回标准 HTTP definition；Python 节点携带当前 `mainPy`。
- 发布行为：前端只发送完整类型、名称、说明、definition 和 `main_py`，不发送或保存来源模板 ID；发布成功后仅把后端返回的新模板加入当前模板面板缓存，不反向绑定当前节点。
- 风险提示：发布确认明确说明 config API Key 会清空、代码秘密不会自动修改；后端继续作为最终清理边界。
- 浏览器 E2E：在空仓储的 Studio 中右键“规则校验”SCRIPT，确认菜单存在发布项并完成确认；页面显示成功 Toast，模板面板立即出现“规则校验 SCRIPT”。后端回读得到新 UUID、空 inputs/outputs/config 和 `response = inputs`。Start 节点右键菜单只有运行/拷贝/删除，无发布项。
- 清理回归：真实浏览器首次进入 Workflow 时发现 `execution.js` 尚有三个已删除 CodeMirror 销毁函数调用，导致主区为空；已删除残留调用并增加生产前端零引用断言，导航复测通过。
- 数据清理：E2E 发布模板和 8013 测试服务均已删除，`tool_registry/` 只保留 `.gitkeep`。
- 专项验证：`uv run pytest tests/test_execution_frontend.py tests/test_tool_templates.py -q`，结果 `21 passed, 1 warning`；修复导航后 Studio 专项 `8 passed, 1 warning`。
- 构建与静态验证：`npm run build`、Python `py_compile`、JavaScript `node --check` 和 `git diff --check` 全部通过。
- 全量回归：`uv run pytest -q`，结果 `106 passed, 1 warning`；warning 为既有 Starlette/httpx 弃用提示。
- 依赖结论：Step 8 已完成。下一阶段是新版 Workflow 持久化与 DAG 协议；分支/汇合、端口、失败传播、循环和输入映射仍在第 16 节列为未确认业务规则，未确认前不得自行实现执行语义。

### Step 9：发布前全量验收与环境清理（completed，2026-07-20）

- 目标：确认 T13.2 当前已实现范围可构建、可回归且不包含 E2E 临时数据，再提交并推送本次不兼容重构。
- 浏览器清理：恢复临时 `1440x900` 视口覆盖，并清理 `http://127.0.0.1:8013/` 的测试标签页；不影响用户当前 `8012` 服务页面。
- 数据清理：复核 `tool_registry/` 只包含 `.gitkeep`，没有临时模板目录或测试 ZIP。
- 生产构建：`npm run build` 通过，重新生成 Workflow JavaScript/CSS bundle。
- 全量回归：`uv run pytest -q` 结果为 `106 passed, 1 warning`，耗时 3.79 秒；warning 仍为既有 Starlette/httpx 弃用提示。
- 静态检查：生产 Python `compileall`、`app.js / tool-templates.js / execution.js / workflow-canvas.js` 的 `node --check`、常见真实令牌值模式扫描和 `git diff --check` 全部通过；README 中只存在环境变量名和 `<your-key>` 占位示例。
- E2E 覆盖：本阶段已覆盖工具模板 CRUD、ZIP 往返、模板删除后的画布深拷贝、SCRIPT 独立执行、运行中断、画布发布新模板、系统节点禁止发布，以及桌面布局无横向溢出或可见重叠。
- 未覆盖与风险：没有真实供应商 API Key，因此不得宣称新 AGENT/LLM Worker 已通过 DeepSeek/Qwen live 验证；Workflow 持久化、DAG 执行、Run 追溯和独立凭据仓储仍未实现，必须先完成第 16 节业务规则确认。
- 价值验证：新手可从四类模板复制完整定义到画布后少量修改，画布个性化节点也可发布为独立模板；两者无来源绑定，模板删除、更新或同名均不会改变既有画布节点。

### Step 10：模型管理（in progress，2026-07-21）

#### 业务背景与目标（Why）

- Agent Bench 当前需要在 LLM、AGENT 和其他模型调用场景中反复填写供应商连接；本功能集中管理供应商、BASE_URL、API Key 和已选模型，减少重复配置并为后续画布节点选择模型提供稳定数据源。
- 当前阶段不建设供应商插件生态或深度 SDK 适配，只支持 OpenAI-compatible 与 Anthropic 模型发现；Header Override、Body Override 和导入导出继续延后。

#### 用户与真实场景（Who & Where）

- 本机 Workflow / Agent 作者从左侧一级导航进入“模型管理”，搜索和维护已有供应商连接。
- 点击“新增模型”进入独立新增页面，完成测速、获取模型、选择多个模型并保存；编辑时复用同一页面和完整配置。
- 一条记录代表一个供应商连接及其多个已选模型，同名供应商允许由独立 ID 区分。

#### 已确认规则与优先级（What & When）

- P0：供应商列表、新增、编辑、删除、搜索、BASE_URL 测速、模型发现、手工模型兜底和重启后持久化。
- 供应商名称、官网链接选填；API Key、BASE_URL 必填；至少添加一个模型后才能保存。
- API Key 明文保存在本机 SQLite；列表页不展示 Key，编辑页按用户选择完整回显。不得把真实 Key 写入代码、测试、文档、日志或 Git。
- 协议探测复用已验证的 OpenAI Bearer 与 Anthropic `x-api-key` 逻辑；模型端点支持完整版本路径与 `/v1/models`、`/models` 补全。
- Header Override、Body Override、凭据加密/绑定和导入导出不在本批实现范围，继续保留在待优化项。

#### 可独立验证子任务

| 子任务 | 目标 | 输入 | 输出 | 验证方法 | 依赖 |
|---|---|---|---|---|---|
| Step 10.1 | 本地持久化与 API | 已确认字段和模型发现原型 | SQLite Repository；CRUD、测速、模型发现 API | Repository 重启回读；API CRUD；Stub 真实 HTTP；非法 URL/响应和密钥不进入错误信息 | 无 |
| Step 10.2 | 一级导航、列表和新增/编辑页 | Step 10.1 API；独立原型视觉 | 模型管理列表、搜索、独立表单、连接状态、模型选择和删除确认 | 前端契约测试；JS 语法；桌面浏览器新增/编辑/搜索/删除 | Step 10.1 |
| Step 10.3 | 集成验收与发布 | 完成的前后端 | E2E 记录、全量回归、更新计划并推送 | `pytest`、`npm run build`、Python/JS 静态检查、真实浏览器业务流、密钥扫描 | Step 10.1-10.2 |

#### 验收标准与价值验证（How to Measure）

- 左侧“模型管理”可稳定进入，新增按钮打开独立页面，布局与供应商连接原型一致且适配现有明暗主题。
- 使用本地 OpenAI-compatible Stub 完成测速、模型发现、选择多个模型、保存、列表回读、编辑和删除；页面无横向溢出、控件重叠或控制台错误。
- 服务重启后供应商、官网、BASE_URL、完整 API Key 和模型列表保持一致；列表和普通错误响应不泄露 API Key。
- 受影响专项测试、前端构建、静态检查和全量回归全部通过后才能标记完成。

#### Step 10.1：模型供应商持久化与 API（completed）

- 持久化：复用被 Git 忽略的 `run_storage/agent_bench.sqlite3`，新增独立 `model_providers` 表；一条记录保存可选名称/官网、完整 API Key、BASE_URL、协议、模型端点和多个模型。
- API：新增供应商列表、创建、单条读取、完整更新、删除、BASE_URL 测速和模型发现接口；列表与删除响应使用不含 API Key 的摘要，单条编辑接口按已确认的 3B 完整回显。
- 协议探测：支持 OpenAI Bearer 与 Anthropic `x-api-key`，自动处理根 BASE_URL、版本化 `/v1` 路径以及 chat/responses/messages 完整端点；失败允许前端进入手工模型模式。
- 安全边界：BASE_URL 拒绝非 HTTP(S)、内嵌用户名密码、query、fragment 和非法端口；上游错误只返回协议、端点、HTTP 状态或异常类型，不返回请求 Header、响应正文或 API Key。
- 验证：`uv run pytest tests/test_model_providers.py -q` 结果 `13 passed, 1 warning`；覆盖 Repository 重启回读、完整 CRUD、列表密钥剥离、字段校验、端点归一化、真实本地 OpenAI-compatible HTTP 探测和错误密钥扫描。
- 静态检查：新增后端与测试通过 `py_compile`，相关文件 `git diff --check` 通过；warning 为既有 Starlette/httpx 弃用提示。
- 依赖结论：Step 10.1 已通过，可以开始 Step 10.2 前端；尚未接入一级导航或页面。

#### Step 10.2：一级导航、模型列表和新增/编辑页（completed）

- 导航与资产：左侧一级导航新增“模型管理”；新增独立 `model-providers.js/css`，静态资源使用显式无缓存 GET 路由，不把模型业务继续堆入 `app.js`。
- 管理列表：支持新增、刷新、供应商/地址/协议/模型前端搜索、名称进入编辑、官网跳转、协议与模型摘要、更新时间、编辑和删除；API Key 不进入列表响应和 DOM。
- 新增/编辑页：复用供应商连接原型的双列表单、连接状态带、测速、模型发现、下拉选择、手工模型兜底和已选模型列表；增加保存/返回，编辑页按已确认 3B 完整回显 API Key。
- 主题和布局：全部颜色复用现有语义变量并提供协议状态的暗色覆盖；仅实现桌面布局。首次 `1440x900` 截图发现时间内容把操作列推入表格内部滚动区，已改为固定列布局，复测操作按钮完整可见、页面与表格横向溢出均为 0。
- 浏览器 E2E：在 8026 Agent Bench 与 8027 本地 OpenAI-compatible Stub 中完成左侧导航、新增、HTTP 200 测速、发现 3 个模型、选择 `deepseek-chat / qwen-max`、保存、无结果/模型名搜索、编辑页密钥完整回显、名称更新、服务重启后 SQLite 回读和页面删除清理。
- E2E 修复：刷新首页发现既有 `viewSets()` 引用已删除的 `setSortMark` 导致主区为空；补回最小排序标记函数并新增回归测试。全新浏览器标签复测测试集首屏与模型管理均可渲染，控制台错误为 0。
- 专项验证：模型后端、前端、主题和 Web 入口组合结果 `22 passed, 1 warning`；E2E 修复后的集合页/模型页组合结果 `22 passed, 1 warning`；JavaScript/Python 语法和相关 `git diff --check` 通过。
- 数据清理：E2E 模型供应商已从 SQLite 删除；列表恢复为 0 个供应商。8027 Stub 将在最终回归后关闭，8026 Agent Bench 保留为交付服务。
- 依赖结论：Step 10.2 已通过，可以开始 Step 10.3 全量回归、计划收口和发布。

#### Step 10.3：集成验收与发布（completed）

- 全量回归：`uv run pytest -q` 结果 `123 passed, 1 warning`，耗时 12.47 秒；warning 为既有 Starlette/httpx 弃用提示。
- 生产构建：`npm run build` 成功，Workflow JavaScript/CSS bundle 正常生成。
- 静态检查：`execution/`、`web/` 通过 Python `compileall`；`app.js / model-providers.js / tool-templates.js / execution.js` 通过 `node --check`；全仓 `git diff --check` 通过。
- 安全扫描：带令牌边界的真实 `sk-` Key 形态扫描为零命中。初次宽泛扫描命中的 `sk-background / sk-stroke` 均为 Workflow bundle 中 CSS 标识片段，不是凭据。
- 数据与服务：SQLite 中 E2E 供应商数量为 0；本地 Stub 8027 已关闭；集成后的 Agent Bench 服务保留在 `http://127.0.0.1:8026/`，首页与模型管理均返回正常。
- 最终价值验证：用户可以从一级导航集中管理供应商连接，通过 API Key + BASE_URL 自动发现模型或手工添加，保存多个模型并在重启后继续编辑；列表不暴露密钥，编辑页按明确选择完整回显。
- 已知风险：API Key 当前按用户选择在本机 SQLite 明文保存并在编辑页完整回显；任何能访问该本机 Web 页或数据库的用户都可读取。凭据加密、绑定和脱敏仍属于第 22.1 节待优化项。
- 结论：Step 10 全部验收通过，可以提交并推送当前分支。

### Step 11：Workflow 工具内聚与 LLM 模型参数（completed，2026-07-21）

#### 最新业务方向（Why / Who & Where）

- 用户明确提出删除工具管理页面与耦合逻辑，工具节点只在 Workflow 中创建、编辑和保存；此前“工具模板库作为起点、画布发布回模板”的方向被本节最新决策取代。
- Workflow / Agent 作者从模型管理维护供应商连接与模型清单，在 LLM 节点中引用已有模型，不重复填写 API Key 或 BASE_URL。
- LLM 节点的模型选择 UI 参考用户提供的 Dify 截图：顶部搜索、供应商分组折叠、供应商连接状态、模型单选和当前项勾选。
- LLM 节点需要允许用户自行添加高级参数；Header/Body Override 仍属于模型连接层后续能力，不与本批节点参数混为一谈。

#### 行业调研：高级参数与默认值

- Dify 使用供应商/具体模型下发的 `parameter_rules` 动态生成控件，可选参数通过开关决定是否写入；SDK 通用模板为 Temperature `0`、Top P `1`、Presence/Frequency Penalty `0`、Max Tokens `64`，但具体模型可覆盖，例如 `gpt-4o-mini` 把 Max Tokens 改为 `512`，`gpt-5` 则去掉常规采样参数并增加 Reasoning Effort `medium`、Verbosity `medium`、Streaming `true`、Service Tier `auto`。
- n8n 的 OpenAI Chat Model 使用固定 Options 集合：Temperature `0.7`、Top P `1`、Presence/Frequency Penalty `0`、Max Tokens `-1`（不限制）、Timeout `60000ms`、Max Retries `2`、Response Format `text`。
- Langflow OpenAI 组件默认 Temperature `0.1`、Seed `1`、Max Retries `5`、Timeout `700s`，Max Tokens 未设置时传 `None`；同时提供任意 `model_kwargs` 字典作为供应商扩展逃生口。统一 Language Model 组件只保留 Temperature `0.1`、Stream `false` 和可选 Max Tokens。
- Flowise OpenAI Chat 默认 Temperature `0.9`、Streaming `true`；Max Tokens、Top P、Presence/Frequency Penalty、Timeout 和 Stop Sequence 都是可选且不设置默认值。
- 结论：不存在可靠的跨供应商默认参数。Agent Bench 若强行写入平台默认值，会覆盖供应商或具体模型默认行为；当前最稳妥策略是节点默认不发送高级参数，用户显式添加后才持久化和发送。

#### 调研来源

- Dify SDK 参数模板：<https://github.com/langgenius/dify-plugin-sdks/blob/main/src/dify_plugin/entities/model/schema.py>
- Dify `gpt-4o-mini` 与 `gpt-5` 模型 Schema：<https://github.com/langgenius/dify-official-plugins/tree/main/models/openai/models/llm>
- n8n OpenAI Chat Model：<https://github.com/n8n-io/n8n/blob/master/packages/@n8n/nodes-langchain/nodes/llms/LMChatOpenAi/LmChatOpenAi.node.ts>
- Langflow OpenAI / Language Model：<https://github.com/langflow-ai/langflow/tree/main/src/lfx/src/lfx/components>
- Flowise ChatOpenAI：<https://github.com/FlowiseAI/Flowise/blob/main/packages/components/nodes/chatmodels/ChatOpenAI/ChatOpenAI.ts>

#### 专有参数透传补充调研

- `model_kwargs` 是 LangChain 构造参数，不是供应商协议。当前 `ChatOpenAI` 会把 `model_kwargs` 展开为 OpenAI SDK 的顶层调用参数；SDK 未声明的千问/DeepSeek 扩展字段可能直接触发 `TypeError`，通常必须通过 `extra_body` 才能进入 HTTP Body。
- 当前 `ChatAnthropic` 对 `thinking` 和 `output_config` 有显式字段，也会把 `model_kwargs` 合并进请求 payload，但这仍是框架实现细节，不适合作为 Workflow 持久化契约。
- Open WebUI 使用“默认不设置”的标准参数，并在自定义模型管理中提供 `custom_params`；Dify 使用具体模型 Schema 白名单；n8n/Flowise 使用固定 Options；Langflow 使用 `model_kwargs`/`model_kwargs` 字典作为逃生口。它们共同说明 UI 数据应与具体 SDK 解耦。
- Agent Bench 节点字段统一命名为 `modelParameters`：保存原始 JSON 对象。OpenAI-compatible 直连时合并到请求 Body；使用 OpenAI SDK 的用户代码可将其传给 `extra_body`；Anthropic 已知字段可直接展开，未知网关字段可走 SDK 的 `extra_body`。不得把持久化字段命名为 `model_kwargs`。
- 千问 `enable_thinking / thinking_budget`、DeepSeek `thinking / reasoning_effort`、Anthropic `thinking / output_config` 都可以由该 JSON 数据结构表达；最终能否生效仍由所选供应商、模型和协议端点决定，平台不伪造兼容保证。

#### 已确认决策（1A / 2B / 3A）

- 彻底删除工具模板仓储、CRUD/ZIP/独立运行 API、左侧工具模板页面、画布模板面板、深拷贝和发布入口；不保留隐藏后台兼容。通用 Worker、进程中断和运行流内核保留，供后续 Workflow 节点执行复用。
- LLM 高级参数只提供一个任意 JSON 对象编辑器，不提供 Temperature 等固定快捷控件；默认值为 `{}`，平台不主动向供应商发送任何高级参数。
- Token 消耗默认无平台上限：基础请求不发送 `max_tokens` 或 `max_completion_tokens`，由供应商和模型自身上限处理；用户需要限制时可在节点 `modelParameters` 中显式添加。
- LLM 节点只保存 `provider_id + model_name` 和节点自己的高级参数，不复制 API Key、BASE_URL 或完整供应商记录。供应商或模型被删除后，节点显示“模型已失效”并要求重新选择。
- 模型选择器采用用户截图结构：顶部搜索、供应商分组折叠、绿色连接状态、模型单选和当前模型勾选。
- 最新确认采用模型网关式 Body 合并：基础请求、模型级默认参数和节点 `modelParameters` 递归合并，越靠近节点的值优先；数组和非对象值整体替换。
- 用户选择 `1B / 2A`：节点参数可以覆盖包括 `model`、`messages`、`stream` 在内的全部基础请求字段；嵌套对象递归合并，不设置保留字段白名单。

#### 可独立验证子任务

| 子任务 | 目标 | 输入 | 输出 | 验证方法 | 依赖 |
|---|---|---|---|---|---|
| Step 11.1 | 删除工具模板后端和页面 | 1A；现有模板仓储/API/UI | 模板文件、路由、导航、ZIP/运行测试全部删除；通用 Worker 保留 | `/api/tool-templates` 与静态资产 404；生产源码零引用；Worker 专项通过 | 无 |
| Step 11.2 | 删除画布模板耦合 | Step 11.1；当前 React Flow Studio | 顶部模板面板、加载/深拷贝、发布菜单与 API 调用删除；四类空白节点保留 | 前端源码断言、构建、Studio 基线回归 | Step 11.1 |
| Step 11.3 | LLM 模型引用与高级 JSON | 模型管理列表 API；2B/3A；用户 UI 参考 | 分组模型选择器、失效态、`providerId/modelName/modelParameters` 节点状态 | 模型列表加载、搜索/折叠/选择、JSON 校验、删除后失效测试 | Step 11.2 |
| Step 11.4 | 集成验收与发布 | 完成的清理和 LLM 编辑器 | E2E、全量回归、计划收口和 GitHub 提交 | 1440x900 浏览器 E2E、构建、静态检查、全量 pytest、密钥扫描 | Step 11.1-11.3 |

#### Step 11.1：删除工具模板后端和一级页面（completed）

- 删除范围：删除模板 Pydantic/目录仓储、ZIP 归档、CRUD/刷新/导入导出/发布/独立运行 API、模板运行适配器、左侧页面与脚本、迁移脚本、`tool_registry/` 占位和全部模板专项测试；不保留隐藏 API 兼容。
- 保留范围：保留 `tool_runtime.py / tool_worker.py / run_stream.py` 作为 Workflow 节点通用子进程、HTTP、进程中断和 SSE 流内核；模块文案已去除“模板”语义。
- 内核测试重写：`test_tool_execution.py` 不再构造 ToolTemplate，直接发送通用 Worker payload；继续覆盖 Python `inputs/config/response`、无换行 flush、NaN/Infinity、超时、中断和真实 HTTP 请求。
- 页面与文档：删除左侧“工具模板”、`tool-templates.js` 静态路由和专属 CSS；README 与 `.gitignore` 删除 `tool_registry` 说明和规则。
- 专项验证：`uv run pytest tests/test_tool_execution.py tests/test_run_stream.py tests/test_tool_removal.py tests/test_web_app.py -q` 结果 `13 passed, 1 warning`；Python 编译和 `git diff --check` 通过。
- 零引用验证：除下一步待处理的 React Flow 画布源码/CSS 和构建产物外，`web/ execution/ README.md / .gitignore` 对 `tool-template / ToolTemplate / tool_registry / viewToolTemplates` 零命中。
- 依赖结论：Step 11.1 已完成，可以开始 Step 11.2 画布模板耦合删除。

#### Step 11.2：删除画布模板耦合（completed）

- 删除范围：React Flow Studio 顶部“工具模板”入口、模板加载状态和 `/api/tool-templates` 请求、模板深拷贝、发布方法、右键“发布为工具模板”操作及全部专属样式均已删除。
- 保留范围：`HTTP / AGENT / LLM / SCRIPT` 四类空白节点的新增、编辑、复制、连线、状态演示和历史操作继续保留。
- 构建验证：`npm run build` 成功，重新生成 `workflow-canvas.js / workflow-canvas.css`，`node --check web/static/assets/workflow-canvas.js` 通过。
- 专项验证：`uv run pytest tests/test_execution_frontend.py tests/test_tool_removal.py -q` 结果 `10 passed, 1 warning`；`git diff --check` 通过。
- 零引用验证：`web/ execution/ README.md / .gitignore` 以及生成资源对工具模板标识和显示文案零命中。
- 依赖结论：Step 11.2 已完成，可以开始 Step 11.3 LLM 模型引用、任意 JSON 参数和网关式递归合并。

#### Step 11.3：LLM 模型引用、高级 JSON 与网关合并（completed）

- 网关内核：新增与 LangChain 解耦的 OpenAI-compatible 请求组装与 HTTP 传输；合并顺序为“基础请求 → 模型默认参数 → 节点 `modelParameters`”，后层优先，对象递归合并，数组和标量整体替换。
- Token 默认：基础请求不包含 `max_tokens` 或 `max_completion_tokens`，Agent Bench 默认不限制 token 消耗；节点显式填写时仍按普通高级参数合并并透传。
- 覆盖边界：按已确认的 `1B / 2A`，节点参数可覆盖 `model`、`messages`、`stream` 及任意其他 Body 字段，平台不维护保留字段白名单，也不翻译供应商专有参数。
- 节点状态：LLM 节点只保存 `providerId / modelName / modelParameters`；API Key、BASE_URL 和供应商完整记录仍由模型管理持有，不进入 Workflow 节点状态。高级参数默认为空对象 `{}`。
- 选择器 UI：接入不含密钥的 `/api/model-providers` 列表，实现供应商分组、搜索、折叠、连接状态、当前模型勾选和刷新；供应商或模型删除后显示“模型已失效”并禁用节点保存/运行。
- JSON 编辑：使用任意 JSON 对象编辑器；非法 JSON 或顶层非对象时显示明确错误并禁用保存/运行，修复为合法对象后即恢复。
- 自动化验证：`uv run pytest tests/test_model_gateway.py tests/test_execution_frontend.py tests/test_tool_removal.py -q` 结果 `25 passed, 1 warning`；`npm run build`、生成 bundle 的 `node --check` 和 `git diff --check` 全部通过。
- 真实浏览器 E2E：在 `1440x900` 下验证 DeepSeek 选择、搜索过滤、当前项选中、供应商折叠、非法/合法 JSON 切换和无裁切重叠；通过创建临时供应商、选择、删除并刷新，实测“模型已失效”与禁用状态，临时数据已清理。
- 范围约束：新网关内核已可独立真实调用，但新 Workflow Studio 仍是前端本地状态和演示运行，本步没有实现 Workflow 持久化或 DAG 真实执行 API，不得宣称画布端到端模型执行已完成。
- 真实模型验证：新增受 `live` marker 控制的网关集成测试，固定覆盖千问 `qwen3.7-max` 和 DeepSeek `deepseek-v4-pro`；未注入环境变量时安全跳过，不影响公开回归。为验证稳定性，每个模型顺序执行两轮真实请求。
- 真实业务场景：测试使用企业客服 Agent 合规评测，输入用户退款问题、三条明确策略以及一段“未授权即宣称退款完成，并索取身份证、银行卡和验证码”的高风险回复；要求模型输出包含 `passed / score / summary / issues / recommendation` 的严格 JSON。
- 真实调用结果：使用用户提供的两家凭据仅在 pytest 进程内执行 `uv run pytest tests/test_model_gateway.py tests/test_model_gateway_live.py -m live -q`，结果 `4 passed, 4 deselected in 25.22s`。千问和 DeepSeek 各两轮均返回可解析且字段完整的 JSON，均稳定判定该 Agent 回复不通过并输出具体问题和改进建议。
- 覆盖价值：live 请求故意在基础层放入错误模型、错误消息和 `stream: true`，再由节点参数覆盖为真实模型、完整的 system/user 业务消息和 `stream: false`；模型默认层的 `response_format: {"type": "json_object"}` 被保留，千问同时直透 `enable_thinking: false`。四次请求均明确断言不存在 `max_tokens / max_completion_tokens`。
- 密钥边界：API Key 未写入测试、文档、代码、命令输出或 Git 跟踪文件；DeepSeek 密钥从本机模型仓储读入子进程，千问密钥只注入单次 pytest 进程。
- 依赖结论：Step 11.3 及两家真实模型验证已完成，可以进入 Step 11.4 全量回归与发布。

#### Step 11.4：集成验收与发布（completed）

- 业务验收：工具管理一级页面、仓储、CRUD/ZIP/独立运行 API、画布模板面板、深拷贝和发布入口均已删除；`HTTP / AGENT / LLM / SCRIPT` 节点继续由 Workflow Studio 直接创建和编辑。
- LLM 交互验收：`1440x900` 真实浏览器覆盖模型列表加载、搜索、供应商折叠、当前项勾选、DeepSeek 选择、非法/合法高级 JSON、删除供应商后的失效态和禁用操作；截图无裁切、重叠或文本越界。
- 真实模型回归：千问 `qwen3.7-max` 和 DeepSeek `deepseek-v4-pro` 各连续两轮企业 Agent 合规评测，结果 `4 passed, 4 deselected in 25.22s`；全程不发送 token 上限，两家均稳定返回字段完整且业务判定正确的结构化 JSON。
- 全量回归：`uv run pytest -q` 结果 `100 passed, 4 skipped, 1 warning in 11.47s`；4 个跳过项为默认未注入两家凭据时的两轮 live 测试，warning 为既有 Starlette/httpx 弃用提示。
- 构建与静态检查：`npm run build` 成功生成 Workflow JS/CSS bundle；`execution/` 和 `web/` Python `compileall`、`app.js / model-providers.js / execution.js / workflow-canvas.js` 的 `node --check`、`git diff --check` 全部通过。
- 清理与安全：生产源码对 `tool-template / ToolTemplate / tool_registry / viewToolTemplates` 零引用；Git 跟踪及待提交文件中的真实 `sk-` 凭据形态扫描为 0；失效引用 E2E 临时供应商已删除。
- 已知边界：模型网关的请求组装、递归合并和真实 HTTP 传输已验证；画布仍为前端本地草稿与演示运行，尚未把该网关接入 Workflow 持久化和 DAG 执行后端，因此不宣称 Workflow 端到端真实 LLM 执行已完成。
- 价值结论：Workflow 作者可在 LLM 节点引用已管理模型，使用任意 JSON 直透国内外供应商参数，节点优先覆盖模型默认值，并在默认情况下不受 Agent Bench token 上限限制。
- GitHub 发布：主体改造提交为 `8e8b072`（`Remove tool templates and add model gateway`），已推送到 `origin/codex/tool-template-refactor`。

### Step 12：LLM 真实执行、持久化日志与编辑器收敛（in progress，2026-07-21）

#### 业务背景与目标（Why）

- LLM 节点已能选择模型和编辑高级参数，但当前仍存在不属于网关执行器的 Python“代码”页签、与日志重复的独立“参数”页签，且运行仍是 900ms 前端演示，无法支持真实调试。
- 本阶段目标是让 Workflow 作者在 LLM 节点内完成真实模型验证，并在页面刷新后仍能追溯该节点最近 10 次的输入、输出和错误。

#### 用户与真实场景（Who & Where）

- Workflow / Agent 作者在画布双击 LLM 节点，选择已管理模型，填写可选系统提示词和用户提示词模板，可在模板中以 `${变量名}` 引用 Workflow 变量。
- 作者可在系统提示词为空、高级参数为 `{}` 时直接运行节点；用户提示词解析后必须非空，未解析变量必须在发起供应商请求前失败。
- 作者切换到“日志”后，先扫描月日时间、终态、耗时和最终结果摘要，再按需展开某次运行查看完整输入快照、无密钥请求、输出、usage、HTTP 元数据或错误堆栈。

#### 已确认规则与优先级（What & When）

- `1A`：LLM 编辑器删除“代码”和独立“参数”页签，只保留“设置 / 日志”；原参数快照合并到每次日志详情。AGENT / SCRIPT 的代码能力不受影响。
- `2A`：系统提示词和用户提示词放在设置页模型选择之后，系统提示词选填；用户提示词支持 `${变量名}`，单节点验证时从 Workflow 全局变量解析。
- `3B`：Workflow 草稿、节点 ID 和运行日志保存到本机 SQLite，浏览器刷新后可恢复；每个 Workflow 节点只保留最近 10 次尝试，成功和失败都计入，第 11 次完成后删除最旧记录。
- 日志最新确认 `1A`：执行器仍解析模型输出供节点结果和下游使用，但日志展开区不对供应商响应做结构化拆分，只原样打印完整 HTTP Body/SSE；失败时原样打印已脱敏错误与 traceback。
- 变量祖先规则 `1A`：“之前节点”以画布边反向可达的所有祖先节点为准，与画布 x/y 位置无关；未连接到当前节点的分支变量不可见。
- 原生数据契约：阻塞执行的 `request` 是节点实际发出的原生请求数据，`response` 是节点收到的原生响应数据，平台不注入固定 `body / output / usage` 包装字段。输出变量从这两个根对象提取，例如 `request.messages[0].content` 或 `response.usage[total_tokens]`。
- 提取语法：所有 `HTTP / LLM / AGENT / SCRIPT` 节点统一使用受限 Python 风格路径；支持点访问、整数数组下标和字符串字典键，`response.usage["total_tokens"]`、`response.usage['total_tokens']`、`response.usage[total_tokens]` 等价。禁止函数调用、运算、切片及任意代码执行，路径缺失时节点失败并报告完整表达式。
- 列表过滤：支持 `response.data[id==3]`、`response.data[status=="PASSED"].result` 和嵌套条件 `response.data[meta.id==3].name`；条件只支持 `==` 与标量值。过滤结果必须唯一，0 条或多条均失败，不静默取第一条。
- 流式边界 `1A`：流式模式只实时展示并持久化供应商原始 SSE，不解析流式响应、不构造可提取的 `response`、不生成输出变量；页面隐藏输出变量配置但保留草稿值，切回默认阻塞模式后恢复。
- 变量冲突规则 `3A`：全局变量、当前节点输出变量及当前节点全部祖先输出变量在可见范围内禁止同名；草稿保存时直接拒绝并指明冲突节点。不会汇合到同一下游的隔离分支可以使用相同名称。
- 变量面板：每个节点编辑器右上角增加变量按钮，按“全局变量 → 祖先节点 → 当前节点”分组显示变量名和最近成功运行值；未产生值时显示空值状态。
- 参数替换：`${变量名}` 扩展到节点所有字符串参数，字符串值原样替换，对象/数组以 JSON 序列化后嵌入；缺失变量在执行前失败并记录日志。当前阶段首先在已具备真实执行器的 LLM 节点验证，其他节点仍不伪造真实执行结果。
- 提示词交互：用户直接键入 `${变量名}`；删除用户提示词旁的“插入变量”下拉框，节点右上角变量查看按钮继续用于核对可见变量和值。
- 日志安全：API Key、Authorization 和完整供应商记录不得进入 Workflow 草稿或运行日志；日志中的请求 Body 仅包含实际模型请求字段。
- Token 规则不变：平台默认不发送 `max_tokens / max_completion_tokens`，真实节点运行不增加隐式 token 上限。
- 本阶段只建立 Workflow Studio 草稿与 LLM 单节点运行协议，不自行补全 DAG 调度、分支/汇合、失败传播或其他节点的真实执行语义。

#### 验收标准与价值验证（How to Measure）

- LLM 编辑器只显示“设置 / 日志”；设置页依次显示模型、系统提示词、用户提示词、高级参数、运行配置和输出变量，在 `1440x900` 桌面视口无遮挡、重叠或文本越界。
- 有效模型 + 非空用户提示词在空系统提示词和 `{}` 高级参数下可真实运行；`${变量名}` 正确替换，缺失变量产生可追溯的 `FAILED` 记录且不请求供应商。
- 日志折叠栏显示 `MM-DD HH:mm:ss`、`PASSED / FAILED`、耗时和最终结果摘要；展开后能看到完整输入、请求、执行事件、输出、usage 或错误。
- 同一节点制造 11 次运行后 API 和页面均只返回最新 10 次；重启 Repository、刷新页面和重新打开 Workflow 后记录不丢失。
- 千问 `qwen3.7-max` 和 DeepSeek `deepseek-v4-pro` 需要用真实业务提示词完成节点 API 和页面回读验证；不使用短 token 限制或仅回固定字符串的形式化测试。

#### 可独立验证子任务

| 子任务 | 目标 | 输入 | 输出 | 验证方法 | 依赖 |
|---|---|---|---|---|---|
| Step 12.1 | 草稿与日志持久化 | 当前 React Flow 节点/边；3B | SQLite Workflow draft + node run repository、CRUD/日志 API | Repository 重启回读、11 留 10、级联删除、API 严格校验 | 无 |
| Step 12.2 | 真实 LLM 单节点执行 | Step 12.1；模型管理；`${变量名}` | 变量解析、网关请求、非流式/流式响应解析、PASSED/FAILED 持久化日志 | Stub 真实 HTTP、缺变量无上游请求、错误/输出/usage、无密钥 | Step 12.1 |
| Step 12.3 | LLM 布局与前后端联调 | Step 12.1-12.2；1A/2A/3B | 两页签编辑器、草稿保存/恢复、真实运行、10 条可展开日志 | 前端契约、构建、`1440x900` 浏览器 E2E、刷新回读 | Step 12.1-12.2 |
| Step 12.4 | 真实模型、全量回归与发布 | 完成的 LLM 单节点链路 | 千问/DeepSeek 记录、计划收口、GitHub 提交 | live 业务场景、全量 pytest、构建、静态/密钥扫描 | Step 12.1-12.3 |

#### Step 12.1：Workflow 草稿与节点日志持久化（completed）

- 仓储：新增独立 `workflow_drafts / workflow_node_runs` SQLite 表和 `WorkflowDraftRepository`；草稿保存名称、说明、React Flow 节点/边及全局变量，不恢复旧 Workflow/Run 固定拓扑协议。
- 图校验：节点和边 ID 必须非空且唯一，节点 `data` 必须为对象，边的 source/target 必须引用存在节点，Pydantic 继续拒绝未知顶层字段。
- 运行记录：每条记录保存节点/模型身份、输入快照、无密钥请求 Body、事件、输出、usage、HTTP 元数据和结构化错误；终态写入与同节点裁剪在同一事务完成，最多保留 10 条。
- API：新增 `/api/workflow-drafts` 列表/CRUD、单条读取和 `/{workflow_id}/nodes/{node_id}/runs` 日志列表；删除草稿时通过 SQLite 外键级联删除所有节点记录。
- 验证：`uv run pytest tests/test_workflow_drafts.py tests/test_targets.py tests/test_model_providers.py -q` 结果 `48 passed, 1 warning in 9.52s`；覆盖 Repository 重启回读、11 次仅留最新 10 次、FAILED 记录、级联删除、完整 API CRUD 和非法图拒绝。Python 编译和 `git diff --check` 通过。
- 依赖结论：Step 12.1 已通过，可以在该持久化契约上实现 Step 12.2 真实 LLM 单节点执行。

#### Step 12.2：真实 LLM 单节点执行（completed）

- 执行入口：`POST /api/workflow-drafts/{workflow_id}/nodes/{node_id}/runs` 只从已保存草稿读取 LLM 节点和全局变量，不接受客户端另外传入的模型、Prompt 或凭据，避免“页面配置”与“实际执行”两套事实。
- 变量解析：用户提示词支持已确认的 `${变量名}`；字符串原样替换，其他 JSON 值序列化后替换。缺失变量、变量重名或解析后空 Prompt 都在请求供应商前失败，并持久化 `FAILED` 记录。
- 真实请求：后端按 `providerId / modelName` 从本机模型管理获取 BASE_URL 和 API Key，系统提示词非空时才加入 messages，用户提示词必须存在，`modelParameters` 继续可覆盖任意 Body 字段。
- 响应解析：新增 OpenAI-compatible 非流式 JSON 与缓冲 SSE `data:` 响应解析，支持合并 `content / reasoning_content`、usage 和 finish reason；没有任何隐式 `max_tokens / max_completion_tokens`。
- 真实日志：运行开始即写入 `RUNNING`，最终更新为 `PASSED / FAILED`；记录变量解析、模型请求、HTTP 结果和输出事件，并保存输入快照、无密钥请求 Body、完整输出、usage、request ID 或结构化错误/堆栈。
- 密钥保护：响应错误、异常和 traceback 写入前执行已知 API Key 值与 Bearer 字段脱敏；节点请求和 API 返回均不包含 Authorization。
- Stub 验证：`uv run pytest tests/test_model_gateway.py tests/test_llm_node_runs.py tests/test_llm_node_runs_live.py tests/test_workflow_drafts.py -m 'not live' -q` 结果 `14 passed, 2 deselected, 1 warning in 1.64s`；覆盖真实本地 HTTP、空系统提示词/空高级参数、变量替换、usage/request ID、缺变量零上游请求、HTTP 429、密钥脱敏和 SSE 合并。
- 真实模型验证：使用用户提供的千问 `qwen3.7-max` 和 DeepSeek `deepseek-v4-pro` 凭据仅在 pytest 进程内执行新节点 API，结果 `2 passed, 1 warning in 12.81s`。两家均以空系统提示词、`${agent_answer}` 真实业务变量和无 token 上限完成企业 Agent 合规评测，返回正确结构化结果并通过日志 API 完整回读。
- 静态与安全验证：Python 编译、`git diff --check` 和待提交文件真实 `sk-` 形态扫描通过，密钥文件命中数为 0。
- 依赖结论：Step 12.2 已通过，可以开始 Step 12.3 LLM 布局收敛、草稿恢复和真实日志前端。

#### Step 12.2A：统一原生请求/响应提取规则（completed，2026-07-22）

- 解析器：新增节点类型无关的受限 Python 风格路径解析器，只允许 `request / response` 根、点访问、字符串键和整数下标，不使用 `eval()`。
- 字符串兼容：双引号、单引号和无引号标识符键等价；纯整数（含负数）保持数组下标语义，带引号的数字仍是字符串字典键。
- 失败规则：未知根对象、函数调用、切片、非法键、缺失键、越界下标和不可继续访问的标量均明确失败，错误包含完整提取表达式。
- 通用性验证：`uv run pytest tests/test_workflow_variables.py -q` 结果 `17 passed`；覆盖所有四类可执行节点共用同一 `extract_output_variables` 契约。
- 依赖结论：统一解析器验证通过，下一项将 LLM 阻塞执行改为原生 `request / response`，并移除流式响应解析和流式输出变量。

#### Step 12.2B：列表条件提取（completed，2026-07-22）

- 语法：在统一路径解析器中加入安全过滤 token，支持数组元素字段、嵌套字段、数字/布尔/null/字符串比较和过滤后继续点访问。
- 唯一性：`response.data[id==3]` 必须恰好匹配一条；空结果和重复结果均持久化为执行失败，错误报告表达式和匹配数量。
- 验证：`uv run pytest tests/test_workflow_variables.py -q` 结果 `24 passed`，同时覆盖 `HTTP / LLM / AGENT / SCRIPT` 共用输出映射契约。
- 依赖结论：列表过滤规则已确认并通过验证，可以接入 LLM 原生请求/响应运行契约。

#### Step 12.2C：LLM 原生请求/响应与流式边界（completed，2026-07-22）

- 阻塞执行：变量提取上下文改为实际发送的 `request_body` 和供应商成功响应 JSON；原始响应文本仅用于日志，不再伪装成 `response.body` 包装字段。
- 流式执行：删除缓冲 SSE 的模型解析、usage/最终内容拼接和输出变量提取；运行记录的 `response_body`/`output` 均为脱敏后的完整原始 SSE，`output_variables` 为空。
- 模式强制：阻塞端点固定发送 `stream: false`，流式端点固定发送 `stream: true`，避免高级 JSON 与端点模式不一致。
- 变量面板：跳过没有输出变量的祖先节点，只保留全局变量、有输出变量的祖先和当前节点。
- 验证：`uv run pytest tests/test_workflow_variables.py tests/test_llm_node_runs.py tests/test_workflow_drafts.py tests/test_model_gateway.py -q` 结果 `43 passed, 1 warning`。
- 依赖结论：后端契约通过，可以进入前端交互收敛和真实浏览器流式回归。

#### Step 12.3A：提示词与流式开关交互（completed，2026-07-22）

- 提示词：删除用户提示词旁的变量插入按钮，用户直接输入 `${变量名}`；右上角变量查看按钮仍保留。
- 输出开关：使用单个默认关闭的 `role=switch` 控件；高级参数编辑器隐藏 `stream` 字段，切换开关是唯一输出模式入口。
- 输出变量：LLM 流式模式隐藏输出变量配置，保留草稿数据；切回阻塞模式后恢复配置，阻塞模式显示“提取表达式”字段。
- 验证：`npm run build` 成功；`uv run pytest tests/test_execution_frontend.py tests/test_workflow_variables.py tests/test_llm_node_runs.py tests/test_workflow_drafts.py -q` 结果 `46 passed, 1 warning`。
- 依赖结论：前端交互收敛通过，下一步进行真实浏览器的默认阻塞和流式端到端验证。

#### Step 12.3B：输出变量类型与过滤比较（completed，2026-07-22）

- 类型契约：所有节点输出映射统一支持大写 `AUTO / STRING / INTEGER / NUMBER / BOOLEAN / OBJECT / ARRAY`；旧映射缺省为 `AUTO`，保存时拒绝未知类型。
- 转换时机：先按 `request / response` 原生路径提取，再执行目标类型转换，最后写入运行记录和下游变量；`null` 对所有类型保持 `null`。
- 严格转换：`STRING` 使用 JSON 语义序列化非字符串值；`INTEGER / NUMBER / BOOLEAN` 拒绝不安全的隐式转换；`OBJECT / ARRAY` 接受原生对象/数组或合法 JSON 字符串；转换失败使节点 `FAILED`，错误包含变量名和目标类型。
- 过滤器：统一路径过滤增加 `< / > / <= / >= / == / != / contain`；`contain` 仅支持字符串子串，比较不自动做日期解析或跨类型强制转换；仍只允许一个条件且必须唯一命中。
- 验证：`uv run pytest tests/test_workflow_variables.py tests/test_llm_node_runs.py tests/test_workflow_drafts.py -q` 结果 `70 passed, 1 warning`。
- 依赖结论：类型转换和过滤器后端契约已通过，可以接入所有节点的输出变量编辑 UI。

#### Step 12.3C：输出变量类型编辑器（completed，2026-07-22）

- 通用布局：`HTTP / LLM / AGENT / SCRIPT` 共用输出变量行调整为“变量名｜类型｜提取表达式｜操作”，类型下拉固定提供 `AUTO / STRING / INTEGER / NUMBER / BOOLEAN / OBJECT / ARRAY`。
- 默认与兼容：新增输出变量默认 `AUTO`；旧草稿缺少 `type` 时按 `AUTO` 展示和执行，不需要数据迁移。
- 流式边界：LLM 流式模式继续隐藏整组输出变量配置并保留草稿，阻塞模式恢复后可编辑目标类型。
- 日志修复：运行中的流式记录不再显示 `undefined`，未收到数据时显示“正在接收原始响应…”，收到数据后显示原始片段摘要。
- 验证：`uv run pytest tests/test_execution_frontend.py tests/test_workflow_variables.py tests/test_llm_node_runs.py tests/test_workflow_drafts.py -q` 结果 `78 passed, 1 warning`；`npm run build` 成功生成最新 Workflow JS/CSS bundle。
- 依赖结论：前后端类型配置已通过专项验证，可以进入浏览器持久化、真实模型和全量发布回归。

#### Step 12.3D：流式输出标题与对齐（completed，2026-07-22）

- 交互文案：LLM 设置页的输出开关标题由“输出方式”统一改为“流式输出”，开关旁不再重复显示文字，仅保留可访问的 `aria-label`。
- 布局：标题显式左对齐，开关保持独立控件，避免重复文案导致的视觉拥挤；默认关闭和流式模式语义不变。
- 验证：`npm run build` 成功；`uv run pytest tests/test_execution_frontend.py -q` 结果 `8 passed, 1 warning`；`git diff --check` 通过。
- 浏览器验收：在当前持久化 Workflow 的 LLM 编辑器实测仅出现一处“流式输出”，旧“输出方式”文案计数为 0，`role=switch` 控件计数为 1；标题左对齐 CSS 已加载生效，开关语义未改变。
- 反馈修正：标题增加 `font-weight: 600`，设置 `min-height: 19px`、`display: flex` 和 `align-items: center`，与开关轨道保持同高并垂直对齐；专项前端测试更新为 `8 passed, 1 warning`，构建重新成功。
- 依赖结论：标题调整已通过专项验证，可以继续进行浏览器端到端和发布回归。

#### Step 12.3E：输出类型真实浏览器端到端（completed，2026-07-22）

- 配置：在持久化 Workflow 的 DeepSeek LLM 节点中，将 `llm_output` 设为 `STRING`，新增 `token_count | INTEGER | response.usage.total_tokens`，通过节点保存入口持久化。
- 真实执行：使用本机模型管理中的 `deepseek-v4-pro` 完成一次阻塞运行，终态 `PASSED`、耗时 `7441ms`；`llm_output` 为原生字符串，`token_count` 为 `Int64=427`，与 `usage.total_tokens=427` 完全一致。
- 日志与回读：原始响应日志长度为 `1326` 字符，未因输出提取做结构化替换；草稿 API 回读确认两行类型分别持久化为 `STRING / INTEGER`，表达式保持不变。
- 价值结论：已用真实供应商响应证明“提取 → 类型转换 → 保存变量 → 草稿恢复”的完整链路可用，而非仅依赖 Stub 或静态前端断言。

#### Step 12.3F：节点变量值复制（completed，2026-07-22）

- 使用场景：Workflow 作者查看全局、祖先和当前节点变量时，可直接复制完整变量值用于参数填写、提取表达式调试或与原始日志核对。
- 交互：变量面板改为“变量名｜变量值｜操作”三列；每条有值变量提供独立复制图标和变量名工具提示，尚无值时按钮禁用。
- 数据语义：字符串复制原值，对象/数组复制格式化 JSON；复制内容不受列表中的单行省略显示影响。优先使用 Clipboard API，并保留本机浏览器兼容回退；成功或失败均显示提示。
- 验证：`npm run build` 成功；`uv run pytest tests/test_execution_frontend.py -q` 结果 `8 passed, 1 warning`；`git diff --check` 通过。
- 浏览器验收：刷新最新 bundle 后，当前节点的 `llm_output / token_count` 均出现唯一复制按钮；点击 `token_count` 后页面真实显示“已复制变量 token_count”，未读取系统剪贴板内容。
- 依赖结论：变量值复制前端契约已通过，可以进入真实页面交互回归。

#### Step 12.3G：复制权限失败兼容（completed，2026-07-22）

- 问题复现：部分嵌入式浏览器会暴露 `navigator.clipboard`，但在实际点击时拒绝写入权限；原逻辑在该情况下直接失败，未尝试兼容路径。
- 修复：Clipboard API 写入失败后自动降级到聚焦隐藏文本框、选中完整内容并执行 `document.execCommand('copy')`；资源版本号递增，确保浏览器加载最新 bundle。
- 验证：`npm run build` 成功；`uv run pytest tests/test_execution_frontend.py -q` 结果 `8 passed, 1 warning`；浏览器刷新后点击 `复制变量值 token_count`，剪贴板实际读回本次运行的 `1426`，并显示“已复制变量 token_count”。
- 依赖结论：复制按钮已覆盖 Clipboard API 正常、权限拒绝降级和对象/数组格式化语义，可继续最终全量回归。

#### Step 12.3H：节点编辑器窗口与浏览器缩放（completed，2026-07-22）

- 业务目标：用户缩小节点编辑器时保留更多画布上下文，放大时提高提示词、代码和日志的可读性；浏览器整体缩放必须继续同步作用于编辑器字体。
- 窗口缩放：以节点编辑器本次打开时的尺寸为 `1.0` 基准，拖动八向缩放手柄时按宽高比例中的较小值连续缩放编辑器全部文字与控件，限制在 `0.75–1.35`，避免最小窗口不可读和最大窗口内容溢出。
- 浏览器缩放：不接管或抵消浏览器原生缩放；编辑器内部比例与浏览器缩放倍率叠加，重新打开或刷新时均以当时视口建立新的 `1.0` 基准。
- 专项验证：`npm run build` 成功；`uv run pytest tests/test_execution_frontend.py -q` 结果 `8 passed, 1 warning`。
- 浏览器 A 验收：编辑器基线 `1064x896`、标题可视高度 `18px`；放大到 `1172x1001` 后比例 `1.065`、标题高度 `19.17px`；缩小到 `952x811` 后比例 `0.865`、标题高度 `15.57px`；内容容器 `scrollWidth == clientWidth`，无横向溢出。
- 浏览器 B 验收：未对页面添加自定义浏览器缩放拦截或反向补偿；编辑器的内部缩放比例只由 Rnd 八向拖拽回调改变，浏览器缩放由浏览器原生作用于整个编辑器，刷新时重新建立当前视口的 `1.0` 基准。桌面浏览器自动化快捷键不暴露浏览器级缩放状态，因此不宣称通过快捷键改变浏览器倍率。
- 发布处理：前端资源版本递增至 `v=26`，避免用户刷新时复用旧 bundle。
- 依赖结论：节点编辑器窗口缩放和浏览器原生缩放边界已收敛，可以进入最终全量回归与发布。

#### Step 12.4：真实模型、全量回归与发布（completed，2026-07-22）

- 真实模型：千问 `qwen3.7-max` 和 DeepSeek `deepseek-v4-pro` 已在 Step 12.2 的真实企业 Agent 合规评测场景通过；Step 12.3E 另以 DeepSeek 真实响应验证 `STRING / INTEGER` 提取、类型转换、日志与草稿恢复。
- 前端 E2E：已覆盖模型选择、阻塞运行、原始日志、输出类型、变量复制、流式标题以及节点编辑器窗口放大/缩小；复制验收以剪贴板真实读回值为准，不再只依赖提示消息。
- 全量回归：`uv run pytest -q` 结果 `171 passed, 6 skipped, 1 warning in 14.30s`；6 项跳过均为未在本轮进程注入 live 环境变量的真实供应商用例，warning 为既有 Starlette/httpx 弃用提示。
- 构建与静态检查：`npm run build`、`node --check web/static/assets/workflow-canvas.js`、`uv run python -m compileall -q execution web` 和 `git diff --check` 全部通过。
- 安全扫描：待提交文件 `sk-` 候选扫描排除构建产物中的 CSS 标识符后，带数字的凭据候选为 0；未把用户 API Key 写入代码、测试、文档或提交内容。
- 测试数据清理：真实 E2E 临时 Workflow `fe539097aaca4befbd2c049abe0990ef` 已通过删除 API 清理，随后 GET 返回 `404`。
- 发布结果：功能与测试改造已提交为 `8d405e9`（`Add persistent LLM workflow execution`），并成功推送到 `origin/codex/tool-template-refactor`；随后本计划收口记录单独提交并同步推送。

#### Step 13：Script 节点参数页签收敛（completed，2026-07-22）

##### 业务背景与目标（Why）

- Script 节点的“参数”页签当前只展示只读的 `parameterRecords` 快照，不负责配置脚本输入；在真实编辑场景中通常为空，并与变量面板、日志详情形成重复入口。
- 本步骤目标是让 Workflow 作者在 Script 节点内按实际工作流完成三件事：在“代码”页编写脚本，在右上角变量面板核对可引用值，在“设置 → 输出变量”声明下游变量；执行结果和错误统一进入“日志”。

##### 用户与真实场景（Who / Where）

- 用户：编排评测 Workflow 的业务或测试工程师。
- 场景：用户双击 Script 节点修改 `main.py`，需要查看上游输出并确认脚本结果；此时参数快照既不能编辑输入，也不能替代日志和变量面板。

##### 需求范围与优先级（What / When）

- 高优先级、前端交互收敛：Script 编辑器只保留“设置 / 代码 / 日志”三页。
- “设置”继续保留名称、说明、运行配置和输出变量；“代码”继续保留 `main.py`；“日志”继续保留运行状态、结果和错误。
- 右上角变量面板继续作为 Script 调试输入的唯一查看入口；不新增一套参数映射 UI。
- 共享 `parameterRecords` 数据结构暂不删除，因为 HTTP / AGENT 仍使用参数查看能力；本步骤不改后端运行协议、不改变历史草稿读取。
- 已确认 `1A 2A`：本步骤同时为 `HTTP / AGENT / LLM / SCRIPT` 接入真实执行；日志按“原始请求 / 原始 stdout / 原始 response / 原始 stderr 与 traceback”分区展示，但不改写原始文本；输出变量只能依据原始 `request / response` 结构提取。

##### 可独立验证子任务

| 子任务 | 目标 | 输入/输出 | 验证方法 | 依赖 |
|---|---|---|---|---|
| 13.1 | 原始日志持久化 | Worker stdout/stderr；运行记录新增原始流字段 | Worker 流归属、SQLite 重启回读、10 条保留 | 无 |
| 13.2 | 四类真实执行 | HTTP 配置、AGENT/SCRIPT `main.py`、LLM 网关 | 四类成功/失败、request/response 提取、无密钥日志 | 13.1 |
| 13.3 | 统一日志 UI | 四类运行记录 | 浏览器展开原始四区、错误定位、节点状态 | 13.2 |
| 13.4 | 集成发布 | 完整 Workflow Studio | 全量 pytest、构建、真实浏览器、推送 | 13.1-13.3 |

##### 验收标准与价值验证（How to Measure）

- Script 节点编辑器不显示“参数”按钮，且节点切换或旧状态恢复时不会渲染参数面板。
- Script 的“设置 / 代码 / 日志”、变量按钮和输出变量配置均可正常使用；HTTP / AGENT 的参数页签保持不变。
- `npm run build`、专项前端测试和真实浏览器双击 Script 流程通过，桌面布局无重叠或横向溢出。
- 实现进度：已加入 `isScript / showParametersTab` 路由判定；切换节点时重置到 `initialTab`，避免从 HTTP/AGENT 参数页切换到 Script 后残留隐藏面板。`npm run build` 成功，`uv run pytest tests/test_execution_frontend.py -q` 为 `8 passed, 1 warning`，`node --check web/static/assets/workflow-canvas.js` 通过。
- 13.1 已完成：`WorkflowNodeRunRecord` 增加 `stdout/stderr`，SQLite 自动迁移 `stdout_body/stderr_body`；Worker 事件携带原始流来源并分别收集。`uv run pytest tests/test_tool_execution.py tests/test_workflow_drafts.py -q` 为 `15 passed, 1 warning`，Python 编译通过。
- 13.2 已完成：HTTP 使用真实请求配置进入 Worker，AGENT/SCRIPT 使用真实 `main.py` 子进程；四类节点统一按 `request / response` 提取输出变量。成功/失败均保存原始 stdout、stderr、response 和 traceback，HTTP 非 2xx 保留原始响应。专项 `uv run pytest tests/test_workflow_node_runs.py -q` 为 `5 passed, 1 warning`，与既有 LLM/Worker/草稿专项合计 `24 passed, 1 warning`。
- 13.3 已完成：四类节点共用可展开运行历史，摘要显示日期、状态、耗时和最终结果；详情按原始请求、stdout、response、stderr、traceback 分区展示，空区不伪造内容，保留原始文本。运行入口与日志加载扩展到 HTTP/AGENT/LLM/SCRIPT。`npm run build`、`node --check web/static/assets/workflow-canvas.js` 和 `uv run pytest tests/test_execution_frontend.py -q`（`8 passed, 1 warning`）通过；节点执行专项现为 `6 passed, 1 warning`。
- 13.4 已完成：浏览器真实 Script 成功运行以 `212ms` 进入 `PASSED`，展开日志显示原始 request/stdout/response/stderr，并提取 `browser_value=浏览器回归`；失败运行以 `222ms` 进入 `FAILED`，保留执行前 stdout、用户 stderr、Worker traceback 和路由 traceback。全量回归 `177 passed, 6 skipped, 1 warning in 16.92s`，构建、Python/JS 静态检查和 `git diff --check` 通过；临时 Workflow 删除后 GET 为 `404`。
- 13.5 发布完成：提交 `7f15ac9`（`Add real workflow node execution logs`）已推送到 `origin/codex/tool-template-refactor`。

#### Step 14：Workflow 与节点中断控制（completed，2026-07-22）

##### 业务背景与目标（Why）

- 当前画布运行会按定时器触发节点，运行按钮可重复点击，后端节点请求没有可由画布调用的统一取消协议；长耗时测试容易重复消耗资源，也无法在发现配置错误后及时停止。
- 目标是在画布级和节点级提供一致的运行锁、中断入口、耗时计时与可重新运行能力，同时保证中断后的执行范围可预测。

##### 已确认需求（What）

- 画布运行期间禁用重复运行；运行按钮左侧显示累计计时器；顶部“全局变量”右侧和画布右键菜单均提供中断入口；中断后可重新从头运行。
- 节点运行期间禁用该节点所有运行入口；节点卡片、节点右键菜单和编辑器标题栏均提供中断入口；未运行或已结束节点点击中断不改变状态；中断后可重新运行节点。
- 节点中断后，本次 Workflow 中该节点的后续节点不再执行；四类节点的原始日志和错误追溯规则继续适用。

##### 实现前必须确认

- 中断节点在既定四状态中显示 `FAILED` 还是恢复 `PENDING`。
- 在分支 Workflow 中，“后续节点”是仅指被中断节点的图后代，还是停止本次 Workflow 的所有剩余节点。
- 当前按横坐标定时触发的画布演示调度是否在本步骤升级为依据连线的真实 DAG 调度。
- 用户已确认：`PASSED` 全局更名为 `SUCCESS`，最终状态集合为 `PENDING / RUNNING / SUCCESS / FAILED / INTERRUPTED`；执行失败与用户中断严格区分；节点级中断仅停止当前节点及其图后代，独立分支继续；调度采用 `3B` 真实 DAG，依赖满足后独立分支并行。任一节点 `FAILED` 或 `INTERRUPTED` 后，其图后代在本次运行中保持未执行。

##### Step 14 可独立验证子任务

| 子任务 | 目标 | 输入/输出 | 验证方法 | 依赖 |
|---|---|---|---|---|
| 14.1 | 后端节点取消协议 | 活动运行注册、Worker/LLM 取消、`INTERRUPTED` 记录 | 重复运行拒绝、运行中中断、终态中断无副作用、日志回读 | 无 |
| 14.2 | 并行 DAG 调度 | 节点/边、SUCCESS/FAILED/INTERRUPTED | 独立分支并行、后代阻断、失败分支不影响独立分支 | 14.1 |
| 14.3 | 画布级控制 | 运行锁、计时器、顶部/右键中断 | 连续点击禁用、中断全部活动节点、重新从头运行 | 14.1-14.2 |
| 14.4 | 节点级控制 | 卡片/右键/编辑器运行与中断 | 运行锁、三处中断一致、后代不执行、节点可重跑 | 14.1-14.3 |
| 14.5 | 集成发布 | 完整 Workflow Studio | 专项/全量 pytest、构建、真实浏览器 E2E、推送 | 14.1-14.4 |

##### 14.1 后端节点取消协议（completed，2026-07-22）

- 状态契约：`WorkflowNodeRunStatus` 统一提供 `PENDING / RUNNING / SUCCESS / FAILED / INTERRUPTED`；SQLite 初始化会把历史 `PASSED` 行迁移为 `SUCCESS`，内部查询命名同步为 `latest_success_run`。
- 活动运行：节点运行按 `(workflow_id, node_id)` 注册；同一节点已有活动运行时返回 HTTP `409`。活动 Worker 保存 `run_id`，中断接口终止 Worker 进程树；LLM 非流式任务取消当前 asyncio 任务。
- 流式 LLM：响应生成器开始时绑定实际任务，支持中断前置竞态、运行中 `CancelledError` 和客户端断开后的清理；已接收的原始 chunk 保存到 `response_body`，最终记录为 `INTERRUPTED` 并保留 `INTERRUPTED` 错误事件。
- API：新增 `POST /api/workflow-drafts/{workflow_id}/nodes/{node_id}/interrupt`；未运行、已完成或已中断节点返回 `{"interrupted": false}`，不创建额外运行记录。
- 验证：`uv run pytest tests/test_workflow_node_runs.py::test_script_node_can_be_interrupted_and_rejects_duplicate_runs -q` 通过；`uv run pytest tests/test_llm_node_runs.py::test_llm_stream_can_be_interrupted_and_persists_partial_raw_response -q` 通过；两项均覆盖重复启动、运行中断、日志回读和中断后重跑/部分原始响应。现有 Workflow/LLM/节点专项合计 `23 passed, 1 warning`；Python 编译通过。
- 依赖结论：后端节点级取消协议已具备稳定终态和清理语义，可以进入真实 DAG 调度实现；此前业务数据提取测试中的字符串 `PASSED` 保持原样，不属于运行状态。

##### 14.2 并行 DAG 调度（completed，2026-07-22）

- 调度规则：运行入口依据 Workflow 连线构建前驱表；无前驱节点同时进入就绪队列，独立分支通过 `Promise.race` 并行推进；只有节点返回 `SUCCESS` 才会解锁后继节点。
- 失败隔离：节点返回 `FAILED` 或 `INTERRUPTED` 时，仅将其图后代标记为本次未执行并保持 UI `PENDING`；没有依赖关系的分支继续执行。Workflow 级中断会设置全局中断标记，停止活动节点且不再启动剩余节点。
- 运行锁：Workflow 活动期间 `运行` 按钮禁用；同一节点通过 ref 活动表避免重复调用，节点运行结束或中断后可再次启动。节点卡片、右键菜单和编辑器标题栏共享同一中断回调。
- 控件：画布运行按钮左侧显示累计耗时；“全局变量”右侧新增画布中断按钮；画布右键新增“中断测试”；节点卡片保留运行并新增中断，节点右键新增“中断此步骤”，编辑器标题栏同步提供运行/中断锁定状态。
- 状态：前端统一展示 `PENDING / RUNNING / SUCCESS / FAILED / INTERRUPTED`，节点运行历史摘要对 `INTERRUPTED` 显示中断错误而非伪造成功结果。
- 验证：`npm run build`、`node --check web/static/assets/workflow-canvas.js`、`git diff --check` 通过；资源版本断言同步为 `v=28` 后，`uv run pytest tests/test_execution_frontend.py tests/test_workflow_node_runs.py tests/test_llm_node_runs.py tests/test_workflow_drafts.py -q` 结果为 `31 passed, 1 warning`，覆盖前端契约、Script/HTTP/LLM 执行和取消协议。

##### 14.3 画布级控制（completed，2026-07-22）

- 真实浏览器运行锁：临时 Workflow 进入运行后，顶部运行按钮禁用、中断按钮启用，累计计时器从 `810ms` 持续增长；活动 Script 节点同步显示 `RUNNING` 并禁用节点运行入口。
- 顶部中断：点击顶部中断后，活动 Script 进入 `INTERRUPTED`，Workflow 提示“Workflow 已中断”，运行按钮重新启用且中断按钮禁用；本次计时器冻结在 `10.0s`。
- 重新运行：中断后再次点击顶部运行，Script 重新进入 `RUNNING`，证明 Workflow 可从头启动新一轮执行；随后再次中断，终态仍稳定为 `INTERRUPTED`。
- 右键中断：运行期间在画布空白区打开右键菜单，确认“中断测试”存在并可实际终止活动 Script；菜单关闭后节点保持 `INTERRUPTED`，未继续启动剩余节点。
- 依赖结论：画布运行锁、累计计时、两处中断入口和中断后重跑已通过真实浏览器验收，可以进入节点三入口验收。

##### 14.4 节点级控制（completed，2026-07-22）

- 编辑器入口：30 秒 Script 运行时，编辑器运行按钮禁用、中断按钮启用，卡片耗时从 `0ms` 累加；点击编辑器中断后节点进入 `INTERRUPTED`，运行按钮恢复且中断按钮禁用。
- 卡片入口：卡片运行后同样禁用重复运行并启用中断；点击卡片中断后状态为 `INTERRUPTED`，运行入口重新可用。
- 右键入口：节点右键菜单显示“中断此步骤”，运行期间点击后真实终止 Worker，菜单关闭且节点进入 `INTERRUPTED`。
- 原始日志：最近一次中断记录摘要显示 `07-22 03:28:23 / INTERRUPTED / 23.6s / 用户中断节点`；展开后保留原始 request 和原始 stdout `browser interrupt`，没有因中断丢弃运行前已输出内容。
- 成功状态：同一节点此前完整运行记录在卡片和日志中均显示 `SUCCESS`，不再显示 `PASSED`。
- 依赖结论：节点卡片、右键菜单和编辑器三处运行锁/中断语义一致，且中断日志满足原始输出铁律，可以进入集成发布回归。

##### 14.5 集成发布（completed，2026-07-22）

- 状态契约：源码、前端构建产物、测试和项目说明统一使用 `PENDING / RUNNING / SUCCESS / FAILED / INTERRUPTED`；历史 SQLite `PASSED` 自动迁移并有专项测试覆盖。
- 调度与中断：后端阻塞/流式节点取消、同节点 `409` 运行锁、前端真实 DAG 并行、失败/中断后代阻断、画布和节点全部中断入口均完成。
- 浏览器回归：覆盖编辑器、卡片、节点右键、画布顶部和画布右键五类入口；验证运行禁用、累计计时、原始 stdout 保留、中断终态和重新运行。
- 最终回归并入 Step 15.3：全量 `185 passed, 6 skipped, 1 warning`，构建、JS/Python 静态检查和差异检查均通过。

#### Step 15：禁止游离节点（completed，2026-07-22）

##### 业务背景与目标（Why）

- Workflow 保存后会被真实 DAG 调度执行；若节点不在完整执行链上，用户容易误以为该节点会参与测试，实际却永远不会启动或无法汇入结束节点。
- 目标是在不妨碍拖拽编辑的前提下，确保每个可执行节点都属于完整的 `START → ... → END` 有向路径。

##### 用户与真实场景（Who / Where）

- 用户：在 Workflow Studio 编排企业 Agent 测试流程的业务或测试工程师。
- 场景：用户可以在编辑过程中临时断开节点；只有点击保存或运行时才需要得到明确错误，并定位所有不可从 START 到达或无法到达 END 的节点。

##### 已确认范围与优先级（What / When）

- 采用严格规则 `1A`：每个业务节点必须同时满足“可从 START 到达”和“可以到达 END”；完全无边、只有入边、只有出边、断裂分支均属于游离节点。
- 采用双层校验 `2A`：前端保存/运行立即拦截，后端草稿保存和节点运行接口同步拒绝，避免绕过页面。
- 仅在保存和执行时检测；拖拽、连线和删除过程不实时打断编辑。

##### 可独立验证子任务

| 子任务 | 目标 | 输入/输出 | 验证方法 | 依赖 |
|---|---|---|---|---|
| 15.1 | 后端图完整性校验 | nodes/edges；结构化错误 | 合法 DAG、无边、不可达、死路、API 保存/运行拒绝 | 无 |
| 15.2 | 前端保存/运行拦截 | 当前 React Flow 图；节点名称提示 | 前端专项断言与构建 | 15.1 |
| 15.3 | 端到端回归与发布 | Workflow Studio 完整流程 | 真实浏览器、专项/全量测试、构建、推送 | 15.1-15.2 |

##### 验收标准与价值验证（How to Measure）

- 合法分支 DAG 可以保存和运行；任一业务节点不在完整 `START → END` 路径上时，保存和运行均失败。
- 错误提示包含游离节点名称，用户无需逐条排查连线。
- 直接调用后端 API 不能绕过规则；历史草稿仍可读取和编辑，在重新保存或运行时才触发校验。
- 节点中断、`SUCCESS` 状态、原始日志和现有变量提取能力不受影响。

##### 15.1 后端图完整性校验（completed，2026-07-22）

- 共享规则：新增保存/执行时图校验；要求且仅允许一个 `START` 和一个 `END`，并通过正向可达集与反向可达集的交集判断每个节点是否处于完整 `START → END` 路径。
- 错误定位：无边、从 START 不可达、无法到达 END 和断裂分支均返回 HTTP `422`，错误包含全部游离节点名称或 ID。
- 历史兼容：规则不放入草稿 Pydantic 读取模型；历史无效草稿仍可 GET 和编辑，但 PUT 保存或节点执行时被拒绝。
- 防绕过：草稿 POST/PUT、阻塞节点运行和流式 LLM 运行均调用同一后端校验；活动运行先原子注册，再校验并在失败时清理，保持重复运行 `409` 语义。
- 测试夹具：Script/Agent/HTTP/LLM 执行用例统一升级为 `START → 业务节点 → END`，下游 LLM 用例升级为完整串行路径。
- 验证：`uv run pytest tests/test_workflow_drafts.py tests/test_workflow_node_runs.py tests/test_llm_node_runs.py -q` 结果 `28 passed, 1 warning`；覆盖合法并行 DAG、无边、不可达、死路、更新绕过、历史草稿执行绕过、重复启动、中断及原始流日志。
- 依赖结论：后端保存和执行边界已收敛，可以接入前端保存/运行即时提示。

##### 15.2 前端保存/运行拦截（completed，2026-07-22）

- 前端规则：React Flow 当前节点/边通过与后端一致的正向、反向可达性算法校验；缺少唯一 START/END 或存在不在完整路径上的节点时返回明确错误。
- 触发时机：`persistDraft`、节点运行和画布运行三个入口调用校验；拖拽、连线、删除、复制和粘贴过程中不执行校验，允许用户临时断开图。
- 交互结果：保存失败状态显示为“保存失败”，Toast 列出游离节点名称；运行不会启动计时器、不会把节点改成 `RUNNING`，也不会向后端发送执行请求。
- 构建发布：`npm run build` 成功生成最新 JS/CSS bundle，首页资源版本递增为 `v=29`。
- 验证：`node --check web/static/assets/workflow-canvas.js`、`git diff --check` 通过；`uv run pytest tests/test_execution_frontend.py -q` 结果 `8 passed, 1 warning`。
- 依赖结论：前后端规则一致，可以进入真实浏览器的无边、死路、合法路径保存/运行验收。

##### 15.3 端到端回归与发布（completed，2026-07-22）

- 浏览器无边场景：删除默认 HTTP 中间节点后点击保存，页面显示 `Workflow 存在游离节点: 开始, 执行企业 Agent, 模型质量判断, 规则校验, 完成`，状态变为“保存失败”；点击运行不会启动 Workflow 计时器、不会出现 `RUNNING`。
- 浏览器合法场景：撤销删除恢复 `START → HTTP → AGENT → (LLM/SCRIPT) → END` 完整路径后保存成功并显示“Workflow 草稿已保存”。
- 后端死路/不可达：专项覆盖无边、只有入边、只有出边和完整并行分支；直接 POST/PUT/节点运行 API 均按规则返回 `422` 或正常接受合法图。
- 回归结果：全量 `uv run pytest -q` 为 `185 passed, 6 skipped, 1 warning in 18.60s`；专项草稿/节点/LLM/前端为 `37 passed, 1 warning`。
- 构建检查：`npm run build`、`node --check web/static/assets/workflow-canvas.js`、`uv run python -m compileall -q execution web tests`、`git diff --check` 全部通过。
- 状态契约：运行状态对外统一为 `PENDING / RUNNING / SUCCESS / FAILED / INTERRUPTED`；SQLite 历史 `PASSED` 仅作为一次性迁移输入，普通响应字段中的同名业务值保持原样。
- 安全：代码、测试、文档和构建产物未发现用户 API Key 候选；浏览器临时 Workflow 已删除，API 列表回到 0 条。

##### 15.4 单节点调试与完整图校验解耦（completed，2026-07-22）

- 业务修正：节点卡片和节点编辑器右上角的运行按钮只运行当前节点，不依赖 `START / END`，也不要求当前 Workflow 已形成完整路径。
- 保存边界：显式保存节点或 Workflow、以及画布级运行仍执行完整 `START → END` 校验；单节点运行只创建/更新内部运行快照，不把界面标记为“已保存”，不清除未保存状态。
- 后端边界：草稿 POST/PUT 仅在 `for_node_run=true` 的内部运行快照请求中允许不完整图；节点阻塞/流式运行接口不再校验整张图，但继续校验当前节点的模型、提示词、参数或代码。
- 验证：`uv run pytest tests/test_workflow_drafts.py tests/test_workflow_node_runs.py tests/test_llm_node_runs.py tests/test_execution_frontend.py -q` 结果 `37 passed, 1 warning`；覆盖显式保存拒绝、不完整图快照允许和单节点自身配置失败。
- 浏览器验收：使用仅含一个 LLM、完全没有 `START / END` 的临时 Workflow，选择 DeepSeek 并填写提示词后从编辑器右上角启动；节点立即进入 `RUNNING`，运行按钮禁用、中断按钮启用，最终在 `15.5s` 进入 `SUCCESS`。临时 Workflow 随后删除。
- 发布回归：前端资源升级为 `v=30`；全量 `uv run pytest -q` 结果 `185 passed, 6 skipped, 1 warning in 18.53s`，JS/Python 静态检查和 `git diff --check` 通过。

#### Step 16：弱化 START/END 并完善画布图编辑（completed，2026-07-22）

##### 业务背景与目标（Why）

- 当前 START/END 只承担装饰性连线作用，却被错误地作为 Workflow 保存和运行的硬性前置条件；这会让单节点和多入口/多出口 DAG 增加无意义的配置成本。
- 目标是让调度器根据真实连线自动识别起点和终点，同时保留用户在需要时手工添加 START/END 的能力，并让连线删除、游离提示可见且可操作。

##### 用户与真实场景（Who / Where）

- 用户：在 Workflow Studio 中快速验证单节点、编排并行分支和维护已有流程的测试工程师。
- 场景：用户可以直接运行一个孤立的当前节点；画布运行前需要知道哪些节点未接入图；编辑连线时需要点击选中后用 Delete/Backspace 或右键删除。

##### 已确认范围与优先级（What / When）

- 不再强制要求 START/END；入度为 0 的节点自动作为执行起点，出度为 0 的节点自动作为终点。
- 右键画布可添加 `START` 和 `END`，系统节点与业务节点均可按需使用。
- 连线支持选中高亮、Delete/Backspace 删除和右键菜单删除。
- 保存或运行检测到游离节点时必须显示明确提示，不能静默阻止。

##### 可独立验证子任务

| 子任务 | 目标 | 输入/输出 | 验证方法 | 依赖 |
|---|---|---|---|---|
| 16.1 | 新图规则与提示 | 可选 START/END、游离节点错误 | 后端/前端合法单节点、并行 DAG、孤立节点、保存/运行错误 | 无 |
| 16.2 | 连线编辑交互 | 选中/高亮/删除/右键删除 | 浏览器点击连线、键盘删除、右键删除 | 16.1 |
| 16.3 | 系统节点添加 | 画布右键 START/END | 浏览器菜单添加并持久化 | 16.1 |
| 16.4 | 集成回归与发布 | Workflow Studio 完整流程 | 全量测试、构建、真实浏览器、推送 | 16.1-16.3 |

##### 验收标准与价值验证（How to Measure）

- 单节点和不含 START/END 的合法 DAG 可以保存和运行。
- 完全无连线的业务节点被识别为游离节点；保存和运行均显示包含节点名称的提示。
- 连线点击后有选中高亮；Delete、Backspace 和右键“删除”均能移除连线并更新图。
- 画布右键菜单可添加 START/END，新增节点可继续连线、保存和参与 DAG 调度。

##### 16.1 新图规则与提示（completed，2026-07-22）

- START/END 可选：后端和前端均不再要求 START/END 存在或唯一；调度器继续把所有入度为 0 的节点视为起点，把所有出度为 0 的节点视为终点。
- 新建默认图：删除装饰性 START/END，只保留 `HTTP → AGENT → (LLM / SCRIPT)` 业务节点和真实依赖。
- 游离定义：单节点 Workflow 合法；多节点时，入度与出度总和均为 0 的节点视为游离。多个彼此独立但内部有连线的分支可并行存在。
- DAG 安全：前后端增加 Kahn 拓扑检测，发现循环依赖时显示涉及节点并拒绝保存/画布运行。
- 可见提示：全局 Toast 层级从 `1000` 提升到 `3000`，高于全屏 Workflow Studio 的 `2000`，保存和运行错误不再被画布遮挡。
- 验证：`uv run pytest tests/test_workflow_drafts.py tests/test_execution_frontend.py tests/test_workflow_node_runs.py tests/test_llm_node_runs.py -q` 结果 `37 passed, 1 warning`；覆盖单节点、并行 DAG、游离节点、循环依赖、单节点调试和现有中断协议。
- 依赖结论：图规则与提示边界已通过，可以进入连线选中/删除和系统节点菜单的真实浏览器验收。

##### 16.2 连线编辑交互（completed，2026-07-22）

- 选中高亮：连线点击后独占选中，节点选择被清空；真实浏览器计算样式从中性灰 `rgb(154, 168, 186) / 1.7px` 变为蓝色 `rgb(36, 87, 214) / 2px`。
- 键盘删除：Workflow Studio 在连线点击时主动获得焦点；Delete/Backspace 同时支持选中节点和选中连线。浏览器实测 Delete 后连线数从 3 降到 2。
- 右键删除：新增 `onEdgeContextMenu` 和独立 `edge-context-menu`，右键连线会选中该线并显示“删除连线”；删除共用统一历史记录逻辑，支持 Ctrl+Z 恢复。
- 依赖结论：连线已具备可见选中、键盘删除和右键删除三条完整交互路径，可以进入系统节点菜单验收。

##### 16.3 系统节点添加与可见错误（completed，2026-07-22）

- 画布菜单：右键空白区展开“添加节点”后显示 `开始 START / 结束 END / HTTP / AGENT / LLM / SCRIPT`；Edge `+` 插入仍只提供四种业务节点，避免把 START/END 插入流程中段。
- 浏览器添加：分别点击 START 和 END 菜单项后，对应系统节点真实出现在画布；节点继续使用既有单向 Handle 规则。
- 游离提示：删除默认 AGENT 后，保存和画布运行均显示 `Workflow 存在游离节点`；运行未启动计时器。Toast 的 `z-index: 3000` 确保提示位于全屏画布和编辑器之上。
- 无系统节点保存：默认 `HTTP → AGENT → (LLM / SCRIPT)` 图不含 START/END，浏览器实测保存成功；临时 Workflow 删除后 API 仅保留用户原有数据。
- 依赖结论：系统节点可选入口、游离提示和无 START/END 保存均已通过真实浏览器验收，可以进入全量集成回归。

##### 16.4 集成回归与发布（completed，2026-07-22）

- 专项回归：Workflow 草稿、前端契约、四类节点运行、LLM 阻塞/流式和中断专项合计 `37 passed, 1 warning`。
- 全量回归：`uv run pytest -q` 结果 `185 passed, 6 skipped, 1 warning in 17.93s`；6 项跳过仍是未向本轮进程注入真实供应商环境变量的 live 用例。
- 构建检查：`npm run build`、`node --check web/static/assets/workflow-canvas.js`、`uv run python -m compileall -q execution web tests` 和 `git diff --check` 全部通过。
- 发布资源：Workflow JS/CSS 资源版本升级为 `v=31`；`AGENTS.md` 同步记录 START/END 可选、隐式起止、连线编辑、游离/循环校验和单节点运行边界。
- 测试数据：浏览器 E2E 创建的无 START/END 临时 Workflow 已删除，API 仅保留用户原有 Workflow。

### Step 17：Anthropic 原生协议与内网模型连接（in progress，2026-07-22）

#### 业务背景与目标（Why）

- 模型管理虽可识别 `ANTHROPIC`，但 Workflow LLM 节点只实现了 OpenAI-compatible 请求，导致已保存的 Anthropic 模型无法执行。
- 企业内网模型网关常使用私有 IP、自签名证书，并且不应经过公司 VPN 注入的系统代理；目标是在不降低公网连接安全性的前提下打通这类本机调试场景。

#### 用户与真实场景（Who / Where）

- 企业测试工程师在本机模型管理中配置 OpenAI-compatible 或 Anthropic 供应商，再从 Workflow LLM 节点选择模型进行阻塞或流式验证。
- Step 18 已取代早期内网 IP 自动直连策略：BASE_URL 地址类型不再改变路由，用户必须显式选择 SYSTEM、DIRECT 或 CUSTOM；TLS 证书校验继续与代理模式独立。

#### 已确认范围与优先级（What / When）

- P0：模型管理明确支持 `OPENAI_COMPATIBLE / ANTHROPIC` 两种可执行协议，手工添加模型不再等价于不可执行的 `MANUAL` 协议。
- P0：实现 `build_anthropic_request / invoke_anthropic / parse_anthropic_response`，覆盖 Anthropic 原生阻塞与流式节点路径。
- P0：HTTPX 客户端参数只由显式代理模式和 TLS 开关决定，不再包含地址类型启发式。
- 代理采用已确认的 `1A` 及 Step 18 最终细化：前端下拉、API、数据库与运行时统一使用 `SYSTEM / DIRECT / CUSTOM`。SYSTEM 继承环境变量；DIRECT 设置 `trust_env=False`；CUSTOM 始终使用保存的 HTTP(S)/SOCKS URL及可选认证。正向 `verify_ssl` 默认 `true`，关闭后统一设置 `verify=False`。
- 模型齿轮采用已确认的 `2A`：保存上下文窗口、最大输出 Token 能力和默认 Body JSON；前两项只作为模型元数据，不伪造跨厂商请求字段。
- 参数采用已确认的 `3A`：平台基础请求 < 模型默认 Body < LLM 节点高级参数，后层递归覆盖前层；数组和标量整体替换。
- 每个已添加模型在齿轮旁提供独立测试按钮；测试使用页面当前连接配置、代理和该模型默认 Body 发起真实阻塞推理，不打开弹窗，只在模型行标记可用/不可用并通过轻量提示反馈 HTTP 状态与延迟；不持久化为 Workflow 节点日志，也不隐式保存供应商。
- Anthropic Messages API 强制要求 `max_tokens`；节点未显式设置时使用 `8192` 作为协议必需兼容值，用户 `modelParameters.max_tokens` 优先覆盖。OpenAI-compatible 仍不注入 token 上限。

#### 可独立验证子任务

| 子任务 | 目标 | 输入/输出 | 验证方法 | 依赖 |
|---|---|---|---|---|
| 17.1 | 协议与内网传输内核 | 两类请求/响应和 URL；httpx 参数 | MockTransport、URL/请求/响应、内外网参数单测 | 无 |
| 17.2 | 模型管理接入 | 显式协议；测速和模型发现 | API、前端契约、本地 HTTP 服务 | 17.1 |
| 17.3 | Workflow LLM 接入 | Anthropic 阻塞/流式原始日志 | 本地 Anthropic 网关节点 E2E、中断与变量提取 | 17.1-17.2 |
| 17.4 | 集成回归与发布 | 完整业务流程和文档 | 专项/全量测试、构建、静态检查、浏览器 E2E、GitHub 推送 | 17.1-17.3 |

##### 17.1 协议与内网传输内核（completed，2026-07-22）

- 新增 Anthropic 原生请求构建、`/v1/messages` URL、`x-api-key / anthropic-version` Header、HTTP 调用和非流式响应解析；文本块按原顺序合并，usage 与 stop reason 保持原生语义。
- Anthropic 基础请求仅因原生协议强制要求而默认加入 `max_tokens: 8192`，模型默认参数和节点高级参数仍可递归覆盖全部字段；OpenAI-compatible 的无默认 token 上限契约未改变。
- Step 18 已删除共享内网 IP 判断；此阶段新增的 Anthropic 请求、代理参数构建和证书验证能力继续复用同一 HTTPX 传输内核。
- 验证：`uv run pytest tests/test_model_gateway.py -q` 结果 `8 passed`；覆盖内外网判定、三类 Anthropic BASE_URL、Body 深度合并、专有 Header、原生响应文本/usage/stop reason 和既有 OpenAI 流式解析。
- 依赖结论：共享协议内核可供模型管理和 Workflow 执行复用；模型级代理模式、默认 Body 和上下文元数据仍需按最新需求确认后进入 17.2。

##### 17.2 模型管理接入（completed，2026-07-22）

- 所有新增设置严格收口在“模型管理 → 供应商详情”：协议、代理模式、自定义代理认证、SSL 证书验证、模型默认 Body、上下文元数据、最大输出能力和单模型测试均不进入画布配置。
- 协议在界面对用户统一显示为 `OpenAI / Anthropic`；持久化仍使用稳定的 `OPENAI_COMPATIBLE / ANTHROPIC` 标识。供应商列表、详情摘要和模型行均使用用户可见名称。
- 每个模型的齿轮弹窗可保存 `context_window / max_output_tokens / default_body`；前两项仅是能力元数据，默认 Body 在执行时位于平台基础请求与节点高级参数之间。
- 每个模型的测试按钮使用详情页当前连接、协议、代理和默认 Body 发起真实阻塞请求；测试不打开结果弹窗，模型行按钮直接标记可用/不可用，轻量提示反馈 HTTP 状态与延迟，且不隐式保存供应商。
- 专项验证：`uv run pytest tests/test_model_gateway.py tests/test_model_providers.py tests/test_model_providers_frontend.py -q` 结果 `33 passed, 1 warning`；`node --check web/static/model-providers.js` 通过。
- 浏览器 E2E：DeepSeek `deepseek-v4-pro` 真实单模型请求已验证返回 HTTP 200；详情页确认 `OpenAI / Anthropic`、三种代理模式、测试与齿轮按钮均在模型管理内，未点击保存且未修改用户数据。测试反馈已按最新要求改为无弹窗行内状态，待 17.4 最终浏览器回归复核。

##### 17.3 Workflow LLM 接入（completed，2026-07-22）

- Workflow 后端根据模型管理中已保存的协议选择 OpenAI-compatible 或 Anthropic 原生执行路径；画布和节点编辑 UI 未增加协议、代理、模型默认 Body、上下文或测试配置。
- Anthropic 阻塞请求使用 `/v1/messages`、`x-api-key`、`anthropic-version`，系统提示词写入顶层 `system`；响应保留原始 Body，并解析文本、usage 和 stop reason 供日志与输出变量使用。
- OpenAI 与 Anthropic 均按“平台基础请求 < 模型默认 Body < 节点高级参数”递归合并；模型能力元数据 `context_window / max_output_tokens` 不会被伪装成跨厂商请求字段。
- 阻塞和流式请求统一消费供应商显式代理配置；目标 IP 类型不会覆盖用户选择。代理密码与 API Key 不进入持久化日志或错误文本。
- Anthropic 流式请求原样发送 SSE 到前端并持久化原始响应，不执行结构化解析、不提取输出变量；失败和中断继续保留已收到的真实原文与错误。
- 专项验证：`uv run pytest tests/test_llm_node_runs.py tests/test_model_gateway.py tests/test_model_providers.py tests/test_model_providers_frontend.py -q` 结果 `41 passed, 1 warning`；新增本地 Anthropic 假网关覆盖路径、Header、系统提示词、默认 Body/节点覆盖、usage、变量提取和流式原文。`node --check` 与 Python `compileall` 均通过。

##### 17.4 集成回归与发布（completed，2026-07-22）

- 构建：`npm run build` 通过，Workflow 构建产物无业务差异；模型管理使用独立静态 JS/CSS，无需修改画布资源版本。
- 全量回归：`uv run pytest -q` 结果 `202 passed, 6 skipped, 1 warning`；6 项跳过仍是未向本轮进程注入真实供应商环境变量的 live 用例，warning 为既有 Starlette/httpx 弃用提示。
- 静态检查：Python `compileall`、`node --check web/static/model-providers.js`、Workflow bundle 语法检查和 `git diff --check` 均通过。
- 浏览器 E2E：模型管理详情显示 `OpenAI / Anthropic` 与统一代理枚举 `SYSTEM / DIRECT / CUSTOM`，DeepSeek `deepseek-v4-pro` 真实测试返回 HTTP 200；无结果弹窗，模型行测试按钮直接变为绿色勾选并显示可用、HTTP 状态和延迟提示。齿轮与测试按钮并列，页面无溢出；未点击保存且未修改用户供应商数据。
- 详情页操作布局：删除右上角“未测试”徽标，保存按钮从底部操作栏移动到右上角且只保留一个入口；测速和模型获取状态继续在页面中部“连接状态”区域展示。专项 `25 passed, 1 warning`，浏览器确认标题栏、表单和操作栏布局正常。
- SSL 解耦的早期负向开关已由 Step 18 迁移为正向 `verify_ssl`：默认验证证书，用户关闭后才设置 `verify=False`；三种代理模式与 TLS 继续相互独立。
- 代理布局优化：代理模式下拉缩短，独立 SSL 开关移动到其右侧同一行并保持垂直对齐；CUSTOM 展开区和连接行为不变。前端专项 `3 passed, 1 warning`、全量 `202 passed, 6 skipped, 1 warning`、JS/Python 静态检查和真实浏览器视觉验收均通过，未保存用户数据。
- 范围核对：协议、代理、模型默认配置与测试交互只改动模型管理详情；画布源码和构建产物均无 Git 差异。
- GitHub 发布：实现提交 `2be91ef` 已推送到 `origin/codex/tool-template-refactor`；提交前扫描确认没有 API Key 形式的秘密进入 Git 差异。

#### 验收标准与价值验证（How to Measure）

- Anthropic 节点向 `/v1/messages` 发送 `x-api-key / anthropic-version`，阻塞响应可得到文本、usage、stop reason，原始 request/response 可供输出变量提取。
- Anthropic 流式节点原样展示和持久化 SSE，不做结构化提取；失败和中断仍保存真实原始响应与错误。
- 私有 IP 与域名遵循相同的显式代理模式；关闭“验证 SSL 证书”后可访问自签名 HTTPS，开关开启时保持证书校验。
- OpenAI-compatible 节点、模型管理 CRUD/发现、运行锁、中断、日志和最近 10 次记录无回归。

### Step 18：Provider 显式路由与 TLS 信任（completed，2026-07-22）

#### 业务背景与目标（Why）

- 通过内网 IP 猜测并覆盖用户代理选择会让 `CUSTOM` 被静默忽略，也无法覆盖内部域名、内网代理和跨网段代理；目标是让 Provider 在不同网络环境下具有稳定、可解释的连接行为。
- 代理路由与 TLS 证书信任是两项独立决策。TLS 使用正向、默认安全的语义，避免负向开关造成误解。

#### 用户与真实场景（Who / Where）

- 本机企业测试工程师可能处于公司 VPN、全局代理、显式 HTTP/SOCKS 代理或直连网络中，需要准确选择请求路径。
- 内部模型服务可能使用受信 CA、自签名证书或企业内部 CA；关闭证书验证只能作为当前快速联调手段，不能与内网地址自动绑定。

#### 已确认范围与优先级（What / When）

- P0：严格执行 `SYSTEM / DIRECT / CUSTOM`。`SYSTEM` 使用 HTTPX 环境变量及 `NO_PROXY`；`DIRECT` 设置 `trust_env=False`；`CUSTOM` 设置显式代理并且不再被目标 IP 类型覆盖。
- P0：前端、API、持久化和运行时统一使用正向 `verify_ssl`，默认 `true`；仅在用户关闭“验证 SSL 证书”开关时传递 `verify=False`。
- P0：代理帮助只解释三种路由模式，公网/内网作为辅助示例，不参与运行时自动判断。
- P1 deferred：支持自定义 CA Bundle，使企业内部 CA 场景无需关闭证书验证。

#### 可独立验证子任务

| 子任务 | 目标 | 验证方法 | 依赖 |
|---|---|---|---|
| 18.1 | 删除 IP 启发式，严格执行三种代理模式 | HTTPX 客户端参数矩阵单测 | 无 |
| 18.2 | `verify_ssl` 正向契约与旧本机数据迁移 | Repository/API/Workflow 专项测试 | 18.1 |
| 18.3 | 正向开关和模式帮助 | 前端契约、JS 语法、桌面浏览器 E2E | 18.2 |
| 18.4 | 集成回归与发布 | 全量 pytest、静态检查、密钥扫描、GitHub 推送 | 18.1-18.3 |

##### 18.1 显式代理路由（completed，2026-07-22）

- 删除内网 IP/回环 IP/链路本地 IP 的自动路由判断，HTTPX 参数只由 `SYSTEM / DIRECT / CUSTOM` 决定；CUSTOM 对内网 IP 仍传递显式代理。
- 验证：`uv run pytest tests/test_model_gateway.py -q` 结果 `8 passed`，覆盖公网域名与内网 IP 在三种代理模式下使用完全一致的路由规则。

##### 18.2 正向 TLS 契约（completed，2026-07-22）

- 前端、模型管理 API、Pydantic 模型、SQLite Repository、模型测试和 Workflow 阻塞/流式请求统一使用 `verify_ssl`，默认 `true`；`false` 时 HTTPX 才收到 `verify=False`。
- SQLite 初始化新增 `verify_ssl` 列；检测到旧 `skip_ssl_verify` 列时按反向语义迁移，保留已有 Provider 的连接行为。列表 API 继续隐藏 TLS/代理细节，详情 API 返回正向值。
- 验证：模型网关、Provider Repository/API、Workflow LLM 与前端契约合计 `45 passed, 1 warning`；覆盖旧表迁移、三种代理模式独立 TLS 值和 CUSTOM 对内网地址不再旁路。

##### 18.3 模式帮助与安全开关（completed，2026-07-22）

- 代理模式下拉保持紧凑，右侧使用正向“验证 SSL 证书”滑动开关，默认开启；关闭后同一行显示红色“不安全”提示。
- `?` 支持悬停 CSS 与原生点击展开，内容直接解释 SYSTEM（环境变量及 NO_PROXY）、DIRECT（忽略环境代理）和 CUSTOM（始终使用显式 HTTP(S)/SOCKS5 代理），并明确 TLS 与代理模式独立。
- 前端契约和 JS 语法已纳入 18.2 的 `45 passed` 专项；桌面浏览器验证帮助点击、开关启停/恢复和无溢出布局。迁移后的 DeepSeek Provider 使用 SYSTEM + `verify_ssl=true` 真实测试返回 HTTP 200，页面行内显示可用；未点击保存。

##### 18.4 集成回归与本地提交（completed，2026-07-22）

- `npm run build` 通过且 Workflow 构建产物无 Git 差异；Python `compileall`、模型管理 JS 与 Workflow bundle 语法检查、`git diff --check` 全部通过。
- 全量 `uv run pytest -q` 结果 `203 passed, 6 skipped, 1 warning`；6 项跳过仍是未向本轮进程注入真实供应商环境变量的 live 用例，warning 为既有 Starlette/httpx 弃用提示。
- 浏览器完整流程确认正向 TLS 默认值、模式帮助、关闭验证的不安全提示、SYSTEM 状态恢复和 DeepSeek 真实 HTTP 200；未保存或修改用户 Provider。
- Git 差异未包含画布文件，API Key 形式秘密扫描结果为 0。按用户最新要求只创建本地提交，由用户自行推送当前分支。

#### 验收标准与价值验证（How to Measure）

- 相同代理模式不因 BASE_URL 是公网 IP、内网 IP 或域名而改变；CUSTOM 始终使用用户填写的代理。
- `verify_ssl=true` 时不向 HTTPX 注入 `verify=False`；关闭开关后所有代理模式统一使用 `verify=False`。
- 帮助提示明确说明三种模式与 TLS 独立关系；默认页面显示证书验证开启。
- 现有 Provider 的旧 `skip_ssl_verify` 值迁移后语义保持一致，API Key 和代理密码不进入列表或日志。

## 22. 待优化项目

### 22.1 独立凭据仓储与绑定

- 建立仅保存在本机的加密或受保护凭据仓储，支持 API Key、Bearer Token、Basic Auth、Cookie、自定义 Header、Client Secret 和证书等类型。
- 工具模板只声明凭据需求，不保存真实秘密；Workflow 可设置默认凭据，节点可按需覆盖。
- 节点保存 `credential_id` 或槽位绑定，运行时只在内存中解析并注入 `config["credentials"]`。
- 模板独立测试、节点运行和 Workflow 运行共用缺失凭据预检查及“绑定并运行”流程。
- 画布内复制节点可保留同机绑定；发布模板和导出 Workflow 必须剥离本机凭据 ID；导入后显示未绑定并要求接收者重新选择。
- 删除或失效凭据后，引用节点必须进入明确的“凭据失效”状态并禁止运行。
- 对日志、错误、Artifact 和用户主动打印内容增加已知秘密值脱敏；明确无法可靠识别任意 Python 硬编码秘密的残余风险。

### 22.2 Provider 自定义 CA Bundle

- 在模型管理供应商详情增加可选的本机 CA Bundle 配置，支持企业内部 CA 和自签名根证书；文件路径和证书内容不得进入 Workflow 或导出数据。
- 运行时使用 `ssl.create_default_context(cafile=...)` 构建 HTTPX SSLContext，并保持 `verify_ssl=true`；模型发现、测速、单模型测试、Workflow 阻塞和流式请求必须复用同一证书上下文。
- CA 文件缺失、格式错误或不可读取时在发起网络请求前给出明确错误；不得静默降级为 `verify=False`。
- UI 优先引导用户配置内部 CA，关闭“验证 SSL 证书”仅保留为可信内网临时联调手段，并持续显示“不安全”状态。

### 22.3 SCRIPT 节点待优化项

#### 业务背景与目标（Why）

- SCRIPT 是企业 Agent 测试流程中的 Python 胶水层，用于调用公网或内网接口、读取和转换数据、执行规则校验、聚合结果并向后续节点输出多个业务变量。
- 当前产品面向本机使用，核心价值是“普通非交互 Python 在环境和权限允许时可直接运行、原始控制台可以排错、顶层变量可以稳定传递”，不是建立受限插件生态。
- 优化目标是提高运行配置的真实性、单节点测试的可复现性和 Python 环境问题的可诊断性，同时继续遵守原始日志铁律。

#### 目标用户与真实场景（Who & Where）

- Workflow 编排人员在 Workflow Studio 中编写和调试 Python，通过 `inputs` 读取全局变量和上游输出，并将明确配置的 Python 顶层变量映射为下游 `${变量名}`。
- 用户会直接复用在 PyCharm 中运行的 `requests`、JSON 处理、文件处理和业务校验代码，需要看到真实 stdout、stderr、traceback 和依赖错误。
- 单节点调试经常需要复用上游某次成功输出；如果只能隐式读取“最近一次成功结果”，测试输入可能陈旧或随历史运行变化，无法稳定复现问题。

#### 行业调研结论

| 产品 | Code / Function 节点的代表能力 | 对 Agent Bench 的适用判断 |
|---|---|---|
| Dify | Python/JavaScript、声明式输入输出、独立沙箱、自动重试、失败分支和输出限制 | 借鉴重试与失败语义；严格沙箱不符合当前真实 Python、内网请求和文件处理定位 |
| n8n | 整批/逐条执行、固定并编辑测试数据、独立 Task Runner、代码格式化和受控依赖 | 优先借鉴固定测试输入；逐条/整批模式需等待数组、循环和聚合协议 |
| Node-RED | 多输出、异步完成、节点/流程/全局状态、启动/停止钩子、日志级别和动态状态 | 更适合长期事件流；持久状态和生命周期会降低本项目测试可复现性 |
| Langflow | 类型化输入输出、Python Interpreter、Mock Data、依赖声明、Check & Save | 借鉴语法检查、依赖诊断和测试数据能力，不引入其完整组件框架 |
| Flowise | 显式输入变量、全局变量、运行时状态、工具调用和沙箱执行 | 显式变量已具备；工具调用和运行时状态当前会扩大执行协议和维护成本 |

参考资料：

- Dify Code：<https://github.com/langgenius/dify-docs/blob/main/en/self-host/use-dify/nodes/code.mdx>
- n8n Code：<https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.code/>
- n8n Pin and Mock Data：<https://github.com/n8n-io/n8n-docs/blob/main/docs/build/work-with-data/pin-and-mock-data.md>
- Node-RED Function：<https://nodered.org/docs/user-guide/writing-functions>
- Langflow Python Interpreter：<https://docs.langflow.org/python-interpreter>
- Flowise Custom Function：<https://github.com/FlowiseAI/Flowise/blob/main/packages/components/nodes/utilities/CustomFunction/CustomFunction.ts>

#### 需求真实性与优先级（What & When）

| 优先级 | 优化项 | 决策与原因 |
|---|---|---|
| P0 | 运行配置真实性 | 当前前端展示 `retryCount / retryInterval / delayExecution / repeatExecution`，后端实际只从 `data.config` 读取超时；界面值与执行行为不一致，属于正确性缺陷 |
| P0 | 超时与重试契约 | 优先落实节点超时、重试次数和重试间隔；每次尝试必须可追溯，总耗时累加，中断必须终止当前尝试及等待中的后续重试 |
| P0 | 暂停未定义配置 | “延迟执行”当前价值较低；“重复执行”涉及副作用、停止条件和多次结果合并。协议确认前隐藏或删除，禁止继续展示无效配置 |
| P1 | 固定测试输入/上游快照 | 单节点测试可选择并编辑确定的全局变量和上游输出快照，避免依赖上游最近一次成功结果；不得影响正式整图执行语义 |
| P1 | Python 语法检查 | 使用与 Worker 相同的 Python 解释器执行 `compile()`，在不启动节点运行的情况下返回准确文件名、行号、列号和原始错误 |
| P1 | 依赖检查与环境可见性 | 识别代码中可静态判断的顶层 import，显示已安装、缺失和版本；动态 import 明确标为无法静态确认；不得自动执行 `pip` 或修改环境 |
| P2 | 显式代码格式化 | 只在用户主动点击时格式化 Python，不在保存或运行时静默改写代码；格式化失败不得覆盖原代码 |
| P2 | 常用起始模板 | 提供 HTTP 请求、JSON 转换、断言校验和多个顶层输出变量等最小模板，帮助用户快速写出可运行代码，但不恢复工具仓库或模板运行时引用 |
| P2 | 文件与 Artifact 输出 | 为报告、图片、大型 JSON 等非普通变量结果建立受控 Artifact 契约，避免把大文件或 Base64 数据塞入节点变量；不得暴露任意本机路径 |
| P3 | 代码持久化历史与 Diff | 在多人协作或版本追溯需求明确后再实现，不阻塞当前本机快速迭代 |
| P3 | 资源限制与更强隔离 | 当前继续使用独立子进程；只有产品转为远程、多用户或执行不可信代码时，才把容器隔离、CPU/内存限制升级为 P0 |

#### 保持不变的执行与日志契约

- SCRIPT 继续只支持 Python，不增加 JavaScript、交互式 stdin、桌面 GUI、完整断点调试器或插件市场。
- 用户代码继续运行在项目 `.venv` 的独立子进程中，允许使用已安装标准库和第三方包；依赖仍通过 `pyproject.toml + uv sync` 显式管理。
- `print()`、stdout、stderr、Python traceback 和平台警告继续按接收顺序显示原始内容，不做结构化提取、重组、摘要替换或自动脱敏推断。
- 日志只用于诊断，不参与业务变量提取；节点输出继续来自输出区明确映射的 Python 顶层变量。
- 未配置输出变量时脚本可以成功；已配置但不存在的顶层变量继续输出 `null`、写入原始警告并保持 `SUCCESS`；真实执行异常仍为 `FAILED`。
- 不增加持久节点上下文、启动/停止钩子或隐式跨 Run 状态，避免测试结果依赖历史执行。
- 不增加“逐条/整批执行”、多输出路由或 Script 内调用其他画布工具，除非数组、条件分支、循环、聚合和副作用规则先完成独立业务确认。

#### 待确认的业务规则

- 重试范围：只重试异常、超时和明确的可重试错误，还是所有 `FAILED`；用户代码已经产生外部副作用时是否允许自动重试。
- 重试日志：每次 attempt 独立保留完整控制台，还是在同一节点运行记录中按 attempt 分段；两种方案都不得丢失原始文本。
- 固定测试输入是否持久化到 Workflow 草稿。建议采用 n8n 语义：只对单节点调试生效，正式整图执行始终忽略固定数据并使用真实上游输出，实施前必须确认。

#### 验收标准与价值验证（How to Measure）

- 配置重试 2 次时，最多执行 3 个 attempt；每次开始时间、结束状态、错误、控制台和耗时可追溯，节点总耗时等于全部尝试与间隔的累计时间。
- 节点运行、重试等待或延迟阶段点击中断后，不再开始新的 attempt；当前 Worker 及派生进程被终止，节点状态为 `INTERRUPTED`，后代节点不执行。
- 节点设置页不存在任何保存后不影响执行的运行配置；未完成后端契约的字段必须隐藏或标为不可用，不能以可编辑状态误导用户。
- 单节点测试可以固定、编辑、清除和重新获取输入快照；同一快照重复运行得到相同输入，正式整图运行不读取测试快照。
- 语法错误在 Worker 启动前返回 `<workflow-node-main.py>` 的准确行号、列号和原始消息；检查过程不产生节点运行记录。
- 依赖检查能列出已安装包及版本和明确缺失包；不会安装包、修改 `pyproject.toml`、执行用户代码或声称动态 import 已验证。
- 原始控制台在成功、失败、超时、重试和中断场景中始终保留真实 stdout、stderr 与 traceback 顺序，继续支持鼠标选择、原生 `Ctrl+C` 和整段复制。
- 多个输出变量仍按“对外变量名 + Python 顶层变量名 + 类型”独立转换并传递；新增优化不得恢复基于日志、`request` 或固定 `response` 结构的 Script 字段提取。

#### 实施顺序与验证门禁

1. **运行配置审计与协议冻结**：列出前端所有配置字段、持久化位置和后端消费者；确认重试、副作用、attempt 日志与测试快照规则。验证为字段到行为的一一对应表，未确认项不得进入实现。
2. **超时与重试后端闭环**：实现 attempt、累计耗时、中断和后代阻断，并补充异常、超时、先失败后成功、连续失败和重试等待中断测试。专项测试通过后再改前端。
3. **运行配置 UI 收敛**：只展示已经具备后端行为的字段，移除或隐藏延迟/重复执行；使用真实 API 和浏览器 E2E 验证保存、重开、运行与日志。
4. **固定测试输入**：在不影响正式执行的前提下实现测试快照 CRUD 和单节点执行入口；覆盖上游历史变化、快照清除和整图忽略快照。
5. **语法与依赖诊断**：复用 Worker Python 环境完成只读检查；覆盖标准库、已安装第三方包、缺失包、动态 import 和语法错误。
6. **P2 能力评估**：模板、格式化和 Artifact 分别按独立业务需求立项，每项都需单独测试，不与 P0/P1 打包上线。

每个子任务必须依次执行相关单元测试、静态检查、前端构建、真实 API 流程和桌面浏览器 E2E；前一项未通过时暂停依赖任务。完整回归必须继续覆盖 Script 普通 Python、原始日志、多个顶层输出变量、超时、中断、后代阻断以及 HTTP/AGENT/LLM 节点不回归。

### 22.4 HTTP 节点待优化项（调研完成，开发未开始）

#### 状态与决策边界

- 本节记录 2026-07-23 对 Dify、n8n、Azure Logic Apps 和 Postman 官方能力的调研结论，以及结合企业 Agent 测试场景形成的候选优化项。
- 本节不是已确认开发需求。除已在历史沟通中明确的规则外，标记为“待确认”的行为不得直接实现。
- HTTP 节点的目标不是复制完整 Postman，而是稳定调用内网 FastAPI 或真实企业 Agent 环境、传递上游变量、保留可追溯原始请求与响应，并为下游 SCRIPT / AGENT 分析提供可靠数据。

#### 业务背景与目标（Why）

- 当前基础请求编辑能力已经覆盖 Method、URL、Headers、Params、Body、cURL 导入、`${变量名}` 替换、类型化输出变量和原始请求/响应日志；继续堆叠普通 API 客户端功能的边际价值有限。
- 主要风险转为执行正确性和规模承载：部分运行配置只在前端保存但后端不消费；Body 类型存在界面可选但运行协议不完整的情况；非 2xx 响应无法继续提取变量；大响应完整进入 SQLite 和浏览器后会在批量 Run 中放大存储与渲染成本。
- 优化顺序应为“执行正确性 > 结果可追溯 > 内网连接能力 > 功能广度”。

#### 用户与真实场景（Who / Where）

- 企业测试工程师在本机画布中配置 HTTP 节点，调用内网 FastAPI 数据提取层或未来真实企业 Agent 环境。
- 单次企业 Agent 调用可能持续四到五分钟，响应可能包含数百到数千行数据；测试人员需要在失败后查看原始请求/响应，并把结构化字段继续传递给下游节点。
- 并发数、整批重复执行、定时任务和 Run 级等待策略属于 Run 调度，不应继续堆在单个 HTTP 节点中。

#### 同类产品能力对照

| 能力 | 同类产品 | 当前状态 | 候选结论 |
|---|---|---|---|
| Method、URL、Headers、Params、Body | Dify / n8n 标配 | 已支持 | 保留现状 |
| cURL 导入 | n8n / Postman 支持 | 已支持 | 当前足够，不优先增加 OpenAPI 导入或 cURL 导出 |
| 上游变量引用 | Dify 支持深层变量，n8n 支持表达式 | 已支持 `${变量名}` 和输出提取 | 保持受限表达式，后续可补变量选择与插入交互 |
| 超时 | Dify 区分连接、读取、写入；n8n 支持请求超时 | UI 没有真实超时输入；Worker 外层默认 120 秒，HTTPX 内层默认 30 秒 | P0：统一单一配置来源并真实生效 |
| 重试 | Dify 支持次数/间隔；Logic Apps 支持固定/指数策略 | `retryCount / retryInterval` 只在前端保存 | P0：实现已确认的连接失败/超时重试 |
| Body 类型 | Dify / n8n 支持 JSON、Raw、URL encoded、multipart 和文件 | RAW 可用；FORM_DATA 由 `data=` 发送；Binary 界面可选但后端拒绝 | P0：修正真实协议或隐藏尚不可用入口 |
| HTTP 错误策略 | Dify 支持错误分支；n8n 支持 Never Error | 非 2xx 一律 FAILED，不能提取输出变量 | P0/P1：允许保留响应并按策略决定是否继续 |
| 响应结构 | Dify 输出 body/status/headers/files；n8n 可返回完整响应 | 已输出 `status_code / headers / body` | 当前结构可保留 |
| 大响应处理 | 常见文件变量、Artifact、截断预览或响应优化 | 完整响应进入 SQLite 和浏览器 | P0：建立完整 Artifact 与受控预览 |
| 认证与凭据 | Basic、Bearer、API Key、OAuth、凭据复用 | 只能手填 Header | P1：依赖 22.1，先做本机凭据绑定，不一次实现全部 OAuth |
| SSL、代理、重定向 | Dify / n8n 提供节点或连接配置 | 后端存在隐藏默认值，前端不可设置 | P1：复用 Provider 的显式路由和 TLS 语义 |
| 分页、批处理 | n8n 支持 | 不支持 | 当前企业 Agent 调用场景不需要，暂缓 |
| 请求前后脚本 | Postman 支持 | 可通过独立 SCRIPT 节点实现 | 不并入 HTTP 节点 |

#### 候选优先级（What / When）

##### P0：执行正确性与规模风险

1. **统一并落实超时与重试**
   - 删除当前 HTTPX 30 秒与 Worker 120 秒的隐式双重默认，建立可解释的单一配置来源。
   - 已确认规则继续有效：连接失败或超时按自定义次数和间隔重试；收到业务响应后不重试。HTTP 429/5xx 是否属于可重试服务失败仍未确认，不得自行加入。
   - 每次尝试必须记录序号、失败类型、等待时间和最终结果；中断必须终止当前请求和后续重试。

2. **修正 Body 类型真实性**
   - `application/x-www-form-urlencoded` 必须按 URL encoded 发送，`multipart/form-data` 必须产生真实 multipart 请求。
   - 切换 Body 类型时必须处理新建节点默认的 `Content-Type: application/json`，避免表单数据仍声明为 JSON。
   - Binary 在文件变量、持久化和 Artifact 协议确认前不得继续表现为已可运行功能。

3. **保留失败响应并支持后续分析**
   - 只要远端已经返回 HTTP 响应，就必须保留并允许提取 `response.status_code / response.headers / response.body`。
   - 节点状态与 Workflow 是否继续执行必须拆开定义，支持负向测试用例分析 400、401、422、500 等响应；默认继续还是默认终止仍待确认。

4. **大响应 Artifact 化**
   - 完整原始响应保存为本机 Artifact，运行记录保存路径或 ID、大小、摘要、哈希和受控预览；不得只截断后丢失原文。
   - 输出变量提取必须针对完整响应执行，不得因日志预览截断而改变测试判断。
   - Artifact 大小上限、保留周期、压缩方式和清理策略尚未确认。

##### P1：内网连接与可维护性

- 依赖 22.1 增加本机凭据绑定，首批只考虑 Bearer、API Key、Basic 和自定义 Header；真实秘密不得进入 Workflow 导出、Git 或普通日志。
- 为 HTTP 节点或 Target 建立显式 `SYSTEM / DIRECT / CUSTOM` 代理模式、正向 SSL 验证开关、按需自定义 CA 和重定向策略；不得按公网/内网 IP 自动猜测路由。
- 在 Headers、Params、Body 等字段增加可见变量选择/插入，不扩展为任意 Python 或 JavaScript 表达式。
- 增加变量解析后的请求预览，但凭据和已知秘密必须脱敏；原始执行日志继续记录真实请求的非秘密部分。

##### P2：有真实用例后再评估

- 重复 Query 参数和数组编码格式、Cookie Jar、客户端证书、OAuth1/OAuth2、文件上传/下载、分页和批处理。
- GraphQL、SSE、WebSocket、gRPC 等协议不作为当前 HTTP 节点的隐式扩展。

#### 明确不并入 HTTP 节点的能力

- 并发数、整批重复执行、延迟执行和定时任务属于 Run 调度。
- 业务断言、响应质量判断和前后置脚本分别由 SCRIPT / AGENT 节点承担。
- 面向 LLM 的通用“响应优化”不替代当前明确、可追溯的输出变量提取。

#### 待确认决策

1. 超时口径：`A` 一次节点运行共享总超时预算；`B` 每次重试重新获得完整超时时间。当前推荐 A，但未确认。
2. 非 2xx 默认行为：`A` 节点标记失败但可配置继续下游分析；`B` 始终终止当前流程。当前推荐 A，但未确认。
3. Binary：`A` 先隐藏，等文件变量与 Artifact 协议完成后开放；`B` 立即实现本机文件上传。当前推荐 A，但未确认。
4. 配置覆盖层级：系统默认、Run 参数和节点参数之间的优先级尚未确认；不得自行定义覆盖关系。

#### 初步开发拆分（确认范围后执行）

| 子任务 | 目标 | 输入 / 输出 | 验证方法 | 依赖 |
|---|---|---|---|---|
| 22.3.1 | 超时与重试内核 | 节点/Run 配置；尝试记录与最终结果 | 本地慢服务、连接失败、超时、中断、非重试业务响应 | 待确认决策 1、4 |
| 22.3.2 | Body 协议真实性 | 四类 Body 配置；真实 HTTP 报文 | 本地 Mock 验证 Content-Type、原始字节、multipart 边界和变量替换 | 待确认决策 3 |
| 22.3.3 | 失败响应策略 | 非 2xx 原始响应；状态与继续策略 | 400/401/422/500 节点与下游变量 E2E | 待确认决策 2、真实 DAG 执行语义 |
| 22.3.4 | 大响应 Artifact | 完整响应；Artifact 元数据、预览和提取结果 | 大 JSON/文本/二进制响应、清理、恢复和浏览器性能测试 | Artifact 契约 |
| 22.3.5 | 凭据与网络选项 | credential_id、代理/TLS/CA/重定向 | 密钥脱敏、三代理模式、自签名 HTTPS 和导入导出测试 | 22.1、22.2 |
| 22.3.6 | 集成回归 | 完整 HTTP 节点业务流程 | 单元测试、构建、静态检查、桌面浏览器 E2E、全量回归 | 22.3.1-22.3.5 中本期范围 |

#### 候选验收标准（How to Measure）

- 页面展示的每个运行配置都必须被后端消费并能从运行记录证明生效，不允许继续存在“可填写但无执行语义”的控件。
- 连接失败/超时与收到 HTTP 响应必须可区分；重试次数、等待时间和最终状态可追溯，业务响应不会被默认重复调用。
- RAW、JSON、URL encoded、multipart 和未来 Binary 的页面名称、Content-Type、真实报文及日志一致。
- 非 2xx 响应原文和结构化字段不会丢失，是否继续执行遵循已确认策略。
- 大响应不直接无限制进入 SQLite 和浏览器，但完整原文仍可回溯，变量提取结果不受预览限制。
- HTTP 节点优化不得把 Run 调度、SCRIPT 断言或 AGENT 质量判断重新耦合进节点内部。

#### 调研来源

- Dify HTTP Request: <https://docs.dify.ai/en/cloud/use-dify/nodes/http-request>
- n8n HTTP Request: <https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest>
- Azure Logic Apps error handling and retry policies: <https://learn.microsoft.com/en-us/azure/logic-apps/error-exception-handling>
- Postman request settings: <https://learning.postman.com/docs/use/send-requests/create-requests/request-settings/>

### 22.5 DeepSeek `deepseek-v4-pro` LLM 节点高级参数实测（completed，2026-07-23）

#### 业务背景与验收口径

- Why：企业测试工程师需要在 Workflow LLM 节点直接覆盖模型请求参数，并能从节点日志确认参数确实进入请求、模型成功响应以及 token 消耗，避免仅依据供应商文档声明可用。
- Who / Where：本机 Agent Bench `http://127.0.0.1:8010/`，模型管理中的 `DeppSeek / deepseek-v4-pro`，专用 Workflow `deepseek-v4-pro 高级参数验证`（ID `93fb7ecc003043ae942d6d605cdcbeea`）及 LLM 节点 `LLM_mrwdl894_rmnsw`。
- What / When：按用户确认的 `1A / 2A / 3A` 执行广泛兼容矩阵；请求字段进入实际 Body、节点成功且响应结构合理即记为“接口接受”，存在可观察语义时再单独证明生效。该 live 结果只代表 2026-07-23 当前供应商端点，不固化为跨模型通用契约。
- How to Measure：逐次通过高级参数 JSON 框保存并运行，核对持久化日志中的 `request_body / response_body / usage / error`；使用 JSON 输出、logprobs、工具调用、thinking 开关、stop 截断和流式 usage 作为可观察语义验证。

#### Live 矩阵结果

| 参数 / 组合 | 结果 | 可观察证据与边界 |
|---|---|---|
| `{}` | SUCCESS | 基线输出 `OK`，usage 完整 |
| `temperature / top_p / max_tokens / frequency_penalty / presence_penalty / stop` | 接受 | 全部进入请求；`max_tokens: 16` 将完成 token 限制为 16，`stop: ["XYZ"]` 将 `ABCXYZ` 截断为 `ABC` |
| `response_format: {"type":"json_object"}` | 生效 | 返回合法 JSON `{"result":"OK"}` |
| `logprobs: true / top_logprobs: 2` | 生效 | 阻塞响应包含逐 token `logprob` 与两个候选 `top_logprobs`，包括 reasoning token |
| `tools / tool_choice: "auto"` | 生效 | 返回 `finish_reason: "tool_calls"` 和 `get_weather({"city":"北京"})` |
| `tool_choice: "required"` | 有条件生效 | 默认 thinking 模式返回 HTTP 400 `Thinking mode does not support this tool_choice`；同时设置 `thinking.type: "disabled"` 后成功返回工具调用 |
| `thinking: {"type":"enabled"}` | 生效 | 响应包含 `reasoning_content` 与 `reasoning_tokens` |
| `thinking: {"type":"disabled"}` | 生效 | `reasoning_content` 为 null，短提示只消耗 1 completion token |
| `max_completion_tokens` | 接受 | `max_completion_tokens: 16` 请求成功并返回结构化 usage |
| `stream_options: {"include_usage":true}` | 生效 | 必须配合右侧“流式输出”开关；最终 SSE chunk 包含 usage。流式 response 仍保留原始 SSE，同时从 usage 事件提取并持久化顶层 `usage` 供日志展示 |
| `n` | 仅支持 1 | `n: 1` 成功；`n: 2` 返回 HTTP 400 `currently only n = 1 is supported` |
| `seed / user` | 接受但无法证明生效 | 请求成功且字段进入 Body；当前响应没有足以证明语义生效的信号 |
| `enable_thinking: false` | 接受但未生效 | 请求成功，但响应仍包含 reasoning 且 32 个 completion token 全为 reasoning；不得用它替代 `thinking.type: "disabled"` |
| `reasoning_effort: "low"` | 接受但无法证明生效 | 请求成功，但仍生成完整 reasoning；没有观察到可区分效果 |
| `top_k / min_p / repetition_penalty` | 接受但无法证明生效 | 组合请求成功；供应商会静默接受未知字段，因此不能据此宣称采样语义已实现 |
| 未知字段对照 | 被静默接受 | `definitely_not_a_real_parameter: true` 仍 SUCCESS，证明“HTTP 成功”只能说明网关接受，不能单独证明字段被模型消费 |

#### 结论与保留状态

- 已直接观察到语义生效的参数：`max_tokens`、`stop`、`response_format`、`logprobs`、`top_logprobs`、`tools`、`tool_choice`、`thinking`、`stream_options`。官方候选 `temperature`、`top_p`、`frequency_penalty`、`presence_penalty` 和兼容字段 `max_completion_tokens` 均被当前端点接受，但本轮没有为每个采样参数建立统计显著的独立效果证明。
- `stream` 不属于高级参数框的可编辑字段，画布右侧“流式输出”开关是唯一入口；节点保存时由平台写入最终请求。
- 不推荐依赖 `enable_thinking`、`reasoning_effort`、`top_k`、`min_p`、`repetition_penalty`、`seed` 或 `user`，除非后续增加能证明实际语义的对照测试。
- 专用 Workflow 和最近 10 条节点运行日志已保留；节点当前停在已验证的非流式配置 `thinking.disabled + temperature 0 + top_p 0.8 + max_tokens 128`。节点历史上限固定为 10，完整矩阵以本节为长期记录。
- 官方候选参数来源：DeepSeek Chat Completion 文档 <https://api-docs.deepseek.com/api/create-chat-completion>。

### 22.6 LLM JSON 参考示例与格式化（completed，2026-07-23）

- Why：企业测试人员需要在 LLM 节点和模型默认 Body 中快速识别常用 DeepSeek 参数，但参考内容不能自动改变模型行为、token 成本或已保存配置。
- Who / Where：Workflow LLM 节点“高级参数”编辑器，以及模型管理单模型“默认 Body JSON”配置弹窗。
- What / When：按用户确认的 `1A / 2C / 3A`，两处空编辑器只显示同一组浅色斜体 placeholder；用户输入后参考内容自动消失，不写入状态、不参与请求。两处右上角均提供 Beautify，合法 JSON 对象格式化为两空格缩进，无效 JSON 保留原文并显示错误。
- 模型配置弹窗保持原有 `560px` 宽度，默认 Body 编辑区通过更高优先级样式固定最小高度 `280px`，解决通用 `.input` 将其压缩至 `42px` 最小高度的问题；实测整张弹窗高度为 `542px`，桌面视口内无溢出。
- Workflow LLM 节点高级参数正文同步提升至最小高度 `280px`（含 `34px` 工具栏的编辑器整体最小高度 `314px`）；实测正文 `280px`、整体含边框 `316px`，与运行配置间隔 `43px`，节点编辑器内部滚动且无模块重叠。
- 验收：空 LLM 参数只显示参考值；输入后 placeholder 消失；两处 Beautify 均完成真实页面格式化；无效 JSON 分别显示“高级参数不是合法 JSON”和“默认 Body 不是合法 JSON”；取消弹窗和重载 Workflow 后，模型默认 Body 与节点参数均保持原持久化值。

### 22.7 节点日志请求/响应标题与流式 token（completed，2026-07-23）

- Why：节点调试需要快速区分完整 request/response 并直接复制；LLM 流式运行此前固定保存 `usage=None`，日志行无法显示实际 token 消耗。
- Who / Where：桌面 Workflow Studio 中展开 HTTP、LLM 或其他业务节点的单次运行日志；LLM 用户同时覆盖 OpenAI-compatible 与 Anthropic 协议的流式调用。
- What / When：请求/响应标题统一为 `request / response`，标题字号与日志行时间同为 `14px`，标题行最右侧提供复制完整内容的图标按钮。OpenAI-compatible 流式请求由平台写入 `stream_options.include_usage=true`；流结束后从 OpenAI usage 事件或 Anthropic `message_start / message_delta` 事件合并 usage 并持久化。
- 边界：流式 response 仍保存并展示脱敏后的原始 SSE，不提取流式输出变量；usage 解析失败或供应商未返回 usage 时保持 `None`，不把估算值冒充真实 token。历史记录若 `usage` 为空但原始 SSE 含 usage，前端只为展示提取该真实值，不回写或改造历史数据。
- 验收：HTTP 与 LLM 日志均显示 `request / response`、复制按钮位于标题最右侧且复制完整正文；OpenAI 流式运行记录保存 `total_tokens`，Anthropic 保存合并后的 `input_tokens / output_tokens`，前端日志行显示对应 token 总数。
