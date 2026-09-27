"""P&ID sheets (DXF R2018 + PDF, A3): one sheet per P&ID document, laid out automatically from the database.

Content per sheet (document D): equipment with pid=D, lines with pid=D, instruments with pid=D.
  equipment   symbol blocks by type (pump, compressor, drum, vessel, heat exchanger / coil, generic)
              placed in flow order (pumps/compressors on the lower row), TAG attribute on every block
  lines       orthogonal routes nozzle -> nozzle, line number label, flow arrow, off-page connectors when
              the other end is on another sheet / a branch of another line
  valves      inline VALVE components in seq order (gate, globe, ball, butterfly, check, control, relief)
  instruments ISA 5.1 bubbles (field: plain; DCS/PLC/SIS: with horizontal bar) on their line / equipment
The layout is a generated schematic: topology, tags and data are exact; positions are automatic, not drafted.
Options: sheets=DOC1,DOC2
"""
from __future__ import annotations

import math

from ..core import dxfkit, piping
from ..core.runner import Context, Engine

W, H = 420.0, 297.0
UPPER, LOWER = 205.0, 115.0


def symbol_of(eq) -> str:
    t = f"{eq.get('equipment_type', '')} {eq.get('aveva_class', '')} {eq.get('description', '')}".lower()
    for key, sym in (("pump", "PUMP"), ("compressor", "COMPRESSOR"), ("economi", "COIL"), ("superheat", "COIL"),
                     ("evaporat", "COIL"), ("exchanger", "HX"), ("cooler", "HX"), ("condenser", "HX"),
                     ("heater", "HX"), ("deaerat", "DRUM_H"), ("drum", "DRUM_H"), ("tank", "DRUM_H"),
                     ("vessel", "VESSEL_V"), ("separator", "VESSEL_V"), ("column", "VESSEL_V")):
        if key in t:
            return sym
    return "BOX"


# symbol ports relative to the insertion point: (x, y, direction of flow at the port)
PORTS = {"PUMP": {"in": (-6, 0, (1, 0)), "out": (7, 6, (1, 0))},
         "COMPRESSOR": {"in": (-8, 0, (1, 0)), "out": (8, 0, (1, 0))},
         "DRUM_H": {"in": (-26, 0, (1, 0)), "out": (0, -8, (0, -1))},
         "VESSEL_V": {"in": (-8, 10, (1, 0)), "out": (0, -20, (0, -1))},
         "HX": {"in": (-9, 0, (1, 0)), "out": (9, 0, (1, 0))},
         "COIL": {"in": (-8, 12, (1, 0)), "out": (8, -12, (1, 0))},
         "BOX": {"in": (-12, 0, (1, 0)), "out": (12, 0, (1, 0))}}
STUB = 6.0
ITEM_STEP, INST_STEP, CHAR_W = 18.0, 22.0, 1.25       # mm along a line; approx. text width per character (2.0 h)


def label_of(l) -> str:
    return f"{l['id']}-{l['dn'][2:]}-{l['spec']}" + (f"-{l['insulation'][0].upper()}" if l.get("insulation", "none") != "none" else "")


def needed_length(label, n_items, n_inst) -> float:
    return len(label) * CHAR_W + 8 + n_items * ITEM_STEP + n_inst * INST_STEP + 10


