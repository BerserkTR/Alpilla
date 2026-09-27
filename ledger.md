# Ledger - Lessons Learned
<!-- GENERATED from database/records/lesson by `python -m engine run governance`. DO NOT EDIT.
     Change with: python -m engine db add|update lesson ... --reason "..." -->

Read before working. Add a lesson whenever something went wrong or a better way was found:
`python -m engine db add lesson --set title="..." --set lesson="..." --reason "..."`

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
