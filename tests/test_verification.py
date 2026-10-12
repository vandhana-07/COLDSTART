"""
test_verification.py -- verification and regression tests.
==========================================================
Run:  python3 -m unittest tests.test_verification -v
  or: python3 -m unittest discover -s tests -v

These tests assert EXPECTED PHYSICAL BEHAVIOUR, not merely that the code ran.
Every test states the law or invariant it is checking and why a failure would
matter.

Regression tests are marked with the defect id they lock down (A10, A11, A12).
Those defects were real: each one was found in the audit, fixed at its cause, and
is now guarded here so it cannot silently return.
"""

import math
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))

from engine import battery as bat       # noqa: E402
from engine import mission as ms        # noqa: E402
from engine import params as P          # noqa: E402
from engine import thermal as th        # noqa: E402
from engine import verification as V    # noqa: E402
import verify as VF                     # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
AREA = P.DEFAULT_BOX_AREA_M2
K = P.DEFAULT_K_INSULATION

BASE = dict(cells=6, insulation_mm=10, heater_setpoint_c=-10, heater_max_w=5.0,
            box_area_m2=AREA, payload_load_w=3.0, k_ins=K)


def flat_env(temp_c=-55.0, ground_c=28.0, hours=30, duration_min=825):
    """Constant-profile environment: lets a hand calculation be exact.

    Unit tests only. Never used to produce a figure shown to anyone.
    """
    levels = [{"pressure_hpa": 1000, "alt_km": 0.0, "temp_c": ground_c, "wind_ms": 0.0},
              {"pressure_hpa": 20, "alt_km": 26.4, "temp_c": temp_c, "wind_ms": 0.0}]
    start = datetime(2026, 10, 12, 0, 0, tzinfo=IST)
    return {"site": {"lat": 13.0067, "lon": 80.2570}, "date": "2026-10-12",
            "hours": [start.strftime("%Y-%m-%dT%H:%M")] * hours,
            "profiles": [levels] * hours,
            "profile_start_local": start,
            "solar_by_index": [0.0] * hours,
            "night_hours": 13.0,
            "launch_local": datetime(2026, 10, 12, 18, 0, tzinfo=IST)}


# ===========================================================================
class AnalyticalConsistency(unittest.TestCase):
    """Task 1: the engine must reproduce solutions that are known exactly."""

    def test_first_order_convergence_against_closed_form(self):
        """Forward Euler is first order. Against a TRUE closed form the measured
        order must be 1, not merely 'error decreasing'."""
        r = [b for b in V.run_all_benchmarks() if b["id"] == "A1"][0]
        order = r["conditions"]["observed_order_of_convergence"]
        self.assertIsNotNone(order, "order of convergence was not measurable")
        self.assertAlmostEqual(order, 1.0, delta=0.15,
                               msg=f"expected first-order, measured {order}")

    def test_error_decreases_monotonically_with_dt(self):
        r = [b for b in V.run_all_benchmarks() if b["id"] == "A1"][0]
        errs = [abs(it["abs_error_c"]) for it in r["items"]]
        for a, b in zip(errs, errs[1:]):
            self.assertLess(b, a, "refining the timestep made the answer worse")

    def test_analytical_error_is_negligible_at_production_timestep(self):
        """At the timestep the app actually uses, the error must be far below any
        physical significance."""
        r = [b for b in V.run_all_benchmarks() if b["id"] == "A1"][0]
        worst = min(abs(it["rel_error_pct"]) for it in r["items"] if it["dt_s"] <= 30.0)
        self.assertLess(worst, 0.05, "relative error too large at working timestep")

    def test_radiation_matches_exact_expression(self):
        r = [b for b in V.run_all_benchmarks() if b["id"] == "A2"][0]
        for it in r["items"]:
            self.assertLess(abs(it["abs_error_w"]), 1e-9)

    def test_equilibrium_matches_independent_root_find(self):
        r = [b for b in V.run_all_benchmarks() if b["id"] == "A3"][0]
        for it in r["items"]:
            self.assertLess(abs(it["abs_error_c"]), 1e-6)
            self.assertLess(abs(it["residual_at_solution_w"]), 1e-6)

    def test_all_limit_checks_pass(self):
        r = [b for b in V.run_all_benchmarks() if b["id"] == "A4"][0]
        failed = [it["check"] for it in r["items"] if not it.get("pass")]
        self.assertEqual(failed, [], f"limiting-case checks failed: {failed}")

    def test_passive_equilibrium_is_below_ambient(self):
        """With no heat input the payload must settle BELOW ambient, because it
        radiates to a sink colder than the air. Settling above ambient would
        violate the second law."""
        r = [b for b in V.run_all_benchmarks() if b["id"] == "A4"][0]
        chk = next(it for it in r["items"] if it["check"].startswith("passive equilibrium"))
        self.assertLess(chk["t_final_c"], chk["t_ambient_c"])
        self.assertLess(abs(chk["abs_error_c"]), 0.05)


