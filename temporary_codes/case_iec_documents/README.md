# Case study: simulated Imaginary Electric (IEC) vendor documents (case authoring aid, not a project tool)
The IEC documents in `sources/iec/` are simulated *received* vendor inputs (all fictional). These scripts made them; they write
only to the folder given on the command line, never to the database, `output/` or `internal_deliveries/`.

- `iec_model.py` - the vendor's power-island design model: GT energy balance (NASA polynomials), triple-pressure reheat HRSG
  solved by pinch/approach, steam turbine expansion and condenser (IAPWS-IF97), all via `engine/core/thermo.py`
- `iec_data.py <out.json> [revA]` - all vendor numbers in one JSON (SRC heat balance, streams, ambient and part-load tables);
  `revA` = with the EPC piping pressure/temperature drops agreed in TQ-IEC-003
- `iec_docs.py <data.json> <dir> [PER DS101 ...]` - Word + PDF (+ Excel) of the ten IEC documents; `IEC_REV=A` for a revision

Because datasheets, heat balance and interface data come from one model they are mutually consistent; the EPC checks them
independently with the `hmb` engine. Delete this folder when the case study is no longer needed.

Off-design (added for PER-003):
- `iec_offdesign.py` - rating model calibrated at PER-001 Rev B (fixed HRSG/condenser surfaces, sliding pressure, attemperation,
  LDO with water injection); reproduces the design point exactly. Requires scipy.
- `iec_cases.py <out.json> [revA]` - the nine HMB cases of IEC-ALP-PER-003 (Rev A: LDO with gas-operation air flow and
  water/fuel 0.60, MEL at 30 % GT load)
- `iec_data.py <out.json> revB` - PER-001 Rev B (corrected HRSG arrangement: IP SH after the HP evaporator, LP SH after the
  IP evaporator)
