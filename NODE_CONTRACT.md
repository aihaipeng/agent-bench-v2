# Node Contract

本文档是 Agent Bench v2 节点契约的当前基线。后续节点字段、输入输出协议和运行行为的变更，都必须先更新本文档。第一章统一定义 Context；后续每章只描述一种节点，并统一包含 Design-Time、Run-Time、Input & Output Protocol。

参数表编写规则：

- 每个参数列表必须完整列出当前层级保存的全部字段，不得只列主要字段。
- string、int、boolean 等简单字段直接在当前层级参数表说明。
- object、array 或具有独立校验规则的复杂字段，在当前层级参数表中保留字段入口，并在后续单独列出其全部子字段。
- Design-Time 和 Run-Time 都采用“完整示例在前，参数列表和规则在后”的顺序。
- Design-Time 和 Run-Time 参数表统一使用“字段、类型、取值、示例、含义”五列。

## 1. Context

### 1.1 作用

Context 是一次 Workflow Run 的共享变量池，用于在节点之间传递业务数据。它只保存变量名和值，不保存来源节点、路径、描述或运行日志。

```json
{
  "review_result": {
    "status": "PASS",
    "reason": "审核通过"
  },
  "review_status": "PASS"
}
```

### 1.2 生命周期与隔离

- 每次新的 Workflow Run 开始时创建空 Context。
- Context 只在当前 Workflow Run 内有效，不同 Run 之间完全隔离。
- Workflow Run 结束后，Context 是否持久化由运行记录策略决定；它不作为 Design-Time 定义的一部分。
- 节点只能读取当前 Context，不能直接读取其他 Run 的 Context。

### 1.3 读写规则

- 节点通过统一的输入协议读取 Context 变量。
- 节点成功后才可以把输出变量提交到 Context。
- 节点执行期间产生的中间值属于节点本地状态，不直接修改共享 Context。
- 节点失败、超时或被中断时，其待提交输出全部丢弃，Context 保持执行前状态。
- Context 中的值必须能够序列化为严格 JSON；不可序列化值、NaN、Infinity 和循环引用不得写入。

### 1.4 与 Run-Time 的关系

- Context 是当前 Workflow Run 的业务状态。
- Run-Time 是节点执行记录，保存实际输入、已提交输出、状态、重试和错误。
- Run-Time 的 inputs 和 outputs 是运行快照，不会改变 Context 的数据结构。
- 日志、原始请求、原始响应和错误堆栈属于独立运行数据，不写入 Context。

### 1.5 Design-Time 与 Run-Time 边界

Design-Time 和 Run-Time 是两个独立的数据层，不允许把配置声明与执行事实混合保存。

| 维度       | Design-Time                                        | Run-Time                                               |
| ---------- | -------------------------------------------------- | ------------------------------------------------------ |
| 目标       | 定义节点以后应当如何执行                           | 记录节点某一次实际上如何执行                           |
| 创建时机   | 用户创建或编辑节点时                               | Workflow Run 调度到该节点时                            |
| 生命周期   | 跨多个 Workflow Run 长期存在                       | 只属于一个 Workflow Run                                |
| 可变性     | 用户显式保存后可以更新                             | 执行过程中追加状态，结束后作为历史记录不可编辑         |
| 数量关系   | Workflow 中每个节点一份定义                        | 一个 Design-Time 节点可以产生多个 NodeRun              |
| 重试关系   | execution 声明允许如何重试                         | attempts 记录实际发生了哪些尝试                        |
| 输入       | 保存模板、常量和 Context 引用，不保存本轮实际值    | inputs 保存本次尝试实际读取的 Context 变量和值         |
| 输出       | outputs 声明允许产生哪些变量及其类型或提取路径     | outputs 保存本次成功后实际提交到 Context 的变量名和值  |
| 请求       | 保存尚未解析的 URL、Header、Params、Body 或 Prompt | 保存 Context 解析后实际使用的请求内容                  |
| 响应       | 不保存响应                                         | 保存本次实际收到的响应                                 |
| 状态与时间 | 不保存运行状态、开始时间、结束时间或耗时           | 保存 status、started_at、finished_at、duration_ms      |
| 日志与错误 | 不保存日志、错误或堆栈                             | error 保存结构化错误；日志是契约外的临时观测数据       |
| Context    | 不保存某次 Run 的 Context                          | 只保存 inputs/outputs 快照；Context 本体仍是独立变量池 |

强制边界规则：

- 保存 Workflow 或节点配置时，只更新 Design-Time，不创建或修改 Run-Time。
- 启动节点时，执行器读取该次执行使用的 Design-Time 配置；运行中产生的数据只能写入 Run-Time、日志或待提交输出。
- 节点运行期间修改 Design-Time，不得改变已经开始的 NodeRun 或其中后续重试使用的配置。
- 历史 NodeRun 不因 Design-Time 后续修改而重写。
- Design-Time outputs 是声明数组；Run-Time outputs 是实际值对象，两者名称相同但结构和职责不同。
- Run-Time inputs 和 outputs 只是本次尝试的快照，不是 Context 的另一份主存储。
- Run-Time 不允许反向修改节点名称、脚本源码、HTTP 请求模板、重试配置或输出声明。
- Context 只接受成功尝试一次性提交的 Run-Time outputs；失败尝试不得修改 Context。
- 所有时间数值字段统一使用整数毫秒，字段名使用 _ms 后缀。
- 快速迭代阶段不在 Run-Time 中定义日志字段或日志引用字段；日志只用于执行期间的临时观测。
- Run-Time 的 started_at 和 finished_at 统一使用 YYYY-MM-DD HH:mm:ss 格式，例如 2026-07-24 23:11:50。
- 所有耗时统计字段统一使用整数毫秒，字段名使用 _ms 后缀，例如 duration_ms。
- 快速迭代阶段不在 Run-Time 中定义日志字段或日志引用字段；日志只用于执行期间的临时观测。

当前契约尚未定义 Design-Time 版本号、配置哈希或完整快照字段。历史 NodeRun 如何精确关联到当时使用的 Design-Time 版本，需要后续单独确认。

### 1.6 统一引用格式

HTTP、LLM 和 AGENT 节点中允许引用 Context 的配置字段统一使用以下格式：

```text
{{ context.variable_name }}
{{ ctx.variable_name }}
```

context 和 ctx 完全等价，都指向当前 Workflow Run 的 Context。界面插入变量时默认生成完整形式 {{ context.variable_name }}；保存时保留用户原始写法，不自动改写 ctx。

支持读取嵌套对象和数组：

```text
{{ context.review_result.status }}
{{ ctx.devices[0].name }}
```

引用语法只允许变量读取、对象字段访问和数组下标访问，不允许函数调用、运算符或任意代码。

```text
{{ context.price * 2 }}       不允许
{{ context.name.upper() }}    不允许
```