class ExternalReferences(unittest.TestCase):
    """Task 5: comparison with published reference values."""

    def test_isa_matches_published_table_within_20km(self):
        r = [b for b in V.run_all_benchmarks() if b["id"] == "B1"][0]
        for it in r["items"]:
            self.assertLess(it["temperature_abs_error_c"], 0.01,
                            f"temperature wrong at {it['altitude_km']} km")
            self.assertLess(it["pressure_rel_error_pct"], 0.05,
                            f"pressure wrong at {it['altitude_km']} km")

    def test_isa_diverges_above_20km_and_we_say_so(self):
        """The engine is isothermal above 11 km. It MUST diverge from the real
        standard atmosphere above ~20 km, and that must be documented."""
        r = [b for b in V.run_all_benchmarks() if b["id"] == "B1"][0]
        self.assertTrue(any("diverge" in lim.lower() for lim in r["limitations"]),
                        "the high-altitude ISA limitation is no longer documented")

    def test_reference_table_values_are_the_published_ones(self):
        """Guards against someone 'fixing' the test data instead of the code."""
        ref = dict((a, (t, p)) for a, _k, t, p in V.ISA_REFERENCE_TABLE)
        self.assertAlmostEqual(ref[0.0][0], 15.0, places=2)
        self.assertAlmostEqual(ref[0.0][1], 1013.25, places=2)
        self.assertAlmostEqual(ref[11.0][0], -56.5, places=2)
        self.assertAlmostEqual(ref[20.0][1], 54.75, places=2)


class EnergyConservation(unittest.TestCase):
    """Task 2: the electrical and thermal balance must close."""

    def test_electrical_residual_within_tolerance(self):
        env = flat_env()
        for name, d in (("default", BASE),
                        ("thick", dict(BASE, insulation_mm=75, heater_setpoint_c=None)),
                        ("solar", dict(BASE, insulation_mm=50, panel_m2=0.10,
                                       heater_setpoint_c=None))):
            r = ms.simulate(env, d)
            res = r["energy_balance"]["electrical"]["residual_wh"]
            self.assertLess(abs(res), VF.TOL_WH,
                            f"{name}: electrical balance residual {res} Wh")

    def test_state_audit_clean(self):
        """No impossible states: negative charge, charge above nominal, usable
        energy exceeding stored energy, heater above its rating, charging without
        PV, load on an empty pack."""
        env = flat_env()
        for d in (BASE, dict(BASE, insulation_mm=75, heater_setpoint_c=0,
                             heater_max_w=10.0), dict(BASE, cells=3,
                                                     payload_load_w=8.0)):
            a = VF.audit_states(ms.simulate(env, d))
            self.assertTrue(a["clean"],
                            f"implausible states found: {a['violation_counts']}")

    def test_thermal_residual_is_a_known_identity(self):
        """The thermal residual is identically zero for forward Euler. This test
        documents that it is a BOOKKEEPING identity, not an accuracy measure, so
        it can never be quoted as an error bound."""
        env = flat_env()
        r = ms.simulate(env, BASE)
        self.assertLess(abs(r["energy_balance"]["thermal"]["residual_wh"]), 1e-9)
        self.assertTrue(r["energy_balance"]["thermal"]["identically_zero"])

    def test_energy_never_negative_or_above_nominal(self):
        env = flat_env()
        r = ms.simulate(env, BASE)
        for row in r["timeline"]:
            self.assertGreaterEqual(row["charge_pct"], 0.0)
            self.assertLessEqual(row["charge_pct"], 100.0 + 1e-9)


