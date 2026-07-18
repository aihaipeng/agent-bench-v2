"""Agent 编辑器端到端测试使用的隔离应用。"""

from pathlib import Path

from web import files, routes_tools


TEST_INPUTS_DIR = Path(__file__).parent / "inputs"
TEST_INPUTS_DIR.mkdir(parents=True, exist_ok=True)

files.INPUTS_DIR = TEST_INPUTS_DIR
routes_tools.INPUTS_DIR = TEST_INPUTS_DIR
routes_tools.TOOLS_FILE = TEST_INPUTS_DIR / ".tools.json"

from web.app import app  # noqa: E402
