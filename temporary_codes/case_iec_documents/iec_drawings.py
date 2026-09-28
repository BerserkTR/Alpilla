"""Case authoring: Imaginary Electric general arrangement drawings IEC-ALP-GA-100..104 (DXF + PDF, A1), simulated received
vendor documents. Plant grid in metres (origin SW plot corner, plant north = true north), levels EL m (grade +15.0).
Weights and main dimensions follow the IEC datasheets (DS-101..106) and IEC-ALP-REQ-001 sections 9-11; buildings, roads,
pads and fire walls are EPC items shown as IEC space requirements. Writes only to the folder given on the command line.
Usage: python iec_drawings.py <out_dir> [GA100 GA101 ...]"""
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import ezdxf  # noqa: E402
from ezdxf import const  # noqa: E402
from ezdxf.enums import TextEntityAlignment  # noqa: E402

from engine.core import dxfkit  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
DATE, REV = "2026-09-28", "0"
LAYERS = {"IEC": 7, "EPC": 8, "MAINT": 6, "LAYDOWN": 3, "CRANE": 5, "PAD": 30, "ACCESS": 1, "DIM": 1, "ANNO": 7, "TITLE": 7,
          "PLOT": 8, "TIEIN": 6, "HIDDEN": 8, "SEA": 4, "EXCL": 1}
CW = 0.78                       # DejaVu Sans average width / height (with margin)
GRADE = 15.0


# ------------------------------------------------------------------------------------------------ drawing primitives
class Sheet:
    def __init__(self, s, x0, y0, paper=(841, 594)):
        self.doc = ezdxf.new("R2018", setup=True)
        self.doc.header["$INSUNITS"] = 6
        for n, c in LAYERS.items():
            self.doc.layers.add(n, color=c)
        self.doc.styles.add("IEC", font="DejaVuSans.ttf")
        self.doc.styles.add("ALPILLA", font="DejaVuSans.ttf")
        self.m = self.doc.modelspace()
        self.s, self.paper = s, paper
        self.X0, self.Y0, self.X1, self.Y1 = x0, y0, x0 + paper[0] * s, y0 + paper[1] * s
        self.h = 2.5 * s
        self.boxes = []                              # label extents: kept free of hatches
        self.labels = []

    def T(self, txt, x, y, k=1.0, layer="ANNO", align="LEFT", rot=0.0, keep=True):
        h = self.h * max(k, 0.76)                    # >= 1.9 mm on paper
        t = self.m.add_text(str(txt), height=h, rotation=rot, dxfattribs={"layer": layer, "style": "IEC"})
        t.set_placement((x, y), align={"LEFT": TextEntityAlignment.LEFT, "CENTER": TextEntityAlignment.CENTER,
                                       "RIGHT": TextEntityAlignment.RIGHT, "MIDDLE": TextEntityAlignment.MIDDLE_CENTER}[align])
        if keep and rot == 0:
            w = CW * h * len(str(txt))
            x0 = {"LEFT": x, "CENTER": x - w / 2, "MIDDLE": x - w / 2, "RIGHT": x - w}[align]
            yb = y - h / 2 if align == "MIDDLE" else y
            self.boxes.append((x0 - 0.2 * h, yb - 0.25 * h, x0 + w + 0.2 * h, yb + 1.15 * h))
            self.labels.append(str(txt))

    def rect(self, x0, y0, x1, y1, layer, lt=None, lw=None):
        a = {"layer": layer}
        if lt:
            a["linetype"] = lt
        if lw:
            a["lineweight"] = lw
        self.m.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs=a)

    def hatch(self, x0, y0, x1, y1, layer, pattern, scale):
        """Pattern hatch leaving holes for every label box overlapping it (labels stay readable)."""
        hh = self.m.add_hatch(dxfattribs={"layer": layer})
        hh.set_pattern_fill(pattern, color=const.BYLAYER, scale=scale, style=0)   # style 0: holes by parity
        hh.paths.add_polyline_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], is_closed=True,
                                   flags=const.BOUNDARY_PATH_EXTERNAL)
        for bx0, by0, bx1, by1 in self.boxes:
            cx0, cy0, cx1, cy1 = max(bx0, x0), max(by0, y0), min(bx1, x1), min(by1, y1)
            if cx0 < cx1 and cy0 < cy1:
                hh.paths.add_polyline_path([(cx0, cy0), (cx1, cy0), (cx1, cy1), (cx0, cy1)], is_closed=True,
                                           flags=const.BOUNDARY_PATH_OUTERMOST)

    def zone(self, x0, y0, x1, y1, layer, label, lines=(), k=0.8, pattern="ANSI31", pscale=None, lt="DASHED"):
        """Space requirement: dashed outline, label, hatch around the label."""
        self.rect(x0, y0, x1, y1, layer, lt)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        k = max(k, 0.76)
        allx = [t for t in [label] + list(lines) if t]
        n = len(allx)
        for i, t in enumerate(allx):
            self.T(t, cx, cy + (n / 2 - i - 0.8) * self.h * k * 1.7, k, layer, "CENTER")
        self.hatch(x0, y0, x1, y1, layer, pattern, pscale or self.s * 4)

    def dim(self, p1, p2, off, txt=None, k=0.8):
        """Aligned horizontal / vertical dimension with ticks; off = offset of the dimension line."""
        (x1, y1), (x2, y2) = p1, p2
        if abs(y1 - y2) < 1e-9 or abs(x2 - x1) > abs(y2 - y1):          # horizontal
            y = y1 + off
            self.m.add_line((x1, y1), (x1, y + (0.6 * self.h if off > 0 else -0.6 * self.h)), dxfattribs={"layer": "DIM"})
            self.m.add_line((x2, y2), (x2, y + (0.6 * self.h if off > 0 else -0.6 * self.h)), dxfattribs={"layer": "DIM"})
            self.m.add_line((x1, y), (x2, y), dxfattribs={"layer": "DIM"})
            for x in (x1, x2):
                self.m.add_line((x - 0.4 * self.h, y - 0.4 * self.h), (x + 0.4 * self.h, y + 0.4 * self.h), dxfattribs={"layer": "DIM"})
            self.T(txt or f"{abs(x2 - x1):.1f}", (x1 + x2) / 2, y + 0.3 * self.h, k, "DIM", "CENTER")
        else:                                                           # vertical
            x = x1 + off
            self.m.add_line((x1, y1), (x + (0.6 * self.h if off > 0 else -0.6 * self.h), y1), dxfattribs={"layer": "DIM"})
            self.m.add_line((x2, y2), (x + (0.6 * self.h if off > 0 else -0.6 * self.h), y2), dxfattribs={"layer": "DIM"})
            self.m.add_line((x, y1), (x, y2), dxfattribs={"layer": "DIM"})
            for y in (y1, y2):
                self.m.add_line((x - 0.4 * self.h, y - 0.4 * self.h), (x + 0.4 * self.h, y + 0.4 * self.h), dxfattribs={"layer": "DIM"})
            self.T(txt or f"{abs(y2 - y1):.1f}", x - 0.4 * self.h, (y1 + y2) / 2, k, "DIM", "CENTER", 90, keep=False)

    def arrow(self, pts, layer="ACCESS", label=None, k=0.8, lw=50, at=0):
        self.m.add_lwpolyline(pts, dxfattribs={"layer": layer, "lineweight": lw})
        (ax, ay), (bx, by) = pts[-2], pts[-1]
        L = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        ux, uy = (bx - ax) / L, (by - ay) / L
        a = 1.4 * self.h
        self.m.add_lwpolyline([(bx - a * ux + 0.5 * a * uy, by - a * uy - 0.5 * a * ux), (bx, by),
                               (bx - a * ux - 0.5 * a * uy, by - a * uy + 0.5 * a * ux)], dxfattribs={"layer": layer, "lineweight": lw})
        if label:
            (px, py), (qx, qy) = pts[at], pts[at + 1]
            self.T(label, (px + qx) / 2 + 0.6 * self.h, (py + qy) / 2 + 0.4 * self.h, k, layer)

    def circle(self, x, y, r, layer="IEC", lt=None):
        a = {"layer": layer}
        if lt:
            a["linetype"] = lt
        self.m.add_circle((x, y), r, dxfattribs=a)

    def table(self, x, y, widths_mm, rows, k=0.75, title=None):
        """Table with its top-left corner at (x, y); widths in paper mm; wraps text; returns the bottom y."""
        k = max(k, 0.76)
        s, h = self.s, self.h * k
        assert x + sum(widths_mm) * s <= self.X1 - 10 * s + 1e-6, f"table at x={x} overflows the frame"
        if title:
            self.T(title, x, y + 0.8 * h, 1.05)
            y -= 0.2 * h
        yy = y
        for ri, row in enumerate(rows):
            cells = []
            for w, c in zip(widths_mm, row):
                n = max(4, int((w * s - 1.4 * h) / (CW * h * 1.03)))
                cells.append(textwrap.wrap(str(c), n) or [""])
            lines = max(len(c) for c in cells)
            rh = (lines * 1.45 + 0.7) * h
            xx = x
            for w, c in zip(widths_mm, cells):
                self.rect(xx, yy - rh, xx + w * s, yy, "ANNO")
                for li, t in enumerate(c):
                    self.T(t, xx + 0.6 * h, yy - (li + 1) * 1.45 * h, k * (1.0 if ri else 1.02), "ANNO")
                xx += w * s
            yy -= rh
        return yy

    def frame_and_title(self, docno, title, scale, extra=()):
        s = self.s
        self.rect(self.X0, self.Y0, self.X1, self.Y1, "TITLE")
        self.rect(self.X0 + 10 * s, self.Y0 + 10 * s, self.X1 - 10 * s, self.Y1 - 10 * s, "TITLE", lw=70)
        fields = [("VENDOR", "Imaginary Electric Company - Power Generation Division (fictional)"),
                  ("PROJECT", "Alpilla 600 MW CCGT - 1 x IE-9H.02 multi-shaft power island"),
                  ("CLIENT", "Istanbul EPC (consortium leader) - EPC engineering"),
                  ("TITLE", title), ("DWG NO / REV", f"{docno}  Rev {REV}"),
                  ("SCALE / SHEET", f"{scale} on A1 / 1 of 1"), ("COORDINATES", "plant grid m; levels EL m (grade EL +15.0)"),
                  ("DATE / STATUS", f"{DATE}  issued for EPC layout (reference)")] + list(extra) + [
                  ("NOTE", "CASE STUDY - fictional; IEC proprietary")]
        dxfkit.title_block(self.m, self.X1 - 10 * s, self.Y0 + 10 * s, s, fields, 190, 6.5)
        return self.Y0 + 10 * s + len(fields) * 6.5 * s

    def north(self, x, y):
        s = self.s * 6
        self.m.add_lwpolyline([(x, y), (x - 0.5 * s, y - 1.6 * s), (x, y - 1.2 * s), (x + 0.5 * s, y - 1.6 * s)], close=True,
                              dxfattribs={"layer": "ANNO"})
        self.T("N", x, y + 0.3 * s, 1.4, "ANNO", "CENTER")

    def scalebar(self, x, y, step, n):
        for i in range(n):
            self.rect(x + i * step, y, x + (i + 1) * step, y + self.h * 0.5, "ANNO")
            if i % 2 == 0:
                hh = self.m.add_hatch(dxfattribs={"layer": "ANNO"})
                hh.set_solid_fill(color=const.BYLAYER)
                hh.paths.add_polyline_path([(x + i * step, y), (x + (i + 1) * step, y), (x + (i + 1) * step, y + self.h * 0.5),
                                            (x + i * step, y + self.h * 0.5)], is_closed=True)
            self.T(f"{i * step:g}", x + i * step, y - 1.5 * self.h, 0.8, "ANNO", "CENTER")
        self.T(f"{n * step:g} m", x + n * step, y - 1.5 * self.h, 0.8, "ANNO", "CENTER")

    def legend(self, x, y, items):
        self.T("LEGEND", x, y, 1.1)
        for i, (layer, txt, lt) in enumerate(items):
            yy = y - (i + 1) * 2.3 * self.h
            self.m.add_line((x, yy + 0.4 * self.h), (x + 10 * self.s, yy + 0.4 * self.h),
                            dxfattribs={"layer": layer, "lineweight": 60, "linetype": lt})
            self.T(txt, x + 13 * self.s, yy, 0.8)
        return y - (len(items) + 1) * 2.3 * self.h

    def check(self, stem):
        """All labels inside the inner frame; report overlapping labels (to fix before issue)."""
        fx0, fy0, fx1, fy1 = self.X0 + 10 * self.s, self.Y0 + 10 * self.s, self.X1 - 10 * self.s, self.Y1 - 10 * self.s
        out = [b for b in self.boxes if b[0] < fx0 or b[1] < fy0 or b[2] > fx1 or b[3] > fy1]
        assert not out, f"{stem}: {len(out)} label(s) outside the frame, e.g. {out[:3]}"
        bad = []
        bs = self.boxes
        for i in range(len(bs)):
            for j in range(i + 1, len(bs)):
                a, b = bs[i], bs[j]
                ox = min(a[2], b[2]) - max(a[0], b[0])
                oy = min(a[3], b[3]) - max(a[1], b[1])
                if ox > 0.25 * self.h and oy > 0.35 * self.h:
                    bad.append((i, j, a, b))
        return bad

    def save(self, stem):
        bad = self.check(stem)
        for i, j, a, b in bad:
            print(f"  OVERLAP {stem}: '{self.labels[i]}' / '{self.labels[j]}'")
        assert not self.doc.audit().has_errors
        self.doc.saveas(OUT / f"{stem}.dxf")
        dxfkit.save_pdf(self.doc, OUT / f"{stem}.pdf", self.paper)
        print(stem, "written")


