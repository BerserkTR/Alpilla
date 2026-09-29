"""Engineering workflow timeline - derived from the database, never stored in it (SSOT).

Documents form a network through `inputs`. A document can start when all its inputs have reached the maturity its type
requires (doc_type.input_maturity: IFR or IFC) and not before the data date; then
  first issue (IFR)  = start + prep_days (longer for multi-sheet documents, at most double)
  approval class     : IFA = IFR + Owner review + update_days, IFC = IFA + 5 (approval code 1)
  review class       : IFC = IFR + Owner review + update_days
  information / internal: IFC = IFR + update_days
Owner review = 10 working days (14 calendar days, ER-17.01), 15 for Basic Design Package documents (21 days),
or the period agreed for a document (document.owner_review_days).
Supplier documents (originator not EPC) keep their committed planned dates (VDRL). Issued revisions replace the dates.
Tender-stage documents (document.tender) exist from the bid design: first issue at the data date (NTP), then review.
Supplier documents without committed dates are timed from their MR: po_weeks_ifr / po_weeks_final weeks after the PO
(scaled by manufacture_weeks / 40, at least 0.5, for short-lead packages), or before shipment (ROS - transport) when
negative; they use no EPC capacity and are inputs of the EPC documents that need the vendor data (e.g. foundations need the
foundation loads).
PO = the fixed PO date, or the latest PO prerequisite of the gates with need 'po' (gate_rule, engine/core/release.py):
requisition IFC + bid_days + award_days (award_days includes the bid evaluation), bid evaluation IFR (start_after
'bids': it starts at requisition IFC + bid_days),
specifications IFC, ITP IFR. Supplier documents timed from the PO wait for these prerequisites.
A document with after_activity (test reports) starts at the early finish of that CPM activity.
Documents compiled from site records (start_after 'alap', e.g. system turnover dossiers) start as late as possible: at
their latest start - 60 working days (discipline capacity), when they have a need date.
Gates with a need date independent of procurement (milestone, key-date activity, CWP) make that date the need of every EPC
document they require, at the required status; the PO prerequisites are needed by the latest PO (need - manufacture -
transport, or the fixed PO date).

Resource levelling (when eng_resource records exist): each EPC document needs its hours (document.weight) from the
capacity of its discipline (fte x hours_per_day per working day) and cannot be done faster than its nominal preparation
time. Documents are scheduled in priority order of their latest start, which is computed backwards from the need dates
(EWP: CWP start - lead; requisition: PO date needed for the delivery on site) through the input network; a document
whose start is delayed by its discipline's capacity has the driver 'capacity <discipline>'.

AWP: an EWP is needed `ewp_lead_days` before its CWP starts (CPM early start) for its first IWPs; documents of progressive
types (doc_type.progressive_share, e.g. isometrics, supports, loop diagrams) are needed later, at CWP start - lead + share x
CWP duration. EWP float = the smallest float of its documents; ready = the date its last document is IFC.
A PWP (MR) is issued when its requisition is issued (MRQ IFC); PO as above;
vendor data = PO + vdr_weeks; on site (ROS) = PO + manufacture + transport; needed at the earliest start of its CWPs.
All durations in working days of the project calendar."""
from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from . import planning

OWNER_REVIEW = 10          # working days (14 calendar days)
OWNER_REVIEW_BDP = 15      # working days (21 calendar days)
APPROVAL_CODE = 5
HOURS_PER_DAY = 7.5
ALAP_MARGIN = 60           # working days: documents started as late as possible (start_after 'alap') keep this margin
SHORT_LEAD_WEEKS = 40      # supplier document weeks after PO scale with manufacture / 40 weeks (DEC-EPCE-0013)
SHORT_LEAD_MIN = 0.5
HORIZON = 3000             # working days searched for capacity
NO_NEED = 10 ** 6


@dataclass
class DocT:
    id: str
    rec: dict
    start: int = 0
    ifr: int = 0
    ifa: int | None = None
    ifc: int = 0
    fixed: bool = False
    driver: str | None = None          # input that set the start, or 'capacity <discipline>'
    late_start: int = NO_NEED          # priority (levelling)
    work: dict = field(default_factory=dict)   # working day -> hours (levelled documents)


