"""Engine registry. Any module in this package that defines ENGINE (an Engine instance) is an engine.

To add an engine: copy equipment_list.py, set name/title/version/inputs, implement run(ctx),
write files only into ctx.out_dir, return the list of files. Bump `version` when output logic changes.
"""
from __future__ import annotations

import importlib
import pkgutil


def registry() -> dict:
    out = {}
    for m in pkgutil.iter_modules(__path__):
        if m.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.{m.name}")
        eng = getattr(mod, "ENGINE", None)
        if eng is not None:
            out[eng.name] = eng
    return dict(sorted(out.items()))
