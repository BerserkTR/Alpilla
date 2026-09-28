# Draft preliminary equipment sizing (not loaded)

Drafted per `BRIEF.md` for the Equipment List (ALP-EPC-00000-PR-LST-0001, wave 2). One file per system group:
A cooling / water-steam, B water treatment, C fuel / utilities / fire, D HVAC / electrical / I&C, E power island (IEC data).
Each file has `items` (service, redundancy, capacity, head, design pressure / temperature, material, rating, remarks with
the sizing basis) and `findings` (engineering inconsistencies found in the database).

Status: NOT in the database. The values are loaded only through `python -m engine db import equipment ... --update`
after the findings are resolved (decisions / TQs) and the values are checked. The IEC findings are already raised as
EPC review comments and TQ-IEC-025.