解析规则：

- 整个字段只有一个 Context 引用时，保留变量的原始 JSON 类型。
- Context 引用嵌入普通文本时，将变量转换为文本；对象和数组使用紧凑 JSON。
- 引用的变量不存在或嵌套路径不存在时，节点在实际请求或调用开始前失败。
- 同一字段中可以混合使用 context 和 ctx。
- {{ variable_name }} 不符合 Context 引用语法，始终保持普通文本。
- \{{ ctx.variable_name }} 表示输出引用原文 {{ ctx.variable_name }}，不读取 Context。
- SCRIPT 的 Python 源码不执行模板替换，继续通过 get_val 和 set_val 访问 Context。

## 2. SCRIPT

### 2.1 Design-Time

Design-Time 只记录节点定义，不记录某次运行的输入值、实际输出值、Context、状态、日志或错误。

#### Design-Time 示例

```json
{
  "id": "V1StGXR8_Z5jdHi6B-myT",
  "type": "SCRIPT",
  "name": "汇总审核结果",
  "description": "汇总多个审核节点的结果",
  "script": {
    "language": "python",
    "version": "3.14",
    "source": "review = get_val(\"review_result\")\nset_val(\"review_status\", review[\"status\"])"
  },
  "execution": {
    "max_attempts": 3,
    "delay_ms": 1000
  },
  "outputs": [
    {
      "name": "review_status",
      "type": "string"
    }
  ]
}
```

#### 与 Run-Time 的字段边界

| Design-Time                     | Run-Time                | 边界                                                        |
| ------------------------------- | ----------------------- | ----------------------------------------------------------- |
| id                              | node_id                 | Run-Time 只引用节点 ID，不修改 ID                           |
| type                            | type                    | Run-Time 复制节点类型用于识别记录                           |
| name、description               | 无对应业务字段          | 只用于定义态展示，不作为执行结果                            |
| script.language、script.version | 无对应业务字段          | 决定执行环境，不属于本次运行结果                            |
| script.source                   | 无对应业务字段          | 作为本次执行代码输入，不写入 inputs、outputs 或 Context     |
| execution                       | attempts                | execution 声明最大重试和间隔；attempts 记录实际尝试         |
| outputs 数组                    | attempts[].outputs 对象 | 前者声明允许输出的 name/type，后者保存成功产生的 name/value |
| 无 Design-Time inputs           | attempts[].inputs       | SCRIPT 不预先声明输入，Run-Time 按实际 get_val 调用记录     |
| 无 Design-Time 状态和错误       | status、error           | 只由执行过程产生                                            |
| 无 Design-Time 日志             | 无 Run-Time 字段        | 日志只作为执行期间的临时观测数据                            |

#### 参数列表

| 字段        | 类型   | 取值               | 示例                                                  | 含义                                  |
| ----------- | ------ | ------------------ | ----------------------------------------------------- | ------------------------------------- |
| id          | string | 21 位 NanoID       | V1StGXR8_Z5jdHi6B-myT                                 | 节点在 Workflow 中的唯一标识          |
| type        | string | SCRIPT             | SCRIPT                                                | 节点类型为脚本                        |
| name        | string | 用户自定义         | 汇总审核结果                                          | 画布和日志中显示的节点名称            |
| description | string | 用户自定义，可为空 | 汇总多个审核节点的结果                                | 节点业务用途说明                      |
| script      | object | 必填               | {"language":"python","version":"3.14","source":"..."} | 脚本参数                              |
| execution   | object | 必填               | {"max_attempts":3,"delay_ms":1000}                    | 执行参数                              |
| outputs     | array  | 可为空，默认 []    | [{"name":"review_status","type":"string"}]            | 允许脚本写入 Context 的输出变量白名单 |

#### script 参数

| 字段     | 类型   | 取值            | 示例                              | 含义                   |
| -------- | ------ | --------------- | --------------------------------- | ---------------------- |
| language | string | python          | python                            | 脚本语言类型           |
| version  | string | 例如 "3.14"     | "3.14"                            | Python 语言版本        |
| source   | string | Python 源码文本 | review = get_val("review_result") | 用户编辑的完整脚本代码 |

#### execution 参数

| 字段         | 类型 | 取值     | 示例 | 含义                             |
| ------------ | ---- | -------- | ---- | -------------------------------- |
| max_attempts | int  | 0~10     | 3    | 最大重试次数，不包含首次执行     |
| delay_ms     | int  | 0~600000 | 1000 | 两次重试之间的固定间隔，单位毫秒 |

暂不设置 retry_on 和 max_output_bytes。

max_attempts 的语义：

| 配置值 | 最大总执行次数      |
| ------ | ------------------- |
| 0      | 1 次，不重试        |
| 1      | 2 次，最多重试 1 次 |
| 3      | 4 次，最多重试 3 次 |

delay_ms 只在一次执行失败后、下一次重试开始前生效，不表示节点首次执行前的延迟。

#### outputs 参数

outputs 是脚本输出声明。脚本只能通过 set_val 写入这里声明的变量；未声明的变量不能写入 Context。

| 字段 | 类型   | 取值                                                  | 示例          | 含义                           |
| ---- | ------ | ----------------------------------------------------- | ------------- | ------------------------------ |
| name | string | 合法变量名，且在本节点内唯一                          | review_status | 写入 Context 的变量名          |
| type | string | string、number、integer、boolean、object、array、null | string        | 运行时执行的严格 JSON 类型约束 |

outputs 不包含 description 或输出路径。脚本应直接生成下游需要的值；嵌套对象由下游脚本使用 Python 对象访问语法读取。

Design-Time 不定义输入变量列表。脚本通过 get_val 从当前 Workflow Run 的 Context 读取变量。

### 2.2 Run-Time

Run-Time 记录一次节点执行及其每次尝试，不修改 Design-Time 定义。

#### Run-Time 示例

```json
{
  "run_id": "workflow-run-001",
  "node_run_id": "node-run-001",
  "node_id": "V1StGXR8_Z5jdHi6B-myT",
  "type": "SCRIPT",
  "status": "SUCCESS",
  "started_at": "2026-07-24 23:11:50",
  "finished_at": "2026-07-24 23:11:52",
  "duration_ms": 2000,
  "attempts": [
    {
      "attempt": 1,
      "status": "SUCCESS",
      "started_at": "2026-07-24 23:11:50",
      "finished_at": "2026-07-24 23:11:52",
      "duration_ms": 2000,
      "inputs": {
        "review_result": {
          "status": "PASS",
          "reason": "审核通过"
        }
      },
      "outputs": {
        "review_status": "PASS"
      },
      "error": null
    }
  ]
}
```

#### 参数列表

