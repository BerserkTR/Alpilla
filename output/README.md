# output/ - engine-generated files only
Each engine writes `output/<engine>/` plus `_manifest.json` (file hashes, data fingerprint, engine version, user, git commit).
Not committed: anyone regenerates it with `python -m engine run --all`. Hand-made or edited files here fail validation;
stale outputs (data changed since generation) are reported by `python -m engine status`.
To share or issue a result use `python -m engine deliver` (it copies into internal_deliveries).
