"""Clause-based documents (docx + pdf): design criteria, general specifications, reports, procedures and compliance
matrices - every MDL document with produced_by = technical_documents.

The content is data: doc_clause records (text, required values, matrix rows) plus automatic data blocks read from the
records at generation time, so a document always shows the current design data:
  params:<category,...>          design parameters of the categories (value, condition, status, basis)
  equipment:system=<prefix,...>  equipment of the systems (service, redundancy, rating, design P / T, material)
  equipment:type=<type,...>      equipment of the types
  guarantees                     Owner and power island guarantees
  hmb_summary                    heat and mass balance cases side by side (computed with engine/core/hmb.py)
  aux_loads:<case>               auxiliary loads of a heat balance case
  requirements:<ER-id,...>       Employer's Requirements text
  decisions:<id,...>             decisions (decision text)
  permits                        permits and authorities
  tie_ins                        terminal points
  progress_rules                 progress measurement steps
  doc_types                      document types and review classes
A final section lists every reference record cited by the clauses. WARN: a document without clauses, a block
without data, a clause citing a missing record."""
from __future__ import annotations

from collections import defaultdict

from ..core import docshell
from ..core.runner import Context, Engine, pdf_from_office

HEAD = ["Item", "Value", "Unit", "Status", "Basis / remarks"]


def _ids(refs) -> str:
    """basis references printed as record ids (the entity is clear from the id prefix)"""
    return ", ".join(r.split(":", 1)[-1] for r in refs or [])


def _num(v):
    return f"{v:,.10g}" if isinstance(v, (int, float)) else ""


def _skey(sec: str):
    return tuple(int(x) if x.isdigit() else x for x in str(sec).split("."))


