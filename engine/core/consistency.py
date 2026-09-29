"""Consistency, sanity and coverage checks across the records (reported by the engineering_plan engine, sheet Checks).

- equipment data: the fields each equipment type needs for its datasheet / the equipment list (EPC supply: WARN; supplier
  supply: INFO until the supplier data arrives), IEC standard motor sizes, motors >= 200 kW on MV, number of tags against
  the stated redundancy ('2 x 100 %' needs two units in the system);
- document network: EPC documents without inputs other than those allowed to start first (design basis, procedures,
  plans, registers, surveys, documents started from site records);
- production coverage: documents with a producing engine (document.produced_by) per document type; issued EPC revisions
  frozen in a delivery.
Returns rows (item, check, status, text)."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

IEC_MOTORS = [0.37, 0.55, 0.75, 1.1, 1.5, 2.2, 3, 4, 5.5, 7.5, 11, 15, 18.5, 22, 30, 37, 45, 55, 75, 90, 110, 132, 160, 200,
              250, 315, 355, 400, 450, 500, 560, 630, 710, 800, 900, 1000, 1120, 1250, 1400, 1600, 1800, 2000, 2240, 2500,
              2800, 3150, 3550, 4000, 4500, 5000, 5600, 6300, 7100, 8000]
MOTOR_TYPES = {"pump", "fan", "compressor"}
NEEDS = {
    "pump": ["service", "redundancy", "capacity", "head", "design_pressure", "design_temperature", "material", "rated_power", "voltage"],
    "fan": ["service", "redundancy", "capacity", "rated_power", "voltage"],
    "compressor": ["service", "redundancy", "capacity", "design_pressure", "rated_power", "voltage"],
    "tank": ["service", "capacity", "design_pressure", "design_temperature", "material"],
    "heat exchanger": ["service", "capacity", "design_pressure", "design_temperature", "material"],
    "filter": ["service", "capacity"],
    "transformer": ["service", "capacity", "voltage"],
    "switchgear": ["service", "capacity", "voltage"],
    "crane": ["service", "capacity", "rated_power"],
}
FIRST_TYPES = {"DBR", "PRC", "PLN", "LST", "RPT", "TST", "TRP", "MDB"}      # may start without document inputs


def _units(red: str) -> int | None:
    m = re.match(r"\s*(\d+)\s*x\s*\d+", red or "")
    return int(m.group(1)) if m else None


def check(s) -> list[tuple[str, str, str, str]]:
    out = []
    eqs = [e for e in s.records("equipment") if e.get("status") != "deleted"]
    miss = defaultdict(list)
    for e in eqs:
        need = NEEDS.get(e.get("equipment_type"), [])
        if "diesel" in f"{e.get('description', '')} {e.get('service', '')}".lower():
            need = [f for f in need if f != "voltage"]           # engine driven
        gaps = [f for f in need if e.get(f) in (None, "")]
        if gaps:
            supplier = e.get("supply") not in (None, "IEPC")
            miss["INFO" if supplier else "WARN"].append(e["id"])
            out.append((e["id"], "equipment data", "INFO" if supplier else "WARN",
                        f"{e.get('equipment_type')}: missing {', '.join(gaps)}" + (" (supplier data per VDRL)" if supplier else "")))
        p = e.get("rated_power")
        txt = f"{e.get('description', '')} {e.get('service', '')}".lower()
        if e.get("equipment_type") in MOTOR_TYPES and p and p < 10000 and not re.search(r"diesel|chiller", txt):
            if not any(abs(p - m) < 1e-6 for m in IEC_MOTORS):
                out.append((e["id"], "motor size", "WARN", f"rated power {p:g} kW is not an IEC standard motor size"))
            if p >= 200 and (e.get("voltage") or 0) < 1000:
                out.append((e["id"], "motor size", "WARN", f"{p:g} kW motor not on MV (voltage {e.get('voltage')})"))
            if p < 200 and (e.get("voltage") or 0) >= 1000:
                out.append((e["id"], "motor size", "WARN", f"{p:g} kW motor on MV"))
    groups = defaultdict(list)
    for e in eqs:
        red = e.get("redundancy") or ""
        if e.get("equipment_type") == "package" or re.search(r"\bwith\b|\bper\b|one per|each|trains?|sections?|runs|vessels|stacks|racks", red):
            continue                          # units inside one package tag, or pairs across systems
        groups[(e["system"], e.get("equipment_type"), red)].append(e)
    for (sy, typ, red), items in groups.items():
        n = _units(red)
        units = sum(x.get("quantity") or 1 for x in items)
        if n and n > units:
            out.append((", ".join(x["id"] for x in items), "redundancy", "WARN",
                        f"{red} but {units} {typ} unit(s) registered with this redundancy in {sy}"))
    out.append(("-", "equipment data", "OK" if not miss["WARN"] else "WARN",
                f"{len(eqs)} items: {len(eqs) - len(miss['WARN']) - len(miss['INFO'])} complete, {len(miss['WARN'])} EPC items "
                f"incomplete, {len(miss['INFO'])} supplier items awaiting supplier data"))
    # document network
    docs = [d for d in s.records("document") if d.get("status") != "cancelled"]
    bad = [d for d in docs if d.get("originator", "EPC") == "EPC" and not d.get("inputs") and not d.get("tender")
           and d.get("type_code") not in FIRST_TYPES and not d.get("after_activity")]
    for d in bad:
        out.append((d["id"], "document inputs", "WARN", f"{d.get('type_code')} without inputs - missing links? (L-EPCE-0012)"))
    out.append(("-", "document inputs", "OK" if not bad else "WARN",
                f"{sum(1 for d in docs if d.get('originator', 'EPC') == 'EPC')} EPC documents, {len(bad)} without inputs "
                f"outside the first-start types"))
    # production coverage
    epc = [d for d in docs if d.get("originator", "EPC") == "EPC"]
    by_t = Counter(d.get("type_code") for d in epc)
    prod = Counter(d.get("type_code") for d in epc if d.get("produced_by"))
    out.append(("-", "production coverage", "INFO",
                f"{sum(prod.values())} of {len(epc)} EPC documents have a producing engine; types covered: "
                + ", ".join(f"{t} {prod[t]}/{by_t[t]}" for t in sorted(prod)) + "; types without engine: "
                + ", ".join(f"{t} {n}" for t, n in sorted(by_t.items()) if not prod.get(t))))
    revs = {r["id"]: r for r in s.records("document_revision")}
    frozen = {x for d in s.records("delivery") for x in d.get("revisions") or []}
    dmap = {d["id"]: d for d in docs}
    for rid, r in revs.items():
        d = dmap.get(r["document"], {})
        if d.get("produced_by") and d.get("originator", "EPC") == "EPC" and rid not in frozen:
            out.append((rid, "issued revision", "WARN", "issued without a frozen delivery (use python -m engine doc issue)"))
    return out
