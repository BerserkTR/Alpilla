"""Thermodynamic properties for heat and mass balances.

- Water and steam: IAPWS-IF97 (package `iapws`). Pressures in bar(a), temperatures in degC, enthalpy kJ/kg, entropy kJ/kgK.
- Ideal-gas mixtures (air, combustion products): NASA 7-coefficient polynomials (GRI-Mech 3.0 thermo data),
  enthalpy of the mixture excluding formation enthalpy (sensible enthalpy, zero at 25 degC).
- Natural gas: combustion stoichiometry and LHV per ISO 6976 (molar net calorific values at 25 degC).
"""
from __future__ import annotations

from functools import lru_cache

R = 8.314462618           # J/(mol K)
T0 = 298.15               # K, reference for sensible enthalpy and LHV
M = {"N2": 28.0134, "O2": 31.9988, "Ar": 39.948, "CO2": 44.0095, "H2O": 18.01528,
     "CH4": 16.04246, "C2H6": 30.06904, "C3H8": 44.09562, "iC4H10": 58.1222, "nC4H10": 58.1222, "C5H12": 72.14878,
     "H2": 2.01588, "He": 4.0026}
# NASA polynomials: (low 300-1000 K, high 1000-5000 K), coefficients a1..a7
NASA = {
    "N2": ((3.298677, 1.4082404e-3, -3.963222e-6, 5.641515e-9, -2.444854e-12, -1020.8999, 3.950372),
           (2.92664, 1.4879768e-3, -5.68476e-7, 1.0097038e-10, -6.753351e-15, -922.7977, 5.980528)),
    "O2": ((3.78245636, -2.99673416e-3, 9.84730201e-6, -9.68129509e-9, 3.24372837e-12, -1063.94356, 3.65767573),
           (3.28253784, 1.48308754e-3, -7.57966669e-7, 2.09470555e-10, -2.16717794e-14, -1088.45772, 5.45323129)),
    "H2O": ((4.19864056, -2.0364341e-3, 6.52040211e-6, -5.48797062e-9, 1.77197817e-12, -30293.7267, -0.849032208),
            (3.03399249, 2.17691804e-3, -1.64072518e-7, -9.7041987e-11, 1.68200992e-14, -30004.2971, 4.9667701)),
    "CO2": ((2.35677352, 8.98459677e-3, -7.12356269e-6, 2.45919022e-9, -1.43699548e-13, -48371.9697, 9.90105222),
            (3.85746029, 4.41437026e-3, -2.21481404e-6, 5.23490188e-10, -4.72084164e-14, -48759.166, 2.27163806)),
    "Ar": ((2.5, 0, 0, 0, 0, -745.375, 4.366), (2.5, 0, 0, 0, 0, -745.375, 4.366)),
    "He": ((2.5, 0, 0, 0, 0, -745.375, 0.928723974), (2.5, 0, 0, 0, 0, -745.375, 0.928723974)),
    "CH4": ((5.14987613, -1.36709788e-2, 4.91800599e-5, -4.84743026e-8, 1.66693956e-11, -10246.6476, -4.64130376),
            (0.074851495, 1.33909467e-2, -5.73285809e-6, 1.22292535e-9, -1.0181523e-13, -9468.34459, 18.437318)),
    "C2H6": ((4.29142492, -5.5015427e-3, 5.99438288e-5, -7.08466285e-8, 2.68685771e-11, -11522.2055, 2.66682316),
             (1.0718815, 2.16852677e-2, -1.00256067e-5, 2.21412001e-9, -1.9000289e-13, -11426.3932, 15.1156107)),
    "H2": ((2.34433112, 7.98052075e-3, -1.9478151e-5, 2.01572094e-8, -7.37611761e-12, -917.935173, 0.683010238),
           (3.3372792, -4.94024731e-5, 4.99456778e-7, -1.79566394e-10, 2.00255376e-14, -950.158922, -3.20502331)),
    "C3H8": ((4.21093013, 1.70886504e-3, 7.06530164e-5, -9.20060565e-8, 3.64618453e-11, -14381.0883, 5.61004451),
             (6.6691976, 2.06108751e-2, -7.36512349e-6, 1.18434262e-9, -7.0691463e-14, -16275.4066, -13.1943379)),
}
# heavier hydrocarbons: molar cp approximated as propane x (C atoms / 3); their share in pipeline gas is < 0.5 mol %
HEAVY = {"iC4H10": 4 / 3, "nC4H10": 4 / 3, "C5H12": 5 / 3}
# fuel components: (C atoms, H atoms, O atoms, N atoms, molar LHV kJ/mol at 25 degC per ISO 6976:2016)
FUEL = {"CH4": (1, 4, 0, 0, 802.69), "C2H6": (2, 6, 0, 0, 1428.84), "C3H8": (3, 8, 0, 0, 2043.37),
        "iC4H10": (4, 10, 0, 0, 2648.42), "nC4H10": (4, 10, 0, 0, 2657.60), "C5H12": (5, 12, 0, 0, 3272.00),
        "H2": (0, 2, 0, 0, 241.72), "N2": (0, 0, 0, 2, 0.0), "CO2": (1, 0, 2, 0, 0.0), "O2": (0, 0, 2, 0, 0.0),
        "He": (0, 0, 0, 0, 0.0)}