LEGEND = [("IEC", "IEC supply (equipment outline)", "CONTINUOUS"), ("EPC", "EPC item, shown as IEC space requirement", "DASHED"),
          ("MAINT", "maintenance / withdrawal space (keep free)", "DASHED"), ("LAYDOWN", "laydown area", "DASHED"),
          ("CRANE", "crane hook coverage / crane", "DASHDOT"), ("PAD", "crane pad / pre-assembly area (temporary)", "DASHED"),
          ("ACCESS", "vehicle / heavy-haul access (SPMT)", "CONTINUOUS"), ("DIM", "dimension (m)", "CONTINUOUS")]

# ------------------------------------------------------------------------------------------------ arrangement data (grid m)
GT_HALL = (90, 150, 170, 200)
ST_HALL = (85, 60, 170, 110)
GT_AX, ST_AX = 165.0, 95.0
GEN = (112, GT_AX - 2.3, 122.8, GT_AX + 2.3)             # GT generator stator 10.8 x 4.6 (DS-102)
GEN_ROTOR = (97, GT_AX - 1.2, 112, GT_AX + 1.2)          # withdrawal to the west, 15 m
GT_ENCL = (130, GT_AX - 5, 158, GT_AX + 5)               # GT package enclosure 28 x 10 x 9.5
GT_CORE = (134, GT_AX - 2.95, 147.2, GT_AX + 2.95)       # core engine 13.2 x 5.9 (DS-101)
DIFF = (158, GT_AX - 3.6, 166.5, GT_AX + 3.6)            # exhaust diffuser 8.5 x 7.2
FILTER = (130, 128, 150, 146)                            # inlet filter house (18 modules)
GT_LAY = (120, 178, 170, 196)                            # 900 m2 at 10 t/m2 (REQ-001 11)
GT_GSU = (106, 207, 122, 211.1)                          # 16.0 x 4.1 in service (GA-104)
GT_GSU_PIT = (104.5, 205.5, 123.5, 212.6)
HRSG_IN = (166.5, 180)
HRSG = (180, 153, 222, 177)                              # casing 42 x 24 m
HRSG_OUT = (222, 230)
STACK = (236.0, GT_AX, 4.6)                              # D 9.2 m (EPC)
HRSG_PAD = (182, 185, 222, 213)
MOD_LAY = (250, 145, 290, 195)
CAT_LAY = (195, 138, 215, 148)
ST_GEN = (105, ST_AX - 2.05, 113.6, ST_AX + 2.05)        # ST generator stator 8.6 x 4.1
ST_ROTOR = (93, ST_AX - 0.9, 105, ST_AX + 0.9)
HP_TURB = (122, ST_AX - 2.5, 130, ST_AX + 2.5)
IPLP = (134, ST_AX - 4.5, 150, ST_AX + 4.5)
COND = (132, 64, 152, 84)                                # 4 modules, tubes E-W 9.35 m
TUBE_PULL = (152, 66, 163, 82)
ST_LAY = (118, 101, 166, 108.5)
ST_GSU = (89, 116, 103.2, 119.8)                         # 14.2 x 3.8 in service (GA-104)
ST_GSU_PIT = (87.5, 114.5, 104.7, 121.3)
GIS = (30, 245, 70, 280)