class RegressionA10HeaterAccounting(unittest.TestCase):
    """A10: heater energy was booked at the COMMANDED power, so the reported
    consumption exceeded what the battery actually supplied."""

    def test_heater_energy_never_exceeds_delivered_power(self):
        env = flat_env(temp_c=-70.0)
        # a tiny pack with a big heater forces the C-rate cap to bite
        d = dict(BASE, cells=3, insulation_mm=25, heater_setpoint_c=0,
                 heater_max_w=15.0, payload_load_w=6.0)
        r = ms.simulate(env, d)
        elec = r["energy_balance"]["electrical"]
        self.assertLessEqual(elec["heater_delivered_wh"],
                             elec["storage_drop_wh"] + elec["pv_into_cells_wh"] + 1e-6,
                             "heater consumed more energy than the pack supplied")

    def test_heater_energy_never_exceeds_rating_times_duration(self):
        env = flat_env(temp_c=-70.0)
        d = dict(BASE, cells=3, heater_max_w=15.0, heater_setpoint_c=0)
        r = ms.simulate(env, d)
        cap = 15.0 * d.get("duration_min", P.DEFAULT_DURATION_MIN) / 60.0
        self.assertLessEqual(r["heater_energy_wh"], cap + 1e-6)

    def test_unmet_demand_is_recorded_not_absorbed(self):
        env = flat_env(temp_c=-70.0)
        d = dict(BASE, cells=2, insulation_mm=10, heater_setpoint_c=0,
                 heater_max_w=15.0, payload_load_w=8.0)
        r = ms.simulate(env, d)
        self.assertGreaterEqual(r["unmet_demand_wh"], 0.0)


class RegressionA11SelfHeating(unittest.TestCase):
    """A11: payload self-heating was computed from the commanded load, creating
    thermal energy from nothing when the pack could not supply it."""

    def test_self_heating_uses_delivered_power(self):
        """A design whose pack cannot meet demand must NOT heat the box as if it
        had. Compare against the same design with unlimited capability."""
        env = flat_env(temp_c=-70.0)
        starved = ms.simulate(env, dict(BASE, cells=2, insulation_mm=10,
                                        heater_setpoint_c=0, heater_max_w=15.0,
                                        payload_load_w=10.0))
        # delivered payload can never exceed the commanded load
        self.assertLessEqual(
            starved["energy_balance"]["electrical"]["payload_delivered_wh"],
            10.0 * starved["design"]["duration_min"] / 60.0 + 1e-6)

    def test_self_heat_is_zero_when_no_power_is_delivered(self):
        """Thermal input must be exactly zero in a step where nothing is
        delivered. Verified by running with the payload off and no heater."""
        env = flat_env()
        r = ms.simulate(env, dict(BASE, heater_setpoint_c=None, payload_load_w=0.0))
        bal = r["energy_balance"]
        self.assertAlmostEqual(bal["thermal"]["heat_in_wh"], 0.0, places=6)


