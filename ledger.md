# Ledger - Lessons Learned
<!-- GENERATED from database/records/lesson by `python -m engine run governance`. DO NOT EDIT.
     Change with: python -m engine db add|update lesson ... --reason "..." -->

Read before working. Add a lesson whenever something went wrong or a better way was found:
`python -m engine db add lesson --set title="..." --set lesson="..." --reason "..."`

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
