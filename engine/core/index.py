"""Local SQLite index of the JSON records (database/.cache/index.sqlite, never committed).

Rebuilt automatically whenever the records change, so any user/agent can run
compact SQL queries instead of opening many record files (saves tokens and time).
Tables: one per entity, one column per schema field (lists stored as JSON text),
plus meta_rev, meta_updated_by, meta_updated_at. Also `changelog` (all users).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from .project import Project
from .store import Store, read_changelog

SQL_TYPES = {"number": "NUMERIC", "integer": "INTEGER", "boolean": "INTEGER"}
INDEX_FORMAT = "3"  # bump when the index layout changes, forces a rebuild everywhere


def _fingerprint(p: Project) -> str:
    h = hashlib.sha256(INDEX_FORMAT.encode())
    for d in (p.records_dir, p.changelog_dir, p.schema_dir):
        for f in sorted(d.rglob("*")) if d.is_dir() else []:
            if f.is_file():
                st = f.stat()
                h.update(f"{f.relative_to(p.root)}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def ensure(p: Project, store: Store | None = None, force: bool = False) -> bool:
    """(Re)build the index if stale. Returns True if rebuilt."""
    fp = _fingerprint(p)
    if not force and p.index_path.exists():
        try:
            with sqlite3.connect(p.index_path) as c:
                if c.execute("SELECT v FROM _index WHERE k='fingerprint'").fetchone()[0] == fp:
                    return False
        except Exception:
            pass
    store = store or Store(p)
    p.cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = p.index_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    c = sqlite3.connect(tmp)
    c.execute("CREATE TABLE _index (k TEXT PRIMARY KEY, v TEXT)")
    c.execute("INSERT INTO _index VALUES ('fingerprint', ?)", (fp,))
    for entity, s in store.schemas.items():
        cols = [("id", "TEXT PRIMARY KEY")] + [(f, SQL_TYPES.get(spec["type"], "TEXT")) for f, spec in s.fields.items()]
        cols += [("meta_rev", "INTEGER"), ("meta_updated_by", "TEXT"), ("meta_updated_at", "TEXT")]
        c.execute(f'CREATE TABLE "{entity}" ({", ".join(f"{n} {t}" for n, t in cols)})')
        rows = []
        for r in store.records(entity):
            m = r.get("_meta", {})
            vals = [r["id"]] + [json.dumps(r[f], ensure_ascii=False, sort_keys=True) if isinstance(r.get(f), (list, dict)) else r.get(f)
                                for f in s.fields] + [m.get("rev"), m.get("updated_by"), m.get("updated_at")]
            rows.append(vals)
        if rows:
            c.executemany(f'INSERT INTO "{entity}" VALUES ({",".join("?" * len(cols))})', rows)
    c.execute("CREATE TABLE changelog (ts TEXT, user TEXT, name TEXT, agent TEXT, op TEXT, entity TEXT, "
              "id TEXT, rev INTEGER, reason TEXT, fields TEXT)")
    entries, _ = read_changelog(p)
    c.executemany("INSERT INTO changelog VALUES (?,?,?,?,?,?,?,?,?,?)",
                  [(e.get("ts"), e.get("user"), e.get("name"), e.get("agent"), e.get("op"), e.get("entity"),
                    e.get("id"), e.get("rev"), e.get("reason"), json.dumps(e.get("fields", []))) for e in entries])
    c.commit()
    c.close()
    tmp.replace(p.index_path)
    return True


def query(p: Project, sql: str, limit: int = 50) -> tuple[list[str], list[tuple], bool]:
    ensure(p)
    c = sqlite3.connect(f"file:{p.index_path}?mode=ro", uri=True)
    try:
        cur = c.execute(sql)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(limit + 1)
    finally:
        c.close()
    return cols, rows[:limit], len(rows) > limit