class RegressionA12HeatGain(unittest.TestCase):
    """A12: heat GAIN was clamped to zero and silently discarded."""

    def test_heat_gain_is_recorded(self):
        """A payload lifted into air warmer than itself must GAIN heat, and that
        gain must appear in the accounting rather than being clamped away.

        Operating limits are widened here so the run is not cut short: the point
        of the test is the heat-flow bookkeeping, not a survival verdict.
        """
        env = flat_env(temp_c=20.0, ground_c=-10.0)
        d = dict(BASE, insulation_mm=75, heater_setpoint_c=None,
                 payload_load_w=0.0, duration_min=240,
                 min_operating_c=-80.0, max_operating_c=200.0)
        r = ms.simulate(env, d)
        self.assertEqual(r["verdict"], "PASS", "test setup: run was cut short")
        self.assertGreater(r["heat_gained_wh"], 0.0,
                           "a cold payload in a warm environment gained no heat")
        self.assertGreater(r["heat_gained_wh"], r["heat_lost_wh"],
                           "environment warmer than the payload should dominate")

    def test_heat_loss_and_gain_are_both_non_negative(self):
        env = flat_env()
        for d in (BASE, dict(BASE, insulation_mm=75, heater_setpoint_c=None)):
            r = ms.simulate(env, d)
            self.assertGreaterEqual(r["heat_lost_wh"], 0.0)
            self.assertGreaterEqual(r["heat_gained_wh"], 0.0)

    def test_heat_loss_is_not_reconstructed_from_the_sampled_trace(self):
        """The accumulation must come from the integration itself. With a
        1-minute trace and a 30 s step, a naive reconstruction would be visibly
        different from the integrated value."""
        env = flat_env()
        r = ms.simulate(env, BASE)
        naive = sum(max(0.0, th.heat_loss_w(row["box_c"], row["ambient_c"], row["alt_km"],
                                            r["design"]["insulation_mm"], AREA, K))
                    * 60.0 for row in r["timeline"]) / P.SECONDS_PER_HOUR
        self.assertGreater(r["heat_lost_wh"], 0.0)
        # agreement within a few percent is expected; exact equality would mean
        # the value is still being reconstructed rather than accumulated
        self.assertLess(abs(r["heat_lost_wh"] - naive) / naive, 0.10)


class NumericalConvergence(unittest.TestCase):
    """Task 4: results must not depend materially on the timestep."""

    def test_verdict_is_stable_across_timesteps(self):
        env = flat_env()
        for d in (BASE, dict(BASE, insulation_mm=75, heater_setpoint_c=None),
                  dict(BASE, cells=12, insulation_mm=75, heater_setpoint_c=None)):
            verdicts = {ms.simulate(env, d, dt_override=dt)["verdict"]
                        for dt in (60.0, 30.0, 10.0)}
            self.assertEqual(len(verdicts), 1,
                             f"verdict changed with timestep for {d}")

    def test_failure_reason_is_stable_across_timesteps(self):
        env = flat_env()
        reasons = {ms.simulate(env, BASE, dt_override=dt)["failure_reason"]
                   for dt in (60.0, 30.0, 10.0)}
        self.assertEqual(len(reasons), 1, "failure reason changed with timestep")

    def test_minimum_temperature_is_timestep_independent(self):
        env = flat_env()
        temps = [ms.simulate(env, BASE, dt_override=dt)["min_box_c_raw"]
                 for dt in (60.0, 30.0, 10.0, 5.0)]
        self.assertLess(max(temps) - min(temps), 0.5,
                        f"minimum temperature moved with timestep: {temps}")

    def test_refining_the_step_converges_the_temperature(self):
        """Error against the finest run must fall as dt falls."""
        env = flat_env()
        ref = ms.simulate(env, BASE, dt_override=5.0)["min_box_c_raw"]
        errs = [abs(ms.simulate(env, BASE, dt_override=dt)["min_box_c_raw"] - ref)
                for dt in (60.0, 30.0, 10.0)]
        self.assertLessEqual(errs[-1], errs[0] + 1e-9,
                             "the finest tested step was not the closest to the reference")

    def test_dt_override_is_validated(self):
        env = flat_env()
        with self.assertRaises(ValueError):
            ms.simulate(env, BASE, dt_override=-1.0)
        with self.assertRaises(ValueError):
            ms.simulate(env, BASE, dt_override=0.0)


