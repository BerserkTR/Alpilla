# Project Rules
<!-- GENERATED from database/records/rule by `python -m engine run governance`. DO NOT EDIT.
     Change with: python -m engine db add|update rule ... --reason "..." -->

Mandatory rules bind every person and every AI session. Rule R-001 overrides everything else.

## R-001 [MANDATORY] Engines are the only way to generate outputs from the database
Every output (reports, lists, datasheets, drawings, calculations, rules.md, ledger.md) is produced by an engine in `engine/engines/` run with `python -m engine run <engine>`. Nothing in `output/` or `internal_deliveries/` is created or edited by hand, by a script outside the engine, or by an AI writing files directly. If no engine produces a needed output, build or extend the engine (with template and test) first.
_Why:_ Outputs stay reproducible, consistent with the single source of truth, and traceable to the data and engine version that made them.

## R-002 [MANDATORY] The database is the single source of truth and changes only through the engine CLI
All project data - design data, equipment, parameters, decisions, document register, sources, references, rules and lessons - lives in `database/records/`. Change it only with `python -m engine db add|update|delete|import|reconcile ... --reason "..."`. Never edit record or changelog files directly. Values used anywhere else come from the database, never retyped.
_Why:_ One place of truth; every change is attributed and explained in the changelog; hand edits are detected by `validate`.

## R-003 [MANDATORY] Team work only: one shared branch, pull before work, validate before commit, push after
This is a team project; no personal work. Everyone works on the shared main branch (no long-lived personal branches or local-only files). Start with `git pull` and `python -m engine status`; resolve every WARN it prints. `python -m engine validate` must pass before every commit (the pre-commit hook enforces it; never use --no-verify). After a merge, resolve reported parallel edits with `db reconcile` only after checking the merged content, and re-run stale outputs with `python -m engine run --stale`. Commit small and push immediately.
_Why:_ Keeps several users and AI sessions aligned on the same data and prevents silent lost updates.

## R-004 [MANDATORY] Every design value is traceable
Every design_parameter cites at least one basis (`source:`, `reference:` or `decision:` record) and carries a status (assumption, preliminary, confirmed). Input files go in `sources/`, standards in `references/`, each registered as a record. Agreed positions are recorded as `decision` records.
_Why:_ Engineering deliverables must be defensible and auditable.

## R-005 [MANDATORY] Query, do not read in bulk
Find data with `python -m engine db list|get|query` (compact, limited results) instead of opening many record files or pasting large outputs into a session. Keep rules and lessons short.
_Why:_ Saves tokens and context, and keeps every session working from the same current data.

## R-006 [MANDATORY] Scratch is shared, never a side channel
`temporary_codes/` is committed and visible to the whole team (no personal scripts). Nothing there may write to the database, output or deliveries, or produce a deliverable. Useful code is promoted into an engine or CLI command with a test; dead scratch is deleted.
_Why:_ Prevents unofficial side channels that bypass R-001 and R-002.

## R-007 [MANDATORY] Record lessons learned when they happen
When something goes wrong, is corrected, or a better way is found, add it: `python -m engine db add lesson --set title=... --set lesson=... --set action=... --reason ...`. ledger.md is regenerated automatically and loaded into every session.
_Why:_ The team and every future session learn from past mistakes instead of repeating them.
