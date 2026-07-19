"""测试工具管理 API 路由。"""

import json
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from web.agent_runtime import (
    AgentTemplateError,
    ExecutionAlreadyRunningError,
    find_agent_template_parameters,
    interrupt_python_run,
    run_agent_python,
    run_script_python,
    stream_agent_python,
    stream_script_python,
)
from web.files import open_directory_in_explorer
from web.run_stream import RunStreamError, RunStreamManager
from web.tool_registry import (
    MAIN_FILENAME,
    MANIFEST_FILENAME,
    SCHEMA_VERSION,
    ToolRegistry,
    ToolRegistryError,
    manifest_from_record,
    parse_tool_package,
)

router = APIRouter(prefix="/api/tools", tags=["tools"])

TOOL_TYPES = {"script", "agent"}
AGENT_TEMPLATE_VERSION = 3
TOOL_REGISTRY_ROOT = Path(__file__).resolve().parent.parent / "tool_registry"
_registry_instance: ToolRegistry | None = None
_registry_root: Path | None = None
_run_stream_manager = RunStreamManager()
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

# 流式输出
# for chunk, _ in agent.stream(
#     {
#         "messages": [
#             {"role": "user", "content": ${human_message}},
#         ]
#     },
#     stream_mode="messages",
# ):
#     if isinstance(chunk.content, str):
#         print(chunk.content, end="", flush=True)

# 阻塞式输出
response = agent.invoke({
    "messages": [
        {"role": "user", "content": ${human_message}},
    ]
})

