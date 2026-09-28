"""Engineering workflow timeline - derived from the database, never stored in it (SSOT).

Documents form a network through `inputs`. A document starts when all its inputs have reached the maturity its type
requires (doc_type.input_maturity: IFR or IFC) and not before the data date; then
  first issue (IFR)  = start + prep_days (longer for multi-sheet documents, at most double)
  approval class     : IFA = IFR + Owner review + update_days, IFC = IFA + 5 (approval code 1)
  review class       : IFC = IFR + Owner review + update_days
  information / internal: IFC = IFR + update_days
Owner review = 10 working days (14 calendar days, ER-17.01), 15 for Basic Design Package documents (21 days).
Supplier documents (originator not EPC) keep their committed planned dates (VDRL). Issued revisions replace the dates.
Tender-stage documents (document.tender) exist from the bid design: first issue at the data date (NTP), then review.

AWP: an EWP is ready when its last document is IFC; it is needed `ewp_lead_days` before its CWP starts (CPM early start).
A PWP (MR) is issued when its requisition is issued (MRQ IFC); PO = issue + bid_days + award_days (or the fixed PO date);
vendor data = PO + vdr_weeks; on site (ROS) = PO + manufacture + transport; needed at the earliest start of its CWPs.
All durations in working days of the project calendar."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import planning

OWNER_REVIEW = 10          # working days (14 calendar days)
OWNER_REVIEW_BDP = 15      # working days (21 calendar days)
APPROVAL_CODE = 5


@dataclass
class DocT:
    id: str
    rec: dict
    start: int = 0
    ifr: int = 0
    ifa: int | None = None
    ifc: int = 0
    fixed: bool = False
    driver: str | None = None          # input that set the start


@dataclass
class Result:
    cal: planning.Calendar
    dd: int
    docs: dict[str, DocT]
    acts: dict
    ewps: dict = field(default_factory=dict)
    mrs: dict = field(default_factory=dict)
    order: list = field(default_factory=list)

    def d(self, i):
        return None if i is None else self.cal.date(i)


def _topo(docs: dict) -> list[str]:
    indeg = {k: 0 for k in docs}
    succ: dict[str, list] = {k: [] for k in docs}
    for k, d in docs.items():
        for i in d.rec.get("inputs", []):
            if i in docs:
                indeg[k] += 1
                succ[i].append(k)
    ready = sorted(k for k, v in indeg.items() if v == 0)
    out = []
    while ready:
        k = ready.pop(0)
        out.append(k)
        for s in succ[k]:
            indeg[s] -= 1
            if indeg[s] == 0:
                ready.append(s)
    if len(out) != len(docs):
        loop = sorted(k for k, v in indeg.items() if v > 0)
        raise planning.PlanningError(f"document input loop: {', '.join(loop[:12])}")
    return out


def compute(store) -> Result:
    cal, dd_date, _ = planning.calendar_for(store)
    dd = cal.index(dd_date)
    types = {t["id"]: t for t in store.records("doc_type")}
    revs: dict[str, dict] = {}
    for r in store.records("document_revision"):
        e = revs.setdefault(r["document"], {})
        p = r["purpose"]
        if p not in e or r["issue_date"] < e[p]:
            e[p] = r["issue_date"]
    docs = {r["id"]: DocT(r["id"], r) for r in store.records("document") if r.get("status") != "cancelled"}
    res = Result(cal, dd, docs, {})
    res.order = _topo(docs)
    for k in res.order:
        d = docs[k]
        r = d.rec
        t = types.get(r.get("type_code"), {})
        issued = revs.get(k, {})
        if r.get("originator", "EPC") != "EPC" and (r.get("planned_ifr") or issued):
            d.fixed = True
            d.ifr = cal.index(date.fromisoformat(issued.get("IFR") or issued.get("IFI") or r["planned_ifr"]))
            d.ifc = cal.index(date.fromisoformat(issued.get("IFC") or r.get("planned_ifc") or r["planned_ifr"]))
            d.start = d.ifr - t.get("prep_days", 10)
            continue
        start, driver = dd, None
        mat = t.get("input_maturity", "IFR")
        for i in r.get("inputs", []):
            if i not in docs:
                continue
            x = docs[i]
            ready = x.ifr if mat == "IFR" else x.ifc
            if ready > start:
                start, driver = ready, i
        d.start, d.driver = start, driver
        sheets = r.get("sheets") or 1
        prep = round(t.get("prep_days", 10) * min(2.0, 1 + 0.05 * (sheets - 1)))
        d.ifr = start + prep
        if r.get("tender"):                    # bid design: first issue at the data date (NTP), inputs already met
            d.start, d.ifr, d.driver = dd, dd, None
        if issued.get("IFR"):
            d.ifr = cal.index(date.fromisoformat(issued["IFR"]))
        review = r.get("review") or t.get("review", "review")
        rv = (OWNER_REVIEW_BDP if r.get("bdp") else OWNER_REVIEW) if review in ("approval", "review") else 0
        upd = t.get("update_days", 5)
        if review == "approval":
            d.ifa = d.ifr + rv + upd
            d.ifc = d.ifa + APPROVAL_CODE
        else:
            d.ifc = d.ifr + rv + upd
        if issued.get("IFC"):
            d.ifc = cal.index(date.fromisoformat(issued["IFC"]))

    # construction schedule (CPM)
    try:
        acts, _, _ = planning.compute(store)
        res.acts = {a.id: a for a in acts}
    except planning.PlanningError:
        res.acts = {}
    cwps = {c["id"]: c for c in store.records("cwp")}
    mr_recs = {m["id"]: m for m in store.records("mr")}
    by_ewp: dict[str, list] = {}
    by_mr: dict[str, list] = {}
    for d in docs.values():
        if d.rec.get("ewp"):
            by_ewp.setdefault(d.rec["ewp"], []).append(d)
        if d.rec.get("mr"):
            by_mr.setdefault(d.rec["mr"], []).append(d)

    def cwp_start(cid):
        c = cwps.get(cid, {})
        a = res.acts.get(c.get("activity"))
        return a.es if a else None

    for m in mr_recs.values():
        ds = by_mr.get(m["id"], [])
        mrq = [d for d in ds if d.rec.get("type_code") == "MRQ"]
        if m.get("po_date"):
            issue = None
            po = cal.index(date.fromisoformat(m["po_date"]))
        else:
            issue = max((d.ifc for d in mrq), default=max((d.ifr for d in ds), default=dd))
            po = issue + (m.get("bid_days") or 0) + (m.get("award_days") or 0)
        vdr = po + round(5 * (m.get("vdr_weeks") or 0))
        ros = po + round(5 * ((m.get("manufacture_weeks") or 0) + (m.get("transport_weeks") or 0)))
        starts = [(cwp_start(c), c) for c in m.get("cwps", []) if cwp_start(c) is not None]
        need, need_cwp = min(starts) if starts else (None, None)
        res.mrs[m["id"]] = {"issue": issue, "po": po, "vdr": vdr, "ros": ros, "need": need, "need_cwp": need_cwp,
                            "float": None if need is None else need - ros, "docs": [d.id for d in ds]}
    for e in store.records("ewp"):
        ds = by_ewp.get(e["id"], [])
        c = cwps.get(e["cwp"], {})
        s = cwp_start(e["cwp"])
        need = None if s is None else s - (c.get("ewp_lead_days") or 20)
        last = max(ds, key=lambda d: d.ifc) if ds else None
        ready = last.ifc if last else None
        vendor = [(res.mrs[m]["vdr"], m) for m in res.mrs if e["cwp"] in mr_recs[m].get("cwps", [])]
        vd = max(vendor) if vendor else (None, None)
        res.ewps[e["id"]] = {"cwp": e["cwp"], "cwa": c.get("cwa"), "docs": [d.id for d in ds], "ready": ready,
                             "driver": last.id if last else None, "need": need, "cwp_start": s,
                             "float": None if (need is None or ready is None) else need - ready,
                             "vendor_data": vd[0], "vendor_mr": vd[1],
                             "vendor_float": None if (need is None or vd[0] is None) else need - vd[0]}
    return res
