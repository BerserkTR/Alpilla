"""Runs engines and proves their outputs.

Each run replaces output/<engine>/ and writes output/<engine>/_manifest.json with
the sha256 of every file, the engine version and a fingerprint of the entities it read.
check_outputs() flags any file not produced by an engine (hand-made / hand-edited)
and any output whose input data has changed since it was generated (stale).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .project import Project
from .store import Store, now

MANIFEST = "_manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(root: Path) -> str:
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "uncommitted"


@dataclass
class Context:
    project: Project
    store: Store
    out_dir: Path
    options: dict
    stamp: dict           # generation info to print on every deliverable
    warnings: list = field(default_factory=list)

    def template(self, *parts) -> Path:
        return self.project.templates.joinpath(*parts)

    def project_record(self) -> dict:
        recs = self.store.records("project")
        return recs[0] if recs else {"id": "PROJECT-TBD", "name": "Project not yet defined in database"}


class Engine:
    """Base class. Subclasses set name/title/version/inputs and implement run(ctx) -> [paths]."""
    name = ""
    title = ""
    version = "1.0.0"
    inputs: list[str] = []
    formats: list[str] = []

    def run(self, ctx: Context) -> list[Path]:
        raise NotImplementedError


def run_engine(project: Project, store: Store, engine: Engine, options: dict | None = None) -> dict:
    from . import validate
    rep = validate.Report()
    validate.records(store, rep)
    validate.integrity(store, rep)
    if rep.errors:
        raise RuntimeError("database is not valid - fix before generating outputs:\n" + rep.text(15))

    if engine.name == "governance":  # writes rules.md / ledger.md at repo root, verified by re-rendering
        files = engine.run(Context(project, store, project.root, options or {}, {}))
        return {"engine": engine.name, "files": [project.rel(f) for f in files], "warnings": []}

    out_dir = project.output / engine.name
    tmp = project.output / f".{engine.name}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    stamp = {"engine": engine.name, "engine_version": engine.version, "generated_at": now(),
             "generated_by": store.who.code, "inputs_hash": store.entity_hash(engine.inputs),
             "db_hash": store.db_hash(), "git_commit": git_head(project.root)}
    ctx = Context(project, store, tmp, options or {}, stamp)
    try:
        files = engine.run(ctx)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    manifest = {**stamp, "inputs": sorted(engine.inputs), "options": options or {},
                "files": {f.relative_to(tmp).as_posix(): sha256(f) for f in sorted(files)},
                "warnings": ctx.warnings}
    (tmp / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.rmtree(out_dir, ignore_errors=True)
    tmp.rename(out_dir)
    return manifest


def check_outputs(project: Project, store: Store) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    out = project.output
    if not out.is_dir():
        return issues
    from ..engines import registry
    engines = registry()
    for d in sorted(out.iterdir()):
        if d.name in ("README.md", ".gitkeep") or d.name.startswith("."):
            continue
        if d.is_file():
            issues.append(("error", f"output/{d.name}: loose file not produced by an engine - delete it"))
            continue
        mf = d / MANIFEST
        if not mf.exists():
            issues.append(("error", f"output/{d.name}/: no manifest - not engine output. Delete it and use `python -m engine run`"))
            continue
        m = json.loads(mf.read_text(encoding="utf-8"))
        listed = m.get("files", {})
        for f in sorted(p for p in d.rglob("*") if p.is_file() and p.name != MANIFEST):
            rel = f.relative_to(d).as_posix()
            if rel not in listed:
                issues.append(("error", f"output/{d.name}/{rel}: not produced by engine '{d.name}' (hand-made)"))
            elif sha256(f) != listed[rel]:
                issues.append(("error", f"output/{d.name}/{rel}: modified after generation (hand-edited). Re-run the engine"))
        for rel in listed:
            if not (d / rel).exists():
                issues.append(("warn", f"output/{d.name}/{rel}: listed in manifest but missing"))
        eng = engines.get(d.name)
        if eng is None:
            issues.append(("warn", f"output/{d.name}/: engine no longer exists"))
        elif m.get("engine_version") != eng.version or m.get("inputs_hash") != store.entity_hash(m.get("inputs", [])):
            issues.append(("warn", f"output/{d.name}/: STALE - database or engine changed since generation. "
                                   f"Re-run: python -m engine run {d.name}"))
    return issues


def pdf_from_office(src: Path, ctx: Context) -> Path | None:
    """Convert .docx/.xlsx to PDF with LibreOffice if available; otherwise record a warning."""
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        ctx.warnings.append(f"PDF of {src.name} skipped: LibreOffice (soffice) not installed")
        return None
    import tempfile
    with tempfile.TemporaryDirectory() as prof:  # private profile: works even while the user has LibreOffice open
        r = subprocess.run([exe, "--headless", f"-env:UserInstallation={Path(prof).as_uri()}", "--convert-to", "pdf",
                            "--outdir", str(src.parent), str(src)], capture_output=True, text=True, timeout=300)
    pdf = src.with_suffix(".pdf")
    if r.returncode != 0 or not pdf.exists():
        msg = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["no output"]
        hint = " (LibreOffice Writer/Calc component missing? e.g. apt install libreoffice-writer-nogui)" \
            if "could not be loaded" in msg[0] else ""
        ctx.warnings.append(f"PDF of {src.name} failed: {msg[0][:200]}{hint}")
        return None
    return pdf
