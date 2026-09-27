"""Governance engine: renders rules.md and ledger.md from `rule` and `lesson` records.

These two files are loaded into every Claude Code session (via CLAUDE.md), so they
are kept short: only active items, one compact block each. Output is deterministic,
so validate can prove the files were not hand-edited by re-rendering them.
"""
from __future__ import annotations

from ..core.runner import Context, Engine

HEADER = ("<!-- GENERATED from database/records/{entity} by `python -m engine run governance`. DO NOT EDIT.\n"
          "     Change with: python -m engine db add|update {entity} ... --reason \"...\" -->\n")


def render_rules(rules: list[dict]) -> str:
    active = [r for r in rules if r.get("status", "active") == "active"]
    out = ["# Project Rules", HEADER.format(entity="rule"),
           "Mandatory rules bind every person and every AI session. Rule R-001 overrides everything else.", ""]
    for r in sorted(active, key=lambda r: r["id"]):
        sev = "MANDATORY" if r.get("severity") == "mandatory" else "advisory"
        out.append(f"## {r['id']} [{sev}] {r['title']}")
        out.append(r["statement"].strip())
        if r.get("rationale"):
            out.append(f"_Why:_ {r['rationale'].strip()}")
        out.append("")
    retired = len(rules) - len(active)
    if retired:
        out.append(f"_{retired} retired rule(s) kept in the database: `python -m engine db list rule`._\n")
    return "\n".join(out).rstrip() + "\n"


def render_ledger(lessons: list[dict]) -> str:
    active = [l for l in lessons if l.get("status", "active") == "active"]
    out = ["# Ledger - Lessons Learned", HEADER.format(entity="lesson"),
           "Read before working. Add a lesson whenever something went wrong or a better way was found:",
           "`python -m engine db add lesson --set title=\"...\" --set lesson=\"...\" --reason \"...\"`", ""]
    if not active:
        out.append("_No lessons recorded yet._")
    for l in sorted(active, key=lambda l: (l.get("date", ""), l["id"]), reverse=True):
        tags = f" [{', '.join(l['tags'])}]" if l.get("tags") else ""
        out.append(f"### {l['id']} ({l.get('date', '')}) {l['title']}{tags}")
        if l.get("context"):
            out.append(f"- Context: {l['context'].strip()}")
        out.append(f"- Lesson: {l['lesson'].strip()}")
        if l.get("action"):
            out.append(f"- Action: {l['action'].strip()}")
        out.append("")
    superseded = len(lessons) - len(active)
    if superseded:
        out.append(f"_{superseded} superseded lesson(s) kept in the database._")
    return "\n".join(out).rstrip() + "\n"


def render(store) -> dict[str, str]:
    return {"rules.md": render_rules(store.records("rule")),
            "ledger.md": render_ledger(store.records("lesson"))}


def write(project, store) -> list:
    files = []
    for rel, text in render(store).items():
        f = project.root / rel
        f.write_text(text, encoding="utf-8")
        files.append(f)
    return files


class Governance(Engine):
    name = "governance"
    title = "rules.md and ledger.md (session context) from rule/lesson records"
    version = "1.0.0"
    inputs = ["rule", "lesson"]
    formats = ["md"]

    def run(self, ctx: Context):
        return write(ctx.project, ctx.store)


ENGINE = Governance()