| 字段        | 类型        | 取值                                                           | 示例                               | 含义                                       |
| ----------- | ----------- | -------------------------------------------------------------- | ---------------------------------- | ------------------------------------------ |
| run_id      | string      | Workflow Run ID                                                | workflow-run-001                   | 本次 Workflow Run 的唯一标识               |
| node_run_id | string      | NodeRun ID                                                     | node-run-001                       | 本次节点运行记录的唯一标识                 |
| node_id     | string      | 21 位 NanoID                                                   | V1StGXR8_Z5jdHi6B-myT              | Design-Time 节点 ID                        |
| type        | string      | SCRIPT                                                         | SCRIPT                             | 节点类型                                   |
| status      | string      | PENDING、RUNNING、SUCCESS、FAILED、TIMEOUT、CANCELLED、SKIPPED | SUCCESS                            | 节点最终状态                               |
| started_at  | string      | YYYY-MM-DD HH:mm:ss                                            | 2026-07-24 23:11:50                | 节点首次开始时间，例如 2026-07-24 23:11:50 |
| finished_at | string/null | YYYY-MM-DD HH:mm:ss 或 null                                    | 2026-07-24 23:11:52                | 节点最终结束时间；尚未结束时为 null        |
| duration_ms | int/null    | 大于等于 0 或 null                                             | 2000                               | 节点总耗时，单位毫秒；尚未结束时为 null    |
| attempts    | array       | 可为空                                                         | [{"attempt":1,"status":"SUCCESS"}] | 每次实际执行尝试，按执行顺序排列           |

节点状态统一使用：

```text
PENDING | RUNNING | SUCCESS | FAILED | TIMEOUT | CANCELLED | SKIPPED
```

每次尝试的业务输入和输出统一放在 AttemptRun.inputs 和 AttemptRun.outputs 中，避免重试时覆盖数据。

#### attempts 参数

| 字段        | 类型        | 取值                                         | 示例                                | 含义                                          |
| ----------- | ----------- | -------------------------------------------- | ----------------------------------- | --------------------------------------------- |
| attempt     | int         | 从 1 开始                                    | 1                                   | 当前第几次执行                                |
| status      | string      | RUNNING、SUCCESS、FAILED、TIMEOUT、CANCELLED | SUCCESS                             | 本次尝试状态                                  |
| started_at  | string      | YYYY-MM-DD HH:mm:ss                          | 2026-07-24 23:11:50                 | 本次尝试开始时间                              |
| finished_at | string/null | YYYY-MM-DD HH:mm:ss 或 null                  | 2026-07-24 23:11:52                 | 本次尝试结束时间                              |
| duration_ms | int/null    | 大于等于 0 或 null                           | 2000                                | 本次尝试耗时，单位毫秒                        |
| inputs      | object      | 变量名到 JSON 值的映射                       | {"review_result":{"status":"PASS"}} | 本次尝试实际通过 get_val 读取的变量及其返回值 |
| outputs     | object      | 变量名到 JSON 值的映射，默认 {}              | {"review_status":"PASS"}            | 本次尝试成功后提交到 Context 的变量           |
| error       | object/null | error 对象或 null                            | null                                | 本次尝试错误；成功时为 null                   |

#### error 参数

| 字段    | 类型        | 取值                    | 示例                        | 含义                         |
| ------- | ----------- | ----------------------- | --------------------------- | ---------------------------- |
| code    | string      | 稳定错误码              | SCRIPT_RUNTIME_ERROR        | 机器可读错误码               |
| message | string      | 非空字符串              | review_result.status 不存在 | 面向用户的错误说明           |
| details | object/null | 结构化 JSON 对象或 null | null                        | 可选诊断信息；不写入 Context |

错误堆栈、标准输出和标准错误属于契约外的临时观测日志，不写入 Run-Time。

#### Run-Time 规则

输入记录：

- inputs 只记录脚本实际调用 get_val 读取过的变量。
- 同一次尝试多次读取同一变量时，inputs 中只保留一个变量名和值。
- 读取不存在的变量时，get_val 返回 None，运行记录中的对应值为 JSON null。
- inputs 记录 get_val 返回的值，不包含来源节点、路径或其他来源元数据。

输出记录：

- outputs 只记录成功提交到 Context 的变量。
- 脚本异常、超时、中断或 set_val 校验失败时，outputs 必须为 {}。
- 节点没有输出时，outputs 为 {}，不使用 null 表示空输出。

重试：

- execution.max_attempts 表示最多重试次数，不包含首次执行。
- 每次实际执行都追加一个 AttemptRun，不得覆盖之前的尝试记录。
- 任一尝试失败时，其待提交输出不会进入 Context。
- 只有最终成功的尝试才会更新 Context；如果所有尝试都失败，Context 保持节点执行前状态。
- 中间失败但后续成功时，NodeRun.status 最终为 SUCCESS。

### 2.3 Input & Output Protocol

#### 用户代码接口

平台向 Python 脚本提供：

```python
value = get_val(name)
set_val(name, value)
```

| 调用                 | 参数                                 | 含义                    |
| -------------------- | ------------------------------------ | ----------------------- |
| get_val(name)        | name: string                         | 从当前 Context 读取变量 |
| set_val(name, value) | name: string、value: JSON 可序列化值 | 写入本节点待提交输出    |

#### get_val 规则

- 变量存在时返回 Context 中的原始值，包括嵌套对象和数组。
- 变量不存在时返回 Python None（对应 JSON null），不会自动报错。
- 平台不做路径解析、类型转换或来源包装；脚本直接使用 Python 对象访问语法处理嵌套值。

```python
review = get_val("review_result")
if review is not None:
    status = review["status"]
    reason = review["reason"]
    set_val("review_status", status)
    set_val("review_reason", reason)
```

#### set_val 规则

- name 未在 Design-Time outputs 中声明时，立即使本次执行失败。
- value 必须符合声明的 type，平台不自动转换类型。
- value 必须是严格 JSON 可序列化值。
- 同一次执行中重复设置同名变量时，本次执行失败。
- name 必须符合 [A-Za-z_][A-Za-z0-9_]*，且在 outputs 中唯一。

严格类型对应关系：

| outputs.type | 允许的 Python 值            |
| ------------ | --------------------------- |
| string       | str                         |
| number       | int 或 float，但不允许 bool |
| integer      | int，但不允许 bool          |
| boolean      | bool                        |
| object       | dict                        |
| array        | list                        |
| null         | None                        |

#### 提交与日志

- set_val 只写入本节点待提交集合，不立即修改共享 Context。
- 脚本成功结束后，平台一次性将待提交集合写入 Context。
- 脚本异常、超时、被中断或任一校验失败时，待提交集合全部丢弃。
- print() 只进入执行期间的临时观测日志，不会写入 Run-Time、Context 或 outputs。

#### 用户代码示例

