"""Piping PCF files: one <line>.pcf per routed line + the attribute map.

Consumers (import into, never edited by hand):
  AutoCAD Plant 3D  - PCF import (isometric / model)
  CAESAR II         - PCF interface -> stress model (map COMPONENT-ATTRIBUTEn once, see _PCF_ATTRIBUTE_MAP.txt)
  AFT Fathom/Arrow  - PCF import -> hydraulic model (same attribute map)
Options: lines=L1,L2  only these lines.
"""
from __future__ import annotations

from ..core import pcf
from ..core.runner import Context, Engine


class PipingPCF(Engine):
    name = "piping_pcf"
    title = "Piping PCF per line (Plant 3D, CAESAR II, AFT import) + attribute map"
    version = "1.0.0"
    inputs = ["project", "line", "pipe_component", "pipe_spec", "pipe_size"]
    formats = ["pcf", "txt"]

    def run(self, ctx: Context):
        s = ctx.store
        lines = [l for l in s.records("line") if l.get("status") != "deleted"]
        if ctx.options.get("lines"):
            want = set(ctx.options["lines"].split(","))
            lines = [l for l in lines if l["id"] in want]
        files = []
        for l in lines:
            text, warns = pcf.write(s, l["id"], ctx.project_record()["id"])
            ctx.warnings += warns
            f = ctx.out_dir / f"{l['id']}.pcf"
            f.write_bytes(text.encode("ascii", errors="replace"))
            files.append(f)
        m = ctx.out_dir / "_PCF_ATTRIBUTE_MAP.txt"
        m.write_bytes(pcf.attribute_map_text().encode("ascii"))
        return files + [m]


ENGINE = PipingPCF()
