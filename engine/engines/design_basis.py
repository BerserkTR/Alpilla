"""Design Basis report (.md + .html) from design_parameter records, with full basis traceability."""
from __future__ import annotations

from ..core.runner import Context, Engine

CATEGORY_ORDER = ["site", "ambient", "fuel_gas", "backup_fuel", "grid", "performance", "water", "emissions",
                  "noise", "codes_standards", "operation", "other"]


class DesignBasis(Engine):
    name = "design_basis"
    title = "Design Basis report (Markdown + HTML) with traceability to sources/references/decisions"
    version = "1.1.1"
    inputs = ["project", "design_parameter", "source", "reference", "decision"]
    formats = ["md", "html"]

    def run(self, ctx: Context):
        import jinja2
        import markdown

        s = ctx.store
        sch = s.schema("design_parameter")
        params = [p for p in s.records("design_parameter") if p.get("status") != "superseded"]

        def label(ref: str) -> str:
            ent, rid = ref.split(":", 1)
            r = s.get(ent, rid) or {}
            return f"{rid} {r.get('code') or r.get('title') or ''}".strip()

        groups = []
        for cat in CATEGORY_ORDER:
            rows = sorted((p for p in params if p["category"] == cat), key=lambda p: p["parameter"].lower())
            if rows:
                groups.append({"category": cat.replace("_", " ").title(), "rows": rows})
        cited = sorted({ref for p in params for ref in p.get("basis_refs", [])})
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(ctx.project.templates), autoescape=False,
                                 undefined=jinja2.StrictUndefined, trim_blocks=True, lstrip_blocks=True,
                                 keep_trailing_newline=True)
        env.filters["label"] = label
        env.filters["cell"] = lambda v: str(v).replace("|", "\\|").replace("\n", " ")
        data = dict(project=ctx.project_record(), stamp=ctx.stamp, groups=groups,
                    assumptions=[p for p in params if p.get("status") == "assumption"],
                    cited=[{"entity": r.split(":", 1)[0], "label": label(r)} for r in cited], total=len(params),
                    statuses=sch.fields["status"]["values"])
        md_text = env.get_template("reports/design_basis.md.j2").render(**data)
        prj = data["project"]["id"]
        md_file = ctx.out_dir / f"{prj}_design_basis.md"
        md_file.write_text(md_text, encoding="utf-8")

        body = markdown.markdown(md_text, extensions=["tables"])
        html = env.get_template("html/report.html.j2").render(title=f"{prj} Design Basis", body=body, stamp=ctx.stamp)
        html_file = ctx.out_dir / f"{prj}_design_basis.html"
        html_file.write_text(html, encoding="utf-8")
        return [md_file, html_file]


ENGINE = DesignBasis()
