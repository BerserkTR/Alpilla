"""Alpilla engine CLI - the only way to change the database and generate outputs.

    python -m engine status                        one-screen project state
    python -m engine validate [--pre-commit]       full consistency check
    python -m engine db schema [entity]            fields, types, units
    python -m engine db list <entity> [--where SQL] [--fields a,b] [--limit N]
    python -m engine db get <entity> <id>
    python -m engine db query "SELECT ..."         read-only SQL on the local index
    python -m engine db add <entity> [--id X] --set k=v ... [--json '{..}'] --reason "..."
    python -m engine db update <entity> <id> --set k=v --unset k --reason "..."
    python -m engine db delete <entity> <id> --reason "..."
    python -m engine db import <entity> <file.csv|.json> [--update] --reason "..."
    python -m engine db reconcile <entity> <id>|--all --reason "..."
    python -m engine db import-pcf <file.pcf> --line <id> [--replace] --reason "..."
    python -m engine lib find|show|attr|tree ...     AVEVA class library (classes, attributes, units, lists)
    python -m engine lib build <ttl> --reason "..."  recompile the class library from its source
    python -m engine plan [--all]                   schedule status + critical path (computed)
    python -m engine kks <tag|docno> ... | --next ORG KKS DISC TYPE   KKS / document number check, next number
    python -m engine mdl show [--rule DL-..] | sync [--apply --reason ..]   MDL rules -> required documents
    python -m engine doc status|issue|review <document> ...   release control (prerequisites, revision, review code)
    python -m engine gate [--process P] [--scope K] [--detail]   process gates and the documents they wait for
    python -m engine engines                       list engines
    python -m engine run <engine>|--all|--stale [--option k=v]
    python -m engine deliver <engine> --title T --purpose P --to R --reason "..." [--files GLOB]
    python -m engine setup                         one-time per clone (git hooks, user code)
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys

from .core import index, validate
from .core.project import Project
from .core.schema import coerce, describe
from .core.store import Store, StoreError, read_changelog

GOVERNANCE_ENTITIES = {"rule", "lesson"}


def _table(cols, rows, more=False) -> str:
    if not rows:
        return "(no rows)"
    cells = [[("" if v is None else str(v)).replace("\n", " ")[:60] for v in r] for r in rows]
    w = [max(len(str(c)), *(len(r[i]) for r in cells)) for i, c in enumerate(cols)]
    out = ["  ".join(str(c).ljust(w[i]) for i, c in enumerate(cols))]
    out += ["  ".join(r[i].ljust(w[i]) for i in range(len(cols))) for r in cells]
    if more:
        out.append("... (more rows - raise --limit or refine the query)")
    return "\n".join(out)


def _parse_sets(store: Store, entity: str, sets, unsets=None, js=None) -> dict:
    data = dict(json.loads(js)) if js else {}
    sch = store.schema(entity)
    for kv in sets or []:
        if "=" not in kv:
            raise StoreError(f"--set expects field=value, got '{kv}'")
        k, v = kv.split("=", 1)
        data[k.strip()] = v if k.strip() == "id" else coerce(sch, k.strip(), v)
    for k in unsets or []:
        data[k] = None
    return data


def _apply_attrs(store: Store, entity: str, data: dict, old: dict | None, attrs, unset_attrs) -> dict:
    """--attr "Name=value" / --unset-attr Name -> merged aveva_attrs typed by the record's AVEVA class."""
    if not attrs and not unset_attrs:
        return data
    sch = store.schema(entity)
    af = next((f for f, s in sch.fields.items() if s["type"] == "aveva_attrs"), None)
    if af is None:
        raise StoreError(f"{entity} has no AVEVA attributes")
    cf = sch.fields[af]["class_field"]
    cname = data.get(cf) or (old or {}).get(cf)
    if not cname:
        raise StoreError(f"set --set {cf}=<AVEVA class> before --attr (python -m engine lib find <text>)")
    if store.lib is None:
        raise StoreError("AVEVA class library not built (python -m engine lib build <ttl> --reason ...)")
    cls = store.lib.resolve(cname)
    merged = dict((old or {}).get(af) or {})
    merged.update(data.get(af) or {})
    for kv in attrs or []:
        if "=" not in kv:
            raise StoreError(f"--attr expects Name=value, got '{kv}'")
        k, v = kv.split("=", 1)
        merged[k.strip()] = store.lib.parse_cli(cls, k.strip(), v.strip())
    for k in unset_attrs or []:
        merged.pop(k, None)
    data[af] = merged or None
    return data