HEAVY = [["Piece", "t", "L x W x H m", "Route / erection"],
         ["GT core engine", "405", "13.2 x 5.9 x 5.6", "barge TP-M1, SPMT 480 t gross, skid onto foundation via west door"],
         ["GT generator stator", "340", "10.8 x 4.6 x 4.9", "barge, SPMT, jacking / skidding (no crane)"],
         ["GT GSU", "268", "11.2 x 4.1 x 4.6", "barge, SPMT, skid into bay"],
         ["HRSG HP evaporator module", "185", "24.0 x 3.6 x 26.5", "barge, SPMT, 750 t crawler (EPC) from pad"],
         ["ST generator stator", "185", "8.6 x 4.1 x 4.2", "barge, SPMT, jacking / skidding"],
         ["ST GSU", "168", "9.4 x 3.8 x 4.3", "barge, SPMT, skid into bay"],
         ["Exhaust diffuser (2 pieces)", "2 x 62", "8.5 x 7.2 x 7.0", "road, GT hall crane 120 t"],
         ["HRSG HP drum", "96", "14.0 x D 1.9", "road (< 120 t), crawler crane"],
         ["Condenser modules", "4 x 95", "per DS-105", "road, ST hall crane 100 t / jacking"]]


# ------------------------------------------------------------------------------------------------ GA-100 power island
def ga100():
    sh = Sheet(0.75, -40, -110)
    s, h = sh.s, sh.h
    top_tb = sh.frame_and_title("IEC-ALP-GA-100", "POWER ISLAND ARRANGEMENT - INSTALLATION AND MAINTENANCE SPACES", "1:750")
    # context (Owner / EPC)
    sh.rect(0, 0, 400, 300, "PLOT", lw=70)
    sh.T("PLOT BOUNDARY (Owner) E 0-400, N 0-300, grade EL +15.0", 200, 292, 0.9, "PLOT", "CENTER")
    sh.m.add_lwpolyline([(-40 + 10 * s, -60), (400, -60)], dxfattribs={"layer": "SEA", "lineweight": 50})
    sh.T("SHORELINE", 330, -57, 0.8, "SEA")
    sh.zone(100, -75, 140, -40, "PAD", "TP-M1 BARGE LANDING", ["(EPC, 480 t SPMT)"], k=0.7)
    sh.rect(135, 12, 165, 22, "EPC", "DASHED")
    sh.T("CW pump house (EPC)", 150, 24, 0.7, "EPC", "CENTER")
    sh.zone(GIS[0], GIS[1], GIS[2], GIS[3] - 20, "EPC", "380 kV GIS (EPC)", k=0.8)
    sh.rect(*GIS, "EPC", "DASHED")
    sh.zone(20, 280, 62, 300, "EXCL", "OHL CRANE EXCL.", ["30 m (DWG-002)"], k=0.65, pattern="ANSI37")
    sh.rect(20, 262, 62, 300, "EXCL", "DASHED")
    # halls (EPC) and cranes
    for (x0, y0, x1, y1), nm in ((GT_HALL, "GT HALL (EPC) - 120/20 t EOT crane"), (ST_HALL, "ST HALL (EPC) - 100 t EOT crane")):
        sh.rect(x0, y0, x1, y1, "EPC", "DASHED", 50)
        sh.T(nm, (x0 + x1) / 2, y1 + 1.2, 0.75, "EPC", "CENTER")
        sh.rect(x0 + 2, y0 + 2, x1 - 2, y1 - 2, "CRANE", "DASHDOT")
    # IEC equipment
    for r, nm in ((GEN, ""), (GT_ENCL, "GT"), (DIFF, ""), (FILTER, "FILTER HOUSE"), (HRSG, "HRSG IE-HR3"),
                  (ST_GEN, ""), (HP_TURB, ""), (IPLP, "IP/LP"), (COND, "CONDENSER"), (GT_GSU, "GT GSU"), (ST_GSU, "ST GSU")):
        sh.rect(*r, "IEC", lw=50)
        if nm:
            sh.T(nm, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2 - 0.4 * h, 0.7, "IEC", "CENTER")
    sh.T("GEN", (GEN[0] + GEN[2]) / 2, GT_AX + 3.0, 0.6, "IEC", "CENTER")
    sh.T("ST GEN", (ST_GEN[0] + ST_GEN[2]) / 2, ST_AX + 2.8, 0.6, "IEC", "CENTER")
    sh.T("HP", (HP_TURB[0] + HP_TURB[2]) / 2, ST_AX + 3.2, 0.6, "IEC", "CENTER")
    sh.m.add_lwpolyline([(166.5, GT_AX - 3.6), (180, HRSG[1]), (180, HRSG[3]), (166.5, GT_AX + 3.6)], dxfattribs={"layer": "IEC"})
    sh.m.add_lwpolyline([(222, HRSG[1]), (230, GT_AX - 4.6), (230, GT_AX + 4.6), (222, HRSG[3])], dxfattribs={"layer": "IEC"})
    sh.circle(STACK[0], STACK[1], STACK[2], "EPC", "DASHED")
    sh.T("STACK 65 m (EPC)", STACK[0] + 6, STACK[1] - 1, 0.7, "EPC")
    # maintenance, laydown, pads
    sh.rect(*GEN_ROTOR, "MAINT", "DASHED")
    sh.rect(*ST_ROTOR, "MAINT", "DASHED")
    sh.rect(*TUBE_PULL, "MAINT", "DASHED")
    sh.zone(*GT_LAY, "LAYDOWN", "GT LAYDOWN 900 m2", ["10 t/m2"], k=0.7)
    sh.zone(*ST_LAY, "LAYDOWN", "ST LAYDOWN", k=0.6)
    sh.zone(*HRSG_PAD, "PAD", "CRANE PAD 750 t", ["crawler (EPC)"], k=0.7)
    sh.zone(*MOD_LAY, "PAD", "HRSG MODULE", ["LAYDOWN 40 x 50"], k=0.7)
    sh.zone(*CAT_LAY, "LAYDOWN", "SCR CATALYST", k=0.55)
    sh.T("rotor withdrawal 15 m", GEN_ROTOR[0], GT_AX - 5.5, 0.6, "MAINT")
    sh.T("tube pull 11 m", TUBE_PULL[2] + 1, 72, 0.6, "MAINT")
    # heavy-haul route
    route = [(120, -40), (120, 44), (74, 44), (74, 165), (92, 165)]
    sh.arrow(route, k=0.7)
    sh.T("HEAVY HAUL ROUTE (SPMT 480 t): GT, generators, GSUs, modules", 71, 48, 0.8, "ACCESS", "LEFT", 90, keep=False)
    sh.arrow([(74, 175), (74, 221), (113, 221), (113, 213)], label="GT GSU", at=1, k=0.7)
    sh.arrow([(74, 124), (84, 124), (84, 118), (87.5, 118)], k=0.6)
    sh.arrow([(74, 221), (74, 232), (270, 232), (270, 196)], label="HRSG MODULES", at=1, k=0.7)
    sh.arrow([(74, ST_AX), (84.5, ST_AX)], k=0.6)
    sh.T("ST west door", 86.5, ST_AX - 5.8, 0.6, "ACCESS")
    # axes, key terminal points
    for tag, x, y in (("IF-01", 152, 146.5), ("IF-26", 230, GT_AX), ("IF-27", 142, 64), ("IF-34", 122, 209), ("IF-35", 103.2, 118),
                      ("IF-05", 212, 177), ("IF-06", 126, ST_AX - 2.5)):
        sh.circle(x, y, 0.9 * h, "TIEIN")
        sh.T(tag, x + 1.1 * h, y + 0.6 * h, 0.6, "TIEIN")
    sh.T(f"GT axis N {GT_AX:.1f}", 92, GT_AX + 1.5, 0.6, "ANNO")
    sh.T(f"ST axis N {ST_AX:.1f}", 87, ST_AX + 1.5, 0.6, "ANNO")
    # grid ticks
    for e in range(0, 401, 50):
        sh.m.add_line((e, -2), (e, 2), dxfattribs={"layer": "ANNO"})
        sh.T(f"E {e}", e, -6, 0.6, "ANNO", "CENTER")
    for n in range(0, 301, 50):
        sh.m.add_line((-2, n), (2, n), dxfattribs={"layer": "ANNO"})
        sh.T(f"N {n}", -3, n - 0.7, 0.6, "ANNO", "RIGHT")
    sh.north(380, 280)
    sh.scalebar(-20, -92, 20, 5)
    # tables (right-hand column)
    xt = 417
    y = sh.Y1 - 22 * s
    y = sh.table(xt, y, [44, 12, 30, 134], HEAVY, title="1. HEAVY PIECES AND ROUTES (IEC-ALP-REQ-001 section 10)") - 4 * h
    y = sh.table(xt, y, [50, 170], [
        ["Requirement", "IEC requirement to the EPC (EPC to provide)"],
        ["Heavy-haul route", "SPMT 480 t gross from TP-M1 to the GT and ST foundations and the GSU bays: 10 m clear width, "
                             "25 m inside turning radius, ground bearing >= 150 kN/m2 (verify); no overhead lines below 7 m."],
        ["GT hall crane", "EOT 120 t main / 20 t auxiliary hook, hook covers GT, generator and laydown (GA-101)."],
        ["ST hall crane", "EOT 100 t, hook covers ST, generator and laydown (GA-102)."],
        ["Laydown", "GT major inspection 900 m2 at 10 t/m2 in the GT hall; ST laydown 360 m2; HRSG module laydown 40 x 50 m."],
        ["Withdrawal spaces", "GT generator rotor 15 m and ST generator rotor 12 m to the west; condenser tube pull 11 m to the "
                              "east (inside the ST hall) - keep free of permanent equipment, cable trays and pipes."],
        ["HRSG erection", "crane pad 40 x 28 m north of the HRSG for a 750 t crawler (EPC), 250 kN/m2; module lift radius <= 42 m."],
        ["Transformers", "GSU bays with oil pits (110 %), fire walls where < 15 m to buildings or each other (GA-104)."],
        ["Fire exclusion", "OHL crane exclusion 30 m (ALP-OWN-DWG-002) applies to GIS erection near TP-E1."]],
        title="2. INSTALLATION AND MAINTENANCE REQUIREMENTS") - 4 * h
    ly = sh.legend(xt, y, LEGEND)
    notes = ["NOTES", "1. IEC shows its equipment and the spaces it needs; buildings, roads, pads, fire walls, stack, GIS and all",
             "   foundations are EPC scope and are shown indicatively (EPC plot plan governs).",
             "2. Details: GA-101 GT and generator, GA-102 ST, generator and condenser, GA-103 HRSG, GA-104 GSU.",
             "3. Terminal points per IEC-ALP-IF-001 Rev A; positions indicative until the EPC piping layout.",
             "4. Weights: IEC-ALP-DS-101..106 and IEC-ALP-REQ-001 sections 9-11."]
    for i, t in enumerate(notes):
        sh.T(t, xt, ly - 1 * h - i * 1.6 * h, 0.8 if i else 0.95)
    assert ly - 1 * h - len(notes) * 1.6 * h > top_tb, "notes overlap the title block"
    sh.save("IEC-ALP-GA-100_Rev0")


