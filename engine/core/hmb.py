"""Heat and mass balance calculation for an hmb_case: stream states, node mass/energy balances, auxiliary power,
plant net output/heat rate and checks against guarantees and limits. Pure calculation (no output files).

Conventions: flows kg/s, pressures bar(a), temperatures degC, enthalpy kJ/kg, powers kW.
Enthalpy references: water/steam IAPWS-IF97; air, flue gas and fuel gas sensible enthalpy zero at 25 degC with the
fuel's chemical energy added as mass flow x LHV at the node that burns it (the node receiving both air and fuel);
seawater cp x T. Streams whose from_node equals to_node are internal (shown, not balanced)."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import thermo as t

BOUNDARY_HINT = "nodes that only send or only receive streams are system boundaries"


@dataclass
class Result:
    case: dict
    streams: list = field(default_factory=list)         # stream dicts + h, energy flow
    nodes: dict = field(default_factory=dict)           # node -> balance dict
    aux: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)          # (status OK|WARN|INFO, text)
    fuel: dict = field(default_factory=dict)
    flue_x: dict = field(default_factory=dict)


def parse_composition(s: str) -> dict:
    out = {}
    for part in (s or "").replace(",", ";").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = float(v)
    return out


FUEL_FLUIDS = ("fuel_gas", "ldo")


def calculate(case: dict, streams: list[dict], aux_loads: list[dict], refs: dict[str, dict], reference: dict | None = None) -> Result:
    """refs: 'entity:id' -> record for the case's check_refs (guarantees with their contract kind in '_kind').
    reference: summary of the case's reference_case (base load) for the plant load %."""
    res = Result(case=case)
    p_amb = case["barometric_pressure"] / 1000.0
    if case["fuel"] == "natural_gas":
        comp = parse_composition(case.get("fuel_composition", ""))
        if not comp:
            raise ValueError(f"hmb_case {case['id']}: natural gas case without fuel_composition")
        fuel = t.fuel_properties(comp)
    else:
        if not case.get("fuel_formula") or not case.get("fuel_lhv"):
            raise ValueError(f"hmb_case {case['id']}: liquid fuel case needs fuel_formula and fuel_lhv")
        fuel = t.liquid_fuel(case["fuel_formula"], case["fuel_lhv"])
    res.fuel = fuel
    air_x = t.humid_air(case["ambient_temperature"], case["relative_humidity"], p_amb)
    S = sorted(streams, key=lambda s: s["number"])
    by_to = {}
    for s in S:
        by_to.setdefault(s["to_node"], []).append(s)
    # combustion node: receives air and fuel (gas or liquid); water into it is injected water (leaves as vapour)
    burner = next((n for n, ins in by_to.items() if "air" in {s["fluid"] for s in ins}
                   and {s["fluid"] for s in ins} & set(FUEL_FLUIDS)), None)
    flue_x = {}
    if burner:
        m_air = sum(s["mass_flow"] for s in by_to[burner] if s["fluid"] == "air")
        m_f = sum(s["mass_flow"] for s in by_to[burner] if s["fluid"] in FUEL_FLUIDS)
        m_w = sum(s["mass_flow"] for s in by_to[burner] if s["fluid"] == "water")
        prod = t.combustion(air_x, m_air / t.mixture_M(air_x) * 1000, fuel["x"], m_f / fuel["M"] * 1000,
                            m_w / t.M["H2O"] * 1000, fuel.get("atoms"))
        flue_x = t.mole_fractions(prod)
    res.flue_x = flue_x
    sal = case.get("seawater_salinity") or 35.0
    cp_sw = t.cp_seawater(sal)
    for s in S:
        f = s["fluid"]
        if s.get("enthalpy") is not None:
            h = s["enthalpy"]
        elif f in ("steam", "water"):
            h = t.h_pT(s["pressure"], s["temperature"])
        elif f == "air":
            h = t.h_gas(air_x, s["temperature"])
        elif f == "flue_gas":
            if not flue_x:
                raise ValueError("flue gas stream without a combustion node (air + fuel gas into one node)")
            h = t.h_gas(flue_x, s["temperature"])
        elif f == "fuel_gas":
            h = t.h_fuel(fuel["x"], s["temperature"])
        elif f == "ldo":
            h = t.h_liquid_fuel(fuel, s["temperature"])
        elif f == "seawater":
            h = cp_sw * s["temperature"]
        else:
            raise ValueError(f"stream {s['number']}: fluid {f} not supported")
        x = None
        if f in ("steam", "water"):
            q = t.x_ph(s["pressure"], h)
            x = q if q is not None and 0.0 < q < 1.0 else None
        res.streams.append(dict(s, h=h, E=s["mass_flow"] * h, quality=x))
    # node balances
    nodes = {}
    for s in res.streams:
        if s["from_node"] == s["to_node"]:
            continue
        nodes.setdefault(s["from_node"], {"in": [], "out": []})["out"].append(s)
        nodes.setdefault(s["to_node"], {"in": [], "out": []})["in"].append(s)
    P_gt, P_st = case["gt_output"], case["st_output"]
    st_node = _st_node(res.streams)
    for n, io in nodes.items():
        bal = {"boundary": not io["in"] or not io["out"]}
        m_in, m_out = sum(s["mass_flow"] for s in io["in"]), sum(s["mass_flow"] for s in io["out"])
        E_in, E_out = sum(s["E"] for s in io["in"]), sum(s["E"] for s in io["out"])
        work, note = 0.0, ""
        if n == burner:
            E_in += sum(s["mass_flow"] for s in io["in"] if s["fluid"] in FUEL_FLUIDS) * fuel["LHV_mass"] * 1000
            # injected water: from the IAPWS basis to the flue-gas basis (vapour at 25 degC = 0)
            E_in += sum(s["mass_flow"] * (t.h_water_gas_basis(s["pressure"], s["temperature"]) - s["h"])
                        for s in io["in"] if s["fluid"] == "water")
            work = P_gt / case["gt_generator_efficiency"] + (case.get("gt_other_losses") or 0.0)
            note = "GT: shaft power (output / generator efficiency) + other losses"
        elif n == st_node:
            work = P_st / (case["st_mechanical_efficiency"] * case["st_generator_efficiency"])
            note = "ST: shaft power (output / mechanical / generator efficiency)"
        bal.update(m_in=m_in, m_out=m_out, dm=m_in - m_out, E_in=E_in, E_out=E_out, work=work, note=note,
                   residual=E_in - E_out - work)
        nodes[n] = dict(io, **bal)
    res.nodes = nodes
    # heat exchanger (HRSG) gas-side duty and expected loss
    hrsg = next((n for n, b in nodes.items() if not b["boundary"] and any(s["fluid"] == "flue_gas" for s in b["in"])
                 and any(s["fluid"] == "flue_gas" for s in b["out"])), None)
    q_gas = None
    if hrsg:
        b = nodes[hrsg]
        q_gas = sum(s["E"] for s in b["in"] if s["fluid"] == "flue_gas") - sum(s["E"] for s in b["out"] if s["fluid"] == "flue_gas")
        b["expected_loss"] = q_gas * (case.get("hrsg_heat_loss") or 0.0) / 100
        b["note"] = f"HRSG: gas-side duty {q_gas / 1000:.2f} MW; residual = casing loss"
    # auxiliary loads
    aux_total = tr_total = 0.0
    for a in sorted(aux_loads, key=lambda a: a["id"]):
        m = a["method"]
        if m == "fixed":
            p = a.get("power") or 0.0
            how = "fixed"
        elif m == "pump_node":
            b = nodes.get(a["node"])
            if not b:
                raise ValueError(f"aux_load {a['id']}: node {a['node']} has no streams")
            shaft = b["E_out"] - b["E_in"]
            p = shaft / (a.get("motor_efficiency") or 1.0)
            how = f"enthalpy rise {shaft:,.0f} kW / motor {a.get('motor_efficiency')}"
        else:  # cw_pump
            m_sw = sum(s["mass_flow"] for s in nodes.get(a["node"], {"in": []})["in"] if s["fluid"] == "seawater")
            p = m_sw * 9.81 * a["head"] / (a["pump_efficiency"] * a["motor_efficiency"]) / 1000.0
            how = f"{m_sw:,.0f} kg/s x g x {a['head']} m / ({a['pump_efficiency']} x {a['motor_efficiency']})"
        if a.get("counts_as") == "transformer_loss":
            tr_total += p
        else:
            aux_total += p
        res.aux.append(dict(a, kW=p, how=how))
    # plant summary
    q_fuel = sum(s["mass_flow"] for s in res.streams if s["fluid"] in FUEL_FLUIDS and s["to_node"] == burner) * fuel["LHV_mass"] * 1000
    gross = P_gt + P_st
    net = gross - aux_total - tr_total
    sw = [s for s in res.streams if s["fluid"] == "seawater"]
    cw_in = next((s for s in sw if s["from_node"] not in nodes or nodes[s["from_node"]]["boundary"]), None)
    cw_out = next((s for s in sw if s is not cw_in), None)
    cond_in = [s for s in res.streams if s["fluid"] == "steam" and cw_in and s["to_node"] == cw_in["to_node"]]
    rho_sw = 1000.0 + 0.76 * sal - 0.2 * (cw_in["temperature"] - 15.0) if cw_in else None
    m_fuel = q_fuel / (fuel["LHV_mass"] * 1000)
    res.summary = {
        "gt_output": P_gt, "st_output": P_st, "gross": gross, "aux": aux_total, "transformer_losses": tr_total, "net": net,
        "heat_input": q_fuel, "gross_hr": q_fuel * 3600 / gross, "net_hr": q_fuel * 3600 / net, "net_eff": net / q_fuel,
        "aux_pct_gross": (aux_total + tr_total) / gross * 100, "fuel_flow": m_fuel,
        "fuel_Sm3h": m_fuel / fuel["density_std"] * 3600 if fuel.get("density_std") else None,
        "plant_load_pct": net / reference["net"] * 100 if reference else None,
        "water_injection": sum(s["mass_flow"] for s in res.streams if s["fluid"] == "water" and s["to_node"] == burner),
        "fuel_LHV": fuel["LHV_mass"], "fuel_LHV_vol": fuel["LHV_vol"], "hrsg_gas_duty": q_gas,
        "cw_flow": cw_in["mass_flow"] if cw_in else None, "cw_m3h": cw_in["mass_flow"] / rho_sw * 3600 if cw_in else None,
        "cw_rise": (cw_out["temperature"] - cw_in["temperature"]) if cw_in and cw_out else None,
        "condenser_pressure_mbar": cond_in[0]["pressure"] * 1000 if cond_in else None,
    }
    _checks(res, refs)
    return res