def _after_change(p: Project, store: Store, entities: set):
    if entities & GOVERNANCE_ENTITIES:
        from .engines import governance
        governance.write(p, store)
        print("rules.md / ledger.md regenerated")
    index.ensure(p, store)


def cmd_status(p: Project, a) -> int:
    store = Store(p)
    who = store.who
    print(f"user: {who.code} ({who.name} <{who.email}>){' via ' + who.agent if who.agent else ''}"
          + ("  [code derived - set: git config alpilla.usercode XYZ]" if who.code_is_derived else ""))
    counts = {e: len(r) for e, r in store.all().items() if r}
    print(f"db {store.db_hash()}: " + (", ".join(f"{e}={n}" for e, n in sorted(counts.items())) or "empty"))
    rep = validate.run(p, store)
    print(f"validate: {'OK' if rep.ok else f'{len(rep.errors)} error(s)'}, {len(rep.warnings)} warning(s)")
    if rep.errors or rep.warnings:
        print(rep.text(limit=8))
    g = lambda *x: subprocess.run(["git", "-C", str(p.root), *x], capture_output=True, text=True).stdout.strip()
    branch, dirty = g("branch", "--show-current"), g("status", "--porcelain")
    ab = g("rev-list", "--left-right", "--count", "HEAD...@{upstream}").split()
    ahead, behind = (int(ab[0]), int(ab[1])) if len(ab) == 2 else (None, None)
    print(f"git: {branch or '?'}, {len(dirty.splitlines())} uncommitted path(s)"
          + (f", {ahead} unpushed / {behind} not pulled commit(s)" if ahead is not None else ", no upstream"))
    # team-only project: nothing may stay on one machine
    if dirty:
        print("WARN: uncommitted work - validate, commit and push so the team works on the same data")
    if ahead:
        print("WARN: unpushed commits - push now (git push)")
    if behind:
        print("WARN: team changes not pulled - git pull, then python -m engine validate")
    if ahead is None and branch:
        print("WARN: branch has no upstream - push it to the shared repository (git push -u origin HEAD)")
    hooks = g("config", "core.hooksPath")
    if hooks != ".githooks":
        print("WARN: git hooks not active - run: python -m engine setup")
    entries, _ = read_changelog(p)
    for e in sorted(entries, key=lambda e: e.get("ts", ""))[-a.recent:]:
        print(f"  {e['ts'][:16]} {e['user']:<5} {e['op']:<9} {e['entity']}/{e['id']}: {e['reason'][:60]}")
    return 0 if rep.ok else 1


def cmd_validate(p: Project, a) -> int:
    rep = validate.run(p, pre_commit=a.pre_commit)
    print(rep.text(limit=200) or "OK - database, logs, rules/ledger, outputs and deliveries are consistent")
    return 0 if rep.ok else 1


def _run_query(p, sql, limit):
    import sqlite3
    try:
        c, rows, more = index.query(p, sql, limit)
    except sqlite3.Error as e:
        print(f"ERROR: SQL: {e}\n  columns are the field names; quote any that are SQL keywords, e.g. \"order\"='x'. "
              f"Fields: python -m engine db schema <entity>")
        return 1
    print(_table(c, rows, more))
    return 0


