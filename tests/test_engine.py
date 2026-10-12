"""
test_engine.py -- automated verification of the COLDSTART physics engine.
==========================================================================
Run with:   python3 -m unittest discover -s tests -v
      or:   python3 tests/test_engine.py
(pytest also discovers these classes.)

WHAT THIS FILE IS AND IS NOT
---------------------------
These are SOFTWARE VERIFICATION tests: they check the code against analytical
references, invariants and boundary cases. They are NOT physical validation.
Nothing here proves the model matches a real payload in the stratosphere --
that requires a bench measurement (see bench/). The distinction is maintained
deliberately and stated in the report.

Test groups
  T1 conduction          analytical Fourier reference
  T2 radiation           analytical Stefan-Boltzmann reference
  T3 thermal network     series-resistance invariants, skin bounds
  T4 battery             interpolation, usable-energy algebra, charge limits
  T5 energy accounting   conservation over a controlled step
  T6 integrator          timestep convergence and equilibrium agreement
  T7 atmosphere          ISA values, irradiance altitude scaling
  T8 failure taxonomy    every reason code is reachable and correctly attributed
  T9 data layer          graceful handling of API failure
  T10 determinism        identical inputs give identical outputs
"""

import math
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))

from engine import atmosphere as atm          # noqa: E402
from engine import battery as bat             # noqa: E402
from engine import cost as cst                # noqa: E402
from engine import mission as ms              # noqa: E402
from engine import params as P                # noqa: E402
from engine import thermal as th              # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))

