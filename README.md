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
| `pid` | P&ID sheets per P&ID document (DXF R2018 + PDF): symbol blocks with TAG attributes, routed lines, valves, ISA bubbles, off-page connectors |
| `plot_plan` | plot plan (DXF + PDF) in plant coordinates: footprints, pipe centrelines, grid |
| `model_ifc` | IFC4 plant model: equipment envelopes, pipe/elbow/reducer at true OD and wall, valves, supports, line systems, property sets |
| `piping_pcf` | one PCF per line + attribute map (stress/hydraulic data as COMPONENT-ATTRIBUTEn) |
| `contract_document` | contract (docx + pdf): agreement, conditions, appendices A-G from contract/requirement/guarantee/milestone/scope records |
| `clarification_register` | technical query registers (xlsx), one per contract (Owner contract, IEPC-IEC agreement): rounds, answers, outcomes, price effects, changed records |
| `requirements_matrix` | requirements traceability matrix (xlsx): requirement -> guarantee -> design data / equipment, coverage |
| `hmb` | heat and mass balance per `hmb_case` (DXF + PDF A1 diagram, Excel): IAPWS-IF97 / ideal-gas enthalpies, node mass and energy balances, auxiliary loads, net output and heat rate, checks against guarantees and limits |
| `tie_in_register` | tie-in / terminal point register (xlsx + docx + pdf): data card per point, checks of completeness, HMB envelope over all cases, Owner -> EPC -> IEC chain (pressure, design, flow, voltage, short circuit), dates and agreement |
| `governance` | rules.md / ledger.md |

Import: `python -m engine db import-pcf <file.pcf> --line <id> --reason "..."` reads routing from Plant 3D / E3D PCF.

## Tool interoperability (what is verified, what is not)
The "Not verified here" column and the native CII / AFT / `.simx` exports are **frozen** by decision `DEC-SETUP-0001`
(`python -m engine db get decision DEC-SETUP-0001`). Unfreeze by providing sample files and recording a new decision.

| Target tool | Route | Verified here | Not verified here |
|---|---|---|---|
| AutoCAD Plant 3D | DXF (P&ID, plot plan), PCF, IFC | DXF audit-clean, blocks + attributes; PCF format + round trip | opening/importing in Plant 3D |
| AVEVA E3D / AVEVA Engineering | IFC4 model; AVEVA tag workbook (class IDs, attribute IDs, units) | IFC4 schema validation (0 issues), all geometry tessellates | E3D IFC import settings; AVEVA Engineering import mapping |
| CAESAR II | PCF + `_PCF_ATTRIBUTE_MAP.txt` via the PCF interface | PCF content and attributes | CAESAR import itself; native `.cii` is **not** generated (strict fixed-format file that cannot be checked without CAESAR II) |
| AFT Fathom / Arrow | PCF import + attribute map | PCF content | AFT import; native AFT files are proprietary |
| AVEVA Process Simulation | - | - | `.simx` is proprietary: not generated. Planned route: import APS stream/equipment results (Excel/CSV export) into the database as `source` data |
| MS Project / Primavera P6 | MS Project XML (MSPDI) | XML structure, links, lags, constraints, calendar | opening in MS Project / P6 |

## Contract and requirements (case study)
Contract `ALP-EPC-001` (fictional): Owner Alpilla Enerji Üretim A.Ş.; Contractor = consortium of Istanbul EPC (leader) and
Imaginary Electric (power island). Stored as `party`, `contract`, `contract_clause`, `requirement` (Employer's Requirements
ER-01..ER-18), `guarantee` (PG-xx with LDs), `milestone` (payments), `scope_item` (split and terminal points), plus
Appendix E design data (`design_parameter` citing `requirement:ER-xx.yy`) and key dates (activities under WBS `ALP.KD`).
Design data and equipment trace to requirements through `basis_refs`; the RTM shows what is still untraced.
Owner-provided documents are in `sources/owner/` (registered as `source` records); the interface list is the `tie_in` register;
pre-signature technical queries are `clarification` records (Consortium role `CONS`, Owner role `OWNR` in the changelog),
listed by the `clarification_register` engine and in Appendix I of the contract.

## Vendor data and heat balance (case study)
Imaginary Electric's reference documents (datasheets, thermal performance, terminal points, division of responsibility,
interface requirements) are in `sources/iec/` as `source` records. The internal consortium agreement `ALP-CA-001`
(`contract.kind = consortium_agreement`) holds the IEC guarantees (`IG-xx`), the division of responsibility (`DR-xxx` scope
items), the IEC-EPC interfaces (`IF-xx` tie-ins) and the EPC-IEC queries (`TQ-IEC-nnn`, roles `EPCE` / `IECE`).
The plant heat balance is data: `hmb_case` (conditions, power-island outputs, `check_refs`), `process_stream` (node to node,
from the vendor's heat balance) and `aux_load`; the `hmb` engine recomputes and checks it (`engine/core/hmb.py`,
`engine/core/thermo.py`). The generators of the simulated vendor documents are in `temporary_codes/case_iec_documents/`.
Tie-ins (`TP-` Owner/Contractor, `IF-` EPC/IEC) carry the exact scope break, connection, isolation, protection, design and
operating envelope (barg / degC), capacity, electrical data, the HMB stream or power crossing the point (`hmb_stream`,
`hmb_metric`), the upstream point with the agreed pressure loss (`upstream`, `chain_dp`), dates (`available_by`,
`needed_by`) and the agreement (`status`, `agreed_by`, `agreed_ref`); `tie_in_register` checks them.

## Document control and planning
`document` (MDR line with planned IFR/IFA/IFC dates and weight) -> `document_revision` (each issue: rev, purpose,
date, review code, transmittal) -> `review_comment` (comment / response / close). `wbs` + `activity` (P6-style logic
`E-1010`, `E-1020:SS+5`, `E-1030:FF-2`, constraints, actuals, % complete or progress from linked deliverables).
`progress_rule` records set the % earned per issue step (contract specific). Schedule dates, float, document status
and progress are always computed, never typed: `python -m engine plan` for a quick look.
Add one by copying `engine/engines/equipment_list.py`; it is discovered automatically.

## Tests
`python -m pytest -q`
