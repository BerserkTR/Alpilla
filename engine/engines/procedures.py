"""Engineering procedures and plans generated from the database (Word + PDF):

  ALP-EPC-00000-GE-PRC-0001  KKS identification manual       - key list, unit numbering, systems, plant asset tags
  ALP-EPC-00000-GE-PRC-0002  Document numbering and control   - number format, codes, document types, review rules,
                                                                    release control and process gates
  ALP-EPC-00000-GE-PLN-0001  Engineering execution plan       - scope, workflow rules, input network, timeline
  ALP-EPC-00000-GE-PLN-0002  AWP execution plan               - CWA / CWP / EWP / PWP / IWP, release rules, dates

The rules are those the engines apply (engine/core/kks.py, engine/core/workflow.py), the tables come from the records
(kks_key, system, equipment, doc_type, document, cwa, cwp, ewp, mr, clarification, decision), the dates and floats from the
workflow timeline and the CPM. Each output carries its MDL number; the checks of the engineering_plan engine are repeated
in the relevant document. Options: pdf=no."""
from __future__ import annotations

from collections import Counter, defaultdict

from ..core import kks, workflow
from ..core.runner import Context, Engine, pdf_from_office
from ..core.wordkit import Doc
from .engineering_plan import check_engineering

DOCS = {"kks": "ALP-EPC-00000-GE-PRC-0001", "numbering": "ALP-EPC-00000-GE-PRC-0002",
        "eep": "ALP-EPC-00000-GE-PLN-0001", "awp": "ALP-EPC-00000-GE-PLN-0002"}
PURPOSES = [("IFR", "Issued for review / first issue", "A, B, C ..."),
            ("IFA", "Issued for approval (approval class, after the Owner's comments are incorporated)", "A, B, C ..."),
            ("IFD", "Issued for design (released internally for dependent design, e.g. vendor data frozen)", "A, B, C ..."),
            ("IFP", "Issued for purchase (requisitions, specifications, datasheets)", "A, B, C ..."),
            ("IFC", "Issued for construction / final", "0, 1, 2 ..."),
            ("IFI", "Issued for information (information class, supplier documents received)", "A, B, C ... or supplier rev."),
            ("AB", "As built", "next number"),
            ("VOID", "Cancelled; the number is never reused", "-")]
REVIEW_CODES = [("1", "No comments - proceed (approval: approved)"), ("2", "Proceed with the comments incorporated; re-issue"),
                ("3", "Do not proceed; revise and re-submit"), ("4", "For information / reference only; no review")]
REVIEW_CLASS = {"approval": "Owner approval: IFR -> Owner review -> update -> IFA -> approval code 1 -> IFC",
                "review": "Owner review: IFR -> Owner review -> update -> IFC",
                "information": "sent to the Owner for information: IFR -> update -> IFC (no review period)",
                "internal": "consortium internal, not transmitted for review"}


def _short(parties, pid):
    return parties.get(pid, {}).get("short_name") or pid


