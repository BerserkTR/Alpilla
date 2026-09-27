"""Case authoring: all Imaginary Electric (IEC) vendor data in one place, computed with iec_model.py.
`python iec_data.py <out.json>` writes the data used by iec_docs.py (documents) and by the EPC's database load."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import iec_model as m  # noqa: E402

from engine.core import thermo as t  # noqa: E402

GT_LIMIT = 470.0e3          # kW, GT output limit at the generator terminals (generator / shaft limit), cold ambient
CASE = "SRC-NG-100"


def r(x, n=2):
    return round(float(x), n)


def src_case():
    g = m.gt_balance(m.SRC)
    c = m.steam_cycle(g)
    s = c["states"]
    P, T = m.P, m.T
    m_hp, m_ip, m_lp, m_rh, m_lpt = c["m_hp"], c["m_ip"], c["m_lp"], c["m_rh"], c["m_lpt"]
    m_fgh, m_ipeco, m_cond = c["m_fgh_w"], c["m_ipeco"], c["m_cond"]
    m_bfp = m_hp + m_ipeco
    h_crh_mix = (m_hp * t.h_pT(P["RH_in"], s["T_crh_in"]) + m_ip * t.h_pT(P["IP_sh_out"], s["T_ip_sh"])) / m_rh
    T_crh_mix = t.T_ph(P["RH_in"], h_crh_mix)
    T_cep = t.T_ph(P["CEP"], t.pump(c["p_cond"], c["T_cond"] - 0.01, P["CEP"], m.PUMP["CEP"])[0])
    sw_in, sw_out = m.SRC["T_sw"], m.SRC["T_sw"] + T["dT_cw"]
    # (no, description, fluid, from, to, kg/s, bar(a), degC, enthalpy or None)
    S = [
        (1, "Ambient air to GT compressor inlet", "air", "AMB", "GT", g["m_a"], m.SRC["p_amb"], m.SRC["T_amb"], None),
        (2, "Fuel gas at performance gas heater inlet (IEC terminal point)", "fuel_gas", "FGS", "FGH", g["m_f"], 38.0,
         m.GT["T_fuel_skid"], None),
        (3, "Heated fuel gas to GT combustion system", "fuel_gas", "FGH", "GT", g["m_f"], 35.5, m.GT["T_fuel_heated"], None),
        (4, "GT exhaust gas to HRSG inlet", "flue_gas", "GT", "HRSG", g["m_e"], m.SRC["p_amb"] + m.GT["dp_exhaust"] / 1000,
         m.GT["T_exh"], None),
        (5, "Flue gas at HRSG outlet to stack", "flue_gas", "HRSG", "STK", g["m_e"], m.SRC["p_amb"] + 0.002, c["T_stack"], None),
        (6, "HP steam at HRSG outlet (HP SH outlet)", "steam", "HRSG", "PIPE", m_hp, P["HP_sh_out"], T["HP_sh_out"], None),
        (7, "HP steam at ST main stop valve inlet", "steam", "PIPE", "ST", m_hp, P["HP_st_in"], T["HP_st_in"], None),
        (8, "Cold reheat steam at HP turbine exhaust", "steam", "ST", "PIPE", m_hp, P["HP_st_exh"], s["T_hp_exh"], None),
        (9, "Cold reheat steam at HRSG reheater inlet", "steam", "PIPE", "HRSG", m_hp, P["RH_in"], s["T_crh_in"], None),
        (10, "IP superheated steam (joins cold reheat inside the HRSG)", "steam", "HRSG", "HRSG", m_ip, P["IP_sh_out"],
         s["T_ip_sh"], None),
        (11, "Hot reheat steam at HRSG outlet", "steam", "HRSG", "PIPE", m_rh, P["HRH_out"], T["HRH_out"], None),
        (12, "Hot reheat steam at ST IP stop/control valve inlet", "steam", "PIPE", "ST", m_rh, P["IP_st_in"], T["IP_st_in"], None),
        (13, "LP steam at HRSG outlet", "steam", "HRSG", "PIPE", m_lp, P["LP_sh_out"], T["LP_sh_out"], None),
        (14, "LP steam at ST LP admission", "steam", "PIPE", "ST", m_lp, P["LP_st_in"], T["LP_sh_out"] - T["dT_lp"], None),
        (15, "IP turbine exhaust (crossover, internal)", "steam", "ST", "ST", m_rh, P["IP_st_exh"], s["T_ip_exh"], None),
        (16, "LP turbine exhaust to condenser (UEEP)", "steam", "ST", "COND", m_lpt, c["p_cond"], c["T_cond"], s["h_ueep"]),
        (17, "Condensate at hotwell outlet / CEP suction", "water", "COND", "CEP", m_cond, c["p_cond"], c["T_cond"] - 0.05, None),
        (18, "Condensate at CEP discharge", "water", "CEP", "CMIX", m_cond, P["CEP"], T_cep, None),
        (19, "Fuel gas heater water return to condensate", "water", "FGH", "CMIX", m_fgh, P["BFP_IP"] - 3.0, T["fgh_return"], None),
        (20, "Condensate to HRSG condensate preheater inlet", "water", "CMIX", "HRSG", m_cond + m_fgh, P["CEP"] - 0.5,
         s["T_cph_in"], None),
        (21, "Feedwater from LP drum to boiler feed pumps", "water", "HRSG", "BFP", m_bfp, P["LP_drum"], s["Tsat"]["LP_drum"] - 0.05, None),
        (22, "HP feedwater at BFP discharge", "water", "BFP", "HRSG", m_hp, P["BFP_HP"], s["T_bfp_hp"], None),
        (23, "IP feedwater at BFP interstage outlet", "water", "BFP", "HRSG", m_ipeco, P["BFP_IP"], s["T_bfp_ip"], None),
        (24, "IP economiser water to performance fuel gas heater", "water", "HRSG", "FGH", m_fgh, P["IP_drum"] + 1.5,
         s["T_ip_eco"], None),
        (25, "Circulating seawater to condenser inlet", "seawater", "SEA", "COND", c["m_cw"], 2.5, sw_in, None),
        (26, "Circulating seawater from condenser outlet", "seawater", "COND", "OUT", c["m_cw"], 1.7, sw_out, None),
    ]
    streams = [dict(no=n, description=d, fluid=f, from_node=a, to_node=b, mass_flow=r(mf, 2), pressure=r(p, 4 if p < 0.1 else 2),
                    temperature=r(Tc, 1), enthalpy=(r(h, 1) if h is not None else None)) for n, d, f, a, b, mf, p, Tc, h in S]
    return g, c, streams, dict(T_crh_mix=T_crh_mix)


def ambient_table():
    rows = []
    for Ta, RH, Tsw in [(-8.0, 80, 6.9), (-4.8, 80, 8.0), (5.0, 75, 11.0), (15.0, 70, 16.0), (25.0, 55, 22.0),
                        (32.8, 45, 24.0), (40.0, 35, 27.0)]:
        gt = m.gt_ambient(Ta)
        limited = gt["P_gen"] > GT_LIMIT
        if limited:          # load limiter: IGV closing at constant exhaust temperature margin
            m.GT_T_exh = gt["T_exh"] + 6.0
            gt = dict(m.GT, P_gen=GT_LIMIT, eta=gt["eta"] * (1 - 0.0035), T_exh=gt["T_exh"] + 6.0)
            amb = {"T_amb": Ta, "RH": RH, "p_amb": m.SRC["p_amb"], "T_sw": Tsw}
            g = m.gt_balance(amb, gt)
            c = m.steam_cycle(g, amb)
            m.GT_T_exh = m.GT["T_exh"]
        else:
            gt, g, c = m.ambient_case(Ta, RH, Tsw)
        rows.append(dict(T_amb=Ta, RH=RH, T_sw=Tsw, gt_limited=limited, gt_P=r(gt["P_gen"] / 1e3, 1),
                         gt_HR=r(3600 / gt["eta"], 0), gt_exh_flow=r(g["m_e"], 1), gt_exh_T=r(gt["T_exh"], 1),
                         st_P=r(c["P_st"] / 1e3, 1), gross=r((gt["P_gen"] + c["P_st"]) / 1e3, 1),
                         gross_HR=r(g["Q_fuel"] * 3600 / (gt["P_gen"] + c["P_st"]), 0), p_cond=r(c["p_cond"] * 1000, 1),
                         fuel_Sm3h=r(g["m_f"] / g["fuel"]["density_std"] * 3600, 0), steam_hp=r(c["m_hp"], 1)))
    return rows


def part_load():
    rows = []
    for load, f_hr, dTx in [(100, 1.000, 0.0), (80, 1.052, 0.0), (60, 1.135, 0.0), (50, 1.190, -8.0), (40, 1.275, -25.0)]:
        gt = dict(m.GT, P_gen=m.GT["P_gen"] * load / 100, eta=m.GT["eta"] / f_hr, T_exh=m.GT["T_exh"] + dTx)
        m.GT_T_exh = gt["T_exh"]
        g = m.gt_balance(m.SRC, gt)
        c = m.steam_cycle(g)
        m.GT_T_exh = m.GT["T_exh"]
        rows.append(dict(gt_load=load, gt_P=r(gt["P_gen"] / 1e3, 1), gt_HR=r(3600 / gt["eta"], 0), gt_exh_flow=r(g["m_e"], 1),
                         gt_exh_T=r(gt["T_exh"], 1), st_P=r(c["P_st"] / 1e3, 1), gross=r((gt["P_gen"] + c["P_st"]) / 1e3, 1),
                         gross_HR=r(g["Q_fuel"] * 3600 / (gt["P_gen"] + c["P_st"]), 0)))
    return rows


PIPING_EPC = {  # EPC preliminary piping design (TQ-IEC-003): pressure / temperature drops HRSG -> ST
    "P": {"HP_st_in": 181.5, "IP_st_in": 36.2, "LP_st_in": 5.05, "RH_in": 39.5},
    "T": {"HP_st_in": 598.5, "IP_st_in": 598.5}, "dT_lp": 1.0}


def apply_variant(name):
    if name == "revA":
        m.P.update(PIPING_EPC["P"])
        m.T.update(PIPING_EPC["T"])
        m.T["dT_lp"] = PIPING_EPC["dT_lp"]


def build():
    g, c, streams, extra = src_case()
    f = g["fuel"]
    ex = {k: r(v * 100, 2) for k, v in g["ex_x"].items()}
    perf = {
        "case": CASE, "gt_P_gen": r(m.GT["P_gen"] / 1e3, 2), "gt_eta": m.GT["eta"], "gt_HR": r(3600 / m.GT["eta"], 1),
        "gt_eta_gen": m.GT["eta_gen"], "gt_Q_other": r(m.GT["Q_other"] / 1e3, 2), "Q_fuel": r(g["Q_fuel"] / 1e3, 2),
        "fuel_LHV": r(f["LHV_mass"], 3), "fuel_LHV_vol": r(f["LHV_vol"], 3), "fuel_Sm3h": r(g["m_f"] / f["density_std"] * 3600, 0),
        "Q_fgh": r(g["Q_fgh"] / 1e3, 2), "exhaust_mol_pct": ex, "st_P_gen": r(c["P_st"] / 1e3, 2),
        "st_eta_mech": m.ST["eta_mech"], "st_eta_gen": m.ST["eta_gen"], "st_eta": {k: m.ST[k] for k in ("eta_HP", "eta_IP", "eta_LP")},
        "st_exh_loss": m.ST["exh_loss"], "gross": r((m.GT["P_gen"] + c["P_st"]) / 1e3, 2),
        "gross_HR": r(g["Q_fuel"] * 3600 / (m.GT["P_gen"] + c["P_st"]), 1), "hrsg_loss_pct": m.T["hrsg_loss"] * 100,
        "Q_hrsg": r(c["Q_water"] / 1e3, 2), "Q_cond": r(c["Q_cond"] / 1e3, 2), "p_cond_mbar": r(c["p_cond"] * 1000, 2),
        "T_stack": r(c["T_stack"], 1), "cw_flow": r(c["m_cw"], 0), "cw_m3h": r(c["m_cw"] / 1.0165 * 3.6, 0),
        "sections": {k: [r(a, 1), r(b, 1), r(q / 1e3, 2)] for k, (a, b, q) in c["sections"].items()},
        "Tsat": {k: r(v, 1) for k, v in c["states"]["Tsat"].items()}, "x_ueep": r(c["states"]["x_ueep"], 4),
        "P_hp": r(c["P_hp"] / 1e3, 2), "P_ip": r(c["P_ip"] / 1e3, 2), "P_lp": r(c["P_lp"] / 1e3, 2),
        "T_crh_mix": r(extra["T_crh_mix"], 1), "pinch": [m.T["pinch_HP"], m.T["pinch_IP"], m.T["pinch_LP"]],
        "approach": [m.T["appr_HP"], m.T["appr_IP"], m.T["appr_LP"]], "air_flow": r(g["m_a"], 2),
        "exh_flow": r(g["m_e"], 2), "fuel_flow": r(g["m_f"], 3), "gt_limit": GT_LIMIT / 1e3,
        "pumps_kW": {k: r(v, 0) for k, v in c["pumps"].items()}}
    return {"perf": perf, "streams": streams, "ambient": ambient_table(), "part_load": part_load(),
            "pressures": m.P, "temps": {k: v for k, v in m.T.items()}, "fuel": {"composition": m.FUEL, "M": r(f["M"], 4),
                                                                                 "rel_density": r(f["rel_density"], 4)}}


if __name__ == "__main__":
    if len(sys.argv) > 2:
        apply_variant(sys.argv[2])
    d = build()
    Path(sys.argv[1]).write_text(json.dumps(d, indent=1, default=float))
    p = d["perf"]
    print(f"GT {p['gt_P_gen']} ST {p['st_P_gen']} gross {p['gross']} MW, gross HR {p['gross_HR']}, stack {p['T_stack']}, "
          f"cond {p['p_cond_mbar']} mbar, CW {p['cw_m3h']} m3/h, gas {p['fuel_Sm3h']} Sm3/h")
    for row in d["ambient"]:
        print(row)
    for row in d["part_load"]:
        print(row)