```python
import random
import time

time_str = time.strftime("%Y%m%d%H%M%S")
letters = [chr(random.randint(65, 90)) for _ in range(3)]
currtime = time_str + "".join(letters)

set_val("currtime_1", currtime)
set_val("currtime_2", currtime)

review = get_val("review_result")
if review is not None:
    set_val("review_status", review["status"])
```

#### 成功输出示例

```json
{
  "currtime_1": "20260724153022ABC",
  "currtime_2": "20260724153022ABC",
  "review_status": "PASS"
}
```

以上对象是本次 SCRIPT 执行成功后写入 Context 的变量集合，不属于 Design-Time 节点定义。

## 3. HTTP

### 3.1 Design-Time

Design-Time 描述 HTTP 节点的持久化配置：接口模板、认证 Header、网络策略、执行约束和输出声明。它不保存某次运行解析后的 Context 值、实际请求、实际响应、状态、日志或错误。

#### Design-Time 示例

```json
{
  "id": "N4f7cB9mQ2xK8sL1pR6tV",
  "type": "HTTP",
  "name": "查询 CI 详情",
  "description": "根据设备名称查询 CMDB",
  "request": {
    "method": "POST",
    "url": "https://cmdb.example.com/api/ci/{{ ctx.ci_name }}",
    "headers": [
      {
        "key": "Content-Type",
        "value": "application/json"
      },
      {
        "key": "Authorization",
        "value": "Bearer {{ context.api_token }}"
      }
    ],
    "params": [
      {
        "key": "scope",
        "value": "{{ ctx.scope }}"
      }
    ],
    "body": {
      "type": "raw",
      "content": {
        "name": "{{ ctx.ci_name }}",
        "timeZone": "{{ context.time_zone }}"
      }
    }
  },
  "network": {
    "proxy": {
      "mode": "CUSTOM",
      "url": "http://proxy.example.com:8080",
      "username": "proxy-user",
      "password": "proxy-password"
    },
    "verify_ssl": true
  },
  "execution": {
    "timeout_ms": 30000,
    "max_attempts": 3,
    "delay_ms": 1000
  },
  "outputs": [
    {
      "name": "sent_ci_name",
      "type": "string",
      "path": "$.request.body.name"
    },
    {
      "name": "ci_id",
      "type": "string",
      "path": "$.response.body.id"
    },
    {
      "name": "ci_detail",
      "type": "object",
      "path": "$.response.body"
    }
  ]
}
```

#### 与 Run-Time 的字段边界

| Design-Time               | Run-Time                | 边界                                                              |
| ------------------------- | ----------------------- | ----------------------------------------------------------------- |
| id                        | node_id                 | Run-Time 只引用节点 ID，不修改 ID                                 |
| type                      | type                    | Run-Time 复制 HTTP 类型用于识别记录                               |
| name、description         | 无对应业务字段          | 只用于定义态展示，不作为请求或响应数据                            |
| request                   | attempts[].request      | 前者保存模板、常量和 Context 引用；后者保存解析后实际发送的请求   |
| network                   | attempts[].network      | 前者保存期望的 Proxy/SSL 配置；后者保存本次实际使用的完整网络配置 |
| execution                 | attempts                | 前者声明超时、重试上限和间隔；后者记录实际发生的请求尝试          |
| outputs 数组              | attempts[].outputs 对象 | 前者声明 name/type/path；后者保存提取并成功提交的 name/value      |
| 无 Design-Time inputs     | attempts[].inputs       | Run-Time 只记录本次请求实际引用的 Context 变量和值                |
| 无 Design-Time response   | attempts[].response     | 响应只能由实际 HTTP 请求产生                                      |
| 无 Design-Time 状态和错误 | status、error           | 只由执行过程产生                                                  |
| 无 Design-Time 日志       | 无 Run-Time 字段        | 日志只作为执行期间的临时观测数据                                  |

#### 参数列表

| 字段        | 类型   | 取值               | 示例                                                                        | 含义                                              |
| ----------- | ------ | ------------------ | --------------------------------------------------------------------------- | ------------------------------------------------- |
| id          | string | 21 位 NanoID       | N4f7cB9mQ2xK8sL1pR6tV                                                       | 节点在 Workflow 中的唯一标识                      |
| type        | string | HTTP               | HTTP                                                                        | 节点类型为 HTTP 请求                              |
| name        | string | 用户自定义         | 查询 CI 详情                                                                | 画布和日志中显示的节点名称                        |
| description | string | 用户自定义，可为空 | 根据设备名称查询 CMDB                                                       | 节点业务用途说明                                  |
| request     | object | 必填               | {"method":"POST","url":"https://cmdb.example.com/api/ci/{{ ctx.ci_name }}"} | HTTP 请求定义                                     |
| network     | object | 必填               | {"proxy":{"mode":"CUSTOM"},"verify_ssl":true}                               | Proxy 和 SSL 验证配置                             |
| execution   | object | 必填               | {"timeout_ms":30000,"max_attempts":3,"delay_ms":1000}                       | 超时和重试参数                                    |
| outputs     | array  | 可为空，默认 []    | [{"name":"ci_id","type":"string","path":"$.response.body.id"}]              | 从 request/response 提取并写入 Context 的输出声明 |

#### request 参数

| 字段    | 类型   | 取值                                         | 示例                                                  | 含义                        |
| ------- | ------ | -------------------------------------------- | ----------------------------------------------------- | --------------------------- |
| method  | string | GET、POST、PUT、PATCH、DELETE、HEAD、OPTIONS | POST                                                  | HTTP 请求方法               |
| url     | string | HTTP 或 HTTPS URL                            | https://cmdb.example.com/api/ci/{{ ctx.ci_name }}     | 请求地址，支持 Context 引用 |
| headers | array  | 可为空，默认 []                              | [{"key":"Content-Type","value":"application/json"}]   | 请求 Header 列表            |
| params  | array  | 可为空，默认 []                              | [{"key":"scope","value":"{{ ctx.scope }}"}]           | Query 参数列表              |
| body    | object | 必填                                         | {"type":"raw","content":{"name":"{{ ctx.ci_name }}"}} | 请求 Body 定义              |

协议规则：

- HTTP 节点同时支持 http:// 和 https:// 请求地址。
- request.url 只允许 http 和 https 协议，不接受其他 URL scheme。
- HTTP 与 HTTPS 使用相同的 Context 引用、请求参数、输出提取、Proxy 和重试契约。
- verify_ssl 只对 https:// 请求生效；http:// 请求忽略该开关。

#### headers/params 参数

headers 和 params 使用相同的键值结构：

| 字段  | 类型       | 取值         | 示例             | 含义                                          |
| ----- | ---------- | ------------ | ---------------- | --------------------------------------------- |
| key   | string     | 非空字符串   | Content-Type     | Header 名或 Query 参数名，不支持 Context 引用 |
| value | JSON value | 合法 JSON 值 | application/json | Header 值或 Query 参数值，支持 Context 引用   |

