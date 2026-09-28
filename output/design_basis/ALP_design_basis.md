# Alpilla 600 MW Combined Cycle Power Plant - Design Basis

| Item | Value |
|---|---|
| Project | ALP |
| Plant type | CCGT 1x1 multi-shaft, H-class GT, 3-pressure reheat HRSG, seawater cooling |
| Location | Northern Marmara coast, Türkiye |
| Generated | 2026-09-28T19:00:27Z by EPCE (design_basis v1.2.0) |
| Data fingerprint | 188045b6c33ac38c (git 876a108) |

This document is generated from the project database. Do not edit it; change the
`design_parameter` records and re-run `python -m engine run design_basis`.

## 1. Site

| ID | Parameter | Value | Unit | Condition | Status | Basis |
|---|---|---|---|---|---|---|
| DP-CASE-0003 | Atmospheric corrosivity category | C5 (ISO 12944-2), durability H | - |  | confirmed | ER-02.08 Corrosive coastal atmosphere |
| DP-CASE-0004 | Basic wind speed | 30.0 | m/s | 10 min mean, 10 m, 50-year return | confirmed | ER-02.05 Wind, snow and rain |
| DP-CASE-0006 | Design rainfall intensity | 110.0 | mm/h | 10 min, 25-year return | confirmed | ER-02.05 Wind, snow and rain |
| DP-OWNR-0046 | Distance to heavy-lift port | 18.0 | km by sea | 400 t quay crane | confirmed | SRC-OWNR-0005 Site, existing infrastructure and tie-in points |
| DP-CASE-0005 | Ground snow load | 0.75 | kN/m2 |  | confirmed | ER-02.05 Wind, snow and rain |
| DP-OWNR-0047 | Groundwater level | 13.5 | m a.s.l. | brackish, chloride 3,000-8,000 mg/l | confirmed | SRC-OWNR-0008 Geotechnical baseline summary |
| DP-OWNR-0045 | Heavy transport road limit | 120.0 | t gross | two bridges on the state road | confirmed | SRC-OWNR-0005 Site, existing infrastructure and tie-in points; ER-02.14 Access and transport |
| DP-EPCE-0004 | Height datum | TUDKA-99 orthometric heights (m a.s.l.) |  |  | confirmed | SRC-EPCE-0011 Topographic survey point listing - plot, temporary area TP-A1 and coastal strip |
| DP-EPCE-0001 | Plant grid origin in UTM zone 35N (E 0 / N 0) | E 541,250.000 m / N 4,532,480.000 m | m | TUREF (ITRF96), south-west plot corner | confirmed | SRC-EPCE-0011 Topographic survey point listing - plot, temporary area TP-A1 and coastal strip |
| DP-OWNR-0044 | Plot dimensions | 400 x 300 | m | 12.0 ha; usable about 10.6 ha | confirmed | SRC-OWNR-0005 Site, existing infrastructure and tie-in points; ER-02.01 Site location and area |
| DP-EPCE-0002 | Rotation plant grid to UTM grid | -0.3281 | deg | plant north = true north; grid convergence at site | confirmed | SRC-EPCE-0011 Topographic survey point listing - plot, temporary area TP-A1 and coastal strip |
| DP-EPCE-0003 | Scale factor plant grid to UTM | 0.999612 | - | combined UTM point scale and height factor | confirmed | SRC-EPCE-0011 Topographic survey point listing - plot, temporary area TP-A1 and coastal strip |
| DP-CASE-0002 | Seismic design PGA (DD-2, 475-year) | 0.45 | g | TBDY 2018, site-specific hazard study | confirmed | ER-02.06 Seismic design |
| DP-OWNR-0048 | Seismic site class | ZD (Vs30 = 240 m/s) | - | TBDY 2018 | confirmed | SRC-OWNR-0008 Geotechnical baseline summary |
| DP-CASE-0001 | Site grade level | 15.0 | m a.s.l. |  | confirmed | ER-02.01 Site location and area |

## 2. Ambient

