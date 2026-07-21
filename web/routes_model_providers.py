"""Model provider management, latency testing, and model discovery APIs."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from execution import (
    DEFAULT_DATABASE_PATH,
    ModelProviderConfiguration,
    ModelProviderRecord,
    ModelProviderRepository,
    ModelProviderRepositoryError,
    ModelProviderSummary,
)


router = APIRouter(prefix="/api/model-providers", tags=["model-providers"])
DATABASE_PATH = DEFAULT_DATABASE_PATH
REQUEST_TIMEOUT_SECONDS = 12
ANTHROPIC_VERSION = "2023-06-01"
_repository_instance: ModelProviderRepository | None = None
_repository_path: Path | None = None


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderConnectionRequest(_StrictModel):
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(min_length=1, max_length=4096)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValueError("BASE_URL 必须是有效的 HTTP 或 HTTPS 地址")
        if parsed.username or parsed.password:
            raise ValueError("BASE_URL 不能包含用户名或密码")
        if parsed.query or parsed.fragment:
            raise ValueError("BASE_URL 不能包含 query 或 fragment")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("BASE_URL 端口无效") from exc
        return normalized

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("API Key 不能为空")
        return value


class ProviderEnvelope(_StrictModel):
    provider: ModelProviderRecord


class ProviderSummaryEnvelope(_StrictModel):
    provider: ModelProviderSummary


class ProviderListResponse(_StrictModel):
    providers: list[ModelProviderSummary]


def _get_repository() -> ModelProviderRepository:
    global _repository_instance, _repository_path
    path = Path(DATABASE_PATH).resolve()
    if _repository_instance is None or _repository_path != path:
        _repository_instance = ModelProviderRepository(path)
        _repository_path = path
    return _repository_instance


def _get_provider_or_404(provider_id: str) -> ModelProviderRecord:
    provider = _get_repository().get(provider_id)
    if provider is None:
        raise HTTPException(404, f"模型供应商不存在: {provider_id}")
    return provider


def build_model_candidates(base_url: str) -> list[str]:
    parsed = urlsplit(ProviderConnectionRequest(base_url=base_url, api_key="x").base_url)
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses", "/messages"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    base = urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")
    candidates = [f"{base}/models"] if re.search(r"/v\d+$", path) else [
        f"{base}/v1/models", f"{base}/models"
    ]
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
            model_id, owner = entry.strip(), None
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


def _protocol_headers(protocol: str, api_key: str) -> dict[str, str]:
    if protocol == "ANTHROPIC":
        return {
            "accept": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }
    return {"accept": "application/json", "authorization": f"Bearer {api_key}"}


@router.get("", response_model=ProviderListResponse)
def list_providers() -> ProviderListResponse:
    return ProviderListResponse(
        providers=[ModelProviderSummary.from_record(item) for item in _get_repository().list()]
    )


@router.post("", response_model=ProviderEnvelope)
def create_provider(body: ModelProviderConfiguration) -> ProviderEnvelope:
    try:
        provider = _get_repository().create(
            ModelProviderRecord(**body.model_dump(mode="json"))
        )
    except ModelProviderRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ProviderEnvelope(provider=provider)


@router.post("/latency")
async def test_latency(body: ProviderConnectionRequest) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=REQUEST_TIMEOUT_SECONDS
        ) as client:
            async with client.stream(
                "GET", body.base_url,
                headers={"user-agent": "AgentBenchModelProvider/1.0"},
            ) as response:
                return {
                    "reachable": True,
                    "latency_ms": round((time.perf_counter() - started_at) * 1000),
                    "status_code": response.status_code,
                }
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"BASE_URL 无法访问: {type(exc).__name__}") from exc


@router.post("/models")
async def fetch_models(body: ProviderConnectionRequest) -> dict[str, Any]:
    attempts: list[str] = []
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=REQUEST_TIMEOUT_SECONDS
    ) as client:
        for endpoint in build_model_candidates(body.base_url):
            for protocol in ("OPENAI_COMPATIBLE", "ANTHROPIC"):
                started_at = time.perf_counter()
                try:
                    response = await client.get(
                        endpoint, headers=_protocol_headers(protocol, body.api_key)
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


@router.get("/{provider_id}", response_model=ProviderEnvelope)
def get_provider(provider_id: str) -> ProviderEnvelope:
    return ProviderEnvelope(provider=_get_provider_or_404(provider_id))


@router.put("/{provider_id}", response_model=ProviderEnvelope)
def update_provider(
    provider_id: str, body: ModelProviderConfiguration
) -> ProviderEnvelope:
    current = _get_provider_or_404(provider_id)
    record = ModelProviderRecord(
        id=current.id,
        created_at=current.created_at,
        **body.model_dump(mode="json"),
    )
    try:
        saved = _get_repository().update(record)
    except ModelProviderRepositoryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ProviderEnvelope(provider=saved)


@router.delete("/{provider_id}", response_model=ProviderSummaryEnvelope)
def delete_provider(provider_id: str) -> ProviderSummaryEnvelope:
    provider = _get_provider_or_404(provider_id)
    if not _get_repository().delete(provider_id):
        raise HTTPException(404, f"模型供应商不存在: {provider_id}")
    return ProviderSummaryEnvelope(provider=ModelProviderSummary.from_record(provider))
