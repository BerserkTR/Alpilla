# Alpilla - Gas / Combined-Cycle Power Plant Engineering & Design

Team project - no personal work: everything is committed and pushed to the shared branch. The database is the single source of truth (SSOT); engines are the
only way to produce outputs. The rules and lessons below are loaded into every session
(start, resume, /clear, compaction) and are binding.

@rules.md
@ledger.md

## Working loop (every session)
1. `git pull`, then read the state printed by the session hook (`python -m engine status`).
2. Look data up through the index, not by opening record files:
   `python -m engine db list <entity> --where "..."`, `db get <entity> <id>`, `db query "SELECT ..."`.
   Fields/units: `python -m engine db schema <entity>`.
   AVEVA classes/attributes (project standard, from `references/aveva/`): `python -m engine lib find|show|attr|tree ...`;
   classify tags with `--set aveva_class="..." --attr "Rated Power=3200 kW"`.
   Schedule status / critical path without generating files: `python -m engine plan`.
3. Change data only via `python -m engine db add|update|delete|import ... --reason "..."`.
4. Generate outputs only via `python -m engine run <engine>` (`run --stale` after pulling); issue via `python -m engine deliver ...`.
   Piping routing from Plant 3D / E3D: `python -m engine db import-pcf <file> --line <id> --reason ...`.
   Issue a document only via `python -m engine doc issue <doc> --purpose ...` (checks its inputs; `doc status <doc>` says
   what blocks it); process gates: `python -m engine gate`.
5. New output type = new engine in `engine/engines/` (+ template in `templates/`, + test in `tests/`).
6. Record lessons as they happen: `python -m engine db add lesson --set title=... --set lesson=... --reason ...`.
7. `python -m engine validate` must pass before commit (pre-commit hook enforces it). Commit small, push often.

## Map
| Folder | Holds | Written by |
|---|---|---|
| `database/schema/` | entity definitions (fields, types, units) | people (reviewed change) |
| `database/records/` | one JSON per record - the SSOT | engine CLI only |
| `database/changelog/` | per-user append-only audit log | engine CLI only |
| `database/classlib/` | AVEVA class library compiled from `references/aveva/*.ttl` | `engine lib build` only |
| `engine/` | CLI, core, engines (the only output path) | people |
| `templates/` | Jinja/Word templates used by engines | people |
| `sources/` | inputs received (client/vendor/site), registered as `source` records | people |
| `references/` | codes, standards, literature, registered as `reference` records | people |
| `output/` | generated files + manifest (committed, shared) | engines only |
| `internal_deliveries/` | frozen issued packages + transmittal | `engine deliver` only |
| `temporary_codes/` | shared scratch scripts, never deliverables | anyone |
