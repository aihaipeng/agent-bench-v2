import hashlib
import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from execution import ArtifactStore, ArtifactStoreError


def test_chunked_write_hash_size_and_unicode_json_round_trip(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    chunks = ["第一行\n".encode(), b"second line\n", bytes(range(32))]
    expected = b"".join(chunks)

    info = store.write_chunks("runs/run-1/cases/case-1/response.bin", chunks)
    json_info = store.write_json(
        "runs/run-1/cases/case-1/result.json",
        {"status": "FAIL", "reason": "意图不准确", "count": 2},
    )

    assert info.relative_path == "runs/run-1/cases/case-1/response.bin"
    assert info.size_bytes == len(expected)
    assert info.sha256 == hashlib.sha256(expected).hexdigest()
    assert store.read_bytes(info.relative_path) == expected
    assert json_info.size_bytes > 0
    assert store.read_json(json_info.relative_path) == {
        "status": "FAIL",
        "reason": "意图不准确",
        "count": 2,
    }
    assert "意图不准确" in store.read_text(json_info.relative_path)


def test_existing_artifact_is_never_overwritten(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    store.write_text("runs/run-1/result.txt", "original")

    with pytest.raises(ArtifactStoreError, match="禁止覆盖"):
        store.write_text("runs/run-1/result.txt", "replacement")

    assert store.read_text("runs/run-1/result.txt") == "original"


def test_concurrent_writers_cannot_overwrite_same_artifact(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")

    def write(content: bytes):
        try:
            return store.write_bytes("runs/run-1/shared.bin", content)
        except ArtifactStoreError as exc:
            return exc

    payloads = [f"writer-{index}".encode() for index in range(12)]
    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(write, payloads))

    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(successes) == 1
    assert len(failures) == 11
    assert store.read_bytes("runs/run-1/shared.bin") in payloads
    assert not list((store.root / "runs" / "run-1").glob(".*.tmp"))


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "",
        "   ",
        ".",
        "../escape.json",
        "safe/../../escape.json",
        "..\\escape.json",
        "/absolute/path.json",
        "\\rooted\\path.json",
        "C:\\absolute\\path.json",
        "C:drive-relative.json",
        "\\\\server\\share\\path.json",
        "safe/bad:name.json",
        "safe/null\x00name.json",
    ],
)
def test_path_traversal_absolute_drive_colon_and_nul_are_rejected(
    tmp_path, unsafe_path
):
    root = tmp_path / "artifacts"
    store = ArtifactStore(root)

    with pytest.raises(ArtifactStoreError):
        store.resolve(unsafe_path)
    with pytest.raises(ArtifactStoreError):
        store.write_text(unsafe_path, "blocked")

    assert not (tmp_path / "escape.json").exists()


def test_symlink_escape_is_rejected_when_symlinks_are_available(tmp_path):
    root = tmp_path / "artifacts"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"当前环境不允许创建目录符号链接: {exc}")
    store = ArtifactStore(root)

    with pytest.raises(ArtifactStoreError, match="超出"):
        store.write_text("linked/escape.json", "blocked")
    assert not (outside / "escape.json").exists()


def test_failed_stream_write_leaves_no_target_or_temporary_file(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")

    def broken_chunks():
        yield b"partial"
        raise RuntimeError("source failed")

    with pytest.raises(RuntimeError, match="source failed"):
        store.write_chunks("runs/run-1/partial.bin", broken_chunks())

    target_parent = store.root / "runs" / "run-1"
    assert not (target_parent / "partial.bin").exists()
    assert not list(target_parent.glob(".*.tmp"))


def test_invalid_chunk_json_read_and_delete_errors_are_explicit(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")

    with pytest.raises(ArtifactStoreError, match="必须是 bytes"):
        store.write_chunks("runs/run-1/invalid.bin", [b"valid", "invalid"])
    assert not (store.root / "runs" / "run-1" / "invalid.bin").exists()

    store.write_text("runs/run-1/invalid.json", "{broken")
    with pytest.raises(ArtifactStoreError, match="JSON 格式错误"):
        store.read_json("runs/run-1/invalid.json")
    assert store.delete("runs/run-1/invalid.json") is True
    assert store.delete("runs/run-1/invalid.json") is False
    with pytest.raises(ArtifactStoreError, match="不存在"):
        store.read_bytes("runs/run-1/missing.bin")


def test_async_chunks_are_streamed_hashed_and_cleaned_after_failure(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")

    async def valid_chunks():
        yield b"first"
        yield "中文".encode("utf-8")

    info = asyncio.run(
        store.write_async_chunks("runs/run-1/async.bin", valid_chunks())
    )
    expected = b"first" + "中文".encode("utf-8")
    assert info.size_bytes == len(expected)
    assert info.sha256 == hashlib.sha256(expected).hexdigest()
    assert store.read_bytes(info.relative_path) == expected

    async def broken_chunks():
        yield b"partial"
        raise RuntimeError("async source failed")

    with pytest.raises(RuntimeError, match="async source failed"):
        asyncio.run(
            store.write_async_chunks("runs/run-1/broken.bin", broken_chunks())
        )
    parent = store.root / "runs" / "run-1"
    assert not (parent / "broken.bin").exists()
    assert not list(parent.glob(".*.tmp"))
