"""
test_night_dip.py -- night duration is measured at FLOAT altitude, not at sea level.

WHY THIS FILE EXISTS
--------------------
`data_sources.fetch_environment` used to count the hours in which the sun's
*ground-level* geometric elevation was below zero, sampled once per hour. That
overstates the night twice over:

  1. it ignores the dip of the horizon. From 26 km the horizon sits 5.17 deg
     below level, so the payload is still in daylight for ~21 minutes after
     ground sunset and again before ground sunrise;
  2. sampling on the hour quantises the answer by up to +/-1 h, which is larger
     than the dip correction itself, so it can hide the effect.

The reported figure for Chennai on 12 Oct 2026 therefore read 13 h where the
dip-corrected continuous value is 11.5 h.

`night_hours` is a REPORTED DURATION ONLY. No physics reads it -- the simulation
decides day and night for itself, per timestep, from the sun's elevation. One
test below pins that property so a future change cannot quietly promote this
label into a constraint without a verdict changing.
"""

import math
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

import data_sources                                   # noqa: E402
from engine import atmosphere as atm                  # noqa: E402
from engine import mission as ms                      # noqa: E402
from engine import params as P                        # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
LAT, LON = 13.0067, 80.2570
DATE = "2026-10-12"


def dip_deg(h_km, r_km=P.EARTH_RADIUS_KM):
    """Independent statement of the horizon dip, written from the geometry."""
    return math.degrees(math.acos(r_km / (r_km + h_km)))


def continuous_night_hours(threshold_deg, step_min=1):
    """Independent minute-by-minute scan of the dark part of the local day."""
    d = datetime.strptime(DATE, "%Y-%m-%d").replace(tzinfo=IST)
    dark = 0
    for m in range(0, 24 * 60, step_min):
        t = (d + timedelta(minutes=m)).astimezone(timezone.utc)
        if atm.solar_elevation_deg(LAT, LON, t) <= threshold_deg:
            dark += step_min
    return dark / 60.0


class TestHorizonDip(unittest.TestCase):
    """The dip relation itself."""

    def test_dip_is_zero_at_zero_height(self):
        """No height, no dip -- the correction must vanish, not go negative."""
        self.assertAlmostEqual(dip_deg(0.0), 0.0, places=9)

    def test_dip_matches_published_values(self):
        """Checked against the accepted dip at heights a balloon actually uses."""
        # ~2.5 deg at 6 km, ~3.5 deg at 12 km, ~5.2 deg at 26 km
        self.assertAlmostEqual(dip_deg(6.0), 2.49, delta=0.05)
        self.assertAlmostEqual(dip_deg(12.0), 3.52, delta=0.05)
        self.assertAlmostEqual(dip_deg(26.0), 5.17, delta=0.05)

    def test_dip_grows_with_height(self):
        vals = [dip_deg(h) for h in (1, 5, 10, 20, 26, 35)]
        self.assertEqual(vals, sorted(vals), "dip must increase monotonically with height")

    def test_the_engine_constant_is_a_real_earth_radius(self):
        """Guards against a placeholder value sneaking into the dip formula."""
        self.assertAlmostEqual(P.EARTH_RADIUS_KM, 6371.0, delta=1.0)

    def test_fully_below_horizon_is_still_night(self):
        """A sun far below the horizon counts as night - no off-by-one at the dip."""
        d = datetime.strptime(DATE, "%Y-%m-%d").replace(tzinfo=IST)
        midnight = (d + timedelta(hours=0)).astimezone(timezone.utc)
        elevation = atm.solar_elevation_deg(LAT, LON, midnight)
        self.assertLess(elevation, -dip_deg(P.BURST_ALT_KM),
                        "local midnight should be well inside the dip-corrected night")


