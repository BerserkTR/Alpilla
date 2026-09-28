"""Design basis: the Plant Design Basis Report (MDL document produced_by design_basis: docx + pdf) and a traceability
report (.md + .html) from design_parameter records.

The report is built from the records only: plant configuration (system and equipment records), site, ambient, fuel,
grid, performance, water, emissions, noise and operating data (design_parameter), Owner and power island guarantees
(guarantee), applicable codes (reference), and every value carries its status and basis."""
from __future__ import annotations

from ..core import docshell
from ..core.runner import Context, Engine, pdf_from_office

CATEGORY_ORDER = ["site", "ambient", "fuel_gas", "backup_fuel", "grid", "performance", "water", "emissions",
                  "noise", "codes_standards", "operation", "other"]


class DesignBasis(Engine):
    name = "design_basis"
    title = "Design Basis report (Markdown + HTML) with traceability to sources/references/decisions"
    version = "1.2.0"
    inputs = ["project", "design_parameter", "source", "reference", "decision", "document", "document_revision", "doc_type",
              "system", "equipment", "guarantee", "requirement", "party", "mr"]
    formats = ["md", "html", "docx", "pdf"]
    code_deps = ["engine/core/docshell.py", "engine/core/wordkit.py", "engine/core/release.py",
                 "templates/docx/datasheet_base.docx", "templates/reports/design_basis.md.j2", "templates/html/report.html.j2"]

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
        files = [md_file, html_file]
        for d in s.records("document"):
            if d.get("produced_by") == self.name and d.get("status") != "cancelled":
                out = self._report(ctx, d["id"], params, label)
                files.append(out)
                if ctx.options.get("pdf", "yes") != "no":
                    pdf = pdf_from_office(out, ctx)
                    if pdf:
                        files.append(pdf)
        return files

    # ------------------------------------------------------------------ Plant Design Basis Report (docx)
    def _report(self, ctx, no, params, label):
        s = ctx.store
        d = docshell.word(ctx, no, self)
        prj = ctx.project_record()
        by = {}
        for p in params:
            by.setdefault(p["category"], []).append(p)

        def val(p):
            v = p.get("value")
            txt = (f"{v:,.10g}" if isinstance(v, (int, float)) else "") or p.get("value_text") or "-"
            if isinstance(v, (int, float)) and p.get("value_text"):
                txt += f" ({p['value_text']})"
            return f"{txt} {p.get('unit') or ''}".strip()

        def table(cat):
            rows = [[p["parameter"], val(p), p.get("condition") or "", p.get("status") or "",
                     ", ".join(label(r) for r in p.get("basis_refs") or [])]
                    for p in sorted(by.get(cat, []), key=lambda p: p["parameter"].lower())]
            if rows:
                d.table(["Parameter", "Value", "Condition", "Status", "Basis"], rows, [5.2, 3.4, 3.3, 1.8, 3.7], size=7)
            else:
                d.p("No parameters recorded.")

        systems = sorted((x for x in s.records("system") if len(x["id"]) == 5), key=lambda x: x["id"])
        eq = {e["id"]: e for e in s.records("equipment")}
        d.h("1. Purpose and scope")
        d.p(f"This report fixes the design basis of {prj.get('name', '')}: the site, climatic, fuel, grid, water and "
            f"environmental conditions, the performance and operating requirements and the guarantees against which the "
            f"plant is designed. All values are taken from the project database; each value states its status "
            f"(assumption, preliminary, confirmed) and its basis (Owner document, requirement, reference or decision). "
            f"Discipline design criteria (process, mechanical, electrical, I&C, civil / structural, HVAC, HSE) are "
            f"derived from this report.")
        d.h("2. Plant configuration")
        main = [e for e in eq.values() if e.get("equipment_type") in ("gas turbine", "HRSG", "steam turbine", "generator")
                or (e.get("equipment_type") == "transformer" and e["system"].endswith("BAT"))]
        d.p("1 x 1 multi-shaft combined cycle: one gas turbine with generator, one three-pressure reheat "
            "heat recovery steam generator with SCR, one reheat condensing steam turbine with its own generator and a "
            "seawater-cooled surface condenser; both generators connected through generator step-up transformers to "
            "the 380 kV GIS switchyard. Main equipment (register):")
        d.table(["Tag", "Description", "System", "Supply"],
                [[e["id"], e.get("description", ""), e["system"], e.get("supply", "")] for e in sorted(main, key=lambda e: e["id"])],
                [3.0, 8.5, 2.2, 1.8], size=7)
        cats = {}
        for x in systems:
            if x["id"][2] != "U":
                cats.setdefault(x.get("category", "other"), []).append(x)
        d.p(f"{sum(len(v) for v in cats.values())} plant systems (KKS, ALP-EPC-00000-GE-PRC-0001), by category:")
        d.table(["Category", "Systems"], [[k.replace("_", " "), ", ".join(f"{x['id']} {x['title']}" for x in v)]
                                         for k, v in sorted(cats.items())], [3.5, 13.0], size=7)
        sections = [("3. Site data", "site", "Site location, levels, loads and soil conditions for the civil and structural "
                     "design; site class and seismic hazard per TBDY 2018."),
                    ("4. Ambient and climatic conditions", "ambient", "Design ambient conditions, Site Reference Conditions "
                     "(SRC) for performance, salt-laden marine atmosphere and lightning data."),
                    ("5. Fuels", "fuel_gas", "Natural gas (main fuel) at the terminal point."),
                    (None, "backup_fuel", "Light distillate oil (back-up fuel)."),
                    ("6. Grid connection", "grid", "Connection to the 380 kV transmission grid (TSO)."),
                    ("7. Performance and operation", "performance", "Performance requirements at SRC."),
                    (None, "operation", "Operating regime and design life."),
                    ("8. Cooling water and water supply", "water", "Once-through seawater cooling; seawater quality at the "
                     "intake; condenser design."),
                    ("9. Emissions and noise", "emissions", "Stack emission limits (15 % O2, dry) and stack height."),
                    (None, "noise", "Noise limits.")]
        for head, cat, intro in sections:
            if head:
                d.h(head)
            d.p(intro)
            table(cat)
        d.h("10. Guarantees")
        d.p("Owner guarantees (PG, contract ALP-EPC-001) and the power island guarantees of Imaginary Electric (IG, "
            "ALP-CA-001) that cover them back-to-back.")
        g = sorted(s.records("guarantee"), key=lambda x: (x["contract"], x["id"]))
        d.table(["Id", "Guarantee", "Value", "Min / max", "Conditions"],
                [[x["id"], x["parameter"], f"{x['guaranteed_value']:,.10g} {x['unit']}", x["direction"],
                  x.get("conditions", "")] for x in g], [1.2, 5.2, 2.6, 1.4, 6.0], size=7)
        d.h("11. Codes and standards")
        d.p("The applicable codes, standards and Turkish regulations, their editions and their order of precedence are "
            "listed in the Codes, Standards and Regulations Register (Appendix A.19, ALP-EPC-00000-GE-LST-0001); design to Eurocodes with Turkish national annexes and TBDY 2018 for structures, "
            "IEC for electrical and I&C, ASME / EN for pressure parts, NFPA 850 for fire protection.")
        d.h("12. Open items and assumptions")
        opn = [p for p in params if p.get("status") in ("assumption", "preliminary")]
        if opn:
            d.table(["Parameter", "Value", "Status", "Basis"],
                    [[p["parameter"], val(p), p["status"], ", ".join(label(r) for r in p.get("basis_refs") or [])] for p in opn],
                    [6.0, 3.5, 2.0, 5.0], size=7)
        else:
            d.p(f"None: all {len(params)} design parameters are confirmed by the Owner documents, the contract or "
                f"agreed technical queries.")
        d.h("13. Basis documents")
        cited = sorted({r for p in params for r in p.get("basis_refs") or []})
        d.table(["Reference", "Title"], [[r, label(r)] for r in cited], [4.5, 12.0], size=7)
        out = ctx.out_dir / f"{no}.docx"
        return d.save(out)


ENGINE = DesignBasis()