headers 和 params 使用数组而不是对象，以保留配置顺序，并允许协议需要时出现同名字段。

#### body 参数

| 字段    | 类型       | 取值                                          | 示例                         | 含义                         |
| ------- | ---------- | --------------------------------------------- | ---------------------------- | ---------------------------- |
| type    | string     | none、raw、form_data、form_urlencoded、binary | raw                          | Body 类型                    |
| content | JSON value | 根据 type 决定                                | {"name":"{{ ctx.ci_name }}"} | Body 内容，支持 Context 引用 |

| body.type       | content                                 |
| --------------- | --------------------------------------- |
| none            | null                                    |
| raw             | 字符串、对象、数组或其他 JSON 值        |
| form_data       | key/value 数组，value 支持 Context 引用 |
| form_urlencoded | key/value 数组，value 支持 Context 引用 |
| binary          | 二进制来源结构尚未定义，后续单独确认    |

#### form_data/form_urlencoded content 参数

| 字段  | 类型       | 取值         | 示例              | 含义                            |
| ----- | ---------- | ------------ | ----------------- | ------------------------------- |
| key   | string     | 非空字符串   | name              | 表单字段名，不支持 Context 引用 |
| value | JSON value | 合法 JSON 值 | {{ ctx.ci_name }} | 表单字段值，支持 Context 引用   |

#### network 参数

```json
{
  "proxy": {
    "mode": "SYSTEM",
    "url": null,
    "username": null,
    "password": null
  },
  "verify_ssl": true
}
```

| 字段       | 类型    | 取值                  | 示例                                                    | 含义                        |
| ---------- | ------- | --------------------- | ------------------------------------------------------- | --------------------------- |
| proxy      | object  | 必填                  | {"mode":"CUSTOM","url":"http://proxy.example.com:8080"} | Proxy 配置                  |
| verify_ssl | boolean | true/false，默认 true | true                                                    | 是否验证目标服务的 SSL 证书 |

#### proxy 参数

| 字段     | 类型        | 取值                                | 示例                          | 含义                           |
| -------- | ----------- | ----------------------------------- | ----------------------------- | ------------------------------ |
| mode     | string      | SYSTEM、DIRECT、CUSTOM，默认 SYSTEM | CUSTOM                        | Proxy 模式                     |
| url      | string/null | CUSTOM 时必填                       | http://proxy.example.com:8080 | 自定义代理地址                 |
| username | string/null | CUSTOM 时可选                       | proxy-user                    | 自定义代理用户名，允许直接保存 |
| password | string/null | CUSTOM 时可选                       | proxy-password                | 自定义代理密码，允许直接保存   |

| mode   | 行为                                                                 |
| ------ | -------------------------------------------------------------------- |
| SYSTEM | 使用运行进程的系统代理环境，包括 HTTP_PROXY、HTTPS_PROXY 和 NO_PROXY |
| DIRECT | 禁用系统代理，直接连接目标地址                                       |
| CUSTOM | 只使用本节点配置的 proxy.url，不读取系统代理                         |

网络规则：

- 不根据公网 IP、内网 IP、域名或请求失败情况自动切换 Proxy 模式。
- SYSTEM 和 DIRECT 模式下，proxy.url、proxy.username、proxy.password 必须为 null。
- CUSTOM 模式下，proxy.url 必须是合法代理地址；username 和 password 可以为空。
- CUSTOM 代理连接失败时，不自动回退到 SYSTEM 或 DIRECT。
- verify_ssl 与 Proxy 模式相互独立。
- https:// 请求中，verify_ssl 为 true 时验证目标服务 SSL 证书；为 false 时关闭目标服务 SSL 证书验证。
- http:// 请求不使用 SSL，运行时忽略 verify_ssl，但保留 Design-Time 配置值。
- verify_ssl 为 false 时不改变 Proxy 选择。
- verify_ssl 为 false 时，界面持续显示非阻断式安全提示，不阻止保存或运行。

#### execution 参数

| 字段         | 类型 | 取值     | 示例  | 含义                             |
| ------------ | ---- | -------- | ----- | -------------------------------- |
| timeout_ms   | int  | 大于 0   | 30000 | 单次 HTTP 请求超时时间，单位毫秒 |
| max_attempts | int  | 0~10     | 3     | 最大重试次数，不包含首次请求     |
| delay_ms     | int  | 0~600000 | 1000  | 两次重试之间的固定间隔，单位毫秒 |

max_attempts 和 delay_ms 的语义与 SCRIPT 节点一致。

#### outputs 参数

| 字段 | 类型   | 取值                                                  | 示例               | 含义                                           |
| ---- | ------ | ----------------------------------------------------- | ------------------ | ---------------------------------------------- |
| name | string | 合法变量名，且在本节点内唯一                          | ci_id              | 成功后写入 Context 的变量名                    |
| type | string | string、number、integer、boolean、object、array、null | string             | 输出变量声明类型                               |
| path | string | 标准 JSONPath                                         | $.response.body.id | 从标准 request/response 提取根对象中读取变量值 |

path 必须以 $.request 或 $.response 开头，不定义隐式 Body 路径或自定义 JSONPath 别名。

#### 敏感 Header

- 不建设统一凭据管理，HTTP 节点不定义 credential_id。
- 目标 API 的认证信息统一通过 request.headers 配置。
- CUSTOM Proxy 的认证信息只通过 network.proxy.username 和 network.proxy.password 配置。
- 直接填写 Authorization、Proxy-Authorization、Cookie、Set-Cookie、X-API-Key、API-Key 等敏感 Header 时，界面显示非阻断式警告。
- 警告只用于提示，不弹出确认框，不阻止保存或运行。
- 敏感 Header 在 Run-Time、日志和界面中均展示原值，不进行脱敏。
- Workflow 导出和运行记录持久化可以包含明文敏感信息。

### 3.2 Run-Time

Run-Time 保存某次 Workflow Run 中 HTTP 节点实际发生的执行事实：引用输入、网络配置、最终请求、响应、重试、输出、状态和错误。它不保存可编辑模板，也不保存日志或日志引用，不反向修改 Design-Time。

#### Run-Time 示例