def define_blocks(doc):
    def blk(name):
        b = doc.blocks.new(name)
        return b

    def tagdef(b, y):
        b.add_attdef("TAG", (0, y), dxfattribs={"height": 2.5, "layer": "EQPT-TAG", "style": "ALPILLA"}).set_placement(
            (0, y), align=__import__("ezdxf").enums.TextEntityAlignment.CENTER)

    b = blk("PUMP")
    b.add_circle((0, 0), 6)
    b.add_line((0, 6), (7, 6))
    b.add_lwpolyline([(-4, -4.5), (-6, -8.5), (6, -8.5), (4, -4.5)])
    tagdef(b, -13)
    b = blk("COMPRESSOR")
    b.add_lwpolyline([(-8, -6), (8, -3), (8, 3), (-8, 6)], close=True)
    tagdef(b, -11)
    b = blk("DRUM_H")
    b.add_line((-18, 8), (18, 8))
    b.add_line((-18, -8), (18, -8))
    b.add_arc((-18, 0), 8, 90, 270)
    b.add_arc((18, 0), 8, 270, 90)
    tagdef(b, 19)
    b = blk("VESSEL_V")
    b.add_line((-8, 12), (-8, -12))
    b.add_line((8, 12), (8, -12))
    b.add_arc((0, 12), 8, 0, 180)
    b.add_arc((0, -12), 8, 180, 360)
    tagdef(b, -25)
    b = blk("HX")
    b.add_circle((0, 0), 9)
    b.add_lwpolyline([(-9, 0), (-5, 4), (-1, -4), (3, 4), (7, -4), (9, 0)])
    tagdef(b, -14)
    b = blk("COIL")
    b.add_lwpolyline([(-8, -20), (8, -20), (8, 20), (-8, 20)], close=True)
    b.add_lwpolyline([(-8, 12), (4, 12), (4, 6), (-4, 6), (-4, 0), (4, 0), (4, -6), (-4, -6), (-4, -12), (8, -12)])
    tagdef(b, -25)
    b = blk("BOX")
    b.add_lwpolyline([(-12, -8), (12, -8), (12, 8), (-12, 8)], close=True)
    tagdef(b, -12)
    # valves along +X, 8 long
    bow = [(-4, 2), (4, -2), (4, 2), (-4, -2)]
    for name, extra in (("V_GATE", []), ("V_GLOBE", ["dot"]), ("V_BALL", ["circle"]), ("V_BUTTERFLY", ["bar"]),
                        ("V_PLUG", ["bar"]), ("V_NEEDLE", ["dot"]), ("V_CHECK", ["fill"]), ("V_CONTROL", ["act"])):
        b = blk(name)
        b.add_lwpolyline(bow, close=True)
        if "dot" in extra:
            b.add_circle((0, 0), 0.8)
        if "circle" in extra:
            b.add_circle((0, 0), 1.3)
        if "bar" in extra:
            b.add_line((0, -2.5), (0, 2.5))
        if "fill" in extra:
            b.add_solid([(0, 0), (4, -2), (4, 2)])
        if "act" in extra:
            b.add_line((0, 0), (0, 5))
            b.add_arc((0, 5), 3, 0, 180)
            b.add_line((-3, 5), (3, 5))
    b = blk("V_RELIEF")
    b.add_lwpolyline([(-4, 2), (0, 0), (-4, -2)], close=True)
    b.add_lwpolyline([(-2, 4), (0, 0), (2, 4)], close=True)
    b.add_lwpolyline([(0, 4), (1.5, 5), (-1.5, 6), (1.5, 7), (0, 8)])
    b = blk("REDUCER")
    b.add_lwpolyline([(-2, -2), (2, -1), (2, 1), (-2, 2)], close=True)
    b = blk("INLINE_INST")
    b.add_lwpolyline([(-3, -2), (3, -2), (3, 2), (-3, 2)], close=True)
    b = blk("INST_FIELD")
    b.add_circle((0, 0), 5)
    b = blk("INST_DCS")
    b.add_circle((0, 0), 5)
    b.add_line((-5, 0), (5, 0))
    b.add_lwpolyline([(-5, -5), (5, -5), (5, 5), (-5, 5)], close=True)   # ISA: shared display/control -> square+circle
    b = blk("OFFPAGE")
    b.add_lwpolyline([(0, -3), (22, -3), (26, 0), (22, 3), (0, 3)], close=True)


VALVE_BLOCK = {"gate": "V_GATE", "globe": "V_GLOBE", "ball": "V_BALL", "butterfly": "V_BUTTERFLY", "plug": "V_PLUG",
               "needle": "V_NEEDLE", "check": "V_CHECK", "control": "V_CONTROL", "relief": "V_RELIEF"}


