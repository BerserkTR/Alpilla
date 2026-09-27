"""Case authoring: Owner drawings ALP-OWN-DWG-001 (external connections) and ALP-OWN-DWG-002 (site and construction
area plan) as DXF + PDF. Plant grid in metres (origin SW plot corner, plant north = true north). Simulated received documents.
Tie-in positions follow the tie_in records (location in mm = grid m x 1000)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import ezdxf  # noqa: E402
from ezdxf import const  # noqa: E402
from ezdxf.enums import TextEntityAlignment  # noqa: E402

from engine.core import dxfkit  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
LAYERS = {"PLOT": 7, "SETBACK": 30, "EXIST": 34, "TEMP": 3, "ROAD": 8, "GAS": 30, "OHL": 1, "UTIL": 5, "MARINE": 4,
          "TIEIN": 6, "ANNO": 7, "SEA": 151, "GRIDL": 8, "TITLE": 7, "THIRD": 34}
CW = 0.72                         # DejaVu Sans upper-case character width / height (measured)


def new():
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 6          # metres
    for n, c in LAYERS.items():
        doc.layers.add(n, color=c)
    doc.styles.add("OWN", font="DejaVuSans.ttf")
    doc.styles.add("ALPILLA", font="DejaVuSans.ttf")   # used by dxfkit.title_block
    return doc


def T(msp, s, x, y, h, layer="ANNO", align="LEFT", rot=0.0):
    t = msp.add_text(str(s), height=h, rotation=rot, dxfattribs={"layer": layer, "style": "OWN"})
    t.set_placement((x, y), align={"LEFT": TextEntityAlignment.LEFT, "CENTER": TextEntityAlignment.CENTER,
                                   "MIDDLE": TextEntityAlignment.MIDDLE_CENTER, "RIGHT": TextEntityAlignment.RIGHT}[align])


def text_box(s, x, y, h, align="LEFT", pad=0.5):
    """Approximate extents of a horizontal text (for keeping hatches clear of labels)."""
    w = CW * h * len(s)
    x0 = {"LEFT": x, "CENTER": x - w / 2, "MIDDLE": x - w / 2, "RIGHT": x - w}[align]
    return (x0 - pad * h, y - pad * h, x0 + w + pad * h, y + h * (1 + pad))


def box(msp, x0, y0, x1, y1, layer, hatch=None, scale=1.0, lt=None):
    attrs = {"layer": layer}
    if lt:
        attrs["linetype"] = lt
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs=attrs)
    if hatch:
        h = msp.add_hatch(dxfattribs={"layer": layer})
        if hatch == "SOLID":
            h.set_solid_fill(color=const.BYLAYER)
        else:
            h.set_pattern_fill(hatch, color=const.BYLAYER, scale=scale)
        h.paths.add_polyline_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], is_closed=True)


def sea(msp, outline, scale, holes):
    """Sea hatch with rectangular holes behind labels, tie-ins, scale bar and title block."""
    h = msp.add_hatch(dxfattribs={"layer": "SEA"})
    h.dxf.hatch_style = 0                                   # nested: holes by parity
    h.set_pattern_fill("ANSI33", color=const.BYLAYER, scale=scale)
    h.paths.add_polyline_path(outline, is_closed=True, flags=const.BOUNDARY_PATH_EXTERNAL)
    for x0, y0, x1, y1 in holes:
        h.paths.add_polyline_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], is_closed=True,
                                  flags=const.BOUNDARY_PATH_OUTERMOST)


def tiein(msp, tid, x, y, h, label, dx=1, dy=1, lead=1.6):
    """Tie-in marker + leader; returns the label extents."""
    r = h * 0.7
    msp.add_circle((x, y), r, dxfattribs={"layer": "TIEIN", "lineweight": 35})
    msp.add_line((x - r, y), (x + r, y), dxfattribs={"layer": "TIEIN"})
    msp.add_line((x, y - r), (x, y + r), dxfattribs={"layer": "TIEIN"})
    lx, ly = x + dx * h * lead, y + dy * h * lead
    msp.add_line((x, y), (lx, ly), dxfattribs={"layer": "TIEIN"})
    tx, al = lx + (0.3 * h if dx > 0 else -0.3 * h), "LEFT" if dx > 0 else "RIGHT"
    T(msp, tid, tx, ly + 0.15 * h, h, "TIEIN", al)
    boxes = [text_box(tid, tx, ly + 0.15 * h, h, al)]
    if label:
        T(msp, label, tx, ly - 0.95 * h, h * 0.75, "TIEIN", al)
        boxes.append(text_box(label, tx, ly - 0.95 * h, h * 0.75, al))
    return (min(b[0] for b in boxes + [(x - r, y - r, 0, 0)]), min(b[1] for b in boxes + [(0, y - r, 0, 0)]),
            max(b[2] for b in boxes + [(0, 0, x + r, 0)]), max(b[3] for b in boxes + [(0, 0, 0, y + r)]))


def north(msp, x, y, s):
    msp.add_lwpolyline([(x, y), (x - 0.5 * s, y - 1.6 * s), (x, y - 1.2 * s), (x + 0.5 * s, y - 1.6 * s)], close=True,
                       dxfattribs={"layer": "ANNO"})
    T(msp, "N", x, y + 0.3 * s, 0.8 * s, "ANNO", "CENTER")


def scalebar(msp, x, y, step, n, h, unit="m"):
    for i in range(n):
        box(msp, x + i * step, y, x + (i + 1) * step, y + h * 0.5, "ANNO", "SOLID" if i % 2 == 0 else None)
        T(msp, f"{i * step:g}", x + i * step, y - 1.4 * h, h, "ANNO", "CENTER")
    T(msp, f"{n * step:g} {unit}", x + n * step, y - 1.4 * h, h, "ANNO", "CENTER")
    return (x - h * 2, y - 1.8 * h, x + n * step + 3 * h, y + h)


def frame(msp, x0, y0, x1, y1, s):
    box(msp, x0, y0, x1, y1, "ANNO")
    box(msp, x0 + 5 * s, y0 + 5 * s, x1 - 5 * s, y1 - 5 * s, "ANNO")


def legend(msp, x, y, s, items):
    T(msp, "LEGEND", x, y, 3.2 * s)
    for i, (layer, text, lt) in enumerate(items):
        yy = y - (i + 1) * 5.5 * s
        msp.add_line((x, yy + s), (x + 12 * s, yy + s), dxfattribs={"layer": layer, "lineweight": 60, "linetype": lt})
        T(msp, text, x + 15 * s, yy, 2.4 * s)


def titleblock(msp, xr, yb, s, fields, width=150, row_h=7):
    dxfkit.title_block(msp, xr, yb, s, fields, width, row_h)
    return (xr - width * s, yb, xr, yb + len(fields) * row_h * s)


def paper(s, mm, x0, y0):
    """Sheet extents for paper size mm at s metres per paper mm, lower-left corner (x0, y0)."""
    return x0, y0, x0 + mm[0] * s, y0 + mm[1] * s


# ============================================================ DWG-002 site and construction area plan (A1 portrait)
def dwg002():
    doc = new()
    m = doc.modelspace()
    s = 1.25                    # metres per paper mm = 1:1,250 on A1
    h = 2.6 * s                 # standard text height 2.6 mm on paper
    X0, Y0, X1, Y1 = paper(s, (594, 841), -190, -365)
    ib = 5 * s                  # inner border offset
    holes = []
    # ---- sea (cut at the sheet bottom; offshore tie-ins shown by arrows)
    shore = [(X0 + ib + 20 * i, -60 + 3 * math.sin(i / 2.0)) for i in range(int((X1 - X0 - 2 * ib) / 20) + 1)] + [(X1 - ib, -60)]
    m.add_lwpolyline(shore, dxfattribs={"layer": "MARINE", "lineweight": 50})
    T(m, "SEA OF MARMARA", -80, -210, 3 * h, "MARINE", "CENTER")
    holes.append(text_box("SEA OF MARMARA", -80, -210, 3 * h, "CENTER"))
    T(m, "PUBLIC COASTAL STRIP (60 m): no permanent structures except intake/outfall pipes and the temporary barge landing",
      205, -30, h * 0.75, "SETBACK", "CENTER")
    # ---- plot and setbacks
    m.add_lwpolyline([(0, 0), (400, 0), (400, 300), (0, 300)], close=True, dxfattribs={"layer": "PLOT", "lineweight": 100})
    T(m, "PLOT BOUNDARY 400 m x 300 m = 12.0 ha, platform levelled to +15.0 m", 200, 250, h, "PLOT", "CENTER")
    box(m, 20, 12, 395, 295, "SETBACK", lt="DASHED")
    T(m, "USABLE AREA (about 10.6 ha): E 20-395, N 12-295", 200, 238, h * 0.8, "SETBACK", "CENTER")
    box(m, 2, 0, 6, 300, "MARINE", "ANSI31", 1.0)
    T(m, "SEASONAL STREAM CHANNEL 3 x 2 m + 10 m BUFFER (keep open)", 12, 75, h * 0.75, "MARINE", "CENTER", 90)
    # ---- existing features
    box(m, 300, 20, 360, 60, "EXIST", "ANSI37", 1.5)
    T(m, "EXISTING FOUNDATIONS (1,200 m2)", 330, 64, h * 0.75, "EXIST", "CENTER")
    T(m, "demolition by Contractor", 330, 14, h * 0.75, "EXIST", "CENTER")
    m.add_line((390, 0), (390, Y1 - ib), dxfattribs={"layer": "EXIST", "linetype": "DASHDOT", "lineweight": 35})
    T(m, "EXISTING BURIED 11 kV CABLE - RELOCATED BY OWNER BY 2027-06-30", 385, 150, h * 0.75, "EXIST", "CENTER", 90)
    m.add_circle((20, 280), 3, dxfattribs={"layer": "EXIST"})
    T(m, "MET MAST (keep)", 26, 278, h * 0.75, "EXIST")
    for x, y in ((100, 150), (250, 80), (330, 240)):
        m.add_circle((x, y), 2, dxfattribs={"layer": "EXIST"})
        T(m, "GW monitoring well", x + 4, y - 1, h * 0.7, "EXIST")
    # ---- access road and gate
    for x in (197, 203):
        m.add_line((x, 300), (x, Y1 - ib), dxfattribs={"layer": "ROAD", "lineweight": 50})
    T(m, "EXISTING ACCESS ROAD 6 m (to state road 1.2 km N)", 193, 480, h * 0.8, "ROAD", "CENTER", 90)
    m.add_line((193, 300), (207, 300), dxfattribs={"layer": "PLOT", "lineweight": 100})
    T(m, "NORTH GATE", 192, 303, h * 0.75, "PLOT", "RIGHT")
    # ---- temporary construction area
    box(m, 0, 320, 180, 600, "TEMP", "ANSI32", 5)
    for i, (txt, k) in enumerate((("TEMPORARY CONSTRUCTION AREA (TP-A1)", 1.0), ("E 0-180, N 320-600 = 5.04 ha", 0.85),
                                  ("available 2027-03-01 until Taking-Over; reinstated by Contractor", 0.75))):
        T(m, txt, 90, 470 - i * 13, h * k, "TEMP", "CENTER")
    # ---- utilities along the access road (Owner, to the gate)
    for off, layer, lt in ((8, "UTIL", "DASHED"), (12, "OHL", "CONTINUOUS"), (16, "UTIL", "DOT")):
        m.add_line((200 + off, 300), (200 + off, Y1 - ib), dxfattribs={"layer": layer, "linetype": lt})
    T(m, "POTABLE WATER DN150 / 34.5 kV CONSTRUCTION POWER / FIBRE (Owner)", 222, 520, h * 0.75, "UTIL", "CENTER", 90)
    # ---- gas spur
    m.add_lwpolyline([(535, Y1 - ib), (470, 420), (380, 300)], dxfattribs={"layer": "GAS", "lineweight": 70})
    T(m, "16\" GAS SPUR LINE (Owner) - 4.5 km from tap station", 492, 540, h * 0.8, "GAS", "CENTER", 74)
    # ---- 380 kV OHL: routed west of the temporary area, dead-end tower outside the plot
    ohl = [(X0 + ib, 560), (-80, 335), (-25, 300), (30, 290)]
    m.add_lwpolyline(ohl, dxfattribs={"layer": "OHL", "lineweight": 70})
    for x, y in ohl[1:3]:
        box(m, x - 5, y - 5, x + 5, y + 5, "OHL")
    (ax, ay), (bx, by) = ohl[0], ohl[1]
    ln = math.dist(ohl[0], ohl[1])
    ux, uy = (bx - ax) / ln, (by - ay) / ln                  # along the line
    nx, ny = -uy, ux                                        # text "up" direction for the rotation below
    px, py = ax + 0.45 * (bx - ax) - 3 * nx - h * 0.8 * nx, ay + 0.45 * (by - ay) - 3 * ny - h * 0.8 * ny
    T(m, "380 kV DOUBLE-CIRCUIT OHL (Owner) - 7 km to TSO substation", px, py, h * 0.8, "OHL", "CENTER",
      math.degrees(math.atan2(uy, ux)))
    T(m, "dead-end tower", -32, 294, h * 0.7, "OHL", "RIGHT")
    # ---- marine: CW pump house, intake/outfall corridors (continue off-sheet), barge landing
    box(m, 135, 12, 165, 22, "MARINE")
    T(m, "CW pump house (indicative)", 150, 24, h * 0.7, "MARINE", "CENTER")
    yb = Y0 + 50 * s            # corridors stop above the scale bar / title block band
    for x in (145, 155, 260):
        m.add_line((x, 12), (x, yb), dxfattribs={"layer": "MARINE", "linetype": "DASHED", "lineweight": 35})
    for x in (150, 260):
        m.add_lwpolyline([(x - 6, yb + 8), (x, yb), (x + 6, yb + 8)], dxfattribs={"layer": "MARINE", "lineweight": 35})
    T(m, "INTAKE CORRIDOR 2 x DN2200", 139, -170, h * 0.75, "MARINE", "CENTER", 90)
    T(m, "OUTFALL CORRIDOR DN2400", 254, -170, h * 0.75, "MARINE", "CENTER", 90)
    for txt, x, al in (("to TP-CW1: intake head 650 m offshore, -12 m", 140, "RIGHT"),
                       ("to TP-CW2: outfall diffuser 350 m offshore, -8 m", 268, "LEFT")):
        T(m, txt, x, yb + 2, h * 0.8, "TIEIN", al)
        holes.append(text_box(txt, x, yb + 2, h * 0.8, al))
    holes += [(130, yb - 2, 170, -60), (245, yb - 2, 275, -60)]       # keep the corridors readable
    box(m, 100, -75, 140, -40, "MARINE", "ANSI31", 2)
    T(m, "TEMPORARY BARGE LANDING (Contractor)", 120, -86, h * 0.75, "MARINE", "CENTER")
    holes.append(text_box("TEMPORARY BARGE LANDING (Contractor)", 120, -86, h * 0.75, "CENTER"))
    holes.append((100, -75, 140, -40))
    # ---- tie-ins (tie_in records)
    tiein(m, "TP-G1", 380, 300, h, "gas 16\", 45-70 barg, 2028-06-30", 1, 1, lead=4)
    tiein(m, "TP-E1", 30, 290, h, "380 kV line gantry, 2028-07-15", 1, 1, lead=6)
    tiein(m, "TP-W1 / E2 / T1 / R1 / L1", 200, 300, h, "water, 34.5 kV, fibre, road, LDO tankers - at north gate", 1, -1, lead=4)
    tiein(m, "TP-D1", 4, 150, h, "storm water to stream channel or sea", 1, 1, lead=3.5)
    holes.append(tiein(m, "TP-M1", 120, -40, h, "barge landing, permit by 2027-09-30", -1, 0, lead=7))
    tiein(m, "TP-A1", 180, 600, h, "temporary area 5.04 ha, 2027-03-01", -1, 1)
    for i, note in enumerate(("NOTES", "1. TP-S1: no municipal sewer. Contractor's sanitary treatment plant;",
                              "    treated effluent to the outfall (TP-CW2).",
                              "2. Crane exclusion zone 30 m each side of the 380 kV OHL.",
                              "3. Intake and outfall corridors continue offshore beyond this sheet.",
                              "4. External routes: ALP-OWN-DWG-001; data: ALP-OWN-GEN-001.")):
        T(m, note, 232, 565 - i * 1.6 * h * 0.75, h * (0.9 if i == 0 else 0.75), "ANNO")
    # ---- neighbours
    T(m, "RECEPTOR 900 m NE ->", 548, 450, h * 0.8, "ANNO", "RIGHT")
    T(m, "<- CEMENT TERMINAL 700 m W", X0 + ib + 5, 180, h * 0.8)
    # ---- grid ticks (plant grid, m)
    tb = (X1 - ib - 150 * s, Y0 + ib, X1 - ib, Y0 + ib + 9 * 7 * s)
    for e in range(-100, 501, 100):
        m.add_line((e, Y1 - ib), (e, Y1 - ib - 8), dxfattribs={"layer": "GRIDL"})
        T(m, f"E {e}", e - 2, Y1 - ib - 8, h * 0.75, "GRIDL", "RIGHT")
        if e + 20 < tb[0]:
            m.add_line((e, Y0 + ib), (e, Y0 + ib + 8), dxfattribs={"layer": "GRIDL"})
            T(m, f"E {e}", e + 2, Y0 + ib + 4, h * 0.75, "GRIDL")
            holes.append(text_box(f"E {e}", e + 2, Y0 + ib + 4, h * 0.75))
    for n in range(-300, 601, 100):
        m.add_line((X0 + ib, n), (X0 + ib + 8, n), dxfattribs={"layer": "GRIDL"})
        T(m, f"N {n}", X0 + ib + 10, n - 1.5, h * 0.75, "GRIDL")
        if n < -60:
            holes.append(text_box(f"N {n}", X0 + ib + 10, n - 1.5, h * 0.75))
    for e in range(-100, 501, 100):             # grid crosses on land
        for n in range(100, 601, 100):
            if not (0 <= e <= 400 and 0 <= n <= 300) and not (0 <= e <= 180 and 320 <= n <= 600) \
                    and not (230 <= e <= 370 and 470 <= n <= 660):      # temp area, legend/notes
                m.add_line((e - 3, n), (e + 3, n), dxfattribs={"layer": "GRIDL"})
                m.add_line((e, n - 3), (e, n + 3), dxfattribs={"layer": "GRIDL"})
    north(m, 470, 665, 10)
    holes.append(scalebar(m, -150, Y0 + ib + 30, 25, 4, h))
    legend(m, 250, 655, s, [("PLOT", "plot boundary", "CONTINUOUS"), ("SETBACK", "usable area / setbacks", "DASHED"),
                            ("EXIST", "existing features", "DASHDOT"), ("TEMP", "temporary construction area", "CONTINUOUS"),
                            ("ROAD", "road", "CONTINUOUS"), ("GAS", "gas spur (Owner)", "CONTINUOUS"),
                            ("OHL", "380 kV OHL / 34.5 kV (Owner)", "CONTINUOUS"), ("UTIL", "water / fibre (Owner)", "DASHED"),
                            ("MARINE", "marine / drainage / CW corridors", "DASHED"), ("TIEIN", "tie-in point TP-xx", "CONTINUOUS")])
    frame(m, X0, Y0, X1, Y1, s)
    holes.append(titleblock(m, X1 - ib, Y0 + ib, s, [
        ("OWNER", "Alpilla Enerji Uretim A.S. (fictional)"), ("PROJECT", "Alpilla 600 MW CCGT"),
        ("TITLE", "SITE AND CONSTRUCTION AREA PLAN"), ("DWG NO / REV", "ALP-OWN-DWG-002  Rev 0"),
        ("COORDINATES", "plant grid (m), origin SW plot corner, N = true N"), ("SCALE", "1:1,250 on A1"),
        ("DATE / STATUS", "2026-09-27  issued for contract"), ("PREP. / APPR.", "Owner's Engineer / Project Director"),
        ("NOTE", "CASE STUDY - fictional")]))
    sea(m, shore + [(X1 - ib, Y0 + ib), (X0 + ib, Y0 + ib)], 6, holes)
    assert not doc.audit().has_errors
    doc.saveas(OUT / "ALP-OWN-DWG-002_Rev0.dxf")
    dxfkit.save_pdf(doc, OUT / "ALP-OWN-DWG-002_Rev0.pdf", (594, 841))


# ============================================================ DWG-001 external connections (A3 landscape)
def dwg001():
    doc = new()
    m = doc.modelspace()
    s = 25.0                    # metres per paper mm = 1:25,000 on A3
    h = 2.4 * s
    X0, Y0, X1, Y1 = paper(s, (420, 297), -6900, -1500)
    ib = 5 * s
    holes = []
    coast = [(X0 + ib + 250 * i, -60 + 90 * math.sin(i / 3.1) + (0 if i < 20 else 40 * math.sin(i)))
             for i in range(int((X1 - X0 - 2 * ib) / 250) + 1)] + [(X1 - ib, -40)]
    m.add_lwpolyline(coast, dxfattribs={"layer": "MARINE", "lineweight": 50})
    T(m, "SEA OF MARMARA", -3000, -1000, 2.5 * h, "MARINE", "CENTER")
    holes.append(text_box("SEA OF MARMARA", -3000, -1000, 2.5 * h, "CENTER"))
    box(m, 0, 0, 400, 300, "PLOT", "SOLID")
    T(m, "ALPILLA SITE (12 ha) - see ALP-OWN-DWG-002", 480, 60, h * 0.9, "PLOT")
    box(m, 0, 320, 180, 600, "TEMP", "ANSI31", 15)
    # state road with bridges
    road = [(X0 + ib, 1300), (-4000, 1380), (-2000, 1420), (0, 1500), (1800, 1640), (X1 - ib, 1760)]
    m.add_lwpolyline(road, dxfattribs={"layer": "ROAD", "lineweight": 70})
    T(m, "STATE ROAD (heavy transport route from the east, 120 t bridges)", -6500, 1440, h * 0.9, "ROAD")
    for x, y in ((-2000, 1420), (1800, 1640)):
        box(m, x - 60, y - 60, x + 60, y + 60, "THIRD")
        T(m, "BRIDGE 120 t", x, y + 110, h * 0.75, "THIRD", "CENTER")
    m.add_lwpolyline([(200, 300), (200, 1500)], dxfattribs={"layer": "ROAD", "lineweight": 50})
    T(m, "ACCESS ROAD 1.2 km", 140, 900, h * 0.75, "ROAD", "CENTER", 90)
    for i, note in enumerate(("NOTES", "1. Potable water DN150, 34.5 kV construction power and telecom fibre run along the access road",
                              "    to the north gate (Owner scope, ALP-OWN-GEN-001 section 5).",
                              "2. Routes are indicative; final alignments by the Owner's pipeline and line contractors.",
                              "3. Site layout, temporary construction area and all tie-in points: ALP-OWN-DWG-002.")):
        T(m, note, -6500, 1000 - i * 1.6 * h * 0.8, h * (0.9 if i == 0 else 0.75), "ANNO")
    # gas
    gas = [(X0 + ib, 4550), (-2000, 4720), (900, 4800), (X1 - ib, 4980)]
    m.add_lwpolyline(gas, dxfattribs={"layer": "GAS", "lineweight": 70})
    T(m, "EXISTING 36\" GAS TRANSMISSION LINE (network operator)", -1900, 4800, h * 0.85, "GAS")
    box(m, 850, 4750, 950, 4850, "GAS", "SOLID")
    T(m, "TAP VALVE STATION (Owner)", 1000, 4880, h * 0.75, "GAS")
    spur = [(900, 4800), (700, 3000), (450, 1600), (380, 300)]
    m.add_lwpolyline(spur, dxfattribs={"layer": "GAS", "lineweight": 50, "linetype": "DASHED"})
    L = sum(math.dist(a, b) for a, b in zip(spur, spur[1:]))
    T(m, f"16\" GAS SPUR (Owner) {L / 1000:.1f} km", 780, 3000, h * 0.85, "GAS")
    # grid connection
    box(m, -4750, 5450, -4250, 5750, "OHL", "ANSI37", 25)
    T(m, "TSO 380 kV SUBSTATION 'KIYI'", -4150, 5560, h * 0.85, "OHL")
    ohl = [(-4500, 5600), (-2500, 3200), (-80, 335), (30, 290)]
    m.add_lwpolyline(ohl, dxfattribs={"layer": "OHL", "lineweight": 50})
    L2 = sum(math.dist(a, b) for a, b in zip(ohl, ohl[1:]))
    for a, b in zip(ohl[:2], ohl[1:3]):
        n = int(math.dist(a, b) // 400)
        for k in range(1, n + 1):
            x, y = a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n
            m.add_circle((x, y), 25, dxfattribs={"layer": "OHL"})
    T(m, f"380 kV DOUBLE-CIRCUIT OHL (Owner) {L2 / 1000:.1f} km", -2300, 3300, h * 0.85, "OHL")
    # neighbours, port, marine
    for x, y in ((820, 760), (880, 820), (860, 740), (920, 780)):
        box(m, x - 15, y - 15, x + 15, y + 15, "THIRD", "SOLID")
    T(m, "VILLAGE (nearest receptor, 900 m)", 980, 760, h * 0.75, "THIRD")
    box(m, -700, 0, -400, 300, "THIRD", "ANSI31", 8)
    T(m, "CEMENT TERMINAL", -760, 120, h * 0.75, "THIRD", "RIGHT")
    barge = [(X0 + ib + 100, -700), (-2000, -500), (120, -60)]
    m.add_lwpolyline(barge, dxfattribs={"layer": "MARINE", "linetype": "DASHED", "lineweight": 35})
    lbl = "HEAVY-LIFT BARGE ROUTE from port (18 km by sea)"
    T(m, lbl, X0 + ib + 150, -620, h * 0.8, "MARINE")
    holes.append(text_box(lbl, X0 + ib + 150, -620, h * 0.8))
    for x in (150, 260):                       # shortened at the title block; true lengths in the label
        m.add_line((x, -60), (x, -250), dxfattribs={"layer": "MARINE"})
    T(m, "CW intake 650 m / outfall 350 m offshore", 60, -480, h * 0.75, "MARINE", "RIGHT")
    holes.append(text_box("CW intake 650 m / outfall 350 m offshore", 60, -480, h * 0.75, "RIGHT"))
    tiein(m, "TP-G1", 380, 300, h * 0.9, "", 1, -1)
    tiein(m, "TP-E1", 30, 290, h * 0.9, "", -1, -1)
    # annotation
    north(m, X1 - ib - 400, Y1 - ib - 400, 250)
    legend(m, X0 + ib + 250, Y1 - ib - 150, s, [
        ("GAS", "gas pipeline / spur (dashed)", "CONTINUOUS"), ("OHL", "380 kV OHL with towers", "CONTINUOUS"),
        ("ROAD", "state road / access road", "CONTINUOUS"), ("MARINE", "coast / barge route / CW", "DASHED"),
        ("THIRD", "third party / bridges", "CONTINUOUS"), ("TEMP", "temporary construction area", "CONTINUOUS"),
        ("TIEIN", "tie-in point TP-xx", "CONTINUOUS")])
    holes.append(scalebar(m, -6500, Y0 + ib + 200, 500, 4, h * 0.8))
    frame(m, X0, Y0, X1, Y1, s)
    holes.append(titleblock(m, X1 - ib, Y0 + ib, s, [
        ("OWNER", "Alpilla Enerji Uretim A.S. (fictional)"), ("PROJECT", "Alpilla 600 MW CCGT"),
        ("TITLE", "EXTERNAL CONNECTIONS - GAS, GRID, ROAD, WATER"), ("DWG NO / REV", "ALP-OWN-DWG-001  Rev 0"),
        ("COORDINATES", "plant grid (m); routes indicative"), ("SCALE", "1:25,000 on A3"),
        ("DATE / STATUS", "2026-09-27  issued for contract"), ("NOTE", "CASE STUDY - fictional")], width=135, row_h=5.5))
    sea(m, coast + [(X1 - ib, Y0 + ib), (X0 + ib, Y0 + ib)], 60, holes)
    assert not doc.audit().has_errors
    doc.saveas(OUT / "ALP-OWN-DWG-001_Rev0.dxf")
    dxfkit.save_pdf(doc, OUT / "ALP-OWN-DWG-001_Rev0.pdf", (420, 297))
    return L, L2


dwg002()
print("routes (km):", [round(x / 1000, 2) for x in dwg001()])
