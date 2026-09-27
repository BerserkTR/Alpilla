"""Single source of truth: schema enforcement, audit log, tamper detection, multi-user merges."""
import json
import shutil

import pytest

from engine.core import index, validate
from engine.core.store import Store, StoreError
from tests.conftest import seed, who


def test_seed_is_valid(project):
    s = Store(project, who())
    seed(s)
    rep = validate.run(project, Store(project, who()))
    assert rep.ok, rep.text()


def test_schema_enforced(project):
    s = Store(project, who())
    seed(s)
    with pytest.raises(StoreError, match="unknown field"):
        s.create("system", {"id": "10XYZ", "title": "x", "category": "other", "colour": "red"}, "r")
    with pytest.raises(StoreError, match="not in"):
        s.create("system", {"id": "10XYZ", "title": "x", "category": "banana"}, "r")
    with pytest.raises(StoreError, match="does not exist"):
        s.create("equipment", {"id": "10XX01", "description": "x", "system": "NOPE", "equipment_type": "pump"}, "r")
    with pytest.raises(StoreError, match="required field 'basis_refs'"):
        s.create("design_parameter", {"category": "site", "parameter": "Altitude", "value": 10}, "r")
    with pytest.raises(StoreError, match="<entity>:<id>"):
        s.create("design_parameter", {"category": "site", "parameter": "Altitude", "basis_refs": ["SRC-AAA-0001"]}, "r")
    with pytest.raises(StoreError, match="must be number"):
        s.update("equipment", "10MBV10AP001", {"rated_power": "big"}, "r")
    with pytest.raises(StoreError, match="reason"):
        s.update("equipment", "10MBV10AP001", {"rated_power": 80}, "")
    with pytest.raises(StoreError, match="case-insensitive"):
        s.create("system", {"id": "10mba", "title": "dup", "category": "other"}, "r")


def test_delete_blocked_while_referenced(project):
    s = Store(project, who())
    seed(s)
    with pytest.raises(StoreError, match="referenced by"):
        s.delete("system", "10MBA", "r")
    s.delete("equipment", "10MBV10AP001", "removed from scope")
    s.delete("system", "10MBA", "removed from scope")
    assert validate.run(project, Store(project, who())).ok


def test_auto_ids_carry_user_code(project):
    s = Store(project, who("AAA"))
    seed(s)
    b = Store(project, who("BBB"))
    r = b.create("design_parameter", {"category": "site", "parameter": "Altitude", "value": 12, "unit": "m",
                                      "basis_refs": ["source:SRC-AAA-0001"]}, "r")
    assert r["id"] == "DP-BBB-0001"
    assert s.next_id("design_parameter") == "DP-AAA-0003"


def test_hand_edit_detected_and_reconciled(project):
    s = Store(project, who())
    seed(s)
    f = s.path("equipment", "10MBV10AP001")
    rec = json.loads(f.read_text())
    rec["rated_power"] = 90
    f.write_text(json.dumps(rec, indent=2))            # someone edits the JSON by hand
    rep = validate.run(project, Store(project, who()))
    assert not rep.ok and any("edited by hand" in e for e in rep.errors)
    s2 = Store(project, who("BBB"))
    s2.reconcile("equipment", "10MBV10AP001", "accepted after check", rep.divergent[0][2])
    assert validate.run(project, Store(project, who())).ok
    log = (project.changelog_dir / "BBB.jsonl").read_text()
    assert '"op":"reconcile"' in log


def test_hand_created_and_hand_deleted_records_detected(project):
    s = Store(project, who())
    seed(s)
    (project.records_dir / "system" / "20MBA.json").write_text(
        json.dumps({"id": "20MBA", "title": "GT 2", "category": "gas_turbine", "_meta": {"rev": 1}}))
    s.path("equipment", "10MBV10AP001").unlink()
    errs = validate.run(project, Store(project, who())).errors
    assert any("never logged" in e for e in errs)
    assert any("deleted by hand" in e for e in errs)