class PID(Engine):
    name = "pid"
    title = "P&ID sheets (DXF + PDF, A3) generated from equipment, lines, valves and instruments"
    version = "1.0.0"
    inputs = ["project", "document", "document_revision", "equipment", "nozzle", "line", "pipe_component",
              "instrument", "pipe_size"]
    formats = ["dxf", "pdf"]

    def run(self, ctx: Context):
        s = ctx.store
        sheets = sorted({r["pid"] for e in ("equipment", "line", "instrument") for r in s.records(e) if r.get("pid")})
        if ctx.options.get("sheets"):
            sheets = [x for x in sheets if x in set(ctx.options["sheets"].split(","))]
        files = []
        for doc_id in sheets:
            files += self.sheet(ctx, doc_id)
        if not sheets:
            ctx.warnings.append("no records reference a P&ID document (set pid on equipment/lines/instruments)")
        return files

    def sheet(self, ctx, doc_id):
        s = ctx.store
        prj = ctx.project_record()
        pdoc = s.get("document", doc_id)
        doc = dxfkit.new_doc()
        define_blocks(doc)
        msp = doc.modelspace()
        eqs = [e for e in s.records("equipment") if e.get("pid") == doc_id and e.get("status") != "deleted"]
        lines = [l for l in s.records("line") if l.get("pid") == doc_id and l.get("status") != "deleted"]
        insts = [i for i in s.records("instrument") if i.get("pid") == doc_id]
        noz_eq = {n["id"]: n["equipment"] for n in s.records("nozzle")}
        on_sheet = {e["id"] for e in eqs}

        # ---- flow order (topological over lines between equipment on this sheet)
        edges = {(noz_eq.get(l.get("from_nozzle")), noz_eq.get(l.get("to_nozzle"))) for l in lines}
        edges = {(a, b) for a, b in edges if a in on_sheet and b in on_sheet and a != b}
        order, placed = [], set()
        indeg = {e: sum(1 for a, b in edges if b == e) for e in on_sheet}
        ready = sorted(e for e, d in indeg.items() if d == 0)
        while len(order) < len(on_sheet):
            if not ready:  # cycle: take the smallest remaining id
                ready = [sorted(on_sheet - placed)[0]]
            e = ready.pop(0)
            if e in placed:
                continue
            order.append(e)
            placed.add(e)
            for a, b in sorted(edges):
                if a == e:
                    indeg[b] -= 1
                    if indeg[b] <= 0 and b not in placed:
                        ready.append(b)
        # reserve margins for off-page connectors so equipment never sits on top of them
        has_in = any(noz_eq.get(l.get("from_nozzle")) not in on_sheet for l in lines)
        has_out = any(noz_eq.get(l.get("to_nozzle")) not in on_sheet for l in lines)
        inline_types = ("VALVE", "REDUCER-CONCENTRIC", "REDUCER-ECCENTRIC", "INSTRUMENT")
        need = {l["id"]: needed_length(label_of(l), sum(1 for c in piping.components(s, l["id"]) if c["type"] in inline_types),
                                       sum(1 for i in insts if i.get("line") == l["id"])) for l in lines}
        out_need = max((need[l["id"]] for l in lines if noz_eq.get(l.get("to_nozzle")) not in on_sheet), default=0)
        x_lo, x_hi = 60 + (35 if has_in else 0), 360 - (min(200, max(70, out_need + 40)) if has_out else 0)
        n = max(1, len(order))
        xs = [x_lo + i * ((x_hi - x_lo) / (n - 1)) for i in range(n)] if n > 1 else [(x_lo + x_hi) / 2]
        pos, sym = {}, {}
        for x, eid in zip(xs, order):
            eq = s.get("equipment", eid)
            sym[eid] = symbol_of(eq)
            y = LOWER if sym[eid] in ("PUMP", "COMPRESSOR") else UPPER
            pos[eid] = (x, y)
            ref = msp.add_blockref(sym[eid], (x, y), dxfattribs={"layer": "EQPT"})
            ref.add_auto_attribs({"TAG": eid})
            ty = y + (15 if sym[eid] == "DRUM_H" else -18 if sym[eid] == "PUMP" else -30 if sym[eid] in ("VESSEL_V", "COIL") else -19)
            dxfkit.text(msp, eq["description"][:34], x, ty, 1.8, "EQPT-TAG", "CENTER")

        # ---- lines
        def port(eid, kind):
            px, py, d = PORTS[sym[eid]][kind]
            return (pos[eid][0] + px, pos[eid][1] + py), d

        lane = 0
        drawn, inst_start, alt_seg = {}, {}, {}
        for l in sorted(lines, key=lambda l: l["id"]):
            src = noz_eq.get(l.get("from_nozzle"))
            dst = noz_eq.get(l.get("to_nozzle"))
            p0, d0 = port(src, "out") if src in on_sheet else (None, (1, 0))
            p1, d1 = port(dst, "in") if dst in on_sheet else (None, (1, 0))
            if p0 is None and p1 is None:
                ctx.warnings.append(f"{doc_id}: line {l['id']} has no end on this sheet - not drawn")
                continue
            if p0 is None:
                p0 = (22.0, p1[1] + 22 + 6 * (lane % 3))
                self.offpage(msp, s, p0, l, "from", l.get("from_nozzle"), l.get("from_line"), noz_eq, left=True)
            if p1 is None:
                p1 = (W - 22.0 - 26, p0[1] + 6 * (lane % 3))
                self.offpage(msp, s, (p1[0], p1[1]), l, "to", l.get("to_nozzle"), l.get("to_line"), noz_eq, left=False)
            lane += 1
            path = self.route(p0, d0, p1, d1, lane)
            msp.add_lwpolyline(path, dxfattribs={"layer": "PIPE", "lineweight": 50})
            segs = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
            main = max(segs, key=lambda sg: math.dist(*sg))
            drawn[l["id"]] = main
            alt_seg[l["id"]] = max((sg for sg in segs if sg is not main), key=lambda sg: math.dist(*sg), default=None)
            n_inline = sum(1 for c in piping.components(s, l["id"]) if c["type"] in inline_types)
            inst_start[l["id"]] = len(label_of(l)) * CHAR_W + 8 + n_inline * ITEM_STEP + INST_STEP / 2
            self.arrow(msp, segs[-1])
            (ax, ay), (bx, by) = main
            vertical = abs(bx - ax) < 1e-6
            label = label_of(l)
            L = math.dist((ax, ay), (bx, by))
            n_inl = sum(1 for c in piping.components(s, l["id"]) if c["type"] in inline_types)
            n_ins = sum(1 for i in insts if i.get("line") == l["id"])
            fits_items = L >= len(label) * CHAR_W + 8 + n_inl * ITEM_STEP      # same rule as the placement below
            spare = max((math.dist(*sg) for sg in segs if sg is not main), default=0)
            fits_inst = L >= need[l["id"]] or spare >= n_ins * INST_STEP + 8
            if not (fits_items and fits_inst):
                ctx.warnings.append(f"{doc_id}: line {l['id']} run is {L:.0f} mm, content needs {need[l['id']]:.0f} mm "
                                    f"- symbols may crowd (split the sheet or move equipment to another P&ID)")
            ux, uy = ((bx - ax) / L, (by - ay) / L) if L else (1, 0)
            lx, ly = ax + ux * 4, ay + uy * 4
            dxfkit.text(msp, label, lx + (-2.5 if vertical else 0), ly + (0 if vertical else 1.8), 2.0, "PIPE-TAG",
                        "LEFT", 90 if vertical else 0)
            # inline items on the main segment, from 45 % onwards
            inline = [c for c in piping.components(s, l["id"]) if c["type"] in ("VALVE", "REDUCER-CONCENTRIC",
                                                                                   "REDUCER-ECCENTRIC", "INSTRUMENT")]
            ang = math.degrees(math.atan2(by - ay, bx - ax))
            start = len(label) * CHAR_W + 8 + ITEM_STEP / 2
            for k, c in enumerate(inline):
                d = min(start + k * ITEM_STEP, max(0.0, L - 6))
                x, y = ax + ux * d, ay + uy * d
                blk = (VALVE_BLOCK.get(c.get("valve_type"), "V_GATE") if c["type"] == "VALVE"
                       else "REDUCER" if c["type"].startswith("REDUCER") else "INLINE_INST")
                msp.add_blockref(blk, (x, y), dxfattribs={"layer": "VALVE", "rotation": ang})
                if c.get("tag"):
                    dxfkit.text(msp, c["tag"], x + (4 if vertical else 0), y + (0 if vertical else -5.5), 1.6, "VALVE",
                                "MIDLEFT" if vertical else "CENTER")
                if c["type"].startswith("REDUCER") and c.get("dn2"):
                    dxfkit.text(msp, f"{(c.get('dn') or l['dn'])[2:]}x{c['dn2'][2:]}", x, y + 3, 1.5, "VALVE", "CENTER")

        # ---- instruments
        per_line: dict = {}
        for ins in sorted(insts, key=lambda i: i["id"]):
            if ins.get("line") in drawn:
                per_line.setdefault(ins["line"], []).append(ins)
            elif ins.get("equipment") in pos:
                x, y = pos[ins["equipment"]]
                self.bubble(msp, ins, (x + 16, y + 18), (x + 6, y + 6))
            else:
                ctx.warnings.append(f"{doc_id}: instrument {ins['id']} not attached to a line/equipment on this sheet")
        for lid, lst in per_line.items():
            (ax, ay), (bx, by) = drawn[lid]
            L = math.dist((ax, ay), (bx, by))
            if inst_start[lid] + len(lst) * INST_STEP > L and alt_seg.get(lid) is not None \
                    and math.dist(*alt_seg[lid]) >= len(lst) * INST_STEP + 8:
                (ax, ay), (bx, by) = alt_seg[lid]          # main run is full: use the next longest straight run
                L = math.dist((ax, ay), (bx, by))
                inst_start[lid] = INST_STEP / 2 + 4
            vertical = abs(bx - ax) < 1e-6
            ux, uy = ((bx - ax) / L, (by - ay) / L) if L else (1, 0)
            for k, ins in enumerate(lst):
                d = min(inst_start[lid] + k * INST_STEP, max(0.0, L - 6))   # after the label and inline items
                px, py = ax + ux * d, ay + uy * d
                c = (px + 16, py) if vertical else (px, py - 16)
                self.bubble(msp, ins, c, (px, py))

        # ---- border, notes, title block
        msp.add_lwpolyline([(10, 10), (W - 10, 10), (W - 10, H - 10), (10, H - 10)], close=True,
                           dxfattribs={"layer": "BORDER", "lineweight": 70})
        dxfkit.text(msp, "NOTES: 1. Generated from the project database (schematic layout, not to scale).", 14, H - 16,
                    1.8, "NOTE")
        dxfkit.text(msp, "2. Line label: LINE-DN-SPEC[-INSULATION]. Instruments per ISA 5.1; bar = DCS/PLC/SIS.", 14,
                    H - 19.5, 1.8, "NOTE")
        revs = sorted((r for r in s.records("document_revision") if r["document"] == doc_id),
                      key=lambda r: (r["issue_date"], r["revision"]))
        rev = f"{revs[-1]['revision']} {revs[-1]['purpose']} {revs[-1]['issue_date']}" if revs else "- (not issued)"
        dxfkit.title_block(msp, W - 10, 10, 1.0, [
            ("PROJECT", f"{prj['id']} {prj.get('name', '')}"[:44]),
            ("TITLE", (pdoc or {}).get("title", "P&ID")[:44]), ("DOCUMENT", doc_id), ("REVISION", rev), ("SCALE", "NTS"),
            ("GENERATED", f"{ctx.stamp['generated_at'][:10]} {ctx.stamp['generated_by']} {self.name} v{self.version}"),
            ("DATA", f"{ctx.stamp['inputs_hash']} git {ctx.stamp['git_commit']}")], 130, 6)
        errs = dxfkit.audit(doc)
        if errs:
            raise RuntimeError(f"DXF audit failed for {doc_id}: {errs[:3]}")
        base = ctx.out_dir / doc_id
        doc.saveas(base.with_suffix(".dxf"))
        dxfkit.save_pdf(doc, base.with_suffix(".pdf"), (W, H))
        return [base.with_suffix(".dxf"), base.with_suffix(".pdf")]

    @staticmethod
    def route(p0, d0, p1, d1, lane):
        """Orthogonal route: leave p0 along d0, arrive at p1 along d1 (short stubs keep lines off outlines)."""
        a = (p0[0] + d0[0] * STUB, p0[1] + d0[1] * STUB)
        b = (p1[0] - d1[0] * STUB, p1[1] - d1[1] * STUB)
        off = ((lane % 5) - 2) * 3
        if d0[1] != 0:                       # vertical exit (bottom/top outlet)
            if b[0] > a[0] + 2:
                mid = [(a[0], b[1])]         # drop to the target level, then across
            else:
                y = min(a[1], b[1]) - 20 - 4 * (lane % 4)
                mid = [(a[0], y), (b[0] - 10, y), (b[0] - 10, b[1])]
        elif b[0] > a[0] + 2:                # horizontal, forwards: Z with a vertical lane
            xm = (a[0] + b[0]) / 2 + off
            mid = [(xm, a[1]), (xm, b[1])]
        else:                                # backwards: go round underneath
            y = min(a[1], b[1]) - 30 - 4 * (lane % 4)
            mid = [(a[0], y), (b[0], y)]
        pts = [p0, a] + mid + [b, p1]
        out = [pts[0]]
        for q in pts[1:]:                    # drop duplicate and collinear points
            if math.dist(q, out[-1]) < 1e-6:
                continue
            if len(out) >= 2:
                (x1, y1), (x2, y2) = out[-2], out[-1]
                if (abs(x1 - x2) < 1e-6 and abs(x2 - q[0]) < 1e-6) or (abs(y1 - y2) < 1e-6 and abs(y2 - q[1]) < 1e-6):
                    out[-1] = q          # three points on one axis-aligned line: keep the outer two
                    continue
            out.append(q)
        return out

    @staticmethod
    def arrow(msp, seg):
        (ax, ay), (bx, by) = seg
        L = math.dist(*seg)
        if L < 8:
            return
        ux, uy = (bx - ax) / L, (by - ay) / L
        tx, ty = bx - ux * 5, by - uy * 5
        msp.add_solid([(tx, ty), (tx - ux * 3 - uy * 1.2, ty - uy * 3 + ux * 1.2),
                       (tx - ux * 3 + uy * 1.2, ty - uy * 3 - ux * 1.2)], dxfattribs={"layer": "PIPE"})

    @staticmethod
    def bubble(msp, ins, c, anchor):
        blk = "INST_FIELD" if ins.get("location", "field") in ("field", "local_panel") else "INST_DCS"
        msp.add_line(anchor, c, dxfattribs={"layer": "INST-SIG"})
        ref = msp.add_blockref(blk, c, dxfattribs={"layer": "INST"})
        dxfkit.text(msp, ins["function"], c[0], c[1] + 1.8, 2.0, "INST", "CENTER")
        dxfkit.text(msp, ins.get("loop") or "", c[0], c[1] - 2.6, 1.6, "INST", "CENTER")
        dxfkit.text(msp, ins["id"], c[0] + 6.5, c[1] - 0.8, 1.4, "INST", "LEFT")
        return ref

    @staticmethod
    def offpage(msp, s, p, line, direction, nozzle, other_line, noz_eq, left):
        x, y = (p[0] - 26, p[1]) if left else (p[0], p[1])
        msp.add_blockref("OFFPAGE", (x, y), dxfattribs={"layer": "OFFPAGE"})
        if nozzle:
            item, sheet = noz_eq.get(nozzle, nozzle), (s.get("equipment", noz_eq.get(nozzle, "")) or {}).get("pid")
        elif other_line:
            item, sheet = other_line, (s.get("line", other_line) or {}).get("pid")
        else:
            item, sheet = "not connected", None
        dxfkit.text(msp, f"{direction} {item}", x + 12, y, 1.5, "OFFPAGE", "MIDDLE")
        dxfkit.text(msp, sheet or "no P&ID assigned", x + 12, y - 5.5, 1.5, "OFFPAGE", "MIDDLE")


ENGINE = PID()