@dataclass
class Result:
    cal: planning.Calendar
    dd: int
    docs: dict[str, DocT]
    acts: dict
    ewps: dict = field(default_factory=dict)
    mrs: dict = field(default_factory=dict)
    order: list = field(default_factory=list)
    capacity: dict = field(default_factory=dict)      # discipline -> hours per working day
    levelled: bool = False
    po_late: dict = field(default_factory=dict)       # MR -> latest PO (working day)
    gate_needs: list = field(default_factory=list)    # (document, status, working day, gate) imposed by gates

    def d(self, i):
        return None if i is None else self.cal.date(i)


def _topo(docs: dict, extra: dict | None = None) -> list[str]:
    indeg = {k: 0 for k in docs}
    succ: dict[str, list] = {k: [] for k in docs}
    for k, d in docs.items():
        for i in dict.fromkeys([*d.rec.get("inputs", []), *(extra or {}).get(k, ())]):
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


def _prep(d: DocT, t: dict) -> int:
    if d.rec.get("duration"):
        return d.rec["duration"]
    sheets = d.rec.get("sheets") or 1
    return round(t.get("prep_days", 10) * min(2.0, 1 + 0.05 * (sheets - 1)))


def _review_offsets(d: DocT, t: dict) -> tuple[int | None, int]:
    """(IFA - IFR or None, IFC - IFR)."""
    review = d.rec.get("review") or t.get("review", "review")
    rv = (d.rec.get("owner_review_days") or (OWNER_REVIEW_BDP if d.rec.get("bdp") else OWNER_REVIEW)) \
        if review in ("approval", "review") else 0              # an agreed review period overrides ER-17.01
    upd = t.get("update_days", 5)
    if review == "approval":
        return rv + upd, rv + upd + APPROVAL_CODE
    return None, rv + upd


def _finish(d: DocT, t: dict, issued: dict, cal) -> None:
    if issued.get("IFR"):
        d.ifr = cal.index(date.fromisoformat(issued["IFR"]))
    ifa, ifc = _review_offsets(d, t)
    d.ifa = None if ifa is None else d.ifr + ifa
    d.ifc = d.ifr + ifc
    if issued.get("IFC"):
        d.ifc = cal.index(date.fromisoformat(issued["IFC"]))


def level_offset(d: DocT, t: dict, level: str) -> int | None:
    """Working days from first issue (IFR) until the document reaches `level` (release.LEVEL names)."""
    ifa, ifc = _review_offsets(d, t)
    review = d.rec.get("review") or t.get("review", "review")
    if level in ("NONE", "IFR"):
        return 0
    if level == "IFA":
        return ifa or 0
    if level == "ACCEPTED":
        return {"approval": ifc - APPROVAL_CODE, "review": ifc - t.get("update_days", 5)}.get(review, 0)
    if level == "IFC":
        return ifc
    return None                                     # AB: after construction


def level_date(d: DocT, t: dict, level: str) -> int | None:
    """Planned working-day index at which the document reaches `level`."""
    if level == "IFC":
        return d.ifc
    if level == "IFA" and d.ifa is not None:
        return d.ifa
    o = level_offset(d, t, level)
    return None if o is None else min(d.ifr + o, d.ifc)


