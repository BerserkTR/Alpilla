"""DXF drawings: P&ID and plot plan - audit-clean DXF, real blocks with tags, content from the database, PDF print."""
import ezdxf

from engine.core.runner import run_engine
from engine.core.store import Store
from engine.engines import registry
from tests.conftest import who
from tests.piping_fixture import seed_piping


def texts(doc):
    return [e.dxf.text for e in doc.modelspace().query("TEXT")]


def test_pid_sheet(project):
    s = Store(project, who())
    seed_piping(s)
    m = run_engine(project, Store(project, who()), registry()["pid"], {})
    assert sorted(m["files"]) == ["ALP-PID-10LAB-001.dxf", "ALP-PID-10LAB-001.pdf"]
    doc = ezdxf.readfile(project.output / "pid" / "ALP-PID-10LAB-001.dxf")
    assert doc.dxfversion == "AC1032" and not doc.audit().has_errors
    inserts = doc.modelspace().query("INSERT")
    tags = {i.dxf.name: i.get_attrib_text("TAG") for i in inserts if i.has_attrib("TAG")}
    assert tags == {"DRUM_H": "10LAA10BB001", "PUMP": "10LAC10AP001", "COIL": "10HAC10AC001"}
    names = [i.dxf.name for i in inserts]
    assert names.count("V_CHECK") == 1 and names.count("V_GATE") == 1 and names.count("REDUCER") == 1
    assert names.count("INST_DCS") == 2 and names.count("INST_FIELD") == 1
    t = texts(doc)
    assert "10LAB10BR001-150-D1A-H" in t and "10LAB10BR002-200-D1A" in t
    assert {"PT", "FT", "TI", "1001", "10LAB10AA001", "150x100"} <= set(t)
    pipes = doc.modelspace().query('LWPOLYLINE[layer=="PIPE"]')
    for p in pipes:                                   # orthogonal routing only
        pts = [q[:2] for q in p.get_points()]
        assert all(abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6 for a, b in zip(pts, pts[1:]))
    assert (project.output / "pid" / "ALP-PID-10LAB-001.pdf").read_bytes()[:4] == b"%PDF"


def test_pid_offpage_connector(project):
    s = Store(project, who())
    seed_piping(s)
    s.create("document", {"id": "ALP-PID-10HAC-001", "title": "P&ID HP economiser", "discipline": "process",
                          "doc_type": "diagram"}, "t")
    s.update("equipment", "10HAC10AC001", {"pid": "ALP-PID-10HAC-001"}, "moved to its own sheet")
    run_engine(project, Store(project, who()), registry()["pid"], {})
    doc = ezdxf.readfile(project.output / "pid" / "ALP-PID-10LAB-001.dxf")
    assert "OFFPAGE" in [i.dxf.name for i in doc.modelspace().query("INSERT")]
    assert {"to 10HAC10AC001", "ALP-PID-10HAC-001"} <= set(texts(doc))
    assert (project.output / "pid" / "ALP-PID-10HAC-001.dxf").exists()


def test_plot_plan(project):
    seed_piping(Store(project, who()))
    run_engine(project, Store(project, who()), registry()["plot_plan"], {})
    doc = ezdxf.readfile(project.output / "plot_plan" / "ALP_plot_plan.dxf")
    assert not doc.audit().has_errors
    msp = doc.modelspace()
    eq = msp.query('LWPOLYLINE[layer=="EQPT"]')
    assert len(eq) == 3
    pump = next(p for p in eq if min(q[0] for q in p.get_points()) == 7750)      # 10000 -/+ 4500/2
    xs = sorted({round(q[0]) for q in pump.get_points()}); ys = sorted({round(q[1]) for q in pump.get_points()})
    assert xs == [7750, 12250] and ys == [4200, 5800]
    assert "10LAB10BR001  DN150-D1A" in texts(doc)
    assert msp.query('LWPOLYLINE[layer=="PIPE"]')


def test_pdf_print_keeps_paper_size(tmp_path):
    """ezdxf's finalize() resizes the matplotlib figure; the PDF must still be printed on the requested paper."""
    import re

    from engine.core import dxfkit
    doc = dxfkit.new_doc()
    doc.modelspace().add_line((0, 0), (420, 297))
    pdf = dxfkit.save_pdf(doc, tmp_path / "a3.pdf", (420, 297)).read_bytes()
    box = [float(v) for v in re.search(rb"/MediaBox \[\s*([\d.\s]+)\]", pdf).group(1).split()]
    assert abs(box[2] - 420 / 25.4 * 72) < 1 and abs(box[3] - 297 / 25.4 * 72) < 1
