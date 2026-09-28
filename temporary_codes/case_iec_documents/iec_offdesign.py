"""Case authoring: IEC off-design (rating) model of the power island, calibrated at the design point (PER-001 Rev A).
Fixed HRSG section UA values (gas-side scaling m^0.6), fixed condenser UA with constant CW flow, sliding pressure by the
Stodola cone law, attemperation to 600 degC, turbine efficiency and LP exhaust loss off design, natural gas or LDO with
water injection. Simulates the vendor's off-design heat balances (a received input for the EPC); writes nothing to the DB.
Requires scipy (root finding)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

from scipy.optimize import brentq

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import iec_data  # noqa: E402
import iec_model as m  # noqa: E402

from engine.core import thermo as t  # noqa: E402

iec_data.apply_variant("revB")                 # design basis = PER-001 Rev B (EPC piping values, corrected arrangement)
P0, T0, ST0 = dict(m.P), dict(m.T), dict(m.ST)
KEEP = 1 - T0["hrsg_loss"]
T_SH_MAX = 600.0
DT_PIPE = {"HP": T0["HP_sh_out"] - T0["HP_st_in"], "HRH": T0["HRH_out"] - T0["IP_st_in"], "CRH": T0["dT_crh"], "LP": T0["dT_lp"]}
LDO = {"formula": "C12H23", "LHV": 42.9, "T": 30.0, "water_fuel": 1.02, "T_water": 30.0, "p_water": 60.0}
GT_LDO = {"P_gen": 395.0e3, "eta": 3600 / 8650, "T_exh": 622.0}
GT_LIMIT = 470.0e3
PART = [(100, 1.000, 640.0), (80, 1.052, 640.0), (60, 1.135, 640.0), (50, 1.190, 632.0), (40, 1.275, 615.0),
        (30, 1.400, 598.0)]  # load, HR factor, T_exh; 30 % only with the DLN low-load extension (TQ-IEC-019)


LDO_FIXED_AIR = [False]     # Rev 0: air flow back-calculated from P, HR, T_exh (inconsistent on LDO, TQ-IEC-018)


def apply_revA():
    """PER-003 Rev A (TQ-IEC-018): LDO with the compressor air flow of gas operation (IGV fully open), exhaust temperature
    from the GT energy balance, water/fuel ratio 0.60 with the SCR sized for LDO (GT-outlet NOx <= 150 mg/Nm3)."""
    GT_LDO.update(P_gen=400.5e3, eta=3600 / 8640)
    LDO["water_fuel"] = 0.60
    LDO_FIXED_AIR[0] = True


def lmtd(d1, d2):
    if d1 <= 0 or d2 <= 0:
        raise ValueError("temperature cross")
    return d1 if abs(d1 - d2) < 1e-9 else (d1 - d2) / math.log(d1 / d2)


# ------------------------------------------------------------------ GT
def gt_state(amb, gt, fuel_mode="gas"):
    """GT energy balance -> air flow, exhaust flow and composition; gas or LDO with water injection."""
    air_x = t.humid_air(amb["T_amb"], amb["RH"], amb["p_amb"])
    Ma = t.mixture_M(air_x)
    if fuel_mode == "gas":
        f = t.fuel_properties(m.FUEL)
        atoms, h_sens = None, t.h_fuel(f["x"], m.GT["T_fuel_heated"])
    else:
        f = t.liquid_fuel(LDO["formula"], LDO["LHV"])
        atoms, h_sens = f["atoms"], t.h_liquid_fuel(f, LDO["T"])
    Q_fuel = gt["P_gen"] / gt["eta"]
    m_f = Q_fuel / (f["LHV_mass"] * 1000)
    m_w = LDO["water_fuel"] * m_f if fuel_mode == "ldo" else 0.0
    h_w = t.h_water_gas_basis(LDO["p_water"], LDO["T_water"]) if m_w else 0.0
    E_f = m_f * (f["LHV_mass"] * 1000 + h_sens) + m_w * h_w
    W = gt["P_gen"] / m.GT["eta_gen"] + m.GT["Q_other"]
    if fuel_mode == "ldo" and LDO_FIXED_AIR[0]:
        # compressor air as on gas at this ambient (IGV fully open); exhaust temperature from the energy balance
        m_a = gt_state(amb, gt_for_case(amb, 100.0, "gas"), "gas")["m_a"]
        ex = t.mole_fractions(t.combustion(air_x, m_a / Ma * 1000, f["x"], m_f / f["M"] * 1000, m_w / t.M["H2O"] * 1000, atoms))
        h_e = (m_a * t.h_gas(air_x, amb["T_amb"]) + E_f - W) / (m_a + m_f + m_w)
        gt = dict(gt, T_exh=t.T_from_h_gas(ex, h_e))
    else:
        m_a = 750.0
        for _ in range(80):
            ex = t.mole_fractions(t.combustion(air_x, m_a / Ma * 1000, f["x"], m_f / f["M"] * 1000, m_w / t.M["H2O"] * 1000, atoms))
            h_a, h_e = t.h_gas(air_x, amb["T_amb"]), t.h_gas(ex, gt["T_exh"])
            new = (E_f - W - (m_f + m_w) * h_e) / (h_e - h_a)
            if abs(new - m_a) < 1e-8:
                break
            m_a = new
    Q_fgh = m_f * (t.h_fuel(f["x"], m.GT["T_fuel_heated"]) - t.h_fuel(f["x"], m.GT["T_fuel_skid"])) if fuel_mode == "gas" else 0.0
    return dict(fuel=f, fuel_mode=fuel_mode, Q_fuel=Q_fuel, m_f=m_f, m_w=m_w, m_a=m_a, m_e=m_a + m_f + m_w, ex_x=ex, air_x=air_x,
                T_exh=gt["T_exh"], P_gen=gt["P_gen"], eta=gt["eta"], Q_fgh=Q_fgh)


def gt_for_case(amb, load_pct=100.0, fuel_mode="gas"):
    if fuel_mode == "ldo":
        return dict(GT_LDO)
    a = m.gt_ambient(amb["T_amb"])
    if a["P_gen"] > GT_LIMIT:                              # generator/shaft limit, IGV closing
        a = {"P_gen": GT_LIMIT, "eta": a["eta"] * (1 - 0.0035), "T_exh": a["T_exh"] + 6.0}
    if load_pct < 100.0:
        loads = [p[0] for p in PART]
        for (l1, f1, x1), (l2, f2, x2) in zip(PART, PART[1:]):
            if l2 <= load_pct <= l1:
                w = (load_pct - l2) / (l1 - l2)
                fhr, tx = f2 + w * (f1 - f2), x2 + w * (x1 - x2)
                break
        else:
            raise ValueError(f"GT load {load_pct} outside {loads}")
        a = {"P_gen": a["P_gen"] * load_pct / 100, "eta": a["eta"] / fhr, "T_exh": tx}
    return a


# ------------------------------------------------------------------ design calibration
def design():
    g = m.gt_balance(m.SRC)
    c = m.steam_cycle(g)
    return g, c


G_D, C_D = design()
S_D = C_D["states"]
MG_D = G_D["m_e"]


def _cal():
    """UA of every sub-exchanger from the design point, with exactly the state definitions used by the rating."""
    sec = C_D["sections"]
    Ts = S_D["Tsat"]
    cin = lambda p, h: t.T_ph(p, h)                                    # noqa: E731  cold inlet as the rating defines it
    ua = {}
    m_hp, m_ip, m_rh = C_D["m_hp"], C_D["m_ip"], C_D["m_rh"]
    # S1 split: HP SH and RH, gas split by design duty
    h_crh_mix = (m_hp * t.h_pT(P0["RH_in"], S_D["T_crh_in"]) + m_ip * t.h_pT(P0["IP_sh_out"], S_D["T_ip_sh"])) / m_rh
    q_hp = m_hp * (t.h_pT(P0["HP_sh_out"], T0["HP_sh_out"]) - t.h_g(P0["HP_drum"]))
    q_rh = m_rh * (t.h_pT(P0["HRH_out"], T0["HRH_out"]) - h_crh_mix)
    Tg0, Tg1, _ = sec["HPSH_RH"]
    ua["psi"] = q_hp / (q_hp + q_rh)
    ua["HPSH"] = q_hp / lmtd(Tg0 - T0["HP_sh_out"], Tg1 - cin(P0["HP_sh_out"], t.h_g(P0["HP_drum"])))
    ua["RH"] = q_rh / lmtd(Tg0 - T0["HRH_out"], Tg1 - cin(P0["HRH_out"], h_crh_mix))
    a, b, q = sec["HPEVAP"]; ua["HPEV"] = q / lmtd(a - Ts["HP_drum"], b - Ts["HP_drum"])
    a, b, q = sec["IPSH"]; ua["IPSH"] = q / lmtd(a - S_D["T_ip_sh"], b - cin(P0["IP_sh_out"], t.h_g(P0["IP_drum"])))
    a, b, q = sec["HPECO2"]
    ua["HPE2"] = q / lmtd(a - S_D["T_hp_eco"], b - cin(P0["HP_drum"] + 3, t.h_pT(P0["HP_drum"] + 6, S_D["T_x"])))
    a, b, q = sec["IPEVAP"]; ua["IPEV"] = q / lmtd(a - Ts["IP_drum"], b - Ts["IP_drum"])
    a, b, q = sec["LPSH"]; ua["LPSH"] = q / lmtd(a - T0["LP_sh_out"], b - cin(P0["LP_sh_out"], t.h_g(P0["LP_drum"])))
    a, b, q = sec["HPECO1_IPECO"]
    h_bfp_hp = t.pump(P0["LP_drum"], Ts["LP_drum"] - 0.01, P0["BFP_HP"], m.PUMP["BFP"])[0]
    h_bfp_ip = t.pump(P0["LP_drum"], Ts["LP_drum"] - 0.01, P0["BFP_IP"], m.PUMP["BFP"])[0]
    q_h = m_hp * (t.h_pT(P0["HP_drum"] + 6, S_D["T_x"]) - h_bfp_hp)
    ua["phi"] = q_h / q
    ua["HPE1"] = q_h / lmtd(a - S_D["T_x"], b - cin(P0["HP_drum"] + 6, h_bfp_hp))
    ua["IPE"] = (q - q_h) / lmtd(a - S_D["T_ip_eco"], b - cin(P0["IP_drum"] + 1.5, h_bfp_ip))
    a, b, q = sec["LPEVAP"]; ua["LPEV"] = q / lmtd(a - Ts["LP_drum"], b - Ts["LP_drum"])
    a, b, q = sec["CPH"]
    h_cph_in = C_D["states"]["h_cph_in"] if "h_cph_in" in C_D["states"] else None
    if h_cph_in is None:
        h_cep = t.pump(C_D["p_cond"], C_D["T_cond"] - 0.01, P0["CEP"], m.PUMP["CEP"])[0]
        h_ret = t.h_pT(P0["BFP_IP"], T0["fgh_return"])
        h_cph_in = (C_D["m_cond"] * h_cep + C_D["m_fgh_w"] * h_ret) / (C_D["m_cond"] + C_D["m_fgh_w"])
    ua["CPH"] = q / lmtd(a - S_D["T_cph_out"], b - cin(P0["LP_drum"] + 1, h_cph_in))
    Tin = m.SRC["T_sw"]
    ua["COND"] = C_D["Q_cond"] / lmtd(C_D["T_cond"] - Tin, C_D["T_cond"] - (Tin + T0["dT_cw"]))
    return ua


UA = _cal()


def _v_exh_design():
    """Volumetric flow at the LP exhaust (ELEP) at the design point - reference for the exhaust loss."""
    h_elep = t.expand_h(P0["IP_st_exh"], S_D["h_mix_lp"], C_D["p_cond"], ST0["eta_LP"])
    return t._ph(round(C_D["p_cond"], 6), round(h_elep, 6)).v * C_D["m_lpt"]
D = dict(m_hp=C_D["m_hp"], m_ip=C_D["m_ip"], m_lp=C_D["m_lp"], m_rh=C_D["m_rh"], m_lpt=C_D["m_lpt"], m_cw=C_D["m_cw"],
         T_ip_exh=S_D["T_ip_exh"], v_exh=_v_exh_design())


# ------------------------------------------------------------------ heat exchanger rating
def ua_off(key, mg):
    return UA[key] * (mg / MG_D) ** 0.6


def rate_evap(ex, mg, Tg_in, Tsat, ua):
    """Evaporator: gas outlet temperature and water-side duty."""
    hin = t.h_gas(ex, Tg_in)
    f = lambda Tg: mg * KEEP * (hin - t.h_gas(ex, Tg)) - ua * lmtd(Tg_in - Tsat, Tg - Tsat)  # noqa: E731
    Tg = brentq(f, Tsat + 1e-6, Tg_in - 1e-6, xtol=1e-10)
    return Tg, mg * KEEP * (hin - t.h_gas(ex, Tg))


def rate_cf(ex, mg, Tg_in, m_c, p_c, h_c_in, ua, T_c_max=None):
    """Counterflow exchanger, cold stream at pressure p_c: cold outlet temperature, gas outlet, duty."""
    hin = t.h_gas(ex, Tg_in)
    T_c_in = t.T_ph(p_c, h_c_in)

    def gas_out(Tc):
        q = m_c * (t.h_pT(p_c, Tc) - h_c_in)
        return t.T_from_h_gas(ex, hin - q / (mg * KEEP)), q

    def f(Tc):
        Tg, q = gas_out(Tc)
        d1, d2 = Tg_in - Tc, Tg - T_c_in
        if d2 <= 0:
            return 1e9
        return q - ua * lmtd(d1, d2)

    hi = Tg_in - 1e-4 if T_c_max is None else min(Tg_in - 1e-4, T_c_max)
    lo = T_c_in + 1e-4
    if f(hi) < 0:                                   # capped (e.g. economiser at the steaming limit)
        Tc = hi
    else:
        Tc = brentq(f, lo, hi, xtol=1e-10)
    Tg, q = gas_out(Tc)
    return Tc, Tg, q


# ------------------------------------------------------------------ pressures (sliding) and turbine
def scaled_dp(dp_d, m_, m_d, p=None, p_d=None):
    r = (m_ / m_d) ** 2
    return dp_d * r * ((p_d / p) if p and p_d else 1.0)


def eta_off(eta_d, r):
    return eta_d * (1 - 0.3 * (1 - r) ** 2)


def rate_case(amb, gt_spec, fuel_mode="gas", tol=1e-4, verbose=False):
    g = gt_state(amb, gt_spec, fuel_mode)
    ex, mg, Tg0 = g["ex_x"], g["m_e"], g["T_exh"]
    fl = dict(m_hp=D["m_hp"] * mg / MG_D, m_ip=D["m_ip"] * mg / MG_D, m_lp=D["m_lp"] * mg / MG_D, sp_hp=0.0, sp_rh=0.0,
              p_cond=C_D["p_cond"], T_x=S_D["T_x"], T_hp_eco=S_D["T_hp_eco"], T_ip_eco=S_D["T_ip_eco"],
              T_cph_out=S_D["T_cph_out"], T_ip_sh=S_D["T_ip_sh"], T_sh=T0["HP_sh_out"], T_rh=T0["HRH_out"],
              T_lpsh=T0["LP_sh_out"], m_fgh=C_D["m_fgh_w"] if fuel_mode == "gas" else 0.0)
    for it in range(300):
        m_hp_st = fl["m_hp"] + fl["sp_hp"]
        m_rh = m_hp_st + fl["m_ip"] + fl["sp_rh"]
        m_lpt = m_rh + fl["m_lp"]
        # --- pressures
        T_hp_st = fl["T_sh"] - DT_PIPE["HP"]
        p_hp_st = min(200.0, max(60.0, P0["HP_st_in"] * m_hp_st / D["m_hp"] * math.sqrt((T_hp_st + 273.15) / (T0["HP_st_in"] + 273.15))))
        p_sh = p_hp_st + scaled_dp(P0["HP_sh_out"] - P0["HP_st_in"], m_hp_st, D["m_hp"], p_hp_st, P0["HP_st_in"])
        p_hpd = min(215.0, p_sh + scaled_dp(P0["HP_drum"] - P0["HP_sh_out"], fl["m_hp"], D["m_hp"], p_sh, P0["HP_sh_out"]))
        T_ip_st = fl["T_rh"] - DT_PIPE["HRH"]
        p_ip_st = P0["IP_st_in"] * m_rh / D["m_rh"] * math.sqrt((T_ip_st + 273.15) / (T0["IP_st_in"] + 273.15))
        p_hrh = p_ip_st + scaled_dp(P0["HRH_out"] - P0["IP_st_in"], m_rh, D["m_rh"], p_ip_st, P0["IP_st_in"])
        p_rhin = p_hrh + scaled_dp(P0["RH_in"] - P0["HRH_out"], m_rh, D["m_rh"], p_hrh, P0["HRH_out"])
        p_hpx = p_rhin + scaled_dp(P0["HP_st_exh"] - P0["RH_in"], m_hp_st, D["m_hp"], p_rhin, P0["RH_in"])
        p_ipsh = p_rhin + scaled_dp(P0["IP_sh_out"] - P0["RH_in"], fl["m_ip"], D["m_ip"], p_rhin, P0["RH_in"])
        p_ipd = p_ipsh + scaled_dp(P0["IP_drum"] - P0["IP_sh_out"], fl["m_ip"], D["m_ip"], p_ipsh, P0["IP_sh_out"])
        p_x = P0["IP_st_exh"] * m_lpt / D["m_lpt"]
        p_lp_st = p_x + scaled_dp(P0["LP_st_in"] - P0["IP_st_exh"], fl["m_lp"], D["m_lp"])
        p_lpsh = p_lp_st + scaled_dp(P0["LP_sh_out"] - P0["LP_st_in"], fl["m_lp"], D["m_lp"], p_lp_st, P0["LP_st_in"])
        p_lpd = p_lpsh + scaled_dp(P0["LP_drum"] - P0["LP_sh_out"], fl["m_lp"], D["m_lp"], p_lpsh, P0["LP_sh_out"])
        p_bfp_hp = p_hpd + scaled_dp(P0["BFP_HP"] - P0["HP_drum"], fl["m_hp"], D["m_hp"])
        p_bfp_ip = p_ipd + scaled_dp(P0["BFP_IP"] - P0["IP_drum"], fl["m_ip"] + fl["m_fgh"], D["m_ip"] + C_D["m_fgh_w"])
        Ts = {"HP": t.T_sat(p_hpd), "IP": t.T_sat(p_ipd), "LP": t.T_sat(p_lpd)}
        # economiser / CPH outlets stay subcooled at the current (sliding) drum pressures
        fl["T_hp_eco"] = min(fl["T_hp_eco"], Ts["HP"] - 2.0)
        fl["T_x"] = min(fl["T_x"], Ts["HP"] - 2.0, fl["T_hp_eco"] - 0.5)
        fl["T_ip_eco"] = min(fl["T_ip_eco"], Ts["IP"] - 2.0)
        fl["T_cph_out"] = min(fl["T_cph_out"], Ts["LP"] - 2.0)
        # --- turbine HP expansion -> cold reheat
        h_hp_in = t.h_pT(p_hp_st, T_hp_st)
        h_hpx = t.expand(p_hp_st, T_hp_st, p_hpx, eta_off(ST0["eta_HP"], m_hp_st / D["m_hp"]))
        T_hpx = t.T_ph(p_hpx, h_hpx)
        T_crh = T_hpx - DT_PIPE["CRH"]
        h_crh = t.h_pT(p_rhin, T_crh)
        # --- feed pumps (suction LP drum saturated)
        h_bfp_hp, w_hp = t.pump(p_lpd, Ts["LP"] - 0.01, p_bfp_hp, m.PUMP["BFP"])
        h_bfp_ip, w_ip = t.pump(p_lpd, Ts["LP"] - 0.01, p_bfp_ip, m.PUMP["BFP"])
        # --- HRSG, gas side hot to cold
        # S1: HP SH and RH in parallel (gas split psi)
        h_ipsh = t.h_pT(p_ipsh, fl["T_ip_sh"])
        h_rh_in = (m_hp_st * h_crh + fl["m_ip"] * h_ipsh) / (m_hp_st + fl["m_ip"])
        m_rh_sec = m_hp_st + fl["m_ip"]                       # steam through the reheater before the RH attemperator
        Tsh_raw, Tg1a, q_sh = rate_cf(ex, mg * UA["psi"], Tg0, fl["m_hp"], p_sh, t.h_g(p_hpd), ua_off("HPSH", mg))
        Trh_raw, Tg1b, q_rh = rate_cf(ex, mg * (1 - UA["psi"]), Tg0, m_rh_sec, p_hrh, h_rh_in, ua_off("RH", mg))
        hg1 = UA["psi"] * t.h_gas(ex, Tg1a) + (1 - UA["psi"]) * t.h_gas(ex, Tg1b)
        Tg1 = t.T_from_h_gas(ex, hg1)
        # attemperation to 600 degC (spray from the BFP discharges)
        h600_sh, h600_rh = t.h_pT(p_sh, T_SH_MAX), t.h_pT(p_hrh, T_SH_MAX)
        h_sh_raw, h_rh_raw = t.h_pT(p_sh, Tsh_raw), t.h_pT(p_hrh, Trh_raw)
        sp_hp = fl["m_hp"] * (h_sh_raw - h600_sh) / (h600_sh - h_bfp_hp) if Tsh_raw > T_SH_MAX else 0.0
        sp_rh = m_rh_sec * (h_rh_raw - h600_rh) / (h600_rh - h_bfp_ip) if Trh_raw > T_SH_MAX else 0.0
        sp_hp, sp_rh = min(sp_hp, 0.2 * fl["m_hp"]), min(sp_rh, 0.2 * m_rh_sec)
        T_sh, T_rh = min(Tsh_raw, T_SH_MAX), min(Trh_raw, T_SH_MAX)
        # S2 HP evaporator
        Tg2, q2 = rate_evap(ex, mg, Tg1, Ts["HP"], UA["HPEV"] * (mg / MG_D) ** 0.6)
        h_hp_eco = t.h_pT(p_hpd + 3, fl["T_hp_eco"])
        m_hp_new = q2 / (t.h_g(p_hpd) - h_hp_eco)
        # S3 IP SH (directly after the HP evaporator, Rev B arrangement)
        T_ip_sh, Tg3, q4 = rate_cf(ex, mg, Tg2, fl["m_ip"], p_ipsh, t.h_g(p_ipd), UA["IPSH"] * (mg / MG_D) ** 0.6)
        # S4 HP ECO2 (water from ECO1 outlet), capped 2 K below saturation
        T_hp_eco, Tg4, q3 = rate_cf(ex, mg, Tg3, fl["m_hp"], p_hpd + 3, t.h_pT(p_hpd + 6, fl["T_x"]),
                                    UA["HPE2"] * (mg / MG_D) ** 0.6, T_c_max=Ts["HP"] - 2.0)
        # S5 IP evaporator
        Tg5, q5 = rate_evap(ex, mg, Tg4, Ts["IP"], UA["IPEV"] * (mg / MG_D) ** 0.6)
        h_ip_eco = t.h_pT(p_ipd + 1.5, fl["T_ip_eco"])
        m_ip_new = q5 / (t.h_g(p_ipd) - h_ip_eco)
        # S6 LP SH (Rev B: directly after the IP evaporator)
        T_lpsh, Tg7, q7 = rate_cf(ex, mg, Tg5, fl["m_lp"], p_lpsh, t.h_g(p_lpd), UA["LPSH"] * (mg / MG_D) ** 0.6)
        # S7 HP ECO1 and IP ECO in parallel (gas split phi)
        T_x, Tg6a, q6a = rate_cf(ex, mg * UA["phi"], Tg7, fl["m_hp"], p_hpd + 6, h_bfp_hp, UA["HPE1"] * (mg / MG_D) ** 0.6,
                                 T_c_max=Ts["HP"] - 2.0)
        m_ipe = fl["m_ip"] + fl["m_fgh"]
        T_ip_eco, Tg6b, q6b = rate_cf(ex, mg * (1 - UA["phi"]), Tg7, m_ipe, p_ipd + 1.5, h_bfp_ip, UA["IPE"] * (mg / MG_D) ** 0.6,
                                      T_c_max=Ts["IP"] - 2.0)
        Tg6 = t.T_from_h_gas(ex, UA["phi"] * t.h_gas(ex, Tg6a) + (1 - UA["phi"]) * t.h_gas(ex, Tg6b))
        # FGH water (gas operation)
        h_ret = t.h_pT(p_bfp_ip, T0["fgh_return"])              # same convention as the design model
        m_fgh = g["Q_fgh"] / (t.h_pT(p_ipd + 1.5, T_ip_eco) - h_ret) if fuel_mode == "gas" else 0.0
        # S8 LP evaporator
        Tg8, q8 = rate_evap(ex, mg, Tg6, Ts["LP"], UA["LPEV"] * (mg / MG_D) ** 0.6)
        h_cph_out = t.h_pT(p_lpd + 1, fl["T_cph_out"])
        m_bfp = fl["m_hp"] + fl["sp_hp"] + fl["m_ip"] + fl["m_fgh"] + fl["sp_rh"]
        m_lp_new = (q8 - m_bfp * (t.h_f(p_lpd) - h_cph_out)) / (t.h_g(p_lpd) - h_cph_out)
        # --- steam turbine and condenser
        h_ip_in = t.h_pT(p_ip_st, T_ip_st)
        h_ipx = t.expand(p_ip_st, T_ip_st, p_x, eta_off(ST0["eta_IP"], m_rh / D["m_rh"]))
        T_lp_st = T_lpsh - DT_PIPE["LP"]
        h_lp_adm = t.h_pT(p_lp_st, T_lp_st)
        h_mix = (m_rh * h_ipx + fl["m_lp"] * h_lp_adm) / m_lpt
        eta_lp = eta_off(ST0["eta_LP"], m_lpt / D["m_lpt"])
        cw_cp = t.cp_seawater(22.0)
        Tin = amb["T_sw"]

        def cond_res(Tsat):
            pc = t.p_sat(Tsat)
            h_elep = t.expand_h(p_x, h_mix, pc, eta_lp)
            v = t._ph(round(pc, 6), round(h_elep, 6)).v * m_lpt
            r = v / D["v_exh"]
            el = ST0["exh_loss"] * max(0.3, r * r)
            h_ueep = h_elep + el
            q = m_lpt * (h_ueep - t.h_f(pc))
            Tout = Tin + q / (D["m_cw"] * cw_cp)
            if Tout >= Tsat - 1e-6:                      # duty needs a higher saturation temperature
                return 1e9, h_ueep, q, pc
            return q - UA["COND"] * lmtd(Tsat - Tin, Tsat - Tout), h_ueep, q, pc

        Tsat_c = brentq(lambda x: cond_res(x)[0], Tin + 0.5 + 0.01, 90.0, xtol=1e-10)
        _, h_ueep, q_cond, p_cond = cond_res(Tsat_c)
        # S9 CPH: condensate + FGH return
        m_cond = m_lpt
        h_cep, w_cep = t.pump(p_cond, Tsat_c - 0.01, P0["CEP"], m.PUMP["CEP"])
        m_cph = m_cond + m_fgh
        h_cph_in = (m_cond * h_cep + m_fgh * h_ret) / m_cph
        T_cph_out, Tg9, q9 = rate_cf(ex, mg, Tg8, m_cph, p_lpd + 1, h_cph_in, UA["CPH"] * (mg / MG_D) ** 0.6,
                                     T_c_max=Ts["LP"] - 2.0)
        new = dict(m_hp=m_hp_new, m_ip=m_ip_new, m_lp=m_lp_new, sp_hp=sp_hp, sp_rh=sp_rh, T_x=T_x, T_hp_eco=T_hp_eco,
                   T_ip_eco=T_ip_eco, T_cph_out=T_cph_out, T_ip_sh=T_ip_sh, T_sh=T_sh, T_rh=T_rh, T_lpsh=T_lpsh, m_fgh=m_fgh,
                   p_cond=p_cond)
        err = max(abs(new[k] - fl[k]) / (1.0 if k.startswith(("T_", "sp_")) else max(1e-3, abs(fl[k]))) for k in new)
        w = 0.6 if it < 150 else 0.3
        for k in new:
            fl[k] = w * new[k] + (1 - w) * fl[k]
        if verbose:
            print(it, round(err, 9), round(fl["m_hp"], 4), round(fl["m_ip"], 4), round(fl["m_lp"], 4), round(Tg9, 2))
        if err < tol:
            break
    else:
        raise RuntimeError("rating did not converge")
    # final consistent state
    P_hp = m_hp_st * (h_hp_in - h_hpx)
    P_ip = m_rh * (h_ip_in - h_ipx)
    P_lp = m_lpt * (h_mix - h_ueep)
    P_st = (P_hp + P_ip + P_lp) * ST0["eta_mech"] * ST0["eta_gen"]
    q_water = q_sh + q_rh + q2 + q3 + q4 + q5 + q6a + q6b + q7 + q8 + q9
    q_gas = mg * (t.h_gas(ex, Tg0) - t.h_gas(ex, Tg9))
    return dict(g=g, fuel_mode=fuel_mode, P_st=P_st, P_hp=P_hp, P_ip=P_ip, P_lp=P_lp, T_stack=Tg9, q_gas=q_gas, q_water=q_water,
                q_cond=q_cond, m_cw=D["m_cw"], p=dict(hp_st=p_hp_st, sh=p_sh, hpd=p_hpd, ip_st=p_ip_st, hrh=p_hrh, rhin=p_rhin,
                                                      hpx=p_hpx, ipsh=p_ipsh, ipd=p_ipd, x=p_x, lp_st=p_lp_st, lpsh=p_lpsh,
                                                      lpd=p_lpd, bfp_hp=p_bfp_hp, bfp_ip=p_bfp_ip, cond=p_cond, cep=P0["CEP"]),
                T=dict(sh=T_sh, rh=T_rh, hp_st=T_hp_st, ip_st=T_ip_st, hpx=T_hpx, crh=T_crh, ipsh=fl["T_ip_sh"], ipx=t.T_ph(p_x, h_ipx),
                       lpsh=T_lpsh, lp_st=T_lp_st, cond=Tsat_c, cph_in=t.T_ph(P0["CEP"] - 0.5, h_cph_in), cph_out=T_cph_out,
                       ip_eco=T_ip_eco, bfp_hp=t.T_ph(p_bfp_hp, h_bfp_hp), bfp_ip=t.T_ph(p_bfp_ip, h_bfp_ip), lpd=Ts["LP"],
                       cep=t.T_ph(P0["CEP"], h_cep)),
                m=dict(hp=fl["m_hp"], ip=fl["m_ip"], lp=fl["m_lp"], sp_hp=fl["sp_hp"], sp_rh=fl["sp_rh"], hp_st=m_hp_st, rh=m_rh,
                       lpt=m_lpt, fgh=m_fgh, cph=m_cph, bfp=m_bfp, ipe=m_ipe),
                h_ueep=h_ueep, x_ueep=t.x_ph(p_cond, h_ueep), pumps=dict(BFP=(fl["m_hp"] + fl["sp_hp"]) * w_hp +
                                                                         (m_ipe + fl["sp_rh"]) * w_ip, CEP=m_cond * w_cep),
                gas_T=dict(g0=Tg0, g1=Tg1, g2=Tg2, g3=Tg3, g4=Tg4, g5=Tg5, g6=Tg6, g7=Tg7, g8=Tg8, g9=Tg9))


if __name__ == "__main__":
    r = rate_case(m.SRC, dict(m.GT), verbose=False)
    print(f"design reproduction: ST {r['P_st'] / 1e3:.3f} MW (design {C_D['P_st'] / 1e3:.3f}); HP {r['m']['hp']:.3f} "
          f"({C_D['m_hp']:.3f}) IP {r['m']['ip']:.3f} ({C_D['m_ip']:.3f}) LP {r['m']['lp']:.3f} ({C_D['m_lp']:.3f}); stack "
          f"{r['T_stack']:.2f} ({C_D['T_stack']:.2f}); p_cond {r['p']['cond'] * 1000:.3f} ({C_D['p_cond'] * 1000:.3f}) mbar; "
          f"spray {r['m']['sp_hp']:.3f}/{r['m']['sp_rh']:.3f}")