# ------------------------------------------------------------------------------------------------ GA-101 GT and generator
def ga101():
    sh = Sheet(0.3, 80, 52)
    s, h = sh.s, sh.h
    top_tb = sh.frame_and_title("IEC-ALP-GA-101", "GAS TURBINE AND GENERATOR - GA, MAINTENANCE AND INSTALLATION", "1:300")
    x0, y0, x1, y1 = GT_HALL
    sh.T("PLAN (grid E/N m)", 90, 222, 1.2)
    sh.rect(x0, y0, x1, y1, "EPC", "DASHED", 50)
    sh.T("GT HALL (EPC) 80 x 50 m", (x0 + x1) / 2, y1 + 1.2, 0.9, "EPC", "CENTER")
    sh.rect(x0 + 2, y0 + 2, x1 - 2, y1 - 2, "CRANE", "DASHDOT")
    sh.T("120/20 t EOT hook coverage", x0 + 3, y1 - 4.5, 0.75, "CRANE")
    for r in (GEN, GT_ENCL, GT_CORE, DIFF, FILTER, GT_GSU):
        sh.rect(*r, "IEC", lw=50)
    sh.T("GT GENERATOR", (GEN[0] + GEN[2]) / 2, GT_AX + 3.3, 0.7, "IEC", "CENTER")
    sh.T("560 MVA, stator 340 t", (GEN[0] + GEN[2]) / 2, GT_AX - 4.6, 0.65, "IEC", "CENTER")
    sh.T("GT ENCLOSURE 28 x 10 x 9.5", (GT_ENCL[0] + GT_ENCL[2]) / 2, GT_ENCL[1] + 0.8, 0.7, "IEC", "CENTER")
    sh.T("core engine 405 t", (GT_CORE[0] + GT_CORE[2]) / 2, GT_AX - 0.8, 0.6, "IEC", "CENTER")
    sh.T("DIFFUSER", (DIFF[0] + DIFF[2]) / 2, DIFF[1] - 2.3, 0.6, "IEC", "CENTER")
    sh.T("INLET FILTER HOUSE 20 x 18 (elevated)", (FILTER[0] + FILTER[2]) / 2, FILTER[1] + 7.5, 0.65, "IEC", "CENTER")
    sh.T("18 modules <= 28 t", (FILTER[0] + FILTER[2]) / 2, FILTER[1] + 4.5, 0.6, "IEC", "CENTER")
    sh.T("GT GSU (GA-104)", (GT_GSU[0] + GT_GSU[2]) / 2, GT_GSU[1] + 1.2, 0.65, "IEC", "CENTER")
    sh.rect(*GT_GSU_PIT, "EPC", "DASHED")
    sh.m.add_line((GT_GSU_PIT[0], 204), (GT_GSU_PIT[2], 204), dxfattribs={"layer": "EPC", "lineweight": 100})
    sh.T("fire wall (EPC), GSU 5.5 m from the hall", GT_GSU_PIT[2] + 1, 203.4, 0.6, "EPC")
    sh.zone(*GEN_ROTOR, "MAINT", "ROTOR WITHDRAWAL", ["72 t, 15 m clear"], k=0.55)
    sh.zone(*GT_LAY, "LAYDOWN", "GT LAYDOWN 50 x 18 = 900 m2", ["10 t/m2, casings and rotor 112 t on stands"], k=0.75)
    sh.zone(128, 171, 160, 177, "MAINT", "CASING UPPER HALF LIFT ZONE", k=0.55)
    sh.zone(130, 146.5, 150, 150, "MAINT", "", k=0.5)
    sh.T("filter module access (25 t mobile crane)", 140, 124.5, 0.6, "MAINT", "CENTER")
    sh.m.add_lwpolyline([(120, 128), (120, 122), (160, 122), (160, 128)], dxfattribs={"layer": "ACCESS", "linetype": "DASHED"})
    sh.arrow([(84, GT_AX), (97, GT_AX)], label="SPMT", k=0.8)
    sh.T("west door 8 x 9 m", 91, GT_AX - 6.5, 0.6, "ACCESS")
    sh.arrow([(113, 222), (113, 213)], label="GSU skid-in", k=0.6)
    sh.dim((x0, y0), (x1, y0), -4)
    sh.dim((x1, y0), (x1, y1), 4)
    sh.dim((GEN_ROTOR[0], GT_AX), (GEN[0], GT_AX), -9, "15.0")
    sh.dim((GT_ENCL[0], GT_ENCL[1]), (GT_ENCL[2], GT_ENCL[1]), -7)
    sh.dim((GT_LAY[0], GT_LAY[3]), (GT_LAY[2], GT_LAY[3]), 2.5)
    for tag, x, y in (("IF-01 gas", 152, 150.8), ("IF-34", 122, 209)):
        sh.circle(x, y, 0.8 * h, "TIEIN")
        sh.T(tag, x + h, y + 0.5 * h, 0.6, "TIEIN")
    sh.T(f"GT axis N {GT_AX:.1f}", x0 + 0.6, GT_AX - 2.2, 0.55, "ANNO")
    # elevation (looking north): y = yb + (EL - 15)
    yb = 66
    sh.T("ELEVATION ON GT AXIS (looking north), EL m", 90, yb + 30, 1.2)
    sh.m.add_line((88, yb), (172, yb), dxfattribs={"layer": "ANNO", "lineweight": 50})
    sh.T("GRADE EL +15.0", 172.5, yb - 0.4 * h, 0.6)
    ey = lambda el: yb + el - GRADE                      # noqa: E731
    sh.rect(90, ey(15), 170, ey(38), "EPC", "DASHED")
    sh.m.add_line((90, ey(34)), (170, ey(34)), dxfattribs={"layer": "CRANE", "linetype": "DASHDOT"})
    sh.T("crane rail EL +34.0", 91, ey(34.4), 0.6, "CRANE")
    sh.m.add_line((90, ey(32)), (170, ey(32)), dxfattribs={"layer": "CRANE", "linetype": "DASHDOT"})
    sh.T("hook max EL +32.0 (17 m above grade)", 91, ey(30.6), 0.6, "CRANE")
    sh.rect(GEN[0], ey(15), GEN[2], ey(15 + 4.9 + 1.5), "IEC", lw=50)
    sh.rect(GT_ENCL[0], ey(15), GT_ENCL[2], ey(24.5), "IEC", lw=50)
    sh.rect(GT_CORE[0], ey(16.2), GT_CORE[2], ey(21.8), "IEC")
    sh.rect(DIFF[0], ey(15.5), DIFF[2], ey(22.5), "IEC")
    sh.m.add_line((95, ey(19)), (170, ey(19)), dxfattribs={"layer": "ANNO", "linetype": "CENTER"})
    sh.T("GT centreline EL +19.0", 159, ey(19.4), 0.55)
    sh.zone(GT_CORE[0], ey(24.8), GT_CORE[2] - 1, ey(29.5), "MAINT", "ROTOR LIFT ENVELOPE", ["112 t, 11.0 x 3.2 x 3.2"], k=0.5)
    sh.dim((166.5, ey(15)), (166.5, ey(32)), 4, "17.0")
    sh.dim((GT_ENCL[0], ey(15)), (GT_ENCL[0], ey(24.5)), -3, "9.5")
    # tables
    xt = 80 + 505 * s
    y = sh.Y1 - 22 * s
    y = sh.table(xt, y, [60, 22, 40, 108], [
        ["Item", "t", "L x W x H m", "Remark"],
        ["GT core engine (shipping)", "405", "13.2 x 5.9 x 5.6", "DS-101; SPMT via west door, skidded"],
        ["GT rotor (maintenance lift)", "112", "11.0 x 3.2 x 3.2", "120 t hook, lifting beam by IEC"],
        ["Compressor / turbine casing upper halves", "<= 48", "per IEC manual", "laid on stands in the laydown"],
        ["Exhaust diffuser (2 pieces)", "2 x 62", "8.5 x 7.2 x 7.0", "hall crane"],
        ["Generator stator", "340", "10.8 x 4.6 x 4.9", "DS-102; jacking and skidding, no crane lift"],
        ["Generator rotor", "72", "about 12.5 long", "withdrawn west with IEC rotor carriage, 15 m clear"],
        ["Filter house modules", "<= 28", "18 modules", "25 t mobile crane from the south access strip"]],
        title="1. WEIGHTS AND LIFTS") - 4 * h
    y = sh.table(xt, y, [62, 168], [
        ["Requirement", "IEC requirement (EPC to provide)"],
        ["Crane", "EOT 120 t main / 20 t auxiliary; hook max >= EL +32.0 (17 m above grade); hook covers GT, generator, "
                  "diffuser and the laydown."],
        ["Laydown", "900 m2 at 10 t/m2 inside the hall next to the GT (major inspection every 50,000 EOH, 35 days)."],
        ["Access doors", "west door 8 m wide x 9 m high on the GT axis for SPMT (GT core 405 t, stator 340 t); personnel "
                         "doors at both ends of the hall."],
        ["Clearances", "1.2 m walkway around the enclosure; 3.0 m in front of enclosure doors and the lube oil skid; filter "
                       "house access strip 6 m on the south side."],
        ["Foundations", "GT and generator on a common block foundation, 1,050 t static (REQ-001 section 9)."],
        ["Ventilation", "enclosure ventilation air from the hall; hall ventilation for 1.2 MW enclosure heat (EPC)."]],
        title="2. MAINTENANCE AND INSTALLATION REQUIREMENTS") - 4 * h
    ly = sh.legend(xt, y, LEGEND)
    assert ly > top_tb
    sh.north(165, 222)
    sh.scalebar(90, 58, 5, 4)
    sh.save("IEC-ALP-GA-101_Rev0")


