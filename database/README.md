# database/ - single source of truth
- `schema/<entity>.json` - field definitions (type, unit, required, enum values, references). Changing a schema changes the contract for everyone: do it in a reviewed commit and run `python -m engine validate`.
- `records/<entity>/<id>.json` - one record per file. **Written only by `python -m engine db ...`.**
- `changelog/<USERCODE>.jsonl` - append-only audit log per person. **Never edited.**
- `.cache/index.sqlite` - local query index, rebuilt automatically, not committed.

References inside records: single-target refs hold the id (`"system": "10MBA"`); multi-target refs hold `entity:id` (`"basis_refs": ["source:SRC-ABC-0001", "decision:DEC-ABC-0002"]`).

After a git merge, `python -m engine validate` reports records changed by two people in parallel. Check the merged file, then accept it with `python -m engine db reconcile <entity> <id> --reason "merged A and B changes"`.