| ID | Parameter | Value | Unit | Condition | Status | Basis |
|---|---|---|---|---|---|---|
| DP-CASE-0008 | Ambient temperature - maximum for full capability | 40.0 | degC |  | confirmed | ER-02.02 Ambient design range |
| DP-CASE-0007 | Ambient temperature - minimum for full capability | -8.0 | degC |  | confirmed | ER-02.02 Ambient design range |
| DP-CASE-0009 | Ambient temperature - survival range | -15 to +45 | degC |  | confirmed | ER-02.02 Ambient design range |
| DP-OWNR-0004 | Annual mean temperature (measured) | 14.9 | degC | 2015-2024 site mast | confirmed | SRC-OWNR-0001 Meteorological and ambient air data |
| DP-OWNR-0007 | Chloride deposition maximum | 420.0 | mg/m2/day | ISO 9225, category S3 | confirmed | SRC-OWNR-0001 Meteorological and ambient air data; ER-02.10 Airborne salt and dust |
| DP-OWNR-0009 | Ground flash density | 2.4 | flashes/km2/year | 26 thunderstorm days/year | confirmed | SRC-OWNR-0001 Meteorological and ambient air data; ER-02.12 Lightning |
| DP-OWNR-0010 | Performance test ambient range | 5 to 30 | degC |  | confirmed | SRC-OWNR-0001 Meteorological and ambient air data; ER-02.11 Design ambient points |
| DP-OWNR-0008 | PM10 maximum (event) | 260.0 | ug/m3 | Saharan dust episodes | confirmed | SRC-OWNR-0001 Meteorological and ambient air data; ER-02.10 Airborne salt and dust |
| DP-OWNR-0003 | Record maximum / minimum temperature | 39.6 / -11.4 | degC | 1960-2024 | confirmed | SRC-OWNR-0001 Meteorological and ambient air data |
| DP-OWNR-0006 | Sea-salt aerosol annual mean | 14.0 | ug/m3 | as NaCl | confirmed | SRC-OWNR-0001 Meteorological and ambient air data |
| DP-OWNR-0005 | Sea-salt aerosol maximum (event) | 165.0 | ug/m3 | as NaCl, lodos storms | confirmed | SRC-OWNR-0001 Meteorological and ambient air data; ER-02.10 Airborne salt and dust |
| DP-CASE-0010 | SRC ambient dry-bulb temperature | 15.0 | degC | Site Reference Conditions | confirmed | ER-02.03 Site Reference Conditions (SRC) |
| DP-CASE-0012 | SRC barometric pressure | 1011.5 | mbar | Site Reference Conditions | confirmed | ER-02.03 Site Reference Conditions (SRC) |
| DP-CASE-0011 | SRC relative humidity | 70.0 | % | Site Reference Conditions | confirmed | ER-02.03 Site Reference Conditions (SRC) |
| DP-OWNR-0001 | Summer design dry bulb (0.4 %) | 32.8 | degC | coincident RH 48 % | confirmed | SRC-OWNR-0001 Meteorological and ambient air data; ER-02.11 Design ambient points |
| DP-OWNR-0002 | Winter design dry bulb (99.6 %) | -4.8 | degC | coincident RH 88 % | confirmed | SRC-OWNR-0001 Meteorological and ambient air data; ER-02.11 Design ambient points |

## 3. Fuel Gas