# ------------------------------------------------------------------------------------------------ GA-102 ST, generator, condenser
def ga102():
    sh = Sheet(0.3, 75, -20)
    s, h = sh.s, sh.h
    top_tb = sh.frame_and_title("IEC-ALP-GA-102", "STEAM TURBINE, GENERATOR AND CONDENSER - GA, MAINTENANCE", "1:300")
    x0, y0, x1, y1 = ST_HALL
    sh.T("PLAN (grid E/N m)", 85, 133, 1.2)
    sh.rect(x0, y0, x1, y1, "EPC", "DASHED", 50)
    sh.T("ST HALL (EPC) 85 x 50 m", (x0 + x1) / 2, y1 + 1.2, 0.9, "EPC", "CENTER")
    sh.rect(x0 + 2, y0 + 2, x1 - 2, y1 - 2, "CRANE", "DASHDOT")
    sh.T("100 t EOT hook coverage", x0 + 3, y0 + 3, 0.75, "CRANE")
    for r in (ST_GEN, HP_TURB, IPLP, COND, ST_GSU):
        sh.rect(*r, "IEC", lw=50)
    sh.T("ST GENERATOR 270 MVA", (ST_GEN[0] + ST_GEN[2]) / 2, ST_AX + 3.0, 0.65, "IEC", "CENTER")
    sh.T("HP 92 t", (HP_TURB[0] + HP_TURB[2]) / 2, ST_AX + 3.2, 0.65, "IEC", "CENTER")
    sh.T("IP/LP (rotor 86 t)", (IPLP[0] + IPLP[2]) / 2, ST_AX + 5.2, 0.65, "IEC", "CENTER")
    sh.T("CONDENSER (side exhaust)", (COND[0] + COND[2]) / 2, 75.5, 0.65, "IEC", "CENTER")
    sh.T("4 modules x 95 t, Ti tubes 9.35 m", (COND[0] + COND[2]) / 2, 72.5, 0.6, "IEC", "CENTER")
    sh.T("inlet/outlet water boxes (west)", COND[0] - 0.5, 65.5, 0.55, "IEC", "RIGHT")
    sh.T("ST GSU (GA-104)", (ST_GSU[0] + ST_GSU[2]) / 2, ST_GSU[3] + 1, 0.6, "IEC", "CENTER")
    sh.rect(*ST_GSU_PIT, "EPC", "DASHED")
    sh.m.add_line((ST_GSU[0], 111), (ST_GSU[2], 111), dxfattribs={"layer": "EPC", "lineweight": 100})
    sh.zone(*ST_ROTOR, "MAINT", "ROTOR WITHDRAWAL", ["46 t, 12 m"], k=0.5)
    sh.zone(*TUBE_PULL, "MAINT", "TUBE PULL", ["11 m clear", "(return box end)"], k=0.6)
    sh.zone(*ST_LAY, "LAYDOWN", "ST LAYDOWN 48 x 7.5 = 360 m2 - rotor stands 86 t / 46 t", k=0.6)
    sh.arrow([(80, ST_AX), (92.5, ST_AX)], label="SPMT", k=0.6)
    sh.T("west door 7 x 8 m", 86, ST_AX - 6, 0.6, "ACCESS")
    sh.m.add_lwpolyline([(136, 64), (136, 40), (148, 40), (148, 64)], dxfattribs={"layer": "EPC", "linetype": "DASHED"})
    sh.T("CW pipes to the pump house (EPC)", 150, 45, 0.6, "EPC")
    for tag, x, y in (("IF-06", 124, ST_AX - 2.5), ("IF-10", 134, ST_AX - 4.5), ("IF-27", 132, 68), ("IF-15", 140, 64),
                      ("IF-35", 103.2, 118)):
        sh.circle(x, y, 0.8 * h, "TIEIN")
        sh.T(tag, x + h, y + 0.5 * h, 0.6, "TIEIN")
    sh.dim((x0, y0), (x1, y0), -4)
    sh.dim((x1, y0), (x1, y1), 4)
    sh.dim((ST_ROTOR[0], ST_AX), (ST_GEN[0], ST_AX), -6.5, "12.0")
    sh.dim((TUBE_PULL[0], TUBE_PULL[1]), (TUBE_PULL[2], TUBE_PULL[1]), -3, "11.0")
    sh.T(f"ST axis N {ST_AX:.1f}", x0 + 0.6, ST_AX - 2.2, 0.55)
    # elevation
    yb = -20 + 38 * s + 10 * s
    sh.T("SECTION ON ST AXIS (looking north), EL m", 85, yb + 32.5, 1.2)
    ey = lambda el: yb + el - GRADE                      # noqa: E731
    sh.m.add_line((83, yb), (172, yb), dxfattribs={"layer": "ANNO", "lineweight": 50})
    sh.T("GRADE EL +15.0", 172.5, yb - 0.4 * h, 0.6)
    sh.rect(85, ey(15), 170, ey(45), "EPC", "DASHED")
    sh.rect(100, ey(15), 155, ey(24), "EPC", "DASHED")
    sh.T("spring-mounted table-top, operating deck EL +24.0 (EPC)", 101, ey(20), 0.6, "EPC")
    for lev, txt in ((41, "crane rail EL +41.0"), (39, "hook max EL +39.0 (15 m above deck)")):
        sh.m.add_line((85, ey(lev)), (170, ey(lev)), dxfattribs={"layer": "CRANE", "linetype": "DASHDOT"})
        sh.T(txt, 86, ey(lev + 0.4), 0.6, "CRANE")
    sh.rect(ST_GEN[0], ey(24), ST_GEN[2], ey(24 + 4.2 + 1), "IEC", lw=50)
    sh.rect(HP_TURB[0], ey(24), HP_TURB[2], ey(30), "IEC", lw=50)
    sh.rect(IPLP[0], ey(24), IPLP[2], ey(31), "IEC", lw=50)
    sh.rect(COND[0], ey(15), COND[2], ey(28), "HIDDEN", "DASHED")
    sh.T("condenser behind (south), top EL +28.0", COND[0] + 0.5, ey(16), 0.55, "HIDDEN")
    sh.zone(IPLP[0], ey(31.5), IPLP[2], ey(36.5), "MAINT", "ROTOR / CASING LIFT", ["86 t over the lower half"], k=0.5)
    sh.dim((168, ey(24)), (168, ey(39)), -2, "15.0")
    # tables
    xt = 75 + 505 * s
    y = sh.Y1 - 22 * s
    y = sh.table(xt, y, [62, 22, 38, 108], [
        ["Item", "t", "L x W x H m", "Remark"],
        ["HP turbine (shipped assembled)", "92", "per DS-103", "hall crane"],
        ["IP/LP outer casing lower half", "2 x 78", "-", "hall crane, 2 pieces"],
        ["IP/LP rotor", "86", "about 9 long", "heaviest maintenance lift; 100 t hook"],
        ["ST generator stator", "185", "8.6 x 4.1 x 4.2", "DS-102; jacking / skidding onto the deck"],
        ["ST generator rotor", "46", "about 10 long", "withdrawn west, 12 m clear"],
        ["Condenser modules", "4 x 95", "per DS-105", "set on the condenser foundation before the ST"]],
        title="1. WEIGHTS AND LIFTS") - 4 * h
    y = sh.table(xt, y, [62, 168], [
        ["Requirement", "IEC requirement (EPC to provide)"],
        ["Crane", "EOT 100 t; hook max >= EL +39.0 (15 m above the operating deck); coverage over ST, generator, laydown "
                  "and the condenser tube pull area."],
        ["Tube pull", "11 m clear at the condenser return water box end (east) inside the hall; removable wall panel if the "
                      "hall is shortened. Water box removal 2 x 12 t."],
        ["Laydown", "360 m2 on the operating deck level for rotor stands (86 t, 46 t) and casing halves, 5 t/m2."],
        ["Access", "west door 7 x 8 m for SPMT; hatch in the deck over the condenser neck expansion joint."],
        ["Foundations", "ST + generator spring-mounted table-top 980 t (REQ-001 section 9); spring elements by EPC."],
        ["CW", "4 x DN1800 at the west water boxes (IF-27); ball injection nozzles (IF-44)."]],
        title="2. MAINTENANCE AND INSTALLATION REQUIREMENTS") - 4 * h
    ly = sh.legend(xt, y, LEGEND)
    assert ly > top_tb
    sh.north(165, 132)
    sh.scalebar(85, -14, 5, 4)
    sh.save("IEC-ALP-GA-102_Rev0")