DRY_AIR = {"N2": 0.78084, "O2": 0.20946, "Ar": 0.00934, "CO2": 0.00036}   # ISO 2314 / ISO 2533 (mole fractions)
V_MOLAR_STD = 23.6449     # l/mol, ideal gas at 15 degC, 1.01325 bar (Sm3 per ISO 13443)


# ------------------------------------------------------------------ ideal gases
def _coef(sp, T):
    return NASA[sp][0] if T < 1000.0 else NASA[sp][1]


def cp_species(sp, T_C):
    """Molar cp/R -> kJ/kg K of one species at T (degC)."""
    T = T_C + 273.15
    a = _coef(sp, T)
    return (a[0] + a[1] * T + a[2] * T ** 2 + a[3] * T ** 3 + a[4] * T ** 4) * R / M[sp]


def _h_RT(a, T):
    return a[0] + a[1] * T / 2 + a[2] * T ** 2 / 3 + a[3] * T ** 3 / 4 + a[4] * T ** 4 / 5 + a[5] / T


def h_species_molar(sp, T_C):
    """Sensible molar enthalpy J/mol relative to 25 degC."""
    T = T_C + 273.15
    return R * (T * _h_RT(_coef(sp, T), T) - T0 * _h_RT(_coef(sp, T0), T0))


def mixture_M(x: dict) -> float:
    return sum(x[k] * M[k] for k in x)


def h_gas(x: dict, T_C: float) -> float:
    """Sensible enthalpy of an ideal-gas mixture (mole fractions x) in kJ/kg, zero at 25 degC."""
    return sum(x[k] * h_species_molar(k, T_C) for k in x) / mixture_M(x)


def cp_gas(x: dict, T_C: float) -> float:
    mm = mixture_M(x)
    return sum(x[k] * cp_species(k, T_C) * M[k] for k in x) / mm


def T_from_h_gas(x: dict, h: float) -> float:
    """Inverse of h_gas by Newton iteration (degC)."""
    T = 300.0
    for _ in range(50):
        dT = (h - h_gas(x, T)) / cp_gas(x, T)
        T += dT
        if abs(dT) < 1e-6:
            break
    return T


def p_sat_water(T_C: float) -> float:
    """Saturation pressure of water vapour in bar: over liquid (IAPWS-IF97 region 4) above the triple point,
    over ice below it (IAPWS 2011 sublimation equation) - used for humid air at sub-zero ambient."""
    import math

    from iapws import iapws97
    T = T_C + 273.15
    if T >= 273.16:
        return iapws97._PSat_T(T) * 10.0
    th = T / 273.16
    s = sum(a * th ** b for a, b in ((-21.2144006, 0.00333333333), (27.3203819, 1.20666667), (-6.1059813, 1.70333333)))
    return 611.657e-5 * math.exp(s / th)


