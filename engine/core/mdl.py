"""MDL rules: which documents the project needs, derived from the records (never typed).

An `mdl_rule` says: for every plant / system / structure / construction area (CWA) / procurement package (MR) that matches
its filters, the project needs document(s) of a type, with a number of sheets from a quantity (a system `q_` field, summed
over the systems of the scope; the register count replaces the estimate when it is larger), hours, inputs (other rules),
EWP / MR links and, for supplier documents, the timing after the purchase order. `required()` expands the rules into
instances; `plan_sync()` compares them with the document records:
  create  - instance without a document (new number allocated per ALP-<ORG>-<KKS>-<DISC>-<TYPE>-<NNNN>)
  update  - rule-managed document whose sheets, hours, links or inputs differ from the rule (its rule-generated inputs
            are exactly those the rule resolves to; manual inputs and supplier documents with committed dates are kept)
  orphan  - document whose rule instance no longer exists, or whose type changed (the number changes: a new document is
            created); reported, cancelled only with mdl sync --apply --cancel-orphans, never deleted
A document is rule-managed when its `rule` field holds the instance key <rule id>|<scope key>|<part>."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from . import kks

ACTUAL = {"q_equipment": "equipment", "q_instruments": "instrument", "q_lines": "line"}
FALLBACK = {"PI": ["ME", "HV", "CV"], "IC": ["PI", "EL", "CV"], "EL": ["CV"], "SS": ["CV"], "HV": ["CV"], "ME": ["PI", "CV"], "CV": ["SS"]}
DRAWING_CATS = {"drawing", "diagram", "layout", "isometric"}
SPEC_CATS = {"specification", "datasheet"}


class MdlError(Exception):
    pass


@dataclass
class Inst:
    key: str
    rule: dict
    scope_key: str
    part: int
    parts: int
    name: str
    kks: str
    org: str
    sheets: int
    hours: float
    systems: set = field(default_factory=set)
    cwa: str | None = None
    ewp: str | None = None
    mr: str | None = None
    inputs: list = field(default_factory=list)
    doc_id: str | None = None
    equipment: list = field(default_factory=list)

    @property
    def title(self):
        t = self.rule["title"].format(name=self.name, part=self.part, kks=self.kks).strip(" -")
        if self.parts > 1 and "{part}" not in self.rule["title"]:
            t += f" - part {self.part} of {self.parts}"
        return t


class Ctx:
    def __init__(self, store):
        self.store = store
        self.systems = {s["id"]: s for s in store.records("system")}
        self.cwas = {c["id"]: c for c in store.records("cwa")}
        self.mrs = {m["id"]: m for m in store.records("mr")}
        self.cwps = {c["id"]: c for c in store.records("cwp")}
        self.ewps = sorted(e["id"] for e in store.records("ewp"))
        self.types = {t["id"]: t for t in store.records("doc_type")}
        self.actual = defaultdict(lambda: defaultdict(int))        # field -> system -> count
        for f, ent in ACTUAL.items():
            if ent not in store.schemas:
                continue
            for r in store.records(ent):
                if r.get("status") == "deleted":
                    continue
                sy = r.get("system") or r["id"][:5]
                self.actual[f][sy] += 1
        self.eq_mr = defaultdict(set)
        self.tags_mr = defaultdict(list)
        self.equipment = [e for e in store.records("equipment") if e.get("status") != "deleted"]
        for e in self.equipment:
            if e.get("mr") and e.get("system"):
                self.eq_mr[e["mr"]].add(e["system"])
                self.tags_mr[e["mr"]].append(e["id"])

    def q(self, sy: str, f: str) -> int:
        s = self.systems.get(sy, {})
        return max(s.get(f) or 0, self.actual[f].get(sy, 0) if f in ACTUAL else 0)

    def cwa_of(self, sy: str):
        c = self.systems.get(sy, {}).get("cwas") or []
        return c[0] if c else None

    def mr_cwa(self, mid: str):
        for c in self.mrs.get(mid, {}).get("cwps", []):
            if c in self.cwps:
                return self.cwps[c]["cwa"]
        return None

    def ewp_for(self, cwa: str | None, disc: str, seq: int | None):
        """EWP of the CWP of `disc` in the CWA; when the CWA has no CWP of that discipline the work is done under the
        next one of FALLBACK (e.g. steel of a small structure under the civil CWP)."""
        if not cwa:
            return None
        for dd in [disc] + FALLBACK.get(disc, []):
            cands = [e for e in self.ewps if e.startswith(f"EWP-{cwa[4:]}-{dd}-")]
            if seq and dd == disc:
                cands = [e for e in cands if e.endswith(f"-{seq:02d}")] or cands
            if cands:
                return cands[-1]
        return None

    def org(self, rule, mid):
        if rule["originator"] != "SUPPLIER":
            return rule["originator"]
        m = self.mrs.get(mid or "")
        if not m:
            raise MdlError(f"{rule['id']}: supplier document without MR")
        if m.get("package_type") == "iec_supply":
            return "IEC"
        if not m.get("supplier_code"):
            raise MdlError(f"{rule['id']}: {mid} has no supplier_code")
        return m["supplier_code"]


def _scopes(rule, c: Ctx):
    """[(scope key, name, kks, systems, cwa, mr, own quantity or None)]"""
    sc, out = rule["scope"], []
    only, excl = set(rule.get("systems") or []), set(rule.get("exclude") or [])
    cats, parties = set(rule.get("categories") or []), set(rule.get("parties") or [])

    def sys_ok(s):
        return (not cats or s.get("category") in cats) and (not parties or s.get("scope") in parties)

    if sc == "plant":
        sy = {k for k, s in c.systems.items() if len(k) == 5 and sys_ok(s) and (not only or k in only)}
        out.append(("00000", "", rule.get("kks") or "00000", sy, rule.get("cwa"),
                    rule.get("mr"), None))
    elif sc in ("system", "structure"):
        for k, s in sorted(c.systems.items()):
            if len(k) != 5 or (k[2] == "U") != (sc == "structure") or k in excl:
                continue
            if (only and k not in only) or not sys_ok(s):
                continue
            mr = rule.get("mr") or (s.get("mr") if (c.types.get(rule["type_code"], {}).get("procurement")
                                                    or rule["originator"] == "SUPPLIER") else None)
            out.append((k, s["title"], k, {k}, c.cwa_of(k), mr, None))
    elif sc == "cwa":
        for k, a in sorted(c.cwas.items()):
            if k in excl or (only and k not in only):
                continue
            sy = {x for x, s in c.systems.items() if k in (s.get("cwas") or []) and sys_ok(s)}
            out.append((k, a["title"], (a.get("structures") or ["00000"])[0], sy, k, rule.get("mr"), None))
    elif sc == "eqgroup":
        types, sup = set(rule.get("equipment_types") or []), set(rule.get("supply") or [])
        groups = defaultdict(list)
        for e in c.equipment:
            if (types and e.get("equipment_type") not in types) or (sup and e.get("supply") not in sup):
                continue
            if only and e["system"] not in only:
                continue
            groups[(e["system"], e.get("mr") or "-", e.get("equipment_type"))].append(e["id"])
        for (sy, mr, typ), tags in sorted(groups.items()):
            key = f"{sy}:{mr}:{typ}"
            if key in excl:
                continue
            name = f"{c.systems.get(sy, {}).get('title', sy)}: {typ}" + (f" ({len(tags)} items)" if len(tags) > 1 else "")
            out.append((key, name, sy, {sy}, c.cwa_of(sy), None if mr == "-" else mr, sorted(tags)))
    elif sc == "mr":
        pts, ids = set(rule.get("package_types") or []), set(rule.get("mrs") or [])
        for k, m in sorted(c.mrs.items()):
            if k in excl or (pts and m.get("package_type") not in pts) or (ids and k not in ids):
                continue
            sy = {x for x, s in c.systems.items() if s.get("mr") == k} | c.eq_mr.get(k, set())
            out.append((k, m["title"], m.get("system") or "00000", sy, c.mr_cwa(k), k, None))
    return out


def required(store) -> tuple[dict[str, Inst], list[str]]:
    """All rule instances {key: Inst} and the errors found."""
    c = Ctx(store)
    rules = sorted((r for r in store.records("mdl_rule") if r.get("status") != "superseded"), key=lambda r: r["id"])
    out, errs, by_rule = {}, [], defaultdict(list)
    for r in rules:
        if r["type_code"] not in c.types:
            errs.append(f"{r['id']}: type {r['type_code']} unknown")
            continue
        for key, name, code, sy, cwa, mr, tags in _scopes(r, c):
            own = len(tags) if tags is not None else None
            f = r.get("quantity")
            if f or own is not None:
                qty = own if own is not None else sum(c.q(x, f) for x in sy)
                if qty <= 0 and not r.get("min_sheets"):
                    continue
                sheets = max(r.get("min_sheets") or 1, math.ceil(qty / (r.get("per_sheet") or 1)))
            else:
                sheets = r.get("min_sheets") or 1
            mx = r.get("max_sheets") or sheets
            n = max(1, math.ceil(sheets / mx))
            try:
                org = c.org(r, mr)
            except MdlError as e:
                errs.append(str(e))
                continue
            for part in range(1, n + 1):
                sh = sheets // n + (1 if part <= sheets % n else 0)
                i = Inst(f"{r['id']}|{key}|{part}", r, key, part, n, name, code, org, sh,
                         round((r.get("hours_base") or 0) + (r.get("hours_per_sheet") or 0) * sh, 1), set(sy), cwa,
                         None, mr)
                if r.get("ewp_disc"):
                    i.ewp = c.ewp_for(cwa, r["ewp_disc"], r.get("ewp_seq"))
                elif r["scope"] == "mr" and mr and c.types[r["type_code"]].get("construction"):
                    first = next((x for x in c.mrs[mr].get("cwps", []) if x in c.cwps), None)   # installation CWP
                    if first and "EWP" + first[3:] in c.ewps:
                        i.ewp, i.cwa = "EWP" + first[3:], c.cwps[first]["cwa"]
                if tags is not None:
                    i.equipment = tags
                elif r["scope"] == "mr" and r["type_code"] in ("DSH", "GAD") and mr:
                    i.equipment = sorted(c.tags_mr.get(mr, []))
                out[i.key] = i
                by_rule[r["id"]].append(i)
    # inputs
    for i in out.values():
        res = []
        for ent in i.rule.get("inputs") or []:
            if ent.startswith("doc:"):
                res.append(ent[4:])
                continue
            rid, _, mode = ent.partition("@")
            cands = by_rule.get(rid, [])
            if not cands:
                continue
            if mode == "plant":
                sel = [x for x in cands if x.scope_key == "00000"]
            elif mode == "cwa":
                sel = [x for x in cands if i.cwa and x.cwa == i.cwa]
            elif mode == "system":
                sel = [x for x in cands if x.systems & i.systems]
            elif mode == "structure":
                housed = {k for k, v in c.systems.items() if i.scope_key in (v.get("structures") or [])}
                sel = [x for x in cands if x.systems & housed]
            elif mode == "all":
                sel = cands
            else:
                sel = [x for x in cands if x.scope_key == i.scope_key]
                same_scope = cands[0].rule["scope"] == i.rule["scope"]      # no fallback between instances of one scope
                if not sel and all(x.scope_key == "00000" for x in cands):
                    sel = cands
                if not sel and i.cwa and not same_scope:
                    sel = [x for x in cands if x.cwa == i.cwa]
                if not sel and i.scope_key == "00000":
                    sel = cands
            res += [x.key for x in sel if x.key != i.key]
        i.inputs = list(dict.fromkeys(res))
    return out, errs


def _doc_fields(i: Inst, c_types: dict) -> dict:
    t = c_types[i.rule["type_code"]]
    cat = t.get("category", "other")
    rec = {"title": i.title, "discipline": i.rule["discipline"], "doc_type": cat, "type_code": i.rule["type_code"],
           "originator": i.org, "status": "planned", "sheets": i.sheets, "weight": i.hours, "rule": i.key,
           "aveva_class": "Drawing" if cat in DRAWING_CATS else ("Specification Documents" if cat in SPEC_CATS
                                                                 else "Deliverables Documents")}
    if not i.kks.endswith("000"):
        rec["system"] = i.kks
    for k in ("review", "bdp", "po_weeks_ifr", "po_weeks_final"):
        if i.rule.get(k) is not None:
            rec[k] = i.rule[k]
    if i.ewp:
        rec["ewp"], rec["cwa"] = i.ewp, i.cwa
    if i.mr:
        rec["mr"] = i.mr
    if i.equipment:
        rec["equipment"] = i.equipment
    if i.rule.get("basis_refs"):
        rec["basis_refs"] = sorted(i.rule["basis_refs"])
    return rec


@dataclass
class SyncPlan:
    create: list = field(default_factory=list)       # (doc id, fields)
    update: list = field(default_factory=list)       # (doc id, changes)
    links: list = field(default_factory=list)        # (doc id, inputs) after create
    orphans: list = field(default_factory=list)      # doc ids
    dropped: list = field(default_factory=list)      # (doc id, input) removed: rule-generated input no longer in the rule
    errors: list = field(default_factory=list)


def plan_sync(store) -> SyncPlan:
    inst, errs = required(store)
    types = {t["id"]: t for t in store.records("doc_type")}
    docs = {d["id"]: d for d in store.records("document")}
    by_rule = {d["rule"]: d for d in docs.values() if d.get("rule") and d.get("status") != "cancelled"
               and (d["rule"] not in inst or d.get("type_code") == inst[d["rule"]].rule["type_code"])}
    retyped = sorted(d["id"] for d in docs.values() if d.get("rule") in inst and d.get("status") != "cancelled"
                     and d.get("type_code") != inst[d["rule"]].rule["type_code"])
    p = SyncPlan(errors=errs)
    existing = list(docs)
    disc_code = kks.DISC_CODE
    for key, i in sorted(inst.items()):
        d = by_rule.get(key)
        if d:
            i.doc_id = d["id"]
        else:
            no = kks.next_number(existing, i.org, i.kks, disc_code[i.rule["discipline"]], i.rule["type_code"])
            existing.append(no)
            i.doc_id = no
    for key, i in sorted(inst.items()):
        want = _doc_fields(i, types)
        ins = [inst[k].doc_id if k in inst else k for k in i.inputs if k in inst or k in docs]
        d = by_rule.get(key)
        if not d:
            p.create.append((i.doc_id, {"id": i.doc_id, **want}))
            if ins:
                p.links.append((i.doc_id, ins))
            continue
        ch = {}
        for k in ("sheets", "weight", "po_weeks_ifr", "po_weeks_final", "review"):
            if want.get(k) is not None and d.get(k) != want[k]:
                ch[k] = want[k]
        if want.get("ewp") and (not d.get("ewp") or d["ewp"].split("-")[2] != want["ewp"].split("-")[2]):
            ch["ewp"], ch["cwa"] = want["ewp"], want["cwa"]      # a curated EWP of the same discipline is kept
        if want.get("mr") and not d.get("mr"):
            ch["mr"] = want["mr"]
        if want.get("equipment") and sorted(set(d.get("equipment") or []) | set(want["equipment"])) != sorted(d.get("equipment") or []):
            ch["equipment"] = sorted(set(d.get("equipment") or []) | set(want["equipment"]))
        br = sorted(set(d.get("basis_refs") or []) | set(want.get("basis_refs") or []))
        if br != sorted(d.get("basis_refs") or []):
            ch["basis_refs"] = br
        allowed = {e.partition("@")[0] for e in i.rule.get("inputs") or [] if not e.startswith("doc:")}
        cur = list(d.get("inputs") or [])
        keep = [x for x in cur if x in ins or docs.get(x, {}).get("planned_ifr") or not docs.get(x, {}).get("rule")]
        new_in = [x for x in ins if x not in keep and x != d["id"]]
        if new_in or len(keep) != len(cur):
            ch["inputs"] = keep + new_in
            p.dropped += [(d["id"], x) for x in cur if x not in keep]
        if ch:
            p.update.append((d["id"], ch))
    p.orphans = sorted({d["id"] for k, d in by_rule.items() if k not in inst} | set(retyped))
    return p


def check_loops(store, plan: SyncPlan) -> list[str]:
    """Input network after the sync must stay acyclic."""
    g = {d["id"]: set(d.get("inputs") or []) for d in store.records("document") if d.get("status") != "cancelled"}
    for no, rec in plan.create:
        g.setdefault(no, set())
    for no, ins in plan.links:
        g[no] |= set(ins)
    for no, ch in plan.update:
        if "inputs" in ch:
            g[no] = set(ch["inputs"])
    indeg = {k: 0 for k in g}
    succ = defaultdict(list)
    for k, v in g.items():
        for x in v:
            if x in g:
                indeg[k] += 1
                succ[x].append(k)
    ready = [k for k, v in indeg.items() if v == 0]
    seen = 0
    while ready:
        k = ready.pop()
        seen += 1
        for s in succ[k]:
            indeg[s] -= 1
            if indeg[s] == 0:
                ready.append(s)
    return [] if seen == len(g) else sorted(k for k, v in indeg.items() if v > 0)[:15]
