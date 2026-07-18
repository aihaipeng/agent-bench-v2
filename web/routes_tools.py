"""测试工具管理 API 路由。"""

import json
import time
import traceback
import builtins
from datetime import datetime
from io import StringIO
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from rich.console import Console

from web.agent_runtime import (
    AgentTemplateError,
    migrate_legacy_agent_template,
    run_agent_python,
)
from web.files import INPUTS_DIR

router = APIRouter(prefix="/api/tools", tags=["tools"])

TOOLS_FILE = INPUTS_DIR / ".tools.json"
TOOL_TYPES = {"script", "agent"}
AGENT_TEMPLATE_VERSION = 3
DEFAULT_AGENT_PYTHON_CODE = '''from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from rich import print

model = init_chat_model(
    model=${model},
    model_provider=${model_provider},
    api_key=${api_key},
    base_url=${base_url},
)

agent = create_agent(
    model=model,
    system_prompt=${system_prompt},
)

response = agent.invoke({
    "messages": [
        {"role": "user", "content": ${human_message}},
    ]
})

print(response)
'''
SAFE_BUILTINS = {
    name: getattr(builtins, name)
    for name in (
        "abs",
        "all",
        "any",
        "bool",
        "callable",
        "dict",
        "enumerate",
        "Exception",
        "filter",
        "float",
        "getattr",
        "hasattr",
        "int",
        "isinstance",
        "issubclass",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "object",
        "range",
        "repr",
        "reversed",
        "round",
        "RuntimeError",
        "set",
        "setattr",
        "slice",
        "sorted",
        "str",
        "sum",
        "super",
        "tuple",
        "TypeError",
        "type",
        "ValueError",
        "zip",
        "__build_class__",
    )
}


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _normalize_tool_type(tool_type: str) -> str:
    normalized = (tool_type or "").strip().lower()
    if normalized in {"python_script", "python script"}:
        normalized = "script"
    if normalized not in TOOL_TYPES:
        raise HTTPException(400, "工具类型仅支持 Script 和 Agent")
    return normalized


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def _new_output() -> tuple[StringIO, Console, Any]:
    """创建请求私有日志缓冲区，避免 redirect_stdout 导致并发串日志。"""
    output = StringIO()
    console = Console(file=output, force_terminal=False, color_system=None, width=140)

    def output_print(*values: Any, sep: str = " ", end: str = "\n", **_: Any) -> None:
        output.write(sep.join(str(value) for value in values) + end)

    return output, console, output_print


def _restricted_globals(output_print: Any, values: dict[str, Any] | None = None) -> dict[str, Any]:
    """提供受限执行命名空间；用于降低误操作风险，不作为强安全沙箱。"""
    result: dict[str, Any] = {
        "__builtins__": {**SAFE_BUILTINS, "print": output_print},
        "__name__": "__tool_runtime__",
        "print": output_print,
    }
    if values:
        result.update(values)
    return result


def _read_tools_file() -> dict:
    if not TOOLS_FILE.is_file():
        return {"tools": []}
    try:
        with open(TOOLS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"tools": []}
    if not isinstance(data, dict) or not isinstance(data.get("tools"), list):
        return {"tools": []}
    return data


def _save_tools_file(data: dict) -> None:
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOOLS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_tools() -> list[dict]:
    file_data = _read_tools_file()
    result: list[dict] = []
    migrated = False
    for raw in file_data.get("tools", []):
        if not isinstance(raw, dict):
            continue
        try:
            tool_type = _normalize_tool_type(str(raw.get("type", "")))
        except HTTPException:
            continue
        tool_id = _normalize_text(str(raw.get("id", "")))
        name = _normalize_text(str(raw.get("name", "")))
        if not tool_id or not name:
            continue
        script_code = str(raw.get("script_code") or "")
        if not script_code and tool_type == "script":
            script_code = str(raw.get("content") or "")
        prompt = str(raw.get("prompt") or "")
        if not prompt and tool_type == "agent":
            prompt = str(raw.get("content") or "")
        python_code = str(raw.get("python_code") or "")
        needs_review = bool(raw.get("needs_review", False))
        agent_template_version = raw.get("agent_template_version")
        if tool_type == "agent":
            if agent_template_version == 2 and python_code:
                python_code = migrate_legacy_agent_template(python_code)
            elif agent_template_version != AGENT_TEMPLATE_VERSION:
                python_code = DEFAULT_AGENT_PYTHON_CODE
            if not python_code:
                python_code = DEFAULT_AGENT_PYTHON_CODE
            if (
                raw.get("python_code") != python_code
                or agent_template_version != AGENT_TEMPLATE_VERSION
            ):
                raw["python_code"] = python_code
                raw["agent_template_version"] = AGENT_TEMPLATE_VERSION
                migrated = True
            needs_review = False
        human_message = raw.get("human_message")
        if human_message is None:
            human_message = "你好，请介绍一下自己。"
        result.append(
            {
                "id": tool_id,
                "type": tool_type,
                "name": name,
                "description": _normalize_text(raw.get("description")),
                "model_provider": _normalize_text(raw.get("model_provider")),
                "api_key": _normalize_text(raw.get("api_key") or raw.get("llm_api_key")),
                "base_url": _normalize_text(raw.get("base_url") or raw.get("llm_endpoint")),
                "model": _normalize_text(raw.get("model") or raw.get("llm_model")),
                "system_prompt": _normalize_text(raw.get("system_prompt") or prompt),
                "human_message": str(human_message),
                "python_code": python_code,
                "needs_review": needs_review,
                "agent_template_version": AGENT_TEMPLATE_VERSION,
                "script_code": script_code,
                "created_at": str(raw.get("created_at") or ""),
                "updated_at": str(raw.get("updated_at") or ""),
            }
        )
    if migrated:
        _save_tools_file(file_data)
    return result


