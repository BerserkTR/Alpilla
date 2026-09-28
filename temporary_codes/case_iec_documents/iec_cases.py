"""Case authoring: IEC off-design heat balance case book (IEC-ALP-PER-003) from the rating model iec_offdesign.py.
`python iec_cases.py <out.json>` writes all cases with streams in the same numbering as PER-001 (plus 27/28 for LDO fuel and
injection water, 29/30 for HP/RH attemperation spray when in service)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import iec_offdesign as o  # noqa: E402
import iec_model as m  # noqa: E402

from engine.core import thermo as t  # noqa: E402

P_AMB = m.SRC["p_amb"]
CASES = [  # id, title, ambient degC, RH %, seawater degC, fuel, load mode, load value
    ("SRC-NG-100", "Site Reference Conditions, natural gas, base load (guarantee case)", 15.0, 70.0, 16.0, "gas", "gt", 100.0),
    ("SRC-NG-GT80", "Site Reference Conditions, natural gas, GT at 80 % load", 15.0, 70.0, 16.0, "gas", "gt", 80.0),
    ("SRC-NG-060", "Site Reference Conditions, natural gas, 60 % plant net load (guarantee PG-03)", 15.0, 70.0, 16.0, "gas", "plant", 60.0),
    ("SRC-NG-MEL", "Site Reference Conditions, natural gas, GT at minimum emissions-compliant load (40 %)", 15.0, 70.0, 16.0, "gas", "gt", 40.0),
    ("SRC-LDO-100", "Site Reference Conditions, LDO with water injection, base load (guarantee PG-15/16)", 15.0, 70.0, 16.0, "ldo", "gt", 100.0),
    ("WIN-NG-100", "Winter design (-4.8 degC, 99.6 %), natural gas, base load (GT at output limit)", -4.8, 80.0, 8.0, "gas", "gt", 100.0),
    ("MIN-NG-100", "Minimum ambient for full capability (-8 degC), natural gas, base load", -8.0, 80.0, 6.9, "gas", "gt", 100.0),
    ("SUM-NG-100", "Summer design (32.8 degC, 0.4 %), natural gas, base load", 32.8, 45.0, 24.0, "gas", "gt", 100.0),
    ("MAX-NG-100", "Maximum ambient (40 degC) with maximum seawater (27 degC), natural gas, base load", 40.0, 35.0, 27.0, "gas", "gt", 100.0),
]
EPC_FIXED = 2630.0 - 30.0 - 60.0            # EPC fixed loads without the fuel-dependent ones (DEC-EPCE-0001)
IEC_FIXED = 2585.0


def gsu_losses(P_gt, P_st):
    s_gt, s_st = P_gt / 0.85 / 1000, P_st / 0.85 / 1000
    return 190 + 1150 * (s_gt / 560) ** 2, 110 + 620 * (s_st / 270) ** 2


def net_estimate(gt, r, fuel):
    """The EPC's auxiliary model (same as the hmb engine and aux_load records) - for the 60 % load search only."""
    l_gt, l_st = gsu_losses(gt["P_gen"], r["P_st"])
    fuel_loads = (30.0 + 60.0) if fuel == "gas" else (420.0 + 20.0 + 200.0)
    aux = IEC_FIXED + EPC_FIXED + fuel_loads + r["pumps"]["BFP"] / 0.965 + r["pumps"]["CEP"] / 0.95 + \
        r["m_cw"] * 9.81 * 16.0 / (0.86 * 0.96) / 1000
    return gt["P_gen"] + r["P_st"] - aux - l_gt - l_st


def rate(amb, load, fuel):
    gt = o.gt_for_case(amb, load, fuel)
    return gt, o.rate_case(amb, gt, fuel)


