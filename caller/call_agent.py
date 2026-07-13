import asyncio
import time

import requests

from core.models import TestCase, RawAnswer


def build_payload(tc: TestCase, agent_cfg: dict) -> dict:
    """根据测试用例和 Agent 配置生成 POST 请求体。

    Args:
        tc: 当前测试用例。
        agent_cfg: 目标 Agent 配置。

    Returns:
        可直接作为 JSON 发送的请求体。
    """
    custom = agent_cfg.get("custom_param", {})
    return {
        "username": agent_cfg["username"],
        "password": agent_cfg["password"],
        "access_address": agent_cfg["ip"],
        "config_name": custom.get("config_name", ""),
        "model_name": custom.get("model_name", ""),
        "question": tc.question,
    }


class AgentCallError(Exception):
    """Agent 调用失败异常"""

    pass


def _post_with_retry(
    payload: dict, base_url: str, api_path: str, timeout: int, max_retries: int = 3
) -> dict:
    """同步发送 POST 请求，并对请求异常执行指数退避重试。

    Args:
        payload: POST 请求体。
        base_url: 目标 Agent 基础地址。
        api_path: Agent API 路径。
        timeout: 单次请求超时秒数。
        max_retries: 最大尝试次数。

    Returns:
        Agent 返回的 JSON 对象。

    Raises:
        AgentCallError: 所有请求尝试均失败。
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{base_url}{api_path}",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                time.sleep(wait_time)
        except requests.exceptions.RequestException as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                time.sleep(wait_time)

    raise AgentCallError(f"Agent 调用失败，已重试 {max_retries} 次: {last_exception}")


async def call_agent(tc: TestCase, config: dict) -> RawAnswer:
    """异步调用目标 Agent，并返回包装后的原始响应。

    Args:
        tc: 当前测试用例。
        config: 完整项目配置。

    Returns:
        包含 Agent 原始 JSON 和用例辅助信息的响应对象。

    Raises:
        AgentCallError: 请求重试后仍无法获得有效响应。
    """
    agent_cfg = config["target_agent"]
    payload = build_payload(tc, agent_cfg)

    response_json = await asyncio.to_thread(
        _post_with_retry,
        payload,
        agent_cfg["base_url"],
        agent_cfg["api_path"],
        agent_cfg.get("timeout_seconds", 180),
    )

    return RawAnswer(
        raw_data=response_json,
        extra_data={
            "case_id": tc.case_id,
            "question": tc.question,
            "tools": tc.tools,
        },
    )
