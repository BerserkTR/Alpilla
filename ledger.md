# Ledger - Lessons Learned
<!-- GENERATED from database/records/lesson by `python -m engine run governance`. DO NOT EDIT.
     Change with: python -m engine db add|update lesson ... --reason "..." -->

Read before working. Add a lesson whenever something went wrong or a better way was found:
`python -m engine db add lesson --set title="..." --set lesson="..." --reason "..."`

### L-EPCE-0003 (2026-09-28) Scale linetypes and text to the drawing, and pass the hatch style in set_pattern_fill [drawings, dxf, pdf, verification]
- Context: The plot plan at real site extents (170 m) took minutes and 1.6 GB: DASHED grid lines in mm units produced hundreds of thousands of dashes, and tags of fixed 300 mm height were unreadable; in the IEC GA drawings hatch lines crossed the labels because ezdxf set_pattern_fill resets hatch_style to 1 (holes ignored)
- Lesson: Drawing engines tested only on small fixtures hide scale problems; hatch islands need style=0 passed in set_pattern_fill itself
- Action: Set $LTSCALE and text heights from the drawing scale (plot_plan 1.1.0); call set_pattern_fill(..., style=0) for hatches with label holes; check every generated sheet automatically (labels inside the frame, overlaps) and then zoomed at print size

### L-EPCE-0002 (2026-09-28) Check every code citation in the requirements against the register, and permit lead times against need dates [standards, permits, authorities, schedule]
- Context: ER-01.07 referred to an Appendix A.19 that did not exist; six permits had 1-5 days float between approval and need; the EIA marine-works window (no works 1 May - 30 September) contradicted the first tie-in need date for the intake/outfall
- Lesson: A codes list and a permits list are only useful when they are data checked by an engine: every cited code must resolve to a register entry, every permit must have authority, legal basis, lead time and a need date tied to the schedule
- Action: Keep codes/standards as reference records and permits as permit records; run standards_register after every requirement or schedule change; read EIA conditions into need dates

### L-EPCE-0001 (2026-09-28) Tie-in conditions are numbers checked against the HMB and the upstream point, not text [tie-in, interfaces, hmb, vendor]
- Context: IEC IF-001 Rev 0 gave the ST inlet rated pressures as design (IF-06/10/12 below the HRSG outlets feeding them), had no terminal point for the attemperation spray water (HMB streams 29/30), and put IF-03 at 16 barg while the water-injection stream was at 60 bar(a); the Owner register lacked the plot handover, TSO and emission data links
- Lesson: Only structured tie-in data (barg/degC ranges, capacity, voltage, short circuit, upstream + chain dp, dates) checked by the tie_in_register engine against all HMB cases exposes these gaps; unmapped HMB streams and uncovered scope items show missing points
- Action: Fill every tie_in field, run tie_in_register, raise a TQ for every WARN and for unmapped boundary-crossing streams; set status agreed only with agreed_by and the TQ reference

### L-SETUP-0008 (2026-09-27) Output staleness must follow code changes, and field names must not be SQL keywords [engine, tooling, database]
- Context: An engine edit without a version bump left outputs looking current; a field named 'case' broke db list --where
- Lesson: Manifests now carry a code fingerprint (engine module + code_deps); SQL errors are reported cleanly
- Action: Declare code_deps (core modules, templates) on engines that use them; avoid SQL keywords (case, order, group, constraint) as field names

### L-SETUP-0007 (2026-09-27) Recompute vendor heat balances independently and check every node [hmb, vendor, process]
- Context: Recomputing the IEC heat balance node by node showed the piping temperature drops assumed by IEC implied 0.96 MW heat loss (EPC design 0.35 MW), and that the Owner reference LHV (48.4 MJ/kg) does not match its own composition (47.48 MJ/kg per ISO 6976)
- Lesson: Enthalpies, LHV and balances must be recalculated from p, T and composition - stated summary values hide inconsistencies
- Action: Load vendor stream data as process_stream records and run the hmb engine; raise a TQ for every WARN

### L-SETUP-0006 (2026-09-27) Check vendor guarantees back-to-back against the Owner guarantees with the EPC's own loads [hmb, guarantees, vendor]
- Context: IEC gross guarantees (614 MW / 5,745 kJ/kWh) looked comfortable, but with the EPC auxiliaries they gave 5,862 kJ/kWh net against the Owner's 5,860; found only by the hmb engine's guarantee-cover check
- Lesson: A vendor guarantee is only useful if, at its limit and with the EPC's balance-of-plant loads, the plant still meets the Owner guarantee
- Action: List Owner and vendor guarantees in hmb_case.check_refs; the hmb engine warns when the cover fails - resolve by TQ before the vendor contract is fixed

### L-SETUP-0005 (2026-09-27) Check drawing PDFs at print size and zoom, not by thumbnail [drawings, pdf, verification]
- Context: Owner drawings DWG-001/002 printed at about 150 x 120 mm instead of A3/A1: ezdxf finalize() shrinks the matplotlib figure; pattern hatches came out black (set_pattern_fill defaults to colour 7); hatch islands need the OUTERMOST path flag
- Lesson: A drawing is verified only after checking the PDF page size (pdfinfo) and zoomed crops of labels, legend and title block; low-resolution previews hide wrong colours and hide overlaps
- Action: dxfkit.save_pdf restores the paper size (tested in tests/test_drawings.py); pass color=BYLAYER to hatch fills; review every sheet with pdfinfo + zoomed pdftoppm crops before issue

### L-SETUP-0004 (2026-09-27) Cross-check Owner documents against the Employer's Requirements before signature [contract, requirements]
- Context: Contract case ALP-EPC-001: the Owner's own documents contradicted the draft contract in 16 places (stack height, seawater reference, gas LHV/pressure, sewer, grid date, LDO quality ...)
- Lesson: Conflicts between Owner data and requirements surface only when each requirement is traced to its source; resolved before signature they cost EUR 1.48M, after signature they become claims
- Action: Every requirement cites its source (basis_refs); run a TQ round per Owner document issue; record answers as clarification records and apply changes with the TQ as reason

### L-SETUP-0003 (2026-09-27) Keep source and reference files byte-for-byte in git [git, team]
- Context: The AVEVA class library TTL has CRLF line endings; git's text normalisation would have changed its sha256 in every fresh clone
- Lesson: Any file whose hash is checked (sources, references, class library source) must be stored with -text in .gitattributes
- Action: Add new source/reference folders under the existing -text rules; after adding a large source, verify with a fresh clone + python -m engine validate

### L-SETUP-0002 (2026-09-27) Write multi-line text with file tools, not shell heredocs [claude, tooling]
- Context: The Claude path guard blocks shell commands that look like writes into engine-owned paths; heredocs mixing prose and paths can trigger it
- Lesson: The guard is deliberately conservative; a block means use the engine CLI, or write non-protected files with the Write tool
- Action: Never work around a guard block with other shell tricks; if the block is wrong, fix the guard and its test (tests/test_guard.py)

### L-SETUP-0001 (2026-09-27) PDF export needs the LibreOffice Writer/Calc components [tooling, pdf]
- Context: Datasheet PDFs were missing: soffice was on PATH but installed without Writer, conversion failed with 'source file could not be loaded'
- Lesson: soffice on PATH is not enough; engines skip PDFs with a WARN line instead of failing
- Action: Install libreoffice-writer-nogui and libreoffice-calc-nogui (or full LibreOffice) and read the WARN lines after every engine run