```json
{
  "run_id": "workflow-run-001",
  "node_run_id": "node-run-http-001",
  "node_id": "N4f7cB9mQ2xK8sL1pR6tV",
  "type": "HTTP",
  "status": "SUCCESS",
  "started_at": "2026-07-24 23:11:50",
  "finished_at": "2026-07-24 23:11:51",
  "duration_ms": 1000,
  "attempts": [
    {
      "attempt": 1,
      "status": "SUCCESS",
      "started_at": "2026-07-24 23:11:50",
      "finished_at": "2026-07-24 23:11:51",
      "duration_ms": 1000,
      "inputs": {
        "ci_name": "SWITCH_1.100.2.142",
        "api_token": "demo-token",
        "scope": "USER_SCOPE",
        "time_zone": "Asia/Shanghai"
      },
      "network": {
        "proxy": {
          "mode": "CUSTOM",
          "url": "http://proxy.example.com:8080",
          "username": "proxy-user",
          "password": "proxy-password"
        },
        "verify_ssl": true
      },
      "request": {
        "method": "POST",
        "url": "https://cmdb.example.com/api/ci/SWITCH_1.100.2.142",
        "headers": [
          {
            "key": "Content-Type",
            "value": "application/json"
          },
          {
            "key": "Authorization",
            "value": "Bearer demo-token"
          }
        ],
        "params": [
          {
            "key": "scope",
            "value": "USER_SCOPE"
          }
        ],
        "body": {
          "name": "SWITCH_1.100.2.142",
          "timeZone": "Asia/Shanghai"
        }
      },
      "response": {
        "status_code": 200,
        "headers": {
          "content-type": "application/json"
        },
        "body": {
          "id": "ci-001",
          "name": "SWITCH_1.100.2.142"
        }
      },
      "outputs": {
        "sent_ci_name": "SWITCH_1.100.2.142",
        "ci_id": "ci-001",
        "ci_detail": {
          "id": "ci-001",
          "name": "SWITCH_1.100.2.142"
        }
      },
      "error": null
    }
  ]
}
```

#### 参数列表

| 字段        | 类型        | 取值                                                           | 示例                               | 含义                                       |
| ----------- | ----------- | -------------------------------------------------------------- | ---------------------------------- | ------------------------------------------ |
| run_id      | string      | Workflow Run ID                                                | workflow-run-001                   | 本次 Workflow Run 的唯一标识               |
| node_run_id | string      | NodeRun ID                                                     | node-run-http-001                  | 本次 HTTP 节点运行记录的唯一标识           |
| node_id     | string      | 21 位 NanoID                                                   | N4f7cB9mQ2xK8sL1pR6tV              | Design-Time 节点 ID                        |
| type        | string      | HTTP                                                           | HTTP                               | 节点类型                                   |
| status      | string      | PENDING、RUNNING、SUCCESS、FAILED、TIMEOUT、CANCELLED、SKIPPED | SUCCESS                            | 节点最终状态                               |
| started_at  | string      | YYYY-MM-DD HH:mm:ss                                            | 2026-07-24 23:11:50                | 节点首次开始时间，例如 2026-07-24 23:11:50 |
| finished_at | string/null | YYYY-MM-DD HH:mm:ss 或 null                                    | 2026-07-24 23:11:51                | 节点最终结束时间；尚未结束时为 null        |
| duration_ms | int/null    | 大于等于 0 或 null                                             | 1000                               | 节点总耗时，单位毫秒；尚未结束时为 null    |
| attempts    | array       | 可为空                                                         | [{"attempt":1,"status":"SUCCESS"}] | 每次实际请求尝试，按执行顺序排列           |

#### attempts 参数

| 字段        | 类型        | 取值                                         | 示例                                                      | 含义                                     |
| ----------- | ----------- | -------------------------------------------- | --------------------------------------------------------- | ---------------------------------------- |
| attempt     | int         | 从 1 开始                                    | 1                                                         | 当前第几次请求                           |
| status      | string      | RUNNING、SUCCESS、FAILED、TIMEOUT、CANCELLED | SUCCESS                                                   | 本次请求尝试状态                         |
| started_at  | string      | YYYY-MM-DD HH:mm:ss                          | 2026-07-24 23:11:50                                       | 本次请求尝试开始时间                     |
| finished_at | string/null | YYYY-MM-DD HH:mm:ss 或 null                  | 2026-07-24 23:11:51                                       | 本次请求尝试结束时间                     |
| duration_ms | int/null    | 大于等于 0 或 null                           | 1000                                                      | 本次请求尝试耗时，单位毫秒               |
| inputs      | object      | 变量名到 JSON 值的映射                       | {"ci_name":"SWITCH_1.100.2.142"}                          | 本次请求实际引用的 Context 变量及其值    |
| network     | object      | network 对象                                 | {"proxy":{"mode":"CUSTOM"},"verify_ssl":true}             | 本次请求实际使用的 Proxy 和 SSL 验证配置 |
| request     | object/null | request 对象或 null                          | {"method":"POST","url":"https://cmdb.example.com/api/ci"} | 完成 Context 解析后实际发送的请求        |
| response    | object/null | response 对象或 null                         | {"status_code":200,"headers":{},"body":{"id":"ci-001"}}   | 实际收到的标准 HTTP 响应                 |
| outputs     | object      | 变量名到 JSON 值的映射，默认 {}              | {"ci_id":"ci-001"}                                        | 本次尝试成功后提交到 Context 的变量      |
| error       | object/null | error 对象或 null                            | null                                                      | 本次尝试错误；成功时为 null              |

#### network 参数

| 字段       | 类型    | 取值       | 示例                                                    | 含义                      |
| ---------- | ------- | ---------- | ------------------------------------------------------- | ------------------------- |
| proxy      | object  | proxy 对象 | {"mode":"CUSTOM","url":"http://proxy.example.com:8080"} | 本次实际使用的 Proxy 配置 |
| verify_ssl | boolean | true/false | true                                                    | 本次请求是否验证 SSL 证书 |

#### proxy 参数

| 字段     | 类型        | 取值                   | 示例                          | 含义                             |
| -------- | ----------- | ---------------------- | ----------------------------- | -------------------------------- |
| mode     | string      | SYSTEM、DIRECT、CUSTOM | CUSTOM                        | 本次实际使用的 Proxy 模式        |
| url      | string/null | 代理 URL 或 null       | http://proxy.example.com:8080 | 本次实际使用的自定义代理地址     |
| username | string/null | 用户名或 null          | proxy-user                    | 本次实际使用的代理用户名，不脱敏 |
| password | string/null | 密码或 null            | proxy-password                | 本次实际使用的代理密码，不脱敏   |

#### request 参数

| 字段    | 类型       | 取值                                         | 示例                                                | 含义                             |
| ------- | ---------- | -------------------------------------------- | --------------------------------------------------- | -------------------------------- |
| method  | string     | GET、POST、PUT、PATCH、DELETE、HEAD、OPTIONS | POST                                                | 实际发送的 HTTP 方法             |
| url     | string     | 完整 HTTP/HTTPS URL                          | https://cmdb.example.com/api/ci/SWITCH_1.100.2.142  | Context 引用解析后的完整请求地址 |
| headers | array      | key/value 数组                               | [{"key":"Content-Type","value":"application/json"}] | 实际发送的 Header，敏感值不脱敏  |
| params  | array      | key/value 数组                               | [{"key":"scope","value":"USER_SCOPE"}]              | Context 引用解析后的 Query 参数  |
| body    | JSON value | 合法 JSON 值                                 | {"name":"SWITCH_1.100.2.142"}                       | Context 引用解析后的请求 Body    |

