"""PCF (Piping Component File, Alias/Intergraph ISOGEN format) writer and reader.

Writer: one PCF per line from line + pipe_component records. Stress / hydraulic data travels as
COMPONENT-ATTRIBUTEn on every component; ATTRIBUTE_MAP documents the numbering for the one-time
mapping in CAESAR II (PCF interface) and AFT Fathom/Arrow (PCF import).
Reader: parses a PCF (e.g. exported from AutoCAD Plant 3D or AVEVA E3D isometrics) into pipe_component
data for `python -m engine db import-pcf`.
"""
from __future__ import annotations

import re

from . import piping

ATTRIBUTE_MAP = [
    (1, "design pressure", "barg", lambda l, p: l.get("design_pressure")),
    (2, "design temperature", "degC", lambda l, p: l.get("design_temperature")),
    (3, "operating pressure", "barg", lambda l, p: l.get("operating_pressure")),
    (4, "operating temperature", "degC", lambda l, p: l.get("operating_temperature")),
    (5, "hydrotest pressure", "barg", lambda l, p: l.get("test_pressure")),
    (6, "pipe material", "-", lambda l, p: p["spec"].get("material")),
    (7, "corrosion allowance", "mm", lambda l, p: p["spec"].get("corrosion_allowance")),
    (8, "wall thickness", "mm", lambda l, p: p["wall"]),
    (9, "insulation thickness", "mm", lambda l, p: l.get("insulation_thickness") or 0),
    (10, "fluid density", "kg/m3", lambda l, p: l.get("fluid_density")),
    (11, "rating", "-", lambda l, p: p["spec"].get("rating")),
]
# SKEYs only where the ISOGEN default is unambiguous; others must be set on the component (skey field)
DEFAULT_SKEY = {"ELBOW": "ELBW", "BEND": "BEBW", "TEE": "TEBW", "REDUCER-CONCENTRIC": "RCBW",
                "REDUCER-ECCENTRIC": "REBW", "FLANGE": "FLWN", "FLANGE-BLIND": "FLBL", "VALVE": "VVFL"}
VALVE_SKEY = {"check": "CKFL"}


def nb(dn: str) -> int:
    return int(dn[2:])


def fmt(p, bore=None) -> str:
    s = " ".join(f"{v:.4f}" for v in p)
    return f"{s} {bore}" if bore is not None else s


def write(store, line_id: str, project_id: str) -> tuple[str, list[str]]:
    line = store.get("line", line_id)
    props = piping.line_props(store, line)
    comps = piping.components(store, line_id)
    warnings = []
    out = ["ISOGEN-FILES ISOGEN.FLS", "UNITS-BORE MM", "UNITS-CO-ORDS MM", "UNITS-WEIGHT KGS",
           "UNITS-BOLT-DIA MM", "UNITS-BOLT-LENGTH MM",
           f"PIPELINE-REFERENCE {line_id}", f"    PROJECT-IDENTIFIER {project_id}", f"    PIPING-SPEC {line['spec']}"]
    if line.get("insulation", "none") != "none":
        out.append(f"    INSULATION-SPEC {line['insulation'].upper()}")
    attrs = [(n, v(line, props)) for n, _, _, v in ATTRIBUTE_MAP]
    for c in comps:
        t = c["type"]
        bore = nb(c.get("dn") or line["dn"])
        out.append(t)
        if t == "SUPPORT":
            out.append(f"    CO-ORDS {fmt(c['end1'], bore)}")
            if c.get("tag"):
                out.append(f"    NAME {c['tag']}")
            out.append(f"    ITEM-DESCRIPTION {c['support_type']}")
        elif t == "OLET":
            out.append(f"    CENTRE-POINT {fmt(c['centre'])}")
            out.append(f"    BRANCH1-POINT {fmt(c['branch'], nb(c.get('dn2') or line['dn']))}")
        elif t in ("FLANGE-BLIND", "CAP"):
            out.append(f"    END-POINT {fmt(c['end1'], bore)}")
        else:
            bore2 = nb(c["dn2"]) if t.startswith("REDUCER") else bore
            out.append(f"    END-POINT {fmt(c['end1'], bore)}")
            out.append(f"    END-POINT {fmt(c['end2'], bore2)}")
            if t in ("ELBOW", "BEND", "TEE"):
                out.append(f"    CENTRE-POINT {fmt(c['centre'])}")
            if t == "TEE":
                out.append(f"    BRANCH1-POINT {fmt(c['branch'], nb(c.get('dn2') or line['dn']))}")
        skey = c.get("skey") or (VALVE_SKEY.get(c.get("valve_type")) if t == "VALVE" else None) or DEFAULT_SKEY.get(t)
        if skey:
            out.append(f"    SKEY {skey}")
        elif t not in ("PIPE", "SUPPORT", "GASKET"):
            warnings.append(f"{line_id} seq {c['seq']} {t}: no SKEY (set skey on the component for ISOGEN symbols)")
        if t == "VALVE":
            out.append(f"    ITEM-DESCRIPTION {c['valve_type']} VALVE")
        if c.get("tag") and t != "SUPPORT":
            out.append(f"    COMPONENT-IDENTIFIER {c['tag']}")
        if c.get("weight"):
            out.append(f"    WEIGHT {c['weight']}")
        for n, v in attrs:
            if v is not None:
                out.append(f"    COMPONENT-ATTRIBUTE{n} {v}")
    if not comps:
        warnings.append(f"{line_id}: no routed components - PCF has the header only")
    return "\r\n".join(out) + "\r\n", warnings