| ID | Parameter | Value | Unit | Condition | Status | Basis |
|---|---|---|---|---|---|---|
| DP-OWNR-0033 | Booked gas capacity (firm) | 115000.0 | Sm3/h | 130,000 interruptible | confirmed | SRC-OWNR-0003 Natural gas quality and supply conditions |
| DP-OWNR-0032 | Exceptional minimum supply pressure | 40.0 | barg | max 72 h/year, 24 h notice | confirmed | SRC-OWNR-0003 Natural gas quality and supply conditions |
| DP-OWNR-0029 | Fuel gas superheat above dew points at GT skid | 28.0 | K | minimum | confirmed | ER-03.06 Natural gas contaminant limits |
| DP-CASE-0019 | Fuel LHV range | 44.2 to 50.0 | MJ/kg |  | confirmed | ER-03.02 Natural gas specification |
| DP-CASE-0022 | Gas supply pressure at terminal point | 45 to 70 | barg |  | confirmed | ER-03.03 Gas supply conditions at terminal point |
| DP-CASE-0023 | Gas supply temperature at terminal point | 5 to 25 | degC |  | confirmed | ER-03.03 Gas supply conditions at terminal point |
| DP-OWNR-0026 | H2S + COS limit | 5.0 | mg/Sm3 |  | confirmed | SRC-OWNR-0003 Natural gas quality and supply conditions; ER-03.06 Natural gas contaminant limits |
| DP-OWNR-0031 | Hydrocarbon dew point | -2.0 | degC (1-70 barg) | maximum | confirmed | SRC-OWNR-0003 Natural gas quality and supply conditions |
| DP-CASE-0021 | Hydrogen admixture capability | 5.0 | vol % | without modification; 10 vol % by future OEM retrofit (provisions included) | confirmed | ER-03.02 Natural gas specification |
| DP-OWNR-0027 | Mercury limit | 1.0 | ug/Sm3 | measured < 0.01 | confirmed | SRC-OWNR-0003 Natural gas quality and supply conditions; ER-03.06 Natural gas contaminant limits |
| DP-OWNR-0024 | Methane content range | 85.0 to 98.5 | mol % |  | confirmed | SRC-OWNR-0003 Natural gas quality and supply conditions; ER-03.02 Natural gas specification |
| DP-OWNR-0028 | Na + K, Pb, V in gas (network data) | < 0.005 (detection limit) | mg/Sm3 | not guaranteed by network operator | confirmed | SRC-OWNR-0003 Natural gas quality and supply conditions; ER-03.06 Natural gas contaminant limits |
| DP-CASE-0018 | Reference fuel LHV | 47.48 | MJ/kg | reference composition, ISO 6976, combustion reference 25 degC | confirmed | ER-03.02 Natural gas specification |
| DP-OWNR-0025 | Total sulphur limit | 30.0 | mg S/Sm3 | measured typical 4, max 17 | confirmed | SRC-OWNR-0003 Natural gas quality and supply conditions; ER-03.06 Natural gas contaminant limits |
| DP-OWNR-0030 | Water dew point | -8.0 | degC at 70 barg | maximum | confirmed | SRC-OWNR-0003 Natural gas quality and supply conditions |
| DP-CASE-0020 | Wobbe index range | 47 to 52 | MJ/Nm3 |  | confirmed | ER-03.02 Natural gas specification |

## 4. Backup Fuel

| ID | Parameter | Value | Unit | Condition | Status | Basis |
|---|---|---|---|---|---|---|
| DP-OWNR-0039 | LDO annual operating limit | 500.0 | h/year | back-up fuel status | confirmed | SRC-OWNR-0004 Secondary fuel: light diesel oil (LDO); SRC-OWNR-0007 Positive EIA decision - binding conditions |
| DP-OWNR-0038 | LDO autonomy at base load | 72.0 | h | two tanks of 50 % | confirmed | SRC-OWNR-0004 Secondary fuel: light diesel oil (LDO); ER-03.08 LDO unloading and storage |
| DP-OWNR-0034 | LDO LHV | 42.9 | MJ/kg | range 42.6-43.2 | confirmed | SRC-OWNR-0004 Secondary fuel: light diesel oil (LDO); ER-03.07 Light diesel oil specification and burner limits |
| DP-OWNR-0036 | LDO Na + K at GT inlet | 0.5 | mg/kg | maximum; as delivered up to 1.0 (history 1.8) | confirmed | SRC-OWNR-0004 Secondary fuel: light diesel oil (LDO); ER-03.07 Light diesel oil specification and burner limits |
| DP-OWNR-0040 | LDO resupply capacity | 25.0 | trucks/day | 30-36 m3 each | confirmed | SRC-OWNR-0004 Secondary fuel: light diesel oil (LDO) |
| DP-OWNR-0035 | LDO sulphur | 10.0 | mg/kg | maximum | confirmed | SRC-OWNR-0004 Secondary fuel: light diesel oil (LDO); ER-03.07 Light diesel oil specification and burner limits |
| DP-OWNR-0037 | LDO vanadium / lead / calcium at GT inlet | 0.5 / 1.0 / 2.0 | mg/kg | maximum | confirmed | SRC-OWNR-0004 Secondary fuel: light diesel oil (LDO); ER-03.07 Light diesel oil specification and burner limits |

