"""AVEVA class library (compiled into database/classlib/ by `python -m engine lib build`).

Records may carry an AVEVA class (`class` field) and class attributes (`attrs` field):
    "class": "Centrifugal Pump",
    "attrs": {"Rated Power": {"value": 3200, "unit": "kW"}, "Casing Material": "A216 WCB"}
Attributes are validated against the class and its ancestors: name, data type, unit (must belong to the
attribute's quantity class; units are stored as given - the library has no conversion factors) and
closed value lists (LOV). Attribute names that are ambiguous for a class must be given by AVEVA ID.
"""
from __future__ import annotations

import difflib
import json
from functools import lru_cache
from pathlib import Path


class ClassLib:
    def __init__(self, folder: Path):
        self.folder = folder
        load = lambda n: [json.loads(l) for l in (folder / f"{n}.jsonl").read_text(encoding="utf-8").splitlines() if l]
        self.classes = {c["id"]: c for c in load("classes")}
        self.attributes = {a["id"]: a for a in load("attributes")}
        self.enums = {e["id"]: e for e in load("enums")}
        self.quantities = {q["label"]: q for q in load("quantities")}
        self.associations = load("associations")
        self._by_label: dict[str, list[str]] = {}
        for c in self.classes.values():
            self._by_label.setdefault(c["label"].lower(), []).append(c["id"])
        self._children: dict[str, list[str]] = {}
        for c in self.classes.values():
            for p in [c.get("parent")] + c.get("other_parents", []):
                if p:
                    self._children.setdefault(p, []).append(c["id"])
        self._eff: dict[str, dict] = {}

    # ------------------------------------------------------------ classes
    def resolve(self, name: str) -> dict:
        if name in self.classes:
            return self.classes[name]
        ids = self._by_label.get(name.lower(), [])
        if len(ids) == 1:
            return self.classes[ids[0]]
        if len(ids) > 1:
            raise KeyError(f"class name '{name}' is ambiguous - use one of the AVEVA IDs {ids}")
        close = difflib.get_close_matches(name.lower(), self._by_label, n=3, cutoff=0.6)
        hint = f" Did you mean: {', '.join(self.classes[self._by_label[c][0]]['label'] for c in close)}?" if close else ""
        raise KeyError(f"unknown AVEVA class '{name}'.{hint} Search: python -m engine lib find <text>")

    def ancestors(self, cls: dict) -> list[dict]:
        out, seen, todo = [], set(), [cls["id"]]
        while todo:
            cid = todo.pop(0)
            if cid in seen or cid not in self.classes:
                continue
            seen.add(cid)
            c = self.classes[cid]
            out.append(c)
            todo += [p for p in [c.get("parent")] + c.get("other_parents", []) if p]
        return out

    def is_under(self, cls: dict, roots: list[str]) -> bool:
        names = {a["label"] for a in self.ancestors(cls)} | {a["id"] for a in self.ancestors(cls)}
        return any(r in names for r in roots)

    def subtree_size(self, cid: str) -> int:
        return 1 + sum(self.subtree_size(k) for k in self._children.get(cid, []))

    def find(self, text: str, roots: list[str] | None = None, limit: int = 30) -> list[dict]:
        t = text.lower()
        hits = [c for c in self.classes.values() if t in c["label"].lower() or t == c["id"].lower()
                or t == c.get("cfihos", "").lower()]
        if roots:
            hits = [c for c in hits if self.is_under(c, roots)]
        return sorted(hits, key=lambda c: (not c["label"].lower().startswith(t), len(c["label"])))[:limit]

    # --------------------------------------------------------- attributes
    def effective(self, cls: dict) -> dict[str, dict]:
        """name -> attribute for the class incl. inherited ones. Ambiguous names only by AVEVA ID."""
        if cls["id"] not in self._eff:
            ids = {a for c in self.ancestors(cls) for a in c.get("attrs", [])}
            by_label: dict[str, list[dict]] = {}
            for i in ids:
                a = self.attributes[i]
                by_label.setdefault(a["label"], []).append(a)
            eff = {a["id"]: a for a in (self.attributes[i] for i in ids)}
            for label, lst in by_label.items():
                if len(lst) == 1:
                    eff[label] = lst[0]
            self._eff[cls["id"]] = eff
        return self._eff[cls["id"]]

    def attr_errors(self, cls: dict, attrs: dict) -> list[str]:
        errs = []
        eff = self.effective(cls)
        for name, v in attrs.items():
            a = eff.get(name)
            if a is None:
                close = difflib.get_close_matches(name, [k for k in eff if not k.startswith("AVEVA-")], n=3)
                errs.append(f"attribute '{name}' is not defined for class '{cls['label']}'"
                            + (f" (did you mean {', '.join(close)}?)" if close else ""))
                continue
            errs += [f"attribute '{name}': {e}" for e in self.value_errors(a, v)]
        return errs

    def value_errors(self, a: dict, v) -> list[str]:
        t = a["type"]
        if t == "quantity":
            if not (isinstance(v, dict) and set(v) == {"value", "unit"}):
                return ['needs {"value": <number>, "unit": "<unit>"} (CLI: "Name=3200 kW")']
            if isinstance(v["value"], bool) or not isinstance(v["value"], (int, float)):
                return ["value must be a number"]
            units = self.quantities.get(a.get("quantity"), {}).get("units", [])
            if units and v["unit"] not in units:
                return [f"unit '{v['unit']}' not valid for {a.get('quantity')}; allowed: {', '.join(units[:25])}"]
            return []
        if t == "int":
            return [] if isinstance(v, int) and not isinstance(v, bool) else ["must be an integer"]
        if t == "double":
            return [] if isinstance(v, (int, float)) and not isinstance(v, bool) else ["must be a number"]
        if t == "boolean":
            return [] if isinstance(v, bool) else ["must be true/false"]
        if not isinstance(v, str) or not v.strip():
            return ["must be a non-empty text"]
        lov = self.enums.get(a.get("lov", ""))
        if lov and lov["closed"] and v not in lov["values"]:
            return [f"'{v}' not in {lov['label']}: {', '.join(lov['values'][:20])}{' ...' if len(lov['values']) > 20 else ''}"]
        return []

    def parse_cli(self, cls: dict, name: str, raw: str):
        """CLI text -> typed attribute value."""
        a = self.effective(cls).get(name)
        if a is None:
            return raw  # reported by attr_errors with suggestions
        t = a["type"]
        if t == "quantity":
            parts = raw.rsplit(None, 1)
            if len(parts) != 2:
                raise ValueError(f"attribute '{name}' needs a value and a unit, e.g. \"{name}=3200 kW\"")
            return {"value": float(parts[0]) if any(c in parts[0] for c in ".eE") else int(parts[0]), "unit": parts[1]}
        if t == "int":
            return int(raw)
        if t == "double":
            return float(raw)
        if t == "boolean":
            return raw.lower() in ("true", "yes", "1", "y")
        return raw

    def describe_attr(self, a: dict) -> str:
        s = f"{a['label']}  [{a['type']}{' ' + a['quantity'] if a.get('quantity') else ''}]  {a['id']}"
        if a.get("quantity"):
            q = self.quantities.get(a["quantity"], {})
            s += f"\n    units (base {q.get('base')}): {', '.join(q.get('units', [])[:30])}"
        if a.get("lov"):
            e = self.enums[a["lov"]]
            s += f"\n    {'closed' if e['closed'] else 'open'} list {e['label']}: {', '.join(e['values'][:40])}"
        if a.get("comment"):
            s += f"\n    {a['comment'][:200]}"
        return s


@lru_cache(maxsize=4)
def _load(folder: str, stamp: float) -> ClassLib:
    return ClassLib(Path(folder))


def get(project) -> ClassLib | None:
    folder = project.database / "classlib"
    m = folder / "manifest.json"
    if not m.exists():
        return None
    return _load(str(folder), m.stat().st_mtime)