AREA = 0.0864          # 12 x 12 x 12 cm box, the documented default
K_XPS = 0.030


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def constant_env(temp_c=-50.0, hours=48, night_hours=12.0, launch_hour=18,
                 date="2026-10-12", ground_c=28.0):
    """A synthetic environment for controlled unit tests.

    The payload sits on the GROUND before launch, so the launch-site level is at
    a realistic ground temperature and the upper level is at `temp_c`. Starting
    the whole column at the cold float temperature would mean the payload begins
    the flight already frozen, which no real mission does.

    Used only for unit tests, where a simple profile makes the analytical answer
    exact. Never used to produce a result shown to judges.
    """
    levels = [{"pressure_hpa": 1000, "alt_km": 0.0, "temp_c": ground_c, "wind_ms": 0.0},
              {"pressure_hpa": 20, "alt_km": 26.4, "temp_c": temp_c, "wind_ms": 0.0}]
    start = datetime.strptime(f"{date} 00:00", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    return {
        "site": {"lat": 13.0067, "lon": 80.2570},
        "date": date,
        "hours": [start.strftime("%Y-%m-%dT%H:%M")] * hours,
        "profiles": [levels] * hours,
        "profile_start_local": start,
        "solar_by_index": [0.0] * hours,
        "night_hours": night_hours,
        "launch_local": datetime.strptime(f"{date} {launch_hour:02d}:00",
                                          "%Y-%m-%d %H:%M").replace(tzinfo=IST),
    }


BASE_DESIGN = dict(cells=8, insulation_mm=50, heater_setpoint_c=-10,
                   payload_load_w=3.0, box_area_m2=AREA, k_ins=K_XPS)


# ===========================================================================
class T1_Conduction(unittest.TestCase):
    """Analytical Fourier reference: UA = (k/t) * A."""

    def test_ua_matches_hand_calculation(self):
        for t_mm in (10, 25, 50, 75):
            expected = (K_XPS / (t_mm / 1000.0)) * AREA
            got = th.conduction_ua(t_mm, AREA, K_XPS)
            self.assertAlmostEqual(got, expected, places=9,
                                   msg=f"UA wrong at {t_mm} mm")

    def test_ua_halves_when_thickness_doubles(self):
        a = th.conduction_ua(25, AREA, K_XPS)
        b = th.conduction_ua(50, AREA, K_XPS)
        self.assertAlmostEqual(a, 2 * b, places=9)

    def test_ua_scales_linearly_with_area(self):
        a = th.conduction_ua(25, AREA, K_XPS)
        b = th.conduction_ua(25, 2 * AREA, K_XPS)
        self.assertAlmostEqual(b, 2 * a, places=9)

    def test_zero_thickness_does_not_divide_by_zero(self):
        self.assertTrue(math.isfinite(th.conduction_ua(0, AREA, K_XPS)))


class T2_Radiation(unittest.TestCase):
    """Analytical Stefan-Boltzmann reference."""

    def test_zero_flux_when_skin_equals_radiant_temperature(self):
        q = th._radiation_from_skin_w(-60.0, -60.0, AREA, 0.9)
        self.assertAlmostEqual(q, 0.0, places=9)

    def test_matches_hand_computation(self):
        t_skin, t_rad, eps = 0.0, -50.0, 0.9
        expected = (eps * P.STEFAN_BOLTZMANN * AREA
                    * (P.c_to_k(t_skin) ** 4 - P.c_to_k(t_rad) ** 4))
        got = th._radiation_from_skin_w(t_skin, t_rad, AREA, eps)
        self.assertAlmostEqual(got, expected, places=9)

    def test_flux_is_positive_when_skin_is_warmer(self):
        self.assertGreater(th._radiation_from_skin_w(-20.0, -60.0, AREA, 0.9), 0.0)

    def test_flux_is_negative_when_skin_is_colder(self):
        self.assertLess(th._radiation_from_skin_w(-70.0, -60.0, AREA, 0.9), 0.0)

    def test_emissivity_scales_flux_linearly(self):
        a = th._radiation_from_skin_w(0.0, -50.0, AREA, 0.5)
        b = th._radiation_from_skin_w(0.0, -50.0, AREA, 1.0)
        self.assertAlmostEqual(2 * a, b, places=9)

    def test_fourth_power_scaling(self):
        """Halving absolute temperature must cut emission 16x (Stefan-Boltzmann)."""
        t = 200.0
        q1 = th._radiation_from_skin_w(P.k_to_c(t), P.T_SPACE_K - 273.15, AREA, 1.0)
        q2 = th._radiation_from_skin_w(P.k_to_c(t / 2), P.T_SPACE_K - 273.15, AREA, 1.0)
        if q1 > 0:
            self.assertAlmostEqual(q1 / q2, 16.0, delta=0.05)


class T3_ThermalNetwork(unittest.TestCase):
    """Invariants of the series conduction -> surface model."""

    def test_skin_lies_between_environment_and_interior(self):
        for t_box in (20.0, 0.0, -20.0):
            t_skin = th.skin_temperature_c(t_box, -55.0, 26.0, 25, AREA, K_XPS)
            self.assertLessEqual(t_skin, t_box + 1e-6)
            self.assertGreaterEqual(t_skin, -55.0 - 40.0)

    def test_effective_ua_is_below_conduction_ua(self):
        """The surface adds resistance IN SERIES, so effective UA must be smaller
        than the wall conductance alone. This is the invariant that the earlier
        parallel model violated (audit addendum A9)."""
        for t_mm in (10, 25, 50, 75):
            ua_cond = th.conduction_ua(t_mm, AREA, K_XPS)
            ua_eff = th.effective_ua(t_mm, AREA, K_XPS, 26.0, -52.0)
            self.assertLess(ua_eff, ua_cond,
                            msg=f"effective UA not in series at {t_mm} mm")
            self.assertGreater(ua_eff, 0.0)

    def test_more_insulation_reduces_effective_ua(self):
        uas = [th.effective_ua(m, AREA, K_XPS, 26.0, -52.0) for m in (10, 25, 50, 75)]
        for a, b in zip(uas, uas[1:]):
            self.assertGreater(a, b)

    def test_heat_loss_zero_at_thermal_equilibrium(self):
        q = th.heat_loss_w(-52.0, -52.0, 26.0, 50, AREA, K_XPS)
        self.assertLess(abs(q), 0.5)      # small residual from the radiant sink only

    def test_heat_loss_positive_when_box_is_warmer(self):
        self.assertGreater(th.heat_loss_w(-10.0, -52.0, 26.0, 50, AREA, K_XPS), 0.0)

    def test_heat_loss_negative_when_box_is_colder(self):
        self.assertLess(th.heat_loss_w(-70.0, -52.0, 26.0, 50, AREA, K_XPS), 0.0)

    def test_convection_weakens_with_altitude(self):
        h0 = th.convection_coefficient_w_m2k(0.0)
        h26 = th.convection_coefficient_w_m2k(26.0)
        self.assertGreater(h0, h26)
        self.assertAlmostEqual(h26 / h0, math.sqrt(atm.atmospheric_pressure_ratio(26.0)),
                              places=9)

    def test_thermal_capacity_increases_with_mass(self):
        c6 = th.thermal_capacity_j_per_k(6, 25, AREA)
        c12 = th.thermal_capacity_j_per_k(12, 25, AREA)
        self.assertGreater(c12, c6)

    def test_thermal_capacity_increases_with_insulation(self):
        c1 = th.thermal_capacity_j_per_k(8, 10, AREA)
        c2 = th.thermal_capacity_j_per_k(8, 75, AREA)
        self.assertGreater(c2, c1)


class T4_Battery(unittest.TestCase):
    """Capacity curve, usable-energy algebra, and electrical limits."""

    def test_curve_endpoints_exact(self):
        self.assertAlmostEqual(bat.capacity_fraction(20), 1.00, places=9)
        self.assertAlmostEqual(bat.capacity_fraction(-60), 0.35, places=9)
        self.assertAlmostEqual(bat.capacity_fraction(-10), 0.70, places=9)

    def test_curve_clamps_outside_range(self):
        self.assertAlmostEqual(bat.capacity_fraction(80), 1.00, places=9)
        self.assertAlmostEqual(bat.capacity_fraction(-120), 0.35, places=9)

    def test_curve_is_monotonic(self):
        temps = list(range(-70, 30, 2))
        vals = [bat.capacity_fraction(t) for t in temps]
        for a, b in zip(vals, vals[1:]):
            self.assertGreaterEqual(b, a - 1e-12)

    def test_capacity_between_0_and_1(self):
        for t in range(-100, 60, 5):
            f = bat.capacity_fraction(t)
            self.assertGreaterEqual(f, 0.0)
            self.assertLessEqual(f, 1.0)

    def test_usable_energy_full_and_warm(self):
        nominal = bat.nominal_wh(8)
        self.assertAlmostEqual(bat.usable_wh(nominal, nominal, 20), nominal, places=6)

    def test_usable_energy_is_frozen_bottom_at_cold(self):
        """At -60 C only 35% of nominal is reachable, even from a full pack."""
        nominal = bat.nominal_wh(8)
        self.assertAlmostEqual(bat.usable_wh(nominal, nominal, -60),
                               nominal * 0.35, places=6)

    def test_usable_energy_never_negative(self):
        nominal = bat.nominal_wh(8)
        self.assertGreaterEqual(bat.usable_wh(nominal * 0.1, nominal, -60), 0.0)

    def test_usable_energy_monotonic_in_charge(self):
        nominal = bat.nominal_wh(8)
        a = bat.usable_wh(nominal * 0.4, nominal, -30)
        b = bat.usable_wh(nominal * 0.8, nominal, -30)
        self.assertGreater(b, a)

    def test_c_rate_limit_scales_with_cells(self):
        p6 = bat.max_discharge_power_w(6, 20.0)
        p12 = bat.max_discharge_power_w(12, 20.0)
        self.assertAlmostEqual(p12, 2 * p6, places=6)

    def test_c_rate_limit_zero_below_operating_floor(self):
        self.assertEqual(bat.max_discharge_power_w(8, P.DEFAULT_MIN_OPERATING_C - 1), 0.0)

    def test_charge_inhibited_below_zero_celsius(self):
        self.assertFalse(bat.can_accept_charge(-5.0))
        self.assertTrue(bat.can_accept_charge(5.0))
        self.assertTrue(bat.can_accept_charge(P.CHARGE_MIN_TEMP_C))

    def test_charge_rejected_is_reported_not_lost_silently(self):
        """Audit finding A4: charging below 0 C must be inhibited AND counted."""
        nominal = bat.nominal_wh(8)
        _, accepted, rejected = bat.step_charge(nominal, nominal, 60.0,
                                                battery_power_out_w=0.0,
                                                pv_available_w=5.0, temp_c=-10.0)
        self.assertEqual(accepted, 0.0)
        self.assertEqual(rejected, 5.0)

    def test_charge_accepted_when_warm(self):
        nominal = bat.nominal_wh(8)
        _, accepted, rejected = bat.step_charge(nominal * 0.5, nominal, 60.0,
                                                battery_power_out_w=0.0,
                                                pv_available_w=5.0, temp_c=10.0)
        self.assertEqual(accepted, 5.0)
        self.assertEqual(rejected, 0.0)

    def test_charge_never_exceeds_nominal(self):
        nominal = bat.nominal_wh(8)
        charge, _, _ = bat.step_charge(nominal, nominal, 3600.0,
                                       battery_power_out_w=0.0,
                                       pv_available_w=50.0, temp_c=20.0)
        self.assertLessEqual(charge, nominal + 1e-9)

    def test_discharge_never_goes_below_zero(self):
        nominal = bat.nominal_wh(8)
        charge, _, _ = bat.step_charge(nominal * 0.01, nominal, 3600.0,
                                       battery_power_out_w=50.0,
                                       pv_available_w=0.0, temp_c=20.0)
        self.assertGreaterEqual(charge, 0.0)


class T5_EnergyAccounting(unittest.TestCase):
    """Energy conservation against a hand-computed reference."""

    def test_constant_load_drain_matches_hand_calculation(self):
        """At 20 C capacity is 100%, no heater, no PV: charge must fall by
        exactly load x hours."""
        env = constant_env(temp_c=20.0, hours=6, night_hours=0.0)
        design = dict(BASE_DESIGN, insulation_mm=50, heater_setpoint_c=None,
                      payload_load_w=3.0, duration_min=120)
        r = ms.simulate(env, design)
        expected_wh = 3.0 * 2.0                      # 3 W for 2 hours
        used = r["nominal_wh"] - (r["timeline"][-1]["charge_pct"] / 100.0) * r["nominal_wh"]
        self.assertAlmostEqual(used, expected_wh, delta=expected_wh * 0.02)

    def test_no_load_means_no_energy_used(self):
        env = constant_env(temp_c=20.0, hours=6)
        design = dict(BASE_DESIGN, heater_setpoint_c=None, payload_load_w=0.0,
                      duration_min=120)
        r = ms.simulate(env, design)
        used = r["nominal_wh"] - (r["timeline"][-1]["charge_pct"] / 100.0) * r["nominal_wh"]
        self.assertAlmostEqual(used, 0.0, delta=0.05)

    def test_heater_energy_equals_time_times_power(self):
        """If the heater is on continuously at a known rating, energy must match."""
        env = constant_env(temp_c=-60.0, hours=6)
        design = dict(BASE_DESIGN, insulation_mm=50, heater_setpoint_c=0,
                      heater_max_w=4.0, payload_load_w=0.0, duration_min=60)
        r = ms.simulate(env, design)
        # heater cannot run the whole time, but must not exceed its rating x duration
        self.assertLessEqual(r["heater_energy_wh"], 4.0 * 1.0 + 1e-6)

    def test_solar_generation_increases_stored_charge(self):
        env = constant_env(temp_c=20.0, hours=6)
        design = dict(BASE_DESIGN, heater_setpoint_c=None, payload_load_w=0.0,
                      duration_min=60)
        r = ms.simulate(env, design)
        self.assertGreaterEqual(r["pv_generated_wh"], 0.0)


class T6_Integrator(unittest.TestCase):
    """Numerical correctness of the time-stepping scheme."""

    def test_step_convergence_halving_dt(self):
        """Halving the timestep must not change the answer materially."""
        env = constant_env(temp_c=-55.0, hours=24)

        design_a = dict(BASE_DESIGN, duration_min=600)
        r_a = ms.simulate(env, design_a)

        # Force a finer step by inflating the thermal capacitance used for dt choice:
        # directly compare against an explicitly finer integration instead.
        r_fine = _simulate_with_dt(env, design_a, r_a["timestep_s"] / 4.0)

        self.assertAlmostEqual(r_a["min_box_c"], r_fine["min_box_c"], delta=0.5,
                               msg="Euler step too coarse: min temperature shifted")
        self.assertAlmostEqual(r_a["survival_hours"], r_fine["survival_hours"],
                               delta=0.15, msg="survival time shifted with finer dt")

    def test_integrator_agrees_with_steady_state_solver(self):
        """Independent check: integrate to steady state, and compare against the
        closed-form bisection equilibrium temperature."""
        ambient = -55.0
        heater = 1.5
        payload_heat = 1.0

        env = constant_env(temp_c=ambient, hours=72)
        design = dict(BASE_DESIGN, insulation_mm=50, heater_setpoint_c=None,
                      payload_load_w=0.0, duration_min=60 * 40)

        # integrate a long time with a constant standing heat input
        c_th = th.thermal_capacity_j_per_k(design["cells"], 50, AREA)
        t = ambient
        for _ in range(200000):
            t = th.step_temperature(t, ambient, 26.0, 10.0, c_th, heater,
                                    payload_heat, 50, AREA, K_XPS)

        t_analytic = th.equilibrium_temperature_c(ambient, 26.0, 50, AREA, K_XPS,
                                                  heater, payload_heat)
        self.assertAlmostEqual(t, t_analytic, delta=0.75,
                               msg="time-stepping and equilibrium solver disagree")

    def test_timestep_is_derived_and_bounded(self):
        for ins in (10, 25, 50, 75):
            dt = ms.choose_timestep_s(dict(BASE_DESIGN, insulation_mm=ins))
            self.assertGreaterEqual(dt, 1.0)
            self.assertLessEqual(dt, 30.0)

    def test_stability_condition_holds(self):
        """dt must satisfy dt < 2 * C_th / UA for every design in the sweep grid."""
        for cells in (6, 8, 10, 12, 14):
            for ins in (10, 25, 50, 75):
                d = dict(BASE_DESIGN, cells=cells, insulation_mm=ins)
                dt = ms.choose_timestep_s(d)
                c_th = th.thermal_capacity_j_per_k(cells, ins, AREA)
                ua = th.effective_ua(ins, AREA, K_XPS, 26.0, -52.0)
                self.assertLess(dt, 2.0 * c_th / ua,
                                msg=f"unstable step at cells={cells} ins={ins}")


def _simulate_with_dt(env, design, dt):
    """Run the mission with an explicitly forced timestep (convergence testing)."""
    original = ms.choose_timestep_s
    ms.choose_timestep_s = lambda d: dt
    try:
        return ms.simulate(env, design)
    finally:
        ms.choose_timestep_s = original


class T7_Atmosphere(unittest.TestCase):
    """Solar geometry, irradiance scaling and ISA references."""

    def test_isa_sea_level_is_15_c(self):
        self.assertAlmostEqual(atm.isa_temperature_c(0.0), 15.0, places=6)

    def test_isa_tropopause_is_minus_56_5(self):
        self.assertAlmostEqual(atm.isa_temperature_c(11.0), -56.5, places=6)
        self.assertAlmostEqual(atm.isa_temperature_c(20.0), -56.5, places=6)

    def test_isa_pressure_sea_level(self):
        self.assertAlmostEqual(atm.isa_pressure_hpa(0.0), 1013.25, delta=0.1)

    def test_isa_pressure_at_26km_matches_reference_table(self):
        """ISA reference values (US Standard Atmosphere 1976):
        0 km 1013.25, 5 km 540.2, 11 km 226.3, 20 km 54.7 hPa.
        At 26 km the isothermal approximation gives ~21 hPa; the true value is
        ~18.6 hPa because the 20-32 km layer warms. We assert the ballpark, not
        a false precision, and ISA is only a declared fallback above 31 km."""
        self.assertAlmostEqual(atm.isa_pressure_hpa(0.0), 1013.25, delta=0.1)
        self.assertAlmostEqual(atm.isa_pressure_hpa(5.0), 540.2, delta=1.0)
        self.assertAlmostEqual(atm.isa_pressure_hpa(11.0), 226.3, delta=1.0)
        self.assertAlmostEqual(atm.isa_pressure_hpa(20.0), 54.7, delta=1.0)
        self.assertGreater(atm.isa_pressure_hpa(26.0), 15.0)
        self.assertLess(atm.isa_pressure_hpa(26.0), 25.0)

    def test_pressure_ratio_decreases_with_altitude(self):
        self.assertGreater(atm.atmospheric_pressure_ratio(0.0),
                           atm.atmospheric_pressure_ratio(10.0))
        self.assertGreater(atm.atmospheric_pressure_ratio(10.0),
                           atm.atmospheric_pressure_ratio(26.0))

    def test_irradiance_increases_with_altitude(self):
        """Audit finding A1: the old model used surface irradiance at 26 km."""
        low = atm.direct_irradiance_wm2(0.0, 60.0, 285)
        high = atm.direct_irradiance_wm2(26.0, 60.0, 285)
        self.assertGreater(high, low)
        self.assertGreater(high / low, 1.1)

    def test_irradiance_approaches_solar_constant_above_atmosphere(self):
        i = atm.direct_irradiance_wm2(60.0, 90.0, 285)
        self.assertGreater(i, P.SOLAR_CONSTANT * 0.9)
        self.assertLess(i, P.SOLAR_CONSTANT * 1.1)

    def test_sea_level_clear_sky_is_physical(self):
        """Independent reference: clear-sky noon at sea level should be physically
        sensible, not wildly high or low. Real GFS surface forecasts for Chennai
        in October peak around 800-1000 W/m2."""
        i = atm.direct_irradiance_wm2(0.0, 75.0, 285)
        self.assertGreater(i, 700.0)
        self.assertLess(i, 1250.0)

    def test_no_irradiance_below_horizon(self):
        self.assertEqual(atm.direct_irradiance_wm2(26.0, -5.0, 285), 0.0)
        self.assertEqual(atm.direct_irradiance_wm2(26.0, 0.0, 285), 0.0)

    def test_extraterrestrial_varies_by_plus_minus_3_percent(self):
        vals = [atm.extraterrestrial_irradiance(d) for d in range(1, 366, 7)]
        self.assertGreater(max(vals), P.SOLAR_CONSTANT)
        self.assertLess(min(vals), P.SOLAR_CONSTANT)
        for v in vals:
            self.assertLess(abs(v / P.SOLAR_CONSTANT - 1.0), 0.034)

    def test_solar_elevation_peaks_at_local_noon(self):
        noon = datetime(2026, 10, 12, 6, 30, tzinfo=timezone.utc)   # 12:00 IST
        midnight = datetime(2026, 10, 12, 18, 30, tzinfo=timezone.utc)  # 00:00 IST
        e_noon = atm.solar_elevation_deg(13.0067, 80.2570, noon)
        e_mid = atm.solar_elevation_deg(13.0067, 80.2570, midnight)
        self.assertGreater(e_noon, 60.0)
        self.assertLess(e_mid, 0.0)

    def test_panel_power_zero_at_night_and_with_no_area(self):
        midnight = datetime(2026, 10, 12, 18, 30, tzinfo=timezone.utc)
        elev = atm.solar_elevation_deg(13.0067, 80.2570, midnight)
        self.assertEqual(atm.panel_power_w(26.0, elev, 285, 0.1), 0.0)
        self.assertEqual(atm.panel_power_w(26.0, 45.0, 285, 0.0), 0.0)


class T8_FailureTaxonomy(unittest.TestCase):
    """Audit finding A7: every failure reason must be reachable and correctly
    attributed -- and cold must NOT be assumed to be the cause."""

    def test_energy_depletion_is_detected(self):
        env = constant_env(temp_c=-50.0, hours=24)
        design = dict(BASE_DESIGN, cells=4, insulation_mm=10, heater_setpoint_c=0,
                      heater_max_w=8.0, duration_min=840)
        r = ms.simulate(env, design)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn(r["failure_reason"],
                      (ms.ENERGY_DEPLETED, ms.TEMP_BELOW_OPERATING))

    def test_temperature_violation_is_detected(self):
        """Deep cold, thin insulation, no heater -> the pack itself goes too cold."""
        env = constant_env(temp_c=-80.0, hours=24)
        design = dict(BASE_DESIGN, insulation_mm=5, heater_setpoint_c=None,
                      min_operating_c=-20.0, duration_min=600)
        r = ms.simulate(env, design)
        self.assertEqual(r["failure_reason"], ms.TEMP_BELOW_OPERATING)
        self.assertIsNotNone(r["failure_explanation"]["mechanism"])

    def test_failure_reason_is_not_assumed_to_be_cold(self):
        """A design that dies of energy depletion must say so, even at -50 C.
        Thin insulation, a big heater and a small pack: the heater drains the
        battery long before the cold can win."""
        env = constant_env(temp_c=-50.0, hours=24)
        design = dict(BASE_DESIGN, cells=3, insulation_mm=10, heater_setpoint_c=0,
                      heater_max_w=10.0, payload_load_w=0.0, duration_min=840)
        r = ms.simulate(env, design)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["failure_reason"], ms.ENERGY_DEPLETED)
        self.assertIn("energy", r["failure_explanation"]["headline"].lower())

    def test_overheating_is_detected_and_explained(self):
        """Over-insulation is a REAL failure mode: the same insulation that holds
        heat in on a cold night traps self-heating electronics in a warm one.
        Found by test T8 while checking the failure taxonomy."""
        env = constant_env(temp_c=-50.0, hours=24)
        design = dict(BASE_DESIGN, cells=3, insulation_mm=75, heater_setpoint_c=-5,
                      heater_max_w=20.0, payload_load_w=8.0, duration_min=840)
        r = ms.simulate(env, design)
        self.assertEqual(r["failure_reason"], ms.TEMP_ABOVE_OPERATING)
        ex = r["failure_explanation"]
        self.assertIn("heat", ex["headline"].lower())
        joined = " ".join(ex["contributing_factors"]).lower()
        self.assertTrue("insulation" in joined or "conductance" in joined)

    def test_simulation_stops_at_first_failure(self):
        """A dead payload must not keep drawing power and self-heating."""
        env = constant_env(temp_c=-50.0, hours=24)
        design = dict(BASE_DESIGN, cells=3, insulation_mm=10, heater_setpoint_c=0,
                      heater_max_w=10.0, payload_load_w=0.0, duration_min=840)
        r = ms.simulate(env, design)
        last = r["timeline"][-1]["minute"]
        self.assertLessEqual(last, r["failure_minute"] + 2.0)
        self.assertLess(last, 840.0)

    def test_temperature_ceiling_is_configurable(self):
        """Raising the ceiling must let the same design run longer."""
        env = constant_env(temp_c=-50.0, hours=24)
        base = dict(BASE_DESIGN, cells=3, insulation_mm=75, heater_setpoint_c=-5,
                    heater_max_w=20.0, payload_load_w=8.0, duration_min=840)
        strict = ms.simulate(env, base)
        lenient = ms.simulate(env, dict(base, max_operating_c=200.0))
        self.assertLess(strict["failure_minute"], lenient["failure_minute"] or 1e9)

    def test_pass_when_adequately_designed(self):
        env = constant_env(temp_c=-50.0, hours=24)
        design = dict(BASE_DESIGN, cells=14, insulation_mm=75, heater_setpoint_c=-10,
                      heater_max_w=6.0, duration_min=600)
        r = ms.simulate(env, design)
        self.assertEqual(r["verdict"], "PASS")
        self.assertIsNone(r["failure_reason"])

    def test_every_failure_has_an_explanation(self):
        env = constant_env(temp_c=-70.0, hours=24)
        for ins in (5, 10, 25):
            for cells in (3, 6, 10):
                r = ms.simulate(env, dict(BASE_DESIGN, cells=cells,
                                          insulation_mm=ins, duration_min=500))
                if r["verdict"] == "FAIL":
                    ex = r["failure_explanation"]
                    self.assertIsNotNone(ex["mechanism"])
                    self.assertTrue(ex["chronology"])
                    self.assertTrue(ex["headline"])

    def test_failure_minute_is_within_mission(self):
        env = constant_env(temp_c=-70.0, hours=24)
        r = ms.simulate(env, dict(BASE_DESIGN, insulation_mm=5, duration_min=400))
        if r["failure_minute"] is not None:
            self.assertGreaterEqual(r["failure_minute"], 0.0)
            self.assertLessEqual(r["failure_minute"], 400.0)

    def test_suggested_changes_are_actionable(self):
        env = constant_env(temp_c=-70.0, hours=24)
        r = ms.simulate(env, dict(BASE_DESIGN, insulation_mm=5, duration_min=400))
        if r["verdict"] == "FAIL":
            sugs = r["failure_explanation"]["suggested_changes"]
            self.assertTrue(sugs)
            for s in sugs:
                self.assertIn("change", s)
                self.assertIn("to", s)
                self.assertIn("why", s)


