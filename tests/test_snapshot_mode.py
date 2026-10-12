"""
test_snapshot_mode.py -- the pinned demo snapshot (audit Task 4).

WHAT IS BEING PINNED HERE
-------------------------
A live demo has two enemies: a flaky venue network, and irreproducibility. The
snapshot mode fixes both by replaying a frozen file of REAL API responses. That
only helps if three properties hold, and each is easy to lose in a later edit:

  1. SNAPSHOT MODE MAKES NO NETWORK CALL. Not "usually", not "unless the file is
     missing" -- it must never silently reach the network, or a demo labelled
     SNAPSHOT could be showing live data.
  2. A MISSING FEED RAISES. It must not fall back to a live fetch and it must
     certainly not invent a value.
  3. THE DEFAULT IS UNCHANGED. Live first, labelled CACHED fallback. Snapshot
     mode is opt-in per request.

The snapshot must also contain only real captured responses, never synthetic
filler, so its provenance fields are checked too.
"""

import json
import os
import sys
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "app")
sys.path.insert(0, APP)

import data_sources as ds                                 # noqa: E402

SITE = (13.0067, 80.2570)
DATE = "2026-10-12"


def no_network(*args, **kwargs):
    raise AssertionError("snapshot mode tried to use the network")


class SnapshotFile(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(ds.SNAPSHOT_PATH):
            self.skipTest("no snapshot pinned yet; run python app/snapshot.py")

    def test_the_file_records_where_it_came_from_and_when(self):
        snap = ds.load_snapshot()
        self.assertIn("retrieved_utc", snap)
        self.assertRegex(snap["retrieved_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
                         "the capture instant must be a real UTC timestamp")
        self.assertTrue(snap.get("feeds"), "the snapshot contains no feeds")

    def test_every_feed_carries_its_own_url(self):
        snap = ds.load_snapshot()
        for key, rec in snap["feeds"].items():
            with self.subTest(feed=key):
                self.assertTrue(rec.get("url", "").startswith("https://"),
                                f"{key} has no source URL - it cannot be audited")
                self.assertIn("model", rec)

    def test_the_payloads_are_real_api_responses_not_synthetic_filler(self):
        """An hourly time series with dozens of entries is an API response. A
        hand-written dict of a few numbers would not be."""
        snap = ds.load_snapshot()
        for key, rec in snap["feeds"].items():
            with self.subTest(feed=key):
                hourly = rec["payload"].get("hourly", {})
                self.assertTrue(hourly.get("time"),
                                f"{key} has no hourly time axis")
                self.assertGreaterEqual(len(hourly["time"]), 20,
                                        f"{key} looks too short to be a real response")

    def test_the_feeds_the_engine_needs_are_present(self):
        snap = ds.load_snapshot()
        needed = [key for _, key in ds.environment_urls(*SITE, DATE).values()]
        for key in needed:
            with self.subTest(feed=key):
                self.assertIn(key, snap["feeds"],
                              "the engine asks for a feed the snapshot does not have")

    def test_the_crosscheck_models_are_both_pinned(self):
        """Task 4(a) requires the GFS forecast AND the ECMWF cross-check."""
        snap = ds.load_snapshot()
        keys = " ".join(snap["feeds"])
        self.assertIn("gfs", keys.lower())
        self.assertIn("ecmwf", keys.lower())


class SnapshotIsOffline(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(ds.SNAPSHOT_PATH):
            self.skipTest("no snapshot pinned yet")

    def test_fetch_environment_in_snapshot_mode_never_touches_the_network(self):
        real = urllib.request.urlopen
        urllib.request.urlopen = no_network
        try:
            env = ds.fetch_environment(*SITE, DATE, snapshot=True)
        finally:
            urllib.request.urlopen = real
        self.assertEqual(env["sources"]["upper_air"]["source"], "SNAPSHOT")
        self.assertTrue(env["snapshot_mode"])
        self.assertTrue(env["profiles"], "snapshot produced no profiles")

    def test_a_missing_feed_raises_instead_of_fetching_or_inventing(self):
        """The dangerous failure mode: a partial snapshot that quietly goes live."""
        real = urllib.request.urlopen
        urllib.request.urlopen = no_network
        try:
            with self.assertRaises(RuntimeError) as ctx:
                ds._snapshot_get("this_feed_does_not_exist.json")
        finally:
            urllib.request.urlopen = real
        msg = str(ctx.exception)
        self.assertIn("this_feed_does_not_exist.json", msg)
        self.assertIn("invented", msg.lower(),
                      "the error must state that nothing was invented")

    def test_a_missing_snapshot_file_says_how_to_make_one(self):
        real_path = ds.SNAPSHOT_PATH
        ds.SNAPSHOT_PATH = os.path.join(ROOT, "data", "__nope__.json")
        try:
            with self.assertRaises(RuntimeError) as ctx:
                ds._snapshot_get("anything.json")
        finally:
            ds.SNAPSHOT_PATH = real_path
        self.assertIn("snapshot.py", str(ctx.exception),
                      "the error should tell the user how to pin a snapshot")

    def test_replay_is_deterministic(self):
        a = ds.fetch_environment(*SITE, DATE, snapshot=True)
        b = ds.fetch_environment(*SITE, DATE, snapshot=True)
        for field in ("hours", "profiles", "solar_by_index", "night_hours"):
            self.assertEqual(a[field], b[field], f"{field} differs between replays")


class DefaultBehaviourUnchanged(unittest.TestCase):
    """Task 4(d): snapshot is opt-in. Live-first must remain the default."""

    def test_snapshot_is_not_the_default(self):
        import inspect
        sig = inspect.signature(ds.fetch_environment)
        self.assertEqual(sig.parameters["snapshot"].default, False,
                         "snapshot mode must be opt-in, never the default")

    def test_the_flag_is_per_request_not_a_module_global(self):
        """A global would leak between browser tabs and could report pinned data
        as live, or vice versa."""
        import server
        import inspect
        src = inspect.getsource(server.build_env)
        self.assertIn('q.get("snapshot"', src,
                      "build_env must read the mode from the request")

    def test_the_badge_is_a_string_the_ui_can_render(self):
        if not os.path.exists(ds.SNAPSHOT_PATH):
            self.skipTest("no snapshot pinned yet")
        from datetime import datetime
        env = ds.fetch_environment(*SITE, DATE, snapshot=True)
        # build_env normally adds this; transparency_block depends on it.
        env["launch_local"] = datetime(2026, 10, 12, 18, 0, tzinfo=ds.IST)
        import server
        block = server.transparency_block(env)
        self.assertTrue(block["snapshot"]["active"])
        self.assertTrue(block["snapshot"]["badge"].startswith("SNAPSHOT "),
                        "the badge must be greppable in the UI and the report")
        self.assertIn(block["snapshot"]["retrieved_utc"], block["snapshot"]["badge"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