def test_parallel_edits_by_two_users_are_detected(project, tmp_path):
    """Two branches: A and B both update the same record from the same revision, then git merges."""
    s = Store(project, who("AAA"))
    seed(s)
    snapshot = tmp_path / "snap"
    shutil.copytree(project.database, snapshot)
    s.update("equipment", "10LAC10AP001", {"rated_power": 3300}, "vendor data rev 1")   # branch of user A
    a_record = json.loads(s.path("equipment", "10LAC10AP001").read_text())
    a_log = (project.changelog_dir / "AAA.jsonl").read_text()
    shutil.rmtree(project.database)
    shutil.copytree(snapshot, project.database)
    Store(project, who("BBB")).update("equipment", "10LAC10AP001", {"voltage": 11000}, "electrical study")
    # git merge result: each user's own changelog file merges cleanly; the record conflict is resolved by hand
    (project.changelog_dir / "AAA.jsonl").write_text(a_log)
    merged = dict(a_record, voltage=11000)
    s.path("equipment", "10LAC10AP001").write_text(json.dumps(merged, indent=2))

    rep = validate.run(project, Store(project, who()))
    assert any("parallel changes" in e and "AAA" in e and "BBB" in e for e in rep.errors), rep.text()
    ent, rid, rev = rep.divergent[0]
    Store(project, who("AAA")).reconcile(ent, rid, "merged A power + B voltage", rev)
    final = Store(project, who())
    assert validate.run(project, final).ok
    r = final.get("equipment", "10LAC10AP001")
    assert (r["rated_power"], r["voltage"], r["_meta"]["rev"]) == (3300, 11000, 3)


def test_index_and_query(project):
    s = Store(project, who())
    seed(s)
    index.ensure(project, s, force=True)
    cols, rows, more = index.query(project, "SELECT id, rated_power FROM equipment WHERE rated_power > 100")
    assert rows == [("10LAC10AP001", 3200)] and not more
    s.update("equipment", "10MBV10AP001", {"rated_power": 150}, "r")
    _, rows, _ = index.query(project, "SELECT count(*) FROM equipment WHERE rated_power > 100")
    assert rows[0][0] == 2                              # index rebuilt automatically after change
    _, rows, _ = index.query(project, "SELECT user, op FROM changelog WHERE id='10MBV10AP001' ORDER BY rev")
    assert rows == [("AAA", "create"), ("AAA", "update")]
    with pytest.raises(Exception):
        index.query(project, "DELETE FROM equipment")    # read-only


def test_changelog_user_code_clash_detected(project):
    s = Store(project, who("AAA", "one@example.com"))
    seed(s)
    Store(project, who("AAA", "two@example.com")).create(
        "system", {"id": "20MBA", "title": "GT 2", "category": "gas_turbine"}, "r")
    assert any("used by several people" in e for e in validate.run(project, Store(project, who())).errors)


def test_update_refuses_to_launder_hand_edit(project):
    s = Store(project, who())
    seed(s)
    f = s.path("equipment", "10MBV10AP001")
    f.write_text(f.read_text().replace('"rated_power": 75', '"rated_power": 99'))
    s2 = Store(project, who())
    with pytest.raises(StoreError, match="differs from its logged state"):
        s2.update("equipment", "10MBV10AP001", {"voltage": 690}, "r")
    with pytest.raises(StoreError, match="differs from its logged state"):
        s2.delete("equipment", "10MBV10AP001", "r")
    s2.update("equipment", "10LAC10AP001", {"voltage": 690}, "r")      # untouched records still editable
    s2.update("equipment", "10LAC10AP001", {"voltage": 700}, "r")      # consecutive updates in one session


def test_merge_conflict_markers_reported_clearly(project):
    s = Store(project, who())
    seed(s)
    f = s.path("system", "10MBA")
    f.write_text("{\n<<<<<<< HEAD\n  \"title\": \"a\"\n=======\n  \"title\": \"b\"\n>>>>>>> elec\n}\n")
    errs = validate.run(project).errors
    assert len(errs) == 1 and "system/10MBA.json" in errs[0] and "merge conflict" in errs[0]


def test_delete_then_recreate_same_id(project):
    s = Store(project, who())
    seed(s)
    s.delete("equipment", "10MBV10AP001", "removed")
    r = s.create("equipment", {"id": "10MBV10AP001", "description": "GT lube oil pump (new)", "system": "10MBA",
                               "equipment_type": "pump"}, "re-added")
    assert r["_meta"]["rev"] == 3                       # create 1, delete 2, re-create 3
    assert validate.run(project, Store(project, who())).ok
    s2 = Store(project, who())                          # fresh store reads the same history
    s2.update("equipment", "10MBV10AP001", {"rated_power": 80}, "vendor")
    assert validate.run(project, Store(project, who())).ok
