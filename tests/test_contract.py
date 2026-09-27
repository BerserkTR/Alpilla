"""Contract engines: document assembled from clause/appendix records; traceability matrix computed from basis refs."""
from docx import Document
from openpyxl import load_workbook

from engine.core import validate
from engine.core.runner import run_engine
from engine.core.store import Store, StoreError
from engine.engines import registry
from tests.conftest import who

R = "t"


def seed_contract(s):
    s.create("project", {"id": "ALP", "name": "Alpilla CCGT", "plant_type": "CCGT", "schedule_start": "2026-11-02"}, R)
    s.create("party", {"id": "OWNER", "name": "Owner Co", "role": "owner"}, R)
    s.create("party", {"id": "LEAD", "name": "Leader Co", "role": "consortium_leader"}, R)
    s.create("party", {"id": "MEMB", "name": "Member Co", "role": "consortium_member"}, R)
    s.create("contract", {"id": "K-1", "title": "Test EPC Contract", "owner": "OWNER", "contractor_parties": ["LEAD", "MEMB"],
                          "leader": "LEAD", "currency": "EUR", "price": 100000000, "status": "signed"}, R)
    s.create("contract_clause", {"contract": "K-1", "number": "A1", "part": "agreement", "title": "Parties", "text": "Between us."}, R)
    s.create("contract_clause", {"contract": "K-1", "number": "A7", "part": "agreement", "title": "Signatures", "text": "Signed."}, R)
    s.create("contract_clause", {"contract": "K-1", "number": "12", "part": "conditions", "title": "Guarantees"}, R)
    s.create("contract_clause", {"contract": "K-1", "number": "12.2", "part": "conditions", "title": "Performance LDs",
                                 "text": "The Contractor shall pay:\n\n- LD one\n- LD two"}, R)
    s.create("contract_clause", {"contract": "K-1", "number": "2.1", "part": "conditions", "title": "Access", "text": "Access."}, R)
    s.create("contract_clause", {"contract": "K-1", "number": "2", "part": "conditions", "title": "The Owner"}, R)
    s.create("guarantee", {"id": "PG-01", "contract": "K-1", "parameter": "Net output", "category": "performance",
                           "guaranteed_value": 600, "unit": "MW", "direction": "min", "conditions": "SRC",
                           "ld_rate": 2200, "ld_unit": "EUR per kW shortfall"}, R)
    s.create("requirement", {"id": "ER-04.01", "contract": "K-1", "section": "ER-04 Performance", "title": "Net output",
                             "text": "Not less than 600 MW.", "discipline": "process", "verification": "test", "guarantee": "PG-01"}, R)
    s.create("requirement", {"id": "ER-04.02", "contract": "K-1", "section": "ER-04 Performance", "title": "Heat rate",
                             "text": "Low.", "discipline": "process", "verification": "test"}, R)
    s.create("milestone", {"id": "MS-01", "contract": "K-1", "title": "Advance", "percent": 10, "trigger": "signature"}, R)
    s.create("milestone", {"id": "MS-02", "contract": "K-1", "title": "Taking-Over", "percent": 90, "trigger": "TOC"}, R)
    s.create("scope_item", {"id": "SC-001", "contract": "K-1", "area": "Power island", "item": "Gas turbine",
                            "design": "MEMB", "supply": "MEMB", "install": "LEAD", "terminal_point": "GT exhaust flange"}, R)
    s.create("design_parameter", {"category": "performance", "parameter": "Net output", "value": 600, "unit": "MW",
                                  "status": "confirmed", "basis_refs": ["requirement:ER-04.01"]}, R)
    s.create("wbs", {"id": "ALP", "title": "Alpilla"}, R)
    s.create("wbs", {"id": "ALP.KD", "title": "Key dates", "parent": "ALP"}, R)
    s.create("activity", {"id": "KD-040", "title": "Taking-Over", "wbs": "ALP.KD", "phase": "commissioning", "duration": 0,
                          "type": "finish_milestone", "constraint": "finish_no_later_than", "constraint_date": "2029-07-04"}, R)


def test_contract_document(project):
    seed_contract(Store(project, who()))
    assert validate.run(project).ok
    m = run_engine(project, Store(project, who()), registry()["contract_document"], {"pdf": "no"})
    doc = Document(project.output / "contract_document" / "K-1_contract.docx")
    text = [p.text for p in doc.paragraphs]
    order = [t for t in text if t.startswith(("2  The Owner", "2.1  Access", "12  Guarantees", "12.2  Performance"))]
    assert order == ["2  The Owner", "2.1  Access", "12  Guarantees", "12.2  Performance LDs"]   # numeric, not text order
    assert "LD one" in text and "Signed." in text
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    assert "EUR 10,000,000" in cells and "EUR 90,000,000" in cells and "100 %" in cells     # amounts computed
    assert ">= 600 MW" in cells and "2,200 EUR per kW shortfall" in cells
    assert any(c.startswith("For the Contractor (Leader)") for c in cells) and "GT exhaust flange" in cells
    assert "2029-07-04" in cells and m["warnings"] == []


def test_payment_schedule_must_total_100(project):
    s = Store(project, who())
    seed_contract(s)
    s.update("milestone", "MS-02", {"percent": 80}, "t")
    m = run_engine(project, Store(project, who()), registry()["contract_document"], {"pdf": "no"})
    assert any("add up to 90" in w for w in m["warnings"])


