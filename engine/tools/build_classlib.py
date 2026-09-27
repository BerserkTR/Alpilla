"""Compile an AVEVA class library (Turtle/RDF, e.g. references/aveva/DATABASE_STRUCTURE.ttl)
into compact, reviewable JSON-lines reference data in database/classlib/.

    python -m engine lib build references/aveva/DATABASE_STRUCTURE.ttl --reason "..."

Output (sorted, deterministic, one object per line -> clean git diffs when AVEVA updates the library):
  classes.jsonl       id, label, parent, comment, cfihos/iso ids, attrs (directly defined attribute ids)
  attributes.jsonl    id, label, type (string|int|double|boolean|quantity), quantity, lov, discipline, flags
  enums.jsonl         id, label, closed, values
  quantities.jsonl    label, base unit, units
  associations.jsonl  id, label, domain classes, range classes
  manifest.json       source file + sha256, counts, sha256 of every compiled file
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

FILES = ("classes", "attributes", "enums", "quantities", "associations")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compile_ttl(ttl: Path) -> dict[str, list[dict]]:
    import rdflib
    from rdflib.collection import Collection
    from rdflib.namespace import OWL, RDF, RDFS, SKOS

    g = rdflib.Graph()
    g.parse(str(ttl), format="turtle")
    MOD = rdflib.Namespace("http://www.aveva.com/modelling#")
    XSD = "http://www.w3.org/2001/XMLSchema#"

    def lab(x):
        v = g.value(x, SKOS.prefLabel)
        return str(v) if v is not None else ""

    def aid(x):
        v = g.value(x, MOD.AVEVAID)
        return str(v) if v is not None else "URI-" + str(x).rsplit("#", 1)[-1]

    def members(node):
        """domain/range may be a class or an owl:unionOf list of classes."""
        if isinstance(node, rdflib.BNode):
            u = g.value(node, OWL.unionOf)
            return list(Collection(g, u)) if u is not None else []
        return [node]

    coo = set(g.subjects(RDF.type, MOD.ClassOfObject))
    cid = {c: aid(c) for c in coo}

    # --- attributes (datatype properties) and where they are defined
    direct = defaultdict(set)
    attributes = []
    for pr in set(g.subjects(RDF.type, RDF.Property)) - set(g.subjects(RDF.type, OWL.ObjectProperty)):
        rng = g.value(pr, RDFS.range)
        if rng is None:
            typ, qty = "string", None
        elif str(rng).startswith(XSD):
            typ, qty = {"string": "string", "int": "int", "double": "double", "boolean": "boolean"}.get(
                str(rng)[len(XSD):], "string"), None
        elif (rng, RDF.type, MOD.UnitQualifiedValue) in g:
            typ, qty = "quantity", lab(rng)
        else:
            typ, qty = "string", None
        a = {"id": aid(pr), "label": lab(pr), "type": typ}
        if qty:
            a["quantity"] = qty
        lov = g.value(pr, MOD.hasValidEnumeration)
        if lov is not None:
            a["lov"] = aid(lov)
        for key, pred in (("discipline", MOD.discipline), ("category", MOD.category)):
            v = g.value(pr, pred)
            if v is not None:
                a[key] = lab(v)
        for key, pred in (("hidden", MOD.isHidden), ("pseudo", MOD.isPseudo)):
            if str(g.value(pr, pred)).lower() == "true":
                a[key] = True
        c = g.value(pr, RDFS.comment)
        if c is not None:
            a["comment"] = str(c)
        for d in g.objects(pr, RDFS.domain):
            for m in members(d):
                if m in coo:
                    direct[m].add(a["id"])
        attributes.append(a)

    # --- classes
    classes = []
    for c in coo:
        parents = [cid[p] for p in g.objects(c, RDFS.subClassOf) if p in coo]
        d = {"id": cid[c], "label": lab(c), "parent": sorted(parents)[0] if parents else None,
             "attrs": sorted(direct.get(c, ()))}
        if len(parents) > 1:
            d["other_parents"] = sorted(parents)[1:]
        for key, pred in (("cfihos", MOD.CfihosID), ("iso15926", MOD.ISO15926Part4ID), ("pcardl", MOD.PoscCaesarID)):
            v = g.value(c, pred)
            if v is not None:
                d[key] = str(v)
        cm = g.value(c, RDFS.comment)
        if cm is not None:
            d["comment"] = str(cm)
        classes.append(d)

    # --- enumerations (items are typed with their enumeration class)
    enums = []
    for e in set(g.subjects(RDF.type, MOD.Enumeration)):
        vals = sorted({str(g.value(i, MOD.enumerationValue) or lab(i)) for i in g.subjects(RDF.type, e)})
        enums.append({"id": aid(e), "label": lab(e), "closed": str(g.value(e, MOD.closedEnumeration)).lower() == "true",
                      "values": vals})

    # --- quantities and units
    quantities = []
    qclasses = set(g.subjects(RDF.type, MOD.QuantityClass))

    def own_units(q):
        return sorted({str(g.value(u, MOD.unitSymbol) or lab(u)) for u in g.subjects(RDF.type, q)
                       if (u, RDF.type, MOD.Unit) in g})

    for q in qclasses:
        units = own_units(q)
        base = g.value(q, MOD.baseForConversion)
        shared_from = None
        if not units and base is not None:
            # e.g. Bore / GaugePressure: no units of their own, they use the unit family of their base unit
            owner = next((o for o in g.objects(base, RDF.type) if o in qclasses), None)
            if owner is not None:
                units, shared_from = own_units(owner), lab(owner)
        d = {"label": lab(q), "base": str(g.value(base, MOD.unitSymbol) or lab(base)) if base else None,
             "units": units}
        if shared_from:
            d["units_from"] = shared_from
        quantities.append(d)

    # --- associations (object properties, excluding generated inverses)
    associations = []
    inverses = set(g.subjects(RDF.type, MOD.autoGeneratedInverse))
    for op in set(g.subjects(RDF.type, OWL.ObjectProperty)) - inverses:
        dom = sorted({cid[m] for d in g.objects(op, RDFS.domain) for m in members(d) if m in coo})
        rng = sorted({cid[m] for r in g.objects(op, RDFS.range) for m in members(r) if m in coo})
        associations.append({"id": aid(op), "label": lab(op), "domain": dom, "range": rng})

    key = lambda d: (d.get("id") or d.get("label"), d.get("label"))
    return {"classes": sorted(classes, key=key), "attributes": sorted(attributes, key=key),
            "enums": sorted(enums, key=key), "quantities": sorted(quantities, key=lambda d: d["label"]),
            "associations": sorted(associations, key=key)}


def write(project, ttl: Path) -> dict:
    data = compile_ttl(ttl)
    out = project.database / "classlib"
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"source": project.rel(ttl), "source_sha256": sha256(ttl), "counts": {}, "files": {}}
    for name in FILES:
        f = out / f"{name}.jsonl"
        f.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in data[name]),
                     encoding="utf-8")
        manifest["counts"][name] = len(data[name])
        manifest["files"][f.name] = sha256(f)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
