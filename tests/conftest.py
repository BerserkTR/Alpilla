import shutil
import subprocess
from pathlib import Path

import pytest

from engine.core.identity import Identity
from engine.core.project import Project
from engine.core.store import Store

ROOT = Path(__file__).resolve().parents[1]


def who(code="AAA", email=None):
    return Identity(f"User {code}", email or f"{code.lower()}@example.com", code, None)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A throw-away copy of the environment (schemas, templates, engine) with an empty database."""
    for d in ("database/schema", "templates"):
        shutil.copytree(ROOT / d, tmp_path / d)
    for d in ("records", "changelog"):
        (tmp_path / "database" / d).mkdir(parents=True)
    (tmp_path / "output").mkdir()
    (tmp_path / "internal_deliveries").mkdir()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.setenv("ALPILLA_ROOT", str(tmp_path))
    monkeypatch.setenv("ALPILLA_USER_CODE", "AAA")
    monkeypatch.setenv("ALPILLA_USER_NAME", "User AAA")
    monkeypatch.setenv("ALPILLA_USER_EMAIL", "aaa@example.com")
    monkeypatch.delenv("CLAUDECODE", raising=False)
    p = Project(tmp_path)
    from engine.engines import governance
    governance.write(p, Store(p, who()))
    return p


def seed(store: Store):
    """Small but realistic CCGT data set used by several tests."""
    R = "test seed"
    store.create("project", {"id": "ALP", "name": "Alpilla CCGT", "plant_type": "CCGT",
                             "configuration": "1x1 multi-shaft", "gross_output_target": 450,
                             "location": "Test site", "phase": "FEED"}, R)
    store.create("source", {"id": "SRC-AAA-0001", "title": "Client site data", "originator": "Client"}, R)
    store.create("reference", {"id": "REF-AAA-0001", "title": "Rotating electrical machines", "code": "IEC 60034-1"}, R)
    store.create("system", {"id": "10MBA", "title": "Gas turbine unit 1", "category": "gas_turbine", "unit_no": "10"}, R)
    store.create("system", {"id": "10LAC", "title": "Feedwater pumps", "category": "condensate_feedwater", "unit_no": "10"}, R)
    store.create("equipment", {"id": "10LAC10AP001", "description": "HP/IP boiler feed pump A", "system": "10LAC",
                               "equipment_type": "pump", "rated_power": 3200, "voltage": 6600, "design_flow": 320,
                               "redundancy": "2x100%", "basis_refs": ["source:SRC-AAA-0001"]}, R)
    store.create("equipment", {"id": "10MBV10AP001", "description": "GT lube oil pump", "system": "10MBA",
                               "equipment_type": "pump", "rated_power": 75, "voltage": 400}, R)
    store.create("design_parameter", {"category": "ambient", "parameter": "Maximum dry bulb temperature",
                                      "value": 45, "unit": "degC", "basis_refs": ["source:SRC-AAA-0001"]}, R)
    store.create("design_parameter", {"category": "grid", "parameter": "Grid frequency", "value": 50, "unit": "Hz",
                                      "status": "confirmed", "basis_refs": ["reference:REF-AAA-0001"]}, R)
