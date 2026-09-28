"""Technical specifications (docx + pdf, one per MDL document of type SPC with produced_by = specifications).

Built from the records only:
- scope of supply: the equipment of the specification's procurement package (equipment.mr) with service, redundancy
  and rated data from the equipment list, plus the scope clauses;
- codes and standards: the reference records cited by the clauses, with the order of precedence of the register;
- site and design conditions: the design_parameter records of the site, ambient and seismic categories (identical in
  every specification);
- technical, material, testing, spares, packing, site, interface and exclusion requirements: spec_clause records
  (text and / or parameter - value - unit, with status and basis);
- inspection and testing: the package ITP; supplier documentation: every supplier document of the package in the MDL
  (VDRL) with its review class and its first / final issue in weeks after the PO or before shipment;
- attachments: the EPC datasheets of the package.
WARN: a specification without clauses, a package without equipment, a clause citing a reference not in the register."""
from __future__ import annotations

from collections import defaultdict

from ..core import docshell
from ..core.runner import Context, Engine, pdf_from_office

SITE_PARAMS = ["Site grade level", "Plot dimensions", "Ambient temperature - minimum for full capability",
               "Ambient temperature - maximum for full capability", "Summer design dry bulb (0.4 %)",
               "Winter design dry bulb (99.6 %)", "Record maximum / minimum temperature", "SRC relative humidity",
               "SRC barometric pressure", "Atmospheric corrosivity category", "Chloride deposition maximum",
               "Sea-salt aerosol maximum (event)", "PM10 maximum (event)", "Seismic design PGA (DD-2, 475-year)",
               "Seismic site class", "Basic wind speed", "Ground snow load", "Design rainfall intensity",
               "Ground flash density"]
SECTIONS = [("design", "Design requirements"), ("technical", "Technical requirements"), ("materials", "Materials"),
            ("testing", "Inspection and testing"), ("documentation", "Documentation"), ("spares", "Spare parts and special tools"),
            ("packing", "Packing, transport and storage"), ("site", "Site services"), ("interfaces", "Interfaces"),
            ("exclusions", "Exclusions")]


