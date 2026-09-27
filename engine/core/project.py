"""Project paths. Everything is resolved from one root so tests can use a temp copy."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Project:
    root: Path

    @classmethod
    def locate(cls) -> "Project":
        return cls(Path(os.environ.get("ALPILLA_ROOT") or DEFAULT_ROOT).resolve())

    # --- folders -------------------------------------------------------
    @property
    def database(self) -> Path: return self.root / "database"
    @property
    def schema_dir(self) -> Path: return self.database / "schema"
    @property
    def records_dir(self) -> Path: return self.database / "records"
    @property
    def changelog_dir(self) -> Path: return self.database / "changelog"
    @property
    def cache_dir(self) -> Path: return self.database / ".cache"
    @property
    def index_path(self) -> Path: return self.cache_dir / "index.sqlite"
    @property
    def output(self) -> Path: return self.root / "output"
    @property
    def deliveries(self) -> Path: return self.root / "internal_deliveries"
    @property
    def templates(self) -> Path: return self.root / "templates"
    @property
    def sources(self) -> Path: return self.root / "sources"
    @property
    def references(self) -> Path: return self.root / "references"
    @property
    def rules_md(self) -> Path: return self.root / "rules.md"
    @property
    def ledger_md(self) -> Path: return self.root / "ledger.md"

    def rel(self, p: Path) -> str:
        return Path(p).resolve().relative_to(self.root).as_posix()