def _save_tools(tools: list[dict]) -> None:
    _save_tools_file({"tools": tools})


def _find_tool(tools: list[dict], tool_id: str) -> dict:
    for tool in tools:
        if tool["id"] == tool_id:
            return tool
    raise HTTPException(404, f"工具不存在: {tool_id}")


def _ensure_unique_tool_name(tools: list[dict], name: str, exclude_id: str | None = None) -> None:
    """确保工具名称在工具列表内唯一。"""
    for tool in tools:
        if exclude_id and tool["id"] == exclude_id:
            continue
        if tool["name"] == name:
            raise HTTPException(400, "名称不可重复")


class ToolCreateRequest(BaseModel):
    """创建工具的请求体。"""

    type: str
    name: str
    description: str = ""


class ToolUpdateRequest(BaseModel):
    """更新工具的请求体。"""

    name: str
    description: str = ""
    model: str = ""
    model_provider: str = ""
    api_key: str = ""
    base_url: str = ""
    system_prompt: str = ""
    human_message: str = "你好，请介绍一下自己。"
    python_code: str = ""
    script_code: str = ""


class ToolMetadataUpdateRequest(BaseModel):
    """仅更新列表页支持内联编辑的工具元数据。"""

    name: str | None = None
    description: str | None = None


class AgentRunRequest(BaseModel):
    """使用编辑页当前参数运行 Agent Python 代码。"""

    model: str = ""
    model_provider: str = ""
    api_key: str = ""
    base_url: str = ""
    system_prompt: str = ""
    human_message: str = ""
    python_code: str = ""


class ScriptRunRequest(BaseModel):
    """运行 Script 工具时传入的请求体。"""

    script_code: str = ""


def _required_agent_values(body: ToolUpdateRequest | AgentRunRequest) -> dict[str, str]:
    return {
        "model": body.model,
        "model_provider": body.model_provider,
        "api_key": body.api_key,
        "base_url": body.base_url,
        "human_message": body.human_message,
    }


def _validate_required_agent_values(body: ToolUpdateRequest | AgentRunRequest) -> None:
    missing = [
        field
        for field, value in _required_agent_values(body).items()
        if not _normalize_text(value)
    ]
    if missing:
        raise HTTPException(400, f"Agent 必填参数不能为空: {', '.join(missing)}")


@router.get("")
def list_tools(
    tool_type: str | None = Query(None, alias="type"),
    q: str = "",
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
) -> JSONResponse:
    """列出测试工具，支持类型筛选、名称模糊匹配和排序。"""
    tools = _load_tools()
    if tool_type:
        normalized_type = _normalize_tool_type(tool_type)
        tools = [tool for tool in tools if tool["type"] == normalized_type]
    query = q.strip().lower()
    if query:
        tools = [tool for tool in tools if query in tool["name"].lower()]

    if sort_by not in {"name", "updated_at"}:
        raise HTTPException(400, "sort_by 仅支持 name 或 updated_at")
    reverse = sort_dir.lower() != "asc"
    tools.sort(key=lambda tool: tool.get(sort_by) or "", reverse=reverse)
    return JSONResponse({"tools": tools})


@router.post("")
def create_tool(body: ToolCreateRequest) -> JSONResponse:
    """新增一个测试工具。"""
    name = _normalize_text(body.name)
    if not name:
        raise HTTPException(400, "名称不能为空")
    tools = _load_tools()
    _ensure_unique_tool_name(tools, name)

    tool_type = _normalize_tool_type(body.type)
    now = _now_iso()
    tool = {
        "id": uuid4().hex,
        "type": tool_type,
        "name": name,
        "description": _normalize_text(body.description),
        # LLM 参数
        "model_provider": "",
        "api_key": "",
        "base_url": "",
        "model": "",
        "system_prompt": "",
        "human_message": "你好，请介绍一下自己。",
        "python_code": DEFAULT_AGENT_PYTHON_CODE if tool_type == "agent" else "",
        "needs_review": False,
        "agent_template_version": AGENT_TEMPLATE_VERSION,
        "script_code": "",
        "created_at": now,
        "updated_at": now,
    }
    tools.append(tool)
    _save_tools(tools)
    return JSONResponse({"tool": tool})


@router.get("/{tool_id}")
def get_tool(tool_id: str) -> JSONResponse:
    """查看一个测试工具。"""
    tool = _find_tool(_load_tools(), tool_id)
    return JSONResponse({"tool": tool})