def streams(r, amb, fuel):
    g, p, T, M = r["g"], r["p"], r["T"], r["m"]
    gas = fuel == "gas"
    S = [(1, "Ambient air to GT compressor inlet", "air", "AMB", "GT", g["m_a"], P_AMB, amb["T_amb"], None)]
    if gas:
        S += [(2, "Fuel gas at performance gas heater inlet (IEC terminal point IF-01)", "fuel_gas", "FGS", "FGH", g["m_f"], 38.0, 25.0, None),
              (3, "Heated fuel gas to GT combustion system", "fuel_gas", "FGH", "GT", g["m_f"], 35.5, 215.0, None)]
    else:
        S += [(27, "LDO at liquid fuel skid inlet (IEC terminal point IF-02)", "ldo", "LDS", "GT", g["m_f"], 5.0, o.LDO["T"], None),
              (28, "Demineralised water for NOx water injection (IF-03)", "water", "DMW", "GT", g["m_w"], o.LDO["p_water"],
               o.LDO["T_water"], None)]
    mg = g["m_e"]
    S += [
        (4, "GT exhaust gas to HRSG inlet", "flue_gas", "GT", "HRSG", mg, P_AMB + 0.036 * (mg / o.MG_D) ** 2, g["T_exh"], None),
        (5, "Flue gas at HRSG outlet to stack", "flue_gas", "HRSG", "STK", mg, P_AMB + 0.002, r["T_stack"], None),
        (6, "HP steam at HRSG outlet (HP SH outlet)", "steam", "HRSG", "PIPE", M["hp_st"], p["sh"], T["sh"], None),
        (7, "HP steam at ST main stop valve inlet", "steam", "PIPE", "ST", M["hp_st"], p["hp_st"], T["hp_st"], None),
        (8, "Cold reheat steam at HP turbine exhaust", "steam", "ST", "PIPE", M["hp_st"], p["hpx"], T["hpx"], None),
        (9, "Cold reheat steam at HRSG reheater inlet", "steam", "PIPE", "HRSG", M["hp_st"], p["rhin"], T["crh"], None),
        (10, "IP superheated steam (joins cold reheat inside the HRSG)", "steam", "HRSG", "HRSG", M["ip"], p["ipsh"], T["ipsh"], None),
        (11, "Hot reheat steam at HRSG outlet", "steam", "HRSG", "PIPE", M["rh"], p["hrh"], T["rh"], None),
        (12, "Hot reheat steam at ST IP stop/control valve inlet", "steam", "PIPE", "ST", M["rh"], p["ip_st"], T["ip_st"], None),
        (13, "LP steam at HRSG outlet", "steam", "HRSG", "PIPE", M["lp"], p["lpsh"], T["lpsh"], None),
        (14, "LP steam at ST LP admission", "steam", "PIPE", "ST", M["lp"], p["lp_st"], T["lp_st"], None),
        (15, "IP turbine exhaust (crossover, internal)", "steam", "ST", "ST", M["rh"], p["x"], T["ipx"], None),
        (16, "LP turbine exhaust to condenser (UEEP)", "steam", "ST", "COND", M["lpt"], p["cond"], T["cond"], r["h_ueep"]),
        (17, "Condensate at hotwell outlet / CEP suction", "water", "COND", "CEP", M["lpt"], p["cond"], T["cond"] - 0.05, None),
        (18, "Condensate at CEP discharge", "water", "CEP", "CMIX", M["lpt"], p["cep"], T["cep"], None)]
    if gas:
        S += [(19, "Fuel gas heater water return to condensate", "water", "FGH", "CMIX", M["fgh"], p["bfp_ip"] - 3.0, m.T["fgh_return"], None)]
    S += [
        (20, "Condensate to HRSG condensate preheater inlet", "water", "CMIX", "HRSG", M["cph"], p["cep"] - 0.5, T["cph_in"], None),
        (21, "Feedwater from LP drum to boiler feed pumps", "water", "HRSG", "BFP", M["bfp"], p["lpd"], T["lpd"] - 0.05, None),
        (22, "HP feedwater at BFP discharge to HP economiser", "water", "BFP", "HRSG", M["hp"], p["bfp_hp"], T["bfp_hp"], None),
        (23, "IP feedwater at BFP interstage to IP economiser", "water", "BFP", "HRSG", M["ipe"], p["bfp_ip"], T["bfp_ip"], None)]
    if gas:
        S += [(24, "IP economiser water to performance fuel gas heater", "water", "HRSG", "FGH", M["fgh"], p["ipd"] + 1.5, T["ip_eco"], None)]
    if M["sp_hp"] > 0.005:
        S += [(29, "HP attemperation spray water (BFP discharge)", "water", "BFP", "HRSG", M["sp_hp"], p["bfp_hp"], T["bfp_hp"], None)]
    if M["sp_rh"] > 0.005:
        S += [(30, "Reheat attemperation spray water (BFP interstage)", "water", "BFP", "HRSG", M["sp_rh"], p["bfp_ip"], T["bfp_ip"], None)]
    cp = t.cp_seawater(22.0)
    S += [(25, "Circulating seawater to condenser inlet", "seawater", "SEA", "COND", r["m_cw"], 2.5, amb["T_sw"], None),
          (26, "Circulating seawater from condenser outlet", "seawater", "COND", "OUT", r["m_cw"], 1.7,
           amb["T_sw"] + r["q_cond"] / (r["m_cw"] * cp), None)]
    rd = lambda x, n: round(float(x), n)  # noqa: E731
    # published precision: states near saturation (hotwell) and the CW outlet are sensitive to rounding -
    # pressures below 0.1 bar with 5 decimals, temperatures with 2 decimals (0.1 K on the CW outlet = 4 MW)
    return [dict(no=n, description=d, fluid=f, from_node=a, to_node=b, mass_flow=rd(mf, 3), pressure=rd(pp, 5 if pp < 0.1 else 3),
                 temperature=rd(tt, 2), enthalpy=(rd(h, 2) if h is not None else None)) for n, d, f, a, b, mf, pp, tt, h in S]