def cmd_db(p: Project, a) -> int:
    store = Store(p)
    op = a.op
    changed = {getattr(a, "entity", None)} - {None}
    if op == "schema":
        ents = [a.entity] if a.entity else sorted(store.schemas)
        print("\n\n".join(describe(store.schema(e)) for e in ents) if a.entity else
              "\n".join(f"{e:<18} {store.schema(e).title}" for e in ents))
        return 0
    if op == "get":
        r = store.get(a.entity, a.id)
        if r is None:
            print(f"{a.entity}/{a.id} not found"); return 1
        print(json.dumps(r, indent=1, ensure_ascii=False)); return 0
    if op == "list":
        sch = store.schema(a.entity)
        cols = ["id"] + (a.fields.split(",") if a.fields else sch.display or list(sch.fields)[:5])
        quoted = ", ".join(f'"{c}"' for c in cols)
        sql = f'SELECT {quoted} FROM "{a.entity}"' + (f" WHERE {a.where}" if a.where else "") + " ORDER BY id"
        return _run_query(p, sql, a.limit)
    if op == "query":
        return _run_query(p, a.sql, a.limit)
    if op == "add":
        data = _apply_attrs(store, a.entity, _parse_sets(store, a.entity, a.set, js=a.json), None, a.attr, None)
        if a.id:
            data["id"] = a.id
        r = store.create(a.entity, data, a.reason)
        print(f"created {a.entity}/{r['id']}")
    elif op == "update":
        data = _parse_sets(store, a.entity, a.set, a.unset, a.json)
        data = _apply_attrs(store, a.entity, data, store.get(a.entity, a.id), a.attr, a.unset_attr)
        r = store.update(a.entity, a.id, data, a.reason)
        print(f"{a.entity}/{a.id} rev {r['_meta']['rev']}")
    elif op == "delete":
        store.delete(a.entity, a.id, a.reason)
        print(f"deleted {a.entity}/{a.id}")
    elif op == "import":
        rows = _read_rows(store, a.entity, a.file)
        created = updated = 0
        try:
            for row in rows:
                if store.get(a.entity, row.get("id", "")) is not None:
                    if not a.update:
                        raise StoreError(f"{a.entity}/{row['id']} exists (use --update to modify existing records)")
                    store.update(a.entity, row["id"], row, a.reason); updated += 1
                else:
                    store.create(a.entity, row, a.reason); created += 1
        finally:
            print(f"import {a.entity}: {created} created, {updated} updated of {len(rows)} row(s)")
            _after_change(p, store, changed)
    elif op == "import-pcf":
        from pathlib import Path
        from .core import pcf
        if store.get("line", a.line) is None:
            raise StoreError(f"line {a.line} does not exist - create the line first (spec, size, conditions)")
        comps, skipped = pcf.parse(Path(a.file).read_text(encoding="utf-8", errors="replace"), a.valve_type)
        existing = [c["id"] for c in store.records("pipe_component") if c["line"] == a.line]
        if existing and not a.replace:
            raise StoreError(f"line {a.line} already has {len(existing)} component(s); use --replace to re-import")
        for cid in existing:
            store.delete("pipe_component", cid, a.reason)
        notes = []
        for i, c in enumerate(comps, 1):
            note = c.pop("_note", None)
            rec = store.create("pipe_component", {"line": a.line, "seq": f"{i * 10:04d}", **c}, a.reason)
            if note:
                notes.append(f"{rec['id']}: {note}")
        print(f"import-pcf {a.line}: {len(comps)} component(s)" + (f", replaced {len(existing)}" if existing else ""))
        for n in notes:
            print(f"  CHECK: {n}")
        if skipped:
            print(f"  not imported (unsupported PCF blocks): {', '.join(skipped)}")
        from .core import piping
        for m in piping.continuity(store, a.line):
            print(f"  WARN: {m}")
        changed = {"pipe_component"}
    elif op == "reconcile":
        rep = validate.Report()
        validate.integrity(store, rep)
        targets = [d for d in rep.divergent if a.all or (d[0], d[1]) == (a.entity, a.id)]
        if not targets:
            print("nothing to reconcile"); return 0
        for ent, rid, rev in targets:
            print(f"{ent}/{rid}: {store.reconcile(ent, rid, a.reason, rev)}")
        changed = {t[0] for t in targets}
    if op != "import":
        _after_change(p, store, changed)
    return 0


def _read_rows(store: Store, entity: str, path: str) -> list[dict]:
    sch = store.schema(entity)
    if path.endswith(".json"):
        data = json.load(open(path, encoding="utf-8"))
        return data if isinstance(data, list) else [data]
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for raw in csv.DictReader(fh):
            row = {}
            for k, v in raw.items():
                k = (k or "").strip()
                if not k or v is None or v.strip() == "":
                    continue
                row[k] = v.strip() if k == "id" else coerce(sch, k, v.strip())
            rows.append(row)
    return rows


