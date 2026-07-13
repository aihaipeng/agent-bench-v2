import argparse
import asyncio
import sys
from pathlib import Path
from typing import Sequence

from runner import SelectionError, run_benchmark


PROJECT_ROOT = Path(__file__).resolve().parent


def _positive_int(value: str) -> int:
    """解析必须大于等于一的命令行整数。"""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("必须大于等于 1")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析批跑范围、重复次数和并发数等命令行参数。"""
    parser = argparse.ArgumentParser(description="Agent Evaluator")
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument(
        "--cases",
        nargs="+",
        metavar="CASE_ID",
        help="指定一个或多个 case_id，支持空格或逗号分隔",
    )
    selector.add_argument(
        "--failed",
        action="store_true",
        help="运行 outputs/fail 中的失败用例",
    )
    parser.add_argument(
        "--repeat",
        type=_positive_int,
        default=1,
        help="每条用例完整运行次数，默认 1",
    )
    parser.add_argument(
        "--concurrency",
        type=_positive_int,
        default=1,
        help="并发执行的用例数，默认 1；同一用例的多次运行保持串行",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(
            run_benchmark(
                project_root=PROJECT_ROOT,
                requested_cases=args.cases,
                failed_only=args.failed,
                repeat=args.repeat,
                concurrency=args.concurrency,
            )
        )
    except SelectionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
