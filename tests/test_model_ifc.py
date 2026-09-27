"""IFC model: schema-valid IFC4, every element tessellates, line grouping and properties present."""
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.validate

from engine.core.runner import run_engine
from engine.core.store import Store
from engine.engines import registry
from tests.conftest import who
from tests.piping_fixture import seed_piping


def test_ifc_model(project):
    seed_piping(Store(project, who()))
    m = run_engine(project, Store(project, who()), registry()["model_ifc"], {})
    f = ifcopenshell.open(str(project.output / "model_ifc" / "ALP_plant_model.ifc"))
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log, express_rules=True)
    assert log.statements == [], log.statements[:3]
    assert {e.Name for e in f.by_type("IfcPump")} == {"10LAC10AP001"}
    assert {e.Name for e in f.by_type("IfcTank")} == {"10LAA10BB001"}
    assert len(f.by_type("IfcValve")) == 2 and len(f.by_type("IfcPipeSegment")) == 2
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    for el in f.by_type("IfcProduct"):
        if el.Representation:
            ifcopenshell.geom.create_shape(settings, el)          # raises if geometry is broken
    system = next(s for s in f.by_type("IfcDistributionSystem") if s.Name == "10LAB10BR001")
    grouped = {o.Name for rel in system.IsGroupedBy for o in rel.RelatedObjects}
    assert "10LAB10AA001" in grouped and "SP-001" not in grouped   # supports are not flow elements
    ps = ifcopenshell.util.element.get_psets(next(e for e in f.by_type("IfcValve") if e.Name == "10LAB10AA001"))
    assert ps["Alpilla_Common"]["Line"] == "10LAB10BR001" and ps["Alpilla_Common"]["DesignPressure_barg"] == 190
    assert ps["Alpilla_Model"]["GeometryFidelity"] == "symbolic"
    seg = next(e for e in f.by_type("IfcPipeSegment") if e.Name.endswith("0060"))
    assert ifcopenshell.util.element.get_psets(seg)["Alpilla_Model"]["WallThickness_mm"] == 10.97
    assert any("modelled 3 equipment" in w for w in m["warnings"])
