# Workflow Studio 节点内聚与执行协议计划（T13.2）

> 状态：T13.1 前端高保真原型和回归已完成；T13.2 Step 11 已完成验收并推送到 GitHub。按最新业务决策，工具管理/工具模板体系及所有画布耦合已彻底删除，工具节点完全在 Workflow 中定义；LLM 节点已接入模型管理引用、任意 JSON 高级参数和框架无关的 OpenAI-compatible 网关内核。新版 Workflow 持久化与 DAG 真实执行 API 仍尚待单独确认和实现。
>
> 更新时间：2026-07-20
>
> 范围：新版全屏 Workflow Studio 和新的工具模板体系。旧固定 Workflow、旧 Run 页面/API/执行链以及当前 Script / Agent 工具协议将被删除，不提供兼容迁移。
>
> 事实来源优先级：用户最新确认 > 本计划的“已确认决策” > `docs/enterprise-agent-test-orchestration.md` 中的既有规则。未列为“已确认”的内容不得直接实现。

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

#### Step 14：Workflow 与节点中断控制（pending clarification，2026-07-22）

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

## 22. 待优化项目

### 22.1 独立凭据仓储与绑定

- 建立仅保存在本机的加密或受保护凭据仓储，支持 API Key、Bearer Token、Basic Auth、Cookie、自定义 Header、Client Secret 和证书等类型。
- 工具模板只声明凭据需求，不保存真实秘密；Workflow 可设置默认凭据，节点可按需覆盖。
- 节点保存 `credential_id` 或槽位绑定，运行时只在内存中解析并注入 `config["credentials"]`。
- 模板独立测试、节点运行和 Workflow 运行共用缺失凭据预检查及“绑定并运行”流程。
- 画布内复制节点可保留同机绑定；发布模板和导出 Workflow 必须剥离本机凭据 ID；导入后显示未绑定并要求接收者重新选择。
- 删除或失效凭据后，引用节点必须进入明确的“凭据失效”状态并禁止运行。
- 对日志、错误、Artifact 和用户主动打印内容增加已知秘密值脱敏；明确无法可靠识别任意 Python 硬编码秘密的残余风险。