def build():
    out = []
    net_ref = None
    for cid, title, Ta, RH, Tsw, fuel, mode, val in CASES:
        amb = {"T_amb": Ta, "RH": RH, "p_amb": P_AMB, "T_sw": Tsw}
        if mode == "plant":
            target = net_ref * val / 100
            lo, hi = 45.0, 80.0
            f = lambda L: net_estimate(*rate(amb, L, fuel), fuel) - target  # noqa: E731
            flo, fhi = f(lo), f(hi)
            for _ in range(30):                                  # regula falsi on GT load
                L = hi - fhi * (hi - lo) / (fhi - flo)
                fl_ = f(L)
                if abs(fl_) < 20.0:                              # kW
                    break
                if fl_ * flo < 0:
                    hi, fhi = L, fl_
                else:
                    lo, flo = L, fl_
            load = L
        else:
            load = val
        gt, r = rate(amb, load, fuel)
        net = net_estimate(gt, r, fuel)
        if cid == "SRC-NG-100":
            net_ref = net
        l_gt, l_st = gsu_losses(gt["P_gen"], r["P_st"])
        out.append(dict(id=cid, title=title, amb=amb, fuel=fuel, gt_load=round(load, 2), plant_load_est=round(net / net_ref * 100, 2) if net_ref else 100,
                        gt=dict(P_gen=round(gt["P_gen"], 0), HR=round(3600 / gt["eta"], 1), T_exh=gt["T_exh"], limited=gt["P_gen"] >= o.GT_LIMIT - 1),
                        st_output=round(r["P_st"], 0), gsu_gt=round(l_gt, 0), gsu_st=round(l_st, 0), T_stack=round(r["T_stack"], 1),
                        p_cond=round(r["p"]["cond"] * 1000, 2), sprays=[round(r["m"]["sp_hp"], 2), round(r["m"]["sp_rh"], 2)],
                        x_ueep=round(r["x_ueep"], 4), hrsg_balance_kW=round(r["q_gas"] * o.KEEP - r["q_water"], 1),
                        fuel_flow=round(r["g"]["m_f"], 3), water_inj=round(r["g"]["m_w"], 3),
                        gas_T={k: round(v, 1) for k, v in r["gas_T"].items()}, streams=streams(r, amb, fuel)))
        print(f"{cid:12s} GT {gt['P_gen'] / 1e3:6.1f} ({load:5.1f} %)  ST {r['P_st'] / 1e3:6.2f}  net~{net / 1e3:6.1f}  "
              f"stack {r['T_stack']:5.1f}  pc {r['p']['cond'] * 1000:5.1f}  spray {r['m']['sp_hp']:.2f}/{r['m']['sp_rh']:.2f}", flush=True)
    return out


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "revA":         # TQ-IEC-018 (LDO rating) and TQ-IEC-019 (MEL 30 % GT load)
        o.apply_revA()
        CASES[:] = [(c[0], "Site Reference Conditions, natural gas, GT at minimum emissions-compliant load (30 %, low-load "
                     "extension)", *c[2:7], 30.0) if c[0] == "SRC-NG-MEL" else c for c in CASES]
    data = {"basis": "IEC-ALP-PER-001 Rev B design point; rating model iec_offdesign.py", "gt_limit_kW": o.GT_LIMIT,
            "ldo": o.LDO, "fuel_composition": m.FUEL, "cases": build()}
    Path(sys.argv[1]).write_text(json.dumps(data, indent=1, default=float))
