"""
test_radiation.py -- the radiative term in engine/thermal.py.

THREE CLAIMS UNDER TEST (Task C of the audit)
---------------------------------------------
  1. Heat leaves the OUTER SKIN by radiation, not the battery and not the
     ambient air. A9 in the audit addendum fixed exactly this, and nothing has
     pinned the fix since.
  2. Insulation moves the skin closer to ambient and so REDUCES radiative loss,
     but can never remove it: if the skin is warmer than the sink, the fourth
     power difference stays positive no matter how thick the foam gets.
  3. The effective sink is NOT deep space. The model parameterises it as
     (air temperature - radiant_offset_c), with a floor at T_SPACE_K. Testing
     that the floor never binds at float conditions is what shows the model is
     not treating the sky as ~0 K.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

from engine import mission as ms                      # noqa: E402
from engine import params as P                        # noqa: E402
from engine import thermal as th                      # noqa: E402
from engine import uncertainty as unc                 # noqa: E402

AREA = 0.0864
K = P.DEFAULT_K_INSULATION

_ENV = None


def float_env():
    """The real forecast environment, fetched once.

    A hand-built env dict is tempting here but has to reproduce every key the
    mission reads (site, profile_start_local, ...), and silently drifts when
    mission.py grows a new one. Using the real fetcher keeps these tests honest.
    """
    global _ENV
    if _ENV is None:
        import data_sources
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        env = data_sources.fetch_environment(13.0067, 80.2570, "2026-10-12")
        env["launch_local"] = _dt(2026, 10, 12, 18, 0,
                                  tzinfo=_tz(_td(hours=5, minutes=30)))
        _ENV = env
    return _ENV
FLOAT_KM = P.BURST_ALT_KM
AMBIENT = -52.0            # typical float-altitude air temperature, C


def radiative_flux_w(t_box_c, insulation_mm, ambient_c=AMBIENT, offset=None):
    """The radiative component, computed from the SOLVED skin temperature."""
    off = P.DEFAULT_RADIANT_OFFSET_C if offset is None else offset
    t_skin = th.skin_temperature_c(t_box_c, ambient_c, FLOAT_KM, insulation_mm,
                                   AREA, K, P.DEFAULT_EMISSIVITY, off)
    t_rad = th.radiant_temperature_c(ambient_c, off)
    return th._radiation_from_skin_w(t_skin, t_rad, AREA, P.DEFAULT_EMISSIVITY)


class TestRadiationUsesSkinTemperature(unittest.TestCase):
    """Claim 1: the radiating node is the skin."""

    def test_the_skin_node_is_distinct_from_both_other_nodes(self):
        """If skin == box or skin == ambient, the model is not two-node at all."""
        t_box, thickness = 5.0, 10.0
        t_skin = th.skin_temperature_c(t_box, AMBIENT, FLOAT_KM, thickness,
                                       AREA, K, P.DEFAULT_EMISSIVITY,
                                       P.DEFAULT_RADIANT_OFFSET_C)
        self.assertNotAlmostEqual(t_skin, t_box, delta=0.5,
                                  msg="skin equals the box temperature: no gradient")
        self.assertNotAlmostEqual(t_skin, AMBIENT, delta=0.5,
                                  msg="skin equals ambient: no gradient")
        self.assertLess(t_skin, t_box, "skin must be cooler than the box it insulates")
        self.assertGreater(t_skin, AMBIENT, "skin must be warmer than the air around it")

    def test_the_radiative_flux_does_not_come_from_the_box_temperature(self):
        """Guard against a regression to the A9 bug (radiation at T_box)."""
        t_box, thickness = 5.0, 10.0
        t_skin = th.skin_temperature_c(t_box, AMBIENT, FLOAT_KM, thickness,
                                       AREA, K, P.DEFAULT_EMISSIVITY,
                                       P.DEFAULT_RADIANT_OFFSET_C)
        t_rad = th.radiant_temperature_c(AMBIENT, P.DEFAULT_RADIANT_OFFSET_C)
        from_skin = th._radiation_from_skin_w(t_skin, t_rad, AREA, P.DEFAULT_EMISSIVITY)
        from_box = th._radiation_from_skin_w(t_box, t_rad, AREA, P.DEFAULT_EMISSIVITY)
        self.assertGreater(from_box, from_skin * 1.2,
                           "radiating at T_box would overstate loss by >20% here - "
                           "the code must use T_skin")

    def test_the_flux_responds_to_the_skin_argument_not_to_ambient(self):
        """Directly: the flux is driven by argument 1."""
        t_rad = -62.0
        low = th._radiation_from_skin_w(-40.0, t_rad, AREA, P.DEFAULT_EMISSIVITY)
        high = th._radiation_from_skin_w(-10.0, t_rad, AREA, P.DEFAULT_EMISSIVITY)
        self.assertGreater(high, low, "a hotter skin must radiate more")

    def test_a_colder_sink_increases_the_flux(self):
        t_skin = -30.0
        warm = th._radiation_from_skin_w(t_skin, -50.0, AREA, P.DEFAULT_EMISSIVITY)
        cold = th._radiation_from_skin_w(t_skin, -80.0, AREA, P.DEFAULT_EMISSIVITY)
        self.assertGreater(cold, warm, "a colder sink must draw more heat away")

    def test_the_source_line_radiates_from_t_skin(self):
        """The requirement was 'show me the exact line'; this pins it.

        If anyone rewrites skin_temperature_c to radiate from t_box_c or
        t_ambient_c, this fails.
        """
        import inspect
        src = inspect.getsource(th.skin_temperature_c)
        self.assertIn("_radiation_from_skin_w(t_skin", src.replace(" ", ""),
                      "skin_temperature_c no longer radiates from t_skin")


class TestInsulationReducesButNeverRemovesRadiation(unittest.TestCase):
    """Claim 2: thicker foam lowers radiative loss; it never zeroes it."""

    def test_doubling_insulation_lowers_radiative_loss(self):
        thin = radiative_flux_w(5.0, 10.0)
        thick = radiative_flux_w(5.0, 20.0)
        self.assertLess(thick, thin,
                        f"doubling insulation raised radiative loss ({thin:.3f} -> "
                        f"{thick:.3f} W)")
        self.assertGreater(thick, 0.0, "radiative loss went to zero, which is unphysical")

    def test_radiative_loss_never_reaches_zero_at_any_thickness(self):
        for mm in (5, 10, 20, 50, 75, 150, 300, 1000):
            with self.subTest(insulation_mm=mm):
                flux = radiative_flux_w(5.0, mm)
                self.assertGreater(flux, 0.0,
                                   f"{mm} mm produced zero radiative loss - the skin "
                                   "cannot stop radiating while it is warmer than the sink")

    def test_loss_decreases_monotonically_with_thickness(self):
        fluxes = [radiative_flux_w(5.0, mm) for mm in (5, 10, 20, 40, 75, 150)]
        self.assertEqual(fluxes, sorted(fluxes, reverse=True),
                         "radiative loss is not monotonic in insulation thickness")

    def test_thicker_insulation_pulls_the_skin_towards_ambient(self):
        """The mechanism behind the reduction, asserted directly."""
        thin = th.skin_temperature_c(5.0, AMBIENT, FLOAT_KM, 10.0, AREA, K,
                                     P.DEFAULT_EMISSIVITY, P.DEFAULT_RADIANT_OFFSET_C)
        thick = th.skin_temperature_c(5.0, AMBIENT, FLOAT_KM, 75.0, AREA, K,
                                      P.DEFAULT_EMISSIVITY, P.DEFAULT_RADIANT_OFFSET_C)
        self.assertLess(thick, thin, "thicker insulation should cool the skin")
        self.assertGreaterEqual(thick, AMBIENT,
                                "the skin should not fall below the air temperature")

    def test_a_passive_box_always_loses_heat_at_float(self):
        """Radiation cannot warm a box that is warmer than its sink."""
        self.assertGreater(th.heat_loss_w(20.0, AMBIENT, FLOAT_KM, 75.0, AREA, K,
                                          P.DEFAULT_EMISSIVITY,
                                          P.DEFAULT_RADIANT_OFFSET_C), 0.0)


class TestSinkAssumptions(unittest.TestCase):
    """Claim 3: the sink is a warm-ish parameterisation, not 0 K."""

    def test_the_sink_is_far_above_deep_space_at_float(self):
        t_rad = th.radiant_temperature_c(AMBIENT, P.DEFAULT_RADIANT_OFFSET_C)
        t_rad_k = P.c_to_k(t_rad)
        self.assertGreater(t_rad_k, 150.0,
                           f"effective sink is {t_rad_k:.0f} K - the model is treating "
                           "the environment as deep space, which would overestimate loss")
        self.assertNotAlmostEqual(t_rad_k, P.T_SPACE_K, delta=50.0)

    def test_the_default_sink_is_colder_than_the_air(self):
        """Documents the direction of the default assumption."""
        t_rad = th.radiant_temperature_c(AMBIENT, P.DEFAULT_RADIANT_OFFSET_C)
        self.assertAlmostEqual(t_rad, AMBIENT - P.DEFAULT_RADIANT_OFFSET_C, delta=1e-9)
        self.assertLess(t_rad, AMBIENT)

    def test_the_space_floor_never_binds_at_float(self):
        """The clamp to T_SPACE_K must be unreachable in flight.

        If it did bind, the sink would be 3 K and loss would be grossly overstated.
        """
        for ambient in (-80.0, -60.0, -52.0, -40.0, -20.0):
            with self.subTest(ambient_c=ambient):
                t_rad = th.radiant_temperature_c(ambient, P.DEFAULT_RADIANT_OFFSET_C)
                self.assertGreater(P.c_to_k(t_rad), P.T_SPACE_K + 50.0)

    def test_sink_offset_moves_the_verdict_ceiling_not_the_floor(self):
        """Physical behaviour: a colder sink must make the box colder."""
        base = dict(box_area_m2=AREA, payload_load_w=3.0, k_ins=K,
                    min_operating_c=-20.0, max_operating_c=60.0, cells=6,
                    insulation_mm=75, heater_setpoint_c=None, heater_max_w=5.0)
        env = float_env()
        warm = ms.simulate(dict(env), dict(base, radiant_offset_c=0.0))["min_box_c"]
        cold = ms.simulate(dict(env), dict(base, radiant_offset_c=20.0))["min_box_c"]
        self.assertLess(cold, warm,
                        "a colder radiative sink must lower the minimum temperature")


class TestRadiantOffsetIsAStressAxis(unittest.TestCase):
    """Audit finding C2: thermal.py claimed this axis existed. Now it does."""

    def test_the_axis_is_declared(self):
        self.assertIn("radiant_offset_c", unc.UNCERTAIN_INPUTS,
                      "the radiative sink is not a declared uncertainty axis")

    def test_the_axis_has_a_range_that_brackets_the_default(self):
        spec = unc.UNCERTAIN_INPUTS["radiant_offset_c"]
        self.assertLess(spec["lo"], P.DEFAULT_RADIANT_OFFSET_C)
        self.assertGreater(spec["hi"], P.DEFAULT_RADIANT_OFFSET_C)
        self.assertLess(spec["lo"], spec["hi"])

    def test_the_axis_has_a_halton_base(self):
        self.assertIn("radiant_offset_c", unc.HALTON_BASES)

    def test_the_axis_is_actually_applied_and_not_a_silent_no_op(self):
        """The failure mode this nearly shipped as: declared, sampled, ignored."""
        design = dict(box_area_m2=AREA, payload_load_w=3.0, k_ins=K, cells=6,
                      insulation_mm=75, heater_setpoint_c=None, heater_max_w=5.0)
        env = float_env()
        _, low = unc._apply(env, design, {"radiant_offset_c": 0.0})
        _, high = unc._apply(env, design, {"radiant_offset_c": 20.0})
        self.assertEqual(low["radiant_offset_c"], 0.0,
                         "_apply drops the radiant factor: the axis would do nothing")
        self.assertEqual(high["radiant_offset_c"], 20.0)

    def test_the_sensitivity_ranking_now_includes_the_axis(self):
        """One-at-a-time attribution must cover the dominant radiative term."""
        env = float_env()
        design = dict(box_area_m2=AREA, payload_load_w=3.0, k_ins=K,
                      min_operating_c=-20.0, max_operating_c=60.0, cells=12,
                      insulation_mm=75, heater_setpoint_c=None, heater_max_w=5.0)
        ranked = unc.sensitivity_ranking(env, design)["ranking"]
        params = [r["parameter"] for r in ranked]
        self.assertIn("radiant_offset_c", params,
                      "the radiative sink is still absent from the sensitivity ranking")


if __name__ == "__main__":
    unittest.main(verbosity=2)