print(response)
'''
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


def _get_registry() -> ToolRegistry:
    """返回当前配置目录对应的仓储，便于测试切换临时目录。"""
    global _registry_instance, _registry_root
    root = Path(TOOL_REGISTRY_ROOT).resolve()
    if _registry_instance is None or _registry_root != root:
        _registry_instance = ToolRegistry(root)
        _registry_root = root
    return _registry_instance


def _to_api_tool(raw: dict) -> dict:
    """将统一文件结构转换为现有页面使用的扁平字段。"""
    parameters = raw.get("parameters", {})
    is_agent = raw["type"] == "agent"
    return {
        "id": raw["id"],
        "type": raw["type"],
        "name": raw["name"],
        "description": raw.get("description", ""),
        "output_example": raw.get("output_example"),
        "output_example_configured": raw.get("output_example_configured", False),
        "model_provider": parameters.get("model_provider", "") if is_agent else "",
        "api_key": parameters.get("api_key", "") if is_agent else "",
        "base_url": parameters.get("base_url", "") if is_agent else "",
        "model": parameters.get("model", "") if is_agent else "",
        "system_prompt": parameters.get("system_prompt", "") if is_agent else "",
        "human_message": parameters.get("human_message", "") if is_agent else "",
        "python_code": raw.get("code", "") if is_agent else "",
        "needs_review": False,
        "agent_template_version": AGENT_TEMPLATE_VERSION,
        "script_code": raw.get("code", "") if not is_agent else "",
        "created_at": raw.get("created_at", ""),
        "updated_at": raw.get("updated_at", ""),
    }


def _load_tools() -> list[dict]:
    return [_to_api_tool(tool) for tool in _get_registry().list_tools()]


def _get_raw_tool(tool_id: str) -> dict:
    tool = _get_registry().get_tool(tool_id)
    if tool is None:
        raise HTTPException(404, f"工具不存在: {tool_id}")
    return tool


def _save_new_tool(raw: dict) -> dict:
    try:
        return _get_registry().create_tool(raw)
    except ToolRegistryError as exc:
        raise HTTPException(400, str(exc)) from exc


def _save_existing_tool(tool_id: str, raw: dict) -> dict:
    try:
        return _get_registry().update_tool(tool_id, raw)
    except ToolRegistryError as exc:
        raise HTTPException(400, str(exc)) from exc


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


class ToolOutputExampleRequest(BaseModel):
    """设置 Parser 字段树使用的 JSON 输出示例。"""

    output_example: Any


class AgentRunRequest(BaseModel):
    """使用编辑页当前参数运行 Agent Python 代码。"""

    model: str = ""
    model_provider: str = ""
    api_key: str = ""
    base_url: str = ""
    system_prompt: str = ""
    human_message: str = ""
    python_code: str = ""
    run_id: str = ""


class ScriptRunRequest(BaseModel):
    """运行 Script 工具时传入的请求体。"""

    script_code: str = ""
    run_id: str = ""


def _required_agent_values(body: ToolUpdateRequest | AgentRunRequest) -> dict[str, str]:
    return {
        "model": body.model,
        "model_provider": body.model_provider,
        "api_key": body.api_key,
        "base_url": body.base_url,
        "human_message": body.human_message,
    }


def _validate_required_agent_values(body: ToolUpdateRequest | AgentRunRequest) -> None:
    referenced = find_agent_template_parameters(body.python_code)
    missing = [
        field
        for field, value in _required_agent_values(body).items()
        if field in referenced and not _normalize_text(value)
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

    tool_type = _normalize_tool_type(body.type)
    now = _now_iso()
    raw = {
        "schema_version": SCHEMA_VERSION,
        "id": uuid4().hex,
        "type": tool_type,
        "name": name,
        "description": _normalize_text(body.description),
        "code": DEFAULT_AGENT_PYTHON_CODE if tool_type == "agent" else "",
        "parameters": (
            {
                "model": "",
                "model_provider": "",
                "api_key": "",
                "base_url": "",
                "system_prompt": "",
                "human_message": "你好，请介绍一下自己。",
            }
            if tool_type == "agent"
            else {}
        ),
        "created_at": now,
        "updated_at": now,
    }
    return JSONResponse({"tool": _to_api_tool(_save_new_tool(raw))})


def get_tool_registry() -> ToolRegistry:
    """供 Workflow 服务读取与工具管理页相同的显式刷新快照。"""
    return _get_registry()


@router.post("/refresh")
def refresh_tools() -> JSONResponse:
    """显式重读项目目录，并返回所有跳过文件的原因。"""
    result = _get_registry().refresh()
    return JSONResponse(
        {
            "loaded": result.loaded,
            "errors": [
                {"file": item.file, "error": item.error} for item in result.errors
            ],
        }
    )


@router.post("/import")
async def import_tools(files: list[UploadFile] = File(...)) -> JSONResponse:
    """逐个解析一个或多个 ZIP 工具包，同 ID 工具直接拒绝。"""
    imported: list[dict] = []
    errors: list[dict] = []
    for upload in files:
        filename = upload.filename or "未命名文件"
        if not filename.lower().endswith(".zip"):
            errors.append({"file": filename, "error": "仅支持 .zip 文件"})
            continue
        try:
            tools = _read_tool_archive(await upload.read())
        except ToolRegistryError as exc:
            errors.append({"file": filename, "error": str(exc)})
            continue
        for raw in tools:
            try:
                saved = _get_registry().create_tool(raw)
            except ToolRegistryError as exc:
                errors.append(
                    {"file": f"{filename}/{raw['id']}", "error": str(exc)}
                )
                continue
            imported.append({"file": filename, "tool": _to_api_tool(saved)})
    return JSONResponse({"imported": imported, "errors": errors})


def _read_tool_archive(content: bytes) -> list[dict]:
    """读取统一 ZIP 结构，并在写入仓储前完成整包结构校验。"""
    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile as exc:
        raise ToolRegistryError("ZIP 文件损坏或格式无效") from exc

    packages: dict[str, dict[str, object]] = {}
    seen_paths: set[str] = set()
    try:
        with archive:
            for info in archive.infolist():
                raw_name = info.filename
                if "\\" in raw_name:
                    raise ToolRegistryError(f"ZIP 路径必须使用正斜杠: {raw_name}")
                path = PurePosixPath(raw_name)
                if path.is_absolute() or ".." in path.parts:
                    raise ToolRegistryError(f"ZIP 包含不安全路径: {raw_name}")
                if info.is_dir():
                    if len(path.parts) != 1:
                        raise ToolRegistryError(f"ZIP 包含无效目录: {raw_name}")
                    continue
                if raw_name in seen_paths:
                    raise ToolRegistryError(f"ZIP 包含重复文件: {raw_name}")
                seen_paths.add(raw_name)
                if len(path.parts) != 2 or path.name not in {
                    MANIFEST_FILENAME,
                    MAIN_FILENAME,
                }:
                    raise ToolRegistryError(f"ZIP 包含无效文件路径: {raw_name}")
                tool_id = path.parts[0]
                package = packages.setdefault(tool_id, {})
                package[path.name] = info

            if not packages:
                raise ToolRegistryError("ZIP 中没有工具目录")

            records: list[dict] = []
            for tool_id, package in packages.items():
                missing = {
                    MANIFEST_FILENAME,
                    MAIN_FILENAME,
                } - set(package)
                if missing:
                    raise ToolRegistryError(
                        f"工具 {tool_id} 缺少文件: {', '.join(sorted(missing))}"
                    )
                try:
                    manifest_content = archive.read(
                        package[MANIFEST_FILENAME]
                    ).decode("utf-8-sig")
                    code = archive.read(package[MAIN_FILENAME]).decode("utf-8")
                except (OSError, RuntimeError, UnicodeError) as exc:
                    raise ToolRegistryError(f"工具 {tool_id} 读取失败: {exc}") from exc
                record = parse_tool_package(
                    manifest_content,
                    code,
                    expected_id=tool_id,
                )
                records.append(record.model_dump())
            return records
    except ToolRegistryError:
        raise
    except (OSError, RuntimeError) as exc:
        raise ToolRegistryError(f"ZIP 读取失败: {exc}") from exc


def _build_tool_archive(tools: list[dict]) -> bytes:
    """将一个或多个工具写为统一的 ID 子目录 ZIP。"""
    archive = BytesIO()
    with ZipFile(archive, mode="w", compression=ZIP_DEFLATED) as zip_file:
        for tool in tools:
            manifest = manifest_from_record(tool)
            zip_file.writestr(
                f"{tool['id']}/{MANIFEST_FILENAME}",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
            zip_file.writestr(f"{tool['id']}/{MAIN_FILENAME}", tool.get("code", ""))
    return archive.getvalue()


@router.get("/export")
def export_tools(ids: list[str] = Query(default=[])) -> Response:
    """将所选工具或全部工具打包为统一目录结构 ZIP。"""
    if ids:
        tools = [_get_raw_tool(tool_id) for tool_id in dict.fromkeys(ids)]
    else:
        tools = _get_registry().list_tools()
    if not tools:
        raise HTTPException(400, "没有可导出的工具")

    filename = f"tools-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return Response(
        content=_build_tool_archive(tools),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{tool_id}")
def get_tool(tool_id: str) -> JSONResponse:
    """查看一个测试工具。"""
    return JSONResponse({"tool": _to_api_tool(_get_raw_tool(tool_id))})


@router.get("/{tool_id}/export")
def export_tool(tool_id: str) -> Response:
    """将单个工具导出为 ZIP，包括 manifest 中保存的密钥。"""
    raw = _get_raw_tool(tool_id)
    return Response(
        content=_build_tool_archive([raw]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{tool_id}.zip"'
        },
    )


@router.post("/{tool_id}/open-dir")
def open_tool_dir(tool_id: str) -> JSONResponse:
    """在 Windows 资源管理器中直接打开指定工具目录。"""
    _get_raw_tool(tool_id)
    path = _get_registry().get_tool_directory(tool_id)
    if path is None:
        raise HTTPException(404, f"工具不存在: {tool_id}")
    abs_path = open_directory_in_explorer(path)
    return JSONResponse({"ok": True, "path": abs_path})


@router.put("/{tool_id}")
def update_tool(tool_id: str, body: ToolUpdateRequest) -> JSONResponse:
    """修改一个测试工具。"""
    name = _normalize_text(body.name)
    if not name:
        raise HTTPException(400, "名称不能为空")

    raw = _get_raw_tool(tool_id)
    raw["name"] = name
    raw["description"] = _normalize_text(body.description)
    raw["updated_at"] = _now_iso()
    if raw["type"] == "agent":
        raw["code"] = body.python_code
        raw["parameters"] = {
            "model": _normalize_text(body.model),
            "model_provider": _normalize_text(body.model_provider),
            "api_key": _normalize_text(body.api_key),
            "base_url": _normalize_text(body.base_url),
            "system_prompt": body.system_prompt or "",
            "human_message": body.human_message.strip(),
        }
    else:
        raw["code"] = body.script_code or ""
        raw["parameters"] = {}
    return JSONResponse({"tool": _to_api_tool(_save_existing_tool(tool_id, raw))})


@router.patch("/{tool_id}")
def update_tool_metadata(tool_id: str, body: ToolMetadataUpdateRequest) -> JSONResponse:
    """局部更新名称或说明，不覆盖 Agent/Script 的其他配置。"""
    if body.name is None and body.description is None:
        raise HTTPException(400, "至少需要提供名称或说明")
    raw = _get_raw_tool(tool_id)
    if body.name is not None:
        name = _normalize_text(body.name)
        if not name:
            raise HTTPException(400, "名称不能为空")
        raw["name"] = name
    if body.description is not None:
        raw["description"] = _normalize_text(body.description)
    raw["updated_at"] = _now_iso()
    return JSONResponse({"tool": _to_api_tool(_save_existing_tool(tool_id, raw))})


@router.put("/{tool_id}/output-example")
def update_tool_output_example(
    tool_id: str,
    body: ToolOutputExampleRequest,
) -> JSONResponse:
    """保存 Parser 声明使用的任意 JSON 输出示例。"""
    raw = _get_raw_tool(tool_id)
    raw["output_example"] = body.output_example
    raw["output_example_configured"] = True
    raw["updated_at"] = _now_iso()
    return JSONResponse({"tool": _to_api_tool(_save_existing_tool(tool_id, raw))})


@router.delete("/{tool_id}/output-example")
def delete_tool_output_example(tool_id: str) -> JSONResponse:
    """清除工具的 Parser 输出示例声明。"""
    raw = _get_raw_tool(tool_id)
    raw["output_example"] = None
    raw["output_example_configured"] = False
    raw["updated_at"] = _now_iso()
    return JSONResponse({"tool": _to_api_tool(_save_existing_tool(tool_id, raw))})


@router.post("/{tool_id}/test")
def test_agent(tool_id: str, body: AgentRunRequest) -> JSONResponse:
    """在独立子进程中编译并运行 Agent Python 代码。"""
    tool = _to_api_tool(_get_raw_tool(tool_id))
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
        run_id = _normalize_text(body.run_id)
        result = (
            run_agent_python(body.python_code, parameters, run_id=run_id)
            if run_id
            else run_agent_python(body.python_code, parameters)
        )
    except AgentTemplateError as exc:
        result = {"ok": False, "logs": f"Agent 模板编译失败: {exc}\n"}
    except ExecutionAlreadyRunningError as exc:
        raise HTTPException(409, str(exc)) from exc
    result["latency_ms"] = round((time.perf_counter() - started_at) * 1000, 1)
    return JSONResponse(result)


@router.post("/{tool_id}/run")
def run_script(tool_id: str, body: ScriptRunRequest) -> JSONResponse:
    """在独立子进程中运行 Script Python 代码。"""
    tool = _to_api_tool(_get_raw_tool(tool_id))
    if tool["type"] != "script":
        raise HTTPException(400, "仅 Script 工具支持运行")

    if not body.script_code.strip():
        raise HTTPException(400, "脚本代码不能为空")

    started_at = time.perf_counter()
    run_id = _normalize_text(body.run_id)
    try:
        result = (
            run_script_python(body.script_code, run_id=run_id)
            if run_id
            else run_script_python(body.script_code)
        )
    except ExecutionAlreadyRunningError as exc:
        raise HTTPException(409, str(exc)) from exc
    result["latency_ms"] = round((time.perf_counter() - started_at) * 1000, 1)
    return JSONResponse(result)


@router.post("/{tool_id}/test/start", status_code=202)
def start_agent_stream(tool_id: str, body: AgentRunRequest) -> JSONResponse:
    """启动 Agent Worker，并立即返回用于订阅日志的 run_id。"""
    tool = _to_api_tool(_get_raw_tool(tool_id))
    if tool["type"] != "agent":
        raise HTTPException(400, "仅 Agent 工具支持测试")
    _validate_required_agent_values(body)
    if not body.python_code.strip():
        raise HTTPException(400, "Python 代码不能为空")

    run_id = _normalize_text(body.run_id) or uuid4().hex
    parameters = {
        "model": _normalize_text(body.model),
        "model_provider": _normalize_text(body.model_provider),
        "api_key": _normalize_text(body.api_key),
        "base_url": _normalize_text(body.base_url),
        "system_prompt": body.system_prompt,
        "human_message": body.human_message.strip(),
    }

    def runner(on_log):
        try:
            return stream_agent_python(
                body.python_code,
                parameters,
                on_log,
                run_id,
            )
        except AgentTemplateError as exc:
            on_log(f"Agent 模板编译失败: {exc}\n")
            return {"ok": False}

    try:
        _run_stream_manager.start(run_id, runner)
    except RunStreamError as exc:
        raise HTTPException(409, str(exc)) from exc
    return JSONResponse({"ok": True, "run_id": run_id}, status_code=202)


@router.post("/{tool_id}/run/start", status_code=202)
def start_script_stream(tool_id: str, body: ScriptRunRequest) -> JSONResponse:
    """启动 Script Worker，并立即返回用于订阅日志的 run_id。"""
    tool = _to_api_tool(_get_raw_tool(tool_id))
    if tool["type"] != "script":
        raise HTTPException(400, "仅 Script 工具支持运行")
    if not body.script_code.strip():
        raise HTTPException(400, "脚本代码不能为空")

    run_id = _normalize_text(body.run_id) or uuid4().hex

    def runner(on_log):
        return stream_script_python(
            body.script_code,
            on_log,
            run_id,
        )

    try:
        _run_stream_manager.start(run_id, runner)
    except RunStreamError as exc:
        raise HTTPException(409, str(exc)) from exc
    return JSONResponse({"ok": True, "run_id": run_id}, status_code=202)


def _encode_sse_event(event: dict) -> str:
    event_type = str(event.get("type") or "message")
    payload = (
        {"text": event.get("text", "")}
        if event_type == "log"
        else event.get("result", {})
    )
    return (
        f"event: {event_type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


@router.get("/runs/{run_id}/events")
def stream_run_events(run_id: str) -> StreamingResponse:
    """以 SSE 顺序推送一次运行的日志和最终结果。"""
    normalized = _normalize_text(run_id)
    if not normalized or _run_stream_manager.get(normalized) is None:
        raise HTTPException(404, f"运行任务不存在: {normalized or run_id}")

    def event_source():
        try:
            for event in _run_stream_manager.iter_events(normalized):
                yield ": keepalive\n\n" if event is None else _encode_sse_event(event)
        except RunStreamError as exc:
            yield _encode_sse_event(
                {
                    "type": "complete",
                    "result": {"ok": False, "error": str(exc)},
                }
            )

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/interrupt")
def interrupt_run(run_id: str) -> JSONResponse:
    """立即终止指定运行任务及其派生子进程。"""
    normalized = _normalize_text(run_id)
    if not normalized:
        raise HTTPException(400, "run_id 不能为空")
    terminated = interrupt_python_run(normalized)
    return JSONResponse(
        {
            "ok": True,
            "run_id": normalized,
            "process_terminated": terminated,
        }
    )


@router.delete("/{tool_id}")
def delete_tool(tool_id: str) -> JSONResponse:
    """删除一个测试工具。"""
    tool = _get_raw_tool(tool_id)
    try:
        _get_registry().delete_tool(tool_id)
    except ToolRegistryError as exc:
        raise HTTPException(500, str(exc)) from exc
    return JSONResponse({"ok": True, "tool_id": tool_id, "name": tool["name"]})