def _input_ready(d: DocT, docs: dict, t: dict, dd: int) -> tuple[int, str | None]:
    start, driver = dd, None
    mat = t.get("input_maturity", "IFR")
    for i in d.rec.get("inputs", []):
        if i in docs:
            x = docs[i]
            ready = x.ifr if mat == "IFR" else x.ifc
            if ready > start:
                start, driver = ready, i
    return start, driver


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
    try:
        res_recs = store.records("eng_resource")
    except Exception:           # schema not present in older databases
        res_recs = []
    res.capacity = {r["discipline"]: r["fte"] * (r.get("hours_per_day") or HOURS_PER_DAY) for r in res_recs}
    ramp = {r["discipline"]: 5 * (r.get("ramp_weeks") or 0) for r in res_recs}

    def cap_on(disc, day):
        c, rw = res.capacity[disc], ramp.get(disc, 0)
        if rw <= 0 or day - dd >= rw:
            return c
        return c * (0.3 + 0.7 * max(0, day - dd) / rw)

    # construction schedule (CPM) first: it gives the need dates
    try:
        acts, _, _ = planning.compute(store)
        res.acts = {a.id: a for a in acts}
    except planning.PlanningError:
        res.acts = {}
    cwps = {c["id"]: c for c in store.records("cwp")}
    mr_recs = {m["id"]: m for m in store.records("mr")}
    ewp_recs = {e["id"]: e for e in store.records("ewp")}

    def cwp_start(cid):
        c = cwps.get(cid, {})
        a = res.acts.get(c.get("activity"))
        return a.es if a else None

    def cwp_dur(cid):
        c = cwps.get(cid, {})
        a = res.acts.get(c.get("activity"))
        return (a.ef - a.es) if a else 0

    def doc_need(rec):
        """Date a construction document is needed: CWP start - lead + progressive share x CWP duration."""
        e = ewp_recs.get(rec.get("ewp"))
        if not e or cwp_start(e["cwp"]) is None:
            return None
        share = types.get(rec.get("type_code"), {}).get("progressive_share") or 0
        return cwp_start(e["cwp"]) - (cwps.get(e["cwp"], {}).get("ewp_lead_days") or 20) + round(share * cwp_dur(e["cwp"]))

    def mr_need(m):
        lag = m.get("need_lag_days") or 0
        starts = [(cwp_start(c) + lag, c) for c in m.get("cwps", []) if cwp_start(c) is not None]
        return min(starts) if starts else (None, None)

    by_mr_all: dict[str, list] = defaultdict(list)
    for d in docs.values():
        if d.rec.get("mr"):
            by_mr_all[d.rec["mr"]].append(d)

    # process gates (gate_rule, engine/core/release.py): the PO prerequisites of each MR and the dates by which the
    # documents required by milestone / activity / CWP gates must reach their status
    from . import release                        # local import: release builds on this module
    po_req, gate_needs = release.gate_constraints(store, res)
    rank = ["NONE", "IFR", "IFA", "ACCEPTED", "IFC"]
    best: dict[str, dict] = defaultdict(dict)
    for mid, v in po_req.items():
        for i, lvl in v:
            if i in docs and rank.index(lvl) >= rank.index(best[mid].get(i, "NONE")):
                best[mid][i] = lvl
    po_req = {mid: sorted(v.items()) for mid, v in best.items()}

    def po_lag(i, m):
        """Working days between the prerequisite reaching its status and the PO."""
        r = docs[i].rec
        if r.get("type_code") == "MRQ":
            return (m.get("bid_days") or 0) + (m.get("award_days") or 0)
        return 0                                  # award_days covers the bid evaluation: TBE issued by the PO

    def from_po(r) -> bool:
        return (r.get("originator", "EPC") != "EPC" and r.get("po_weeks_ifr") is not None and bool(r.get("mr"))
                and not r.get("planned_ifr") and not revs.get(r["id"]))

    # supplier documents timed from the PO wait for every PO prerequisite of their MR
    extra = {k: [i for i, _ in po_req.get(d.rec["mr"], [])] for k, d in docs.items() if from_po(d.rec)}
    res.order = _topo(docs, extra)

    def lvl_date(i, lvl):
        return level_date(docs[i], types.get(docs[i].rec.get("type_code"), {}), lvl)

    def po_ros(mid):
        """(PO, on-site) working-day indices of an MR: its fixed PO date, or the latest of its PO prerequisites (gate
        G-PRC-PO: requisition IFC + bid + award, bid evaluation + award, specifications, ITP), computed so far."""
        m = mr_recs.get(mid, {})
        if m.get("po_date"):
            po = cal.index(date.fromisoformat(m["po_date"]))
        elif po_req.get(mid):
            po = max(lvl_date(i, lvl) + po_lag(i, m) for i, lvl in po_req[mid])
        else:
            ds = by_mr_all.get(mid, [])
            mrq = [x for x in ds if x.rec.get("type_code") == "MRQ"]
            issue = max((x.ifc for x in mrq), default=dd)
            po = issue + (m.get("bid_days") or 0) + (m.get("award_days") or 0)
        return po, po + round(5 * ((m.get("manufacture_weeks") or 0) + (m.get("transport_weeks") or 0)))

    def ready_at(d, t):
        """Earliest start: inputs at the required maturity; after the bids are in for bid evaluations."""
        est, drv = _input_ready(d, docs, t, dd)
        a = res.acts.get(d.rec.get("after_activity") or "")
        if a is not None and a.ef > est:
            est, drv = a.ef, f"after {a.id}"              # records of a site activity (test reports) follow it
        if d.rec.get("start_after") == "alap" and d.late_start < NO_NEED and d.late_start - ALAP_MARGIN > est:
            return d.late_start - ALAP_MARGIN, "as late as possible (need)"
        mid = d.rec.get("mr")
        if d.rec.get("start_after") == "bids" and mid:
            mrq = [x.ifc for x in by_mr_all.get(mid, []) if x.rec.get("type_code") == "MRQ"]
            if mrq and max(mrq) + (mr_recs.get(mid, {}).get("bid_days") or 0) > est:
                est, drv = max(mrq) + (mr_recs[mid].get("bid_days") or 0), f"bids {mid}"
        return est, drv

    def sup_weeks(r):
        """(first, final) weeks of a supplier document: after the PO, scaled for short-lead packages (standard products
        document faster: factor manufacture / 40 weeks, between 0.5 and 1); negative = before shipment (ex works)."""
        m = mr_recs.get(r.get("mr"), {})
        w1, w2 = r["po_weeks_ifr"], r.get("po_weeks_final", r["po_weeks_ifr"])
        if w1 >= 0:
            f = min(1.0, max(SHORT_LEAD_MIN, (m.get("manufacture_weeks") or 0) / SHORT_LEAD_WEEKS))
            return w1 * f, w2 * f
        return w1, w2

    def supplier_dates(d) -> bool:
        """Supplier document timed from its MR: weeks after the PO, or before shipment (ROS - transport) when negative."""
        r = d.rec
        if r.get("originator", "EPC") == "EPC" or r.get("po_weeks_ifr") is None or not r.get("mr"):
            return False
        po, ros = po_ros(r["mr"])
        w1, w2 = sup_weeks(r)
        base = po if w1 >= 0 else ros - round(5 * (mr_recs.get(r["mr"], {}).get("transport_weeks") or 0))
        d.fixed, d.driver = True, f"PO {r['mr']}"
        d.ifr = max(dd, base + round(5 * w1))
        d.ifc = max(d.ifr, base + round(5 * w2))
        d.start = max(dd, d.ifr - types.get(r.get("type_code"), {}).get("prep_days", 10))
        return True

    # 1. fixed documents: supplier (VDRL), tender stage, already issued first revision
    free = []
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
        elif r.get("tender") or issued.get("IFR"):
            d.fixed = True
            d.start = d.ifr = dd
            _finish(d, t, issued, cal)
        else:
            free.append(k)

    # 2. latest starts (priority) backwards from the need dates
    succ = defaultdict(list)
    for k, d in docs.items():
        for i in dict.fromkeys([*d.rec.get("inputs", []), *extra.get(k, ())]):
            if i in docs:
                succ[i].append(k)

    def to_ifc(k, lvl, when):
        """Latest IFC of document k such that it reaches status lvl by `when`."""
        t = types.get(docs[k].rec.get("type_code"), {})
        o = level_offset(docs[k], t, lvl) or 0
        return when - o + _review_offsets(docs[k], t)[1]

    def transit(m):
        return round(5 * ((m.get("manufacture_weeks") or 0) + (m.get("transport_weeks") or 0)))

    late_ifc: dict[str, int] = {}
    for k, d in docs.items():
        need = NO_NEED
        dn = doc_need(d.rec)
        if dn is not None:
            need = dn
        m = mr_recs.get(d.rec.get("mr"))
        if m and not m.get("po_date") and d.rec.get("type_code") == "MRQ" and not po_req.get(m["id"]):
            n, _ = mr_need(m)
            if n is not None:
                need = min(need, n - transit(m) - (m.get("bid_days") or 0) - (m.get("award_days") or 0))
        late_ifc[k] = need
    # latest PO of each MR (fixed PO date, or delivery on site at the need date) -> its PO prerequisites
    po_late: dict[str, int] = {}
    for mid, m in mr_recs.items():
        if m.get("po_date"):
            po_late[mid] = cal.index(date.fromisoformat(m["po_date"]))
        else:
            n, _ = mr_need(m)
            if n is not None:
                po_late[mid] = n - transit(m)
    for mid, reqs in po_req.items():
        if mid in po_late:
            for i, lvl in reqs:
                late_ifc[i] = min(late_ifc[i], to_ifc(i, lvl, po_late[mid] - po_lag(i, mr_recs[mid])))
    # gates with a need date (milestones, key dates, CWPs): their required documents are needed by then
    for i, lvl, need, _ in gate_needs:
        if i in docs:
            late_ifc[i] = min(late_ifc[i], to_ifc(i, lvl, need))
    for k in reversed(res.order):
        d = docs[k]
        t = types.get(d.rec.get("type_code"), {})
        _, off = _review_offsets(d, t)
        for s in succ[k]:
            x = docs[s]
            ts = types.get(x.rec.get("type_code"), {})
            if x.late_start >= NO_NEED:
                continue
            xm = mr_recs.get(x.rec.get("mr") or "", {})
            if s in extra and k in extra[s]:
                if xm.get("po_date"):
                    continue                        # PO fixed: its prerequisites are needed by the PO date (above)
                # supplier data timed from the PO: the PO prerequisites must be met by the data need - weeks
                w1, w2 = sup_weeks(x.rec)
                base = late_ifc[s] - round(5 * w2)
                lp = base if w1 >= 0 else base - round(5 * (xm.get("manufacture_weeks") or 0))
                lvl = dict(po_req.get(xm.get("id"), [])).get(k)
                if lvl:
                    late_ifc[k] = min(late_ifc[k], to_ifc(k, lvl, lp - po_lag(k, xm)))
                continue
            if x.rec.get("start_after") == "bids" and d.rec.get("type_code") == "MRQ" and xm:
                late_ifc[k] = min(late_ifc[k], x.late_start - (xm.get("bid_days") or 0))
                continue
            late_ifc[k] = min(late_ifc[k], x.late_start + (off if ts.get("input_maturity", "IFR") == "IFR" else 0))
        d.late_start = late_ifc[k] - off - _prep(d, t) if late_ifc[k] < NO_NEED else NO_NEED
    res.po_late = po_late
    res.gate_needs = gate_needs

    # 3. forward pass: unconstrained, or levelled by discipline capacity in priority order
    res.levelled = bool(res.capacity)
    free_set = set(free)
    if not res.levelled:
        for k in free:
            d = docs[k]
            if supplier_dates(d):
                continue
            t = types.get(d.rec.get("type_code"), {})
            d.start, d.driver = ready_at(d, t)
            d.ifr = d.start + _prep(d, t)
            _finish(d, t, revs.get(k, {}), cal)
    else:
        left: dict[str, dict] = defaultdict(dict)
        waiting = {k: sum(1 for i in dict.fromkeys([*docs[k].rec.get("inputs", []), *extra.get(k, ())]) if i in free_set)
                   for k in free}
        heap = [(docs[k].late_start, k) for k in free if waiting[k] == 0]
        heapq.heapify(heap)
        while heap:
            _, k = heapq.heappop(heap)
            d = docs[k]
            t = types.get(d.rec.get("type_code"), {})
            if supplier_dates(d):
                for s_ in succ[k]:
                    if s_ in waiting:
                        waiting[s_] -= 1
                        if waiting[s_] == 0:
                            heapq.heappush(heap, (docs[s_].late_start, s_))
                continue
            est, driver = ready_at(d, t)
            prep = _prep(d, t)
            disc = d.rec.get("discipline")
            cap = res.capacity.get(disc)
            hours = d.rec.get("weight") or 0
            if not cap or hours <= 0:
                d.start, d.driver, d.ifr = est, driver, est + prep
            else:
                rate = hours / max(prep, 1)
                rem, day, first = hours, est, None
                book = left[disc]
                floor = min(rate, HOURS_PER_DAY / 2)            # no work on a day with less than half a person free
                while rem > 1e-6 and day < est + HORIZON:
                    avail = book.get(day, cap_on(disc, day))
                    use = min(rem, avail, rate)
                    if use >= min(floor, rem) - 1e-9 and use > 1e-9:
                        book[day] = avail - use
                        d.work[day] = use
                        rem -= use
                        first = day if first is None else first
                    day += 1
                d.start = first if first is not None else est
                d.ifr = max(day, d.start + prep)
                d.driver = driver if d.ifr <= est + prep else f"capacity {disc}"
            _finish(d, t, revs.get(k, {}), cal)
            for s in succ[k]:
                if s in waiting:
                    waiting[s] -= 1
                    if waiting[s] == 0:
                        heapq.heappush(heap, (docs[s].late_start, s))

    # 4. AWP: PWPs and EWPs
    by_ewp: dict[str, list] = {}
    by_mr: dict[str, list] = {}
    for d in docs.values():
        if d.rec.get("ewp"):
            by_ewp.setdefault(d.rec["ewp"], []).append(d)
        if d.rec.get("mr"):
            by_mr.setdefault(d.rec["mr"], []).append(d)
    for m in mr_recs.values():
        ds = by_mr.get(m["id"], [])
        mrq = [d for d in ds if d.rec.get("type_code") == "MRQ"]
        issue = None if m.get("po_date") else max((d.ifc for d in mrq), default=max((d.ifr for d in ds), default=dd))
        po, ros = po_ros(m["id"])
        vdr = po + round(5 * (m.get("vdr_weeks") or 0))
        need, need_cwp = mr_need(m)
        res.mrs[m["id"]] = {"issue": issue, "po": po, "po_late": po_late.get(m["id"]), "vdr": vdr, "ros": ros,
                            "need": need, "need_cwp": need_cwp,
                            "float": None if need is None else need - ros, "docs": [d.id for d in ds]}
    for e in ewp_recs.values():
        ds = by_ewp.get(e["id"], [])
        c = cwps.get(e["cwp"], {})
        s = cwp_start(e["cwp"])
        need = None if s is None else s - (c.get("ewp_lead_days") or 20)
        last = max(ds, key=lambda d: d.ifc) if ds else None
        ready = last.ifc if last else None
        fl = [((doc_need(d.rec) or need) - d.ifc, d.id) for d in ds] if need is not None else []
        worst = min(fl) if fl else (None, None)
        vendor = [(res.mrs[m]["vdr"] - (mr_recs[m].get("need_lag_days") or 0), res.mrs[m]["vdr"], m) for m in res.mrs
                  if e["cwp"] in mr_recs[m].get("cwps", [])]       # data of late-installed materials is needed later
        worst_v = max(vendor) if vendor else None
        vd = (worst_v[1], worst_v[2]) if worst_v else (None, None)
        res.ewps[e["id"]] = {"cwp": e["cwp"], "cwa": c.get("cwa"), "docs": [d.id for d in ds], "ready": ready,
                             "driver": worst[1] or (last.id if last else None), "need": need, "cwp_start": s,
                             "float": worst[0],
                             "vendor_data": vd[0], "vendor_mr": vd[1],
                             "vendor_float": None if (need is None or worst_v is None) else need - worst_v[0]}
    return res