def cmd_lib(p: Project, a) -> int:
    from .core import classlib
    if a.op == "build":
        from pathlib import Path
        from .tools.build_classlib import write
        src = (Path.cwd() / a.ttl).resolve()
        if not src.is_file() or p.root not in src.parents:
            raise ValueError(f"{a.ttl}: the library file must be inside the repository (e.g. references/aveva/)")
        m = write(p, src)
        print(f"class library compiled from {m['source']}: " + ", ".join(f"{k}={v}" for k, v in m["counts"].items()))
        rep = validate.Report()
        validate.records(Store(p), rep)
        print("existing records still valid" if rep.ok else "WARN: records now invalid against the new library:\n" + rep.text(20))
        return 0
    lib = classlib.get(p)
    if lib is None:
        raise ValueError("class library not built: python -m engine lib build references/aveva/<file>.ttl")
    if a.op == "find":
        hits = lib.find(a.text, a.root.split(",") if a.root else None, a.limit)
        rows = [(c["label"], c["id"], lib.classes.get(c.get("parent") or "", {}).get("label", ""),
                 len({v["id"] for v in lib.effective(c).values()})) for c in hits]
        print(_table(["class", "aveva_id", "parent", "attrs"], rows))
    elif a.op == "show":
        cls = lib.resolve(a.cls)
        chain = " > ".join(x["label"] for x in reversed(lib.ancestors(cls)))
        eff = {k: v for k, v in lib.effective(cls).items() if not k.startswith("AVEVA-") or v["label"] not in lib.effective(cls)}
        attrs = sorted({v["id"]: v for v in eff.values()}.values(), key=lambda x: x["label"])
        if a.grep:
            attrs = [x for x in attrs if a.grep.lower() in x["label"].lower()]
        print(f"{cls['label']} ({cls['id']}{', CFIHOS ' + cls['cfihos'] if cls.get('cfihos') else ''})\n{chain}")
        if cls.get("comment"):
            print(cls["comment"][:300])
        rows = [(x["label"], x["type"] + (" " + x["quantity"] if x.get("quantity") else ""),
                 "LOV" if x.get("lov") else "", x.get("discipline", "")) for x in attrs[:a.limit]]
        print(_table(["attribute", "type", "list", "discipline"], rows, len(attrs) > a.limit))
        print(f"{len(attrs)} attribute(s){' matching' if a.grep else ''}; details: python -m engine lib attr \"{cls['label']}\" \"<attribute>\"")
    elif a.op == "attr":
        cls = lib.resolve(a.cls)
        at = lib.effective(cls).get(a.attr)
        if at is None:
            raise ValueError(lib.attr_errors(cls, {a.attr: ""})[0])
        print(lib.describe_attr(at))
    elif a.op == "tree":
        cls = lib.resolve(a.cls)
        def show(cid, d):
            c = lib.classes[cid]
            print("  " * d + f"{c['label']} ({lib.subtree_size(cid)})")
            if d < a.depth:
                for k in sorted(lib._children.get(cid, []), key=lambda x: lib.classes[x]["label"]):
                    show(k, d + 1)
        show(cls["id"], 0)
    return 0


def cmd_plan(p: Project, a) -> int:
    """Compact schedule status: computed on the fly, nothing written."""
    from .core import planning
    store = Store(p)
    acts, cal, dd = planning.compute(store)
    if not acts:
        print("no activities"); return 0
    finish = max(cal.finish_date(x.ef, x.es) for x in acts)
    crit = sorted((x for x in acts if x.critical), key=lambda x: (x.es, x.id))
    print(f"data date {dd}  forecast finish {finish}  activities {len(acts)}  critical {len(crit)}  "
          f"negative float {sum(1 for x in acts if x.tf < 0)}")
    sel = crit if not a.all else sorted(acts, key=lambda x: (x.es, x.id))
    rows = [(x.id, x.title[:40], cal.date(x.es), cal.finish_date(x.ef, x.es),
             "done" if x.status == "completed" else x.tf, f"{x.pct:.0f}") for x in sel[:a.limit]]
    print(_table(["id", "title", "start", "finish", "float", "%"], rows, len(sel) > a.limit))
    return 0


