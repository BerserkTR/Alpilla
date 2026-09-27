# output/ - engine-generated files only
Each engine writes `output/<engine>/` plus `_manifest.json` (file hashes, data fingerprint, engine version, user, git commit).
Committed and shared so the whole team sees the same current outputs. Hand-made or edited files here fail validation;
stale outputs (data changed since generation) are reported by `python -m engine status` - fix with `python -m engine run --stale`.
Merge conflict on an output file: never merge by hand - take either side, then re-run the engine.
To share or issue a result use `python -m engine deliver` (it copies into internal_deliveries).