## 5. Grid

| ID | Parameter | Value | Unit | Condition | Status | Basis |
|---|---|---|---|---|---|---|
| DP-OWNR-0050 | 380 kV voltage range | 360 to 410 | kV | 342-420 kV for up to 30 min | confirmed | SRC-OWNR-0006 Grid connection data |
| DP-OWNR-0051 | Connection capacity | 640.0 | MW export | 40 MW import | confirmed | SRC-OWNR-0006 Grid connection data |
| DP-CASE-0027 | Generator power factor range | 0.85 lagging to 0.95 leading | - | at rated active power | confirmed | ER-04.08 Reactive capability |
| DP-CASE-0024 | Grid connection voltage | 380.0 | kV | nominal | confirmed | ER-11.01 Grid connection |
| DP-CASE-0026 | Grid frequency | 50.0 | Hz | operating range 47.5 to 52.5 Hz per Grid Code | confirmed | ER-04.07 Frequency and voltage support |
| DP-OWNR-0049 | Short-circuit level at 380 kV (2029) | 12 (min) to 40 (max) | kA | future 50 kA (2035) | confirmed | SRC-OWNR-0006 Grid connection data |
| DP-CASE-0025 | Switchyard short-circuit rating | 50.0 | kA |  | confirmed | ER-11.01 Grid connection |

## 6. Performance

| ID | Parameter | Value | Unit | Condition | Status | Basis |
|---|---|---|---|---|---|---|
| DP-CASE-0031 | Auxiliary power consumption | 2.2 | % of gross | maximum, base load | confirmed | ER-04.10 Auxiliary power |
| DP-CASE-0032 | Load ramp rate | 35.0 | MW/min | minimum | confirmed | ER-04.05 Load ramp rate |
| DP-CASE-0033 | Minimum environmental load | 40.0 | % net output | maximum | confirmed | ER-04.06 Minimum environmental load |
| DP-CASE-0028 | Net electrical output (guaranteed) | 600.0 | MW | SRC, 380 kV terminal point | confirmed | ER-04.01 Net electrical output |
| DP-CASE-0029 | Net heat rate LHV (guaranteed) | 5860.0 | kJ/kWh | SRC | confirmed | ER-04.02 Net heat rate |
| DP-CASE-0030 | Net heat rate LHV at 60 % load (guaranteed) | 6250.0 | kJ/kWh | SRC | confirmed | ER-04.03 Part-load efficiency |

## 7. Water

