from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator


ROOT = Path(__file__).resolve().parent
REQUEST_TIMEOUT_SECONDS = 12
ANTHROPIC_VERSION = "2023-06-01"

app = FastAPI(title="Model Provider Connection Prototype", docs_url=None, redoc_url=None)


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderRequest(StrictRequest):
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(min_length=1, max_length=4096)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return normalize_base_url(value)


def normalize_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("BASE_URL 必须是有效的 HTTP 或 HTTPS 地址")
    if parsed.username or parsed.password:
        raise ValueError("BASE_URL 不能包含用户名或密码")
    return normalized


def build_model_candidates(base_url: str) -> list[str]:
    parsed = urlsplit(normalize_base_url(base_url))
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses", "/messages"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break

    base = urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, "")).rstrip("/")
    candidates = []
    if re.search(r"/v\d+$", path):
        candidates.append(f"{base}/models")
    else:
        candidates.extend((f"{base}/v1/models", f"{base}/models"))

    return list(dict.fromkeys(candidates))


def extract_models(payload: Any) -> list[dict[str, str | None]]:
    if not isinstance(payload, dict):
        return []
    entries = payload.get("data")
    if not isinstance(entries, list):
        entries = payload.get("models")
    if not isinstance(entries, list):
        return []

    models: dict[str, dict[str, str | None]] = {}
    for entry in entries:
        if isinstance(entry, str):
            model_id = entry.strip()
            owner = None
        elif isinstance(entry, dict):
            raw_id = entry.get("id") or entry.get("name")
            model_id = str(raw_id).strip() if raw_id is not None else ""
            raw_owner = entry.get("owned_by") or entry.get("ownedBy")
            owner = str(raw_owner) if raw_owner is not None else None
        else:
            continue
        if model_id:
            models[model_id] = {"id": model_id, "owned_by": owner}
    return [models[model_id] for model_id in sorted(models, key=str.casefold)]


def protocol_headers(protocol: str, api_key: str) -> dict[str, str]:
    if protocol == "ANTHROPIC":
        return {
            "accept": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }
    return {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}",
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "index.html")


@app.get("/styles.css")
def styles() -> FileResponse:
    return FileResponse(ROOT / "styles.css", media_type="text/css")


@app.get("/app.js")
def javascript() -> FileResponse:
    return FileResponse(ROOT / "app.js", media_type="application/javascript")


@app.post("/api/latency")
async def test_latency(body: ProviderRequest) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as client:
            async with client.stream(
                "GET",
                body.base_url,
                headers={"user-agent": "ModelProviderConnection/1.0"},
            ) as response:
                latency_ms = round((time.perf_counter() - started_at) * 1000)
                return {
                    "reachable": True,
                    "latency_ms": latency_ms,
                    "status_code": response.status_code,
                }
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"BASE_URL 无法访问: {type(exc).__name__}") from exc


@app.post("/api/models")
async def fetch_models(body: ProviderRequest) -> dict[str, Any]:
    attempts: list[str] = []
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as client:
        for endpoint in build_model_candidates(body.base_url):
            for protocol in ("OPENAI_COMPATIBLE", "ANTHROPIC"):
                started_at = time.perf_counter()
                try:
                    response = await client.get(
                        endpoint,
                        headers=protocol_headers(protocol, body.api_key),
                    )
                except httpx.HTTPError as exc:
                    attempts.append(f"{protocol} {endpoint}: {type(exc).__name__}")
                    continue

                if not response.is_success:
                    attempts.append(f"{protocol} {endpoint}: HTTP {response.status_code}")
                    continue
                try:
                    models = extract_models(response.json())
                except ValueError:
                    attempts.append(f"{protocol} {endpoint}: 响应不是 JSON")
                    continue
                if not models:
                    attempts.append(f"{protocol} {endpoint}: 未发现模型")
                    continue
                return {
                    "protocol": protocol,
                    "endpoint": endpoint,
                    "latency_ms": round((time.perf_counter() - started_at) * 1000),
                    "models": models,
                }

    summary = "；".join(attempts[-4:]) if attempts else "没有可用的模型端点"
    raise HTTPException(502, f"自动获取模型失败，可手工添加模型。{summary}")


if __name__ == "__main__":
    port = int(os.environ.get("MODEL_PROVIDER_PORT", "8024"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
