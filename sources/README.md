# sources/
Inputs received from outside the team: client requirements, site/survey data, OEM/vendor documents,
grid code letters, fuel gas analyses. Files are kept exactly as received (never edited).

Register every file so it can be cited as a basis:
`python -m engine db add source --set title="..." --set originator="Client" --set file=sources/client/xyz.pdf --reason "received"`

Suggested sub-folders: `client/`, `site/`, `vendors/<vendor>/`, `authorities/`.
Large or confidential files: keep a pointer (path/URL) in the `source` record instead of committing them.
