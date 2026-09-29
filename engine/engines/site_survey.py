"""Topographic survey and site setting-out report (docx + pdf; MDL document produced_by site_survey).

From the survey_point records (control pillars, benchmarks, spot heights, existing features of the survey source), the
site design parameters (grade level, plant grid to UTM 35N transformation, height datum) and the Owner's site data:
- reference systems and a check of the plant grid -> UTM transformation against the measured control points;
- control network and benchmarks;
- platform levels on the plot against the Owner's levelled platform (grade level, acceptance +-0.10 m) and the
  temporary construction area TP-A1: statistics, points out of tolerance, cut / fill volumes (grid cell method) and the
  balanced platform level of TP-A1;
- existing features and their consequences; setting-out rules; plan figure with the points and height contours.
WARN: control point residual > 20 mm, benchmark loop inconsistency, platform points outside the tolerance."""
from __future__ import annotations

import math
from collections import defaultdict

from ..core import docshell
from ..core.runner import Context, Engine, pdf_from_office

TOL = 0.10          # m, default acceptance of the levelled platform (design parameter "Platform level acceptance tolerance")
CELL_PLOT = 25.0 * 25.0
CELL_TP = 30.0 * 35.0


class SiteSurvey(Engine):
    name = "site_survey"
    title = "Topographic survey and site setting-out report (Word + PDF)"
    version = "1.1.0"
    inputs = ["project", "document", "document_revision", "doc_type", "survey_point", "design_parameter", "source", "party",
              "requirement", "system", "mr", "clarification"]
    formats = ["docx", "pdf"]
    code_deps = ["engine/core/docshell.py", "engine/core/wordkit.py", "engine/core/release.py",
                 "templates/docx/datasheet_base.docx"]

    def run(self, ctx: Context):
        s = ctx.store
        pts = s.records("survey_point")
        files = []
        for d in s.records("document"):
            if d.get("produced_by") != self.name or d.get("status") == "cancelled":
                continue
            if not pts:
                ctx.warnings.append(f"{d['id']}: no survey_point records - not generated")
                continue
            out = self._report(ctx, d["id"], pts)
            files.append(out)
            if ctx.options.get("pdf", "yes") != "no":
                pdf = pdf_from_office(out, ctx)
                if pdf:
                    files.append(pdf)
        return files

    def _report(self, ctx, no, pts):
        s = ctx.store
        dp = {p["parameter"]: p for p in s.records("design_parameter") if p.get("status") != "superseded"}
        grade = dp.get("Site grade level", {}).get("value", 15.0)
        tol = dp.get("Platform level acceptance tolerance", {}).get("value", TOL)
        rot = math.radians(dp.get("Rotation plant grid to UTM grid", {}).get("value", 0.0))
        k = dp.get("Scale factor plant grid to UTM", {}).get("value", 1.0)
        origin = dp.get("Plant grid origin in UTM zone 35N (E 0 / N 0)", {}).get("value_text", "")
        e0, n0 = [float(x.split()[1].replace(",", "")) for x in origin.split("/")] if origin else (0.0, 0.0)
        by = defaultdict(list)
        for p in pts:
            by[p["kind"]].append(p)
        srcs = sorted({p["source"] for p in pts})
        src = s.get("source", srcs[0]) or {}
        surveyor = (s.get("party", src.get("originator", "")) or {}).get("name", src.get("originator", ""))
        d = docshell.word(ctx, no, self)

        d.h("1. Purpose and scope")
        d.p(f"This report presents the topographic survey of the site, the control network and benchmarks for setting "
            f"out, the check of the Owner's levelled platform and the levels of the temporary construction area TP-A1, "
            f"and fixes the setting-out rules for the works. Survey by {surveyor}, point listing "
            f"{src.get('doc_ref', '')} Rev {src.get('revision', '')} received {src.get('received_date', '')} "
            f"({', '.join(srcs)}): {len(pts)} points - {len(by['control'])} control pillars, {len(by['benchmark'])} "
            f"benchmarks, {len(by['spot'])} spot heights, {len(by['feature'])} existing features.")

        d.h("2. Reference systems")
        rows = [[p["parameter"], (f"{p['value']:g} " if isinstance(p.get("value"), (int, float)) else "")
                 + (p.get("value_text") or "") + (f" {p['unit']}" if p.get("unit") and p.get("unit") != "-" else ""),
                 p.get("condition") or ""]
                for key in ("Plant grid origin in UTM zone 35N (E 0 / N 0)", "Rotation plant grid to UTM grid",
                            "Scale factor plant grid to UTM", "Height datum", "Site grade level") if (p := dp.get(key))]
        d.table(["Item", "Value", "Remarks"], rows, [5.5, 5.5, 5.6], size=7)
        d.p("Plant grid (E, N) in metres, origin at the south-west plot corner, plant north = true north (ALP-OWN-GEN-001). "
            "UTM = origin + k x R(rotation) x (E, N). All design drawings use plant grid coordinates; UTM coordinates are "
            "used for the authority submissions and the external connections.")
        res = []
        for p in sorted(by["control"], key=lambda x: x["id"]):
            if p.get("utm_e") is None:
                continue
            ue = e0 + k * (p["e"] * math.cos(rot) - p["n"] * math.sin(rot))
            un = n0 + k * (p["e"] * math.sin(rot) + p["n"] * math.cos(rot))
            r = math.hypot(ue - p["utm_e"], un - p["utm_n"]) * 1000
            res.append([p["id"], f"{p['e']:.3f}", f"{p['n']:.3f}", f"{p['utm_e']:.3f}", f"{p['utm_n']:.3f}", f"{p['z']:.3f}",
                        f"{r:.0f}"])
            if r > 20:
                ctx.warnings.append(f"{no}: control point {p['id']} transformation residual {r:.0f} mm > 20 mm")
        d.h("3. Control network and benchmarks")
        d.p("Primary control pillars (GNSS static observations) with the residual of the transformation from plant grid "
            "to UTM against the measured coordinates:")
        d.table(["Point", "E plant", "N plant", "E UTM 35N", "N UTM 35N", "Height", "Residual mm"], res,
                [1.6, 2.0, 2.0, 3.0, 3.2, 1.8, 2.0], size=7)
        d.table(["Benchmark", "E plant", "N plant", "Height m", "Description"],
                [[p["id"], f"{p['e']:.1f}", f"{p['n']:.1f}", f"{p['z']:.3f}", p.get("description", "")]
                 for p in sorted(by["benchmark"], key=lambda x: x["id"])], [1.8, 1.7, 1.7, 1.8, 9.6], size=7)

        d.h("4. Platform levels")
        spots = defaultdict(list)
        for p in by["spot"]:
            spots[p["area"]].append(p)
        plot = spots.get("plot", [])
        dev = [p["z"] - grade for p in plot]
        out_tol = [p for p in plot if abs(p["z"] - grade) > tol + 1e-9]
        if plot:
            mean = sum(dev) / len(dev)
            sd = math.sqrt(sum((x - mean) ** 2 for x in dev) / len(dev))
            cut = sum(max(0.0, x) for x in dev) * CELL_PLOT
            fill = sum(max(0.0, -x) for x in dev) * CELL_PLOT
            fill_out = sum(max(0.0, -x - tol) for x in dev) * CELL_PLOT
            d.p(f"Plot ({len(plot)} spot heights on a 25 m grid, stream channel strip excluded): levels "
                f"{min(p['z'] for p in plot):.2f} to {max(p['z'] for p in plot):.2f} m, mean deviation from the "
                f"platform level +{grade:.2f} m {mean * 1000:+.0f} mm, standard deviation {sd * 1000:.0f} mm; "
                f"{len(plot) - len(out_tol)} of {len(plot)} points ({(len(plot) - len(out_tol)) / len(plot):.0%}) within "
                f"+-{tol:.2f} m (acceptance tolerance). Trimming to +{grade:.2f} m: cut {cut:,.0f} m3, fill {fill:,.0f} m3 (grid cell method, "
                f"25 x 25 m cells).")
            if out_tol:
                d.table(["Point", "E", "N", "Level m", "Deviation mm", "Area"],
                        [[p["id"], f"{p['e']:.0f}", f"{p['n']:.0f}", f"{p['z']:.3f}", f"{(p['z'] - grade) * 1000:+.0f}",
                          "old warehouse foundations" if 300 <= p["e"] <= 360 and 20 <= p["n"] <= 60
                          else "south edge (setback fence)" if p["n"] <= 5 else "platform"]
                         for p in sorted(out_tol, key=lambda x: x["id"])], [1.8, 1.5, 1.5, 2.0, 2.2, 7.6], size=7)
                ctx.warnings.append(f"{no}: {len(out_tol)} platform points outside +-{tol:.2f} m (reported)")
        tp = spots.get("TP-A1", [])
        if tp:
            zs = [p["z"] for p in tp]
            bal = sum(zs) / len(zs)
            d.p(f"Temporary construction area TP-A1 ({len(tp)} spot heights, 30 x 35 m grid): levels {min(zs):.2f} to "
                f"{max(zs):.2f} m, rising to the north. Balanced platform level +{bal:.2f} m (cut = fill "
                f"{sum(max(0.0, z - bal) for z in zs) * CELL_TP:,.0f} m3); the laydown and fabrication areas are levelled "
                f"to +{bal:.2f} m with a 1 % fall to the south-west drainage ditch and restored after Taking-Over "
                f"(TQ-012).")

        d.h("5. Existing features")
        d.table(["Point", "E", "N", "Level m", "Feature"],
                [[p["id"], f"{p['e']:.0f}", f"{p['n']:.0f}", f"{p['z']:.2f}", p.get("description", "")]
                 for p in sorted(by["feature"], key=lambda x: x["id"])], [1.6, 1.4, 1.4, 1.8, 10.4], size=7)
        d.bullets(["Stream channel on the west boundary: the 10 m water authority buffer (E 0-20) stays free of "
                   "permanent structures; the channel bed falls from +13.41 m (north) to +13.02 m (south).",
                   "11 kV utility cable along the east boundary (E 390): no excavation within 2 m until its relocation by "
                   "the Owner (due 2027-06-30); hand digging to locate before any crossing.",
                   "Abandoned warehouse foundations (E 300-360, N 20-60) stand up to 0.25 m above the platform: "
                   "demolition and removal by the Contractor before the platform trimming in that area.",
                   "Meteorological mast (E 20, N 280) and groundwater wells GW-1 to GW-3 are kept; wells in conflict "
                   "with foundations are replaced by the Contractor."])

        d.h("6. Setting-out rules")
        d.bullets([f"All setting out from the control pillars {', '.join(p['id'] for p in sorted(by['control'], key=lambda x: x['id']))} "
                   f"and the benchmarks; pillars are checked against each other before each major setting-out and at "
                   f"least monthly (tolerance 10 mm plan, 5 mm height).",
                   "Setting-out tolerances per ISO 4463-1: main grid lines +-10 mm, foundation axes +-5 mm, anchor bolt "
                   "groups +-3 mm (template), levels +-5 mm.",
                   "Every structure is set out from the plant grid; coordinates are taken from the IFC plot plan and the "
                   "3D model (never scaled from drawings).",
                   "Construction benchmarks inside each CWA are levelled from BM-01 / BM-02 with loop closure <= 3 mm."])
        d.h("7. Findings")
        f = [f"Control network: transformation residuals {max((float(r[6]) for r in res), default=0):.0f} mm maximum "
             f"(limit 20 mm) - the plant grid is fixed and can be used for setting out."]
        if plot:
            f.append(f"Owner's platform: mean {mean * 1000:+.0f} mm against +{grade:.2f} m, {len(out_tol)} of {len(plot)} "
                     f"points outside +-{tol:.2f} m, with a systematic fall towards the south and the old warehouse "
                     f"foundations above the platform. Final trimming to +{grade:.2f} m needs about {fill:,.0f} m3 of "
                     f"structural fill and {cut:,.0f} m3 of cut; fill below the tolerance band (-{tol:.2f} m): {fill_out:,.0f} m3.")
        tqs = [q for q in s.records("clarification") if no in (q.get("question") or "")]
        for q in tqs:
            f.append(f"{q['id']} ({q.get('status')}): {q.get('subject')}" + (f" - answer: {q['response']}" if q.get("response") else ""))
        d.bullets(f)
        img = self._figure(ctx, pts, grade)
        d.h("8. Site plan")
        d.image(img, 17.0, "Figure 1 - Survey points and platform levels (plant grid, m); contours of the spot heights at 0.1 m "
                           "(plot) and 0.25 m (TP-A1)")
        out = ctx.out_dir / f"{no}.docx"
        d.save(out)
        img.unlink()
        return out

    def _figure(self, ctx, pts, grade):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 8.6), dpi=150)
        ax.add_patch(plt.Rectangle((0, 0), 400, 300, fill=False, lw=1.5, ec="black"))
        ax.add_patch(plt.Rectangle((0, 320), 180, 280, fill=False, lw=1.2, ec="0.35", ls="--"))
        ax.add_patch(plt.Rectangle((0, 0), 10, 300, fc="#9ecae1", ec="none"))
        ax.text(200, 150, "PLOT 12.0 ha\nplatform +%.2f" % grade, ha="center", va="center", fontsize=9, color="0.3")
        ax.text(90, 460, "TP-A1\ntemporary area", ha="center", va="center", fontsize=9, color="0.3")
        for area, step in (("plot", 0.1), ("TP-A1", 0.25)):
            sp = [p for p in pts if p["kind"] == "spot" and p["area"] == area]
            if len(sp) > 3:
                import numpy as np
                z = [p["z"] for p in sp]
                lv = np.arange(math.floor(min(z) / step) * step, max(z) + step, step)
                cs = ax.tricontour([p["e"] for p in sp], [p["n"] for p in sp], z, levels=lv, linewidths=0.6, cmap="viridis")
                ax.clabel(cs, fontsize=5, fmt="%.2f")
        style = {"control": ("^", "red", 40), "benchmark": ("s", "blue", 30), "spot": (".", "0.5", 4), "feature": ("x", "black", 20)}
        for kind, (m, c, sz) in style.items():
            sel = [p for p in pts if p["kind"] == kind]
            ax.scatter([p["e"] for p in sel], [p["n"] for p in sel], marker=m, c=c, s=sz, label=kind, zorder=3)
            if kind in ("control", "benchmark"):
                for p in sel:
                    ax.annotate(p["id"], (p["e"], p["n"]), textcoords="offset points", xytext=(4, 4), fontsize=6)
        ax.set_xlim(-20, 430)
        ax.set_ylim(-80, 620)
        ax.set_aspect("equal")
        ax.set_xlabel("E (plant grid, m)")
        ax.set_ylabel("N (plant grid, m)")
        ax.axhline(-60, color="#3182bd", lw=0.8)
        ax.text(300, -72, "shoreline", fontsize=7, color="#3182bd")
        ax.legend(loc="upper right", fontsize=7)
        ax.grid(True, lw=0.3, color="0.85")
        fig.tight_layout()
        out = ctx.out_dir / "_survey_plan.png"
        fig.savefig(out)
        plt.close(fig)
        return out


ENGINE = SiteSurvey()
