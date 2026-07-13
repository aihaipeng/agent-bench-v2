import asyncio
from pathlib import Path

from caller import call_agent
from core.config import load_config
from core.models import (
    CheckStatus,
    ExcelRowResult,
    ParsedAgentAnswer,
    RawAnswer,
    TestCase,
    ValidationContext,
    VerifiedData,
)
from parser import parse_agent_answer
from storage import ArtifactStore, ExcelCaseRepository
from verifier import VerificationEngine, create_verification_engine


class SelectionError(ValueError):
    """用例选择参数无效。"""


def normalize_case_ids(values: list[str] | None) -> list[str]:
    """规范化空格或逗号分隔的 case_id，并按首次出现顺序去重。"""
    if not values:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in value.split(","):
            case_id = item.strip()
            if case_id and case_id not in seen:
                seen.add(case_id)
                result.append(case_id)
    return result


def select_test_cases(
    test_cases: list[TestCase], requested_ids: list[str] | None
) -> list[TestCase]:
    """按请求顺序选择测试用例，并在 ID 不存在时给出明确错误。"""
    if requested_ids is None:
        return test_cases
    case_map = {case.case_id: case for case in test_cases}
    missing = [case_id for case_id in requested_ids if case_id not in case_map]
    if missing:
        available = ", ".join(case_map) or "<none>"
        raise SelectionError(
            f"找不到用例: {', '.join(missing)}；可用 case_id: {available}"
        )
    return [case_map[case_id] for case_id in requested_ids]


def format_completion_summary(totals: dict[str, int]) -> str:
    """生成包含各状态数量及通过率的最终日志。"""
    total = sum(totals.values())
    pass_rate = totals.get("PASS", 0) / total if total else 0.0
    counts = ", ".join(f"{status}={count}" for status, count in totals.items())
    return f"Completed! {counts}, PASS_RATE={pass_rate:.2%}"


def _execution_status(verified: VerifiedData) -> str:
    """把动态校验结果转换为批跑内部统计状态。"""
    if verified.result is CheckStatus.PASS:
        return "PASS"
    if verified.result is CheckStatus.FAILED:
        return "FAILED"
    return "ERROR"


def _excel_status(status: str) -> ExcelRowResult:
    """把内部统计状态映射为 Excel 最终结果枚举。"""
    return {
        "PASS": ExcelRowResult.PASS,
        "FAILED": ExcelRowResult.FAILED,
        "ERROR": ExcelRowResult.ERROR,
    }[status]


async def _execute_attempt(
    testcase: TestCase,
    attempt: int,
    config: dict,
    engine: VerificationEngine,
    artifacts: ArtifactStore,
) -> tuple[str, ExcelRowResult, VerifiedData | None]:
    """执行一次调用、解析、校验和产物保存流水线。"""
    raw_answer: RawAnswer | None = None
    parsed_answer: ParsedAgentAnswer | None = None
    verified: VerifiedData | None = None
    stage = "call"
    prefix = f"[{testcase.case_id} #{attempt}]"

    try:
        print(f"{prefix} Call Agent...")
        raw_answer = await call_agent(testcase, config)
        print(f"{prefix} Agent 请求已响应")

        stage = "parse"
        parsed_answer = await asyncio.to_thread(
            parse_agent_answer,
            raw_answer,
            testcase.case_id,
        )
        print(f"{prefix} Raw JSON 解析完成")

        stage = "verify"
        context = ValidationContext(
            testcase=testcase,
            raw_answer=raw_answer,
            parsed=parsed_answer,
        )
        verified = await engine.verify(context)
        status = _execution_status(verified)
        print(f"{prefix} 验证结果: {status}")

        stage = "persist"
        artifacts.persist(
            case_id=testcase.case_id,
            attempt=attempt,
            is_fail=(status != "PASS"),
            raw_answer=raw_answer,
            parsed_answer=parsed_answer,
            verified=verified,
        )
        return status, _excel_status(status), verified
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        print(f"{prefix} ERROR ({stage}): {detail}")
        try:
            artifacts.persist(
                case_id=testcase.case_id,
                attempt=attempt,
                is_fail=True,
                raw_answer=raw_answer,
                parsed_answer=parsed_answer,
                verified=verified,
                error={
                    "stage": stage,
                    "type": type(exc).__name__,
                    "detail": str(exc),
                },
            )
        except Exception as persist_exc:
            print(
                f"{prefix} 记录错误失败: "
                f"{type(persist_exc).__name__}: {persist_exc}"
            )
        return "ERROR", ExcelRowResult.ERROR, None


async def _execute_case(
    testcase: TestCase,
    repeat: int,
    config: dict,
    engine: VerificationEngine,
    artifacts: ArtifactStore,
    semaphore: asyncio.Semaphore,
) -> tuple[str, list[tuple[str, ExcelRowResult, VerifiedData | None]]]:
    """在并发限制内串行执行同一用例的全部重复次数。"""
    async with semaphore:
        executions = [
            await _execute_attempt(testcase, attempt, config, engine, artifacts)
            for attempt in range(1, repeat + 1)
        ]
    return testcase.case_id, executions


async def run_benchmark(
    project_root: Path,
    requested_cases: list[str] | None = None,
    failed_only: bool = False,
    repeat: int = 1,
    concurrency: int = 1,
) -> list[ExcelRowResult] | None:
    """组织用例加载、筛选、并发执行、统计和最终 Excel 写回。"""
    config = load_config(project_root / "config.yaml")
    excel_cfg = config["excel"]
    input_path = Path(excel_cfg["input_path"])
    if not input_path.is_absolute():
        input_path = project_root / input_path

    excel = ExcelCaseRepository(
        input_path,
        excel_cfg.get("sheet_name", "Sheet1"),
    )
    print("Loading Excel test case data...")
    all_cases = excel.read_cases()
    print(f"Total of {len(all_cases)} test cases")
    if not all_cases:
        print("No valid test cases, exiting")
        return None

    artifacts = ArtifactStore(project_root / "outputs")
    artifacts.ensure_dirs()
    if failed_only:
        requested_ids = artifacts.get_failed_ids()
        if not requested_ids:
            print("outputs/fail 中没有失败用例")
            return None
    else:
        requested_ids = normalize_case_ids(requested_cases)

    selected_cases = select_test_cases(
        all_cases,
        requested_ids if requested_ids else None,
    )
    if failed_only:
        artifacts.clear_failed_files()

    print(
        f"Selected {len(selected_cases)} cases; repeat={repeat}; "
        f"concurrency={concurrency}"
    )
    engine = create_verification_engine(config)
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        asyncio.create_task(
            _execute_case(
                testcase,
                repeat,
                config,
                engine,
                artifacts,
                semaphore,
            )
        )
        for testcase in selected_cases
    ]

    completed: list[ExcelRowResult] = []
    excel_results: list[tuple[str, ExcelRowResult, VerifiedData | None]] = []
    totals = {status: 0 for status in ("PASS", "FAILED", "ERROR")}
    for task in asyncio.as_completed(tasks):
        case_id, executions = await task
        _, excel_result, verified = executions[-1]
        excel_results.append((case_id, excel_result, verified))
        completed.extend(result for _, result, _ in executions)
        for status, _, _ in executions:
            totals[status] += 1
        print(f"[{case_id}] 已完成 {len(executions)} 次独立执行")

    excel.write_results(excel_results)
    print(format_completion_summary(totals))
    return completed