def attribute_map_text() -> str:
    rows = [f"COMPONENT-ATTRIBUTE{n:<3} {name} [{unit}]" for n, name, unit, _ in ATTRIBUTE_MAP]
    return ("PCF attribute map (Alpilla engine piping_pcf)\r\n"
            "Configure once: CAESAR II > PCF interface attribute mapping; AFT Fathom/Arrow > PCF import mapping.\r\n\r\n"
            + "\r\n".join(rows) + "\r\n")


# ------------------------------------------------------------------ reader
POINT_KEYS = {"END-POINT", "CENTRE-POINT", "BRANCH1-POINT", "CO-ORDS"}
KNOWN = {"PIPE", "ELBOW", "BEND", "TEE", "OLET", "REDUCER-CONCENTRIC", "REDUCER-ECCENTRIC", "FLANGE", "FLANGE-BLIND",
         "GASKET", "VALVE", "INSTRUMENT", "SUPPORT", "CAP"}
HEADER = {"ISOGEN-FILES", "UNITS-BORE", "UNITS-CO-ORDS", "UNITS-WEIGHT", "UNITS-BOLT-DIA", "UNITS-BOLT-LENGTH",
          "PIPELINE-REFERENCE", "MATERIALS", "MESSAGE-SQUARE", "MESSAGE-CIRCLE", "END-POSITION-OPEN",
          "END-POSITION-NULL", "END-CONNECTION-PIPELINE", "END-CONNECTION-EQUIPMENT"}


def parse(text: str, valve_type_default: str | None = None) -> tuple[list[dict], list[str]]:
    """PCF text -> list of component dicts (without line/seq). Unknown blocks are reported, not guessed."""
    units = "MM"
    blocks, cur = [], None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if not raw[0].isspace():
            key, _, rest = raw.strip().partition(" ")
            if key == "MATERIALS":        # material list follows the components - not geometry
                break
            cur = {"type": key, "rest": rest.strip(), "items": []}
            blocks.append(cur)
            if key == "UNITS-CO-ORDS":
                units = rest.strip().upper()
        elif cur is not None:
            k, _, v = raw.strip().partition(" ")
            cur["items"].append((k, v.strip()))
    if units not in ("MM",):
        raise ValueError(f"PCF uses UNITS-CO-ORDS {units}; only MM is supported (convert on export)")
    comps, skipped = [], []
    for b in blocks:
        t = b["type"]
        if t in HEADER:
            continue
        if t not in KNOWN:
            skipped.append(t)
            continue
        pts = {"END-POINT": [], "CENTRE-POINT": [], "BRANCH1-POINT": [], "CO-ORDS": []}
        c = {"type": t}
        for k, v in b["items"]:
            if k in POINT_KEYS:
                nums = [float(x) for x in v.split()]
                pts[k].append((nums[:3], int(round(nums[3])) if len(nums) > 3 else None))
            elif k == "SKEY":
                c["skey"] = v
            elif k == "COMPONENT-IDENTIFIER" or k == "NAME":
                c["tag"] = v
            elif k == "WEIGHT":
                c["weight"] = float(v)
            elif k == "ITEM-DESCRIPTION":
                c["_desc"] = v
        ep = pts["END-POINT"]
        if ep:
            c["end1"] = _r(ep[0][0])
            if ep[0][1]:
                c["dn"] = f"DN{ep[0][1]}"
        if len(ep) > 1:
            c["end2"] = _r(ep[1][0])
            if t.startswith("REDUCER") and ep[1][1]:
                c["dn2"] = f"DN{ep[1][1]}"
        if pts["CENTRE-POINT"]:
            c["centre"] = _r(pts["CENTRE-POINT"][0][0])
        if pts["BRANCH1-POINT"]:
            c["branch"] = _r(pts["BRANCH1-POINT"][0][0])
            if pts["BRANCH1-POINT"][0][1]:
                c["dn2"] = f"DN{pts['BRANCH1-POINT'][0][1]}"
        if t == "SUPPORT":
            co = pts["CO-ORDS"][0]
            c["end1"] = _r(co[0])
            desc = (c.pop("_desc", "") or "").upper()
            c["support_type"] = desc if desc in ("ANCHOR", "GUIDE", "REST", "LINE-STOP", "HANGER", "SPRING") else "REST"
            if desc not in ("ANCHOR", "GUIDE", "REST", "LINE-STOP", "HANGER", "SPRING"):
                c["_note"] = "support type not stated in PCF - imported as REST, check it"
        if t == "VALVE":
            desc = (c.pop("_desc", "") or "").lower()
            vt = next((v for v in ("gate", "globe", "check", "ball", "butterfly", "plug", "control", "relief", "needle")
                       if desc.startswith(v)), None)
            if vt is None and c.get("skey", "").startswith("CK"):
                vt = "check"
            vt = vt or valve_type_default
            if vt is None:
                raise ValueError(f"VALVE {c.get('tag', '')} at {c.get('end1')}: valve type not in PCF "
                                 f"(ITEM-DESCRIPTION/SKEY); give --valve-type")
            c["valve_type"] = vt
        c.pop("_desc", None)
        comps.append(c)
    return comps, sorted(set(skipped))


def _r(p):
    return [round(v, 1) if abs(v - round(v)) > 1e-6 else int(round(v)) for v in p]