class Procedures(Engine):
    name = "procedures"
    title = "Engineering procedures: KKS manual, document numbering and control, engineering and AWP execution plans (Word + PDF)"
    version = "1.4.0"
    inputs = ["project", "document", "document_revision", "doc_type", "kks_key", "system", "equipment", "cwa", "cwp", "ewp",
              "mr", "activity", "wbs", "requirement", "scope_item", "party", "eng_resource", "clarification", "decision",
              "mdl_rule", "mdl_benchmark", "instrument", "line", "gate_rule", "milestone"]
    formats = ["docx", "pdf"]
    code_deps = ["engine/core/wordkit.py", "engine/core/workflow.py", "engine/core/kks.py", "engine/core/planning.py",
                 "engine/core/mdl.py", "engine/core/release.py",
                 "engine/engines/engineering_plan.py", "templates/docx/datasheet_base.docx"]

    def run(self, ctx: Context):
        s = ctx.store
        if not s.records("doc_type") or not s.records("kks_key"):
            ctx.warnings.append("no doc_type / kks_key records - nothing generated")
            return []
        self.ctx = ctx
        self.res = workflow.compute(s)
        self.checks = check_engineering(s, self.res)
        self.parties = {p["id"]: p for p in s.records("party")}
        self.tqs = {q["id"]: q for q in s.records("clarification")}
        self.decisions = [x for x in s.records("decision") if x.get("status") != "superseded"]
        self.mdl = {d["id"]: d for d in s.records("document")}
        revs = defaultdict(list)
        for r in s.records("document_revision"):
            revs[r["document"]].append(r)
        self.revs = revs
        files = []
        for key, fn in (("kks", self._kks), ("numbering", self._numbering), ("eep", self._eep), ("awp", self._awp)):
            no = DOCS[key]
            if no not in self.mdl:
                ctx.warnings.append(f"{no} is not in the MDL - generated without MDL data")
            d = self._start(no, landscape=key == "awp")
            fn(d)
            out = d.save(ctx.out_dir / f"{no}.docx")
            files.append(out)
            if ctx.options.get("pdf", "yes") != "no":
                pdf = pdf_from_office(out, ctx)
                if pdf:
                    files.append(pdf)
        return files

    # ------------------------------------------------------------------ common parts
    def _start(self, no, landscape=False):
        ctx = self.ctx
        rec = self.mdl.get(no, {"title": no})
        proj = ctx.project_record()
        d = Doc(ctx.template("docx", "datasheet_base.docx"), f"{proj.get('name', '')} | {no}",
                f"engine {self.name} v{self.version} | data {ctx.stamp['inputs_hash']} | generated "
                f"{ctx.stamp['generated_at'][:10]} - generated from the project database; do not edit", landscape=landscape)
        d.title(f"{proj.get('name', '')}\n{rec['title']}")
        issued = sorted(self.revs.get(no, []), key=lambda r: r["issue_date"])
        rev = f"{issued[-1]['revision']} ({issued[-1]['purpose']} {issued[-1]['issue_date']})" if issued else \
            "draft - not yet issued (next issue: IFR rev A)"
        t = self.res.docs.get(no)
        plan = (f"IFR {self.res.d(t.ifr)}" + (f", IFA {self.res.d(t.ifa)}" if t.ifa is not None else "")
                + f", IFC {self.res.d(t.ifc)}") if t else "-"
        dt = ctx.store.get("doc_type", rec.get("type_code") or "") or {}
        rows = [("Document number", no)] + ([("Description", rec["description"])] if rec.get("description") else []) + [
                ("Revision", rev), ("Originator", _short(self.parties, "IEPC")),
                ("Review class", f"{rec.get('review') or dt.get('review') or '-'}" + (" (Basic Design Package)" if rec.get("bdp") else "")),
                ("Planned issue (workflow timeline)", plan),
                ("Basis", ", ".join(rec.get("basis_refs") or []) or "-")]
        tb = d.table(None, [list(r) for r in rows], [5.0, d.width_cm - 5.0], size=8)
        for r in tb.rows:
            r.cells[0].paragraphs[0].runs[0].bold = True
        return d

    def _tq_line(self, tq):
        q = self.tqs.get(tq)
        if not q:
            return f"{tq}: not found"
        if not q.get("response"):
            return f"{tq} (open, raised {q.get('raised_date') or '-'}): {q.get('subject') or q.get('question', '')}"
        return (f"{tq} ({q.get('status')}, answered {q.get('response_date') or '-'} by "
                f"{_short(self.parties, q.get('responded_by'))}): {q.get('response') or '(no response)'}")

    def _checks(self, d, kinds, title="Check results (engine)"):
        rows = [[a, b, c, t] for a, b, c, t in self.checks if b in kinds and (c != "OK" or a == "-")]
        d.h(title, 1)
        cnt = Counter(c for _, b, c, _ in self.checks if b in kinds)
        d.p(f"{cnt.get('OK', 0)} OK, {cnt.get('INFO', 0)} INFO, {cnt.get('WARN', 0)} WARN "
            f"(checks: {', '.join(sorted(kinds))}). WARN must be resolved before the next issue; INFO is noted.")
        if rows:
            d.table(["Item", "Check", "Result", "Detail"], rows[:120], [3.2, 2.8, 1.4, d.width_cm - 7.4])
            if len(rows) > 120:
                d.p(f"... {len(rows) - 120} more rows in the MDL workbook (sheet Checks).")

    # ------------------------------------------------------------------ PRC-0001 KKS manual
    def _kks(self, d):
        s = self.ctx.store
        kk = kks.keys(s)
        req = s.get("requirement", "ER-01.06") or {}
        d.h("1. Purpose, scope and basis")
        d.p("This manual sets the plant identification of the project: systems, equipment, components, structures and the "
            "KKS part of every document number. It applies to the consortium members (Istanbul EPC, Imaginary Electric), "
            "their subsuppliers and subcontractors, for engineering, the 3D model, the engineering database, procurement, "
            "construction (AWP), commissioning and handover.")
        d.p(req.get("text", "-"), bold_lead="ER-01.06: ")
        d.p("The identification follows VGB-S-811 (KKS) with the project key list of section 4. Agreement: ")
        d.bullets([self._tq_line("TQ-035"), self._tq_line("TQ-IEC-023")])
        for x in self.decisions:
            if "KKS" in x.get("title", ""):
                d.p(f"{x['decision']} ({x['id']}, {x.get('status')}, {x.get('decided_by')})", bold_lead="Decision: ")

        d.h("2. Code structure")
        d.p("Codes are written without separators in the database and on documents (e.g. 10MBA10AA001). Data character "
            "types: A = letter, N = digit.")
        d.table(["Level", "Breakdown", "Format", "Meaning", "Example"], [
            ["0", "G", "N", "Plant unit (project numbering, table below)", "1"],
            ["1", "F0", "N", "System prefix number (0 on this project)", "0"],
            ["1", "F1 F2 F3", "AAA", "Function / system key (key list, section 4.1); U = structures", "MBA"],
            ["1", "FN FN", "NN", "System number: 10, 20, ... parallel trains; units 11, 12 ... subdivisions", "10"],
            ["2", "A1 A2", "AA", "Equipment unit key (section 4.2)", "AP"],
            ["2", "AN AN AN", "NNN", "Equipment unit number: 001, 002 ... in flow direction", "001"],
            ["3", "B1 B2", "AA", "Component key (section 4.3)", "KP"],
            ["3", "BN BN", "NN", "Component number", "01"]], [1.2, 2.2, 1.6, 8.8, 2.6])
        d.table(["Unit (G)", "Plant unit"], [[k, v] for k, v in kks.UNITS.items()], [2.5, d.width_cm - 2.5])
        d.p("A system record is identified by G F0 F1F2F3 (e.g. 10MBA) or its group G F0 F1F2 (e.g. 10MB); the system "
            "number FN is part of equipment tags only. Examples from the plant asset register:")
        eqs = sorted(s.records("equipment"), key=lambda e: e["id"])
        ex = [e for e in eqs if len(e["id"]) >= 12][:3] + [e for e in eqs if len(e["id"]) == 7][:2]
        rows = [[e["id"], "; ".join(kks.explain(e["id"], kk)) + f" - {e.get('description', '')}"] for e in ex]
        pump = next((e["id"] for e in eqs if len(e["id"]) == 12 and e["id"][7:9] == "AP"), None)
        if pump and "KP" in kk["B"]:
            rows.append([pump + "KP01", "; ".join(kks.explain(pump + "KP01", kk)) + " - component level (illustration)"])
        d.table(["Tag", "Breakdown"], rows, [3.2, d.width_cm - 3.2])

        d.h("3. Tagging rules")
        d.bullets([
            "Every system, item of equipment, instrument, electrical consumer, cable and structure receives a KKS code before "
            "it appears on a document; the code is created in the database first (engine CLI) and never typed on a drawing "
            "without a record.",
            "Unit 0 is used for common / balance-of-plant systems, 1 for the GT + HRSG island, 2 for the ST island; the unit "
            "of a system follows the train it serves, not its location.",
            "System numbers FN: 10 for the first train of a system, 20, 30 ... for parallel trains; 11, 12 ... for "
            "subdivisions of train 10. Equipment unit numbers AN: 001, 002 ... in flow direction; parallel units in the "
            "same system are numbered consecutively (e.g. pumps AP001 / AP002 for 2 x 100 %).",
            "Components (level B, e.g. motors KP / MA) carry the tag of their equipment unit plus B1B2 BN BN.",
            "Structures and buildings use the U function keys (section 4.1) with unit and system number, e.g. 10UMA.",
            "Measuring circuits and electrical equipment units use the A-keys of section 4.2; instrument tags follow the "
            "same level-2 structure (e.g. 10LAB10CP001).",
            "Supplier-internal part numbers are kept as vendor attributes below component level and never replace the KKS "
            "code (TQ-IEC-023).",
            "A code is never reused for a different item; deleted items keep their code void in the change log.",
            "Every tagged record carries its AVEVA class (ER-01.06) so the tag data can be exported to the Owner's "
            "engineering database (engine aveva_export)."])

        d.h("4. Project key list")
        d.p(f"{sum(len(v) for v in kk.values())} keys. 'Verified' means the key title has been checked against the licensed "
            f"VGB-S-811 key catalogue by the Owner's Engineer (TQ-035); the key list itself is agreed for use.")
        for lvl, head in (("F", "4.1 Function keys (F1F2F3)"), ("A", "4.2 Equipment unit keys (A1A2)"),
                          ("B", "4.3 Component keys (B1B2)")):
            d.h(head, 2)
            rows = [[k, v.get("main_group", ""), v.get("title", ""), v.get("status", ""), "yes" if v.get("verified") else "no",
                     ", ".join(v.get("agreed_refs") or [])] for k, v in sorted(kk[lvl].items())]
            d.table(["Key", "Main group", "Title", "Status", "Verified", "Agreed in"], rows, [1.3, 3.2, 7.4, 1.6, 1.4, 2.5],
                    size=7)

        d.h("5. System register")
        systems = sorted(s.records("system"), key=lambda x: x["id"])
        d.p(f"{len(systems)} systems and groups. Scope = party responsible for the design of the system.")
        d.table(["Code", "Title", "Category", "Scope", "Parent", "AVEVA class"],
                [[x["id"], x.get("title", ""), (x.get("category") or "").replace("_", " "), x.get("scope") or "-",
                  x.get("parent") or "-", x.get("aveva_class") or "-"] for x in systems], [1.6, 7.3, 2.4, 1.4, 1.5, 3.2],
                size=7)

        d.h("6. Plant asset register (equipment tags)")
        d.p(f"{len(eqs)} equipment items. CWA / CWP / MR assign each asset to its construction area, construction package "
            f"and procurement package (AWP, ALP-EPC-00000-GE-PLN-0002).")
        d.table(["Tag", "Description", "AVEVA class", "Supply", "CWA", "CWP", "MR"],
                [[e["id"], e.get("description", ""), e.get("aveva_class") or "-", e.get("supply") or "-", e.get("cwa") or "-",
                  e.get("cwp") or "-", e.get("mr") or "-"] for e in eqs], [2.4, 5.4, 2.8, 1.1, 1.4, 2.2, 1.9], size=7)

        d.h("7. Tools and control")
        d.bullets([
            "Check or explain a code: python -m engine kks <tag | system | document number>.",
            "Create tags only via python -m engine db add equipment ... --reason (classify with --set aveva_class=...).",
            "The engineering_plan engine checks every system code and equipment tag against the key list at each run; "
            "findings are listed below and in the MDL workbook.",
            "Changes to the key list: new key record (status proposed) -> Owner agreement by TQ -> status agreed."])
        self._checks(d, {"KKS system", "KKS tag", "KKS key list", "AVEVA class"})

    # ------------------------------------------------------------------ PRC-0002 numbering and document control
    def _numbering(self, d):
        s = self.ctx.store
        types = sorted(s.records("doc_type"), key=lambda t: t["id"])
        docs = [x for x in self.mdl.values() if x.get("status") != "cancelled"]
        req = s.get("requirement", "ER-17.01") or {}
        d.h("1. Purpose, scope and basis")
        d.p("This procedure sets the numbering of all project documents (consortium, Imaginary Electric, subsuppliers), the "
            "document types and their review class, revisions and purposes, the review cycle with the Owner and the "
            "maintenance of the master document list (MDL).")
        d.p(req.get("text", "-"), bold_lead="ER-17.01: ")
        d.bullets([self._tq_line("TQ-035"), self._tq_line("TQ-IEC-023")])

        d.h("2. Document number")
        d.p("ALP-<ORG>-<KKS>-<DISC>-<TYPE>-<NNNN>", bold_lead="Format: ")
        ex = next((x["id"] for x in sorted(docs, key=lambda x: x["id"]) if x.get("system")), None)
        d.table(["Field", "Format", "Meaning"], [
            ["ALP", "fixed", "Project code"],
            ["ORG", "3 characters", "Originator (section 3)"],
            ["KKS", "NNAAA / 00000", "KKS system G F0 F1F2F3 of the main system the document belongs to "
                                     "(ALP-EPC-00000-GE-PRC-0001); 00000 for plant-general documents"],
            ["DISC", "2 letters", "Discipline (section 3)"],
            ["TYPE", "3 characters", "Document type (section 4); defines the IEC 61355 class and the workflow rules"],
            ["NNNN", "4 digits", "Running number per ORG-KKS-DISC-TYPE, from 0001; never reused"]], [2.0, 3.0, d.width_cm - 5.0])
        if ex:
            d.p("; ".join(kks.explain(ex, kks.keys(s))), bold_lead=f"Example {ex}: ")
        d.p("Sheets of a multi-sheet drawing share the number (sheet count in the MDL); a supplier's own number is recorded "
            "as vendor reference and shown as a secondary number in the title block (TQ-IEC-023).")

        d.h("3. Originator and discipline codes")
        d.table(["ORG", "Originator"], [[k, v] for k, v in kks.ORGS.items()]
                + [["xxx", "Subsupplier: 3-character code allocated by Istanbul EPC with the purchase order"]], [2.0, d.width_cm - 2.0])
        d.table(["DISC", "Discipline"], [[k, "instrumentation and control" if v == "i_and_c" else v.replace("_", " ")]
                                         for k, v in kks.DISCIPLINES.items()], [2.0, d.width_cm - 2.0])

        d.h("4. Document types and workflow rules")
        d.p("Prep = working days from inputs ready to first issue (longer for multi-sheet documents, at most double); "
            "Update = working days to incorporate comments; Inputs at = maturity the inputs must have reached (IFR or IFC); "
            "C = construction document (belongs to an EWP), P = procurement document (belongs to an MR).")
        d.p("Share = AWP progressive release: a construction document of this type is needed at CWP start - lead + share x "
            "CWP duration (0 = at the CWP start).")
        d.table(["Type", "Title", "IEC 61355", "Review class", "Prep", "Upd.", "Inputs at", "Typical inputs", "C/P", "Share"],
                [[t["id"], t.get("title", ""), t.get("dcc") or "-", t.get("review", ""), t.get("prep_days"), t.get("update_days"),
                  t.get("input_maturity"), ", ".join(t.get("input_types") or []) or "-",
                  ("C" if t.get("construction") else "") + ("P" if t.get("procurement") else ""),
                  t.get("progressive_share") if t.get("progressive_share") else ""] for t in types],
                [1.0, 4.0, 1.3, 1.9, 1.0, 1.0, 1.2, 3.5, 0.9, 1.0], size=7)

        d.h("5. Number allocation")
        d.bullets([
            "Numbers are allocated only in the database: python -m engine kks --next <ORG> <KKS> <DISC> <TYPE> gives the next "
            "free number; the document is registered with python -m engine db add document ... --reason.",
            "Every document record carries type_code, discipline, originator and system consistent with its number; the "
            "engineering_plan engine checks all numbers at every run.",
            "A cancelled document keeps its number (status cancelled, purpose VOID); numbers are never reused."])

        d.h("6. Revisions and issue purposes")
        d.table(["Purpose", "Meaning", "Revision"], [list(p) for p in PURPOSES], [1.6, d.width_cm - 5.6, 4.0])
        d.p("Each issue is a document_revision record (revision, purpose, date, prepared / checked / approved by, file); "
            "packages are transmitted with python -m engine deliver (frozen copy and transmittal).")

        d.h("7. Review and approval")
        d.table(["Class", "Cycle"], [[k, v] for k, v in REVIEW_CLASS.items()], [2.4, d.width_cm - 2.4])
        d.p(f"Owner review period: {workflow.OWNER_REVIEW} working days (14 calendar days, ER-17.01), "
            f"{workflow.OWNER_REVIEW_BDP} working days (21 calendar days) for Basic Design Package documents; after approval "
            f"code 1 the IFC follows within {workflow.APPROVAL_CODE} working days. Review codes:")
        d.table(["Code", "Meaning"], [list(c) for c in REVIEW_CODES], [1.6, d.width_cm - 1.6])
        d.p("Comments are recorded as review_comment records against the revision (comment -> response -> closed in the "
            "revision that incorporates it). The review class of a document type may be overridden per document (review "
            "field of the MDL line).")

        d.h("8. Supplier documents")
        d.bullets([
            "Imaginary Electric and subsuppliers submit per their VDRL, which is part of the MDL (originator IEC / subsupplier "
            "code) with committed first-issue and final dates.",
            "Supplier documents are numbered by Istanbul EPC before the purchase order, carry the project number as the "
            "primary number and are reviewed by Istanbul EPC before transmittal to the Owner where the class requires it.",
            "Received files are registered as source records (sources/) and linked to the MDL line (source field) with an "
            "IFR / IFI revision."])

        d.h("9. Master document list")
        by_org = Counter(x.get("originator") for x in docs)
        by_disc = Counter(x.get("discipline") for x in docs)
        d.p(f"The MDL is generated by the engineering_plan engine from the document records ({len(docs)} documents: "
            + ", ".join(f"{k} {v}" for k, v in sorted(by_org.items())) + f"; {sum(1 for x in docs if x.get('bdp'))} in the "
            f"Basic Design Package). It is updated with every change of the records and issued monthly with the progress "
            f"report (TQ-035).")
        d.table(["Discipline", "Documents", "Hours", "Sheets"],
                [[k.replace("_", " "), v, f"{sum(x.get('weight') or 0 for x in docs if x.get('discipline') == k):,.0f}",
                  sum(x.get("sheets") or 1 for x in docs if x.get("discipline") == k)] for k, v in sorted(by_disc.items())],
                [5.0, 3.0, 3.0, 3.0])
        self._release(d)
        self._checks(d, {"numbering"})

    def _release(self, d):
        """Section 10: release control and process gates (engine/core/release.py, gate_rule records)."""
        s = self.ctx.store
        res = self.res
        d.h("10. Release control and process gates")
        d.p("A document is released in the order of its input network and only at the maturity its inputs allow; the "
            "processes that use the documents (procurement, Owner acceptance, construction, commissioning / acceptance, "
            "operations) start only through gates that name the documents and statuses they need. The rules below are "
            "applied by the engine: python -m engine doc status <document> shows the next purpose and revision and what "
            "blocks it; python -m engine doc issue <document> --purpose <purpose> refuses a blocked release (an --override is "
            "recorded on the revision); python -m engine gate lists the gates. The release_control engine issues the "
            "release plan, the relations, the impacts and the gate status (Excel).")
        d.table(["Status", "Reached when"], [
            ["IFR", "first issue (also IFI / IFD / IFP)"],
            ["IFA", "issued for approval (approval class)"],
            ["ACCEPTED", "review code 1 or 2 on the latest issue; information and internal EPC documents when issued; supplier "
                         "documents when accepted by Istanbul EPC"],
            ["IFC", "issued for construction / final (certified for supplier documents)"],
            ["AB", "as built"]], [2.4, d.width_cm - 2.4])
        d.table(["Release", "Condition"], [
            ["IFR / IFA", "every input at least at the maturity the document type requires (Inputs at, section 4); IFA after "
                          "a reviewed IFR"],
            ["IFC", "every EPC input IFC, every supplier input ACCEPTED; the document ACCEPTED (approval / review class, "
                    "supplier documents); no code 3"],
            ["AB", "the document is IFC"],
            ["Impact", "each revision records the input revisions it was based on; an input revised later makes the document "
                       "CHECK REQUIRED, which blocks the release of the documents using it until it is re-issued or "
                       "confirmed"]], [2.4, d.width_cm - 2.4])
        d.p("Gate requirement: '[any:]selector[|selector][?] STATUS' - selector type:<TYPE>, rule:<MDL rule>, id:<document>, "
            "bdp, construction, ewp-first, ewp-all; @mr = documents of the packages of the gate scope, @plant = plant-general "
            "documents, @epc / @supplier = originator; '|' unites several selectors, '?' = optional (none selected is not a "
            "finding), 'any:' = one selected document is enough. The plan uses the same gates: the PO is planned when the "
            "prerequisites of the PO gate are met, and the documents a milestone, key-date or CWP gate requires are "
            "prioritised to its date (ALP-EPC-00000-GE-PLN-0001).")
        from ..core import release
        pt = {"procurement": "Procurement", "owner_acceptance": "Owner acceptance", "construction": "Construction",
              "commissioning": "Commissioning", "operations": "Operations"}
        rules = sorted((g for g in s.records("gate_rule") if g.get("status") != "superseded"),
                       key=lambda g: (list(pt).index(g["process"]), g["id"]))
        gs = release.gates(s, res)
        cnt = defaultdict(lambda: [0, 0, None])
        for g in gs:
            c = cnt[g.gate]
            c[0] += 1
            c[1] += bool(g.float is not None and g.float < 0)
            if g.float is not None:
                c[2] = g.float if c[2] is None else min(c[2], g.float)
        d.table(["Gate", "Process", "Step", "Requires", "Need", "No.", "Late", "Float"],
                [[g["id"], pt[g["process"]], g["title"], "; ".join(g["requires"]),
                  g["need"] + (f" {g['offset_days']:+d} wd" if g.get("offset_days") else ""),
                  cnt[g["id"]][0], cnt[g["id"]][1], cnt[g["id"]][2] if cnt[g["id"]][2] is not None else "-"]
                 for g in rules], [2.4, 2.6, 3.4, 4.9, 2.2, 0.9, 1.0, 1.2], size=7)
        late = sorted((g for g in gs if g.float is not None and g.float < 0), key=lambda g: g.float)
        d.p(f"{len(gs)} gate instances, {sum(1 for g in gs if g.ok_now)} open now, {len(late)} planned after their need "
            f"date, {sum(1 for g in gs if g.empty)} with a mandatory requirement selecting no document.")
        if late:
            d.table(["Gate", "Scope", "Need", "Planned", "Float wd", "Driving document"],
                    [[g.gate, g.scope_key, str(res.d(g.need)), str(res.d(g.ready)), g.float,
                      max((r for r in g.rows if r[3] is not None), key=lambda r: r[3])[4]] for g in late],
                    [2.4, 2.6, 2.2, 2.2, 1.6, d.width_cm - 11.0])
            open_tq = [q for q in sorted(self.tqs) if not self.tqs[q].get("response")
                       and any(g.gate in (self.tqs[q].get("question") or "") for g in late)]
            d.p("A gate planned late is resolved by resequencing (priority, staffing), expediting the supplier or a "
                "technical query; it stays a WARN of the release_control engine until the plan meets the need date.")
            d.bullets([self._tq_line(q) for q in open_tq])

    # ------------------------------------------------------------------ PLN-0001 engineering execution plan
    def _eep(self, d):
        s, res = self.ctx.store, self.res
        docs = {k: v for k, v in res.docs.items()}
        types = {t["id"]: t for t in s.records("doc_type")}
        dd = res.d
        d.h("1. Purpose and scope")
        d.p("This plan sets how the engineering of the project is executed: scope (the MDL), organisation, the workflow "
            "between documents and disciplines, the review cycle and the timeline against the construction need dates "
            "(Advanced Work Packaging, ALP-EPC-00000-GE-PLN-0002). All figures are taken from the MDL and the workflow "
            "timeline computed from it; they change when the records change.")
        d.h("2. Organisation and responsibilities")
        d.table(["Party", "Responsibility"], [
            [_short(self.parties, "IEPC"), "Consortium leader: plant design and balance of plant engineering, integration of "
                                           "the power island, MDL and document control, procurement of BOP packages, "
                                           "construction and commissioning management"],
            [_short(self.parties, "IEC"), "Power island design and supply (GT, HRSG, ST, generators, GSUs, TCS); VDRL "
                                          "documents per the MDL dates (TQ-IEC-023); interface data (IF- points)"],
            [_short(self.parties, "OWNER"), "Review and approval per the review class (14 / 21 days); approval of the KKS "
                                            "key list, numbering and AWP (TQ-035)"],
            [_short(self.parties, "OE"), "Owner's Engineer: technical review on behalf of the Owner, KKS key verification"]],
            [3.5, d.width_cm - 3.5])

        d.h("3. Engineering scope (MDL)")
        rows, tot = [], Counter()
        for disc in sorted({x.rec.get("discipline") for x in docs.values()}):
            ds = [x for x in docs.values() if x.rec.get("discipline") == disc]
            h = sum(x.rec.get("weight") or 0 for x in ds)
            rows.append([disc.replace("_", " "), len(ds), sum(1 for x in ds if x.rec.get("originator") == "EPC"),
                         sum(1 for x in ds if x.rec.get("originator") != "EPC"), sum(1 for x in ds if x.rec.get("bdp")),
                         sum(1 for x in ds if x.rec.get("ewp")), f"{h:,.0f}", dd(min(x.ifr for x in ds)), dd(max(x.ifc for x in ds))])
            tot.update({"n": len(ds), "h": h})
        d.table(["Discipline", "Docs", "EPC", "Supplier", "BDP", "In EWP", "Hours", "First IFR", "Last IFC"], rows,
                [3.2, 1.2, 1.2, 1.4, 1.2, 1.4, 1.6, 2.2, 2.2])
        d.p(f"Total {tot['n']} documents, {tot['h']:,.0f} hours: EPC document preparation incl. checking and the plant 3D "
            f"model; for supplier documents the EPC review. Site support, expediting and management are budgeted separately.")
        rules = s.records("mdl_rule") if "mdl_rule" in s.schemas else []
        if rules:
            d.h("3.1 How the MDL is derived", 2)
            d.p(f"{len(rules)} MDL rules (records mdl_rule) define the documents per plant, system, structure, construction "
                "area, procurement package and equipment group: type, quantity basis (sheets per P&ID sheet, instrument, "
                "loop, line, isometric, consumer, structure ...), hours, inputs, EWP / MR links and, for supplier documents, "
                "the timing after the purchase order. Quantities are system estimates (basis "
                + ", ".join(sorted({d_["id"] for d_ in s.records("decision") if d_["title"].startswith("MDL quantity basis")}))
                + ") until the equipment, instrument and line registers are larger; python -m engine mdl sync keeps the "
                "documents in line with the rules and registers. Single deliverables (studies, plans, permit dossiers, test "
                "reports) are individual records citing their requirement, permit or clause.")
            fam = Counter(r["scope"] for r in rules)
            d.table(["Rule scope", "Rules"], [[k, v] for k, v in sorted(fam.items())], [5.0, 3.0])
        bms = s.records("mdl_benchmark") if "mdl_benchmark" in s.schemas else []
        if bms:
            d.h("3.2 Completeness against indicative benchmarks", 2)
            d.p("Indicative ranges for a comparable 1x1 H-class CCGT (engineering judgement, not contractual): below the "
                "minimum = scope probably missing (WARN), above the maximum = review for duplication (INFO).")
            brow = []
            for b in sorted(bms, key=lambda x: x["id"]):
                sel = [x.rec for x in docs.values() if (b["discipline"] == "all" or x.rec.get("discipline") == b["discipline"])
                       and ((x.rec.get("originator") == "EPC") == (b["originator"] == "EPC") or b["originator"] == "ALL")]
                act = {"docs": len(sel), "sheets": sum(r.get("sheets") or 1 for r in sel), "hours": sum(r.get("weight") or 0 for r in sel)}
                for k in ("docs", "sheets", "hours"):
                    lo, hi = b.get(f"{k}_min"), b.get(f"{k}_max")
                    if lo is not None or hi is not None:
                        brow.append([b["id"], f"{b['discipline']} / {b['originator']}", k, f"{act[k]:,.0f}",
                                     (f"{lo:,}" if lo is not None else "-") + " - " + (f"{hi:,}" if hi is not None else "-")])
            d.table(["Benchmark", "Scope", "Measure", "MDL", "Indicative range"], brow, [2.6, 4.2, 2.0, 2.6, 4.0], size=7.5)
        d.p("Coverage is checked at every engine run: every design discipline has its design criteria, every KKS system "
            "has the document types its category requires, every "
            "Employer's Requirement and every EPC / IEC scope item is answered by at least one document, every equipment "
            "item has a datasheet, an MR and a CWP, every MR a specification and a requisition, every CWP an EWP.")

        d.h("4. Workflow rules")
        d.bullets([
            "Documents form a network through their inputs (MDL column Inputs). A document starts when all its inputs have "
            "reached the maturity its type requires (IFR or IFC, section 4 of ALP-EPC-00000-GE-PRC-0002), not before NTP.",
            "First issue (IFR) = start + preparation time of the type (+5 % per extra sheet, at most double).",
            f"Owner review {workflow.OWNER_REVIEW} wd ({workflow.OWNER_REVIEW_BDP} wd for the Basic Design Package); "
            f"approval class: IFA = IFR + review + update, IFC = IFA + {workflow.APPROVAL_CODE} wd; review class: IFC = IFR + "
            "review + update; information / internal: IFC = IFR + update.",
            "Tender-stage documents (bid design, and the requisitions of long-lead packages per the procurement decision) "
            "are issued at NTP. Supplier documents with committed dates keep them (IEC, TQ-IEC-023); the others are timed "
            "from their MR: weeks after the PO for design data, weeks before delivery for FAT, erection and O&M documents. "
            "Issued revisions replace the planned dates.",
            "Construction documents belong to the EWP of their CWP. An EWP is needed ewp_lead_days before its CWP starts for "
            "the first IWPs; documents of progressive types (isometrics, supports, schematics, loop diagrams, reinforcement, "
            "equipment foundations ...) are released to later IWPs at CWP start - lead + share x CWP duration (share per "
            "document type, section 4 of ALP-EPC-00000-GE-PRC-0002). EPC documents that need certified vendor data "
            "(e.g. equipment foundations) take the supplier documents as inputs.",
            "Requisitions start the PWP (MR) cycle: PO = MRQ IFC + bid + award; delivery on site = PO + manufacture + "
            "transport; needed at the first CWP start (+ need lag for materials installed late in the CWP).",
            "Engineering capacity per discipline (eng_resource) with a mobilisation ramp from 30 % at NTP; documents are "
            "scheduled in need-date priority within the capacity (levelled timeline)."])

        d.h("5. Interdisciplinary inputs (who feeds whom)")
        m = defaultdict(Counter)
        for x in docs.values():
            for i in x.rec.get("inputs", []):
                if i in docs:
                    m[docs[i].rec.get("discipline")][x.rec.get("discipline")] += 1
        discs = sorted({x.rec.get("discipline") for x in docs.values()})
        ab = {v: k for k, v in kks.DISCIPLINES.items()}
        d.p("Number of input links from the supplying discipline (row) to the receiving discipline (column).")
        d.table(["from \\ to"] + [ab.get(x, x) for x in discs],
                [[ab.get(a, a)] + [m[a][b] or "" for b in discs] for a in discs], [1.8] + [1.2] * len(discs), size=7)
        d.p("Typical inputs per document type (checked at every run; a document without any of them is reported):")
        d.table(["Type", "Title", "Inputs at", "Typical inputs"],
                [[t["id"], t.get("title", ""), t.get("input_maturity"), ", ".join(t.get("input_types") or []) or "-"]
                 for t in sorted(types.values(), key=lambda t: t["id"]) if t.get("input_types")], [1.2, 6.5, 1.6, 8.0], size=7)

        d.h("6. Timeline")
        q = defaultdict(Counter)
        for x in docs.values():
            dt = dd(x.ifc)
            q[f"{dt.year} Q{(dt.month - 1) // 3 + 1}"][x.rec.get("discipline")] += 1
        qs = sorted(q)
        d.p("IFC / final issues per quarter and discipline (the monthly curve and the AWP bars are in "
            "ALP_engineering_timeline.pdf of the engineering_plan engine):")
        d.table(["Quarter"] + [ab.get(x, x) for x in discs] + ["Total"],
                [[k] + [q[k][x] or "" for x in discs] + [sum(q[k].values())] for k in qs], [1.9] + [1.15] * len(discs) + [1.3],
                size=7)
        load = self._load()
        tender = [x for x in docs.values() if x.rec.get("tender")]
        if res.capacity:
            d.p("Document preparation capacity at full mobilisation (eng_resource, levelled timeline): " + ", ".join(
                f"{ab.get(k, k)} {v / workflow.HOURS_PER_DAY:.0f} FTE" for k, v in sorted(res.capacity.items()))
                + f" - total {sum(res.capacity.values()) / workflow.HOURS_PER_DAY:.0f} FTE. Documents are scheduled in the "
                  "order of their latest start (backwards from the EWP and PWP need dates) within these capacities.")
        d.p(f"Engineering load per month: hours of each EPC document as booked by the levelled timeline (spread over its "
            f"preparation when not levelled); "
            f"{len(tender)} tender-stage documents ({sum(x.rec.get('weight') or 0 for x in tender):,.0f} h) were prepared "
            f"in the bid and are excluded; FTE at 150 h / month.")
        peak = max(load.items(), key=lambda kv: sum(kv[1].values())) if load else None
        d.table(["Month"] + [ab.get(x, x) for x in discs] + ["Hours", "FTE"],
                [[k] + [f"{v[x]:,.0f}" if v[x] else "" for x in discs] + [f"{sum(v.values()):,.0f}", f"{sum(v.values()) / 150:.0f}"]
                 for k, v in sorted(load.items())], [1.9] + [1.05] * len(discs) + [1.4, 1.0], size=7)
        if peak:
            d.p(f"Peak {peak[0]}: {sum(peak[1].values()):,.0f} h (about {sum(peak[1].values()) / 150:.0f} FTE)."
                + ("" if res.levelled else " Early dates of an unconstrained network - no capacity records; the profile "
                                           "front-loads the work."))
        d.p("Key dates (CPM, driven by mechanical completion of the CWPs):")
        d.table(["Key date", "Title", "Forecast", "Float (wd)"],
                [[k, a.title, res.cal.finish_date(a.ef, a.es), a.tf] for k, a in sorted(res.acts.items()) if k.startswith("KD-")],
                [2.0, 9.4, 3.0, 3.0])

        d.h("7. Supplier documents (VDRL)")
        sup = defaultdict(list)
        for x in docs.values():
            if x.rec.get("originator", "EPC") != "EPC":
                sup[x.rec.get("mr") or "-"].append(x)
        d.p(f"{sum(len(v) for v in sup.values())} supplier documents in {len(sup)} packages. Per package:")
        d.table(["MR", "Originator", "Docs", "Sheets", "First IFR", "Last final"],
                [[m, ", ".join(sorted({x.rec.get("originator") for x in v})), len(v), sum(x.rec.get("sheets") or 1 for x in v),
                  dd(min(x.ifr for x in v)), dd(max(x.ifc for x in v))] for m, v in sorted(sup.items())],
                [2.6, 2.4, 1.6, 1.8, 2.4, 2.4], size=7)
        d.p("Power island (IEC) documents:")
        succ = Counter(i for x in docs.values() for i in x.rec.get("inputs", []))
        iec = sorted((x for x in docs.values() if x.rec.get("originator") == "IEC"), key=lambda x: x.ifr)
        d.table(["Number", "IEC ref", "Title", "IFR", "IFC", "Feeds"],
                [[x.id, x.rec.get("vendor_ref") or "-", x.rec.get("title", ""), dd(x.ifr), dd(x.ifc), succ.get(x.id, 0)]
                 for x in iec], [4.3, 2.6, 5.9, 1.8, 1.8, 1.2], size=7)

        d.h("8. Near-critical items")
        rows = [[e, v["cwp"], v["driver"] or "-", dd(v["ready"]), dd(v["need"]), v["float"]]
                for e, v in sorted(res.ewps.items(), key=lambda kv: (kv[1]["float"] is None, kv[1]["float"]))
                if v["float"] is not None and v["float"] < 20]
        d.p("EWPs with less than 20 working days float (the document with the smallest float drives the EWP):")
        d.table(["EWP", "CWP", "Driving document", "Ready", "Needed", "Float"], rows, [2.8, 2.8, 5.2, 2.0, 2.0, 1.2], size=7)
        rows = [[k, s.get("mr", k).get("title", ""), dd(v["po"]), dd(v["ros"]), dd(v["need"]), v["need_cwp"], v["float"]]
                for k, v in sorted(res.mrs.items(), key=lambda kv: (kv[1]["float"] is None, kv[1]["float"]))
                if v["float"] is not None and v["float"] < 20]
        d.p("PWPs (MRs) with less than 20 working days float between delivery on site and the first CWP start:")
        d.table(["MR", "Title", "PO", "On site", "Needed", "CWP", "Float"], rows, [2.0, 6.0, 1.9, 1.9, 1.9, 2.3, 1.0], size=7)

        d.h("9. Limitations of this revision")
        d.bullets([
            ("Dates are levelled against the document preparation capacity of section 6 (basis "
             + (", ".join(sorted({b for r in s.records("eng_resource") for b in r.get("basis_refs") or []})) or "-")
             + "); a change of staffing changes the dates at the next run." if res.levelled else
             "Dates are early dates of an unconstrained network: engineering resources are not levelled."),
            "Document quantities are estimates per system until the P&IDs and the 3D model produce the instrument, line "
            "and valve registers; the rules then use the register counts (section 3.1).",
            "Benchmarks are indicative ranges (engineering judgement), to be replaced by company historical data.",
            "Supplier document quantities follow the package rules; the supplier's own VDRL replaces them after the PO.",
            "KKS key titles are not yet verified against the licensed VGB key catalogue (Owner's Engineer, TQ-035)."])
        self._checks(d, {"inputs", "coverage system", "coverage requirement", "coverage scope", "coverage equipment",
                         "coverage MR", "key date", "MDL rules", "benchmark", "design criteria"})

    def _load(self):
        res = self.res
        load = defaultdict(Counter)
        for x in res.docs.values():
            if x.fixed or x.rec.get("tender") or x.rec.get("originator", "EPC") != "EPC":
                continue
            n = max(1, x.ifr - x.start)
            work = x.work or {i: (x.rec.get("weight") or 0) / n for i in range(x.start, x.start + n)}
            for i, h in work.items():
                dt = res.d(i)
                load[f"{dt.year}-{dt.month:02d}"][x.rec.get("discipline")] += h
        return load

    # ------------------------------------------------------------------ PLN-0002 AWP execution plan
    def _awp(self, d):
        s, res = self.ctx.store, self.res
        dd = res.d
        cwas = sorted(s.records("cwa"), key=lambda c: c.get("path_seq") or 99)
        cwps = sorted(s.records("cwp"), key=lambda c: c["id"])
        mrs = {m["id"]: m for m in s.records("mr")}
        eqs = s.records("equipment")
        d.h("1. Purpose and definitions")
        d.p("Advanced Work Packaging (AWP) aligns engineering and procurement with the construction sequence: construction is "
            "planned by area and package first (path of construction), and engineering and procurement deliver what each "
            "package needs, when it needs it.")
        d.table(["Package", "Definition on this project", "Record"], [
            ["CWA", "Construction work area: geographic area of the plot, ordered in the path of construction", "cwa"],
            ["CWP", "Construction work package: one per CWA and discipline, a level-3 CPM activity with the same id; scope, "
                    "quantities and contractor", "cwp / activity"],
            ["EWP", "Engineering work package: the IFC documents one CWP needs (one EWP per CWP); documents link to it", "ewp"],
            ["PWP", "Procurement work package: a material requisition (MR) with its PO, vendor data, manufacture and "
                    "delivery; linked to the CWPs that install its materials", "mr"],
            ["IWP", "Installation work package: 1-2 weeks of work for one crew, prepared by the construction contractor from "
                    "the CWP and released only when constraint-free", "(construction)"]], [1.4, d.width_cm - 4.4, 3.0])
        for x in self.decisions:
            if "Advanced Work Packaging" in x.get("title", ""):
                d.p(f"{x['decision']} ({x['id']}, {x.get('status')}, {x.get('decided_by')})", bold_lead="Decision: ")
        d.bullets([self._tq_line("TQ-035"), self._tq_line("TQ-037")])

        d.h("2. Path of construction (CWAs)")
        n_eq = Counter(e.get("cwa") for e in eqs)
        d.table(["Seq", "CWA", "Title", "Area (E / N, m)", "Structures", "Assets", "Status", "Description"],
                [[c.get("path_seq"), c["id"], c.get("title", ""),
                  f"E {c.get('e_min')} to {c.get('e_max')} / N {c.get('n_min')} to {c.get('n_max')}",
                  ", ".join(c.get("structures") or []), n_eq.get(c["id"], 0), c.get("status", ""), c.get("description", "")]
                 for c in cwas], [1.0, 1.6, 4.4, 3.6, 3.4, 1.3, 1.5, 9.3], size=7)

        d.h("3. Construction work packages (CWPs)")
        ewp_of = {e["cwp"]: e["id"] for e in s.records("ewp")}
        mr_of = defaultdict(list)
        for m in mrs.values():
            for c in m.get("cwps", []):
                mr_of[c].append(m["id"])
        rows = []
        for c in cwps:
            a = res.acts.get(c.get("activity"))
            e = res.ewps.get(ewp_of.get(c["id"]), {})
            ros = max((res.mrs[m]["ros"] for m in mr_of[c["id"]] if m in res.mrs), default=None)
            rows.append([c["id"], c.get("title", ""), c.get("contractor") or "-", dd(a.es) if a else "-",
                         res.cal.finish_date(a.ef, a.es) if a else "-", dd(e.get("ready")), e.get("float"),
                         dd(ros) if ros is not None else "-", ", ".join(mr_of[c["id"]]) or "-"])
        d.table(["CWP", "Title", "Contractor", "Start", "Finish", "EWP ready", "EWP float", "Last ROS", "PWPs (MR)"], rows,
                [2.6, 6.2, 3.2, 2.0, 2.0, 2.0, 1.4, 2.0, 4.7], size=7)

        d.h("4. Engineering work packages (EWPs)")
        rows = [[e, v["cwp"], len(v["docs"]), v["driver"] or "-", dd(v["ready"]), dd(v["need"]), v["float"],
                 v["vendor_mr"] or "-", dd(v["vendor_data"]), v["vendor_float"]] for e, v in sorted(res.ewps.items())]
        d.table(["EWP", "CWP", "Docs", "Driving document", "Complete (IFC)", "First need", "Float", "Vendor data of", "Vendor data",
                 "Float"], rows, [2.8, 2.8, 1.1, 7.2, 2.3, 2.3, 1.3, 2.6, 2.3, 1.3], size=7)

        d.h("5. Procurement work packages (PWPs / MRs)")
        rows = []
        for k, v in sorted(res.mrs.items()):
            m = mrs[k]
            rows.append([k, m.get("title", ""), m.get("package_type", "").replace("_", " "), m.get("supplier") or "-",
                         dd(v["issue"]) if v["issue"] is not None else "fixed", dd(v["po"]), dd(v["vdr"]), dd(v["ros"]),
                         dd(v["need"]), v["need_cwp"] or "-", v["float"]])
        d.table(["MR", "Title", "Type", "Supplier", "MRQ IFC", "PO", "Vendor data", "On site", "Needed", "First CWP", "Float"],
                rows, [1.9, 6.4, 1.8, 1.6, 1.9, 1.9, 1.9, 1.9, 1.9, 2.3, 1.1], size=7)

        d.h("6. Release rules and IWPs")
        d.bullets([
            "A CWP is released when the documents of its first IWPs are IFC and their materials are on site or have a "
            "confirmed delivery; no IWP is issued to the field unless all its documents are IFC and its constraints are "
            "removed; the EWP completeness for the next 8 weeks of IWPs is reported monthly per CWP (TQ-037, amending "
            "TQ-035).",
            "Documents of progressive types (isometrics, supports, schematics, loop diagrams, reinforcement, equipment "
            "foundations ...) are released to the later IWPs of the CWP: needed at CWP start - lead + share x CWP duration.",
            "The engineering_plan engine reports EWP float (smallest float of its documents), vendor data float and PWP float "
            "(on site before the first CWP start) at every run; negative float is a warning to be resolved by re-sequencing, "
            "expediting or a TQ before the plan is re-issued.",
            "IWPs are prepared by the construction contractors from the released CWP: scope of 1-2 weeks for one crew, with "
            "the IFC documents, material pick list (from the PWPs), permits, scaffolding and equipment; an IWP is issued to "
            "the field only when all its constraints are removed.",
            "Plant assets carry cwa / cwp / mr; documents carry ewp / mr; construction progress is reported per CWP "
            "(activity percent complete) and rolls up to the level-3 schedule."])
        self._checks(d, {"AWP", "coverage CWP", "coverage EWP", "EWP float", "EWP vendor data", "PWP float", "agreement"})


ENGINE = Procedures()
