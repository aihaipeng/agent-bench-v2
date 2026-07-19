"""大型运行制品的安全、原子文件存储。"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from tempfile import NamedTemporaryFile
from typing import Any


DEFAULT_ARTIFACT_ROOT = (
    Path(__file__).resolve().parents[1] / "run_storage" / "artifacts"
)


class ArtifactStoreError(RuntimeError):
    """Artifact 路径或文件操作不符合存储约束。"""


@dataclass(frozen=True)
class ArtifactInfo:
    """一次 Artifact 写入后可持久化到 SQLite 的文件信息。"""

    relative_path: str
    size_bytes: int
    sha256: str


class ArtifactStore:
    """将所有制品限制在一个独立根目录内。"""

    def __init__(self, root: str | Path = DEFAULT_ARTIFACT_ROOT):
        requested_root = Path(root)
        requested_root.mkdir(parents=True, exist_ok=True)
        self.root = requested_root.resolve()

    def resolve(self, relative_path: str | Path, *, must_exist: bool = False) -> Path:
        """解析并校验一个受限于 Artifact 根目录的相对路径。"""
        raw = str(relative_path).strip()
        if not raw or "\x00" in raw:
            raise ArtifactStoreError("Artifact 路径不能为空或包含空字符")

        windows_path = PureWindowsPath(raw)
        posix_path = PurePosixPath(raw.replace("\\", "/"))
        if (
            windows_path.is_absolute()
            or bool(windows_path.drive)
            or posix_path.is_absolute()
            or ".." in windows_path.parts
            or ".." in posix_path.parts
            or any(":" in part for part in windows_path.parts)
        ):
            raise ArtifactStoreError("Artifact 路径必须是根目录内的安全相对路径")

        candidate = (self.root / Path(*posix_path.parts)).resolve(strict=False)
        if candidate == self.root or not candidate.is_relative_to(self.root):
            raise ArtifactStoreError("Artifact 路径超出运行制品目录")
        if must_exist and not candidate.is_file():
            raise ArtifactStoreError(f"Artifact 不存在: {posix_path.as_posix()}")
        return candidate

    def write_bytes(
        self,
        relative_path: str | Path,
        content: bytes,
    ) -> ArtifactInfo:
        """原子写入二进制内容。"""
        return self.write_chunks(relative_path, (content,))

    def write_text(
        self,
        relative_path: str | Path,
        content: str,
    ) -> ArtifactInfo:
        """以 UTF-8 原子写入文本。"""
        return self.write_bytes(relative_path, content.encode("utf-8"))

    def write_json(
        self,
        relative_path: str | Path,
        content: Any,
    ) -> ArtifactInfo:
        """以 UTF-8、非 ASCII 转义格式原子写入 JSON。"""
        payload = json.dumps(
            content,
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        return self.write_text(relative_path, payload)

    def write_chunks(
        self,
        relative_path: str | Path,
        chunks: Iterable[bytes],
    ) -> ArtifactInfo:
        """流式写入多个字节块，并在提交前计算大小和 SHA-256。"""
        target = self.resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self.resolve(relative_path)
        if target.exists():
            raise ArtifactStoreError(
                f"Artifact 已存在，禁止覆盖: {self._relative(target)}"
            )

        digest = hashlib.sha256()
        size_bytes = 0
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
            ) as temporary:
                temporary_path = Path(temporary.name)
                for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise ArtifactStoreError("Artifact 数据块必须是 bytes")
                    temporary.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            try:
                os.link(temporary_path, target)
            except FileExistsError as exc:
                raise ArtifactStoreError(
                    f"Artifact 已存在，禁止覆盖: {self._relative(target)}"
                ) from exc
            temporary_path.unlink(missing_ok=True)
            temporary_path = None
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

        return ArtifactInfo(
            relative_path=self._relative(target),
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
        )

    async def write_async_chunks(
        self,
        relative_path: str | Path,
        chunks: AsyncIterable[bytes],
    ) -> ArtifactInfo:
        """异步流式写入字节块，供大型 HTTP Response 使用。"""
        target = self.resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self.resolve(relative_path)
        if target.exists():
            raise ArtifactStoreError(
                f"Artifact 已存在，禁止覆盖: {self._relative(target)}"
            )

        digest = hashlib.sha256()
        size_bytes = 0
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
            ) as temporary:
                temporary_path = Path(temporary.name)
                async for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise ArtifactStoreError("Artifact 数据块必须是 bytes")
                    temporary.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            try:
                os.link(temporary_path, target)
            except FileExistsError as exc:
                raise ArtifactStoreError(
                    f"Artifact 已存在，禁止覆盖: {self._relative(target)}"
                ) from exc
            temporary_path.unlink(missing_ok=True)
            temporary_path = None
        except BaseException:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

        return ArtifactInfo(
            relative_path=self._relative(target),
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
        )

    def read_bytes(self, relative_path: str | Path) -> bytes:
        """读取已存在的二进制 Artifact。"""
        return self.resolve(relative_path, must_exist=True).read_bytes()

    def read_text(self, relative_path: str | Path) -> str:
        """以 UTF-8 读取已存在的文本 Artifact。"""
        return self.resolve(relative_path, must_exist=True).read_text(encoding="utf-8")

    def read_json(self, relative_path: str | Path) -> Any:
        """读取并解析 JSON Artifact。"""
        try:
            return json.loads(self.read_text(relative_path))
        except json.JSONDecodeError as exc:
            raise ArtifactStoreError(
                f"Artifact JSON 格式错误: {relative_path}"
            ) from exc

    def delete(self, relative_path: str | Path) -> bool:
        """删除单个 Artifact，不递归删除运行目录。"""
        target = self.resolve(relative_path)
        if not target.exists():
            return False
        if not target.is_file():
            raise ArtifactStoreError("只能删除 Artifact 文件")
        target.unlink()
        return True

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()
