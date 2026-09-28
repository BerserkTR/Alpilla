"""KKS identification (VGB-S-811) and the project document number: parsing and checking against the project key list.

Tag layout written without separators (record IDs):
  level 0  G        plant unit: 0 common / BOP, 1 GT + HRSG island, 2 ST island (project convention)
  level 1  F0       system prefix number (0)
           F1F2F3   function key (kks_key level 'function', incl. U structures)
           FN FN    system number (2 digits)                           e.g. 10MBA10, 00PAC10
  level 2  A1A2     equipment unit key (kks_key level 'equipment_unit')
           AN AN AN equipment unit number (3 digits)                   e.g. 00PAC10AP001
  level 3  B1B2     component key (kks_key level 'component')
           BN BN    component number (2 digits)                        e.g. 00PAC10AP001KP01
A system record is identified by G F0 F1F2F3 (e.g. 10MBA) or its group G F0 F1F2 (e.g. 10MB).

Document number: ALP-<ORG>-<KKS>-<DISC>-<TYPE>-<NNNN>
  ORG   originator code (EPC, IEC, OWN or a 3-character subsupplier code)
  KKS   system code G F0 F1F2F3 (e.g. 00PAC) or 00000 for plant-general documents
  DISC  discipline code (DISCIPLINES)
  TYPE  document type code (doc_type record)
  NNNN  running number per ORG-KKS-DISC-TYPE
"""
from __future__ import annotations

import re

UNITS = {"0": "common / balance of plant", "1": "GT + HRSG island", "2": "ST island"}
DISCIPLINES = {"GE": "general", "PR": "process", "ME": "mechanical", "PI": "piping", "EL": "electrical", "IC": "i_and_c",
               "CV": "civil", "SS": "structural", "HV": "hvac", "HS": "hse", "CM": "commissioning", "PC": "project_control"}
DISC_CODE = {v: k for k, v in DISCIPLINES.items()}
ORGS = {"EPC": "Istanbul EPC (consortium leader)", "IEC": "Imaginary Electric (consortium member)", "OWN": "Owner"}

TAG = re.compile(r"^(?P<G>[0-9])(?P<F0>[0-9])(?P<F>[A-Z]{3})(?P<FN>[0-9]{2})"
                 r"(?:(?P<A>[A-Z]{2})(?P<AN>[0-9]{3})(?:(?P<B>[A-Z]{2})(?P<BN>[0-9]{2}))?)?$")
SYSTEM = re.compile(r"^(?P<G>[0-9])(?P<F0>[0-9])(?P<F>[A-Z]{2,3})$")
DOCNO = re.compile(r"^ALP-(?P<ORG>[A-Z0-9]{3})-(?P<KKS>[0-9]{2}(?:[A-Z]{3}|000))-(?P<DISC>[A-Z]{2})-(?P<TYPE>[A-Z][A-Z0-9]{2})-"
                   r"(?P<SEQ>[0-9]{4})$")


def keys(store) -> dict[str, dict]:
    """{'F': {key: rec}, 'A': {...}, 'B': {...}} from the kks_key records (superseded keys excluded)."""
    out = {"F": {}, "A": {}, "B": {}}
    for r in store.records("kks_key"):
        if r.get("status") != "superseded":
            out[r["id"][0]][r["key"]] = r
    return out


def parse_tag(tag: str, kk: dict | None = None) -> tuple[dict | None, list[str]]:
    """Parse an equipment / instrument tag; returns (parts, errors). Keys are checked when the key list is given."""
    m = TAG.match(tag or "")
    if not m:
        return None, [f"'{tag}' is not a KKS tag (G F0 F1F2F3 FNFN [A1A2 ANANAN [B1B2 BNBN]])"]
    p = {k: v for k, v in m.groupdict().items() if v}
    errs = []
    if p["G"] not in UNITS:
        errs.append(f"{tag}: unit '{p['G']}' not in {sorted(UNITS)}")
    if kk is not None:
        if p["F"] not in kk["F"]:
            errs.append(f"{tag}: function key {p['F']} not in the project key list")
        if p.get("A") and p["A"] not in kk["A"]:
            errs.append(f"{tag}: equipment unit key {p['A']} not in the project key list")
        if p.get("B") and p["B"] not in kk["B"]:
            errs.append(f"{tag}: component key {p['B']} not in the project key list")
    p["system"] = p["G"] + p["F0"] + p["F"]
    return p, errs


