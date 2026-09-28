"""Planning: calendar, CPM (hand-checked network), progress from documents, loops, curves."""
from datetime import date

import pytest

from engine.core import planning
from engine.core.store import Store, StoreError
from tests.conftest import who

R = "test"


def base(project, start="2026-01-05", data_date=None, **extra):
    s = Store(project, who())
    prj = {"id": "ALP", "name": "Alpilla CCGT", "plant_type": "CCGT", "schedule_start": start, **extra}
    if data_date:
        prj["data_date"] = data_date
    s.create("project", prj, R)
    s.create("wbs", {"id": "ALP", "title": "Alpilla"}, R)
    s.create("wbs", {"id": "ALP.E", "title": "Engineering", "parent": "ALP"}, R)
    return s


def act(s, aid, dur, preds=(), **kw):
    s.create("activity", {"id": aid, "title": aid, "wbs": "ALP.E", "phase": "engineering", "duration": dur,
                          **({"predecessors": list(preds)} if preds else {}), **kw}, R)


def test_calendar():
    cal = planning.Calendar(date(2026, 1, 5), 5, ["2026-01-07"])        # Monday start, Wednesday holiday
    assert [cal.date(i).isoformat() for i in range(4)] == ["2026-01-05", "2026-01-06", "2026-01-08", "2026-01-09"]
    assert cal.date(4) == date(2026, 1, 12)                              # weekend skipped
    assert cal.index(date(2026, 1, 7)) == 2 and cal.index(date(2026, 1, 10)) == 4
    assert cal.date(-1) == date(2026, 1, 2)
    assert planning.Calendar(date(2026, 1, 5), 6).date(5) == date(2026, 1, 10)   # Saturday works


def test_cpm_hand_checked_network(project):
    s = base(project)
    act(s, "A", 5)
    act(s, "B", 3, ["A"])
    act(s, "C", 4, ["A:SS+2"])
    act(s, "D", 2, ["B", "C"])
    act(s, "E", 0, ["D"], type="finish_milestone")
    act(s, "F", 1, ["D:FF"])
    acts, cal, _ = planning.compute(Store(project, who()))
    got = {a.id: (a.es, a.ef, a.ls, a.lf, a.tf, a.critical) for a in acts}
    assert got == {"A": (0, 5, 0, 5, 0, True), "B": (5, 8, 5, 8, 0, True), "C": (2, 6, 4, 8, 2, False),
                   "D": (8, 10, 8, 10, 0, True), "E": (10, 10, 10, 10, 0, True), "F": (9, 10, 9, 10, 0, True)}
    a = next(x for x in acts if x.id == "A")
    assert cal.date(a.es) == date(2026, 1, 5) and cal.finish_date(a.ef, a.es) == date(2026, 1, 9)


def test_constraints_actuals_and_data_date(project):
    s = base(project, data_date="2026-01-14")                              # index 7
    act(s, "A", 5, actual_start="2026-01-05", actual_finish="2026-01-09")
    act(s, "B", 4, ["A"], actual_start="2026-01-12", percent_complete=50)
    act(s, "C", 3, ["A"])                                                # not started: pushed to the data date
    act(s, "D", 2, ["B"], constraint="start_no_earlier_than", constraint_date="2026-01-26")   # index 15
    act(s, "M", 0, ["C", "D"], type="finish_milestone", constraint="finish_no_later_than",
        constraint_date="2026-01-27")
    acts = {a.id: a for a in planning.compute(Store(project, who()))[0]}
    assert (acts["A"].es, acts["A"].ef, acts["A"].status) == (0, 5, "completed")
    assert (acts["B"].es, acts["B"].remaining, acts["B"].ef) == (5, 2, 9)          # remaining from data date 7
    assert (acts["C"].es, acts["C"].ef) == (7, 10)
    assert (acts["D"].es, acts["D"].ef) == (15, 17)
    assert acts["M"].es == 17 and acts["M"].lf == 16 and acts["M"].tf == -1        # FNLT missed -> negative float
    assert acts["D"].critical and acts["M"].critical


