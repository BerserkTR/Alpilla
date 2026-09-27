"""The Claude Code PreToolUse guard: blocks direct writes to engine-owned paths, allows normal work."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / ".claude" / "hooks" / "guard_paths.py"
spec = importlib.util.spec_from_file_location("guard", GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

R = "/repo"

BLOCK = [
    "echo x > output/equipment_list/a.xlsx",
    "echo hi >> ledger.md",
    "cat > rules.md <<'EOF'\nx\nEOF",
    "sed -i s/a/b/ database/records/equipment/X.json",
    "rm -rf output",
    "cd /repo && cp /tmp/a.xlsx output/equipment_list/",
    "touch database/changelog/ABC.jsonl",
    "mv x.json /repo/database/records/system/10MBA.json",
    "ls | tee internal_deliveries/x.txt",
    "python3 -m engine run --all && echo x > output/x",
]
ALLOW = [
    "python3 -m engine run --all",
    "python -m engine db add lesson --set title=x --set lesson=y --reason z",
    "git add -A && git commit -m 'update output/ and rules.md'",
    "git checkout -- database/records/equipment/X.json",
    "cp output/equipment_list/a.xlsx /tmp/",
    "ls output/ > /tmp/listing 2>&1 | head",
    "cat rules.md ledger.md",
    "cat > output/README.md <<'EOF'\ndocs\nEOF",
    "cat > notes.md <<'EOF'\nRun `python -m engine run <engine>`; every output comes from it.\nEOF",
    "grep -r pump database/records | head",
    "echo x > /tmp/output/a",
    "cat > temporary_codes/x.py <<'EOF'\nimport os  # install nothing into output here\nEOF",
]


@pytest.mark.parametrize("cmd", BLOCK)
def test_bash_blocked(cmd):
    assert guard.bash_target(cmd, R), cmd


@pytest.mark.parametrize("cmd", ALLOW)
def test_bash_allowed(cmd):
    assert guard.bash_target(cmd, R) is None, cmd


def run_hook(event):
    r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), capture_output=True, text=True,
                       env={"CLAUDE_PROJECT_DIR": R, "PATH": "/usr/bin:/bin"})
    return r.returncode


@pytest.mark.parametrize("path,code", [
    ("/repo/rules.md", 2), ("/repo/ledger.md", 2), ("/repo/output/x/a.docx", 2),
    ("/repo/database/records/equipment/A.json", 2), ("/repo/database/changelog/ABC.jsonl", 2),
    ("/repo/internal_deliveries/D/x.pdf", 2),
    ("/repo/output/README.md", 0), ("/repo/database/schema/equipment.json", 0), ("/repo/engine/cli.py", 0),
    ("/repo/templates/reports/x.md.j2", 0), ("/repo/sources/README.md", 0),
])
def test_file_tools(path, code):
    assert run_hook({"tool_name": "Write", "tool_input": {"file_path": path}}) == code
    assert run_hook({"tool_name": "Edit", "tool_input": {"file_path": path}}) == code
