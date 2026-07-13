import asyncio
import time

import requests

from core.models import TestCase, RawAnswer


def build_payload(tc: TestCase, agent_cfg: dict) -> dict:
    """根据 TestCase 和 agent 配置生成 POST 请求体"""
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
    """同步 POST 请求，支持指数退避重试"""
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
    """
    调用 Agent API，返回 RawAnswer。
    内部流程：build_payload → _post → return RawAnswer
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