def parse_system(code: str, kk: dict | None = None) -> tuple[dict | None, list[str]]:
    m = SYSTEM.match(code or "")
    if not m:
        return None, [f"'{code}' is not a KKS system code (G F0 F1F2[F3])"]
    p = m.groupdict()
    errs = []
    if p["G"] not in UNITS:
        errs.append(f"{code}: unit '{p['G']}' not in {sorted(UNITS)}")
    if kk is not None:
        known = kk["F"].keys()
        if len(p["F"]) == 3 and p["F"] not in known:
            errs.append(f"{code}: function key {p['F']} not in the project key list")
        if len(p["F"]) == 2 and not any(k.startswith(p["F"]) for k in known):
            errs.append(f"{code}: no function key of group {p['F']} in the project key list")
    return p, errs


def parse_docno(no: str) -> tuple[dict | None, list[str]]:
    m = DOCNO.match(no or "")
    if not m:
        return None, [f"'{no}' does not follow ALP-<ORG>-<KKS>-<DISC>-<TYPE>-<NNNN>"]
    p = m.groupdict()
    errs = []
    if p["DISC"] not in DISCIPLINES:
        errs.append(f"{no}: discipline code {p['DISC']} unknown")
    return p, errs


def check_document(doc: dict, doc_types: dict, systems: dict) -> list[str]:
    """Consistency of the number with the record: type, discipline, originator and KKS system."""
    p, errs = parse_docno(doc["id"])
    if not p:
        return errs
    if p["TYPE"] not in doc_types:
        errs.append(f"{doc['id']}: type {p['TYPE']} is not a doc_type")
    if doc.get("type_code") and doc["type_code"] != p["TYPE"]:
        errs.append(f"{doc['id']}: type_code {doc['type_code']} differs from the number")
    if DISCIPLINES.get(p["DISC"]) and doc.get("discipline") != DISCIPLINES[p["DISC"]]:
        errs.append(f"{doc['id']}: discipline {doc.get('discipline')} differs from the number ({p['DISC']})")
    if doc.get("originator") and doc["originator"] != p["ORG"]:
        errs.append(f"{doc['id']}: originator {doc['originator']} differs from the number")
    if p["KKS"].endswith("000"):
        if doc.get("system"):
            errs.append(f"{doc['id']}: plant-general number but system {doc['system']} set")
    elif doc.get("system") != p["KKS"]:
        errs.append(f"{doc['id']}: system {doc.get('system')} differs from the KKS part {p['KKS']}")
    elif p["KKS"] not in systems:
        errs.append(f"{doc['id']}: KKS system {p['KKS']} is not a system record")
    return errs


def next_number(existing: list[str], org: str, kks_code: str, disc: str, dtype: str) -> str:
    prefix = f"ALP-{org}-{kks_code}-{disc}-{dtype}-"
    used = [int(x[len(prefix):]) for x in existing if x.startswith(prefix) and x[len(prefix):].isdigit()]
    return f"{prefix}{(max(used) + 1 if used else 1):04d}"


def explain(tag: str, kk: dict) -> list[str]:
    """Human-readable breakdown of a tag or document number."""
    if tag.startswith("ALP-"):
        p, errs = parse_docno(tag)
        if not p:
            return errs
        return [f"originator {p['ORG']} ({ORGS.get(p['ORG'], 'subsupplier')})",
                f"KKS {p['KKS']}" + ("" if p["KKS"].endswith("000") else f" ({kk['F'].get(p['KKS'][2:], {}).get('title', '?')})"),
                f"discipline {p['DISC']} ({DISCIPLINES.get(p['DISC'], '?')})", f"type {p['TYPE']}", f"number {p['SEQ']}"] + errs
    p, errs = parse_tag(tag, kk)
    if not p:
        p, errs = parse_system(tag, kk)
        if not p:
            return errs
        return [f"unit {p['G']} ({UNITS.get(p['G'], '?')})",
                f"function {p['F']} ({kk['F'].get(p['F'], {}).get('title', 'group') if len(p['F']) == 3 else 'group'})"] + errs
    out = [f"unit {p['G']} ({UNITS.get(p['G'], '?')})", f"system {p['G']}{p['F0']}{p['F']}{p['FN']}: {kk['F'].get(p['F'], {}).get('title', '?')}"]
    if p.get("A"):
        out.append(f"equipment unit {p['A']}{p['AN']}: {kk['A'].get(p['A'], {}).get('title', '?')}")
    if p.get("B"):
        out.append(f"component {p['B']}{p['BN']}: {kk['B'].get(p['B'], {}).get('title', '?')}")
    return out + errs