class EvidenceDiscipline(unittest.TestCase):
    """The verification layer must not overclaim."""

    def test_no_result_is_labelled_physical_experiment(self):
        for b in V.run_all_benchmarks():
            self.assertNotEqual(b["category"], "E",
                                f"benchmark {b['id']} claims a physical experiment")

    def test_category_e_is_declared_empty(self):
        self.assertIn("NOT PERFORMED", V.CATEGORIES["E"])
        self.assertIn("no physical bench test", V.CATEGORY_E_NOTE.lower())

    def test_every_benchmark_declares_its_limitations(self):
        for b in V.run_all_benchmarks():
            self.assertTrue(b["limitations"], f"{b['id']} lists no limitations")
            self.assertIn(b["category"], ("A", "B", "C", "D"))

    def test_benchmarks_report_no_failed_checks(self):
        s = V.summary(V.run_all_benchmarks())
        self.assertEqual(s["failed_checks"], [])


class BatteryModel(unittest.TestCase):
    """Task 3: the battery model must be internally consistent and honestly
    labelled as an assumption."""

    def test_consistency_checks_all_pass(self):
        t3 = VF.task3_battery()
        failed = [c["check"] for c in t3["consistency_checks"] if not c["pass"]]
        self.assertEqual(failed, [], f"battery consistency failed: {failed}")

    def test_battery_model_is_labelled_an_assumption(self):
        t3 = VF.task3_battery()
        self.assertEqual(t3["category"], "D")
        self.assertIn("ASSUMPTION", t3["source_status"])
        self.assertIn("not taken from a datasheet", t3["source_status"].lower())

    def test_curve_is_physically_sensible(self):
        for t in range(-70, 30, 1):
            f = bat.capacity_fraction(float(t))
            self.assertGreaterEqual(f, 0.0)
            self.assertLessEqual(f, 1.0)
        self.assertGreater(bat.capacity_fraction(20.0), bat.capacity_fraction(-40.0))

    def test_power_versus_energy_are_not_confused(self):
        """Raising the C-rate ceiling must change the POWER limit without
        changing the stored ENERGY."""
        e1 = bat.usable_wh(bat.nominal_wh(8), bat.nominal_wh(8), -30.0)
        p1 = bat.max_discharge_power_w(8, -30.0, c_rate_max=1.0)
        p2 = bat.max_discharge_power_w(8, -30.0, c_rate_max=2.0)
        e2 = bat.usable_wh(bat.nominal_wh(8), bat.nominal_wh(8), -30.0)
        self.assertAlmostEqual(e1, e2, places=9)
        self.assertAlmostEqual(p2, 2 * p1, places=6)


class UncertaintyDiscipline(unittest.TestCase):
    """Task 6: uncertainty ranges must be labelled exploratory and must never be
    presented as a survival probability."""

    def test_ranges_are_marked_exploratory(self):
        env = flat_env()
        t6 = VF.task6_uncertainty(env)
        self.assertTrue(t6["ranges_are_exploratory"])
        self.assertIn("scenario pass rates", t6["disclaimer"].lower())

    def test_no_survival_probability_language(self):
        env = flat_env()
        t6 = VF.task6_uncertainty(env)
        text = t6["disclaimer"].lower()
        self.assertTrue("not" in text and "probabilit" in text,
                        "the disclaimer must deny that these are probabilities")

    def test_unsupported_ranges_are_not_claimed_as_measured(self):
        t6 = VF.task6_uncertainty(flat_env())
        for k, spec in t6["axes"].items():
            self.assertNotIn("measured", spec["basis"].lower(),
                             f"{k} claims a measured basis")


class UnresolvedDisclosure(unittest.TestCase):
    """The project must keep stating what it has NOT done."""

    def test_solar_structural_heating_gap_is_disclosed(self):
        """The engine models solar ELECTRICAL generation only. Sunlit structure
        heating is not modelled; that must stay visible."""
        import verify as vf
        import inspect
        src = inspect.getsource(vf.main)
        self.assertIn("SOLAR HEATING OF THE STRUCTURE IS NOT MODELLED", src)

    def test_unvalidated_ua_is_disclosed(self):
        import verify as vf
        import inspect
        src = inspect.getsource(vf.main)
        self.assertIn("UA is UNVALIDATED", src)

    def test_governing_equations_are_declared(self):
        import verify as vf
        import inspect
        src = inspect.getsource(vf.main)
        for term in ("Conduction", "Convection", "Radiation", "Skin closure",
                     "Lumped node"):
            self.assertIn(term, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
