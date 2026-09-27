"""PCF: writer output, attribute map, round trip through the reader, Plant 3D-style import."""
from engine.cli import main
from engine.core import pcf, validate
from engine.core.runner import run_engine
from engine.core.store import Store
from engine.engines import registry
from tests.conftest import who
from tests.piping_fixture import seed_piping

GEOM = ("type", "end1", "end2", "centre", "branch", "dn2", "tag", "valve_type", "support_type")


def test_pcf_engine_output(project):
    s = Store(project, who())
    seed_piping(s)
    m = run_engine(project, Store(project, who()), registry()["piping_pcf"], {})
    assert sorted(m["files"]) == ["10LAB10BR001.pcf", "10LAB10BR002.pcf", "_PCF_ATTRIBUTE_MAP.txt"]
    raw = (project.output / "piping_pcf" / "10LAB10BR001.pcf").read_bytes()
    assert b"\r\n" in raw
    t = raw.decode().replace("\r\n", "\n")
    assert t.startswith("ISOGEN-FILES ISOGEN.FLS\nUNITS-BORE MM\nUNITS-CO-ORDS MM")
    assert "PIPELINE-REFERENCE 10LAB10BR001\n    PROJECT-IDENTIFIER ALP\n    PIPING-SPEC D1A" in t
    assert "ELBOW\n    END-POINT 10000.0000 5000.0000 4000.0000 150\n    END-POINT 10229.0000 5000.0000 4229.0000 150\n" \
           "    CENTRE-POINT 10000.0000 5000.0000 4229.0000\n    SKEY ELBW" in t
    assert "REDUCER-CONCENTRIC\n    END-POINT 18000.0000 5000.0000 4229.0000 150\n    END-POINT 18152.0000 5000.0000 4229.0000 100" in t
    assert "    SKEY CKFL\n    ITEM-DESCRIPTION check VALVE\n    COMPONENT-IDENTIFIER 10LAB10AA001" in t
    assert "SUPPORT\n    CO-ORDS 14000.0000 5000.0000 4229.0000 150\n    NAME SP-001\n    ITEM-DESCRIPTION GUIDE" in t
    assert "    COMPONENT-ATTRIBUTE1 190\n    COMPONENT-ATTRIBUTE2 160" in t
    assert "    COMPONENT-ATTRIBUTE8 10.97" in t                    # XS wall from spec schedule
    assert "COMPONENT-ATTRIBUTE10  fluid density [kg/m3]" in (project.output / "piping_pcf" / "_PCF_ATTRIBUTE_MAP.txt").read_text()
    assert any("10LAB10BR002: no routed components" in w for w in m["warnings"])


def test_round_trip_and_cli_import(project, tmp_path, capsys):
    s = Store(project, who())
    seed_piping(s)
    text, _ = pcf.write(s, "10LAB10BR001", "ALP")
    parsed, skipped = pcf.parse(text)
    original = [c for c in sorted(s.records("pipe_component"), key=lambda c: c["seq"])]
    assert skipped == [] and len(parsed) == len(original)
    for a, b in zip(original, parsed):
        for k in GEOM:
            assert a.get(k) == b.get(k), (a["seq"], k, a.get(k), b.get(k))
    # import into a second, empty line through the CLI, then re-export: identical geometry
    s.create("line", {"id": "10LAB20BR001", "service": "BFP B discharge", "system": "10LAB", "dn": "DN150",
                      "spec": "D1A", "design_pressure": 190, "design_temperature": 160}, "t")
    f = tmp_path / "plant3d_export.pcf"
    f.write_text(text.replace("PIPELINE-REFERENCE 10LAB10BR001", "PIPELINE-REFERENCE 10LAB20BR001")
                 + "MATERIALS\nITEM-CODE X1\n    DESCRIPTION something\n")
    assert main(["db", "import-pcf", str(f), "--line", "10LAB20BR001", "--reason", "Plant 3D iso export"]) == 0
    out = capsys.readouterr().out
    assert "9 component(s)" in out and "unsupported" not in out   # MATERIALS section is not components
    assert main(["db", "import-pcf", str(f), "--line", "10LAB20BR001", "--reason", "again"]) == 1
    assert main(["db", "import-pcf", str(f), "--line", "10LAB20BR001", "--replace", "--reason", "rev B"]) == 0
    st = Store(project, who())
    t2, _ = pcf.write(st, "10LAB20BR001", "ALP")
    geometry = lambda t: [x for x in t.split("PIPING-SPEC D1A", 1)[1].splitlines()
                          if "COMPONENT-ATTRIBUTE" not in x and "INSULATION-SPEC" not in x]
    assert geometry(t2) == geometry(text)
    assert validate.run(project).ok


def test_reader_refuses_to_guess(project):
    import pytest
    bad = "UNITS-CO-ORDS MM\nVALVE\n    END-POINT 0 0 0 150\n    END-POINT 500 0 0 150\n    SKEY VVFL\n"
    with pytest.raises(ValueError, match="valve type not in PCF"):
        pcf.parse(bad)
    assert pcf.parse(bad, "gate")[0][0]["valve_type"] == "gate"
    with pytest.raises(ValueError, match="only MM"):
        pcf.parse("UNITS-CO-ORDS INCH\nPIPE\n    END-POINT 0 0 0 6\n")