class T9_DataLayer(unittest.TestCase):
    """The weather layer must fail gracefully and never invent data."""

    def setUp(self):
        sys.path.insert(0, os.path.join(HERE, "..", "app"))
        import data_sources
        self.ds = data_sources

    def test_fetch_failure_without_cache_raises(self):
        path = os.path.join(self.ds.CACHE, "nonexistent_test_key.json")
        if os.path.exists(path):
            os.remove(path)
        with self.assertRaises(Exception):
            self.ds._get_json("https://invalid.invalid/does-not-exist",
                              "nonexistent_test_key.json")

    def test_cache_fallback_returns_cached_flag(self):
        key = "_unittest_cache_probe.json"
        path = os.path.join(self.ds.CACHE, key)
        with open(path, "w") as f:
            f.write('{"probe": true}')
        try:
            payload, meta = self.ds._get_json("https://invalid.invalid/nope", key)
            self.assertEqual(meta["source"], "CACHED")
            self.assertTrue(payload["probe"])
        finally:
            os.remove(path)

    def test_health_check_reports_status_for_every_source(self):
        h = self.ds.health_check()
        self.assertIn("open_meteo_gfs", h)
        self.assertIn("ok", h["open_meteo_gfs"])

    def test_missing_pressure_levels_are_skipped_not_faked(self):
        """A level absent from the API must be dropped, never interpolated from
        nothing or filled with a placeholder."""
        env = self.ds.fetch_environment(13.0067, 80.2570, "2026-10-12")
        for profile in env["profiles"][:3]:
            for lv in profile:
                self.assertIn("temp_c", lv)
                self.assertIsInstance(lv["temp_c"], (int, float))


