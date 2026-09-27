#!/usr/bin/env python3
"""PreToolUse guard: blocks direct writes to engine-owned paths (rules R-001 / R-002).

Engine-owned: database/records, database/changelog, output/, internal_deliveries/, rules.md, ledger.md.
These change only through `python -m engine ...`. The Bash check is a heuristic (write-like command
followed by a protected path); `python -m engine validate` is the backstop for anything it misses.
"""
import json
import os
import re
import sys

PROTECTED = ("database/records/", "database/changelog/", "output/", "internal_deliveries/", "rules.md", "ledger.md")
EXEMPT = {"output/README.md", "internal_deliveries/README.md"}  # folder documentation is hand-written
# write-like commands, only when in command position (line start or after ; && || | ( $( sudo xargs)
CMD_POS = r"(?:^|[;&|(]|\$\(|\bsudo\s+|\bxargs\s+)\s*"
WRITE_CMDS = r"(?:tee|mv|rm|touch|sed\s+-i\S*|truncate|dd|unlink|mkdir)\b"   # any argument is written
DEST_CMDS = r"(?:cp|install|rsync|ln)\b"                                    # only the last argument is written
MSG = ("BLOCKED by project rule R-001/R-002: '{p}' is engine-owned. Change data with "
       "`python -m engine db add|update|delete ...`, generate outputs with `python -m engine run <engine>`, "
       "issue with `python -m engine deliver ...`, lessons/rules via `db add lesson|rule` (see rules.md).")


def rel(path: str, root: str) -> str:
    p = os.path.normpath(os.path.join(root, path))
    return os.path.relpath(p, root).replace(os.sep, "/")


def protected(r: str) -> bool:
    return r not in EXEMPT and any(r == x.rstrip("/") or r.startswith(x) for x in PROTECTED)


def bash_target(cmd: str, root: str = "") -> str | None:
    """Return the first protected path that a write-like command targets, else None."""
    if re.match(r"^\s*(git|python3? -m engine)\b[^;&|<>]*$", cmd):
        return None
    for x in PROTECTED:
        pat = re.escape(x.rstrip("/"))
        prefix = rf"(?:\./|{re.escape(root.rstrip('/'))}/)?" if root else r"(?:\./)?"
        path = rf"['\"]?{prefix}({pat}(?:/[^\s'\";&|)]*)?)(?=[\s'\";&|)]|$)"
        patterns = (rf">>?\s*{path}",                                                  # redirect into it
                    rf"(?m){CMD_POS}{WRITE_CMDS}[^;&|\n]*?(?<=[\s'\"=]){path}",         # any argument
                    rf"(?m){CMD_POS}{DEST_CMDS}[^;&|\n]*?(?<=[\s'\"=]){path}\s*(?:[;&|)]|$)")  # destination
        for p in patterns:
            for m in re.finditer(p, cmd):
                if m.group(1) not in EXEMPT:
                    return m.group(1)
    return None


def main() -> int:
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or ev.get("cwd") or os.getcwd()
    tool, ti = ev.get("tool_name", ""), ev.get("tool_input", {}) or {}
    if tool == "Bash":
        hit = bash_target(ti.get("command", ""), root)
        if hit:
            print(MSG.format(p=hit), file=sys.stderr)
            return 2
        return 0
    path = ti.get("file_path") or ti.get("notebook_path")
    if path and protected(rel(path, root)):
        print(MSG.format(p=rel(path, root)), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