# ------------------------------------------------------------------------------------------------ GA-103 HRSG
SECTIONS = [("HP SH/RH", 6.0), ("HP EVAP", 3.6), ("SCR", 4.2), ("IP SH", 3.0), ("HP ECO2", 3.6), ("IP EVAP", 3.6),
            ("LP SH", 3.0), ("HP ECO1/IP ECO", 5.0), ("LP EVAP", 4.0), ("CPH", 6.0)]


def ga103():
    sh = Sheet(0.4, 155, 0)
    s, h = sh.s, sh.h
    top_tb = sh.frame_and_title("IEC-ALP-GA-103", "HRSG IE-HR3 - GA, ERECTION AND MAINTENANCE", "1:400")
    sh.T("PLAN (grid E/N m)", 165, 222, 1.2)
    sh.m.add_lwpolyline([(166.5, GT_AX - 3.6), (180, HRSG[1]), (180, HRSG[3]), (166.5, GT_AX + 3.6)], dxfattribs={"layer": "IEC"})
    sh.m.add_lwpolyline([(222, HRSG[1]), (230, GT_AX - 4.6), (230, GT_AX + 4.6), (222, HRSG[3])], dxfattribs={"layer": "IEC"})
    sh.rect(*HRSG, "IEC", lw=50)
    x = HRSG[0]
    scale_len = (HRSG[2] - HRSG[0]) / sum(w for _, w in SECTIONS)
    for nm, w in SECTIONS:
        xe = x + w * scale_len
        sh.m.add_line((xe, HRSG[1]), (xe, HRSG[3]), dxfattribs={"layer": "IEC"})
        sh.T(nm, (x + xe) / 2, HRSG[1] + 2, 0.5, "IEC", "LEFT", 90, keep=False)
        x = xe
    sh.circle(STACK[0], STACK[1], STACK[2], "EPC", "DASHED")
    sh.T("STACK D 9.2 m (EPC)", STACK[0], STACK[1] + 6, 0.65, "EPC", "CENTER")
    sh.T("HRSG CASING 42 x 24 m", 190, HRSG[3] + 1.2, 0.8, "IEC", "CENTER")
    sh.zone(*HRSG_PAD, "PAD", "CRANE PAD 40 x 28 m", ["750 t crawler (EPC)", "250 kN/m2"], k=0.75)
    sh.m.add_arc((202, 199), 42, 205, 335, dxfattribs={"layer": "CRANE", "linetype": "DASHDOT"})
    sh.m.add_line((202, 199), (202 + 42 * 0.906, 199 - 42 * 0.423), dxfattribs={"layer": "CRANE"})
    sh.T("lift radius 42 m (750 t crawler)", 232, 181, 0.7, "CRANE", "LEFT")
    sh.zone(*MOD_LAY, "PAD", "MODULE LAYDOWN 40 x 50 m", ["pre-assembly, 185 t modules"], k=0.75)
    sh.zone(*CAT_LAY, "LAYDOWN", "SCR CATALYST", ["LAYDOWN 20 x 10"], k=0.6)
    scr_x = HRSG[0] + (6.0 + 3.6 + 2.1) * scale_len
    sh.m.add_line((scr_x, HRSG[1]), (scr_x, CAT_LAY[3]), dxfattribs={"layer": "MAINT", "linetype": "DASHED", "lineweight": 50})
    sh.T("catalyst door + monorail", scr_x + 1, 150.5, 0.55, "MAINT")
    sh.zone(166.5, 177.5, 180, 184, "MAINT", "INLET DUCT", ["manway access"], k=0.5)
    sh.arrow([(265, 226), (265, 196)], label="SPMT modules", k=0.6)
    for tag, xx, yy in (("IF-05", 205, 177), ("IF-09", 211, 177), ("IF-11", 217, 177), ("IF-18", 219, 153), ("IF-26", 230, GT_AX),
                        ("IF-25", 190, 153)):
        sh.circle(xx, yy, 0.8 * h, "TIEIN")
        sh.T(tag, xx + h, yy + (0.5 if yy > GT_AX else -1.6) * h, 0.55, "TIEIN")
    sh.dim((HRSG[0], HRSG[1]), (HRSG[2], HRSG[1]), -8)
    sh.dim((HRSG[2], HRSG[1]), (HRSG[2], HRSG[3]), 3)
    # elevation (looking north)
    yb = 14
    sh.T("ELEVATION (looking north), EL m", 165, yb + 70, 1.2)
    ey = lambda el: yb + el - GRADE                      # noqa: E731
    sh.m.add_line((163, yb), (300, yb), dxfattribs={"layer": "ANNO", "lineweight": 50})
    sh.T("GRADE EL +15.0", 300.5, yb - 0.4 * h, 0.6)
    sh.rect(HRSG[0], ey(15.5), HRSG[2], ey(45), "IEC", lw=50)
    sh.m.add_lwpolyline([(166.5, ey(15.5)), (180, ey(15.5)), (180, ey(45)), (166.5, ey(22.5))], dxfattribs={"layer": "IEC"})
    for i, (nm, (dx, el, ln)) in enumerate(zip(("HP DRUM 96 t", "IP DRUM", "LP DRUM"), ((188, 47.0, 14.0), (201, 46.5, 10),
                                                                                     (211, 46.5, 9)))):
        sh.rect(dx - 1.0, ey(el - 1.0), dx + 1.0, ey(el + 1.0), "IEC")
        sh.T(nm, dx, ey(el + 1.6), 0.55, "IEC", "CENTER")
    sh.rect(STACK[0] - 4.6, ey(15), STACK[0] + 4.6, ey(80), "EPC", "DASHED")
    sh.T("STACK EL +80.0 (65 m, EPC)", STACK[0] + 5.5, ey(78), 0.6, "EPC")
    sh.T("CEMS platform (EPC)", STACK[0] + 5.5, ey(45), 0.6, "EPC")
    sh.m.add_lwpolyline([(222, ey(15.5)), (230, ey(22)), (230, ey(38)), (222, ey(45))], dxfattribs={"layer": "IEC"})
    sh.zone(HRSG[0] + 6.0 * scale_len, ey(15.5), HRSG[0] + 9.6 * scale_len, ey(42), "MAINT", "", k=0.5)
    sh.T("HP EVAP module 185 t, 24.0 x 3.6 x 26.5 m", HRSG[0] + 11, ey(30), 0.6, "MAINT")
    sh.dim((HRSG[0], ey(15)), (HRSG[0], ey(45)), -3, "30.0")
    sh.dim((250, ey(15)), (250, ey(80)), 3, "65.0")
    sh.T("access: stairs to all drum and platform levels (IEC); elevator (EPC option)", 165, yb - 3.5, 0.6)
    # tables
    xt = 155 + 505 * s
    y = sh.Y1 - 22 * s
    y = sh.table(xt, y, [70, 30, 130], [
        ["Item", "t", "Remark"],
        ["Heaviest module (HP evaporator)", "185", "24.0 x 3.6 x 26.5 m shipped horizontal; upended on the pad"],
        ["HP drum", "96", "14.0 m, OD 1.9 m; lifted onto the drum supports"],
        ["Total HRSG (pressure parts, casing, steel, catalyst)", "6,400", "DS-104; operating 7,800 t on the base plates"],
        ["SCR catalyst modules", "<= 1.5", "replacement every 4-5 years through the side door with monorail"]],
        title="1. WEIGHTS AND LIFTS") - 4 * h
    y = sh.table(xt, y, [62, 168], [
        ["Requirement", "IEC requirement (EPC to provide)"],
        ["Erection crane", "750 t crawler with superlift on the crane pad north of the HRSG; module lift radius <= 42 m; "
                           "pad 40 x 28 m, 250 kN/m2 (EPC to verify with the geotechnical data)."],
        ["Module laydown", "40 x 50 m east of the stack for upending and pre-assembly; SPMT access from the north road."],
        ["Catalyst", "20 x 10 m laydown at the south side below the catalyst door; 5 t monorail at the catalyst section."],
        ["Inspection access", "inlet duct manway, access doors per section, 2.5 m clear at all doors and headers."],
        ["Stack interface", "IF-26 outlet flange; fabric expansion joint by EPC; stack 65 m (TQ-029 pending on SC-011)."]],
        title="2. ERECTION AND MAINTENANCE REQUIREMENTS") - 4 * h
    ly = sh.legend(xt, y, LEGEND)
    assert ly > top_tb
    sh.north(290, 222)
    sh.scalebar(165, 7, 10, 4)
    sh.save("IEC-ALP-GA-103_Rev0")


