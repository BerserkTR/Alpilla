"""Document titles: '<Subject> - <Document Type>' in title case; explanations in brackets go to the description.

  split("Process design criteria (design margins, design pressure)") -> ("Process design criteria", ["design margins, design pressure"])
  proper("MV switchgear 10.5 kV - technical specification") -> "MV Switchgear 10.5 kV - Technical Specification"
  swap("Technical specification - MV switchgear") -> "MV switchgear - Technical specification"
Words with capitals or digits (KKS codes, units such as kV, H2/CO2) and lowercase units are kept as written."""
from __future__ import annotations

import re

MINOR = {"a", "an", "and", "or", "of", "for", "to", "in", "on", "at", "by", "with", "incl.", "per", "the", "from", "vs",
         "via", "as", "into", "e.g.", "i.e.", "and/or", "nor", "than", "under", "over", "between", "within", "without"}
UNITS = {"mm", "m", "cm", "km", "kg", "t", "bar", "barg", "bara", "h", "s", "min", "ppm", "mg", "g", "l", "wd", "kw", "mw"}
KEEP = {"kw": "kW", "mw": "MW", "kv": "kV", "kva": "kVA", "mva": "MVA", "ph": "pH", "dc": "DC", "ac": "AC", "hv": "HV",
        "mv": "MV", "lv": "LV", "i/o": "I/O", "p&id": "P&ID", "p&ids": "P&IDs"}


def split(text: str) -> tuple[str, list[str]]:
    """Title without bracketed parts, and the bracketed parts (outermost level) in order."""
    out, parts, depth, buf = [], [], 0, ""
    for ch in text:
        if ch == "(":
            if depth == 0:
                buf = ""
            else:
                buf += ch
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth == 0:
                parts.append(buf.strip())
            else:
                buf += ch
        elif depth:
            buf += ch
        else:
            out.append(ch)
    t = re.sub(r"\s+", " ", "".join(out)).strip()
    t = re.sub(r"\s+([,:;])", r"\1", t).strip(" -,:;")
    return t, [p for p in parts if p]


def _word(w: str, first: bool) -> str:
    low = w.lower()
    if low in KEEP:
        return KEEP[low]
    if any(c.isdigit() for c in w) or any(c.isupper() for c in w[1:]) or (w[:1].isupper() and len(w) > 1 and w.isupper()):
        return w
    if low in UNITS and not first:
        return w
    if low in MINOR and not first:
        return low
    if "-" in w and not w.startswith("-"):
        return "-".join(_word(p, first and i == 0) if p else p for i, p in enumerate(w.split("-")))
    if "/" in w:
        return "/".join(_word(p, first and i == 0) if p else p for i, p in enumerate(w.split("/")))
    return w[:1].upper() + w[1:]


def proper(text: str) -> str:
    """Title case: every word capitalised except minor words and units; codes and acronyms unchanged. Each segment
    after ' - ' or ': ' starts with a capital."""
    segs = re.split(r"(\s-\s|:\s)", text)
    out = []
    for s in segs:
        if s in (" - ", ": ") or re.fullmatch(r"\s-\s|:\s", s or ""):
            out.append(s)
            continue
        words = s.split(" ")
        out.append(" ".join(_word(w, i == 0) if w else w for i, w in enumerate(words)))
    return "".join(out)


def swap(text: str, prefixes) -> str:
    """'<Type> - <Subject>' -> '<Subject> - <Type>' when the part before the first ' - ' is a known type phrase."""
    if " - " not in text:
        return text
    head, rest = text.split(" - ", 1)
    if head.strip().lower() in prefixes:
        return f"{rest.strip()} - {head.strip()}"
    return text


def make(text: str, prefixes=()) -> tuple[str, str | None]:
    """(proper title, description or None) from a raw title."""
    t, parts = split(text)
    t = proper(swap(t, prefixes))
    return t, ("; ".join(parts) or None)
