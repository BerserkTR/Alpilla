"""Planning calculations - derived from the database, never stored in it (SSOT).

Calendar: working days from project.work_days_per_week (5 = Mon-Fri, 6 = Mon-Sat, 7 = all) minus
project.holidays. Time unit = working day. An activity occupies working days [ES, EF) (EF exclusive);
a milestone has ES == EF.

CPM with links FS/SS/FF/SF and lags (working days), constraints start_no_earlier_than /
finish_no_later_than, actual dates and percent complete at the data date:
  completed    -> fixed at its actual dates
  in progress  -> started at actual_start, remaining work from the data date
  not started  -> cannot start before the data date
Document progress = highest progress_rule % reached by an issued revision (on/before the data date),
or the STARTED % while the document is in progress; activity progress follows its deliverables
(weighted by document weight) when it has any, otherwise its manual percent_complete.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from .schema import parse_logic


class PlanningError(ValueError):
    pass


class Calendar:
    def __init__(self, start: date, days_per_week: int = 5, holidays=()):
        self.start = start
        self.dpw = days_per_week
        self.holidays = {date.fromisoformat(h) if isinstance(h, str) else h for h in holidays}
        self._days: list[date] = []

    def working(self, d: date) -> bool:
        return d.weekday() < self.dpw and d not in self.holidays

    def _extend(self, n: int):
        d = self._days[-1] + timedelta(days=1) if self._days else self.start
        while len(self._days) <= n:
            if self.working(d):
                self._days.append(d)
            d += timedelta(days=1)

    def date(self, i: int) -> date:
        """Working day index -> calendar date (index may be negative: before the start)."""
        if i < 0:
            d, k = self.start, 0
            while k > i:
                d -= timedelta(days=1)
                if self.working(d):
                    k -= 1
            return d
        self._extend(i)
        return self._days[i]

    def index(self, d: date) -> int:
        """Calendar date -> index of the first working day on/after it."""
        if d < self.start:
            return -sum(1 for k in range((self.start - d).days) if self.working(d + timedelta(days=k)))
        i = 0
        while self.date(i) < d:
            i += 1
        return i

    def finish_date(self, ef: int, es: int) -> date:
        """Displayed finish = last working day occupied (milestones: their date)."""
        return self.date(ef - 1) if ef > es else self.date(es)


@dataclass
class Act:
    id: str
    title: str
    wbs: str
    type: str
    dur: int
    preds: list = field(default_factory=list)      # (pred_id, rel, lag)
    rec: dict = field(default_factory=dict)
    es: int = 0
    ef: int = 0
    ls: int = 0
    lf: int = 0
    remaining: int = 0
    status: str = "not_started"
    pct: float = 0.0

    @property
    def tf(self) -> int:
        return self.ls - self.es if self.status == "not_started" else self.lf - self.ef

    @property
    def critical(self) -> bool:
        return self.status != "completed" and self.tf <= 0


def document_progress(store, data_date: date) -> dict[str, float]:
    rules = {r["id"]: r["percent"] for r in store.records("progress_rule")}
    revs: dict[str, list] = {}
    for r in store.records("document_revision"):
        if date.fromisoformat(r["issue_date"]) <= data_date:
            revs.setdefault(r["document"], []).append(r)
    out = {}
    for d in store.records("document"):
        if d.get("status") == "cancelled":
            continue
        p = max((rules.get(r["purpose"], 0) for r in revs.get(d["id"], [])), default=0)
        if p == 0 and d.get("status") == "in_progress":
            p = rules.get("STARTED", 0)
        out[d["id"]] = float(p)
    return out


def activity_progress(rec: dict, docs: dict[str, float], weights: dict[str, float]) -> float:
    if rec.get("actual_finish"):
        return 100.0
    dl = [d for d in rec.get("deliverables", []) if d in docs]
    if dl:
        w = [weights.get(d) or 1.0 for d in dl]
        return sum(docs[d] * wi for d, wi in zip(dl, w)) / sum(w)
    return float(rec.get("percent_complete") or 0)


def calendar_for(store) -> tuple[Calendar, date, dict]:
    prj = (store.records("project") or [{}])[0]
    if not prj.get("schedule_start"):
        raise PlanningError("project.schedule_start is not set (python -m engine db update project <id> --set schedule_start=YYYY-MM-DD)")
    start = date.fromisoformat(prj["schedule_start"])
    dd = date.fromisoformat(prj["data_date"]) if prj.get("data_date") else start
    return Calendar(start, prj.get("work_days_per_week", 5), prj.get("holidays", [])), dd, prj


def compute(store) -> tuple[list[Act], Calendar, date]:
    cal, data_date, _ = calendar_for(store)
    DD = cal.index(data_date)
    docs = document_progress(store, data_date)
    weights = {d["id"]: d.get("weight") for d in store.records("document")}
    acts = {}
    for r in store.records("activity"):
        dur = 0 if r.get("type", "task") != "task" else r["duration"]
        a = Act(r["id"], r["title"], r["wbs"], r.get("type", "task"), dur,
                [parse_logic(x) for x in r.get("predecessors", [])], r)
        a.pct = activity_progress(r, docs, weights)
        if r.get("actual_finish"):
            a.status = "completed"
        elif r.get("actual_start") or a.pct > 0:
            a.status = "in_progress"
        acts[a.id] = a
    order = _topo(acts)

    # ---- forward pass
    for aid in order:
        a = acts[aid]
        r = a.rec
        if a.status == "completed":
            a.es = cal.index(date.fromisoformat(r.get("actual_start") or r["actual_finish"]))
            a.ef = cal.index(date.fromisoformat(r["actual_finish"])) + (1 if a.dur else 0)
            a.remaining = 0
            continue
        es = 0
        for pid, rel, lag in a.preds:
            p = acts[pid]
            es = max(es, {"FS": p.ef + lag, "SS": p.es + lag, "FF": p.ef + lag - a.dur,
                          "SF": p.es + lag - a.dur}[rel])
        if r.get("constraint") == "start_no_earlier_than" and r.get("constraint_date"):
            es = max(es, cal.index(date.fromisoformat(r["constraint_date"])))
        if a.status == "in_progress":
            a.es = cal.index(date.fromisoformat(r["actual_start"])) if r.get("actual_start") else min(es, DD)
            a.remaining = math.ceil(a.dur * (1 - a.pct / 100.0))
            a.ef = max(DD, a.es) + a.remaining
        else:
            a.es = max(es, DD)
            a.remaining = a.dur
            a.ef = a.es + a.dur

    # ---- backward pass
    finish = max((a.ef for a in acts.values()), default=0)
    succs: dict[str, list] = {k: [] for k in acts}
    for a in acts.values():
        for pid, rel, lag in a.preds:
            succs[pid].append((a.id, rel, lag))
    for aid in reversed(order):
        a = acts[aid]
        lf = finish
        for sid, rel, lag in succs[aid]:
            s = acts[sid]
            lf = min(lf, {"FS": s.ls - lag, "SS": s.ls - lag + a.dur, "FF": s.lf - lag,
                          "SF": s.lf - lag + a.dur}[rel])
        r = a.rec
        if r.get("constraint") == "finish_no_later_than" and r.get("constraint_date"):
            lf = min(lf, cal.index(date.fromisoformat(r["constraint_date"])) + (1 if a.dur else 0))
        a.lf = lf
        a.ls = lf - (a.remaining if a.status == "in_progress" else a.dur)
    return [acts[i] for i in order], cal, data_date


def _topo(acts: dict) -> list[str]:
    indeg = {k: 0 for k in acts}
    out: dict[str, list] = {k: [] for k in acts}
    for a in acts.values():
        for pid, _, _ in a.preds:
            if pid not in acts:
                raise PlanningError(f"{a.id}: predecessor {pid} does not exist")
            indeg[a.id] += 1
            out[pid].append(a.id)
    ready = sorted(k for k, v in indeg.items() if v == 0)
    order = []
    while ready:
        k = ready.pop(0)
        order.append(k)
        for s in sorted(out[k]):
            indeg[s] -= 1
            if indeg[s] == 0:
                ready.append(s)
    if len(order) != len(acts):
        loop = sorted(k for k, v in indeg.items() if v > 0)
        raise PlanningError(f"logic loop between activities: {', '.join(loop[:12])}")
    return order


def document_curves(store, cal: Calendar) -> dict:
    """Weekly planned vs earned document progress (weighted), for the S-curve."""
    rules = {r["id"]: r["percent"] for r in store.records("progress_rule")}
    docs = [d for d in store.records("document") if d.get("status") != "cancelled"]
    total = sum(d.get("weight") or 1.0 for d in docs) or 1.0
    planned_events, earned_events = [], []
    for d in docs:
        w = (d.get("weight") or 1.0) / total * 100
        for purpose, f in (("IFR", "planned_ifr"), ("IFA", "planned_ifa"), ("IFC", "planned_ifc")):
            if d.get(f) and purpose in rules:
                planned_events.append((date.fromisoformat(d[f]), d["id"], rules[purpose] * w / 100))
    for r in store.records("document_revision"):
        dd = next((d for d in docs if d["id"] == r["document"]), None)
        if dd and r["purpose"] in rules:
            w = (dd.get("weight") or 1.0) / total * 100
            earned_events.append((date.fromisoformat(r["issue_date"]), dd["id"], rules[r["purpose"]] * w / 100))

    def cumulative(events):
        best, series = {}, {}
        for d, doc, v in sorted(events):
            best[doc] = max(best.get(doc, 0), v)
            series[d] = sum(best.values())
        return series
    return {"planned": cumulative(planned_events), "earned": cumulative(earned_events)}