# ------------------------------------------------------------------------------------------------ GA-104 GSU transformers
def gsu(sh, x, y, L, W, H, tank_h, label, weight, pit):
    """Plan at (x, y) lower-left of the tank; returns nothing."""
    sh.rect(x, y, x + L, y + W, "IEC", lw=50)
    sh.rect(x + L, y + 0.5, x + L + 2.6, y + W - 0.5, "IEC")                   # radiator bank (ONAF)
    sh.rect(x - 2.2, y + W / 2 - 1.0, x, y + W / 2 + 1.0, "IEC")               # conservator end
    sh.T(label, x + L / 2, y + W / 2 + 0.3, 0.8, "IEC", "CENTER")
    sh.T(weight, x + L / 2, y + W / 2 - 1.2, 0.65, "IEC", "CENTER")
    sh.rect(x - pit, y - pit, x + L + 2.6 + pit, y + W + pit, "EPC", "DASHED")


def ga104():
    sh = Sheet(0.1, 0, 0)
    s, h = sh.s, sh.h
    top_tb = sh.frame_and_title("IEC-ALP-GA-104", "GENERATOR STEP-UP TRANSFORMERS - GA, INSTALLATION AND MAINTENANCE", "1:100")
    sh.T("GT GSU 560 MVA - PLAN", 5, 54, 1.2)
    gx, gy = 8, 38
    gsu(sh, gx, gy, 11.2, 4.1, 4.6, 4.6, "GT GSU 400/21 kV", "268 t transport / 395 t total", 1.5)
    sh.m.add_line((gx - 3.7, gy + 4.1 + 3), (gx + 13.8 + 1.5, gy + 4.1 + 3), dxfattribs={"layer": "EPC", "lineweight": 100})
    sh.T("fire wall (EPC) where < 15 m to the hall or the other GSU", gx - 3.7, gy + 4.1 + 3.5, 0.6, "EPC")
    sh.zone(gx - 3.7, gy - 1.5 - 6.0, gx + 15.3, gy - 1.5, "ACCESS", "SPMT / SKIDDING ACCESS 6 m (transport 11.2 x 4.1 x 4.6)",
            ["also 50 t mobile crane position for bushing replacement"], k=0.6, pattern="ANSI37")
    sh.T("oil pit 110 % of 98 m3 (EPC)", gx - 3.5, gy - 1.2, 0.55, "EPC")
    sh.dim((gx, gy), (gx + 11.2, gy), -9.5, "11.2")
    sh.dim((gx - 2.2, gy), (gx - 2.2, gy + 4.1), -2.8, "4.1")
    for jx in (gx + 0.6, gx + 10.6):
        for jy in (gy + 0.4, gy + 3.7):
            sh.circle(jx, jy, 0.25, "MAINT")
    sh.T("jacking pads (4)", gx + 11.4, gy + 0.2, 0.55, "MAINT")
    # elevation GT GSU
    ey0 = 8
    sh.T("GT GSU - SIDE ELEVATION", 5, ey0 + 19.5, 1.2)
    sh.m.add_line((3, ey0), (30, ey0), dxfattribs={"layer": "ANNO", "lineweight": 50})
    sh.rect(gx, ey0 + 0.5, gx + 11.2, ey0 + 0.5 + 4.6, "IEC", lw=50)
    sh.rect(gx + 11.2, ey0 + 1.0, gx + 13.8, ey0 + 4.6, "IEC")
    sh.rect(gx - 2.2, ey0 + 5.6, gx, ey0 + 7.0, "IEC")
    for bx in (gx + 2.0, gx + 4.0, gx + 6.0):
        sh.m.add_line((bx, ey0 + 5.1), (bx + 0.8, ey0 + 11.3), dxfattribs={"layer": "IEC", "lineweight": 50})
    sh.T("HV bushings (air), top EL +26.3", gx + 6.5, ey0 + 11.0, 0.6, "IEC")
    sh.zone(gx + 1.0, ey0 + 11.8, gx + 8.0, ey0 + 16.5, "MAINT", "BUSHING REMOVAL", ["hook >= EL +32.0"], k=0.55)
    sh.dim((gx - 3.0, ey0), (gx - 3.0, ey0 + 11.3), -1.0, "11.3")
    sh.T("foundation EL +15.5 with skid rails; EL m = grade +15.0", 3, ey0 - 2.2, 0.6)
    # ST GSU plan
    sx, sy = 44, 38
    sh.T("ST GSU 270 MVA - PLAN", 40, 54, 1.2)
    gsu(sh, sx, sy, 9.4, 3.8, 4.3, 4.3, "ST GSU 400/15.75 kV", "168 t transport / 245 t total", 1.5)
    sh.zone(sx - 3.7, sy - 1.5 - 6.0, sx + 13.5, sy - 1.5, "ACCESS", "SPMT / SKIDDING ACCESS 6 m", k=0.6, pattern="ANSI37")
    sh.dim((sx, sy), (sx + 9.4, sy), -9.5, "9.4")
    sh.T("oil pit 110 % of 62 m3 (EPC)", sx - 3.5, sy - 1.2, 0.55, "EPC")
    # tables
    xt = 60 * 1.0 + 3
    y = sh.Y1 - 22 * s
    y = sh.table(xt, y, [42, 38, 38, 73], [
        ["Item", "GT GSU", "ST GSU", "Remark"],
        ["Rating / ratio", "560 MVA, 400/21 kV", "270 MVA, 400/15.75 kV", "OLTC +/- 8 x 1.25 %, YNd11 (DS-106)"],
        ["Transport weight / dims", "268 t, 11.2 x 4.1 x 4.6", "168 t, 9.4 x 3.8 x 4.3", "nitrogen-filled, without oil"],
        ["Total weight / oil", "395 t / 98 m3", "245 t / 62 m3", "natural ester (K-class)"],
        ["In-service footprint", "16.0 x 4.1 m", "14.2 x 3.8 m", "tank + radiators (LV end) + conservator (HV end)"],
        ["Bushing top", "EL +26.3", "EL +25.8", "HV air bushings; arresters by EPC"]], title="1. DATA") - 4 * h
    y = sh.table(xt, y, [42, 149], [
        ["Requirement", "IEC requirement (EPC to provide)"],
        ["Installation", "SPMT to the bay, jacking on 4 pads and skidding onto the foundation rails; 6 m clear access strip "
                         "on the long side; ground 150 kN/m2."],
        ["Oil containment", "pit 110 % of the oil volume with flame trap gravel and oil-water separator (EPC)."],
        ["Fire", "fire walls (2 h) where < 15 m to buildings or the other GSU (IEC 61936-1); deluge (NFPA 850) by EPC."],
        ["Maintenance", "50 t mobile crane access for bushing replacement (hook >= EL +32.0); 1.5 m walkway around the tank; "
                        "OLTC and fan access from the ground."],
        ["Clearances", "phase-to-earth and working clearances per IEC 61936-1 for 420 kV (Um); HV connection to the GIS by "
                       "EPC (IF-34 / IF-35)."]], title="2. INSTALLATION AND MAINTENANCE REQUIREMENTS") - 4 * h
    ly = sh.legend(xt, y, LEGEND)
    assert ly > top_tb
    sh.north(36, 50)
    sh.scalebar(40, 6, 2, 5)
    sh.save("IEC-ALP-GA-104_Rev0")


DRAWINGS = {"GA100": ga100, "GA101": ga101, "GA102": ga102, "GA103": ga103, "GA104": ga104}
if __name__ == "__main__":
    for k in (sys.argv[2:] or DRAWINGS):
        DRAWINGS[k]()
