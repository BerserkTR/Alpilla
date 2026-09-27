# Alpilla

Engineering and design environment for a gas-fired / combined-cycle power plant, built so that several
people (and AI sessions) can work on one consistent data set.

**Principle:** all project data lives in `database/` (single source of truth). Every deliverable is
generated from it by an engine. Nothing in `output/` or `internal_deliveries/` is ever made or
edited by hand. See [rules.md](rules.md) and [ledger.md](ledger.md).

Team project: nobody keeps personal work. Everything (data, outputs, scratch) is committed and pushed to the
shared branch; `python -m engine status` warns about anything uncommitted, unpushed or not yet pulled.

## First time (per clone)
```bash
pip install -r requirements.txt          # LibreOffice (soffice) optional, for PDF
python -m engine setup --user-code ABC   # unique 2-8 char code per person; activates git hooks
python -m engine status
```
AI sessions (e.g. Claude Code on the web) run as a generic git user. Give each person's environment
the variable `ALPILLA_USER_CODE=<their code>` so their changes stay attributed to them.

## Daily use
```bash
git pull
python -m engine db schema equipment
python -m engine db add system --id 10MBA --set title="Gas turbine unit 1" --set category=gas_turbine --reason "initial breakdown"
python -m engine db add equipment --id 10MBV10AP001 --set description="Lube oil pump" --set system=10MBA \
       --set equipment_type=pump --set rated_power=75 --reason "GT OEM scope list rev B"
python -m engine db import equipment my_list.csv --reason "..."      # CSV headers = field names
python -m engine db list equipment --where "rated_power > 50"
python -m engine run --stale                                         # regenerate outdated outputs
python -m engine deliver equipment_list --title "Equipment list for review" --purpose "internal review" \
       --to "Mechanical lead" --reason "first issue"
python -m engine validate && git add -A && git commit -m "..." && git push
```

## How consistency across users is guaranteed
| Mechanism | What it prevents |
|---|---|
| One JSON file per record, sorted keys | binary merge conflicts; unreadable diffs |
| Schemas with types, units, enums, references | inconsistent or dangling data |
| Every change stamped (user, time, reason) in `database/changelog/<USER>.jsonl` | anonymous or unexplained changes; users never conflict on the log |
| Record hash must equal the logged hash | hand edits that bypass the engine |
| Parallel edits to one record detected after merge, then `db reconcile` | silent lost updates |
| Auto IDs carry the user code (`DP-ABC-0007`) | ID collisions between parallel branches |
| Output manifests (sha256 + data fingerprint) | hand-made, hand-edited or stale outputs |
| Delivery transmittals with hashes | changes to issued documents |
| pre-commit hook + Claude session/path hooks | all of the above slipping into git |

## Engines
`python -m engine engines` lists them. Included:

| Engine | Output |
|---|---|
| `equipment_list` | equipment list (xlsx) |
| `equipment_datasheets` | datasheets (docx + pdf) |
| `design_basis` | design basis report (md + html) with traceability |
| `aveva_export` | AVEVA Engineering / E3D tag import workbook (one sheet per AVEVA class) |
| `document_register` | master document register: latest issue, review codes, comments, lateness, progress (xlsx) |
| `schedule` | CPM schedule: Excel Gantt, interactive HTML Gantt, MS Project XML (Primavera P6 import) |
| `progress_report` | engineering progress S-curve (planned vs earned), KPIs, late documents (html) |
| `governance` | rules.md / ledger.md |

## Document control and planning
`document` (MDR line with planned IFR/IFA/IFC dates and weight) -> `document_revision` (each issue: rev, purpose,
date, review code, transmittal) -> `review_comment` (comment / response / close). `wbs` + `activity` (P6-style logic
`E-1010`, `E-1020:SS+5`, `E-1030:FF-2`, constraints, actuals, % complete or progress from linked deliverables).
`progress_rule` records set the % earned per issue step (contract specific). Schedule dates, float, document status
and progress are always computed, never typed: `python -m engine plan` for a quick look.
Add one by copying `engine/engines/equipment_list.py`; it is discovered automatically.

## Tests
`python -m pytest -q`