def cmd_kks(p: Project, a) -> int:
    """Explain KKS tags / document numbers against the project key list, or propose the next document number."""
    from .core import kks
    store = Store(p)
    kk = kks.keys(store)
    if a.next:
        org, code, disc, dtype = a.next
        print(kks.next_number([d["id"] for d in store.records("document")], org, code, disc, dtype))
        return 0
    rc = 0
    for t in a.tags:
        lines = kks.explain(t, kk)
        bad = any("not" in x or "unknown" in x for x in lines)
        rc |= bad
        print(f"{t}: {'INVALID' if bad else 'ok'}")
        for x in lines:
            print(f"  {x}")
    return rc


def cmd_mdl(p: Project, a) -> int:
    """MDL rules -> document records: `sync` shows (and with --apply writes) the documents the rules require."""
    from collections import Counter
    from .core import mdl
    store = Store(p)
    if a.op == "show":
        inst, errs = mdl.required(store)
        rows = [i for i in inst.values() if not a.rule or i.rule["id"] == a.rule]
        for i in rows[:a.limit]:
            print(f"{i.key:<42} {i.org} {i.kks} sheets {i.sheets:>4} h {i.hours:>7.0f}  {i.title[:70]}")
        print(f"{len(rows)} instance(s), {sum(i.sheets for i in rows)} sheets, {sum(i.hours for i in rows):,.0f} h")
        for e in errs:
            print(f"ERROR: {e}")
        return 1 if errs else 0
    plan = mdl.plan_sync(store)
    for e in plan.errors:
        print(f"ERROR: {e}")
    by = Counter((rec["discipline"], rec["originator"] if rec["originator"] in ("EPC", "IEC") else "supplier")
                 for _, rec in plan.create)
    print(f"create {len(plan.create)} document(s), {sum(r['sheets'] for _, r in plan.create)} sheets, "
          f"{sum(r['weight'] for _, r in plan.create):,.0f} h; update {len(plan.update)}; orphans {len(plan.orphans)}")
    for (disc, org), n in sorted(by.items()):
        print(f"  + {disc:<16} {org:<9} {n}")
    for no in plan.orphans:
        print(f"  ORPHAN {no}: its rule instance no longer exists - cancel it or fix the rule")
    if plan.dropped:
        by = Counter((no.split("-")[4], x.split("-")[4]) for no, x in plan.dropped)
        print(f"  inputs removed: {len(plan.dropped)} (" + ", ".join(f"{a}<-{b} {n}" for (a, b), n in sorted(by.items())) + ")")
    loops = mdl.check_loops(store, plan)
    if loops:
        print(f"ERROR: input loop after sync: {', '.join(loops)}")
        return 1
    if plan.errors:
        return 1
    if not a.apply:
        print("dry run - nothing written (use --apply --reason ...)")
        return 0
    if not a.reason:
        raise StoreError("--apply needs --reason")
    for no, rec in plan.create:
        store.create("document", rec, a.reason)
    for no, ins in plan.links:
        store.update("document", no, {"inputs": ins}, a.reason)
    for no, ch in plan.update:
        store.update("document", no, ch, a.reason)
    if a.cancel_orphans and plan.orphans:
        gone = set(plan.orphans)
        for no in plan.orphans:
            store.update("document", no, {"status": "cancelled"}, a.reason)
        for d in store.records("document"):
            ins = d.get("inputs") or []
            if gone & set(ins):
                store.update("document", d["id"], {"inputs": [i for i in ins if i not in gone] or None}, a.reason)
        print(f"cancelled {len(gone)} orphan(s) and removed them from the inputs of other documents")
    print("applied")
    return 0


