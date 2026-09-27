"""Contract document (.docx + .pdf) rendered from the contract records.

Part I Contract Agreement and Part II Conditions come from contract_clause records; the appendices come from
requirement (A), guarantee (B), milestone (C, amounts computed from the Contract Price), scope_item (D),
design_parameter (E), party (F) and the contractual key-date activities (G, WBS <project>.KD).
Options: contract=<id> (default: the only contract).
"""
from __future__ import annotations

import re

from ..core.runner import Context, Engine, pdf_from_office

APPENDICES = [("A", "Employer's Requirements (technical)"), ("B", "Performance Guarantees and Liquidated Damages"),
              ("C", "Schedule of Payments"), ("D", "Scope of Works Split and Terminal Points"),
              ("E", "Site and Design Data"), ("F", "Parties and Addresses for Notices"), ("G", "Key Dates"),
              ("H", "Owner-provided Documents"), ("I", "Agreed Clarifications")]


def clause_key(num: str):
    m = re.match(r"^([A-Z]?)(.*)$", num)
    return (m.group(1) != "", m.group(1), [int(x) for x in m.group(2).split(".")])


def eur(v) -> str:
    return f"EUR {v:,.0f}"


class ContractDocument(Engine):
    name = "contract_document"
    title = "Contract document (Word + PDF): agreement, conditions, appendices A-G from the database"
    version = "1.1.0"
    inputs = ["contract", "contract_clause", "party", "requirement", "guarantee", "milestone", "scope_item",
              "design_parameter", "activity", "wbs", "project", "tie_in", "source", "clarification"]
    formats = ["docx", "pdf"]

    def run(self, ctx: Context):
        from docx import Document
        from docx.enum.section import WD_ORIENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
        from docx.shared import Cm, Pt, RGBColor

        s = ctx.store
        contracts = s.records("contract")
        if not contracts:
            ctx.warnings.append("no contract records - nothing generated")
            return []
        cid = ctx.options.get("contract") or (contracts[0]["id"] if len(contracts) == 1 else None)
        if not cid or not s.get("contract", cid):
            raise ValueError("give --option contract=<id> (none or several contracts in the database)")
        k = s.get("contract", cid)
        parties = {p["id"]: p for p in s.records("party")}
        base = ctx.template("docx", "datasheet_base.docx")
        doc = Document(str(base)) if base.exists() else Document()
        for p in list(doc.paragraphs):
            p._element.getparent().remove(p._element)
        self.doc = doc
        st = doc.styles
        st["Normal"].font.size = Pt(10)
        for sec in doc.sections:
            prj_name = ctx.project_record().get("name", "")
            self._set(sec.header.paragraphs[0], f"Contract {cid}  |  {prj_name}  |  EPC Contract  |  CASE STUDY - fictional")
            self._set(sec.footer.paragraphs[0], f"{self.name} v{self.version} | data {ctx.stamp['inputs_hash']} | "
                                                 f"generated {ctx.stamp['generated_at'][:10]} by {ctx.stamp['generated_by']} | page ")
            self._page_field(sec.footer.paragraphs[0])

        # ------------------------------------------------------------- cover
        for _ in range(4):
            doc.add_paragraph()
        t = doc.add_paragraph()
        t.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = t.add_run(k["title"])
        r.bold, r.font.size, r.font.color.rgb = True, Pt(20), RGBColor(0x1F, 0x38, 0x64)
        c = doc.add_paragraph(f"Contract No. {cid}")
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph()
        owner = parties[k["owner"]]
        members = [parties[x] for x in k["contractor_parties"]]
        for line in ["between", owner["name"], "(the Owner)", "and", "the Consortium of",
                     *[f"{m['name']}{' (Leader)' if m['id'] == k.get('leader') else ''}" for m in members],
                     "(jointly and severally, the Contractor)"]:
            p = doc.add_paragraph(line)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if line in (owner["name"], *[m["name"] for m in members]) or line.endswith("(Leader)"):
                p.runs[0].bold = True
        doc.add_paragraph()
        info = doc.add_table(rows=0, cols=2)
        info.style = "Table Grid"
        for a, b in (("Form", k.get("form", "")), ("Contract Price", f"{eur(k['price'])} (lump sum, fixed)"),
                     ("Price basis", k.get("price_history", "-")),
                     ("Date of signature", k.get("signature_date", "-")), ("Notice to Proceed", k.get("ntp_date", "-")),
                     ("Time for Completion", f"{k.get('time_for_completion', '-')} days from NTP"),
                     ("Governing law", k.get("governing_law", "")), ("Status", k.get("status", ""))):
            row = info.add_row().cells
            row[0].text, row[1].text = a, str(b)
            row[0].paragraphs[0].runs[0].bold = True
        self._widths(info, (Cm(4.5), Cm(12)))
        if k.get("case_note"):
            doc.add_paragraph()
            n = doc.add_paragraph(k["case_note"])
            n.runs[0].italic = True
            n.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

        clauses = sorted((x for x in s.records("contract_clause") if x["contract"] == cid), key=lambda x: clause_key(x["number"]))
        # ------------------------------------------------------------- contents
        doc.add_heading("Contents", level=1)
        doc.add_paragraph("Part I - Contract Agreement", style="List Bullet")
        doc.add_paragraph("Part II - Conditions of Contract", style="List Bullet")
        for x in clauses:
            if x["part"] == "conditions" and "." not in x["number"]:
                doc.add_paragraph(f"Clause {x['number']}  {x['title']}", style="List Bullet 2")
        for code, title in APPENDICES:
            doc.add_paragraph(f"Appendix {code} - {title}", style="List Bullet")
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

        # ------------------------------------------------------------- Part I and II
        doc.add_heading("Part I - Contract Agreement", level=1)
        for x in clauses:
            if x["part"] == "agreement":
                if x["number"] == "A7":             # signature page: attestation clause + signature block together
                    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
                doc.add_heading(f"Article {x['number']}  {x['title']}", level=2)
                self._text(x.get("text", ""))
        for p in self.doc.paragraphs[-3:]:
            p.paragraph_format.keep_with_next = True
        self._signatures(owner, members, k)
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        doc.add_heading("Part II - Conditions of Contract", level=1)
        for x in clauses:
            if x["part"] not in ("conditions", "particular"):
                continue
            if "." not in x["number"]:
                doc.add_heading(f"{x['number']}  {x['title']}", level=2)
            else:
                h = doc.add_paragraph()
                r = h.add_run(f"{x['number']}  {x['title']}")
                r.bold = True
                h.paragraph_format.space_before = Pt(6)
                h.paragraph_format.keep_with_next = True
            if x.get("text"):
                self._text(x["text"])

        # ------------------------------------------------------------- Appendix A
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        doc.add_heading("Appendix A - Employer's Requirements (technical)", level=1)
        doc.add_paragraph("The requirements below are mandatory (\"shall\"). Each states its verification method and, where "
                          "applicable, the acceptance criterion and the related guarantee in Appendix B.")
        reqs = sorted((r for r in s.records("requirement") if r["contract"] == cid and r.get("status") != "withdrawn"),
                      key=lambda r: r["id"])
        current = None
        for r in reqs:
            if r["section"] != current:
                current = r["section"]
                doc.add_heading(current, level=2)
            p = doc.add_paragraph()
            p.paragraph_format.keep_with_next = True
            p.paragraph_format.space_before = Pt(4)
            b = p.add_run(f"{r['id']}  {r['title']}")
            b.bold = True
            doc.add_paragraph(r["text"])
            meta = f"Discipline: {r['discipline']}  |  Verification: {r['verification']}"
            if r.get("acceptance"):
                meta += f"  |  Acceptance: {r['acceptance']}"
            if r.get("guarantee"):
                meta += f"  |  Guarantee: {r['guarantee']}"
            m = doc.add_paragraph(meta)
            m.runs[0].italic, m.runs[0].font.size = True, Pt(8)
            m.runs[0].font.color.rgb = RGBColor(0x59, 0x59, 0x59)

        # ------------------------------------------------------------- Appendix B (landscape)
        self._landscape(WD_ORIENT)
        doc.add_heading("Appendix B - Performance Guarantees and Liquidated Damages", level=1)
        gs = sorted((g for g in s.records("guarantee") if g["contract"] == cid), key=lambda g: g["id"])
        rows = []
        for g in gs:
            sign = ">=" if g["direction"] == "min" else "<="
            ld = f"{g['ld_rate']:,.0f} {g['ld_unit']}" if g.get("ld_rate") else (g.get("remedy") or "-")
            if g.get("ld_rate") and g.get("remedy"):
                ld += f". {g['remedy']}"
            rows.append([g["id"], g["parameter"], f"{sign} {g['guaranteed_value']:g} {g['unit']}", g["conditions"],
                         g.get("test_procedure", ""), ld,
                         f"{g['minimum_acceptance']:g} {g['unit']}" if g.get("minimum_acceptance") is not None else "-"])
        self._table(["ID", "Guarantee", "Value", "Conditions", "Test", "Liquidated damages / remedy", "Minimum acceptance"],
                    rows, (1.3, 4.0, 2.4, 6.0, 4.5, 5.2, 2.2))
        doc.add_paragraph("Caps: performance liquidated damages 15 % and aggregate liquidated damages 20 % of the Contract Price "
                          "(Sub-Clause 12.6). Delay damages per Sub-Clause 9.5.")

        # ------------------------------------------------------------- Appendix C
        doc.add_heading("Appendix C - Schedule of Payments", level=1)
        ms = sorted((m for m in s.records("milestone") if m["contract"] == cid), key=lambda m: m["id"])
        rows = [[m["id"], m["title"], m["trigger"], f"{m.get('planned_month', '-')}", f"{m['percent']:g} %",
                 eur(k["price"] * m["percent"] / 100), m.get("security", "")] for m in ms]
        total = sum(m["percent"] for m in ms)
        rows.append(["", "Total", "", "", f"{total:g} %", eur(k["price"] * total / 100), ""])
        self._table(["ID", "Milestone", "Payment trigger", "Planned month after NTP", "Share", "Amount", "Security"],
                    rows, (1.3, 5.0, 8.5, 2.2, 1.6, 3.5, 3.5))
        if abs(total - 100) > 1e-9:
            ctx.warnings.append(f"payment milestones add up to {total} %, not 100 %")
        doc.add_paragraph("Amounts are computed from the Contract Price; the advance is recovered pro rata from MS-02 to MS-10 "
                          "and 5 % retention applies to each milestone (Clause 15).")

        # ------------------------------------------------------------- Appendix D
        doc.add_heading("Appendix D - Scope of Works Split and Terminal Points", level=1)
        codes = sorted({v for x in s.records("scope_item") for v in (x.get("design"), x.get("supply"), x.get("install"), x.get("commission")) if v})
        doc.add_paragraph("Party codes: " + "; ".join(f"{c} = {parties[c]['name']}" for c in codes if c in parties))
        items = sorted((x for x in s.records("scope_item") if x["contract"] == cid), key=lambda x: x["id"])
        rows = [[x["id"], x["area"], x["item"], x.get("design", "-"), x.get("supply", "-"), x.get("install", "-"),
                 x.get("commission", "-"), x.get("terminal_point", "")] for x in items]
        self._table(["ID", "Area", "Item", "Design", "Supply", "Install", "Commission", "Terminal point"], rows,
                    (1.4, 2.6, 9.0, 1.5, 1.5, 1.5, 1.8, 6.3))

        tis = sorted((t for t in s.records("tie_in") if t["contract"] == cid), key=lambda t: t["id"])
        if tis:
            doc.add_heading("Tie-in register", level=2)
            rows = [[t["id"], t["service"], t["location_text"], t.get("size", ""), t.get("operating_conditions", ""),
                     t["owner_side"], t["contractor_side"], t.get("available_by", "-")] for t in tis]
            self._table(["ID", "Service", "Location", "Size", "Conditions", "Owner provides", "Contractor provides", "Available by"],
                        rows, (1.5, 3.0, 3.8, 2.4, 4.0, 5.0, 4.6, 2.0))

        # ------------------------------------------------------------- Appendix E
        doc.add_heading("Appendix E - Site and Design Data", level=1)
        dps = sorted((d for d in s.records("design_parameter") if d.get("status") != "superseded"),
                     key=lambda d: (d["category"], d["id"]))
        rows = [[d["category"].replace("_", " "), d["parameter"],
                 f"{d['value']:g}" if d.get("value") is not None else d.get("value_text", ""), d.get("unit", ""),
                 d.get("condition", ""), ", ".join(x.split(":", 1)[1] for x in d.get("basis_refs", []))] for d in dps]
        self._table(["Category", "Parameter", "Value", "Unit", "Condition", "Basis"], rows, (2.4, 7.5, 3.0, 2.4, 7.0, 3.0))

        # ------------------------------------------------------------- Appendix F, G
        doc.add_heading("Appendix F - Parties and Addresses for Notices", level=1)
        rows = [[p["id"], p["name"], p["role"].replace("_", " "), p.get("country", ""), p.get("representative", ""),
                 p.get("address", ""), "yes" if p.get("fictional", True) else "no"] for p in sorted(parties.values(), key=lambda p: p["id"])]
        self._table(["Code", "Name", "Role", "Country", "Representative", "Address", "Fictional"], rows,
                    (1.6, 6.0, 3.0, 2.0, 4.0, 6.0, 1.6))
        doc.add_heading("Appendix G - Key Dates", level=1)
        prj = ctx.project_record()
        kd = sorted((a for a in s.records("activity") if a["wbs"].endswith(".KD")), key=lambda a: (a.get("constraint_date", ""), a["id"]))
        rows = [[a["id"], a["title"], a.get("constraint_date", "-"),
                 "start no earlier than" if a.get("constraint") == "start_no_earlier_than" else "complete no later than"] for a in kd]
        self._table(["ID", "Key date", "Date", "Obligation"], rows, (2.0, 12.0, 3.5, 5.0))
        if not kd:
            ctx.warnings.append(f"no key-date activities under WBS {prj['id']}.KD")
        doc.add_paragraph("Key dates are contractual; the Contractor's Level 3 programme (Sub-Clause 9.3) shall be linked to them.")

        # ------------------------------------------------------------- Appendix H
        doc.add_heading("Appendix H - Owner-provided Documents", level=1)
        own = sorted((x for x in s.records("source") if "owner" in x.get("originator", "").lower()), key=lambda x: x.get("doc_ref", x["id"]))
        rows = [[x.get("doc_ref", x["id"]), x["title"], x.get("revision", ""), x.get("received_date", ""), x.get("file", "")] for x in own]
        self._table(["Document", "Title", "Rev", "Date", "File in the project repository"], rows, (3.8, 8.0, 1.2, 2.5, 10.0))
        doc.add_paragraph("The Owner's documents are part of the Contract to the extent stated in Article A3; the Contractor is "
                          "responsible for their interpretation (Sub-Clause 4.5).")

        # ------------------------------------------------------------- Appendix I
        doc.add_heading("Appendix I - Agreed Clarifications", level=1)
        tqs = sorted((q for q in s.records("clarification") if q["contract"] == cid), key=lambda q: q["id"])
        doc.add_paragraph("Technical queries raised by the Contractor and answered by the Owner before signature. Where an answer "
                          "modifies Appendix A or an Owner document, the answer prevails (Article A3). Records changed as a result are "
                          "listed; the changed requirements are already reflected in Appendix A.")
        rows = []
        for q in tqs:
            cost = eur(q["cost_impact"]) if q.get("cost_impact") else "-"
            follows = f" (follows {q['follows']})" if q.get("follows") else ""
            rows.append([q["id"], str(q["round"]), q["subject"] + follows, q["question"], q.get("response", "(open)"),
                         (q.get("outcome") or "-").replace("_", " "), cost, ", ".join(q.get("changed_records", []))])
        self._table(["TQ", "Round", "Subject", "Question", "Owner's answer", "Outcome", "Price", "Records changed"], rows,
                    (1.4, 1.1, 3.0, 6.8, 6.4, 2.0, 2.0, 3.1))
        open_q = [q["id"] for q in tqs if q.get("status") not in ("closed", "superseded")]
        if open_q:
            ctx.warnings.append(f"clarifications not closed: {', '.join(open_q)}")

        out = ctx.out_dir / f"{cid}_contract.docx"
        doc.save(out)
        files = [out]
        if ctx.options.get("pdf", "yes") != "no":
            pdf = pdf_from_office(out, ctx)
            if pdf:
                files.append(pdf)
        return files

    # ------------------------------------------------------------------ helpers
    def _text(self, text: str):
        for block in [b.strip() for b in text.split("\n\n") if b.strip()]:
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if all(l.startswith("- ") for l in lines):
                for l in lines:
                    self.doc.add_paragraph(l[2:], style="List Bullet")
            else:
                for l in lines:
                    if l.startswith("- "):
                        self.doc.add_paragraph(l[2:], style="List Bullet")
                    else:
                        self.doc.add_paragraph(l).paragraph_format.space_after = __import__("docx").shared.Pt(4)

    def _table(self, head, rows, widths_cm):
        from docx.shared import Cm, Pt, RGBColor
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        t = self.doc.add_table(rows=1, cols=len(head))
        t.style = "Table Grid"
        for c, h in zip(t.rows[0].cells, head):
            c.text = h
            run = c.paragraphs[0].runs[0]
            run.bold, run.font.size, run.font.color.rgb = True, Pt(8), RGBColor(0xFF, 0xFF, 0xFF)
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear"), shd.set(qn("w:color"), "auto"), shd.set(qn("w:fill"), "1F3864")
            c._element.get_or_add_tcPr().append(shd)
        trpr = t.rows[0]._tr.get_or_add_trPr()                       # repeat header row on each page
        rh = OxmlElement("w:tblHeader")
        rh.set(qn("w:val"), "true")
        trpr.append(rh)
        for r in rows:
            cells = t.add_row().cells
            for c, v in zip(cells, r):
                c.text = str(v)
                for p in c.paragraphs:
                    for run in p.runs:
                        run.font.size = Pt(8)
        self._widths(t, [Cm(w) for w in widths_cm])
        self.doc.add_paragraph()
        return t

    @staticmethod
    def _widths(table, widths):
        table.autofit = False
        for col, w in zip(table.columns, widths):
            col.width = w
        for row in table.rows:
            for cell, w in zip(row.cells, widths):
                cell.width = w

    def _landscape(self, WD_ORIENT):
        from docx.enum.section import WD_SECTION
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        sec.orientation = WD_ORIENT.LANDSCAPE
        if sec.page_width < sec.page_height:
            sec.page_width, sec.page_height = sec.page_height, sec.page_width

    def _signatures(self, owner, members, k):
        from docx.shared import Cm, Pt
        self.doc.add_paragraph()
        t = self.doc.add_table(rows=1, cols=1 + len(members))
        t.style = "Table Grid"
        heads = [f"For the Owner\n{owner['name']}"] + [f"For the Contractor ({'Leader' if m['id'] == k.get('leader') else 'Member'})\n{m['name']}"
                                                          for m in members]
        for c, h in zip(t.rows[0].cells, heads):
            c.text = h
            c.paragraphs[0].runs[0].bold = True
        for label in ("Name:", "Title:", "Signature:\n\n", "Date:"):
            for c in t.add_row().cells:
                c.text = label
                c.paragraphs[0].runs[0].font.size = Pt(9)
        self._widths(t, [Cm(16.5 / len(t.columns))] * len(t.columns))
        self._keep_together(t)

    @staticmethod
    def _keep_together(table):
        """Rows never split and every row keeps with the next one, so the block moves to the next page whole."""
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        for i, row in enumerate(table.rows):
            trpr = row._tr.get_or_add_trPr()
            cs = OxmlElement("w:cantSplit")
            cs.set(qn("w:val"), "true")
            trpr.append(cs)
            if i < len(table.rows) - 1:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        p.paragraph_format.keep_with_next = True

    @staticmethod
    def _set(paragraph, text):
        runs = paragraph.runs
        if runs:
            runs[0].text = text
            for r in runs[1:]:
                r._element.getparent().remove(r._element)
        else:
            paragraph.text = text

    @staticmethod
    def _page_field(paragraph):
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        run = paragraph.add_run()
        if paragraph.runs and paragraph.runs[0].font.size:
            run.font.size = paragraph.runs[0].font.size
        for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
            if kind:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), kind)
            else:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = text
            run._r.append(el)


ENGINE = ContractDocument()
