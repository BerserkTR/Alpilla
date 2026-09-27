#!/usr/bin/env bash
# Runs at session start, resume, /clear and after compaction.
# rules.md + ledger.md are already in context via CLAUDE.md imports; this adds the live project state.
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0
git config core.hooksPath .githooks 2>/dev/null
if ! python3 -c "import openpyxl, docx, jinja2, markdown" 2>/dev/null; then
  pip install -q -r requirements.txt >/dev/null 2>&1 || echo "WARN: could not install requirements.txt"
fi
echo "== Alpilla project state (python -m engine status) =="
python3 -m engine status --recent 3 2>&1 | head -n 25
echo "Reminder: data changes -> python -m engine db ...; outputs -> python -m engine run ...; lessons -> db add lesson."
exit 0
