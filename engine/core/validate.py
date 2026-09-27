"""Whole-project validation. Run by: CLI `validate`, git pre-commit, session start, and before any engine run."""
from __future__ import annotations

import subprocess
from collections import defaultdict
from dataclasses import dataclass, field

from .project import Project
from .schema import check_record
from .store import Store, read_changelog, rec_hash


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    divergent: list[tuple[str, str, int]] = field(default_factory=list)  # (entity, id, max_rev)

    @property
    def ok(self) -> bool:
        return not self.errors

    def text(self, limit: int = 40) -> str:
        out = []
        for label, items in (("ERROR", self.errors), ("WARN", self.warnings)):
            for m in items[:limit]:
                out.append(f"{label}: {m}")
            if len(items) > limit:
                out.append(f"{label}: ... and {len(items) - limit} more")
        return "\n".join(out)


def records(store: Store, rep: Report):
    lower_ids = defaultdict(list)
    for entity, recs in store.all().items():
        for rid, rec in recs.items():
            where = f"{entity}/{rid}"
            if rec.get("id") != rid:
                rep.errors.append(f"{where}: file name and id '{rec.get('id')}' differ")
            for e in check_record(store.schema(entity), rec) + store.ref_errors(entity, rec) + store.class_errors(entity, rec):
                rep.errors.append(f"{where}: {e}")
            if not isinstance(rec.get("_meta"), dict) or "rev" not in rec["_meta"]:
                rep.errors.append(f"{where}: missing _meta.rev (record not written by the engine)")
            lower_ids[(entity, rid.lower())].append(rid)
    for (entity, _), ids in lower_ids.items():
        if len(ids) > 1:
            rep.errors.append(f"{entity}: IDs {ids} differ only by case (breaks on Windows/macOS)")
    for d in store.p.records_dir.glob("*"):
        if d.is_dir() and d.name not in store.schemas:
            rep.errors.append(f"records/{d.name}/ has no schema")


def integrity(store: Store, rep: Report):
    """Every record must match the hash logged for its current revision - proves no hand edits."""
    entries, errs = read_changelog(store.p)
    rep.errors += errs
    by_key = defaultdict(list)
    for e in entries:
        by_key[(e.get("entity"), e.get("id"))].append(e)
    keys = set(by_key) | {(e, r) for e, recs in store.all().items() for r in recs}
    for key in sorted(keys, key=lambda k: (str(k[0]), str(k[1]))):
        entity, rid = key
        where = f"{entity}/{rid}"
        log = by_key.get(key, [])
        rec = store.all().get(entity, {}).get(rid)
        if not log:
            rep.errors.append(f"{where}: exists but was never logged - created by hand. "
                              f"Fix: python -m engine db reconcile {entity} {rid} --reason \"...\"")
            rep.divergent.append((entity, rid, 0))
            continue
        max_rev = max(int(e.get("rev", 0)) for e in log)
        heads = [e for e in log if int(e.get("rev", 0)) == max_rev]
        if len({(h.get("op") == "delete", h.get("hash")) for h in heads}) > 1:
            users = sorted({h.get("user") for h in heads})
            rep.errors.append(f"{where}: parallel changes at rev {max_rev} by {users} - check the merged file, then "
                              f"python -m engine db reconcile {entity} {rid} --reason \"merged ...\"")
            rep.divergent.append((entity, rid, max_rev))
            continue
        head = heads[0]
        if rec is None:
            if head.get("op") != "delete":
                rep.errors.append(f"{where}: file missing but log says it exists (deleted by hand?). "
                                  f"Restore it with git, or: python -m engine db reconcile {entity} {rid} --reason ...")
                rep.divergent.append((entity, rid, max_rev))
            continue
        if head.get("op") == "delete":
            rep.errors.append(f"{where}: logged as deleted but file exists. Reconcile or remove it.")
            rep.divergent.append((entity, rid, max_rev))
            continue
        if rec.get("_meta", {}).get("rev") != max_rev or rec_hash(rec) != head.get("hash"):
            rep.errors.append(f"{where}: content differs from logged rev {max_rev} (edited by hand or merged). "
                              f"Use `db update`, or accept it: python -m engine db reconcile {entity} {rid} --reason ...")
            rep.divergent.append((entity, rid, max_rev))


def outputs(project: Project, store: Store, rep: Report):
    from . import runner
    for issue in runner.check_outputs(project, store):
        (rep.errors if issue[0] == "error" else rep.warnings).append(issue[1])


def deliveries(project: Project, rep: Report):
    from . import delivery
    rep.errors += delivery.check_deliveries(project)


def classlib(project: Project, rep: Report):
    """database/classlib is compiled reference data: must match its manifest and its source file."""
    folder = project.database / "classlib"
    mf = folder / "manifest.json"
    if not mf.exists():
        return
    import json
    from ..tools.build_classlib import sha256
    m = json.loads(mf.read_text(encoding="utf-8"))
    for name, h in m["files"].items():
        f = folder / name
        if not f.exists() or sha256(f) != h:
            rep.errors.append(f"database/classlib/{name}: missing or edited by hand - rebuild with python -m engine lib build")
    src = project.root / m["source"]
    if not src.exists():
        rep.warnings.append(f"class library source {m['source']} not found - cannot prove classlib matches it")
    elif sha256(src) != m["source_sha256"]:
        rep.errors.append(f"{m['source']} changed since the class library was compiled - run python -m engine lib build {m['source']}")


def governance(project: Project, store: Store, rep: Report):
    from ..engines import governance as gov
    for path, text in gov.render(store).items():
        f = project.root / path
        if not f.exists() or f.read_text(encoding="utf-8") != text:
            rep.errors.append(f"{path} is out of sync with database rule/lesson records "
                              "(hand-edited?). Regenerate: python -m engine run governance")


def changelog_append_only(project: Project, rep: Report):
    """Pre-commit only: a staged changelog must extend what is in HEAD, never rewrite it."""
    def git(*a):
        return subprocess.run(["git", "-C", str(project.root), *a], capture_output=True, text=True)
    staged = git("diff", "--cached", "--name-only", "--", "database/changelog").stdout.split()
    for path in staged:
        old = git("show", f"HEAD:{path}")
        if old.returncode != 0:
            continue  # new file
        new = git("show", f":{path}")
        if new.returncode != 0:
            rep.errors.append(f"{path}: changelog files must never be deleted")
        elif not new.stdout.startswith(old.stdout):
            rep.errors.append(f"{path}: changelog history was rewritten - it is append-only")


def run(project: Project, store: Store | None = None, pre_commit: bool = False) -> Report:
    rep = Report()
    try:
        store = store or Store(project)
        store.all()
    except Exception as e:  # broken schema / unreadable JSON / merge conflict markers
        rep.errors.append(f"database cannot be loaded: {e}")
        return rep
    classlib(project, rep)
    records(store, rep)
    integrity(store, rep)
    governance(project, store, rep)
    deliveries(project, rep)
    outputs(project, store, rep)
    if pre_commit:
        changelog_append_only(project, rep)
    for e, recs in store.all().items():
        for rid, rec in recs.items():
            for f in ("file",):
                if rec.get(f) and not (project.root / rec[f]).exists():
                    rep.warnings.append(f"{e}/{rid}.{f}: '{rec[f]}' not found in repository")
    return rep

