"""Plot plan (DXF R2018 + PDF): true-scale top view of equipment footprints and routed pipe centrelines,
plant coordinate grid, north arrow, title block. Drawn in plant coordinates (mm) so it overlays the 3D model.
Options: grid=10000 (grid spacing mm)."""
from __future__ import annotations

import math

from ..core import dxfkit, piping
from ..core.runner import Context, Engine


def footprint(eq):
    x, y, _ = eq["position"]
    a = math.radians(eq.get("orientation") or 0)
    shp = eq.get("shape")
    if shp == "vertical_cylinder" and eq.get("diameter"):
        return "circle", (x, y, eq["diameter"] / 2)
    if shp == "horizontal_cylinder" and eq.get("length") and eq.get("diameter"):
        L, W = eq["length"], eq["diameter"]
    elif shp == "box" and eq.get("length") and eq.get("width"):
        L, W = eq["length"], eq["width"]
    else:
        return None, None
    c, s = math.cos(a), math.sin(a)
    pts = [(x + c * dx - s * dy, y + s * dx + c * dy) for dx, dy in
           ((-L / 2, -W / 2), (L / 2, -W / 2), (L / 2, W / 2), (-L / 2, W / 2))]
    return "poly", pts


class PlotPlan(Engine):
    name = "plot_plan"
    title = "Plot plan (DXF + PDF): equipment footprints, pipe centrelines, coordinate grid"
    version = "1.1.0"
    inputs = ["project", "equipment", "line", "pipe_component", "pipe_size"]
    formats = ["dxf", "pdf"]

    def run(self, ctx: Context):
        s = ctx.store
        prj = ctx.project_record()
        doc = dxfkit.new_doc()
        msp = doc.modelspace()
        eqs = [e for e in s.records("equipment") if e.get("position") and e.get("status") != "deleted"]
        ext = [p for e in eqs for p in ([e["position"][:2]] + (footprint(e)[1] if footprint(e)[0] == "poly" else []))]
        ex = max((max(p[0] for p in ext) - min(p[0] for p in ext), max(p[1] for p in ext) - min(p[1] for p in ext)),
                 default=0) if ext else 0
        th = max(1.0, 1.2 * ex / 400.0 / 100.0)          # text scale: about 2.5 mm tags on A3 for large plots
        pts = []
        drawn = 0
        for eq in eqs:
            kind, geo = footprint(eq)
            if kind is None:
                ctx.warnings.append(f"{eq['id']}: no shape/dimensions - shown as a point only")
                x, y = eq["position"][:2]
                msp.add_point((x, y), dxfattribs={"layer": "EQPT"})
                pts.append((x, y))
                tx, ty = x, y
            elif kind == "circle":
                x, y, r = geo
                msp.add_circle((x, y), r, dxfattribs={"layer": "EQPT"})
                pts += [(x - r, y - r), (x + r, y + r)]
                tx, ty = x, y
                drawn += 1
            else:
                msp.add_lwpolyline(geo, close=True, dxfattribs={"layer": "EQPT"})
                pts += geo
                tx, ty = sum(p[0] for p in geo) / 4, sum(p[1] for p in geo) / 4
                drawn += 1
            dxfkit.text(msp, eq["id"], tx, ty + 350 * th, 300 * th, "EQPT-TAG", "CENTER")
            dxfkit.text(msp, eq["description"][:40], tx, ty - 250 * th, 180 * th, "EQPT-TAG", "CENTER")
            msp.add_circle((eq["position"][0], eq["position"][1]), 60, dxfattribs={"layer": "EQPT-TAG"})
        for line in s.records("line"):
            comps = piping.components(s, line["id"])
            longest = None
            for c in comps:
                if c["type"] == "SUPPORT" or not c.get("end1") or not c.get("end2"):
                    continue
                seg = (piping.arc_points(c["end1"], c["centre"], c["end2"], 8)
                       if c["type"] in ("ELBOW", "BEND") and c.get("centre") else [c["end1"], c["end2"]])
                msp.add_lwpolyline([(p[0], p[1]) for p in seg], dxfattribs={"layer": "PIPE"})
                pts += [(p[0], p[1]) for p in seg]
                L = math.dist(seg[0][:2], seg[-1][:2])
                if longest is None or L > longest[0]:
                    longest = (L, seg[0], seg[-1])
            if longest and longest[0] > 500:
                (x1, y1), (x2, y2) = longest[1][:2], longest[2][:2]
                ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
                if ang > 90 or ang < -90:
                    ang += 180
                dxfkit.text(msp, f"{line['id']}  {line['dn']}-{line['spec']}", (x1 + x2) / 2, (y1 + y2) / 2 + 150,
                            160, "PIPE-TAG", "CENTER", ang)
        if not pts:
            ctx.warnings.append("no equipment positions or routed piping - empty plot plan")
            pts = [(0, 0), (10000, 10000)]
        xmin, ymin = min(p[0] for p in pts), min(p[1] for p in pts)
        xmax, ymax = max(p[0] for p in pts), max(p[1] for p in pts)
        g = float(ctx.options.get("grid", 10000))
        pad = 0.08 * max(xmax - xmin, ymax - ymin, g)          # breathing room, then snap to the grid
        gx0, gy0 = math.floor((xmin - pad) / g) * g, math.floor((ymin - pad) / g) * g
        gx1, gy1 = math.ceil((xmax + pad) / g) * g, math.ceil((ymax + pad) / g) * g
        x = gx0
        while x <= gx1:
            msp.add_line((x, gy0), (x, gy1), dxfattribs={"layer": "GRID"})
            dxfkit.text(msp, f"E {x / 1000:+.0f}", x, gy0 - 500 * th, 250 * th, "GRID", "CENTER")
            x += g
        y = gy0
        while y <= gy1:
            msp.add_line((gx0, y), (gx1, y), dxfattribs={"layer": "GRID"})
            dxfkit.text(msp, f"N {y / 1000:+.0f}", gx0 - 400 * th, y, 250 * th, "GRID", "RIGHT")
            y += g
        # north arrow (plant north = +Y)
        nx, ny = gx1 + 1500, gy1 - 3000
        msp.add_lwpolyline([(nx, ny), (nx - 500, ny - 1500), (nx, ny - 1100), (nx + 500, ny - 1500)], close=True,
                           dxfattribs={"layer": "NOTE"})
        dxfkit.text(msp, "N", nx, ny + 300, 500, "NOTE", "CENTER")
        # frame + title block scaled to the drawing
        span = max(gx1 - gx0, gy1 - gy0)
        sc = span / 400.0
        doc.header["$LTSCALE"] = max(1.0, sc)       # dash lengths in paper mm, not model mm (else millions of dashes)
        fx0, fy0, fx1, fy1 = gx0 - 2500, gy0 - 2500 - 60 * sc, gx1 + 3000, gy1 + 1500
        msp.add_lwpolyline([(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1)], close=True, dxfattribs={"layer": "BORDER"})
        dxfkit.title_block(msp, fx1, fy0, sc, [
            ("PROJECT", f"{prj['id']} {prj.get('name', '')}"[:48]), ("DRAWING", "PLOT PLAN"),
            ("COORDINATES", "plant E/N/EL in mm, grid " + f"{g / 1000:.0f} m"),
            ("GENERATED", f"{ctx.stamp['generated_at'][:10]} {ctx.stamp['generated_by']} {self.name} v{self.version}"),
            ("DATA", f"{ctx.stamp['inputs_hash']} git {ctx.stamp['git_commit']}"),
            ("STATUS", "GENERATED - issue only via transmittal")], 150, 7)
        errs = dxfkit.audit(doc)
        if errs:
            raise RuntimeError(f"DXF audit failed: {errs[:3]}")
        base = ctx.out_dir / f"{prj['id']}_plot_plan"
        doc.saveas(base.with_suffix(".dxf"))
        dxfkit.save_pdf(doc, base.with_suffix(".pdf"), (420, 297))
        return [base.with_suffix(".dxf"), base.with_suffix(".pdf")]


ENGINE = PlotPlan()