class TechnicalDocuments(Engine):
    name = "technical_documents"
    title = "Clause-based documents: design criteria, general specifications, reports, procedures, matrices (Word + PDF)"
    version = "1.2.0"
    inputs = ["project", "document", "document_revision", "doc_type", "doc_clause", "design_parameter", "equipment",
              "guarantee", "hmb_case", "process_stream", "aux_load", "requirement", "decision", "permit", "tie_in",
              "progress_rule", "reference", "party", "system", "mr", "source", "contract"]
    formats = ["docx", "pdf"]
    code_deps = ["engine/core/docshell.py", "engine/core/wordkit.py", "engine/core/release.py", "engine/core/hmb.py",
                 "engine/core/thermo.py", "templates/docx/datasheet_base.docx"]

    def run(self, ctx: Context):
        s = ctx.store
        clauses = defaultdict(list)
        for c in s.records("doc_clause"):
            if c.get("status") != "superseded":
                clauses[c["document"]].append(c)
        files = []
        for d in sorted((d for d in s.records("document") if d.get("produced_by") == self.name
                         and d.get("status") != "cancelled"), key=lambda d: d["id"]):
            cl = clauses.get(d["id"])
            if not cl:
                ctx.warnings.append(f"{d['id']}: no doc_clause records - not generated")
                continue
            out = self._doc(ctx, d, sorted(cl, key=lambda c: (_skey(c["section"]), c["seq"])))
            files.append(out)
            if ctx.options.get("pdf", "yes") != "no":
                pdf = pdf_from_office(out, ctx)
                if pdf:
                    files.append(pdf)
        return files

    # ------------------------------------------------------------------ document
    def _doc(self, ctx, doc, cl):
        s = ctx.store
        no = doc["id"]
        d = docshell.word(ctx, no, self)
        secs = defaultdict(list)
        for c in cl:
            secs[c["section"]].append(c)
        titles = {k: next((c.get("section_title") for c in v if c.get("section_title")), "") for k, v in secs.items()}
        for sec in sorted(secs, key=_skey):
            items = secs[sec]
            level = 1 if "." not in str(sec) else 2
            d.h(f"{sec}. {titles[sec]}".rstrip(". ") if titles[sec] else f"{sec}.", level)
            rows, head, n = [], None, 0
            for c in items:
                if c.get("block"):
                    self._flush(d, rows, head)
                    rows, head = [], None
                    self._block(ctx, d, no, c["block"])
                if c.get("text"):
                    self._flush(d, rows, head)
                    rows, head = [], None
                    n += 1
                    d.p(c["text"], bold_lead=f"{sec}.{n} ")
                if c.get("parameter"):
                    head = head or c.get("table_head")
                    val = " ".join(filter(None, [_num(c.get("value")), c.get("value_text")]))
                    ids = _ids(c.get("basis_refs"))
                    basis = "; ".join(filter(None, [ids, c.get("remarks")]))
                    evidence = " ".join(filter(None, [c.get("remarks"), f"[{ids}]" if ids else ""]))   # matrix column
                    rows.append([c["parameter"], val, c.get("unit") or "", c.get("status") or "", basis, evidence])
            self._flush(d, rows, head)
        # references
        refs = {r["id"]: r for r in s.records("reference")}
        cited = sorted({r.split(":", 1)[1] for c in cl for r in c.get("basis_refs") or [] if r.startswith("reference:")})
        for c in cl:
            for r in c.get("basis_refs") or []:
                ent, rid = r.split(":", 1)
                if s.get(ent, rid) is None:
                    ctx.warnings.append(f"{no}: clause {c['id']} cites {r}, not in the database")
        if cited:
            d.h("References")
            d.p("Codes and standards cited in this document (Codes, Standards and Regulations Register "
                "ALP-EPC-00000-GE-LST-0001; latest edition at contract date unless stated).")
            d.table(["Code", "Title"], [[refs[r]["code"], refs[r]["title"]] for r in cited if r in refs], [4.0, 12.6], size=7)
        out = ctx.out_dir / f"{no}.docx"
        return d.save(out)

    @staticmethod
    def _flush(d, rows, head):
        if not rows:
            return
        h = head or HEAD
        if len(h) == 5:
            w = [5.0, 4.2, 1.6, 1.8, 4.0]
        else:
            w = [16.6 / len(h)] * len(h)
        d.table(h, [r[:5] if len(h) == 5 else [r[0], r[1], r[5]][:len(h)] for r in rows], w, size=7)

    # ------------------------------------------------------------------ automatic blocks
    def _block(self, ctx, d, no, spec):
        s = ctx.store
        kind, _, arg = spec.partition(":")
        vals = [x.strip() for x in arg.split(",") if x.strip()]
        warn = lambda: ctx.warnings.append(f"{no}: block '{spec}' has no data")
        if kind == "params":
            ps = sorted((p for p in s.records("design_parameter") if p.get("status") != "superseded"
                         and (not vals or p["category"] in vals)), key=lambda p: (p["category"], p["parameter"].lower()))
            if not ps:
                return warn()
            d.table(["Parameter", "Value", "Condition", "Status", "Basis"],
                    [[p["parameter"], " ".join(filter(None, [_num(p.get("value")), p.get("value_text"), p.get("unit")])),
                      p.get("condition") or "", p.get("status") or "", _ids(p.get("basis_refs"))] for p in ps],
                    [5.0, 3.6, 3.4, 1.8, 2.8], size=7)
        elif kind == "equipment":
            how, _, sel = arg.partition("=")
            sel = [x.strip() for x in sel.split(",") if x.strip()]
            eq = [e for e in s.records("equipment") if e.get("status") != "deleted" and
                  (any(e["system"].startswith(p) for p in sel) if how == "system" else e.get("equipment_type") in sel)]
            if not eq:
                return warn()

            def rating(e):
                parts = [f"{_num(e.get('capacity'))} {e.get('capacity_unit') or ''}".strip() if e.get("capacity") is not None else "",
                         f"{_num(e.get('head'))} m" if e.get("head") else "",
                         f"{_num(e.get('rated_power'))} kW" if e.get("rated_power") else "",
                         (f"{e['voltage'] / 1000:g} kV" if e["voltage"] >= 1000 else f"{e['voltage']:g} V") if e.get("voltage") else ""]
                return ", ".join(p for p in parts if p)
            def pt(e):
                return " / ".join(filter(None, [f"{_num(e.get('design_pressure'))} barg" if e.get("design_pressure") is not None else "",
                                                f"{_num(e.get('design_temperature'))} degC" if e.get("design_temperature") is not None else ""]))
            eq = sorted(eq, key=lambda e: e["id"])
            rows = [[e["id"], e.get("description", ""), e.get("service") or "", e.get("redundancy") or "", rating(e), pt(e),
                     e.get("material") or ""] for e in eq]
            if any(r[5] for r in rows):
                d.table(["Tag", "Description", "Service", "Redundancy", "Rating", "Design P / T", "Material"], rows,
                        [2.0, 3.4, 3.0, 2.0, 2.2, 1.4, 2.6], size=6.5)
            else:                                   # no pressure equipment in the selection: no empty column
                d.table(["Tag", "Description", "Service", "Redundancy", "Rating", "Material"], [r[:5] + r[6:] for r in rows],
                        [2.0, 3.6, 3.2, 2.2, 2.6, 3.0], size=6.5)
        elif kind == "guarantees":
            g = sorted(s.records("guarantee"), key=lambda x: (x["contract"], x["id"]))
            d.table(["Id", "Guarantee", "Value", "Min / max", "Conditions"],
                    [[x["id"], x["parameter"], f"{_num(x['guaranteed_value'])} {x['unit']}", x["direction"], x.get("conditions", "")]
                     for x in g], [1.2, 5.2, 2.6, 1.4, 6.2], size=7)
        elif kind == "hmb_summary":
            self._hmb(ctx, d, no)
        elif kind == "aux_loads":
            a = sorted((x for x in s.records("aux_load") if x["hmb_case"] == arg), key=lambda x: x["id"])
            if not a:
                return warn()
            d.table(["Id", "Consumer", "Method", "Power kW", "Status"],
                    [[x["id"], x["description"], x["method"], _num(x.get("power")) or "computed", x.get("status") or ""] for x in a],
                    [1.4, 8.0, 2.0, 2.2, 2.0], size=7)
        elif kind == "requirements":
            for rid in vals:
                r = s.get("requirement", rid)
                if r:
                    d.p(r.get("text", ""), bold_lead=f"{rid}: ")
                else:
                    ctx.warnings.append(f"{no}: requirement {rid} not found")
        elif kind == "decisions":
            for rid in vals:
                r = s.get("decision", rid)
                if r:
                    d.p(r.get("decision", ""), bold_lead=f"{rid} {r.get('title', '')}: ")
                else:
                    ctx.warnings.append(f"{no}: decision {rid} not found")
        elif kind == "permits":
            p = sorted(s.records("permit"), key=lambda x: x["id"])
            d.table(["Permit", "Title", "Authority", "Phase", "Need", "Status"],
                    [[x["id"], x["title"], x["authority"], x["phase"], x.get("needed_by") or "", x["permit_status"]] for x in p],
                    [1.6, 6.8, 2.2, 2.2, 2.0, 1.8], size=7)
        elif kind == "tie_ins":
            t = sorted(s.records("tie_in"), key=lambda x: x["id"])
            d.table(["Point", "Service", "Status"], [[x["id"], x.get("service", ""), x.get("status", "")] for x in t],
                    [2.0, 12.0, 2.6], size=7)
        elif kind == "progress_rules":
            p = sorted(s.records("progress_rule"), key=lambda x: (x["percent"], x["id"]))   # in step order
            if not p:
                return warn()
            d.table(["Step", "% earned", "Remarks"], [[x["id"], _num(x["percent"]), x.get("remarks") or ""] for x in p],
                     [4.0, 2.0, 10.6], size=7)
        elif kind == "doc_types":
            t = sorted(s.records("doc_type"), key=lambda x: x["id"])
            d.table(["Type", "Title", "Review class"], [[x["id"], x.get("title", ""), x.get("review", "")] for x in t],
                    [1.6, 11.0, 4.0], size=7)
        else:
            ctx.warnings.append(f"{no}: unknown block '{spec}'")

    def _hmb(self, ctx, d, no):
        from ..core import hmb
        from .hmb import refs_for
        s = ctx.store
        cases = sorted(s.records("hmb_case"), key=lambda c: (bool(c.get("reference_case")), c["id"]))
        res = {}
        for c in cases:
            st = [x for x in s.records("process_stream") if x["hmb_case"] == c["id"]]
            aux = [x for x in s.records("aux_load") if x["hmb_case"] == c["id"]]
            if not st:
                continue
            ref = c.get("reference_case")
            res[c["id"]] = hmb.calculate(c, st, aux, refs_for(s, c), res[ref].summary if ref and ref in res else None)
        ids = sorted(res)
        rows = [("GT output", "gt_output", 1e-3, "MW"), ("ST output", "st_output", 1e-3, "MW"), ("Gross output", "gross", 1e-3, "MW"),
                ("Auxiliaries + transformer losses", None, None, "MW"), ("Net output", "net", 1e-3, "MW"),
                ("Heat input (LHV)", "heat_input", 1e-3, "MW"), ("Net heat rate (LHV)", "net_hr", 1, "kJ/kWh"),
                ("Net efficiency", "net_eff", 100, "%")]
        table = []
        for label, key, f, unit in rows:
            if key is None:
                vals = [(res[i].summary["aux"] + res[i].summary["transformer_losses"]) / 1000 for i in ids]
            else:
                vals = [res[i].summary[key] * f for i in ids]
            table.append([f"{label} [{unit}]"] + [f"{v:,.1f}" if abs(v) >= 100 else f"{v:,.2f}" for v in vals])
        nwarn = {i: sum(1 for st, _ in res[i].checks if st == "WARN") for i in ids}
        table.append(["Checks WARN"] + [str(nwarn[i]) for i in ids])
        w = [4.0] + [12.6 / len(ids)] * len(ids)
        d.table(["Item"] + ids, table, w, size=6)


ENGINE = TechnicalDocuments()
