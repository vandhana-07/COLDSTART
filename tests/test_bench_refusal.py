"""
test_bench_refusal.py -- the bench tool must refuse to produce numbers.

WHY THIS TEST EXISTS
--------------------
There are two ways to fail a judging criterion here. The obvious one is doing no
physical validation. The subtler and far worse one is *appearing* to do physical
validation you never did: a plausible-looking UA figure on a slide, computed from
an empty measurements table, is a fabrication regardless of intent.

`bench/bench_test.py` is built to refuse in that situation -- it prints what to
do and stops before computing anything. That behaviour is a load-bearing honesty
guarantee, so it is pinned here rather than trusted to survive future edits.

This test asserts an ABSENCE. It must never be "fixed" by filling in RUNS with
plausible numbers: evidence category E (physical experiment) stays empty until a
real measurement exists.
"""

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BENCH_DIR = os.path.join(ROOT, "bench")
BENCH = os.path.join(BENCH_DIR, "bench_test.py")


def run_bench():
    return subprocess.run([sys.executable, os.path.basename(BENCH)],
                          cwd=BENCH_DIR, capture_output=True, text=True, timeout=120)


class BenchRefusal(unittest.TestCase):

    def test_no_measurements_are_recorded_in_the_source(self):
        """A fabricated row in RUNS would poison every number downstream."""
        sys.path.insert(0, BENCH_DIR)
        try:
            import bench_test
        finally:
            sys.path.pop(0)
        completed = [r for r in bench_test.RUNS
                     if all(r.get(k) is not None
                            for k in ("volts", "ohms", "t_inside", "t_outside"))]
        self.assertEqual(
            completed, [],
            "bench_test.RUNS contains a completed-looking measurement. If a real "
            "measurement was taken, record it with its date and rig; if not, "
            "remove it - a fabricated row here is exactly what the audit forbids.")

    def test_it_refuses_and_says_why(self):
        result = run_bench()
        self.assertEqual(result.returncode, 0,
                         f"bench_test.py crashed: {result.stderr[-400:]}")
        self.assertIn("NO MEASUREMENTS YET", result.stdout,
                      "the bench tool no longer announces that it has no data")

    def test_it_emits_no_measured_figures(self):
        """The decisive one: no measurement table, no error %, no measured UA."""
        out = run_bench().stdout
        for forbidden in ("UA meas", "error %", "measured UA", "YOUR MEASUREMENTS"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(
                    forbidden, out,
                    f"the bench tool printed '{forbidden}' with an empty RUNS table - "
                    "that is an invented measurement")

    def test_the_model_prediction_is_still_shown(self):
        """Refusing is not the same as being useless: the analyst still needs to
        see what the MODEL claims, so they know what the rig is testing."""
        out = run_bench().stdout
        self.assertIn("PREDICTED UA", out,
                      "the tool should still show the model's predicted UA")


if __name__ == "__main__":
    unittest.main(verbosity=2)