#### request.headers/request.params 参数

| 字段  | 类型       | 取值         | 示例         | 含义                                |
| ----- | ---------- | ------------ | ------------ | ----------------------------------- |
| key   | string     | 非空字符串   | Content-Type | 实际发送的 Header 名或 Query 参数名 |
| value | JSON value | 合法 JSON 值 | USER_SCOPE   | Context 引用解析后的实际值          |

#### response 参数

| 字段        | 类型       | 取值                 | 示例                                        | 含义                                                   |
| ----------- | ---------- | -------------------- | ------------------------------------------- | ------------------------------------------------------ |
| status_code | int        | 100~599              | 200                                         | HTTP 响应状态码                                        |
| headers     | object     | Header 名到值的映射  | {"content-type":"application/json"}         | 完整响应 Header                                        |
| body        | JSON value | 合法 JSON 值或字符串 | {"id":"ci-001","name":"SWITCH_1.100.2.142"} | JSON 解析后的响应 Body，或无法解析为 JSON 时的原始文本 |

#### error 参数

| 字段    | 类型        | 取值                    | 示例          | 含义                         |
| ------- | ----------- | ----------------------- | ------------- | ---------------------------- |
| code    | string      | 稳定错误码              | HTTP_TIMEOUT  | 机器可读错误码               |
| message | string      | 非空字符串              | HTTP 请求超时 | 面向用户的错误说明           |
| details | object/null | 结构化 JSON 对象或 null | null          | 可选诊断信息，不写入 Context |

#### Run-Time 规则

输入与请求：

- inputs 只记录 request.url、request.headers[].value、request.params[].value 和 request.body.content 实际引用过的 Context 变量。
- Context 引用或嵌套路径解析失败时，本次尝试失败，request 和 response 都为 null。
- 请求已完成解析但未收到响应时，保留 request，response 为 null。
- request 记录实际发送值；敏感 Header 不脱敏。
- network 记录完整 Proxy 配置；proxy.username 和 proxy.password 不脱敏。

响应与输出：

- 只有 HTTP 状态码 200~299 表示本次请求成功。
- 1xx、3xx、4xx 和 5xx 响应均表示本次请求失败，但必须保留 response。
- request 和 response 是 HTTP 请求与响应在 Run-Time 中的唯一标准记录。
- Run-Time 不定义额外的原始请求、原始响应引用字段，也不定义独立的原始 Body 字段。
- 日志中的 request 和 response 由 Run-Time 的结构化 request 和 response 生成，不单独持久化另一份原始请求或响应。
- JSON 响应解析为 response.body 后，不保证保留原始空格、换行、字段顺序或数字文本格式；非 JSON 响应以字符串保存在 response.body。
- 收到成功响应后，再按照 Design-Time outputs.path 提取声明输出。
- 输出提取失败时，本次尝试失败，保留 request 和 response，但 outputs 为 {}。
- 只有成功尝试的 outputs 才批量写入 Context。
- 请求失败、超时、中断或输出处理失败时，outputs 必须为 {}。

重试：

- execution.max_attempts 表示最多重试次数，不包含首次请求。
- 自动重试只适用于 GET、HEAD、OPTIONS、PUT、DELETE 幂等方法。
- POST 和 PATCH 不自动重试，即使 max_attempts 大于 0。
- 幂等方法仅在连接失败、请求超时、HTTP 408、HTTP 429、HTTP 500、HTTP 502、HTTP 503、HTTP 504 时自动重试。
- 其他 HTTP 状态、Context 引用错误、SSL 验证错误、配置错误和输出提取错误不自动重试。
- 每次实际请求都追加一个 AttemptRun，不得覆盖之前的请求、响应或错误。
- 只有最终成功的尝试才更新 Context；全部失败时 Context 保持节点执行前状态。
- 中间失败但后续成功时，NodeRun.status 最终为 SUCCESS。

### 3.3 Input & Output Protocol

#### Context 输入

以下 HTTP 配置字段支持第一章定义的统一 Context 引用格式：

```text
request.url
request.headers[].value
request.params[].value
request.body.content
```

request.headers[].key 和 request.params[].key 不支持 Context 引用。

引用规则：

- {{ context.variable_name }} 与 {{ ctx.variable_name }} 等价。
- {{ ctx.ci_name }} 与 {{ctx.ci_name}} 等价，双花括号内侧的首尾空白不影响解析。
- 支持对象字段和数组下标访问。
- 整个字段只有一个引用时保留 Context 原始 JSON 类型。
- 引用嵌入文本时转换为文本；对象和数组转换为紧凑 JSON。
- 变量或嵌套路径不存在时，HTTP 节点在发出请求前失败。
- {{ variable_name }} 保持普通文本，不作为 Context 引用。

#### request/response 与输出提取

outputs.path 使用标准 JSONPath，并从以下统一根对象中读取：

```json
{
  "request": {
    "method": "POST",
    "url": "https://cmdb.example.com/api/ci",
    "headers": [],
    "params": [],
    "body": {
      "name": "SWITCH_1.100.2.142"
    }
  },
  "response": {
    "status_code": 200,
    "headers": {
      "content-type": "application/json"
    },
    "body": {
      "id": "ci-001"
    }
  }
}
```

| path                   | 提取内容                 |
| ---------------------- | ------------------------ |
| $.request.method       | 实际请求方法             |
| $.request.url          | Context 解析后的最终 URL |
| $.request.body.name    | 实际请求 Body 中的 name  |
| $.response.status_code | HTTP 状态码              |
| $.response.headers     | 完整响应 Header          |
| $.response.body        | 完整响应 Body            |
| $.response.body.id     | JSON 响应 Body 中的 id   |

$.response.body.id 与 $.response.id 不等价。平台不会在字段不存在时自动转入 response.body 查找。

只有 HTTP 节点最终成功，声明的 outputs 才写入 Context。JSONPath 找不到值时，本次输出提取失败，outputs 整体不提交。

## 4. LLM

### 4.1 Design-Time

Design-Time 描述 LLM 节点使用的模型引用、Prompt、生成参数、执行约束和原始文本输出声明。不保存 API Key、Base URL、协议、Proxy、SSL、模型默认 Body 或某次运行的实际 Prompt。

#### Design-Time 示例