| ID | Parameter | Value | Unit | Condition | Status | Basis |
|---|---|---|---|---|---|---|
| DP-OWNR-0022 | Condenser cleanliness factor (design) | 0.85 | - | HEI | confirmed | ER-07.07 Condenser design standard |
| DP-CASE-0015 | Condenser cooling water temperature rise | 7.0 | K | maximum, base load | confirmed | ER-07.04 Cooling water temperature rise |
| DP-OWNR-0021 | Condenser pressure at SRC (maximum) | 36.0 | mbar(a) | base load, seawater 16.0 degC | confirmed | ER-07.08 Condenser pressure |
| DP-OWNR-0023 | Condenser tube velocity | 1.8 to 2.2 | m/s | titanium | confirmed | ER-07.07 Condenser design standard |
| DP-OWNR-0019 | Jellyfish load design | 20.0 | kg/m3 | blooms June-September | confirmed | SRC-OWNR-0002 Seawater quality and marine conditions; ER-08.07 Jellyfish and mucilage |
| DP-OWNR-0016 | Pycnocline depth | 20 to 25 | m |  | confirmed | SRC-OWNR-0002 Seawater quality and marine conditions |
| DP-CASE-0017 | Residual chlorine at outfall | 0.1 | mg/l | maximum | confirmed | ER-08.04 Biofouling control |
| DP-OWNR-0018 | Seawater boron | 2.4 to 3.4 | mg/l |  | confirmed | SRC-OWNR-0002 Seawater quality and marine conditions |
| DP-OWNR-0014 | Seawater chloride - maximum (upper layer) | 14500.0 | mg/l |  | confirmed | SRC-OWNR-0002 Seawater quality and marine conditions |
| DP-OWNR-0015 | Seawater salinity range (upper layer) | 21.8 to 26.1 | PSU | lower layer 38.2 PSU below pycnocline | confirmed | SRC-OWNR-0002 Seawater quality and marine conditions |
| DP-OWNR-0011 | Seawater temperature at intake - annual mean (measured) | 15.4 | degC | 12 m depth, station M2 | confirmed | SRC-OWNR-0002 Seawater quality and marine conditions |
| DP-OWNR-0012 | Seawater temperature at intake - maximum | 27.0 | degC | August | confirmed | SRC-OWNR-0002 Seawater quality and marine conditions |
| DP-OWNR-0013 | Seawater temperature at intake - minimum | 6.9 | degC | February | confirmed | SRC-OWNR-0002 Seawater quality and marine conditions |
| DP-CASE-0013 | Seawater temperature range at intake | 6 to 27 | degC |  | confirmed | ER-02.04 Seawater conditions |
| DP-OWNR-0017 | Seawater TSS maximum (storm) | 140.0 | mg/l |  | confirmed | SRC-OWNR-0002 Seawater quality and marine conditions |
| DP-CASE-0014 | SRC seawater temperature | 16.0 | degC | Site Reference Conditions | confirmed | ER-02.03 Site Reference Conditions (SRC) |
| DP-CASE-0016 | Thermal plume excess at 100 m mixing zone | 3.0 | K | maximum | confirmed | ER-08.05 Thermal plume |
| DP-OWNR-0020 | Wave height Hs 50-year | 4.4 | m | Tp 8.5 s, SW | confirmed | SRC-OWNR-0002 Seawater quality and marine conditions |

## 8. Emissions

| ID | Parameter | Value | Unit | Condition | Status | Basis |
|---|---|---|---|---|---|---|
| DP-CASE-0041 | CO | 30.0 | mg/Nm3 | dry, 15 % O2, 50-100 % GT load | confirmed | ER-14.02 Air emissions |
| DP-OWNR-0043 | Dust on LDO | 5.0 | mg/Nm3 | dry, 15 % O2 | confirmed | SRC-OWNR-0007 Positive EIA decision - binding conditions; ER-14.02 Air emissions |
| DP-CASE-0042 | NH3 slip | 5.0 | mg/Nm3 | dry, 15 % O2 | confirmed | ER-14.02 Air emissions |
| DP-CASE-0040 | NOx (as NO2) | 30.0 | mg/Nm3 | dry, 15 % O2, 50-100 % GT load | confirmed | ER-14.02 Air emissions |
| DP-OWNR-0041 | NOx on LDO | 50.0 | mg/Nm3 | dry, 15 % O2 | confirmed | SRC-OWNR-0007 Positive EIA decision - binding conditions; ER-14.02 Air emissions |
| DP-OWNR-0042 | SO2 on LDO | 10.0 | mg/Nm3 | dry, 15 % O2 | confirmed | SRC-OWNR-0007 Positive EIA decision - binding conditions; ER-14.02 Air emissions |
| DP-CASE-0043 | Stack height | 65.0 | m | EIA decision (approved dispersion study) | confirmed | ER-06.06 Stack; SRC-OWNR-0007 Positive EIA decision - binding conditions |

## 9. Noise