def test_requirements_matrix(project):
    seed_contract(Store(project, who()))
    run_engine(project, Store(project, who()), registry()["requirements_matrix"], {})
    wb = load_workbook(project.output / "requirements_matrix" / "ALP_requirements_matrix.xlsx")
    rows = {r[0]: r for r in wb["RTM"].iter_rows(min_row=5, values_only=True)}
    assert rows["ER-04.01"][8] == ">= 600 MW" and rows["ER-04.01"][9].startswith("design_parameter/DP-AAA-")
    assert rows["ER-04.01"][10] == "yes" and rows["ER-04.02"][10] == "no"
    cov = list(wb["Coverage"].iter_rows(min_row=5, max_row=5, values_only=True))[0]
    assert cov[:5] == ("ER-04 Performance", 2, 1, 1, 50.0)


def test_requirement_refs_validated(project):
    s = Store(project, who())
    seed_contract(s)
    import pytest
    with pytest.raises(StoreError, match="does not exist"):
        s.create("design_parameter", {"category": "site", "parameter": "x", "value": 1, "basis_refs": ["requirement:ER-99.01"]}, R)
    with pytest.raises(StoreError, match="referenced by"):
        s.delete("requirement", "ER-04.01", "t")


def test_tie_ins_clarifications_and_appendices(project):
    import pytest
    s = Store(project, who())
    seed_contract(s)
    s.create("source", {"id": "SRC-AAA-0001", "title": "Site report", "originator": "Owner Co (Owner)", "doc_ref": "OWN-001",
                        "file": "sources/owner/x.md"}, R)
    s.create("tie_in", {"id": "TP-G1", "contract": "K-1", "service": "Natural gas", "medium": "gas", "location": [380000, 300000, 14000],
                        "location_text": "NE corner", "owner_side": "spur line", "contractor_side": "metering station",
                        "available_by": "2028-06-30", "basis_refs": ["source:SRC-AAA-0001"]}, R)
    with pytest.raises(StoreError, match="must be \\[x, y, z\\]"):
        s.create("tie_in", {"id": "TP-E1", "contract": "K-1", "service": "x", "medium": "x", "location": [1, 2],
                            "location_text": "x", "owner_side": "x", "contractor_side": "x"}, R)
    s.create("clarification", {"id": "TQ-001", "contract": "K-1", "round": 1, "raised_by": "LEAD", "raised_date": "2026-09-18",
                               "discipline": "process", "subject": "Gas pressure", "question": "Is 40 barg possible?",
                               "references": ["tie_in:TP-G1", "requirement:ER-04.01"]}, R)
    m = run_engine(project, Store(project, who()), registry()["contract_document"], {"pdf": "no"})
    assert any("clarifications not closed: TQ-001" in w for w in m["warnings"])
    s2 = Store(project, who())
    s2.update("clarification", "TQ-001", {"response": "No, 45 barg.", "responded_by": "OWNER", "status": "closed",
                                          "outcome": "confirmed_as_is", "impact": "none"}, R)
    m = run_engine(project, Store(project, who()), registry()["contract_document"], {"pdf": "no"})
    doc = Document(project.output / "contract_document" / "K-1_contract.docx")
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    assert {"TP-G1", "metering station", "OWN-001", "Is 40 barg possible?", "No, 45 barg.", "confirmed as is"} <= set(cells)
    assert not any("not closed" in w for w in m["warnings"])
    # an internal consortium agreement with its own interfaces and queries: not rendered as an Owner contract,
    # its queries get their own register
    s3 = Store(project, who())
    s3.create("contract", {"id": "CA-1", "title": "Consortium agreement", "kind": "consortium_agreement", "owner": "LEAD",
                           "contractor_parties": ["MEMB"], "currency": "EUR", "price": 50000000}, R)
    s3.create("scope_item", {"id": "DR-001", "contract": "CA-1", "area": "Steam", "item": "Main steam piping",
                             "design": "LEAD", "supply": "LEAD"}, R)
    s3.create("tie_in", {"id": "IF-05", "contract": "CA-1", "service": "HP steam", "medium": "steam", "location_text": "HRSG outlet",
                         "owner_side": "piping", "contractor_side": "HRSG"}, R)
    s3.create("clarification", {"id": "TQ-MEMB-001", "contract": "CA-1", "round": 1, "raised_by": "LEAD", "raised_date": "2026-09-27",
                                "discipline": "piping", "subject": "Piping pressure drop", "question": "Confirm 7 bar?",
                                "references": ["tie_in:IF-05", "scope_item:DR-001"]}, R)
    with pytest.raises(StoreError, match="pattern"):
        s3.create("scope_item", {"id": "XX-001", "contract": "CA-1", "area": "a", "item": "b"}, R)
    m = run_engine(project, Store(project, who()), registry()["contract_document"], {"pdf": "no"})
    assert sorted(m["files"]) == ["K-1_contract.docx"]
    doc = Document(project.output / "contract_document" / "K-1_contract.docx")
    cells = {c.text for t in doc.tables for row in t.rows for c in row.cells}
    assert "IF-05" not in cells and "DR-001" not in cells
    m = run_engine(project, Store(project, who()), registry()["clarification_register"], {})
    assert sorted(m["files"]) == ["ALP_clarification_register_CA-1.xlsx", "ALP_clarification_register_K-1.xlsx"]
    wb = load_workbook(project.output / "clarification_register" / "ALP_clarification_register_K-1.xlsx")
    summary = [r for r in wb["Summary"].iter_rows(values_only=True)]
    assert ("Round 1", 1, 1, 0, 0) in summary
    wb = load_workbook(project.output / "clarification_register" / "ALP_clarification_register_CA-1.xlsx")
    assert ("Round 1", 1, 0, 1, 0) in [r for r in wb["Summary"].iter_rows(values_only=True)]