def test_logic_validation_and_loops(project):
    s = base(project)
    act(s, "A", 1)
    with pytest.raises(StoreError, match="must be a list like"):
        act(s, "B", 1, ["A:XX"])
    with pytest.raises(StoreError, match="does not exist"):
        act(s, "B", 1, ["NOPE"])
    act(s, "B", 1, ["A"])
    s.update("activity", "A", {"predecessors": ["B"]}, "loop")
    with pytest.raises(planning.PlanningError, match="logic loop between activities: A, B"):
        planning.compute(Store(project, who()))
    with pytest.raises(StoreError, match="referenced by"):
        s.delete("activity", "B", "x")


def test_document_progress_drives_activity(project):
    s = base(project, data_date="2026-03-02")
    for rid, pct in (("STARTED", 10), ("IFR", 50), ("IFA", 70), ("IFC", 100)):
        s.create("progress_rule", {"id": rid, "percent": pct}, R)
    s.create("document", {"id": "ALP-EPC-10LAC-ME-DSH-0001", "title": "BFP datasheet", "discipline": "mechanical",
                          "doc_type": "datasheet", "weight": 30, "planned_ifr": "2026-02-02", "planned_ifc": "2026-03-02"}, R)
    s.create("document", {"id": "ALP-EPC-10LAC-ME-DSH-0002", "title": "CEP datasheet", "discipline": "mechanical",
                          "doc_type": "datasheet", "weight": 10, "status": "in_progress", "planned_ifc": "2026-04-06"}, R)
    r = s.create("document_revision", {"document": "ALP-EPC-10LAC-ME-DSH-0001", "revision": "A", "purpose": "IFR", "issue_date": "2026-02-03"}, R)
    assert r["id"] == "ALP-EPC-10LAC-ME-DSH-0001_A"
    with pytest.raises(StoreError, match="already exists"):
        s.create("document_revision", {"document": "ALP-EPC-10LAC-ME-DSH-0001", "revision": "A", "purpose": "IFA", "issue_date": "2026-02-04"}, R)
    s.create("document_revision", {"document": "ALP-EPC-10LAC-ME-DSH-0001", "revision": "B", "purpose": "IFA", "issue_date": "2026-03-10"}, R)  # after data date
    act(s, "E-1", 20, deliverables=["ALP-EPC-10LAC-ME-DSH-0001", "ALP-EPC-10LAC-ME-DSH-0002"], percent_complete=5)
    st = Store(project, who())
    assert planning.document_progress(st, date(2026, 3, 2)) == {"ALP-EPC-10LAC-ME-DSH-0001": 50.0, "ALP-EPC-10LAC-ME-DSH-0002": 10.0}
    a = planning.compute(st)[0][0]
    assert a.pct == pytest.approx((50 * 30 + 10 * 10) / 40)             # weighted, manual % ignored
    cal = planning.calendar_for(st)[0]
    curves = planning.document_curves(st, cal)
    assert curves["planned"][date(2026, 3, 2)] == pytest.approx(75.0)   # DS-001 IFC (100% x 30/40)
    assert curves["earned"][date(2026, 3, 10)] == pytest.approx(52.5)   # DS-001 IFA 70% x 30/40


def test_hyphenated_ids_are_not_lags():
    from engine.core.schema import parse_logic
    assert parse_logic("PM-100") == ("PM-100", "FS", 0)
    assert parse_logic("PM-100:FS-5") == ("PM-100", "FS", -5)
    assert parse_logic("E.2-10:SS+15") == ("E.2-10", "SS", 15)
    with pytest.raises(ValueError):
        parse_logic("PM-100+5")          # lag without link type is ambiguous -> rejected


def test_float_measured_against_contract_deadline(project):
    s = base(project)                                          # Monday 2026-01-05 = index 0
    act(s, "A", 5)
    act(s, "KD", 0, ["A"], type="finish_milestone", constraint="finish_no_later_than", constraint_date="2026-01-30")  # index 19
    acts = {a.id: a for a in planning.compute(Store(project, who()))[0]}
    assert acts["KD"].es == 5 and acts["KD"].lf == 19 and acts["KD"].tf == 14
    assert acts["A"].tf == 14 and not acts["A"].critical
