"""The single source of truth: one JSON file per record + per-user append-only changelog.

  database/records/<entity>/<id>.json      canonical, sorted-key JSON (clean git diffs)
  database/changelog/<USERCODE>.jsonl      one line per change: who, when, what, why, hash

Every write goes through Store, which validates, stamps _meta, writes the file and
logs the change. validate.integrity() then proves no record was touched by hand:
each record's hash must equal the hash logged for its current revision.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import identity as ident
from .project import Project
from .schema import Schema, check_record, load_schemas


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def rec_hash(rec: dict) -> str:
    return hashlib.sha256(canonical(rec).encode("utf-8")).hexdigest()[:16]


def dump(rec: dict) -> str:
    return json.dumps(rec, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class StoreError(Exception):
    pass


class Store:
    def __init__(self, project: Project, who: ident.Identity | None = None):
        self.p = project
        self.schemas: dict[str, Schema] = load_schemas(project.schema_dir)
        self._who = who
        self._cache: dict[str, dict[str, dict]] | None = None
        self._log_heads: dict | None = None

    # ------------------------------------------------------------------ read
    @property
    def who(self) -> ident.Identity:
        if self._who is None:
            self._who = ident.current(self.p.root)
        return self._who

    def schema(self, entity: str) -> Schema:
        if entity not in self.schemas:
            raise StoreError(f"unknown entity '{entity}'. Known: {', '.join(sorted(self.schemas))}")
        return self.schemas[entity]

    def path(self, entity: str, rid: str) -> Path:
        return self.p.records_dir / entity / f"{rid}.json"

    def all(self) -> dict[str, dict[str, dict]]:
        if self._cache is None:
            data: dict[str, dict[str, dict]] = {e: {} for e in self.schemas}
            for e in self.schemas:
                d = self.p.records_dir / e
                if d.is_dir():
                    for f in sorted(d.glob("*.json")):
                        txt = f.read_text(encoding="utf-8")
                        try:
                            data[e][f.stem] = json.loads(txt)
                        except json.JSONDecodeError as err:
                            hint = " - unresolved git merge conflict: edit the file to the intended content, then " \
                                   f"python -m engine db reconcile {e} {f.stem} --reason ..." if "<<<<<<<" in txt else ""
                            raise StoreError(f"{e}/{f.name} is not valid JSON ({err}){hint}") from None
            self._cache = data
        return self._cache

    def records(self, entity: str) -> list[dict]:
        self.schema(entity)
        return [self.all()[entity][k] for k in sorted(self.all()[entity])]

    def get(self, entity: str, rid: str) -> dict | None:
        self.schema(entity)
        return self.all()[entity].get(rid)

    def entity_hash(self, entities) -> str:
        """Content fingerprint of the given entities (used for output staleness)."""
        h = hashlib.sha256()
        for e in sorted(entities):
            for rid, rec in sorted(self.all().get(e, {}).items()):
                h.update(f"{e}/{rid}:{rec_hash(rec)}\n".encode())
        return h.hexdigest()[:16]

    def db_hash(self) -> str:
        return self.entity_hash(self.schemas)

    def resolve_ref(self, schema: Schema, fname: str, value: str) -> tuple[str, str] | None:
        if schema.fields[fname]["type"] == "logic_list":
            from .schema import LOGIC_RE
            m = LOGIC_RE.match(value)
            return (schema.targets(fname)[0], m["id"]) if m else None
        if schema.multi_target(fname):
            if ":" not in value:
                return None
            ent, rid = value.split(":", 1)
            return (ent, rid) if ent in schema.targets(fname) else None
        return schema.targets(fname)[0], value

    def referrers(self, entity: str, rid: str) -> list[str]:
        out = []
        for e, s in self.schemas.items():
            for f, spec in s.fields.items():
                if spec["type"] not in ("ref", "ref_list", "logic_list") or entity not in s.targets(f):
                    continue
                for r in self.all()[e].values():
                    vals = r.get(f) or []
                    vals = vals if isinstance(vals, list) else [vals]
                    for v in vals:
                        if self.resolve_ref(s, f, v) == (entity, rid):
                            out.append(f"{e}/{r['id']}.{f}")
        return out

    @property
    def lib(self):
        from . import classlib
        return classlib.get(self.p)

    def class_errors(self, entity: str, rec: dict) -> list[str]:
        s = self.schema(entity)
        errs = []
        for f, spec in s.fields.items():
            if spec["type"] != "aveva_class" or not rec.get(f):
                continue
            if self.lib is None:
                return [f"{f}: AVEVA class library not built (python -m engine lib build <ttl> --reason ...)"]
            try:
                cls = self.lib.resolve(rec[f])
            except KeyError as e:
                errs.append(f"{f}: {e.args[0]}")
                continue
            if spec.get("roots") and not self.lib.is_under(cls, spec["roots"]):
                errs.append(f"{f}: '{cls['label']}' is not under {spec['roots']} in the AVEVA class tree")
            for af, aspec in s.fields.items():
                if aspec["type"] == "aveva_attrs" and aspec.get("class_field") == f and rec.get(af):
                    errs += [f"{af}: {e}" for e in self.lib.attr_errors(cls, rec[af])]
        for af, aspec in s.fields.items():
            if aspec["type"] == "aveva_attrs" and rec.get(af) and not rec.get(aspec.get("class_field", "")):
                errs.append(f"{af}: set {aspec.get('class_field')} first - attributes are defined by the class")
        return errs

    def ref_errors(self, entity: str, rec: dict) -> list[str]:
        s = self.schema(entity)
        errs = []
        for f, spec in s.fields.items():
            if spec["type"] not in ("ref", "ref_list", "logic_list") or rec.get(f) is None:
                continue
            vals = rec[f] if isinstance(rec[f], list) else [rec[f]]
            for v in vals:
                tgt = self.resolve_ref(s, f, v)
                if tgt is None:
                    errs.append(f"{f}: '{v}' must be written as <entity>:<id> with entity in {s.targets(f)}")
                elif tgt[1] not in self.all()[tgt[0]]:
                    errs.append(f"{f}: '{v}' -> {tgt[0]}/{tgt[1]} does not exist")
        return errs

    # ----------------------------------------------------------------- write
    def next_id(self, entity: str) -> str:
        s = self.schema(entity)
        if not s.id_prefix:
            raise StoreError(f"{entity} has no auto-id; give --id (e.g. the plant tag / document number)")
        stem = f"{s.id_prefix}-{self.who.code}-"
        nums = [int(m.group(1)) for rid in self.all()[entity] if (m := re.fullmatch(re.escape(stem) + r"(\d+)", rid))]
        return f"{stem}{(max(nums) + 1 if nums else 1):04d}"

    @staticmethod
    def _id_from(s: Schema, data: dict) -> str:
        missing = [f for f in s.id_from if not data.get(f)]
        if missing:
            raise StoreError(f"{s.entity}: id is built from {s.id_from}; missing {missing}")
        return re.sub(r"[^A-Za-z0-9._-]", "-", "_".join(str(data[f]) for f in s.id_from))

    def _log(self, op: str, entity: str, rid: str, rev: int, h: str | None, reason: str, fields=None):
        if not reason or not reason.strip():
            raise StoreError("a --reason is required for every change (it is the audit trail)")
        entry = {"ts": now(), **self.who.stamp(), "op": op, "entity": entity, "id": rid,
                 "rev": rev, "hash": h, "reason": reason.strip()}
        if fields:
            entry["fields"] = sorted(fields)
        self.p.changelog_dir.mkdir(parents=True, exist_ok=True)
        with open(self.p.changelog_dir / f"{self.who.code}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(canonical(entry) + "\n")
        if self._log_heads is not None:
            self._log_heads.setdefault((entity, rid), []).append(entry)

    def _write(self, entity: str, rec: dict):
        f = self.path(entity, rec["id"])
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(dump(rec), encoding="utf-8")
        self.all()[entity][rec["id"]] = rec

    def _check(self, entity: str, rec: dict):
        errs = check_record(self.schema(entity), rec) + self.ref_errors(entity, rec) + self.class_errors(entity, rec)
        if errs:
            raise StoreError(f"{entity}/{rec.get('id')}: " + "; ".join(errs))

    def _case_clash(self, entity: str, rid: str) -> str | None:
        return next((k for k in self.all()[entity] if k.lower() == rid.lower() and k != rid), None)

    def create(self, entity: str, data: dict, reason: str) -> dict:
        s = self.schema(entity)
        data = {k: v for k, v in data.items() if v is not None}
        rid = data.get("id") or (self._id_from(s, data) if s.id_from else self.next_id(entity))
        if rid in self.all()[entity] or self._case_clash(entity, rid):
            raise StoreError(f"{entity}/{rid} already exists (IDs are case-insensitive). Use update.")
        for f, spec in s.fields.items():
            if f not in data and "default" in spec:
                data[f] = spec["default"]
        # an ID that existed before (deleted) continues its revision history
        prev = self._heads(entity, rid)
        if prev and prev[0].get("op") != "delete":
            raise StoreError(f"{entity}/{rid} is logged as existing but its file is missing - restore it or reconcile")
        rev = (int(prev[0]["rev"]) + 1) if prev else 1
        ts = now()
        rec = {**data, "id": rid, "_meta": {"rev": rev, "created_by": self.who.code, "created_at": ts,
                                            "updated_by": self.who.code, "updated_at": ts}}
        self._check(entity, rec)
        self._write(entity, rec)
        self._log("create", entity, rid, rev, rec_hash(rec), reason, [k for k in data if k != "id"])
        return rec

    def _heads(self, entity: str, rid: str) -> list[dict]:
        """Changelog entries at the highest revision of a record (normally one)."""
        if self._log_heads is None:
            heads: dict = {}
            for e in read_changelog(self.p)[0]:
                heads.setdefault((e.get("entity"), e.get("id")), []).append(e)
            self._log_heads = heads
        log = self._log_heads.get((entity, rid), [])
        top = max((int(e.get("rev", 0)) for e in log), default=None)
        return [e for e in log if int(e.get("rev", 0)) == top]

    def _assert_logged(self, entity: str, rid: str, rec: dict):
        """Never build on a hand-edited or unreconciled record (would launder the edit into the log)."""
        heads = self._heads(entity, rid)
        top = int(heads[0]["rev"]) if heads else None
        ok = len(heads) == 1 and rec.get("_meta", {}).get("rev") == top and heads[0].get("hash") == rec_hash(rec)
        if not ok:
            raise StoreError(f"{entity}/{rid} differs from its logged state (hand edit or unreconciled merge). "
                             f"Check it, then: python -m engine db reconcile {entity} {rid} --reason ...")

    def update(self, entity: str, rid: str, changes: dict, reason: str) -> dict:
        old = self.get(entity, rid)
        if old is None:
            raise StoreError(f"{entity}/{rid} does not exist")
        self._assert_logged(entity, rid, old)
        if "id" in changes and changes["id"] != rid:
            raise StoreError("IDs cannot be changed; create a new record and delete the old one")
        rec = {k: v for k, v in old.items() if k != "_meta"}
        touched = []
        for k, v in changes.items():
            if k == "id":
                continue
            if v is None:
                if k in rec:
                    rec.pop(k); touched.append(k)
            elif rec.get(k) != v:
                rec[k] = v; touched.append(k)
        if not touched:
            return old
        meta = dict(old["_meta"])
        meta.update(rev=meta["rev"] + 1, updated_by=self.who.code, updated_at=now())
        rec["_meta"] = meta
        self._check(entity, rec)
        self._write(entity, rec)
        self._log("update", entity, rid, meta["rev"], rec_hash(rec), reason, touched)
        return rec

    def delete(self, entity: str, rid: str, reason: str):
        old = self.get(entity, rid)
        if old is None:
            raise StoreError(f"{entity}/{rid} does not exist")
        self._assert_logged(entity, rid, old)
        refs = self.referrers(entity, rid)
        if refs:
            raise StoreError(f"{entity}/{rid} is still referenced by: {', '.join(refs[:10])}")
        self.path(entity, rid).unlink()
        del self.all()[entity][rid]
        self._log("delete", entity, rid, old["_meta"]["rev"] + 1, None, reason)

    def reconcile(self, entity: str, rid: str, reason: str, heads_rev: int) -> str:
        """Accept the current on-disk state after a git merge / manual resolution."""
        f = self.path(entity, rid)
        new_rev = heads_rev + 1
        if not f.exists():
            self._log("delete", entity, rid, new_rev, None, reason)
            return "logged as deleted"
        rec = json.loads(f.read_text(encoding="utf-8"))
        meta = dict(rec.get("_meta") or {})
        meta.setdefault("created_by", self.who.code)
        meta.setdefault("created_at", now())
        meta.update(rev=new_rev, updated_by=self.who.code, updated_at=now())
        rec["_meta"] = meta
        self._check(entity, rec)
        self._write(entity, rec)
        self._log("reconcile", entity, rid, new_rev, rec_hash(rec), reason)
        return f"accepted at rev {new_rev}"


def read_changelog(project: Project) -> tuple[list[dict], list[str]]:
    entries, errs = [], []
    d = project.changelog_dir
    if not d.is_dir():
        return entries, errs
    for f in sorted(d.glob("*.jsonl")):
        emails = set()
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                errs.append(f"changelog/{f.name}:{n} is not valid JSON (merge damage?)")
                continue
            if e.get("user") != f.stem:
                errs.append(f"changelog/{f.name}:{n} written by user '{e.get('user')}' (file belongs to {f.stem})")
            emails.add(e.get("email"))
            e["_src"] = f"{f.name}:{n}"
            entries.append(e)
        if len(emails) > 1:
            errs.append(f"changelog/{f.name}: user code {f.stem} is used by several people {sorted(emails)} "
                        "- each person needs a unique code (git config alpilla.usercode)")
    return entries, errs
