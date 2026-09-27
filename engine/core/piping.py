"""Piping helpers shared by the piping engines (PCF, IFC, stress/hydraulic exports) and validation.

Wall thickness: line.wall_thickness if given, else the pipe_spec schedule wall (STD/XS) from pipe_size
(ASME B36.10M reference data). Components are in flow order by their 4-digit seq; supports sit on the
pipe and branches leave from TEE/OLET, so continuity is checked end2 -> end1 for in-line components only.
"""
from __future__ import annotations

import math

INLINE = {"PIPE", "ELBOW", "BEND", "TEE", "REDUCER-CONCENTRIC", "REDUCER-ECCENTRIC", "FLANGE", "GASKET",
          "VALVE", "INSTRUMENT"}
TOL = 1.0  # mm


def dist(a, b) -> float:
    return math.dist(a, b)


def size(store, dn: str) -> dict:
    s = store.get("pipe_size", dn)
    if s is None:
        raise ValueError(f"pipe size {dn} not in pipe_size reference data")
    return s


def line_props(store, line: dict) -> dict:
    spec = store.get("pipe_spec", line["spec"])
    sz = size(store, line["dn"])
    wall = line.get("wall_thickness")
    wall_src = "line"
    if wall is None:
        sched = (spec or {}).get("schedule", "STD")
        wall = sz.get("wall_xs" if sched == "XS" else "wall_std")
        wall_src = f"{sched} schedule (ASME B36.10M)"
    return {"od": sz["od"], "wall": wall, "wall_source": wall_src, "bore_id": sz["od"] - 2 * wall if wall else None,
            "spec": spec or {}, "size": sz}


def components(store, line_id: str) -> list[dict]:
    return sorted((c for c in store.records("pipe_component") if c["line"] == line_id), key=lambda c: c["seq"])


def od_of(store, comp: dict, line: dict, which: str = "dn") -> float:
    dn = comp.get(which) or (line["dn"] if which == "dn" else None)
    return size(store, dn)["od"] if dn else None


def continuity(store, line_id: str) -> list[str]:
    """Gaps/overlaps between consecutive in-line components and zero-length items."""
    issues = []
    prev = None
    for c in components(store, line_id):
        if c["type"] in INLINE and c.get("end1") and c.get("end2"):
            if dist(c["end1"], c["end2"]) < TOL and c["type"] not in ("GASKET",):
                issues.append(f"{line_id} seq {c['seq']} {c['type']}: zero length")
            if prev is not None and dist(prev["end2"], c["end1"]) > TOL:
                issues.append(f"{line_id}: gap of {dist(prev['end2'], c['end1']):.0f} mm between seq {prev['seq']} "
                              f"and {c['seq']}")
            prev = c
    return issues


def arc_points(p1, corner, p2, n: int = 8) -> list:
    """Points on the circular arc tangent to p1->corner and corner->p2 (PCF elbow: CENTRE-POINT = corner)."""
    v1 = [a - b for a, b in zip(p1, corner)]
    v2 = [a - b for a, b in zip(p2, corner)]
    l1, l2 = math.hypot(*v1), math.hypot(*v2)
    if l1 < TOL or l2 < TOL:
        return [p1, p2]
    u1 = [x / l1 for x in v1]
    u2 = [x / l2 for x in v2]
    cosang = max(-1.0, min(1.0, sum(a * b for a, b in zip(u1, u2))))
    theta = math.acos(cosang)                      # angle between the legs
    bisector = [a + b for a, b in zip(u1, u2)]
    bl = math.hypot(*bisector)
    if bl < 1e-9 or abs(math.sin(theta / 2)) < 1e-9:
        return [p1, p2]
    r = l1 * math.tan(theta / 2)                   # bend radius for tangent length l1
    centre = [c + b / bl * (r / math.sin(theta / 2)) for c, b in zip(corner, bisector)]
    a = [x - c for x, c in zip(p1, centre)]
    b = [x - c for x, c in zip(p2, centre)]
    ang = math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)) / (math.hypot(*a) * math.hypot(*b)))))
    pts = []
    for i in range(n + 1):
        t = i / n
        s1 = math.sin((1 - t) * ang) / math.sin(ang)
        s2 = math.sin(t * ang) / math.sin(ang)
        pts.append([c + s1 * x + s2 * y for c, x, y in zip(centre, a, b)])
    return pts