~~~json
{
  "id": "L1StGXR8_Z5jdHi6B-myT",
  "type": "LLM",
  "name": "中文合规审核",
  "description": "判断内容是否符合中文要求",
  "model": {
    "provider_id": "provider-deepseek",
    "model_name": "deepseek-v4-pro"
  },
  "prompt": {
    "system": "你是中文合规审核员，只输出审核结论文本。",
    "user": "请审核以下内容：{{ ctx.conversation }}"
  },
  "generation": {
    "stream": false,
    "parameters": {
      "thinking": {
        "type": "disabled"
      },
      "temperature": 0,
      "top_p": 0.8,
      "max_tokens": 1024
    }
  },
  "execution": {
    "timeout_ms": 120000,
    "max_attempts": 2,
    "delay_ms": 1000
  },
  "outputs": [
    {
      "name": "llm_text",
      "type": "string"
    }
  ]
}
~~~

#### 与 Run-Time 的字段边界

| Design-Time | Run-Time | 边界 |
| --- | --- | --- |
| id | node_id | Run-Time 只引用节点 ID，不修改 ID |
| type | type | Run-Time 复制 LLM 类型用于识别记录 |
| name、description | 无对应业务字段 | 只用于定义态展示，不作为模型输出 |
| model | 实际请求使用的模型信息 | 前者只保存供应商和模型引用，后者记录本次调用实际使用的模型 |
| prompt.system、prompt.user | 实际解析后的 Prompt | 前者保存模板和 Context 引用，后者是本次调用使用的文本 |
| generation.parameters | 实际合并后的模型参数 | 前者保存节点级参数，后者是合并后的请求参数 |
| execution | attempts | 前者声明超时和重试约束，后者记录实际尝试 |
| outputs 数组 | 实际原始文本输出 | 前者最多声明一个 string 输出，后者保存实际模型文本 |

#### 参数列表

| 字段 | 类型 | 取值 | 示例 | 含义 |
| --- | --- | --- | --- | --- |
| id | string | 21 位 NanoID | L1StGXR8_Z5jdHi6B-myT | 节点在 Workflow 中的唯一标识 |
| type | string | LLM | LLM | 节点类型 |
| name | string | 用户自定义 | 中文合规审核 | 画布和日志中显示的节点名称 |
| description | string | 用户自定义，可为空 | 判断内容是否符合中文要求 | 节点业务用途说明 |
| model | object | 必填 | {"provider_id":"provider-deepseek","model_name":"deepseek-v4-pro"} | 模型引用 |
| prompt | object | 必填 | {"system":"...","user":"..."} | Prompt 定义 |
| generation | object | 必填 | {"stream":false,"parameters":{"temperature":0}} | 流式开关和生成参数 |
| execution | object | 必填 | {"timeout_ms":120000,"max_attempts":2,"delay_ms":1000} | 执行约束 |
| outputs | array | 可为空，最多一个 | [{"name":"llm_text","type":"string"}] | 原始文本输出声明 |

#### model 参数

| 字段 | 类型 | 取值 | 示例 | 含义 |
| --- | --- | --- | --- | --- |
| provider_id | string | 模型管理中的供应商 ID | provider-deepseek | 引用模型供应商 |
| model_name | string | 供应商已配置模型名 | deepseek-v4-pro | 引用具体模型 |

LLM 节点不复制模型管理中的 API Key、Base URL、协议、Proxy、SSL、模型默认 Body、上下文窗口或最大输出能力。

#### prompt 参数

| 字段 | 类型 | 取值 | 示例 | 含义 |
| --- | --- | --- | --- | --- |
| system | string | 可为空 | 你是中文合规审核员。 | 系统提示词模板 |
| user | string | 非空 | 请审核：{{ ctx.conversation }} | 用户提示词模板 |

Prompt 当前只支持 system 和 user 两个字段，不支持 messages[]、assistant 示例消息或其他角色。

#### generation 参数

| 字段 | 类型 | 取值 | 示例 | 含义 |
| --- | --- | --- | --- | --- |
| stream | boolean | true/false，默认 false | false | 是否启用流式输出 |
| parameters | object | 合法 JSON object | {"temperature":0,"max_tokens":1024} | 节点高级参数，原样参与请求合并 |

parameters 规则：

- parameters 可以包含供应商特有字段，以保持模型兼容性。
- stream 单独保存，不重复放入 parameters。
- 不对白名单之外的参数做强制拒绝。
- response_format 等模型特有参数可以原样填写，但平台不解析结构化结果。
- 请求合并顺序为：平台基础请求 < 模型默认 Body < 节点 parameters。

#### execution 参数

| 字段 | 类型 | 取值 | 示例 | 含义 |
| --- | --- | --- | --- | --- |
| timeout_ms | int | 大于 0 | 120000 | 单次模型请求超时时间，单位毫秒 |
| max_attempts | int | 0~10 | 2 | 最大重试次数，不包含首次请求 |
| delay_ms | int | 0~600000 | 1000 | 两次重试之间的固定间隔，单位毫秒 |

#### outputs 参数

| 字段 | 类型 | 取值 | 示例 | 含义 |
| --- | --- | --- | --- | --- |
| name | string | 合法变量名，且本节点最多一项 | llm_text | 写入 Context 的原始文本变量名 |
| type | string | 固定 string | string | 原始模型文本类型 |

LLM 输出不设置 path，不声明 object、array 或 JSON Schema。用户需要结构化字段时，应由下游 SCRIPT 节点解析原始文本。

### 4.2 Run-Time

LLM Run-Time 的完整请求、响应、重试记录、错误码和 Token 统计结构尚未讨论，本节暂不补充未确认的运行字段。

已确认的输出边界：

- 模型最终文本作为唯一模型输出数据。
- 平台不自动解析 JSON，不生成 structured、reasoning 或 json 字段。
- 流式输出完成后再形成完整文本结果。
- 未声明 outputs 时，模型结果不写入 Context。

### 4.3 Input & Output Protocol

#### Context 输入

以下 Prompt 字段支持第一章定义的统一 Context 引用格式：

~~~text
prompt.system
prompt.user
~~~

规则：

- {{ context.variable_name }} 与 {{ ctx.variable_name }} 等价。
- {{ ctx.ci_name }} 与 {{ctx.ci_name}} 等价，双花括号内侧的首尾空白不影响解析。
- 支持对象字段和数组下标访问。
- 变量或嵌套路径不存在时，LLM 节点在模型请求前失败。
- {{ variable_name }} 保持普通文本，不作为 Context 引用。

#### 输出协议

LLM 输出是模型最终返回的原始文本字符串：

~~~text
模型返回的完整文本，包括 Markdown、JSON 文本、换行和前后空白
~~~

- 不执行 JSON 解析。
- 不执行 Schema 校验。
- 不提取 reasoning、status 或其他子字段。
- Design-Time 声明 outputs 后，完整文本作为该变量的 string 值写入 Context。
- 下游需要结构化字段时，由 SCRIPT 使用 get_val 和 json.loads 自行处理。

输出值类型校验和类型不匹配时的处理方式尚未确认，后续讨论后补充。