def humid_air(T_C: float, RH_pct: float, p_bar: float) -> dict:
    """Mole fractions of humid air (ISO dry-air composition, water vapour from relative humidity)."""
    x_w = RH_pct / 100.0 * p_sat_water(T_C) / p_bar
    x = {k: v * (1 - x_w) for k, v in DRY_AIR.items()}
    x["H2O"] = x_w
    return x


# ------------------------------------------------------------------ fuel gas
def fuel_properties(comp_mol_pct: dict) -> dict:
    """Molar mass, LHV (mass and volume, ISO 6976 at 25 degC combustion, 15 degC metering), relative density."""
    tot = sum(comp_mol_pct.values())
    x = {k: v / tot for k, v in comp_mol_pct.items()}
    mm = sum(x[k] * M[k] for k in x)
    lhv_molar = sum(x[k] * FUEL[k][4] for k in x)                   # kJ/mol
    return {"x": x, "M": mm, "LHV_mass": lhv_molar / mm, "LHV_vol": lhv_molar / V_MOLAR_STD,
            "rel_density": mm / mixture_M({**DRY_AIR}), "density_std": mm / V_MOLAR_STD}


def _cp_molar_R(sp, T_C):
    if sp in HEAVY:
        return _cp_molar_R("C3H8", T_C) * HEAVY[sp]
    T = T_C + 273.15
    a = _coef(sp, T)
    return a[0] + a[1] * T + a[2] * T ** 2 + a[3] * T ** 3 + a[4] * T ** 4


def cp_fuel(fx: dict, T_C: float) -> float:
    """Ideal-gas cp of the fuel gas (kJ/kg K) from NASA polynomials of its components."""
    mm = sum(fx[k] * M[k] for k in fx)
    return sum(fx[k] * _cp_molar_R(k, T_C) for k in fx) * R / mm


def h_fuel(fx: dict, T_C: float, steps: int = 40) -> float:
    """Sensible enthalpy of fuel gas relative to 25 degC (kJ/kg), midpoint integration of cp_fuel."""
    a, b = 25.0, T_C
    dt = (b - a) / steps
    return sum(cp_fuel(fx, a + (i + 0.5) * dt) for i in range(steps)) * dt


def combustion(air_x: dict, n_air: float, fuel_x: dict, n_fuel: float, n_water: float = 0.0, atoms: dict | None = None) -> dict:
    """Complete combustion; returns product moles by species (mol/s if inputs are mol/s).
    n_water: water injected into the combustor (leaves as vapour). atoms: {component: (C, H, O, N, LHV)} for fuels not in
    FUEL (e.g. a liquid fuel as one pseudo-molecule CcHh)."""
    table = {**FUEL, **(atoms or {})}
    out = {k: air_x.get(k, 0.0) * n_air for k in ("N2", "O2", "Ar", "CO2", "H2O")}
    out["H2O"] += n_water
    for k, xf in fuel_x.items():
        c, h, o, n, _ = table[k]
        nf = xf * n_fuel
        if k in ("N2", "CO2", "O2"):
            out[k] += nf
            continue
        if k == "He":
            continue
        out["CO2"] += c * nf
        out["H2O"] += h / 2 * nf
        out["O2"] -= (c + h / 4 - o / 2) * nf
    if out["O2"] < 0:
        raise ValueError("not enough air for complete combustion")
    return out


def parse_formula(formula: str) -> tuple[float, float]:
    """'C12H23' -> (12, 23)."""
    import re
    m = re.fullmatch(r"C(\d+(?:\.\d+)?)H(\d+(?:\.\d+)?)", formula.replace(" ", ""))
    if not m:
        raise ValueError(f"liquid fuel formula must be CcHh, got {formula!r}")
    return float(m.group(1)), float(m.group(2))


def liquid_fuel(formula: str, lhv_mass: float, cp: float = 2.0) -> dict:
    """Liquid fuel (e.g. LDO) as one pseudo-molecule CcHh with a stated LHV (MJ/kg) and liquid cp (kJ/kg K)."""
    c, h = parse_formula(formula)
    mm = c * 12.0107 + h * 1.00794
    return {"x": {"LIQ": 1.0}, "M": mm, "LHV_mass": lhv_mass, "LHV_vol": None, "rel_density": None, "density_std": None,
            "atoms": {"LIQ": (c, h, 0, 0, lhv_mass * mm)}, "cp_liquid": cp, "formula": formula}