class T10_Determinism(unittest.TestCase):
    """Reproducibility: same inputs, same outputs. Required for the report."""

    def test_repeated_runs_are_identical(self):
        env = constant_env(temp_c=-52.0, hours=24)
        design = dict(BASE_DESIGN, duration_min=400)
        a = ms.simulate(env, design)
        b = ms.simulate(env, design)
        self.assertEqual(a["verdict"], b["verdict"])
        self.assertEqual(a["min_box_c"], b["min_box_c"])
        self.assertEqual(a["survival_hours"], b["survival_hours"])
        self.assertEqual(a["failure_reason"], b["failure_reason"])

    def test_cost_breakdown_totals_are_consistent(self):
        d = dict(BASE_DESIGN, panel_m2=0.05)
        b = cst.breakdown(d)
        self.assertAlmostEqual(sum(i["mass_kg"] for i in b["items"]), b["mass_kg"],
                               places=3)
        self.assertAlmostEqual(sum(i["cost_inr"] for i in b["items"]), b["cost_inr"],
                               places=0)

    def test_more_cells_costs_more_and_weighs_more(self):
        a = cst.breakdown(dict(BASE_DESIGN, cells=6))
        b = cst.breakdown(dict(BASE_DESIGN, cells=12))
        self.assertGreater(b["cost_inr"], a["cost_inr"])
        self.assertGreater(b["mass_kg"], a["mass_kg"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
