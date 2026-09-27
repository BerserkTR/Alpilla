"""Case authoring: Imaginary Electric (IEC) power-island design model, used to produce the vendor's thermal performance data.
This simulates the vendor's own calculation (a received input for the EPC); it writes nothing to the database.

Power island: 1 x IE-9H gas turbine + triple-pressure reheat HRSG + IE-ST3 reheat steam turbine + seawater condenser.
Gas side: GT energy balance (NASA polynomials); steam side: IAPWS-IF97; HRSG solved section by section with pinch/approach."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.core import thermo as t  # noqa: E402

FUEL = {"CH4": 93.0, "C2H6": 3.5, "C3H8": 0.8, "iC4H10": 0.15, "nC4H10": 0.15, "C5H12": 0.05, "N2": 1.55, "CO2": 0.8,
        "O2": 0.001, "He": 0.01}                     # Owner ALP-OWN-FUL-001 design composition
SRC = {"T_amb": 15.0, "RH": 70.0, "p_amb": 1.0115, "T_sw": 16.0}   # Site Reference Conditions (ER-02.03)

GT = {  # IE-9H at SRC, base load, natural gas, fuel heated to 215 degC, inlet dp 10 mbar, exhaust dp 36 mbar
    "P_gen": 425.0e3, "eta": 0.4330, "T_exh": 640.0, "eta_gen": 0.9890, "Q_other": 3.8e3,   # kW
    "T_fuel_skid": 25.0, "T_fuel_heated": 215.0, "dp_inlet": 10.0, "dp_exhaust": 36.0}
ST = {"eta_HP": 0.890, "eta_IP": 0.925, "eta_LP": 0.885, "exh_loss": 24.0, "eta_mech": 0.9955, "eta_gen": 0.9880}
P = {  # bar(a)
    "HP_drum": 195.0, "HP_sh_out": 187.0, "HP_st_in": 180.0, "RH_in": 39.4, "HRH_out": 37.6, "IP_st_in": 36.0,
    "HP_st_exh": 40.2, "IP_drum": 41.8, "IP_sh_out": 40.3, "LP_drum": 5.9, "LP_sh_out": 5.4, "LP_st_in": 4.95,
    "IP_st_exh": 4.95, "BFP_HP": 209.0, "BFP_IP": 46.0, "CEP": 16.0}
T = {"HP_sh_out": 600.0, "HP_st_in": 597.0, "HRH_out": 600.0, "IP_st_in": 597.0, "dT_crh": 1.0, "LP_sh_out": 300.0,
     "dT_lp": 2.0, "pinch_HP": 8.0, "pinch_IP": 8.0, "pinch_LP": 8.0, "appr_HP": 5.0, "appr_IP": 5.0, "appr_LP": 5.0,
     "TTD": 3.4, "dT_cw": 7.0, "fgh_return": 75.0, "hrsg_loss": 0.004}
PUMP = {"BFP": 0.80, "CEP": 0.80}


def gt_balance(amb, gt=GT):
    """Air flow from the GT energy balance for the given power, efficiency and exhaust temperature."""
    f = t.fuel_properties(FUEL)
    Q_fuel = gt["P_gen"] / gt["eta"]                               # kW (LHV)
    m_f = Q_fuel / (f["LHV_mass"] * 1000)                          # kg/s
    air_x = t.humid_air(amb["T_amb"], amb["RH"], amb["p_amb"])
    Ma = t.mixture_M(air_x)
    P_shaft = gt["P_gen"] / gt["eta_gen"]
    h_in_f = m_f * (f["LHV_mass"] * 1000 + t.h_fuel(f["x"], gt["T_fuel_heated"]))
    m_a = 700.0
    for _ in range(60):
        prod = t.combustion(air_x, m_a / Ma * 1000, f["x"], m_f / f["M"] * 1000)
        ex_x = t.mole_fractions(prod)
        m_e = m_a + m_f
        # m_a*h_air + fuel = shaft + other losses + m_e*h_exh  ->  solve for m_a
        h_a, h_e = t.h_gas(air_x, amb["T_amb"]), t.h_gas(ex_x, gt["T_exh"])
        m_new = (h_in_f - P_shaft - gt["Q_other"] - m_f * h_e) / (h_e - h_a)
        if abs(m_new - m_a) < 1e-7:
            break
        m_a = m_new
    return {"fuel": f, "Q_fuel": Q_fuel, "m_f": m_f, "m_a": m_a, "m_e": m_a + m_f, "air_x": air_x, "ex_x": ex_x,
            "P_shaft": P_shaft, "Q_fgh": m_f * (t.h_fuel(f["x"], gt["T_fuel_heated"]) - t.h_fuel(f["x"], gt["T_fuel_skid"])),
            "heat_rate": 3600.0 / gt["eta"]}


def steam_cycle(g, amb=SRC):
    """Size the HRSG (pinch/approach) and the steam turbine for the GT exhaust g; returns streams and results."""
    ex = g["ex_x"]
    mg = g["m_e"]
    keep = 1 - T["hrsg_loss"]
    hg = lambda Tc: t.h_gas(ex, Tc)                                # noqa: E731
    Tg = lambda h: t.T_from_h_gas(ex, h)                           # noqa: E731
    Tsat = {k: t.T_sat(P[k]) for k in ("HP_drum", "IP_drum", "LP_drum")}
    # condenser
    T_cond = amb["T_sw"] + T["dT_cw"] + T["TTD"]
    p_cond = t.p_sat(T_cond)
    # turbine expansion
    h_hp_in = t.h_pT(P["HP_st_in"], T["HP_st_in"])
    h_hp_exh = t.expand(P["HP_st_in"], T["HP_st_in"], P["HP_st_exh"], ST["eta_HP"])
    T_hp_exh = t.T_ph(P["HP_st_exh"], h_hp_exh)
    h_ip_in = t.h_pT(P["IP_st_in"], T["IP_st_in"])
    h_ip_exh = t.expand(P["IP_st_in"], T["IP_st_in"], P["IP_st_exh"], ST["eta_IP"])
    # states in the water/steam cycle
    h_hp_sh = t.h_pT(P["HP_sh_out"], T["HP_sh_out"])
    h_hrh = t.h_pT(P["HRH_out"], T["HRH_out"])
    h_crh_st = h_hp_exh
    T_crh_in = T_hp_exh - T["dT_crh"]
    h_crh_in_hp = t.h_pT(P["RH_in"], T_crh_in)                     # HP-turbine exhaust at the RH inlet
    T_ip_sh = 330.0
    h_ip_sh = t.h_pT(P["IP_sh_out"], T_ip_sh)
    h_lp_sh = t.h_pT(P["LP_sh_out"], T["LP_sh_out"])
    h_hp_g, h_ip_g, h_lp_g = t.h_g(P["HP_drum"]), t.h_g(P["IP_drum"]), t.h_g(P["LP_drum"])
    T_hp_eco = Tsat["HP_drum"] - T["appr_HP"]
    T_ip_eco = Tsat["IP_drum"] - T["appr_IP"]
    T_lp_cph = Tsat["LP_drum"] - T["appr_LP"]
    h_hp_eco = t.h_pT(P["HP_drum"] + 3, T_hp_eco)
    h_ip_eco = t.h_pT(P["IP_drum"] + 1.5, T_ip_eco)
    h_cph_out = t.h_pT(P["LP_drum"] + 1, T_lp_cph)
    # feed pumps from the LP drum (saturated water)
    T_lp_w = Tsat["LP_drum"]
    h_bfp_hp, w_hp = t.pump(P["LP_drum"], T_lp_w - 0.01, P["BFP_HP"], PUMP["BFP"])
    h_bfp_ip, w_ip = t.pump(P["LP_drum"], T_lp_w - 0.01, P["BFP_IP"], PUMP["BFP"])
    T_bfp_hp, T_bfp_ip = t.T_ph(P["BFP_HP"], h_bfp_hp), t.T_ph(P["BFP_IP"], h_bfp_ip)
    # HP economiser split: ECO1 (cold, parallel to IP ECO) heats to T_x, ECO2/3 (hot) to the approach
    T_x = Tsat["IP_drum"] - 2.0
    h_x = t.h_pT(P["HP_drum"] + 6, T_x)
    # condensate
    h_hotwell = t.h_f(p_cond)
    h_cep, w_cep = t.pump(p_cond, T_cond - 0.01, P["CEP"], PUMP["CEP"])
    m_fgh_w = g["Q_fgh"] / (h_ip_eco - t.h_pT(P["BFP_IP"], T["fgh_return"]))
    h_fgh_ret = t.h_pT(P["BFP_IP"], T["fgh_return"])

    m_hp, m_ip = 100.0, 20.0
    T2 = Tsat["HP_drum"] + T["pinch_HP"]
    T5 = Tsat["IP_drum"] + T["pinch_IP"]
    Q12 = mg * keep * (hg(GT_T_exh) - hg(T2))                      # gas heat from GT exhaust down to the HP pinch
    for _ in range(100):
        # sections 1+2 (HP SH + RH + HP EVAP) -> HP flow for the given IP flow (IP steam is reheated too)
        m_hp_new = (Q12 - m_ip * (h_hrh - h_ip_sh)) / ((h_hp_sh - h_hp_eco) + (h_hrh - h_crh_in_hp))
        # section 3 (HP ECO2) then sections 4+5 (IP SH + IP EVAP) down to the IP pinch -> IP flow
        h3 = hg(T2) - m_hp_new * (h_hp_eco - h_x) / (mg * keep)
        m_ip_new = mg * keep * (h3 - hg(T5)) / (h_ip_sh - h_ip_eco)
        done = abs(m_hp_new - m_hp) < 1e-7 and abs(m_ip_new - m_ip) < 1e-7
        m_hp, m_ip = m_hp_new, m_ip_new
        if done:
            break
    m_rh = m_hp + m_ip
    # recompute section boundaries with the converged flows
    Q1 = m_hp * (h_hp_sh - h_hp_g) + m_hp * (h_hrh - h_crh_in_hp) + m_ip * (h_hrh - h_ip_sh)
    h1 = hg(GT_T_exh) - Q1 / (mg * keep)
    T1 = Tg(h1)
    T2 = Tsat["HP_drum"] + T["pinch_HP"]
    Q2 = m_hp * (h_hp_g - h_hp_eco)
    Q3 = m_hp * (h_hp_eco - h_x)
    h3 = hg(T2) - Q3 / (mg * keep)
    T3 = Tg(h3)
    Q4 = m_ip * (h_ip_sh - h_ip_g)
    h4 = h3 - Q4 / (mg * keep)
    T4 = Tg(h4)
    T5 = Tsat["IP_drum"] + T["pinch_IP"]
    Q5 = m_ip * (h_ip_g - h_ip_eco)
    # section 6: HP ECO1 + IP ECO (IP ECO flow = IP steam + fuel gas heater water)
    m_ipeco = m_ip + m_fgh_w
    Q6 = m_hp * (h_x - h_bfp_hp) + m_ipeco * (h_ip_eco - h_bfp_ip)
    h6 = hg(T5) - Q6 / (mg * keep)
    T6 = Tg(h6)
    # section 7 (LP SH) + 8 (LP EVAP): LP pinch
    T8 = Tsat["LP_drum"] + T["pinch_LP"]
    h_lp_f = t.h_f(P["LP_drum"])
    # LP drum balance: feed from CPH (h_cph_out); outflows: LP steam + BFP suction (m_hp + m_ipeco) as sat. water
    # LP evaporator duty = m_lp*(h_lp_g - h_cph_out) + m_bfp*(h_lp_f - h_cph_out)
    m_bfp = m_hp + m_ipeco
    Q78 = mg * keep * (h6 - hg(T8))
    m_lp = (Q78 - m_bfp * (h_lp_f - h_cph_out)) / ((h_lp_sh - h_lp_g) + (h_lp_g - h_cph_out))
    Q7 = m_lp * (h_lp_sh - h_lp_g)
    T7 = Tg(h6 - Q7 / (mg * keep))
    Q8 = Q78 - Q7
    # section 9: condensate preheater: all feed water (m_lp + m_bfp) from the mix of condensate + FGH return
    m_cond = m_hp + m_ip + m_lp                                    # steam to condenser (no losses in this summary)
    m_cph = m_cond + m_fgh_w
    h_cph_in = (m_cond * h_cep + m_fgh_w * h_fgh_ret) / m_cph
    T_cph_in = t.T_ph(P["CEP"], h_cph_in)
    Q9 = m_cph * (h_cph_out - h_cph_in)
    h9 = hg(T8) - Q9 / (mg * keep)
    T_stack = Tg(h9)
    # steam turbine
    m_lpt = m_rh + m_lp
    h_mix_lp = (m_rh * h_ip_exh + m_lp * t.h_pT(P["LP_st_in"], T["LP_sh_out"] - T["dT_lp"])) / m_lpt
    h_elep = t.expand_h(P["IP_st_exh"], h_mix_lp, p_cond, ST["eta_LP"])
    h_ueep = h_elep + ST["exh_loss"]
    h_hrh_st = h_ip_in
    P_hp = m_hp * (h_hp_in - h_hp_exh)
    P_ip = m_rh * (h_hrh_st - h_ip_exh)
    P_lp = m_lpt * (h_mix_lp - h_ueep)
    P_st = (P_hp + P_ip + P_lp) * ST["eta_mech"] * ST["eta_gen"]
    Q_cond = m_lpt * (h_ueep - h_hotwell) + m_fgh_w * 0                # FGH water returns to condensate, not condenser
    cp_sw = t.cp_seawater(22.0)
    m_cw = Q_cond / (cp_sw * T["dT_cw"])
    Q_gas = mg * (hg(GT_T_exh) - hg(T_stack))
    Q_water = Q1 + Q2 + Q3 + Q4 + Q5 + Q6 + Q7 + Q8 + Q9
    pumps = {"BFP": m_hp * w_hp + m_ipeco * w_ip, "CEP": m_cond * w_cep}
    return dict(p_cond=p_cond, T_cond=T_cond, m_hp=m_hp, m_ip=m_ip, m_lp=m_lp, m_rh=m_rh, m_lpt=m_lpt, m_fgh_w=m_fgh_w,
                m_ipeco=m_ipeco, m_cond=m_cond, m_cw=m_cw, Q_cond=Q_cond, P_st=P_st, P_hp=P_hp, P_ip=P_ip, P_lp=P_lp,
                T_stack=T_stack, Q_gas=Q_gas, Q_water=Q_water, sections=dict(
                    HPSH_RH=(GT_T_exh, T1, Q1), HPEVAP=(T1, T2, Q2), HPECO2=(T2, T3, Q3), IPSH=(T3, T4, Q4),
                    IPEVAP=(T4, T5, Q5), HPECO1_IPECO=(T5, T6, Q6), LPSH=(T6, T7, Q7), LPEVAP=(T7, T8, Q8),
                    CPH=(T8, T_stack, Q9)),
                states=dict(h_hp_in=h_hp_in, h_hp_exh=h_hp_exh, T_hp_exh=T_hp_exh, h_ip_in=h_ip_in, h_ip_exh=h_ip_exh,
                            T_ip_exh=t.T_ph(P["IP_st_exh"], h_ip_exh), h_mix_lp=h_mix_lp, h_ueep=h_ueep,
                            x_ueep=t.x_ph(p_cond, h_ueep), T_crh_in=T_crh_in, T_ip_sh=T_ip_sh, T_bfp_hp=T_bfp_hp,
                            T_bfp_ip=T_bfp_ip, T_x=T_x, T_hp_eco=T_hp_eco, T_ip_eco=T_ip_eco, T_cph_in=T_cph_in,
                            T_cph_out=T_lp_cph, Tsat=Tsat, h_crh_st=h_crh_st), pumps=pumps)


GT_T_exh = GT["T_exh"]

# GT ambient correction (vendor curves, base load, IGV fully open above -5 degC); ratios to SRC
def gt_ambient(T_amb):
    d = T_amb - SRC["T_amb"]
    f_P = 1 - 0.0061 * d - 0.000045 * d * abs(d)
    f_HR = 1 + 0.00105 * d + 0.000012 * d * abs(d)
    return {"P_gen": GT["P_gen"] * f_P, "eta": GT["eta"] / f_HR, "T_exh": GT["T_exh"] + 0.52 * d}


def ambient_case(T_amb, RH, T_sw):
    """Power-island performance at another ambient: GT from the correction curves, bottoming cycle re-solved with
    the same pinch/approach (design-type estimate, not an off-design rating of the fixed HRSG surface)."""
    global GT_T_exh
    gt = dict(GT, **gt_ambient(T_amb))
    amb = {"T_amb": T_amb, "RH": RH, "p_amb": SRC["p_amb"], "T_sw": T_sw}
    GT_T_exh = gt["T_exh"]
    try:
        g = gt_balance(amb, gt)
        c = steam_cycle(g, amb)
    finally:
        GT_T_exh = GT["T_exh"]
    return gt, g, c

if __name__ == "__main__":
    g = gt_balance(SRC)
    c = steam_cycle(g)
    print(f"fuel LHV {g['fuel']['LHV_mass']:.3f} MJ/kg  m_f {g['m_f']:.3f} kg/s  Q_fuel {g['Q_fuel']/1e3:.1f} MW  "
          f"air {g['m_a']:.1f} exh {g['m_e']:.1f} kg/s  FGH {g['Q_fgh']/1e3:.2f} MW")
    print("exhaust mol%", {k: round(v * 100, 2) for k, v in g["ex_x"].items()})
    print(f"HP {c['m_hp']:.2f}  IP {c['m_ip']:.2f}  LP {c['m_lp']:.2f}  FGH water {c['m_fgh_w']:.2f} kg/s  stack {c['T_stack']:.1f} C")
    for k, (a, b, q) in c["sections"].items():
        print(f"  {k:14s} gas {a:6.1f} -> {b:6.1f} C   Q {q/1e3:7.2f} MW")
    print(f"closure gas {c['Q_gas']/1e3:.2f} MW, water {c['Q_water']/1e3:.2f} MW (loss {T['hrsg_loss']*100:.1f} %)")
    print(f"ST HP {c['P_hp']/1e3:.1f} IP {c['P_ip']/1e3:.1f} LP {c['P_lp']/1e3:.1f} gross gen {c['P_st']/1e3:.2f} MW; "
          f"cond {c['p_cond']*1000:.2f} mbar Q {c['Q_cond']/1e3:.1f} MW  CW {c['m_cw']:.0f} kg/s; x_ueep {c['states']['x_ueep']:.4f}")
    print({k: round(v, 2) for k, v in c["states"].items() if not isinstance(v, dict)}, c["states"]["Tsat"])
    gross = GT["P_gen"] + c["P_st"]
    print(f"gross {gross/1e3:.2f} MW  pumps {c['pumps']}")