def cmd_doc(p: Project, a) -> int:
    """Document release control: status / issue (with prerequisite check and based_on) / review code."""
    from .core import release
    store = Store(p)
    docs = {d["id"]: d for d in store.records("document")}
    if a.id not in docs:
        raise StoreError(f"document {a.id} not found")
    st = release.states(store)
    types = {t["id"]: t for t in store.records("doc_type")}
    d, me = docs[a.id], st[a.id]
    if a.op == "status":
        print(f"{a.id}  {d['title']}")
        print(f"  status {release.NAME[me.level]}  latest rev {me.rev or '-'} {me.purpose or ''} {me.issued or ''}"
              f"{'  code ' + me.code if me.code else ''}  review class {release.review_class(d, types)}")
        print(f"  next: {release.next_action(d, me, types)}")
        for purpose in ("IFR", "IFA", "IFC", "AB"):
            why = release.can_issue(store, a.id, purpose, st)
            print(f"  {purpose}: {'allowed' if not why else 'blocked'}" + ("" if not why else " - " + "; ".join(why[:4])
                                                                               + (" ..." if len(why) > 4 else "")))
        for i in d.get("inputs") or []:
            if i in st:
                print(f"  input  {i:<30} {release.NAME[st[i].level]:<9} rev {st[i].rev or '-'}")
        for x in sorted(k for k, v in docs.items() if a.id in (v.get("inputs") or [])):
            print(f"  feeds  {x:<30} {release.NAME[st[x].level]:<9} rev {st[x].rev or '-'}")
        for i, r in me.suspect:
            print(f"  CHECK REQUIRED: input {i} revised ({r}) after this revision was prepared")
        return 0
    if a.op == "review":
        rid = f"{a.id}_{a.rev}"
        store.update("document_revision", rid, {"review_code": a.code, "review_date": a.date}, a.reason)
        return 0
    # issue
    why = release.can_issue(store, a.id, a.purpose, st)
    if why and not a.override:
        print(f"BLOCKED: {a.id} cannot be issued {a.purpose}:")
        for w in why:
            print(f"  - {w}")
        print("fix the prerequisites, or issue with --override \"justification\" (recorded on the revision)")
        return 1
    rev = a.rev or release.next_rev(me, a.purpose)
    based = sorted(st[i].rev_id for i in d.get("inputs") or [] if i in st and st[i].rev_id)
    rec = {"document": a.id, "revision": rev, "purpose": a.purpose, "issue_date": a.date}
    if based:
        rec["based_on"] = based
    if a.description:
        rec["description"] = a.description
    if why:
        rec["override"] = a.override + " | unmet: " + "; ".join(why)
    r = store.create("document_revision", rec, a.reason)
    print(f"issued {r['id']} ({a.purpose}) based on {len(based)} input revision(s)" + (" - OVERRIDE recorded" if why else ""))
    return 0


def cmd_gate(p: Project, a) -> int:
    from .core import release, workflow
    store = Store(p)
    res = workflow.compute(store)
    rows = [g for g in release.gates(store, res) if (not a.process or g.process == a.process)
            and (not a.scope or g.scope_key == a.scope)]
    for g in rows[:a.limit]:
        fl = g.float
        print(f"{g.gate:<16} {g.scope_key:<13} {'OPEN' if g.ok_now else 'blocked':<8} need {res.d(g.need) if g.need is not None else '-'}"
              f"  ready {res.d(g.ready) if g.ready is not None else '-'}  float {fl if fl is not None else '-'}  {g.title[:50]}")
        if a.detail:
            for req, n, missing, when, drv in g.rows:
                print(f"    {req:<34} {n:>4} doc(s), {len(missing):>4} not yet  planned {res.d(when) if when is not None else '-'}")
            for req in g.empty:
                print(f"    {req:<34} NO DOCUMENT SELECTED")
    late = sum(1 for g in rows if g.float is not None and g.float < 0)
    print(f"{len(rows)} gate(s): {sum(1 for g in rows if g.ok_now)} open now, {late} planned late")
    return 0


def cmd_engines(p: Project, a) -> int:
    from .engines import registry
    for name, e in registry().items():
        print(f"{name:<22} v{e.version:<7} [{','.join(e.formats)}]  {e.title}\n{'':<24}inputs: {', '.join(e.inputs)}")
    return 0


def cmd_run(p: Project, a) -> int:
    from .core.runner import run_engine
    from .engines import registry
    engines = registry()
    if a.stale:
        from .core.runner import check_outputs
        stale = {m.split("/")[1] for lvl, m in check_outputs(p, Store(p)) if "STALE" in m or "hand-" in m}
        names = sorted(stale & set(engines))
        if not names:
            print("all outputs are current"); return 0
    else:
        names = [n for n in engines if n != "governance"] if a.all else [a.engine]
    opts = dict(o.split("=", 1) for o in a.option or [])
    store = Store(p)
    rc = 0
    for n in names:
        if n not in engines:
            print(f"unknown engine '{n}'. Available: {', '.join(engines)}"); return 2
        try:
            m = run_engine(p, store, engines[n], opts)
        except Exception as e:
            print(f"{n}: FAILED - {e}"); rc = 1; continue
        print(f"{n}: {len(m['files'])} file(s) -> output/{n}/" if n != "governance" else f"{n}: {', '.join(m['files'])}")
        for w in m.get("warnings", []):
            print(f"  WARN: {w}")
    return rc


