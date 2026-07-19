import json
import os
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from web import routes_tools
from web.agent_runtime import compile_agent_template
from web.app import app
from web.run_stream import RunStreamManager


@dataclass(frozen=True)
class LiveProvider:
    id: str
    model: str
    model_provider: str
    api_key_env: str
    base_url_env: str
    default_base_url: str


@dataclass(frozen=True)
class ToolScenarioItem:
    tool_type: str
    name: str
    check_item: str
    code: str


@dataclass(frozen=True)
class LiveParameters:
    model: str
    model_provider: str
    api_key: str
    base_url: str
    system_prompt: str
    human_message: str

    def __repr__(self) -> str:
        return (
            "LiveParameters("
            f"model={self.model!r}, "
            f"model_provider={self.model_provider!r}, "
            "api_key='***', "
            f"base_url={self.base_url!r})"
        )

    def request_fields(self) -> dict[str, str]:
        return {
            "model": self.model,
            "model_provider": self.model_provider,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "system_prompt": self.system_prompt,
            "human_message": self.human_message,
        }


LIVE_PROVIDERS = (
    LiveProvider(
        id="deepseek",
        model="deepseek-v4-pro",
        model_provider="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_BASE_URL",
        default_base_url="https://api.deepseek.com",
    ),
    LiveProvider(
        id="dashscope",
        model="qwen3.7-max",
        model_provider="openai",
        api_key_env="DASHSCOPE_API_KEY",
        base_url_env="DASHSCOPE_BASE_URL",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
)


LIVE_AGENT_CODE = r'''
import json
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ToolRetryMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.chat_models import init_chat_model
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class EvaluationEvidence(BaseModel):
    check_item: Literal["__CHECK_ITEM__"]
    expected_intent: Literal["query_order"]
    language: Literal["zh-CN"]


class LiveEvaluation(BaseModel):
    status: Literal["PASS"]
    reason: str = Field(min_length=1)
    data: EvaluationEvidence


attempts = {"inspect_candidate": 0}
audit_events = []


@tool
def load_expectation(case_id: Literal["case_001"]) -> dict:
    """读取指定测试用例期望的意图和回答语言。"""
    return {"expected_intent": "query_order", "language": "zh-CN"}


@tool
def inspect_candidate(
    detected_intent: Literal["query_order"],
    language: Literal["zh-CN"],
) -> dict:
    """校验候选回答；首次调用固定失败，用于验证工具重试中间件。"""
    attempts["inspect_candidate"] += 1
    if attempts["inspect_candidate"] == 1:
        raise RuntimeError("planned first-attempt failure")
    return {"intent_matches": True, "language_matches": True}


class AuditMiddleware(AgentMiddleware):
    def wrap_tool_call(self, request, handler):
        tool_name = request.tool_call["name"]
        audit_events.append(f"before:{tool_name}")
        try:
            result = handler(request)
        except Exception as exc:
            audit_events.append(f"error:{tool_name}:{type(exc).__name__}")
            raise
        audit_events.append(f"after:{tool_name}")
        return result


model_options = {
    "model": ${model},
    "model_provider": ${model_provider},
    "api_key": ${api_key},
    "timeout": 60,
    "max_retries": 0,
}
if ${base_url}:
    model_options["base_url"] = ${base_url}
if ${model_provider} == "deepseek":
    model_options["extra_body"] = {"thinking": {"type": "disabled"}}
if ${model}.startswith("qwen"):
    model_options["extra_body"] = {"enable_thinking": False}

model = init_chat_model(**model_options)
agent = create_agent(
    model=model,
    tools=[load_expectation, inspect_candidate],
    middleware=[
        ToolRetryMiddleware(
            max_retries=1,
            tools=[inspect_candidate],
            initial_delay=0,
            backoff_factor=0,
            jitter=False,
        ),
        AuditMiddleware(),
    ],
    system_prompt=(
        "你正在执行 Agent Bench 真实模型集成测试。必须先调用 load_expectation，"
        "case_id 固定为 case_001；再调用 inspect_candidate，detected_intent 固定为 "
        "query_order，language 固定为 zh-CN。禁止跳过工具或自行推断工具结果。"
        "工具成功后返回 PASS，data.check_item 固定为 __CHECK_ITEM__，"
        "data.expected_intent 固定为 query_order，data.language 固定为 zh-CN。"
    ),
    response_format=ToolStrategy(LiveEvaluation),
)

execution = agent.invoke(
    {"messages": [{"role": "user", "content": ${human_message}}]}
)
tool_messages = [
    message for message in execution["messages"] if isinstance(message, ToolMessage)
]
print(
    "LIVE_AGENT_AUDIT="
    + json.dumps(
        {
            "attempts": attempts["inspect_candidate"],
            "audit_events": audit_events,
            "tool_names": [message.name for message in tool_messages],
        },
        ensure_ascii=False,
    ),
    flush=True,
)
response = execution["structured_response"]
'''


SCRIPT_CODES = {
    "tool_use": r'''
print("SCRIPT_CHECK=tool_use", flush=True)
response = {
    "status": "PASS",
    "reason": "example-business-tool 被调用",
    "data": {"check_item": "tool_use", "tool_name": "example-business-tool"},
}
''',
    "tool_use_count": r'''
print("SCRIPT_CHECK=tool_use_count", flush=True)
tool_use_count = 2
response = {
    "status": "PASS" if tool_use_count <= 10 else "FAIL",
    "reason": f"tool_use_count = {tool_use_count} <= 10",
    "data": {"check_item": "tool_use_count", "actual": tool_use_count},
}
''',
}


def _agent_item(name: str, check_item: str) -> ToolScenarioItem:
    return ToolScenarioItem(
        tool_type="agent",
        name=name,
        check_item=check_item,
        code=LIVE_AGENT_CODE.replace("__CHECK_ITEM__", check_item),
    )


def _script_item(check_item: str) -> ToolScenarioItem:
    return ToolScenarioItem(
        tool_type="script",
        name=f"live-{check_item}-script",
        check_item=check_item,
        code=SCRIPT_CODES[check_item],
    )


SCENARIOS = {
    "single-script": (_script_item("tool_use"),),
    "single-agent": (_agent_item("live-intent-agent", "intent"),),
    "multi-script": (
        _script_item("tool_use"),
        _script_item("tool_use_count"),
    ),
    "multi-agent": (
        _agent_item("live-intent-agent", "intent"),
        _agent_item("live-i18n-agent", "i18n"),
    ),
    "script-agent": (
        _script_item("tool_use"),
        _script_item("tool_use_count"),
        _agent_item("live-intent-agent", "intent"),
        _agent_item("live-i18n-agent", "i18n"),
    ),
}


def _patch_runtime(tmp_path, monkeypatch):
    registry_root = tmp_path / "tools"
    monkeypatch.setattr(routes_tools, "TOOL_REGISTRY_ROOT", registry_root)
    monkeypatch.setattr(routes_tools, "_registry_instance", None)
    monkeypatch.setattr(routes_tools, "_registry_root", None)
    monkeypatch.setattr(routes_tools, "_run_stream_manager", RunStreamManager())
    return registry_root


def _provider_parameters(provider: LiveProvider) -> LiveParameters:
    api_key = os.getenv(provider.api_key_env, "").strip()
    if not api_key:
        pytest.skip(f"缺少真实模型测试环境变量: {provider.api_key_env}")
    return LiveParameters(
        model=provider.model,
        model_provider=provider.model_provider,
        api_key=api_key,
        base_url=os.getenv(
            provider.base_url_env,
            provider.default_base_url,
        ).strip(),
        system_prompt="",
        human_message="严格按系统要求调用两个工具并返回结构化校验结果。",
    )


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        lines = block.splitlines()
        event_line = next(
            (line for line in lines if line.startswith("event: ")),
            None,
        )
        data_line = next(
            (line for line in lines if line.startswith("data: ")),
            None,
        )
        if event_line and data_line:
            events.append(
                {
                    "type": event_line.removeprefix("event: "),
                    "data": json.loads(data_line.removeprefix("data: ")),
                }
            )
    return events


def _save_tool(client: TestClient, item: ToolScenarioItem, provider: LiveProvider):
    created = client.post(
        "/api/tools",
        json={
            "type": item.tool_type,
            "name": item.name,
            "description": "真实模型端到端测试临时工具",
        },
    )
    assert created.status_code == 200
    tool_id = created.json()["tool"]["id"]

    body = {
        "name": item.name,
        "description": "真实模型端到端测试临时工具",
        "script_code": item.code if item.tool_type == "script" else "",
        "python_code": item.code if item.tool_type == "agent" else "",
        "model": provider.model if item.tool_type == "agent" else "",
        "model_provider": (
            provider.model_provider if item.tool_type == "agent" else ""
        ),
        "api_key": "",
        "base_url": provider.default_base_url if item.tool_type == "agent" else "",
        "system_prompt": "",
        "human_message": "严格按系统要求调用两个工具并返回结构化校验结果。",
    }
    updated = client.put(f"/api/tools/{tool_id}", json=body)
    assert updated.status_code == 200
    saved = client.get(f"/api/tools/{tool_id}")
    assert saved.status_code == 200
    assert saved.json()["tool"]["api_key"] == ""
    return tool_id


def _run_tool(
    client: TestClient,
    tool_id: str,
    item: ToolScenarioItem,
    provider: LiveProvider,
    parameters: LiveParameters | None,
) -> tuple[dict, str]:
    run_id = f"live-{provider.id}-{uuid4().hex}"
    if item.tool_type == "agent":
        assert parameters is not None
        path = f"/api/tools/{tool_id}/test/start"
        body = {
            **parameters.request_fields(),
            "python_code": item.code,
            "run_id": run_id,
        }
    else:
        path = f"/api/tools/{tool_id}/run/start"
        body = {"script_code": item.code, "run_id": run_id}

    started = client.post(path, json=body)
    assert started.status_code == 202
    assert started.json()["run_id"] == run_id

    streamed = client.get(f"/api/tools/runs/{run_id}/events")
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(streamed.text)
    assert events
    assert events[-1]["type"] == "complete"
    logs = "".join(
        event["data"]["text"]
        for event in events
        if event["type"] == "log"
    )
    complete = events[-1]["data"]
    if not complete.get("ok"):
        redacted_logs = logs
        if parameters:
            redacted_logs = redacted_logs.replace(parameters.api_key, "***")
        pytest.fail(
            f"{provider.id}/{item.name} 执行失败:\n{redacted_logs[-4000:]}"
        )
    return complete["response"], logs


def _assert_evaluator_result(result: dict, check_item: str) -> None:
    assert result["status"] == "PASS"
    assert isinstance(result["reason"], str) and result["reason"].strip()
    assert result["data"]["check_item"] == check_item


def _assert_agent_audit(logs: str) -> None:
    audit_line = next(
        line.removeprefix("LIVE_AGENT_AUDIT=")
        for line in logs.splitlines()
        if line.startswith("LIVE_AGENT_AUDIT=")
    )
    audit = json.loads(audit_line)
    assert audit["attempts"] == 2
    assert {"load_expectation", "inspect_candidate"}.issubset(
        audit["tool_names"]
    )
    assert "before:load_expectation" in audit["audit_events"]
    assert "after:load_expectation" in audit["audit_events"]
    assert "error:inspect_candidate:RuntimeError" in audit["audit_events"]
    assert "after:inspect_candidate" in audit["audit_events"]


def test_live_matrix_definition_and_agent_templates_compile():
    assert {
        name: [item.tool_type for item in items]
        for name, items in SCENARIOS.items()
    } == {
        "single-script": ["script"],
        "single-agent": ["agent"],
        "multi-script": ["script", "script"],
        "multi-agent": ["agent", "agent"],
        "script-agent": ["script", "script", "agent", "agent"],
    }
    parameters = {
        "model": "test-model",
        "model_provider": "openai",
        "api_key": "test-only",
        "base_url": "https://example.test/v1",
        "system_prompt": "",
        "human_message": "test",
    }
    for items in SCENARIOS.values():
        for item in items:
            if item.tool_type == "agent":
                compiled = compile_agent_template(item.code, parameters)
                compile(compiled, f"<{item.name}>", "exec")


@pytest.mark.live
@pytest.mark.parametrize("provider", LIVE_PROVIDERS, ids=lambda item: item.id)
@pytest.mark.parametrize("scenario_name", SCENARIOS)
def test_real_model_tool_matrix_through_web_crud_and_sse(
    tmp_path,
    monkeypatch,
    provider: LiveProvider,
    scenario_name: str,
):
    registry_root = _patch_runtime(tmp_path, monkeypatch)
    client = TestClient(app)
    items = SCENARIOS[scenario_name]
    parameters = (
        _provider_parameters(provider)
        if any(item.tool_type == "agent" for item in items)
        else None
    )
    tool_ids = []
    try:
        for item in items:
            tool_id = _save_tool(client, item, provider)
            tool_ids.append(tool_id)
            result, logs = _run_tool(
                client,
                tool_id,
                item,
                provider,
                parameters,
            )
            _assert_evaluator_result(result, item.check_item)
            if item.tool_type == "agent":
                _assert_agent_audit(logs)
                manifest = (registry_root / tool_id / "manifest.json").read_text(
                    encoding="utf-8"
                )
                assert parameters is not None
                assert parameters.api_key not in manifest
    finally:
        for tool_id in tool_ids:
            deleted = client.delete(f"/api/tools/{tool_id}")
            assert deleted.status_code == 200
            assert client.get(f"/api/tools/{tool_id}").status_code == 404
