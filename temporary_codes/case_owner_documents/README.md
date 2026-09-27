# Case study: simulated Owner documents (case authoring aid, not a project tool)
The Owner's documents in `sources/owner/` are simulated *received* inputs for the case study (all fictional).
These scripts made them; they write only to the folder given on the command line, never to the database,
`output/` or `internal_deliveries/`.

- `owner_md/` - Owner text drafts (source text of the eight documents)
- `owner_docs.py <dir>` - Word + PDF per document (Owner cover, approval and revision tables), Excel data for MET/MAR/FUL
- `owner_drawings.py <dir>` - ALP-OWN-DWG-001 external connections (A3) and ALP-OWN-DWG-002 site and construction
  area plan (A1), DXF + PDF; tie-in positions follow the `tie_in` records

To reissue: run into a scratch folder, review every PDF page, copy into `sources/owner/`, then update the `source`
records through `python -m engine db update source ... --reason ...` (the Owner's user code for the role-play is OWNR).
Delete this folder when the case study is no longer needed.