class TestReportedNightDuration(unittest.TestCase):
    """The value the pipeline actually reports."""

    @classmethod
    def setUpClass(cls):
        cls.env = data_sources.fetch_environment(LAT, LON, DATE)

    def test_reported_night_matches_an_independent_scan_at_float_altitude(self):
        expected = continuous_night_hours(-dip_deg(P.BURST_ALT_KM))
        self.assertAlmostEqual(self.env["night_hours"], expected, delta=0.05,
                               msg="the reported night does not match a direct scan")

    def test_float_altitude_night_is_shorter_than_ground_night(self):
        """The physical claim: height shortens the night. Not just 'it ran'."""
        ground = continuous_night_hours(0.0)
        self.assertLess(self.env["night_hours"], ground,
                        "night at float altitude must be shorter than at ground level")

    def test_dip_correction_is_about_40_minutes_in_total(self):
        """Sanity band: ~21 min of extra daylight at each end, ~42 min in total."""
        removed_h = continuous_night_hours(0.0) - continuous_night_hours(
            -dip_deg(P.BURST_ALT_KM))
        self.assertGreater(removed_h, 0.5, "dip correction implausibly small")
        self.assertLess(removed_h, 1.2, "dip correction implausibly large")

    def test_the_old_definition_would_have_read_13_hours(self):
        """Document the number that was on the deck, so the change is traceable."""
        d = datetime.strptime(DATE, "%Y-%m-%d").replace(tzinfo=IST)
        whole_hours = sum(
            1 for k in range(24)
            if atm.solar_elevation_deg(LAT, LON, (d + timedelta(hours=k)).astimezone(
                timezone.utc)) <= 0)
        self.assertEqual(whole_hours, 13,
                         "the superseded ground-level whole-hour definition changed; "
                         "update the audit note if this is deliberate")
        self.assertNotAlmostEqual(self.env["night_hours"], 13.0, delta=0.5,
                                  msg="the reported night still equals the old figure")

    def test_night_is_a_plausible_duration(self):
        self.assertGreater(self.env["night_hours"], 6.0)
        self.assertLess(self.env["night_hours"], 18.0)

    def test_data_sources_no_longer_imports_the_legacy_physics_module(self):
        """The dip fix also removed a stale `from physics import ...` inside the
        night computation; `physics.py` is the superseded model."""
        with open(os.path.join(ROOT, "app", "data_sources.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("from physics import", src,
                         "data_sources still imports the legacy physics module")


class TestNightHoursIsALabel(unittest.TestCase):
    """Pins the property that makes the Task B change safe to make.

    If anyone ever wires `night_hours` into a constraint, a verdict will move
    when the label moves, and this test will fail loudly.
    """

    def test_changing_the_label_does_not_change_any_verdict(self):
        env = data_sources.fetch_environment(LAT, LON, DATE)
        env["launch_local"] = datetime(2026, 10, 12, 18, 0, tzinfo=IST)
        design = dict(box_area_m2=0.0864, payload_load_w=3.0, k_ins=0.030,
                      cells=6, insulation_mm=10, heater_setpoint_c=-10.0,
                      heater_max_w=5.0)

        a = dict(env, night_hours=11.5)
        b = dict(env, night_hours=99.0)
        ra, rb = ms.simulate(a, design), ms.simulate(b, design)

        self.assertEqual(ra["verdict"], rb["verdict"],
                         "night_hours feeds the physics: a verdict moved when only "
                         "this reported duration changed")
        self.assertEqual(ra["failure_time"], rb["failure_time"])
        self.assertEqual(ra["min_box_c"], rb["min_box_c"])
        self.assertAlmostEqual(ra["survival_hours"], rb["survival_hours"], delta=1e-9)

    def test_the_simulation_derives_daylight_itself(self):
        """It must, since it does not consume night_hours. A panel generates only
        while the sun is up, which is the observable consequence."""
        env = data_sources.fetch_environment(LAT, LON, DATE)
        env["launch_local"] = datetime(2026, 10, 12, 18, 0, tzinfo=IST)
        design = dict(box_area_m2=0.0864, payload_load_w=3.0, k_ins=0.030,
                      cells=6, insulation_mm=75, heater_setpoint_c=None,
                      heater_max_w=5.0, panel_m2=0.06)
        night_flight = ms.simulate(dict(env), design)["pv_generated_wh"]

        day_env = dict(env)
        day_env["launch_local"] = datetime(2026, 10, 12, 8, 0, tzinfo=IST)
        day_flight = ms.simulate(day_env, design)["pv_generated_wh"]

        self.assertGreater(day_flight, night_flight,
                           "a daytime flight should generate more solar energy than a "
                           "night flight; day/night is not being derived per timestep")


if __name__ == "__main__":
    unittest.main(verbosity=2)
