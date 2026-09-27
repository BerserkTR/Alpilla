# internal_deliveries/ - issued packages (committed, frozen)
Created only by `python -m engine deliver <engine> --title ... --purpose ... --to ... --reason ...`.
Each folder holds copies of engine outputs, `transmittal.json` (hashes, data fingerprint, who, why) and `TRANSMITTAL.md`.
Issued files are never changed: to revise, update the database, re-run the engine and deliver again.
