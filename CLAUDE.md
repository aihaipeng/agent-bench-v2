# CLAUDE.md

开始任何任务前必须完整阅读根目录 `AGENTS.md`。T13.2 工具模板化与新版 Workflow Studio 的当前事实、已确认业务规则、逐步验证记录和未确认项统一记录在 `PLAN.md`；两者优先于历史文档和 Git 历史。

## 当前边界

- 旧 Script/Agent 工具协议、旧固定 Workflow/Run 页面/API/执行链已不兼容删除，不得恢复。
- 一级“工具模板”统一管理大写 `HTTP / AGENT / LLM / SCRIPT`，目录包为 `{id}/manifest.json + definition.json + 可选 main.py`。
- 四类模板支持安全 ZIP、独立测试、SSE、严格 JSON response、超时和中断；Python 类型统一使用顶层 `inputs / config / response`。
- 模板深拷贝到画布后没有来源引用；画布发布始终生成独立新模板 ID。
- 新版 Workflow Studio 仍是前端会话草稿。Workflow 持久化、DAG 执行和 Run 追溯协议未确认前不得自行补全。
- 凭据仓储与绑定属于 `PLAN.md` 待优化项。导出不会自动清理 `config` 或 Python 代码中的全部秘密。
- 前端只支持桌面浏览器，不新增移动端适配或回归。

## 常用命令

```bash
uv sync
npm ci
npm run build
uv run python run.py
uv run pytest
```

本机服务默认绑定 `http://127.0.0.1:8010`。API Key 不得写入代码、测试、文档、模板包或提交内容。
