"""Document release control: which document may be issued, at which purpose and revision, from which input revisions, and
which process gates (procurement, Owner acceptance, construction, commissioning, operations) are open.

Status ladder of a document (from its document_revision records):
  NONE < IFR (first issue: IFR / IFI / IFD / IFP) < IFA < ACCEPTED (review code 1 or 2 on the latest issue; information
  and internal classes are accepted when issued) < IFC (issued for construction / final, certified for supplier documents)
  < AB (as built)
Release rules (can_issue):
  IFR / IFA  every input at least at the maturity the document type requires (doc_type.input_maturity: IFR or IFC);
             IFA needs a reviewed IFR (any review code)
  IFC        every EPC input at IFC, every supplier input ACCEPTED (certified data); the document itself ACCEPTED when its
             review class is approval or review (Owner code 1 / 2); supplier documents need the EPC acceptance
  AB         the document is IFC
A revision records the input revisions it was based on (based_on). An input revised after that (newer revision) makes the
document CHECK REQUIRED: it is re-issued, or confirmed unaffected by a new revision with the same purpose.
Planned dates of each status come from the workflow timeline (engine/core/workflow.py)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from . import workflow

LEVEL = {"NONE": 0, "IFR": 1, "IFA": 2, "ACCEPTED": 3, "IFC": 4, "AB": 5}
NAME = {v: k for k, v in LEVEL.items()}
PURPOSE_LEVEL = {"IFR": 1, "IFI": 1, "IFD": 1, "IFP": 1, "IFA": 2, "IFC": 4, "AB": 5}


@dataclass
class DocState:
    id: str
    level: int = 0
    rev: str | None = None                 # latest revision label
    rev_id: str | None = None
    purpose: str | None = None
    code: str | None = None                # review code of the latest revision
    issued: str | None = None              # date of the latest revision
    void: bool = False
    revs: list = field(default_factory=list)
    suspect: list = field(default_factory=list)        # (input, input revision newer than the one used)


def review_class(doc: dict, types: dict) -> str:
    return doc.get("review") or types.get(doc.get("type_code"), {}).get("review", "review")


def states(store) -> dict[str, DocState]:
    types = {t["id"]: t for t in store.records("doc_type")}
    docs = {d["id"]: d for d in store.records("document")}
    revs = defaultdict(list)
    for r in store.records("document_revision"):
        revs[r["document"]].append(r)
    out = {}
    for k, d in docs.items():
        st = DocState(k, void=d.get("status") == "cancelled")
        rs = sorted(revs.get(k, []), key=lambda r: (r["issue_date"], r.get("_meta", {}).get("created_at", "")))
        st.revs = rs
        for r in rs:
            if r["purpose"] == "VOID":
                st.void = True
                continue
            st.level = max(st.level, PURPOSE_LEVEL.get(r["purpose"], 1))
        if rs:
            last = rs[-1]
            st.rev, st.rev_id, st.purpose, st.code, st.issued = (last["revision"], last["id"], last["purpose"],
                                                               last.get("review_code"), last["issue_date"])
            accepted = (last.get("review_code") in ("1", "2")
                        or (review_class(d, types) in ("information", "internal") and d.get("originator", "EPC") == "EPC"))
            if accepted and st.level < LEVEL["ACCEPTED"]:
                st.level = LEVEL["ACCEPTED"]
        out[k] = st
    # impact of input revisions
    latest = {k: s.rev_id for k, s in out.items() if s.rev_id}
    rev_date = {r["id"]: r["issue_date"] for rs in revs.values() for r in rs}
    for k, d in docs.items():
        st = out[k]
        if not st.rev_id:
            continue
        last = st.revs[-1]
        used = {x.rsplit("_", 1)[0]: x for x in last.get("based_on") or []}
        for i in d.get("inputs") or []:
            if i not in out or not latest.get(i):
                continue
            if i in used:
                if latest[i] != used[i] and rev_date.get(latest[i], "") >= rev_date.get(used[i], ""):
                    st.suspect.append((i, latest[i]))
            elif rev_date.get(latest[i], "") > st.issued:
                st.suspect.append((i, latest[i]))
    return out


def next_rev(st: DocState, purpose: str) -> str:
    labels = [r["revision"] for r in st.revs]
    nums = [int(x) for x in labels if x.isdigit()]
    letters = [x for x in labels if x.isalpha()]
    if purpose in ("IFC", "AB") or (st.level >= LEVEL["IFC"]):
        return str(max(nums) + 1) if nums and st.level >= LEVEL["IFC"] else "0"
    if not letters:
        return "A"
    last = max(letters, key=lambda x: (len(x), x))
    return chr(ord(last[-1]) + 1) if last != "Z" else "AA"


def required_input_level(doc: dict, purpose: str, inp: dict, types: dict) -> int:
    if purpose == "IFC":
        return LEVEL["IFC"] if inp.get("originator", "EPC") == "EPC" else LEVEL["ACCEPTED"]
    if purpose == "AB":
        return 0
    mat = types.get(doc.get("type_code"), {}).get("input_maturity", "IFR")
    if mat == "IFC":
        return LEVEL["IFC"] if inp.get("originator", "EPC") == "EPC" else LEVEL["ACCEPTED"]
    return LEVEL["IFR"]


def can_issue(store, doc_id: str, purpose: str, st: dict | None = None, docs: dict | None = None,
              types: dict | None = None) -> list[str]:
    """Reasons why doc_id may not be issued now at `purpose` (empty = release allowed)."""
    st = st or states(store)
    types = types or {t["id"]: t for t in store.records("doc_type")}
    docs = docs or {d["id"]: d for d in store.records("document")}
    d = docs[doc_id]
    me = st[doc_id]
    why = []
    if me.void:
        return [f"{doc_id} is cancelled"]
    for i in d.get("inputs") or []:
        if i not in docs or st[i].void:
            continue
        need = required_input_level(d, purpose, docs[i], types)
        if st[i].level < need:
            why.append(f"input {i} is {NAME[st[i].level]}, {purpose} needs it at {NAME[need]}")
        if st[i].suspect:
            why.append(f"input {i} is CHECK REQUIRED (its own inputs were revised)")
    rc = review_class(d, types)
    supplier = d.get("originator", "EPC") != "EPC"
    if purpose == "IFA" and not (me.level >= LEVEL["IFR"] and me.code):
        why.append("IFA needs a reviewed IFR (review code received)")
    if purpose == "IFC":
        if (supplier or rc in ("approval", "review")) and me.level < LEVEL["ACCEPTED"]:
            who = "EPC" if supplier else "Owner"
            why.append(f"not yet accepted by the {who} (review code 1 / 2 on the latest issue; class {rc})")
        if me.code == "3":
            why.append("latest issue returned with code 3 (revise and resubmit)")
    if purpose == "AB" and me.level < LEVEL["IFC"]:
        why.append("as-built needs the IFC revision")
    return why


def next_purpose(doc: dict, me: DocState, types: dict) -> str | None:
    """Purpose of the next issue of the document (None: nothing to issue now - awaiting review, or complete)."""
    rc = review_class(doc, types)
    supplier = doc.get("originator", "EPC") != "EPC"
    if me.void or me.level > LEVEL["IFC"]:
        return None
    if me.suspect or me.code == "3":
        return me.purpose
    if me.level == 0:
        return "IFR"
    if me.level == LEVEL["IFC"]:
        return "AB"
    if me.level < LEVEL["ACCEPTED"]:
        if (supplier or rc in ("approval", "review")) and not me.code:
            return None
        if rc == "approval" and me.purpose == "IFR":
            return "IFA"
    return "IFC"


def next_action(doc: dict, me: DocState, types: dict) -> str:
    rc = review_class(doc, types)
    supplier = doc.get("originator", "EPC") != "EPC"
    if me.void:
        return "-"
    if me.suspect:
        return f"CHECK: re-issue {me.purpose} or confirm (inputs revised)"
    if me.level == 0:
        return "issue IFR"
    if me.code == "3":
        return f"revise and re-issue {me.purpose}"
    if me.level >= LEVEL["IFC"]:
        return "as-built after construction" if me.level == LEVEL["IFC"] else "complete"
    if me.level < LEVEL["ACCEPTED"]:
        if (supplier or rc in ("approval", "review")) and not me.code:
            return f"await {'EPC' if supplier else 'Owner'} review of {me.purpose}"
        if rc == "approval" and me.purpose == "IFR":
            return "issue IFA"
    return "issue IFC"


def planned_level_date(t: workflow.DocT, level: int, doc: dict, types: dict):
    """Working-day index at which the document is planned to reach `level` (None for AB: after construction)."""
    return workflow.level_date(t, types.get(doc.get("type_code"), {}), NAME[level])


# ------------------------------------------------------------------ gates
@dataclass
class GateResult:
    gate: str
    process: str
    scope_key: str
    title: str
    need: int | None
    ready: int | None                   # planned date all requirements met
    ok_now: bool
    rows: list = field(default_factory=list)       # (requirement, docs selected, not met now, planned date, driver)
    empty: list = field(default_factory=list)      # requirements that select no document
    members: list = field(default_factory=list)    # (document, status) required by the gate

    @property
    def float(self):
        return None if self.need is None or self.ready is None else self.need - self.ready


def _need(g: dict, key: str, res: workflow.Result, store, cwps: dict, mrs: dict):
    spec = g["need"]
    off = g.get("offset_days") or 0
    v = None
    if g["scope"] == "mr" and spec in ("enquiry", "po", "fabrication", "shipment", "ros"):
        m, rec = res.mrs.get(key), mrs.get(key, {})
        if m:
            po, ros = m["po"], m["ros"]
            man = round(5 * (rec.get("manufacture_weeks") or 0))
            if m.get("po_late") is not None:
                po = m["po_late"]                  # latest PO for the delivery on site at the need date
            v = {"enquiry": po - (rec.get("bid_days") or 0) - (rec.get("award_days") or 0), "po": po,
                 "fabrication": po + round(0.4 * man), "shipment": ros - round(5 * (rec.get("transport_weeks") or 0)),
                 "ros": ros}[spec]
    elif g["scope"] == "cwp" and spec in ("cwp_start", "cwp_mid"):
        c = cwps.get(key, {})
        a = res.acts.get(c.get("activity"))
        if a:
            lead = c.get("ewp_lead_days") or 20
            v = a.es - lead + (round(0.5 * (a.ef - a.es)) if spec == "cwp_mid" else 0)
    elif spec.startswith("activity:"):
        a = res.acts.get(spec.split(":", 1)[1])
        v = a.ef if a else None
    elif spec.startswith("milestone:"):
        m = store.get("milestone", spec.split(":", 1)[1])
        if m is not None:
            start = res.cal.date(res.dd)
            mo = start.month - 1 + int(m.get("planned_month") or 0)
            v = res.cal.index(date(start.year + mo // 12, mo % 12 + 1, min(start.day, 28)))
    return None if v is None else v + off


def _scopes(g: dict, store):
    sc = g["scope"]
    if sc == "plant":
        return ["00000"]
    if sc == "mr":
        pts = set(g.get("package_types") or [])
        return sorted(m["id"] for m in store.records("mr") if not pts or m["package_type"] in pts)
    if sc == "cwp":
        return sorted(c["id"] for c in store.records("cwp"))
    cats, parties = set(g.get("categories") or []), set(g.get("parties") or [])
    return sorted(x["id"] for x in store.records("system") if len(x["id"]) == 5 and x["id"][2] != "U"
                  and (not cats or x.get("category") in cats) and (not parties or x.get("scope") in parties))


def _select(sel: str, g: dict, key: str, docs: dict, types: dict, systems: dict, mrs: dict):
    what, _, binding = sel.partition("@")
    pool = [d for d in docs.values() if d.get("status") != "cancelled"]
    tokens = binding.split(",") if binding else []
    if "epc" in tokens:                                  # originator filters combine with a binding: @mr,epc
        pool = [d for d in pool if d.get("originator", "EPC") == "EPC"]
    if "supplier" in tokens:
        pool = [d for d in pool if d.get("originator", "EPC") != "EPC"]
    binding = next((t for t in tokens if t not in ("epc", "supplier")), "")
    # binding to the gate instance
    if binding == "plant":
        pool = [d for d in pool if not d.get("system")]
    elif binding == "mr":
        if g["scope"] == "mr":
            keys = {key}
        elif g["scope"] == "cwp":           # packages installed from the CWP start (a need lag installs later)
            keys = {m["id"] for m in mrs.values() if key in (m.get("cwps") or []) and not m.get("need_lag_days")}
        elif g["scope"] == "system":
            keys = {systems.get(key, {}).get("mr")} - {None}
        else:
            keys = set(mrs)
        pool = [d for d in pool if d.get("mr") in keys]
    elif g["scope"] == "mr":
        pool = [d for d in pool if d.get("mr") == key]
    elif g["scope"] == "cwp":
        pool = [d for d in pool if d.get("ewp") == "EWP" + key[3:]]
    elif g["scope"] == "system":
        pool = [d for d in pool if d.get("system") == key or key in (d.get("systems") or [])]
    # selector
    kind, _, val = what.partition(":")
    if kind == "type":
        return [d for d in pool if d.get("type_code") == val]
    if kind == "rule":
        return [d for d in pool if (d.get("rule") or "").split("|")[0] == val]
    if kind == "id":
        return [d for d in pool if d["id"] == val]
    if kind == "bdp":                       # bdp = whole package, bdp:<n> = submission batch n
        return [d for d in pool if d.get("bdp") and (not val or d.get("bdp_batch") == int(val))]
    if kind == "construction":
        return [d for d in pool if types.get(d.get("type_code"), {}).get("construction")]
    if kind == "ewp-first":
        return [d for d in pool if not types.get(d.get("type_code"), {}).get("progressive_share")]
    if kind in ("ewp-all", "all"):
        return pool
    raise ValueError(f"unknown selector {sel}")


def _requirements(g: dict, key: str, docs: dict, types: dict, systems: dict, mrs: dict):
    """[(requirement, optional, any, level name, [document records])] of one gate instance.
    Requirement syntax: '[any:]selector[|selector...][?] STATUS' - '|' unites the documents of several selectors,
    '?' = optional (no document selected is not an error), 'any:' = met when one selected document has the status
    (e.g. the first IWP of a CWP with progressive documents only)."""
    out = []
    for req in g["requires"]:
        sel, status = req.rsplit(" ", 1)
        anyof = sel.startswith("any:")
        sel = sel[4:] if anyof else sel
        chosen = {}
        for alt in sel.rstrip("?").split("|"):
            chosen.update({d["id"]: d for d in _select(alt, g, key, docs, types, systems, mrs)})
        out.append((req, sel.endswith("?"), anyof, status, list(chosen.values())))
    return out


def _active_rules(store) -> list[dict]:
    if "gate_rule" not in store.schemas:
        return []
    return sorted((g for g in store.records("gate_rule") if g.get("status") != "superseded"), key=lambda x: x["id"])


def gate_constraints(store, res: workflow.Result) -> tuple[dict, list]:
    """What the gates impose on the planning (called by workflow.compute before its passes; res has the calendar and
    the construction schedule only):
      po_req  MR id -> [(document id, level name)]: EPC documents that must reach the level before the PO (gates with
              need 'po'); the PO is planned at the latest of them (plus bid / award time, see workflow)
      needs   [(document id, level name, working-day index, gate id)]: the date a required document must reach the level,
              from gates with a need independent of the procurement dates (milestone, activity, CWP)"""
    types = {t["id"]: t for t in store.records("doc_type")}
    docs = {d["id"]: d for d in store.records("document")}
    systems = {x["id"]: x for x in store.records("system")}
    mrs = {m["id"]: m for m in store.records("mr")}
    cwps = {c["id"]: c for c in store.records("cwp")}
    po_req: dict[str, list] = defaultdict(list)
    needs = []
    for g in _active_rules(store):
        if g["scope"] == "mr" and g["need"] != "po":
            continue                                   # timed from the procurement dates: checked, not driving
        for key in _scopes(g, store):
            need = None if g["scope"] == "mr" else _need(g, key, res, store, cwps, mrs)
            if g["scope"] != "mr" and need is None:
                continue
            for _, _, anyof, status, chosen in _requirements(g, key, docs, types, systems, mrs):
                if status == "AB" or anyof:
                    continue                            # as-built: after construction; any-of: no single document driven
                for d in chosen:
                    if d.get("originator", "EPC") != "EPC":
                        continue                        # supplier documents are timed from their PO
                    if g["scope"] == "mr":
                        po_req[key].append((d["id"], status))
                    else:
                        needs.append((d["id"], status, need, g["id"]))
    return dict(po_req), needs


def gates(store, res: workflow.Result | None = None, st: dict | None = None) -> list[GateResult]:
    res = res or workflow.compute(store)
    st = st or states(store)
    types = {t["id"]: t for t in store.records("doc_type")}
    docs = {d["id"]: d for d in store.records("document")}
    systems = {x["id"]: x for x in store.records("system")}
    mrs = {m["id"]: m for m in store.records("mr")}
    cwps = {c["id"]: c for c in store.records("cwp")}
    out = []
    for g in _active_rules(store):
        for key in _scopes(g, store):
            gr = GateResult(g["id"], g["process"], key, g["title"], _need(g, key, res, store, cwps, mrs), None, True)
            ready = []
            for req, optional, anyof, status, chosen in _requirements(g, key, docs, types, systems, mrs):
                lvl = LEVEL[status]
                if not chosen:
                    if not optional:
                        gr.empty.append(req)            # a mandatory requirement without documents: gate cannot open
                        gr.ok_now = False
                    continue
                gr.members += [(d["id"], status) for d in chosen]
                missing = [d["id"] for d in chosen if st[d["id"]].level < lvl]
                if anyof and len(missing) < len(chosen):
                    missing = []
                plan = [(planned_level_date(res.docs[d["id"]], lvl, d, types), d["id"]) for d in chosen if d["id"] in res.docs]
                plan = [p for p in plan if p[0] is not None]
                last = (min if anyof else max)(plan) if plan else (None, None)
                gr.rows.append((req, len(chosen), missing, last[0], last[1]))
                if missing:
                    gr.ok_now = False
                if last[0] is not None:
                    ready.append(last[0])
            if not gr.rows and not gr.empty:
                continue                     # gate does not apply to this scope (only optional requirements, none selected)
            gr.ready = max(ready) if ready else None
            out.append(gr)
    return out


def release_sequence(store, res: workflow.Result) -> list[tuple]:
    """(wave, document) - wave = longest input chain to the document; documents of a wave can be released together once
    the earlier waves are at the required maturity."""
    docs = res.docs
    wave = {}
    for k in res.order:
        ins = [i for i in docs[k].rec.get("inputs") or [] if i in docs]
        wave[k] = 1 + max((wave[i] for i in ins), default=0)
    return sorted(((w, k) for k, w in wave.items()), key=lambda x: (x[0], docs[x[1]].ifc, x[1]))
