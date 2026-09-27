"""Small but real piping data set: BFP A discharge to HRSG HP economiser (used by piping/drawing/model tests)."""
from engine.core.store import Store

R = "piping fixture"
SIZES = [("DN100", "4", 114.3, 6.02, 8.56), ("DN150", "6", 168.3, 7.11, 10.97), ("DN200", "8", 219.1, 8.18, 12.70)]


def seed_piping(s: Store):
    s.create("project", {"id": "ALP", "name": "Alpilla CCGT", "plant_type": "CCGT"}, R)
    s.create("reference", {"id": "REF-AAA-0001", "title": "Welded and Seamless Wrought Steel Pipe", "code": "ASME B36.10M"}, R)
    for dn, nps, od, std, xs in SIZES:
        s.create("pipe_size", {"id": dn, "nps": nps, "od": od, "wall_std": std, "wall_xs": xs,
                               "basis_refs": ["reference:REF-AAA-0001"]}, R)
    s.create("pipe_spec", {"id": "D1A", "rating": "CL1500", "material": "ASTM A106 Gr.C", "corrosion_allowance": 1.5,
                           "schedule": "XS", "max_design_pressure": 250, "max_design_temperature": 200}, R)
    s.create("system", {"id": "10LAB", "title": "Feedwater piping", "category": "condensate_feedwater"}, R)
    s.create("system", {"id": "10HAC", "title": "HP economiser", "category": "hrsg"}, R)
    s.create("system", {"id": "10LAC", "title": "Feedwater pumps", "category": "condensate_feedwater"}, R)
    s.create("document", {"id": "ALP-PID-10LAB-001", "title": "P&ID HP feedwater", "discipline": "process",
                          "doc_type": "diagram"}, R)
    s.create("equipment", {"id": "10LAA10BB001", "description": "Feedwater tank / deaerator", "system": "10LAB",
                           "equipment_type": "tank", "shape": "horizontal_cylinder", "position": [2000, 5000, 8000],
                           "length": 9000, "diameter": 3200, "orientation": 0, "pid": "ALP-PID-10LAB-001"}, R)
    s.create("equipment", {"id": "10LAC10AP001", "description": "HP/IP boiler feed pump A", "system": "10LAC",
                           "equipment_type": "pump", "shape": "box", "position": [10000, 5000, 0], "length": 4500,
                           "width": 1600, "height": 1200, "orientation": 0, "rated_power": 3200,
                           "pid": "ALP-PID-10LAB-001"}, R)
    s.create("equipment", {"id": "10HAC10AC001", "description": "HP economiser 1", "system": "10HAC",
                           "equipment_type": "heat exchanger", "shape": "box", "position": [20000, 5000, 0],
                           "length": 3000, "width": 6000, "height": 12000, "pid": "ALP-PID-10LAB-001"}, R)
    s.create("nozzle", {"equipment": "10LAA10BB001", "name": "N5", "service": "outlet", "dn": "DN200",
                        "position": [4000, 5000, 6400], "direction": [0, 0, -1]}, R)
    s.create("nozzle", {"equipment": "10LAC10AP001", "name": "S", "service": "suction", "dn": "DN200",
                        "position": [9000, 5000, 900], "direction": [-1, 0, 0]}, R)
    s.create("nozzle", {"equipment": "10LAC10AP001", "name": "D", "service": "discharge", "dn": "DN150",
                        "position": [10000, 5000, 1200], "direction": [0, 0, 1]}, R)
    s.create("nozzle", {"equipment": "10HAC10AC001", "name": "N1", "service": "inlet", "dn": "DN100",
                        "position": [18500, 5000, 4229], "direction": [-1, 0, 0]}, R)
    s.create("line", {"id": "10LAB10BR001", "service": "BFP A discharge", "fluid_code": "BFW", "phase": "liquid",
                      "system": "10LAB", "dn": "DN150", "spec": "D1A", "from_nozzle": "10LAC10AP001_D",
                      "to_nozzle": "10HAC10AC001_N1", "design_pressure": 190, "design_temperature": 160,
                      "operating_pressure": 165, "operating_temperature": 145, "test_pressure": 285,
                      "fluid_density": 920, "flow": 320, "insulation": "hot", "insulation_thickness": 80,
                      "pid": "ALP-PID-10LAB-001"}, R)
    s.create("line", {"id": "10LAB10BR002", "service": "BFP A suction", "fluid_code": "BFW", "phase": "liquid",
                      "system": "10LAB", "dn": "DN200", "spec": "D1A", "from_nozzle": "10LAA10BB001_N5",
                      "to_nozzle": "10LAC10AP001_S", "design_pressure": 16, "design_temperature": 160,
                      "pid": "ALP-PID-10LAB-001"}, R)
    x, y = 10000, 5000
    comps = [
        ("0010", "FLANGE", dict(end1=[x, y, 1200], end2=[x, y, 1350])),
        ("0020", "VALVE", dict(end1=[x, y, 1350], end2=[x, y, 1850], valve_type="check", tag="10LAB10AA001")),
        ("0030", "VALVE", dict(end1=[x, y, 1850], end2=[x, y, 2350], valve_type="gate", tag="10LAB10AA002")),
        ("0040", "PIPE", dict(end1=[x, y, 2350], end2=[x, y, 4000])),
        ("0050", "ELBOW", dict(end1=[x, y, 4000], centre=[x, y, 4229], end2=[x + 229, y, 4229])),
        ("0060", "PIPE", dict(end1=[x + 229, y, 4229], end2=[x + 8000, y, 4229])),
        ("0070", "SUPPORT", dict(end1=[x + 4000, y, 4229], support_type="GUIDE", tag="SP-001")),
        ("0080", "REDUCER-CONCENTRIC", dict(end1=[x + 8000, y, 4229], end2=[x + 8152, y, 4229], dn2="DN100")),
        ("0090", "FLANGE", dict(end1=[x + 8152, y, 4229], end2=[x + 8500, y, 4229], dn="DN100")),
    ]
    for seq, typ, kw in comps:
        s.create("pipe_component", {"line": "10LAB10BR001", "seq": seq, "type": typ, **kw}, R)
    s.create("instrument", {"id": "10LAB10CP001", "function": "PT", "loop": "1001", "service": "BFP A discharge pressure",
                            "line": "10LAB10BR001", "signal": "4-20mA HART", "location": "dcs", "pid": "ALP-PID-10LAB-001"}, R)
    s.create("instrument", {"id": "10LAB10CF001", "function": "FT", "loop": "1002", "service": "BFP A discharge flow",
                            "line": "10LAB10BR001", "signal": "4-20mA HART", "location": "dcs", "pid": "ALP-PID-10LAB-001"}, R)
    s.create("instrument", {"id": "10LAB10CT001", "function": "TI", "loop": "1003", "service": "BFP suction temperature",
                            "line": "10LAB10BR002", "location": "field", "pid": "ALP-PID-10LAB-001"}, R)