def cmd_deliver(p: Project, a) -> int:
    from .core.delivery import deliver
    store = Store(p)
    dest = deliver(p, store, a.engine, a.title, a.purpose, a.to, a.reason, a.files)
    index.ensure(p, store)
    print(f"issued {p.rel(dest)}/ - commit it to share")
    return 0


def cmd_setup(p: Project, a) -> int:
    g = lambda *x: subprocess.run(["git", "-C", str(p.root), *x], capture_output=True, text=True)
    g("config", "core.hooksPath", ".githooks")
    print("git hooks: .githooks (pre-commit validation) active")
    if a.user_code:
        g("config", "alpilla.usercode", a.user_code.upper())
    from .core.identity import current
    who = current(p.root)
    print(f"user: {who.code} ({who.name} <{who.email}>)")
    if who.code_is_derived:
        print("WARN: user code derived from your name. Pick a unique one: python -m engine setup --user-code ABC")
    taken = {f.stem for f in p.changelog_dir.glob("*.jsonl")} if p.changelog_dir.is_dir() else set()
    entries, _ = read_changelog(p)
    others = {e["user"] for e in entries if e.get("email") != who.email}
    if who.code in others:
        print(f"ERROR: user code {who.code} already belongs to someone else. Choose another with --user-code.")
        return 1
    print(f"known user codes: {', '.join(sorted(taken)) or 'none yet'}")
    missing = []
    for mod in ("openpyxl", "docx", "jinja2", "markdown", "ezdxf", "ifcopenshell", "rdflib", "matplotlib", "iapws"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    print("python deps OK" if not missing else f"missing python deps {missing}: pip install -r requirements.txt")
    index.ensure(p, force=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m engine", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.add_argument("--recent", type=int, default=5)
    s = sub.add_parser("validate"); s.add_argument("--pre-commit", action="store_true")
    sub.add_parser("engines")
    s = sub.add_parser("plan", help="schedule status and critical path (computed, nothing written)")
    s.add_argument("--all", action="store_true"); s.add_argument("--limit", type=int, default=40)
    s = sub.add_parser("run"); s.add_argument("engine", nargs="?"); s.add_argument("--all", action="store_true")
    s.add_argument("--stale", action="store_true", help="re-run only engines whose outputs are stale or invalid")
    s.add_argument("--option", action="append", help="k=v passed to the engine")
    s = sub.add_parser("deliver"); s.add_argument("engine"); s.add_argument("--title", required=True)
    s.add_argument("--purpose", required=True, help="e.g. internal review, IFR, for information")
    s.add_argument("--to", required=True); s.add_argument("--reason", required=True)
    s.add_argument("--files", nargs="*", help="glob(s) to select files, default all")
    s = sub.add_parser("setup"); s.add_argument("--user-code")
    s = sub.add_parser("kks", help="explain / check KKS tags and document numbers; --next ORG KKS DISC TYPE")
    s.add_argument("tags", nargs="*"); s.add_argument("--next", nargs=4, metavar=("ORG", "KKS", "DISC", "TYPE"))

    docp = sub.add_parser("doc", help="document release control").add_subparsers(dest="op", required=True)
    s = docp.add_parser("status"); s.add_argument("id")
    s = docp.add_parser("issue"); s.add_argument("id"); s.add_argument("--purpose", required=True,
                                                                        choices=["IFR", "IFA", "IFC", "AB", "IFI", "IFD", "IFP"])
    s.add_argument("--rev"); s.add_argument("--date", required=True); s.add_argument("--description")
    s.add_argument("--override", help="justification to issue although a prerequisite is not met"); s.add_argument("--reason", required=True)
    s = docp.add_parser("review"); s.add_argument("id"); s.add_argument("--rev", required=True)
    s.add_argument("--code", required=True, choices=["1", "2", "3", "4"]); s.add_argument("--date", required=True)
    s.add_argument("--reason", required=True)
    s = sub.add_parser("gate", help="process gates: documents needed by procurement, acceptance, construction, commissioning, operations")
    s.add_argument("--process"); s.add_argument("--scope"); s.add_argument("--detail", action="store_true")
    s.add_argument("--limit", type=int, default=60)
    mdlp = sub.add_parser("mdl", help="MDL rules: show instances, sync document records").add_subparsers(dest="op", required=True)
    s = mdlp.add_parser("show"); s.add_argument("--rule"); s.add_argument("--limit", type=int, default=60)
    s = mdlp.add_parser("sync"); s.add_argument("--apply", action="store_true"); s.add_argument("--reason")
    s.add_argument("--cancel-orphans", action="store_true", help="cancel documents whose rule instance no longer exists")

    lib = sub.add_parser("lib", help="AVEVA class library").add_subparsers(dest="op", required=True)
    s = lib.add_parser("build"); s.add_argument("ttl"); s.add_argument("--reason", required=True)
    s = lib.add_parser("find"); s.add_argument("text"); s.add_argument("--root"); s.add_argument("--limit", type=int, default=30)
    s = lib.add_parser("show"); s.add_argument("cls"); s.add_argument("--grep"); s.add_argument("--limit", type=int, default=60)
    s = lib.add_parser("attr"); s.add_argument("cls"); s.add_argument("attr")
    s = lib.add_parser("tree"); s.add_argument("cls"); s.add_argument("--depth", type=int, default=1)

    db = sub.add_parser("db").add_subparsers(dest="op", required=True)
    s = db.add_parser("schema"); s.add_argument("entity", nargs="?")
    s = db.add_parser("get"); s.add_argument("entity"); s.add_argument("id")
    s = db.add_parser("list"); s.add_argument("entity"); s.add_argument("--where"); s.add_argument("--fields")
    s.add_argument("--limit", type=int, default=50)
    s = db.add_parser("query"); s.add_argument("sql"); s.add_argument("--limit", type=int, default=50)
    s = db.add_parser("add"); s.add_argument("entity"); s.add_argument("--id")
    s.add_argument("--attr", action="append", help='AVEVA class attribute, e.g. "Rated Power=3200 kW"')
    s.add_argument("--set", action="append"); s.add_argument("--json"); s.add_argument("--reason", required=True)
    s = db.add_parser("update"); s.add_argument("entity"); s.add_argument("id")
    s.add_argument("--attr", action="append"); s.add_argument("--unset-attr", action="append")
    s.add_argument("--set", action="append"); s.add_argument("--unset", action="append"); s.add_argument("--json")
    s.add_argument("--reason", required=True)
    s = db.add_parser("delete"); s.add_argument("entity"); s.add_argument("id"); s.add_argument("--reason", required=True)
    s = db.add_parser("import"); s.add_argument("entity"); s.add_argument("file")
    s.add_argument("--update", action="store_true"); s.add_argument("--reason", required=True)
    s = db.add_parser("import-pcf", help="read routing from a PCF (Plant 3D / E3D) into pipe_component records")
    s.add_argument("file"); s.add_argument("--line", required=True); s.add_argument("--replace", action="store_true")
    s.add_argument("--valve-type", help="valve type for valves whose PCF gives none"); s.add_argument("--reason", required=True)
    s = db.add_parser("reconcile"); s.add_argument("entity", nargs="?"); s.add_argument("id", nargs="?")
    s.add_argument("--all", action="store_true"); s.add_argument("--reason", required=True)

    a = ap.parse_args(argv)
    if a.cmd == "run" and not (a.engine or a.all or a.stale):
        ap.error("run needs an engine name, --all or --stale")
    if a.cmd == "db" and a.op == "reconcile" and not (a.all or (a.entity and a.id)):
        ap.error("reconcile needs <entity> <id> or --all")
    p = Project.locate()
    fn = {"status": cmd_status, "validate": cmd_validate, "db": cmd_db, "engines": cmd_engines, "lib": cmd_lib, "plan": cmd_plan,
          "run": cmd_run, "deliver": cmd_deliver, "setup": cmd_setup, "kks": cmd_kks, "mdl": cmd_mdl, "doc": cmd_doc,
          "gate": cmd_gate}[a.cmd]
    try:
        return fn(p, a)
    except (StoreError, RuntimeError, ValueError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
