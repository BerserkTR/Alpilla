# Brief: preliminary equipment sizing data for the Equipment List (Alpilla 600 MW CCGT, EPC case study)

You are a senior plant engineer drafting preliminary equipment data for the Equipment List (IFR rev A) of a 1 x 1
multi-shaft combined cycle (one 9H-class-like gas turbine ~418 MW, 3-pressure reheat HRSG with SCR, reheat condensing
steam turbine ~200 MW, once-through seawater cooling, Black Sea coast of Turkey, site grade 15 m a.s.l.).
Net output 600 MW, net heat rate 5,860 kJ/kWh. Natural gas main fuel, LDO back-up (500 h/y, 72 h autonomy).

## Rules (binding)
- READ ONLY. Never write to the database, never edit repository files. Work in the repository at /home/user/Alpilla.
- Query data only with the CLI (keep outputs small): 
  `python -m engine db get equipment <tag>`, `python -m engine db query "SELECT ... FROM equipment WHERE system IN (...)" --limit 200`,
  `python -m engine db query "SELECT id, parameter, value, value_text, unit, condition FROM design_parameter" --limit 200`,
  `python -m engine db query "SELECT number, description, fluid, from_node, to_node, mass_flow, pressure, temperature FROM process_stream WHERE hmb_case='SRC-NG-100'" --limit 100`
  (other cases: `python -m engine db query "SELECT id, title FROM hmb_case"`, e.g. SUM-NG-100 summer, WIN-NG-100 winter, SRC-LDO-100 on LDO),
  `python -m engine db query "SELECT id, description, method, power, head, node, pump_efficiency, motor_efficiency FROM aux_load WHERE hmb_case='SRC-NG-100'"`,
  `python -m engine db get system <id>` (system records carry quantity notes), `python -m engine db query "SELECT id, title, package_type, supply FROM mr"`.
- The heat and mass balance (process_stream) and the aux_load records are the operating basis. Your rated values must
  be consistent with them: rated flow >= max operating flow over the cases with the usual margin (pumps +10 % flow,
  +5-10 % head), motor rating = shaft power / motor efficiency rounded UP to the next IEC standard motor size
  (e.g. 0.75, 1.1, 1.5, 2.2, 3, 4, 5.5, 7.5, 11, 15, 18.5, 22, 30, 37, 45, 55, 75, 90, 110, 132, 160, 200, 250, 315,
  355, 400, 450, 500, 560, 630, 710, 800, 900, 1000, 1120, 1250, 1400, 1600, 1800, 2000, 2240, 2500, 2800, 3150, 3550,
  4000, 4500, 5000, 5600, 6300 kW). Shaft power P = rho g Q H / eta.
- Motors >= 200 kW are MV (voltage 10000 V at the motor, 10.5 kV switchgear); below 200 kW LV 400 V. Put the motor
  voltage in `voltage` (V) for driven equipment.
- Seawater service materials: super duplex / 6Mo / titanium / GRP / rubber-lined CS as appropriate; marine C5 atmosphere.
- Design pressure (barg): max of (shut-off pressure incl. max suction) and operating + 10 %, rounded up sensibly; for
  atmospheric tanks use 0 (atm) and state 'atmospheric' in remarks; design temperature: max operating + 15-30 K
  (min 50 degC for ambient water services, 65 degC for sun-exposed storage).
- Existing rated_power values were rough placeholders. Keep them only if consistent with your sizing; if you change
  one, the remarks must say why (e.g. 'rated 1,250 kW: 18,500 m3/h x 16 m / 0.87 = 950 kW shaft').
- Tanks: capacity in m3 from autonomy / hold-up requirements (state the basis, e.g. demin tank = 2 x ... for 24 h makeup
  + HRSG fill), dimensions not needed. Heat exchangers: duty in kW as capacity. Fans: capacity in m3/h (actual) plus
  rated_power. Compressors: Nm3/h. Cranes: capacity in t (SWL). Transformers / switchgear / UPS / batteries / diesel:
  capacity in kVA / A / Ah / kVA as appropriate with voltage.
- `service` = short functional service text (e.g. 'Condenser cooling seawater supply'); `redundancy` e.g. '2 x 100 %',
  '3 x 50 %', '1 x 100 %'. `material` = main wetted / shell material. `location` = building or area name.
- Do not invent vendor names or models. Do not change tags, systems, MRs or descriptions.
- If you find an engineering inconsistency in the existing data (wrong redundancy, missing item, package split,
  implausible value, mismatch with the HMB), report it in `findings` - do not silently work around it.

## Output
Write ONE JSON file (path given in your task) with this structure and nothing else:
{"items": [{"id": "<tag>", "service": "...", "redundancy": "...", "capacity": 0, "capacity_unit": "...",
            "design_flow": 0 (t/h, fluids only), "head": 0 (m, pumps only), "design_pressure": 0, "design_temperature": 0,
            "material": "...", "rated_power": 0, "voltage": 0, "location": "...",
            "remarks": "sizing basis in one or two sentences, citing HMB stream numbers / aux_load ids / design parameters"}],
 "findings": ["..."]}
Omit a key when it does not apply (e.g. no head for a tank). Every tag of your systems must appear exactly once.
Finish with a 5-line summary in your final message: items done, values changed vs existing rated_power, findings count.
