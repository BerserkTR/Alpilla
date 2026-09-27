"""Entity schemas (database/schema/<entity>.json) and record validation.

Field types:
  string, text, number, integer, boolean, date (YYYY-MM-DD),
  enum      -> "values": [...]
  ref       -> "to": "entity"            value = "<id>"
               "to": ["a", "b"]          value = "<entity>:<id>"
  ref_list  -> as ref, but a list of values
  list      -> list of strings
  aveva_class -> AVEVA class name or AVEVA ID; "roots": [...] limits it to branches of the class tree
  aveva_attrs -> {"<AVEVA attribute>": value}; validated against the record's aveva_class (see classlib.py)
  point     -> [x, y, z] plant coordinates in mm (East, North, Elevation)
  logic_list -> planning links "<id>[:FS|SS|FF|SF[+/-lag]]" to "to" entity, e.g. ["E-1010", "E-1020:SS+5"]
Schema key "id_from": [fields] builds the id from those fields joined by "_" (e.g. document + revision).
Schema key "required_when": {"field": "type", "rules": {"PIPE": ["end1", "end2"], ...}} adds requirements per value.
Common keys: required, unit, description, default, min, max, pattern.
Unknown fields are rejected: the schema is the contract.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
TYPES = {"string", "text", "number", "integer", "boolean", "date", "enum", "ref", "ref_list", "list",
         "aveva_class", "aveva_attrs", "logic_list", "point"}
LOGIC_RE = re.compile(r"^(?P<id>[A-Za-z0-9][A-Za-z0-9._-]*)(?::(?P<rel>FS|SS|FF|SF)(?P<lag>[+-]\d+)?)?$")


def parse_logic(v: str) -> tuple[str, str, int]:
    """'E-1010' -> (E-1010, FS, 0); 'E-1010:SS+5' -> (E-1010, SS, 5); lag in working days.
    A lag needs an explicit link type ('E-1010:FS-3'), because IDs themselves contain '-' and digits."""
    m = LOGIC_RE.match(v)
    if not m:
        raise ValueError(v)
    return m["id"], m["rel"] or "FS", int(m["lag"] or 0)


@dataclass
class Schema:
    entity: str
    title: str
    id_prefix: str | None          # set -> IDs may be auto-generated as PREFIX-USER-NNNN
    id_pattern: re.Pattern | None
    fields: dict = field(default_factory=dict)
    display: list = field(default_factory=list)   # default columns for listings
    description: str = ""
    id_from: list = field(default_factory=list)
    required_when: dict = field(default_factory=dict)

    def targets(self, fname: str) -> list[str]:
        to = self.fields[fname].get("to")
        return [to] if isinstance(to, str) else list(to or [])

    def multi_target(self, fname: str) -> bool:
        return isinstance(self.fields[fname].get("to"), list)


def load_schemas(schema_dir: Path) -> dict[str, Schema]:
    out: dict[str, Schema] = {}
    for p in sorted(schema_dir.glob("*.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))
        ent = raw["entity"]
        if ent != p.stem:
            raise ValueError(f"{p.name}: entity '{ent}' must match file name")
        for fname, spec in raw["fields"].items():
            if spec.get("type") not in TYPES:
                raise ValueError(f"{p.name}: field '{fname}' has unknown type {spec.get('type')!r}")
            if fname.startswith("_") or fname == "id":
                raise ValueError(f"{p.name}: field name '{fname}' is reserved")
        out[ent] = Schema(ent, raw.get("title", ent), raw.get("id_prefix"),
                          re.compile(raw["id_pattern"]) if raw.get("id_pattern") else None,
                          raw["fields"], raw.get("display", []), raw.get("description", ""), raw.get("id_from", []),
                          raw.get("required_when", {}))
    for s in out.values():  # ref targets must exist
        for fname, spec in s.fields.items():
            if spec["type"] in ("ref", "ref_list", "logic_list"):
                for t in s.targets(fname):
                    if t not in out:
                        raise ValueError(f"{s.entity}.{fname}: ref target '{t}' has no schema")
    return out


def coerce(schema: Schema, fname: str, raw: str):
    """Turn a CLI string into a typed value according to the schema."""
    if fname not in schema.fields:
        raise ValueError(f"{schema.entity}: unknown field '{fname}'. Fields: {', '.join(schema.fields)}")
    t = schema.fields[fname]["type"]
    if raw.strip().startswith("[") and t in ("list", "ref_list", "logic_list", "point"):
        return json.loads(raw)
    if t == "number":
        return float(raw) if any(c in raw for c in ".eE") else int(raw)
    if t == "integer":
        return int(raw)
    if t == "boolean":
        if raw.lower() in ("true", "yes", "1", "y"): return True
        if raw.lower() in ("false", "no", "0", "n"): return False
        raise ValueError(f"{fname}: not a boolean: {raw}")
    if t in ("list", "ref_list", "logic_list"):
        return [x.strip() for x in raw.split(",") if x.strip()]
    if t == "point":
        parts = [p for p in raw.replace(";", ",").split(",") if p.strip()]
        if len(parts) != 3:
            raise ValueError(f"{fname}: needs x,y,z in mm, got '{raw}'")
        return [float(p) if any(c in p for c in ".eE") else int(p) for p in parts]
    return raw


def check_record(schema: Schema, rec: dict) -> list[str]:
    """Structural checks of one record (refs are checked store-wide elsewhere)."""
    errs: list[str] = []
    rid = rec.get("id")
    if not isinstance(rid, str) or not ID_RE.match(rid):
        errs.append(f"id {rid!r} invalid (letters, digits, . _ -; no spaces)")
    elif schema.id_pattern and not schema.id_pattern.match(rid):
        errs.append(f"id '{rid}' does not match pattern {schema.id_pattern.pattern}")
    for k in rec:
        if k not in ("id", "_meta") and k not in schema.fields:
            errs.append(f"unknown field '{k}'")
    rw = schema.required_when
    needed = set(rw.get("rules", {}).get(rec.get(rw.get("field")), [])) if rw else set()
    for fname, spec in schema.fields.items():
        v = rec.get(fname)
        if v is None:
            if fname in needed:
                errs.append(f"'{fname}' is required when {rw['field']} = {rec.get(rw['field'])}")
            elif spec.get("required"):
                errs.append(f"required field '{fname}' missing")
            continue
        errs += [f"{fname}: {e}" for e in _check_value(spec, v)]
    return errs


def _check_value(spec: dict, v) -> list[str]:
    t = spec["type"]
    if t == "aveva_class":
        return [] if isinstance(v, str) and v.strip() else ["must be an AVEVA class name or ID"]
    if t == "aveva_attrs":
        return [] if isinstance(v, dict) and all(isinstance(k, str) for k in v) else ["must be an object {attribute: value}"]
    if t in ("string", "text", "ref"):
        if not isinstance(v, str) or not v.strip():
            return ["must be a non-empty string"]
        if spec.get("pattern") and not re.match(spec["pattern"], v):
            return [f"'{v}' does not match {spec['pattern']}"]
        return []
    if t == "enum":
        return [] if v in spec["values"] else [f"'{v}' not in {spec['values']}"]
    if t in ("number", "integer"):
        ok = isinstance(v, int) if t == "integer" else isinstance(v, (int, float))
        if isinstance(v, bool) or not ok:
            return [f"must be {t}"]
        if "min" in spec and v < spec["min"]: return [f"{v} < min {spec['min']}"]
        if "max" in spec and v > spec["max"]: return [f"{v} > max {spec['max']}"]
        return []
    if t == "boolean":
        return [] if isinstance(v, bool) else ["must be true/false"]
    if t == "date":
        try:
            date.fromisoformat(v)
            return []
        except Exception:
            return [f"'{v}' is not YYYY-MM-DD"]
    if t == "point":
        ok = isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)
        return [] if ok else ["must be [x, y, z] in mm"]
    if t == "logic_list":
        if not isinstance(v, list) or not all(isinstance(x, str) and LOGIC_RE.match(x) for x in v):
            return ['must be a list like ["E-1010", "E-1020:SS+5", "E-1030:FF-2"]']
        ids = [parse_logic(x)[0] for x in v]
        return ["duplicate predecessor"] if len(set(ids)) != len(ids) else []
    if t in ("list", "ref_list"):
        if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
            return ["must be a list of non-empty strings"]
        if spec.get("min_items") and len(v) < spec["min_items"]:
            return [f"needs at least {spec['min_items']} item(s)"]
        if len(set(v)) != len(v):
            return ["duplicate items"]
        return []
    return [f"unsupported type {t}"]


def describe(schema: Schema) -> str:
    lines = [f"{schema.entity}: {schema.title}" + (f"  (auto id: {schema.id_prefix}-<USER>-NNNN)" if schema.id_prefix else "")]
    for fname, s in schema.fields.items():
        extra = []
        if s.get("required"): extra.append("required")
        if s.get("unit"): extra.append(f"unit={s['unit']}")
        if s.get("to"): extra.append(f"to={s['to']}")
        if s.get("roots"): extra.append("AVEVA branch=" + "|".join(s["roots"]))
        if s.get("values"): extra.append("values=" + "|".join(s["values"]))
        lines.append(f"  {fname:<22} {s['type']:<9} {' '.join(extra)}")
    return "\n".join(lines)