def _st_node(streams):
    """The steam turbine node: receives steam and sends steam to a node that also receives seawater (the condenser)."""
    sw_nodes = {s["to_node"] for s in streams if s["fluid"] == "seawater"}
    for s in streams:
        if s["fluid"] == "steam" and s["to_node"] in sw_nodes and s["from_node"] != s["to_node"]:
            return s["from_node"]
    return None


def _checks(res: Result, refs: dict):
    C, sm, case = res.checks, res.summary, res.case
    # balances
    for n, b in sorted(res.nodes.items()):
        if b["boundary"]:
            continue
        tol_m = max(0.05, 0.0005 * b["m_in"])
        if abs(b["dm"]) > tol_m:
            C.append(("WARN", f"mass balance {n}: in {b['m_in']:.2f} / out {b['m_out']:.2f} kg/s (difference {b['dm']:+.2f})"))
        res_kw = b["residual"] - b.get("expected_loss", 0.0)
        tol = max(250.0, 0.001 * b["E_in"])
        if n in [a.get("node") for a in res.aux if a["method"] == "pump_node"]:
            continue                                           # pump nodes: residual is the pump work
        label = f"energy balance {n}: residual {b['residual'] / 1000:+.3f} MW"
        if "expected_loss" in b:
            label += f" vs stated casing loss {b['expected_loss'] / 1000:.3f} MW"
        C.append(("WARN" if abs(res_kw) > tol else "OK", label + f" (tolerance {tol / 1000:.2f} MW)"))
    # references
    for key, r in sorted(refs.items()):
        ent = key.split(":")[0]
        unit, val = r.get("unit", ""), r.get("guaranteed_value", r.get("value"))
        if val is None:
            continue
        rid = r["id"]
        if ent == "guarantee":
            owner = r.get("_kind", "owner_contract") == "owner_contract"
            direction = r["direction"]
            if unit == "MW":
                metric, x = ("net output", sm["net"] / 1000) if owner else \
                    (("GT output", sm["gt_output"] / 1000) if "GT" in r["parameter"] else ("gross output", sm["gross"] / 1000))
            elif unit == "kJ/kWh":                       # which guarantee applies is decided by the case's check_refs
                metric, x = ("net heat rate", sm["net_hr"]) if owner else ("gross heat rate", sm["gross_hr"])
            elif unit.startswith("% of plant net"):
                metric, x = "plant load (net, % of the reference case)", sm.get("plant_load_pct")
            elif unit == "K":
                metric, x = "CW temperature rise", sm["cw_rise"]
            elif unit.startswith("mbar"):
                metric, x = "condenser pressure", sm["condenser_pressure_mbar"]
            else:
                continue
            if x is None:
                continue
            ok = x >= val if direction == "min" else x <= val
            margin = (x - val) / val * 100 * (1 if direction == "min" else -1) + 0.0
            margin = 0.0 if abs(margin) < 0.005 else margin
            C.append(("OK" if ok else "WARN", f"{metric} {x:,.2f} {unit} vs {rid} {'>=' if direction == 'min' else '<='} {val:,.2f} "
                                               f"(margin {margin:+.2f} %)"))
        else:
            if unit.startswith("% of gross"):
                ok = sm["aux_pct_gross"] <= val
                C.append(("OK" if ok else "WARN", f"auxiliary + transformer losses {sm['aux_pct_gross']:.2f} % of gross vs {rid} <= {val} %"))
            elif unit == "MJ/kg":
                if case["fuel"] != "natural_gas":
                    continue
                d = (sm["fuel_LHV"] - val) / val * 100
                C.append(("WARN" if abs(d) > 0.5 else "OK", f"fuel LHV from the composition (ISO 6976) {sm['fuel_LHV']:.2f} MJ/kg vs "
                                                              f"{rid} {val} MJ/kg ({d:+.2f} %)"))
            elif unit == "Sm3/h":
                if sm["fuel_Sm3h"] is None:
                    continue
                u = sm["fuel_Sm3h"] / val * 100
                C.append(("OK" if u <= 100 else "WARN", f"gas flow {sm['fuel_Sm3h']:,.0f} Sm3/h = {u:.1f} % of {rid} ({val:,.0f} Sm3/h)"))
            elif unit.startswith("MW export"):
                C.append(("OK" if sm["net"] / 1000 <= val else "WARN",
                          f"net export {sm['net'] / 1000:,.1f} MW vs {rid} connection capacity {val:,.0f} MW (this case)"))
            elif unit.startswith("mbar"):
                x = sm["condenser_pressure_mbar"]
                if x is not None:
                    C.append(("OK" if x <= val else "WARN", f"condenser pressure {x:.2f} mbar(a) vs {rid} <= {val} mbar(a)"))
    # vendor guarantee cover: worst case of the internal-agreement guarantees against the Owner guarantees
    g = {r["unit"]: r for k, r in refs.items() if k.startswith("guarantee:") and r.get("_kind") not in (None, "owner_contract")
         and "GT" not in r["parameter"] and r["unit"] in ("MW", "kJ/kWh")}
    o = {r["unit"]: r for k, r in refs.items() if k.startswith("guarantee:") and r.get("_kind", "owner_contract") == "owner_contract"
         and r["unit"] in ("MW", "kJ/kWh")}                       # the case's check_refs select the applicable guarantees
    if {"MW", "kJ/kWh"} <= set(g) and {"MW", "kJ/kWh"} <= set(o):
        loads = (sm["aux"] + sm["transformer_losses"]) / 1000
        net_w = g["MW"]["guaranteed_value"] - loads
        hr_w = g["kJ/kWh"]["guaranteed_value"] * g["MW"]["guaranteed_value"] / net_w
        ok = net_w >= o["MW"]["guaranteed_value"] and hr_w <= o["kJ/kWh"]["guaranteed_value"]
        C.append(("OK" if ok else "WARN",
                  f"guarantee cover: at {g['MW']['id']}/{g['kJ/kWh']['id']} limits and this HMB's auxiliaries the net plant is "
                  f"{net_w:.1f} MW / {hr_w:,.0f} kJ/kWh vs Owner {o['MW']['id']} {o['MW']['guaranteed_value']:.0f} MW / "
                  f"{o['kJ/kWh']['id']} {o['kJ/kWh']['guaranteed_value']:,.0f} kJ/kWh"))
    if sm.get("plant_load_pct") is not None and case.get("load_pct", 100) < 100 \
            and abs(sm["plant_load_pct"] - case["load_pct"]) > 1.0:
        C.append(("WARN", f"plant load {sm['plant_load_pct']:.1f} % of {case.get('reference_case')} differs from the case "
                          f"definition {case['load_pct']} %"))
    if case.get("cw_temperature_rise") and sm["cw_rise"] is not None and abs(sm["cw_rise"] - case["cw_temperature_rise"]) > 0.05:
        C.append(("WARN", f"CW temperature rise {sm['cw_rise']:.2f} K differs from the case value {case['cw_temperature_rise']} K"))
