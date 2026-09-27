"""Engineering progress report (.html): weighted document S-curve (planned vs earned), KPIs,
discipline breakdown and late documents. Planned % comes from planned IFR/IFA/IFC dates, earned %
from issued revisions, both weighted by document weight through the progress_rule records."""
from __future__ import annotations

import html
from datetime import date, timedelta

from ..core import planning
from ..core.runner import Context, Engine
from .document_register import register_rows


def value_at(series: dict, d: date) -> float:
    v = 0.0
    for k in sorted(series):
        if k <= d:
            v = series[k]
    return v


class ProgressReport(Engine):
    name = "progress_report"
    title = "Engineering progress report (HTML): document S-curve, KPIs, late documents"
    version = "1.0.0"
    inputs = ["project", "document", "document_revision", "review_comment", "progress_rule"]
    formats = ["html"]

    def run(self, ctx: Context):
        import jinja2
        s = ctx.store
        prj = ctx.project_record()
        if not s.records("document"):
            ctx.warnings.append("no documents - no progress report")
            return []
        if not s.records("progress_rule"):
            raise RuntimeError("no progress_rule records - add e.g. IFR/IFA/IFC percentages first")
        cal, dd, _ = planning.calendar_for(s)
        curves = planning.document_curves(s, cal)
        events = sorted(set(curves["planned"]) | set(curves["earned"]) | {dd})
        t0 = min(events) - timedelta(days=min(events).weekday())
        t1 = max(events) + timedelta(days=7)
        weeks = []
        w = t0 + timedelta(days=6)
        while w <= t1 + timedelta(days=6):
            weeks.append(w)
            w += timedelta(days=7)
        planned = [round(value_at(curves["planned"], w), 2) for w in weeks]
        earned = [round(value_at(curves["earned"], w), 2) if w <= dd else None for w in weeks]   # nothing after the data date
        rows = register_rows(s, dd)
        p_now, e_now = value_at(curves["planned"], dd), value_at(curves["earned"], dd)
        svg = self.scurve(weeks, planned, earned, dd)
        disc: dict = {}
        for r in rows:
            if r["doc"].get("status") != "cancelled":
                disc.setdefault(r["doc"]["discipline"], []).append(r)
        disc_rows = []
        for k, rs in sorted(disc.items()):
            w = [x["doc"].get("weight") or 1.0 for x in rs]
            disc_rows.append({"discipline": k, "n": len(rs), "ifc": sum(1 for x in rs if x["actual_ifc"]),
                              "late": sum(1 for x in rs if x["late"]),
                              "progress": sum((x["progress"] or 0) * wi for x, wi in zip(rs, w)) / sum(w)})
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(ctx.project.templates), autoescape=True)
        text = env.get_template("html/progress.html.j2").render(
            prj=prj, stamp=ctx.stamp, engine=self, dd=dd, planned_now=p_now, earned_now=e_now,
            late=[r for r in rows if r["late"]], open_comments=sum(r["open_comments"] for r in rows),
            svg=svg, disc_rows=disc_rows,
            table=[(w, p, e) for w, p, e in zip(weeks, planned, earned)])
        out = ctx.out_dir / f"{prj['id']}_progress_report.html"
        out.write_text(text, encoding="utf-8")
        return [out]

    @staticmethod
    def scurve(weeks, planned, earned, dd):
        from markupsafe import Markup
        W, H, L, R, T, B = 900, 340, 48, 120, 16, 36
        pw, ph = W - L - R, H - T - B
        n = len(weeks)
        X = lambda i: L + (pw * i / max(1, n - 1))
        Y = lambda v: T + ph * (1 - v / 100)
        e = html.escape
        out = [f'<svg class="scurve" viewBox="0 0 {W} {H}" width="100%" role="img" '
               f'aria-label="S-curve: planned {planned[-1]:.0f}% vs earned progress">']
        for v in (0, 25, 50, 75, 100):
            out.append(f'<line x1="{L}" x2="{L + pw}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="var(--grid)"/>')
            out.append(f'<text x="{L - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" fill="var(--muted)" font-size="11">{v}%</text>')
        out.append(f'<line x1="{L}" x2="{L + pw}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="var(--axis)"/>')
        step = max(1, n // 8)
        for i in range(0, n, step):
            out.append(f'<text x="{X(i):.1f}" y="{H - 14}" text-anchor="middle" fill="var(--muted)" font-size="11">'
                       f'{weeks[i].strftime("%d %b %y")}</text>')
        di = min(range(n), key=lambda i: abs((weeks[i] - dd).days))
        out.append(f'<line x1="{X(di):.1f}" x2="{X(di):.1f}" y1="{T}" y2="{Y(0):.1f}" stroke="var(--text-secondary)" '
                   f'stroke-dasharray="4 3"/><text x="{X(di) + 4:.1f}" y="{T + 10}" fill="var(--text-secondary)" '
                   f'font-size="11">data date</text>')

        def path(vals):
            pts = [(X(i), Y(v)) for i, v in enumerate(vals) if v is not None]
            return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts), pts
        dp, pp = path(planned)
        de, pe = path(earned)
        out.append(f'<path d="{dp}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round"/>')
        if pe:
            out.append(f'<path d="{de}" fill="none" stroke="var(--series-2)" stroke-width="2" stroke-linejoin="round"/>')
        # direct labels at line ends (text in ink, marker carries the color)
        for pts, name, var, val in ((pp, "Planned", "--series-1", planned[-1]),
                                    (pe, "Earned", "--series-2", next((v for v in reversed(earned) if v is not None), 0))):
            if pts:
                x, y = pts[-1]
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="var({var})" stroke="var(--surface-1)" stroke-width="2"/>')
                out.append(f'<text x="{x + 8:.1f}" y="{y + 4:.1f}" fill="var(--text-primary)" font-size="12">{name} {val:.1f}%</text>')
        # crosshair + hover targets (one column per week, wider than the marks)
        out.append(f'<line id="xh" x1="0" x2="0" y1="{T}" y2="{Y(0):.1f}" stroke="var(--text-secondary)" visibility="hidden"/>')
        colw = pw / max(1, n - 1)
        for i, w in enumerate(weeks):
            ev = "-" if earned[i] is None else f"{earned[i]:.1f}%"
            tip = f"week ending {w.strftime('%d %b %Y')}&#10;planned {planned[i]:.1f}%&#10;earned {ev}"
            out.append(f'<rect class="hit" x="{X(i) - colw / 2:.1f}" y="{T}" width="{colw:.1f}" height="{ph}" '
                       f'fill="transparent" data-x="{X(i):.1f}" data-tip="{tip}"/>')
        out.append("</svg>")
        return Markup("\n".join(out))


ENGINE = ProgressReport()
