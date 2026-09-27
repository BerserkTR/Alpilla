"""Piping / 3D data model: points, per-type required fields, wall/bore resolution, routing continuity."""
import pytest

from engine.cli import main
from engine.core import piping, validate
from engine.core.store import Store, StoreError
from tests.conftest import who
from tests.piping_fixture import seed_piping


def test_fixture_valid(project):
    seed_piping(Store(project, who()))
    rep = validate.run(project)
    assert rep.ok, rep.text()
    assert not [w for w in rep.warnings if w.startswith("routing")]


def test_required_by_component_type_and_points(project):
    s = Store(project, who())
    seed_piping(s)
    with pytest.raises(StoreError, match="'centre' is required when type = ELBOW"):
        s.create("pipe_component", {"line": "10LAB10BR001", "seq": "0100", "type": "ELBOW",
                                    "end1": [0, 0, 0], "end2": [1, 1, 0]}, "t")
    with pytest.raises(StoreError, match=r"must be \[x, y, z\]"):
        s.create("pipe_component", {"line": "10LAB10BR001", "seq": "0100", "type": "PIPE",
                                    "end1": [0, 0], "end2": [1, 1, 0]}, "t")
    with pytest.raises(StoreError, match="'support_type' is required"):
        s.create("pipe_component", {"line": "10LAB10BR001", "seq": "0100", "type": "SUPPORT", "end1": [0, 0, 0]}, "t")
    assert s.get("pipe_component", "10LAB10BR001_0050")["type"] == "ELBOW"   # id = line_seq
    assert s.get("nozzle", "10LAC10AP001_D")["dn"] == "DN150"


def test_wall_and_bore(project):
    s = Store(project, who())
    seed_piping(s)
    props = piping.line_props(s, s.get("line", "10LAB10BR001"))
    assert props["od"] == 168.3 and props["wall"] == 10.97 and props["wall_source"].startswith("XS")
    assert props["bore_id"] == pytest.approx(146.36)
    s.update("line", "10LAB10BR001", {"wall_thickness": 14.27}, "calc")
    assert piping.line_props(s, s.get("line", "10LAB10BR001"))["wall"] == 14.27


def test_routing_gap_reported(project, capsys):
    s = Store(project, who())
    seed_piping(s)
    s.update("pipe_component", "10LAB10BR001_0060", {"end1": [10250, 5000, 4229]}, "moved")
    warns = validate.run(project).warnings
    assert any("gap of 21 mm between seq 0050 and 0060" in w for w in warns)
    assert main(["db", "update", "pipe_component", "10LAB10BR001_0060", "--set", "end1=10229,5000,4229",
                 "--reason", "fixed"]) == 0
    assert not [w for w in validate.run(project).warnings if "gap" in w]
