"""企业 Agent FastAPI HTTP Connector。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from execution.artifacts import ArtifactStore
from execution.models import (
    ArtifactRecord,
    AttemptRecord,
    CaseRunRecord,
    ExecutionStatus,
    RetentionClass,
    RunRecord,
    TargetRecord,
    utc_now_iso,
)
from execution.preparation import normalize_request_template
from execution.repository import RunRepository


class ConnectorErrorType(str, Enum):
    CONNECT_ERROR = "connect_error"
    CONNECT_TIMEOUT = "connect_timeout"
    READ_TIMEOUT = "read_timeout"
    WRITE_TIMEOUT = "write_timeout"
    POOL_TIMEOUT = "pool_timeout"
    REQUEST_ERROR = "request_error"
    HTTP_STATUS = "http_status"
    INVALID_JSON = "invalid_json"
    PROTOCOL_ERROR = "protocol_error"
    BUSINESS_ERROR = "business_error"
    ARTIFACT_ERROR = "artifact_error"


@dataclass(frozen=True)
class ConnectorResult:
    """成功进入 Parser 阶段所需的轻量 Artifact 引用。"""

    attempt: AttemptRecord
    request_artifact: ArtifactRecord
    response_artifact: ArtifactRecord
    http_status: int
    body_code: str


class FastAPIConnectorError(RuntimeError):
    """已持久化 Attempt 后返回给上层执行器的请求错误。"""

    def __init__(
        self,
        message: str,
        *,
        error_type: ConnectorErrorType,
        attempt: AttemptRecord,
        request_artifact: ArtifactRecord,
        response_artifact: ArtifactRecord | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.attempt = attempt
        self.request_artifact = request_artifact
        self.response_artifact = response_artifact


class FastAPIConnector:
    """发送一个 Case 请求并持久化所有 Attempt 与大型响应。"""

    def __init__(
        self,
        repository: RunRepository,
        artifact_store: ArtifactStore,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.repository = repository
        self.artifact_store = artifact_store
        self.transport = transport
        self.sleep = sleep

    async def invoke(
        self,
        *,
        run: RunRecord,
        case_run: CaseRunRecord,
        target: TargetRecord,
        request_body: Any,
        timeout_seconds: float = 600,
        connection_retry_count: int = 0,
        retry_interval_seconds: float = 0,
    ) -> ConnectorResult:
        """执行请求；仅连接失败重试，其他错误立即持久化并抛出。"""
        self._validate_inputs(
            run=run,
            case_run=case_run,
            target=target,
            timeout_seconds=timeout_seconds,
            connection_retry_count=connection_retry_count,
            retry_interval_seconds=retry_interval_seconds,
        )
        normalized_body = normalize_request_template(request_body)
        request_bytes = json.dumps(
            normalized_body,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request_artifact = self._write_request_artifact(
            run=run,
            case_run=case_run,
            content=request_bytes,
        )
        next_attempt_number = max(
            (
                attempt.attempt_number
                for attempt in self.repository.list_attempts(case_run.id)
            ),
            default=0,
        ) + 1
        url = f"{target.base_url.rstrip('/')}{target.path}"
        headers = httpx.Headers(target.headers)
        if "content-type" not in headers:
            headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            transport=self.transport,
            follow_redirects=False,
        ) as client:
            for retry_index in range(connection_retry_count + 1):
                attempt = self.repository.create_attempt(
                    AttemptRecord(
                        case_run_id=case_run.id,
                        attempt_number=next_attempt_number + retry_index,
                        status=ExecutionStatus.RUNNING,
                        started_at=utc_now_iso(),
                    )
                )
                http_status: int | None = None
                try:
                    async with client.stream(
                        target.method,
                        url,
                        headers=headers,
                        content=request_bytes,
                    ) as response:
                        http_status = response.status_code
                        response_artifact = await self._write_response_artifact(
                            run=run,
                            case_run=case_run,
                            attempt=attempt,
                            chunks=response.aiter_bytes(),
                        )
                except httpx.ConnectTimeout as exc:
                    failed = self._fail_attempt(
                        attempt,
                        ConnectorErrorType.CONNECT_TIMEOUT,
                        str(exc) or "连接目标超时",
                    )
                    if retry_index < connection_retry_count:
                        await self._wait_before_retry(retry_interval_seconds)
                        continue
                    request_artifact = self._retain_failure(request_artifact)
                    raise FastAPIConnectorError(
                        failed.error or "连接目标超时",
                        error_type=ConnectorErrorType.CONNECT_TIMEOUT,
                        attempt=failed,
                        request_artifact=request_artifact,
                    ) from exc
                except httpx.ConnectError as exc:
                    failed = self._fail_attempt(
                        attempt,
                        ConnectorErrorType.CONNECT_ERROR,
                        str(exc) or "连接目标失败",
                    )
                    if retry_index < connection_retry_count:
                        await self._wait_before_retry(retry_interval_seconds)
                        continue
                    request_artifact = self._retain_failure(request_artifact)
                    raise FastAPIConnectorError(
                        failed.error or "连接目标失败",
                        error_type=ConnectorErrorType.CONNECT_ERROR,
                        attempt=failed,
                        request_artifact=request_artifact,
                    ) from exc
                except httpx.ReadTimeout as exc:
                    failed = self._fail_attempt(
                        attempt,
                        ConnectorErrorType.READ_TIMEOUT,
                        str(exc) or "读取响应超时",
                        http_status=http_status,
                    )
                    request_artifact = self._retain_failure(request_artifact)
                    raise FastAPIConnectorError(
                        failed.error or "读取响应超时",
                        error_type=ConnectorErrorType.READ_TIMEOUT,
                        attempt=failed,
                        request_artifact=request_artifact,
                    ) from exc
                except (httpx.WriteTimeout, httpx.PoolTimeout) as exc:
                    error_type = (
                        ConnectorErrorType.WRITE_TIMEOUT
                        if isinstance(exc, httpx.WriteTimeout)
                        else ConnectorErrorType.POOL_TIMEOUT
                    )
                    failed = self._fail_attempt(
                        attempt,
                        error_type,
                        str(exc) or "HTTP 请求超时",
                        http_status=http_status,
                    )
                    request_artifact = self._retain_failure(request_artifact)
                    raise FastAPIConnectorError(
                        failed.error or "HTTP 请求超时",
                        error_type=error_type,
                        attempt=failed,
                        request_artifact=request_artifact,
                    ) from exc
                except httpx.RequestError as exc:
                    failed = self._fail_attempt(
                        attempt,
                        ConnectorErrorType.REQUEST_ERROR,
                        str(exc) or "HTTP 请求失败",
                        http_status=http_status,
                    )
                    request_artifact = self._retain_failure(request_artifact)
                    raise FastAPIConnectorError(
                        failed.error or "HTTP 请求失败",
                        error_type=ConnectorErrorType.REQUEST_ERROR,
                        attempt=failed,
                        request_artifact=request_artifact,
                    ) from exc
                except asyncio.CancelledError:
                    self.repository.update_attempt_status(
                        attempt.id,
                        ExecutionStatus.CANCELLED,
                        http_status=http_status,
                        error_type="cancelled",
                        error="本地请求等待已取消",
                        finished_at=utc_now_iso(),
                    )
                    raise
                except Exception as exc:
                    failed = self._fail_attempt(
                        attempt,
                        ConnectorErrorType.ARTIFACT_ERROR,
                        f"Response Artifact 保存失败: {exc}",
                        http_status=http_status,
                    )
                    request_artifact = self._retain_failure(request_artifact)
                    raise FastAPIConnectorError(
                        failed.error or "Response Artifact 保存失败",
                        error_type=ConnectorErrorType.ARTIFACT_ERROR,
                        attempt=failed,
                        request_artifact=request_artifact,
                    ) from exc

                if http_status is None:
                    raise RuntimeError("HTTP Response 缺少状态码")
                if not 200 <= http_status < 300:
                    self._raise_response_error(
                        attempt=attempt,
                        request_artifact=request_artifact,
                        response_artifact=response_artifact,
                        error_type=ConnectorErrorType.HTTP_STATUS,
                        message=f"FastAPI 返回 HTTP {http_status}",
                        http_status=http_status,
                    )
                try:
                    body = self.artifact_store.read_json(
                        response_artifact.relative_path
                    )
                except Exception as exc:
                    self._raise_response_error(
                        attempt=attempt,
                        request_artifact=request_artifact,
                        response_artifact=response_artifact,
                        error_type=ConnectorErrorType.INVALID_JSON,
                        message=f"FastAPI Response 不是合法 JSON: {exc}",
                        http_status=http_status,
                        cause=exc,
                    )
                if not isinstance(body, dict) or "code" not in body:
                    self._raise_response_error(
                        attempt=attempt,
                        request_artifact=request_artifact,
                        response_artifact=response_artifact,
                        error_type=ConnectorErrorType.PROTOCOL_ERROR,
                        message="FastAPI Response 必须是包含 code 的 JSON 对象",
                        http_status=http_status,
                    )
                body_code = str(body["code"])
                if body_code != "200":
                    self._raise_response_error(
                        attempt=attempt,
                        request_artifact=request_artifact,
                        response_artifact=response_artifact,
                        error_type=ConnectorErrorType.BUSINESS_ERROR,
                        message=f"FastAPI 业务 code={body_code}",
                        http_status=http_status,
                        body_code=body_code,
                    )
                succeeded = self.repository.update_attempt_status(
                    attempt.id,
                    ExecutionStatus.SUCCEEDED,
                    http_status=http_status,
                    body_code=body_code,
                    error_type=None,
                    error=None,
                    finished_at=utc_now_iso(),
                )
                return ConnectorResult(
                    attempt=succeeded,
                    request_artifact=request_artifact,
                    response_artifact=response_artifact,
                    http_status=http_status,
                    body_code=body_code,
                )
        raise RuntimeError("Connector 未产生结果")

    @staticmethod
    def _validate_inputs(
        *,
        run: RunRecord,
        case_run: CaseRunRecord,
        target: TargetRecord,
        timeout_seconds: float,
        connection_retry_count: int,
        retry_interval_seconds: float,
    ) -> None:
        if case_run.run_id != run.id:
            raise ValueError("CaseRun 不属于指定 Run")
        if run.target_id is not None and run.target_id != target.id:
            raise ValueError("Target 与 Run 快照不一致")
        if isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")
        if (
            not isinstance(connection_retry_count, int)
            or isinstance(connection_retry_count, bool)
            or connection_retry_count < 0
        ):
            raise ValueError("connection_retry_count 必须是非负整数")
        if isinstance(retry_interval_seconds, bool) or retry_interval_seconds < 0:
            raise ValueError("retry_interval_seconds 不能小于 0")

    def _write_request_artifact(
        self,
        *,
        run: RunRecord,
        case_run: CaseRunRecord,
        content: bytes,
    ) -> ArtifactRecord:
        relative_path = f"runs/{run.id}/cases/{case_run.id}/request.json"
        existing = [
            artifact
            for artifact in self.repository.list_artifacts(
                run.id, case_run_id=case_run.id
            )
            if artifact.kind == "request"
        ]
        if existing:
            if len(existing) != 1:
                raise RuntimeError("CaseRun 存在多个 request Artifact")
            if self.artifact_store.read_bytes(existing[0].relative_path) != content:
                raise RuntimeError("CaseRun 已保存的 request Artifact 与本次请求不一致")
            return existing[0]

        target = self.artifact_store.resolve(relative_path)
        if target.is_file():
            if target.read_bytes() != content:
                raise RuntimeError("孤立 request Artifact 与本次请求不一致")
            info_path = relative_path
            size_bytes = len(content)
            sha256 = hashlib.sha256(content).hexdigest()
        else:
            info = self.artifact_store.write_bytes(relative_path, content)
            info_path = info.relative_path
            size_bytes = info.size_bytes
            sha256 = info.sha256
        record = ArtifactRecord(
            run_id=run.id,
            case_run_id=case_run.id,
            kind="request",
            relative_path=info_path,
            size_bytes=size_bytes,
            sha256=sha256,
            retention_class=RetentionClass.SUCCESS_TEMPORARY,
        )
        try:
            return self.repository.create_artifact(record)
        except Exception:
            self.artifact_store.delete(info_path)
            raise

    async def _write_response_artifact(
        self,
        *,
        run: RunRecord,
        case_run: CaseRunRecord,
        attempt: AttemptRecord,
        chunks: AsyncIterable[bytes],
    ) -> ArtifactRecord:
        relative_path = (
            f"runs/{run.id}/cases/{case_run.id}/attempts/"
            f"{attempt.id}/response.json"
        )
        info = await self.artifact_store.write_async_chunks(relative_path, chunks)
        record = ArtifactRecord(
            run_id=run.id,
            case_run_id=case_run.id,
            attempt_id=attempt.id,
            kind="response",
            relative_path=info.relative_path,
            size_bytes=info.size_bytes,
            sha256=info.sha256,
            retention_class=RetentionClass.SUCCESS_TEMPORARY,
        )
        try:
            return self.repository.create_artifact(record)
        except Exception:
            self.artifact_store.delete(info.relative_path)
            raise

    def _fail_attempt(
        self,
        attempt: AttemptRecord,
        error_type: ConnectorErrorType,
        message: str,
        *,
        http_status: int | None = None,
        body_code: str | None = None,
    ) -> AttemptRecord:
        return self.repository.update_attempt_status(
            attempt.id,
            ExecutionStatus.ERROR,
            http_status=http_status,
            body_code=body_code,
            error_type=error_type.value,
            error=message,
            finished_at=utc_now_iso(),
        )

    def _retain_failure(self, artifact: ArtifactRecord) -> ArtifactRecord:
        return self.repository.update_artifact_retention(
            artifact.id,
            RetentionClass.FAILURE_LONG_TERM,
        )

    def _raise_response_error(
        self,
        *,
        attempt: AttemptRecord,
        request_artifact: ArtifactRecord,
        response_artifact: ArtifactRecord,
        error_type: ConnectorErrorType,
        message: str,
        http_status: int,
        body_code: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        failed = self._fail_attempt(
            attempt,
            error_type,
            message,
            http_status=http_status,
            body_code=body_code,
        )
        failed_request = self._retain_failure(request_artifact)
        failed_response = self._retain_failure(response_artifact)
        error = FastAPIConnectorError(
            message,
            error_type=error_type,
            attempt=failed,
            request_artifact=failed_request,
            response_artifact=failed_response,
        )
        if cause is not None:
            raise error from cause
        raise error

    async def _wait_before_retry(self, retry_interval_seconds: float) -> None:
        if retry_interval_seconds > 0:
            await self.sleep(retry_interval_seconds)
