# AGENTS.md

## 项目概述

Agent Bench v2 当前是本机使用的 Web 测试集管理工具，用于管理 `inputs/` 目录下的 Excel 测试集、浏览 sheet 用例、维护测试集/工具的元数据、配置当前测试集，以及创建并联调测试工具（Script / Agent）。

## 常用命令

```bash
# 安装依赖
uv sync

# 启动本机 Web 服务
uv run python run.py

# 运行测试
uv run pytest
```

默认服务地址是 `http://127.0.0.1:8010`。

## 架构

```text
run.py
  └── web/app.py
        ├── web/routes_excel.py      # 测试集上传、列表、sheet、刷新、删除
        ├── web/routes_testcases.py  # 用例分页浏览
        ├── web/routes_files.py      # 打开本机文件目录
        ├── web/routes_tools.py      # 工具 CRUD、Agent 联调
        └── web/routes_config.py     # 当前测试集配置

web/files.py                          # 文件路径安全校验（防止路径穿越）
storage/excel.py                      # 读取 case_id + question 格式的 Excel
web/static/                           # 单页前端
```

## Excel 格式

只支持固定两列输入：

```text
case_id | question
```

第一行可以是表头。第三列及之后允许存在历史结果或人工备注，但 Web 读取用例时只读取前两列。

## 配置

`config.yaml` 只保留 Web 当前选择：

```yaml
excel:
  input_path: inputs/testcases.xlsx
  sheet_name: Sheet1
```

## 约束

- Web 服务只面向本机使用，入口绑定 `127.0.0.1`。
- 文件操作只能发生在项目 `inputs/` 目录内。
- 删除或上传测试集时要保持当前配置一致。
