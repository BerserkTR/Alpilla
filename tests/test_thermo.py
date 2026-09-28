"""Thermodynamic property core used by the heat and mass balance: checked against published reference values."""
import pytest

from engine.core import thermo as t


@pytest.mark.parametrize("p_bar,T_K,h", [      # IAPWS-IF97 verification tables (regions 1 and 2)
    (30.0, 300.0, 115.331273), (800.0, 300.0, 184.142828), (30.0, 500.0, 975.542239),
    (0.035, 300.0, 2549.91145), (0.035, 700.0, 3335.68375), (300.0, 700.0, 2631.49474)])
def test_iapws_if97_verification(p_bar, T_K, h):
    assert t.h_pT(p_bar, T_K - 273.15) == pytest.approx(h, abs=1e-3)


@pytest.mark.parametrize("sp,cp", [("N2", 1.040), ("O2", 0.918), ("CO2", 0.846), ("H2O", 1.864), ("Ar", 0.520),
                                   ("CH4", 2.226), ("C2H6", 1.75)])
def test_ideal_gas_cp_300K(sp, cp):
    assert t.cp_species(sp, 26.85) == pytest.approx(cp, rel=0.01)


@pytest.mark.parametrize("sp", ["N2", "O2", "CO2", "H2O", "CH4", "C2H6", "C3H8", "H2"])
def test_polynomials_continuous_at_1000K(sp):
    below, above = t.h_species_molar(sp, 726.84), t.h_species_molar(sp, 726.86)
    assert abs(above - below) < 5.0          # J/mol across a 0.02 K step: no jump between the two ranges


def test_gas_enthalpy_inverse_and_air_cp():
    air = t.humid_air(15.0, 60.0, 1.01325)
    assert sum(air.values()) == pytest.approx(1.0)
    assert t.cp_gas(air, 15.0) == pytest.approx(1.009, abs=0.003)
    for T in (15.0, 250.0, 645.0, 1400.0):
        assert t.T_from_h_gas(air, t.h_gas(air, T)) == pytest.approx(T, abs=1e-4)


def test_methane_lhv_and_combustion_mass_balance():
    f = t.fuel_properties({"CH4": 100.0})
    assert f["LHV_mass"] == pytest.approx(50.04, abs=0.02)            # ISO 6976: 50.035 MJ/kg at 25 degC
    gas = t.fuel_properties({"CH4": 93.0, "C2H6": 3.5, "C3H8": 0.8, "N2": 1.55, "CO2": 0.8, "iC4H10": 0.15,
                             "nC4H10": 0.15, "C5H12": 0.05})
    air = t.humid_air(15.0, 70.0, 1.0115)
    n_air, n_f = 25000.0, 1150.0                                        # mol/s
    prod = t.combustion(air, n_air, gas["x"], n_f)
    m_in = n_air * t.mixture_M(air) + n_f * gas["M"]
    m_out = sum(n * t.M[k] for k, n in prod.items())
    assert m_out == pytest.approx(m_in, rel=1e-9)
    assert t.mole_fractions(prod)["O2"] == pytest.approx(0.12, abs=0.02)


def test_turbine_expansion_and_pump():
    h_out = t.expand(165.0, 596.0, 40.5, 1.0)
    assert t.s_ph(40.5, h_out) == pytest.approx(t.s_pT(165.0, 596.0), abs=1e-4)   # isentropic at eta = 1
    h2, w = t.pump(5.0, 150.0, 190.0, 0.8)
    assert 22.0 < w < 27.0 and h2 == pytest.approx(t.h_pT(5.0, 150.0) + w)
    assert t.T_sat(t.p_sat(26.4)) == pytest.approx(26.4, abs=1e-3)


def test_saturation_over_ice_and_water():
    assert t.p_sat_water(-10.0) * 1e5 == pytest.approx(259.9, abs=0.5)      # IAPWS 2011 sublimation, 263.15 K
    assert t.p_sat_water(20.0) * 1e5 == pytest.approx(2339.2, abs=1.0)      # IF97 region 4
    assert t.p_sat_water(0.0) * 1e5 == pytest.approx(611.2, abs=0.5)


def test_liquid_fuel_and_water_injection():
    ldo = t.liquid_fuel("C12H23", 42.9)
    assert ldo["M"] == pytest.approx(167.31, abs=0.01)
    assert 23 * 1.00794 / ldo["M"] == pytest.approx(0.1386, abs=1e-3)            # hydrogen mass fraction of diesel
    air = t.humid_air(15.0, 70.0, 1.0115)
    n_air, n_f, n_w = 27000.0, 130.0, 1250.0                                      # mol/s
    prod = t.combustion(air, n_air, ldo["x"], n_f, n_water=n_w, atoms=ldo["atoms"])
    m_in = n_air * t.mixture_M(air) + n_f * ldo["M"] + n_w * t.M["H2O"]
    assert sum(n * t.M[k] for k, n in prod.items()) == pytest.approx(m_in, rel=1e-9)
    assert prod["CO2"] == pytest.approx(air["CO2"] * n_air + 12 * n_f)
    # injected liquid water at 25 degC carries minus the latent heat on the gas basis (about -2442 kJ/kg)
    assert t.h_water_gas_basis(20.0, 25.0) == pytest.approx(-2440.0, abs=5.0)
    with pytest.raises(ValueError):
        t.parse_formula("diesel")
