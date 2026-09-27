# references/
Codes, standards, textbooks and technical references (IEC, IEEE, ASME, EN, API, NFPA, ...).
Register each one: `python -m engine db add reference --set code="IEC 60076-1" --set title="Power transformers - General" --set edition=2011 --reason "..."`.
`aveva/DATABASE_STRUCTURE.ttl` is the AVEVA engineering class library - the project standard for tag classes,
attributes, units and value lists. It is compiled into `database/classlib/` with
`python -m engine lib build references/aveva/DATABASE_STRUCTURE.ttl --reason "..."`; validation fails if either side changes alone.

Licensed standards must not be redistributed: commit only what the licence allows; otherwise record the reference without the file.