def h_liquid_fuel(fuel: dict, T_C: float) -> float:
    """Sensible enthalpy of a liquid fuel relative to 25 degC (kJ/kg)."""
    return fuel["cp_liquid"] * (T_C - 25.0)


def h_water_gas_basis(p_bar: float, T_C: float) -> float:
    """Enthalpy of liquid water on the ideal-gas basis used for flue gas (water vapour at 25 degC = 0): for water injected
    into a combustor. IAPWS-IF97 enthalpy minus that of low-pressure vapour at 25 degC."""
    return h_pT(p_bar, T_C) - h_pT(0.01, 25.0)          # 1 kPa: above the triple point, practically ideal gas


def mole_fractions(n: dict) -> dict:
    tot = sum(n.values())
    return {k: v / tot for k, v in n.items() if v > 0}


# ------------------------------------------------------------------ water / steam (IAPWS-IF97)
@lru_cache(maxsize=4096)
def _w(P, T):
    from iapws import IAPWS97
    return IAPWS97(P=P / 10.0, T=T + 273.15)


def h_pT(p_bar, T_C):
    return _w(round(p_bar, 6), round(T_C, 6)).h


def s_pT(p_bar, T_C):
    return _w(round(p_bar, 6), round(T_C, 6)).s


def v_pT(p_bar, T_C):
    return _w(round(p_bar, 6), round(T_C, 6)).v


@lru_cache(maxsize=4096)
def _ph(p, h):
    from iapws import IAPWS97
    return IAPWS97(P=p / 10.0, h=h)


@lru_cache(maxsize=4096)
def _ps(p, s):
    from iapws import IAPWS97
    return IAPWS97(P=p / 10.0, s=s)


def T_ph(p_bar, h):
    return _ph(round(p_bar, 6), round(h, 6)).T - 273.15


def s_ph(p_bar, h):
    return _ph(round(p_bar, 6), round(h, 6)).s


def x_ph(p_bar, h):
    """Steam quality (1.0 for superheated, 0.0 for subcooled)."""
    return _ph(round(p_bar, 6), round(h, 6)).x


def h_ps(p_bar, s):
    return _ps(round(p_bar, 6), round(s, 6)).h


@lru_cache(maxsize=1024)
def _sat(p):
    from iapws import IAPWS97
    return IAPWS97(P=p / 10.0, x=0), IAPWS97(P=p / 10.0, x=1)


def T_sat(p_bar):
    return _sat(round(p_bar, 6))[0].T - 273.15


def p_sat(T_C):
    return p_sat_water(T_C)


def h_f(p_bar):
    return _sat(round(p_bar, 6))[0].h


def h_g(p_bar):
    return _sat(round(p_bar, 6))[1].h


def v_f(p_bar):
    return _sat(round(p_bar, 6))[0].v


def expand(p_in, T_in, p_out, eta):
    """Adiabatic expansion with isentropic efficiency eta; returns outlet enthalpy (kJ/kg)."""
    h1 = h_pT(p_in, T_in)
    h2s = h_ps(p_out, s_pT(p_in, T_in))
    return h1 - eta * (h1 - h2s)


def expand_h(p_in, h_in, p_out, eta):
    h2s = h_ps(p_out, s_ph(p_in, h_in))
    return h_in - eta * (h_in - h2s)


def pump(p_in, T_in, p_out, eta):
    """Liquid pump: returns (outlet enthalpy kJ/kg, specific work kJ/kg)."""
    w = v_pT(p_in, T_in) * (p_out - p_in) * 100.0 / eta     # m3/kg * bar * 100 = kJ/kg
    return h_pT(p_in, T_in) + w, w


def cp_seawater(S_psu: float) -> float:
    """Specific heat of seawater at 15-25 degC (kJ/kg K), linear fit to UNESCO (Millero) data."""
    return 4.186 - 0.0053 * S_psu