@router.put("/{tool_id}")
def update_tool(tool_id: str, body: ToolUpdateRequest) -> JSONResponse:
    """修改一个测试工具。"""
    name = _normalize_text(body.name)
    if not name:
        raise HTTPException(400, "名称不能为空")

    tools = _load_tools()
    tool = _find_tool(tools, tool_id)
    _ensure_unique_tool_name(tools, name, exclude_id=tool_id)
    if tool["type"] == "agent":
        _validate_required_agent_values(body)
        if not body.python_code.strip():
            raise HTTPException(400, "Python 代码不能为空")
    tool["name"] = name
    tool["description"] = _normalize_text(body.description)
    tool["model"] = _normalize_text(body.model)
    tool["model_provider"] = _normalize_text(body.model_provider)
    tool["api_key"] = _normalize_text(body.api_key)
    tool["base_url"] = _normalize_text(body.base_url)
    tool["system_prompt"] = body.system_prompt or ""
    tool["human_message"] = body.human_message.strip()
    tool["python_code"] = body.python_code
    tool["needs_review"] = False
    tool["agent_template_version"] = AGENT_TEMPLATE_VERSION
    tool["script_code"] = body.script_code or ""
    for legacy_field in (
        "temperature",
        "extra_body",
        "max_tokens",
        "request_timeout",
        "prompt",
        "additional_components",
        "additional_components_enabled",
        "execution_mode",
    ):
        tool.pop(legacy_field, None)
    tool["updated_at"] = _now_iso()
    _save_tools(tools)
    return JSONResponse({"tool": tool})


@router.patch("/{tool_id}")
def update_tool_metadata(tool_id: str, body: ToolMetadataUpdateRequest) -> JSONResponse:
    """局部更新名称或说明，不覆盖 Agent/Script 的其他配置。"""
    if body.name is None and body.description is None:
        raise HTTPException(400, "至少需要提供名称或说明")
    tools = _load_tools()
    tool = _find_tool(tools, tool_id)
    if body.name is not None:
        name = _normalize_text(body.name)
        if not name:
            raise HTTPException(400, "名称不能为空")
        _ensure_unique_tool_name(tools, name, exclude_id=tool_id)
        tool["name"] = name
    if body.description is not None:
        tool["description"] = _normalize_text(body.description)
    tool["updated_at"] = _now_iso()
    _save_tools(tools)
    return JSONResponse({"tool": tool})


@router.post("/{tool_id}/test")
def test_agent(tool_id: str, body: AgentRunRequest) -> JSONResponse:
    """在独立子进程中编译并运行 Agent Python 代码。"""
    tool = _find_tool(_load_tools(), tool_id)
    if tool["type"] != "agent":
        raise HTTPException(400, "仅 Agent 工具支持测试")
    _validate_required_agent_values(body)
    if not body.python_code.strip():
        raise HTTPException(400, "Python 代码不能为空")

    parameters = {
        "model": _normalize_text(body.model),
        "model_provider": _normalize_text(body.model_provider),
        "api_key": _normalize_text(body.api_key),
        "base_url": _normalize_text(body.base_url),
        "system_prompt": body.system_prompt,
        "human_message": body.human_message.strip(),
    }
    started_at = time.perf_counter()
    try:
        result = run_agent_python(body.python_code, parameters)
    except AgentTemplateError as exc:
        result = {"ok": False, "logs": f"Agent 模板编译失败: {exc}\n"}
    result["latency_ms"] = round((time.perf_counter() - started_at) * 1000, 1)
    return JSONResponse(result)


@router.post("/{tool_id}/run")
def run_script(tool_id: str, body: ScriptRunRequest) -> JSONResponse:
    """在受限环境中执行 Script 工具的代码，返回 stdout 输出或错误。"""
    tool = _find_tool(_load_tools(), tool_id)
    if tool["type"] != "script":
        raise HTTPException(400, "仅 Script 工具支持运行")

    script_code = (body.script_code or "").strip()
    if not script_code:
        raise HTTPException(400, "脚本代码不能为空")

    output, console, output_print = _new_output()
    try:
        exec(script_code, _restricted_globals(output_print))
        return JSONResponse({"ok": True, "logs": output.getvalue()})
    except Exception as exc:  # noqa: BLE001 - 运行接口需要把完整异常写入日志区
        console.print("[bold red]Script 运行失败[/bold red]")
        console.print(f"[bold red]错误类型: {type(exc).__name__}[/bold red]")
        console.print(f"[bold red]错误信息: {exc}[/bold red]")
        console.print()
        console.print("[bold yellow]完整 Traceback:[/bold yellow]")
        console.print(traceback.format_exc())
        return JSONResponse({"ok": False, "logs": output.getvalue()})


@router.delete("/{tool_id}")
def delete_tool(tool_id: str) -> JSONResponse:
    """删除一个测试工具。"""
    tools = _load_tools()
    tool = _find_tool(tools, tool_id)
    tools = [item for item in tools if item["id"] != tool_id]
    _save_tools(tools)
    return JSONResponse({"ok": True, "tool_id": tool_id, "name": tool["name"]})
