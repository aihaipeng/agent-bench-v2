import json
import re
import threading
from pathlib import Path
from typing import Any

from core.models import ParsedAgentAnswer, RawAnswer, VerifiedData


def _safe_case_id(case_id: str) -> str:
    """把 case_id 转换为不会越过目录且兼容 Windows 的文件名。"""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(case_id)).strip(" .")
    return safe or "unknown"


def _to_json(obj: Any, filepath: Path) -> None:
    """将模型或普通对象原子写入 UTF-8 JSON 文件。"""
    payload = obj.model_dump() if hasattr(obj, "model_dump") else obj
    content = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    temporary = filepath.with_suffix(filepath.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(filepath)


class ArtifactStore:
    """管理每次执行的 JSON 产物及失败重跑清单。"""

    def __init__(self, output_dir: str | Path):
        """初始化成功产物目录、失败目录和并发写锁。"""
        self.output_dir = Path(output_dir)
        self.failed_dir = self.output_dir / "fail"
        self._lock = threading.Lock()

    def ensure_dirs(self) -> None:
        """确保成功和失败产物目录均已创建。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

    def clear_failed_files(self) -> None:
        """删除失败目录中的旧文件，为失败重跑保留干净目录。"""
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            for path in self.failed_dir.iterdir():
                if path.is_file():
                    path.unlink()

    def persist(
        self,
        case_id: str,
        attempt: int,
        is_fail: bool,
        raw_answer: RawAnswer | None = None,
        parsed_answer: ParsedAgentAnswer | None = None,
        verified: VerifiedData | None = None,
        error: dict | None = None,
    ) -> dict[str, Path]:
        """按执行状态保存一次调用产生的全部可用 JSON 产物。"""
        with self._lock:
            directory = self.failed_dir if is_fail else self.output_dir
            directory.mkdir(parents=True, exist_ok=True)
            safe_id = _safe_case_id(case_id)
            artifacts: dict[str, Path] = {}
            values = {
                "raw": raw_answer,
                "verify": parsed_answer,
                "result": verified,
                "error": error,
            }
            for kind, value in values.items():
                if value is None:
                    continue
                path = directory / f"{safe_id}_{kind}_{attempt}.json"
                _to_json(value, path)
                artifacts[kind] = path
            return artifacts

    def get_failed_ids(self) -> list[str]:
        """从失败目录的终态文件名中提取待重跑用例 ID。"""
        failed_ids = {
            case_id
            for path in self.failed_dir.glob("*.json")
            if (case_id := self._terminal_case_id(path))
        }
        return sorted(failed_ids)

    @staticmethod
    def _terminal_case_id(path: Path) -> str:
        """从当前或旧版 result/error 文件名中提取 case_id。"""
        match = re.fullmatch(r"(.+)_(?:result|error)_\d+\.json", path.name)
        if match:
            return match.group(1)
        for suffix in ("_result.json", "_error.json"):
            if path.name.endswith(suffix):
                return path.name.removesuffix(suffix)
        return ""