class Specifications(Engine):
    name = "specifications"
    title = "Technical specifications of the procurement packages (Word + PDF)"
    version = "1.0.0"
    inputs = ["project", "document", "document_revision", "doc_type", "spec_clause", "equipment", "mr", "design_parameter",
              "reference", "party", "system", "requirement"]
    formats = ["docx", "pdf"]
    code_deps = ["engine/core/docshell.py", "engine/core/wordkit.py", "engine/core/release.py",
                 "templates/docx/datasheet_base.docx"]

    def run(self, ctx: Context):
        s = ctx.store
        docs = [d for d in s.records("document") if d.get("produced_by") == self.name and d.get("status") != "cancelled"]
        clauses = defaultdict(list)
        for c in s.records("spec_clause"):
            if c.get("status") != "superseded":
                clauses[c["document"]].append(c)
        files = []
        for d in sorted(docs, key=lambda x: x["id"]):
            if not clauses.get(d["id"]):
                ctx.warnings.append(f"{d['id']}: no spec_clause records - not generated")
                continue
            out = self._spec(ctx, d, sorted(clauses[d["id"]], key=lambda c: (c["section"], c["seq"])))
            files.append(out)
            if ctx.options.get("pdf", "yes") != "no":
                pdf = pdf_from_office(out, ctx)
                if pdf:
                    files.append(pdf)
        return files

    def _spec(self, ctx, doc, cl):
        s = ctx.store
        no, mr_id = doc["id"], doc.get("mr")
        mr = s.get("mr", mr_id) or {} if mr_id else {}
        prj = ctx.project_record()
        refs = {r["id"]: r for r in s.records("reference")}
        by = defaultdict(list)
        for c in cl:
            by[c["section"]].append(c)
        d = docshell.word(ctx, no, self)

        def clause_block(items, number):
            data = [c for c in items if c.get("parameter")]
            text = [c for c in items if c.get("text")]
            n = 0
            for c in text:
                if c.get("heading"):
                    d.h(c["heading"], 3)
                n += 1
                d.p(c["text"], bold_lead=f"{number}.{n} ")
            if data:
                d.table(["Parameter", "Required value", "Unit", "Status", "Basis / remarks"],
                        [[c["parameter"], (f"{c['value']:,.10g}" if isinstance(c.get("value"), (int, float)) else "")
                          + (f" {c['value_text']}" if c.get("value_text") else ""), c.get("unit") or "",
                          c.get("status") or "", "; ".join(filter(None, [", ".join(c.get("basis_refs") or []),
                                                                         c.get("remarks")]))]
                         for c in data], [5.0, 3.6, 1.6, 1.8, 5.4], size=7)

        # 1 general and scope
        d.h("1. General")
        d.p(f"This specification defines the minimum requirements for the design, manufacture, inspection, testing, "
            f"packing, delivery, documentation and site support of the equipment of procurement package {mr_id} "
            f"({mr.get('title', '')}) for {prj.get('name', '')}. The Supplier shall comply with this specification, "
            f"the datasheets listed in section 12 and the documents referenced herein. Deviations are permitted only "
            f"when listed in the Supplier's bid and accepted in writing by Istanbul EPC.")
        d.h("2. Scope of supply")
        eq = sorted((e for e in s.records("equipment") if e.get("mr") == mr_id and e.get("status") != "deleted"),
                    key=lambda e: e["id"])
        if eq:
            def rating(e):
                parts = []
                if e.get("capacity") is not None:
                    parts.append(f"{e['capacity']:,.10g} {e.get('capacity_unit') or ''}".strip())
                if e.get("design_flow") is not None:
                    parts.append(f"{e['design_flow']:,.10g} t/h")
                if e.get("head") is not None:
                    parts.append(f"{e['head']:,.10g} m")
                if e.get("rated_power") is not None:
                    parts.append(f"{e['rated_power']:,.10g} kW")
                if e.get("voltage"):
                    parts.append(f"{e['voltage'] / 1000:,.10g} kV" if e["voltage"] >= 1000 else f"{e['voltage']:,.0f} V")
                return ", ".join(parts)
            d.table(["Tag", "Description", "Service", "Qty", "Redundancy", "Rating"],
                    [[e["id"], e.get("description", ""), e.get("service") or "", e.get("quantity") or 1,
                      e.get("redundancy") or "", rating(e)] for e in eq], [2.8, 4.4, 3.8, 0.9, 1.8, 3.7], size=7)
        else:
            ctx.warnings.append(f"{no}: package {mr_id} has no equipment records")
        clause_block(by.get("scope", []), 2)
        # 3 codes
        d.h("3. Codes and standards")
        d.p("The latest editions valid at the date of the purchase order apply, together with the Turkish regulations. "
            "In case of conflict the order of precedence is: Turkish law and regulations, this specification and its "
            "datasheets, the codes and standards below, the Supplier's standards (Codes, Standards and Regulations "
            "Register ALP-EPC-00000-GE-LST-0001).")
        cited = sorted({r.split(":", 1)[1] for c in cl for r in c.get("basis_refs") or [] if r.startswith("reference:")})
        for c in cl:
            for r in c.get("basis_refs") or []:
                if r.startswith("reference:") and r.split(":", 1)[1] not in refs:
                    ctx.warnings.append(f"{no}: clause {c['id']} cites {r}, not in the register")
        if cited:
            d.table(["Code", "Title"], [[refs[r]["code"], refs[r]["title"]] for r in cited if r in refs], [4.0, 12.6], size=7)
        clause_block(by.get("codes", []), 3)
        # 4 site conditions
        d.h("4. Site and design conditions")
        dp = {p["parameter"]: p for p in s.records("design_parameter") if p.get("status") != "superseded"}
        rows = []
        for k in SITE_PARAMS:
            p = dp.get(k)
            if p:
                v = p.get("value")
                txt = (f"{v:,.10g}" if isinstance(v, (int, float)) else "") or p.get("value_text") or ""
                rows.append([k, f"{txt} {p.get('unit') or ''}".strip(), p.get("condition") or ""])
        d.p(f"Outdoor installation equipment shall be designed for the following site conditions (Plant Design Basis "
            f"Report ALP-EPC-00000-GE-DBR-0001); marine, salt-laden atmosphere, corrosivity category C5.")
        d.table(["Condition", "Value", "Remarks"], rows, [6.5, 4.0, 6.1], size=7)
        # 5-.. clause sections
        n = 5
        for key, title in SECTIONS:
            items = by.get(key, [])
            if key == "testing":
                d.h(f"{n}. {title}")
                itps = [x for x in s.records("document") if x.get("mr") == mr_id and x.get("type_code") == "ITP"
                        and x.get("originator", "EPC") == "EPC" and x.get("status") != "cancelled"]
                if itps:
                    d.p(f"Inspection and tests per the inspection and test plan {', '.join(x['id'] for x in itps)}; "
                        f"hold and witness points of Istanbul EPC and the Owner as marked in the ITP. The Supplier's "
                        f"detailed ITP is submitted for approval within the time stated in section {n + 1}.")
                clause_block(items, n)
                n += 1
                continue
            if key == "documentation":
                d.h(f"{n}. {title}")
                self._vdrl(d, s, mr_id)
                clause_block(items, n)
                n += 1
                continue
            if not items:
                continue
            d.h(f"{n}. {title}")
            clause_block(items, n)
            n += 1
        # attachments
        d.h(f"{n}. Attachments")
        dsh = sorted(x["id"] + " " + x["title"] for x in s.records("document") if x.get("mr") == mr_id
                     and x.get("type_code") == "DSH" and x.get("originator", "EPC") == "EPC" and x.get("status") != "cancelled")
        d.bullets(dsh or ["No datasheets: the requirements are fully stated in this specification."])
        out = ctx.out_dir / f"{no}.docx"
        return d.save(out)

    def _vdrl(self, d, s, mr_id):
        types = {t["id"]: t for t in s.records("doc_type")}
        sup = sorted((x for x in s.records("document") if x.get("mr") == mr_id and x.get("originator", "EPC") != "EPC"
                      and x.get("status") != "cancelled"), key=lambda x: (x.get("po_weeks_ifr") is not None and x["po_weeks_ifr"] < 0,
                                                                          x.get("po_weeks_ifr") or 0, x["id"]))
        if not sup:
            d.p("Supplier documents per the VDRL agreed with the purchase order.")
            return

        def when(w):
            if w is None:
                return "-"
            return f"PO + {w:g} wk" if w >= 0 else f"shipment - {-w:g} wk"
        d.p("The Supplier shall submit the following documents (vendor document requirements list, part of the master "
            "document list; numbers allocated by Istanbul EPC). Weeks after the PO are for design documents, weeks "
            "before shipment for test, erection and O&M documents. Review class: approval = Istanbul EPC and Owner "
            "approval before manufacture; review = comments incorporated; information = no review.")
        d.table(["Document number", "Title", "Review", "First issue", "Final"],
                [[x["id"], x["title"], x.get("review") or types.get(x.get("type_code"), {}).get("review", ""),
                  when(x.get("po_weeks_ifr")), when(x.get("po_weeks_final", x.get("po_weeks_ifr")))] for x in sup],
                [4.4, 6.8, 1.8, 1.8, 1.8], size=7)


ENGINE = Specifications()