| ID | Parameter | Value | Unit | Condition | Status | Basis |
|---|---|---|---|---|---|---|
| DP-CASE-0044 | Near-field noise | 85.0 | dB(A) | 1 m from equipment | confirmed | ER-14.03 Near-field noise |
| DP-CASE-0045 | Noise at nearest receptor (night) | 45.0 | dB(A) | LAeq night | confirmed | ER-14.04 Environmental noise |

## 10. Operation

| ID | Parameter | Value | Unit | Condition | Status | Basis |
|---|---|---|---|---|---|---|
| DP-CASE-0039 | Cold start time to base load | 180.0 | min | maximum | confirmed | ER-04.04 Start-up times |
| DP-CASE-0034 | Design life | 30.0 | years |  | confirmed | ER-01.03 Design life and operating regime |
| DP-CASE-0037 | Hot start time to base load | 45.0 | min | maximum | confirmed | ER-04.04 Start-up times |
| DP-CASE-0035 | Operating hours per year | 8000.0 | EOH/year |  | confirmed | ER-01.03 Design life and operating regime |
| DP-CASE-0036 | Starts per year | 250.0 | starts/year | 50 cold, 100 warm, 100 hot | confirmed | ER-01.03 Design life and operating regime |
| DP-CASE-0038 | Warm start time to base load | 90.0 | min | maximum | confirmed | ER-04.04 Start-up times |

## Open assumptions (0 of 100)

_None - all parameters are preliminary or confirmed._

## Basis documents cited

- ER-01.03 Design life and operating regime (requirement)
- ER-02.01 Site location and area (requirement)
- ER-02.02 Ambient design range (requirement)
- ER-02.03 Site Reference Conditions (SRC) (requirement)
- ER-02.04 Seawater conditions (requirement)
- ER-02.05 Wind, snow and rain (requirement)
- ER-02.06 Seismic design (requirement)
- ER-02.08 Corrosive coastal atmosphere (requirement)
- ER-02.10 Airborne salt and dust (requirement)
- ER-02.11 Design ambient points (requirement)
- ER-02.12 Lightning (requirement)
- ER-02.14 Access and transport (requirement)
- ER-03.02 Natural gas specification (requirement)
- ER-03.03 Gas supply conditions at terminal point (requirement)
- ER-03.06 Natural gas contaminant limits (requirement)
- ER-03.07 Light diesel oil specification and burner limits (requirement)
- ER-03.08 LDO unloading and storage (requirement)
- ER-04.01 Net electrical output (requirement)
- ER-04.02 Net heat rate (requirement)
- ER-04.03 Part-load efficiency (requirement)
- ER-04.04 Start-up times (requirement)
- ER-04.05 Load ramp rate (requirement)
- ER-04.06 Minimum environmental load (requirement)
- ER-04.07 Frequency and voltage support (requirement)
- ER-04.08 Reactive capability (requirement)
- ER-04.10 Auxiliary power (requirement)
- ER-06.06 Stack (requirement)
- ER-07.04 Cooling water temperature rise (requirement)
- ER-07.07 Condenser design standard (requirement)
- ER-07.08 Condenser pressure (requirement)
- ER-08.04 Biofouling control (requirement)
- ER-08.05 Thermal plume (requirement)
- ER-08.07 Jellyfish and mucilage (requirement)
- ER-11.01 Grid connection (requirement)
- ER-14.02 Air emissions (requirement)
- ER-14.03 Near-field noise (requirement)
- ER-14.04 Environmental noise (requirement)
- SRC-EPCE-0011 Topographic survey point listing - plot, temporary area TP-A1 and coastal strip (source)
- SRC-OWNR-0001 Meteorological and ambient air data (source)
- SRC-OWNR-0002 Seawater quality and marine conditions (source)
- SRC-OWNR-0003 Natural gas quality and supply conditions (source)
- SRC-OWNR-0004 Secondary fuel: light diesel oil (LDO) (source)
- SRC-OWNR-0005 Site, existing infrastructure and tie-in points (source)
- SRC-OWNR-0006 Grid connection data (source)
- SRC-OWNR-0007 Positive EIA decision - binding conditions (source)
- SRC-OWNR-0008 Geotechnical baseline summary (source)
