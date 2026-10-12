"""
test_optimizer_bruteforce.py -- independent check of engine/optimizer.py.

WHY THIS FILE EXISTS
--------------------
`optimizer.py` was overwritten during a repair and rebuilt from the modules that
consume it (`server.py`, `frontier.py`, `battle.py`). A module rebuilt that way is
at risk of a specific failure: its own tests, if any were written afterwards, tend
to re-state the rebuild's assumptions instead of challenging them. So this file
deliberately does NOT reuse `optimizer._record`, `_pick_best` or any other internal.

Instead it:
  1. enumerates the same candidate grid by hand,
  2. runs `mission.simulate` on every candidate DIRECTLY,
  3. picks the winner for each objective with its own logic,
  4. and only then compares against what `optimizer.optimise()` returned.

The grid is shrunk to 2 x 2 x 2 x 1 x 1 = 8 candidates. `_enumerate_space()` reads
the module-level axis lists at call time, so monkeypatching them is enough - the
production module is not modified to make it testable.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

import data_sources                                  # noqa: E402
from engine import cost as cst                        # noqa: E402
from engine import mission as ms                      # noqa: E402
from engine import optimizer as opt                   # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))

# The shrunk grid: 2 x 2 x 2 x 1 x 1 = 8 candidates, as specified.
SMALL = {
    "_CELLS": [6, 12],
    "_INSULATION_MM": [10, 75],
    "_HEATER": [(None, 5.0), (0.0, 5.0)],     # 2 heater settings
    "_PANEL_M2": [0.0],                       # 1 heater rating (in _HEATER), 1 panel
}

BASE = dict(box_area_m2=0.0864, payload_load_w=3.0, k_ins=0.030,
            min_operating_c=-20.0, max_operating_c=60.0)

# The optimiser returns each design MERGED with the fixed base parameters, so a
# like-for-like comparison must reduce both sides to the searched axes.
GRID_KEYS = ("cells", "insulation_mm", "heater_setpoint_c", "heater_max_w", "panel_m2")


def grid_of(design):
    return {k: design[k] for k in GRID_KEYS}


def brute_force_candidates():
    """The same grid, enumerated here, without calling optimizer._enumerate_space."""
    out = []
    for cells in SMALL["_CELLS"]:
        for ins in SMALL["_INSULATION_MM"]:
            for sp, hw in SMALL["_HEATER"]:
                for panel in SMALL["_PANEL_M2"]:
                    out.append({"cells": cells, "insulation_mm": ins,
                                "heater_setpoint_c": sp, "heater_max_w": hw,
                                "panel_m2": panel})
    return out


class TestOptimiserBruteForce(unittest.TestCase):
    """Every objective must agree with an independently computed answer."""

    @classmethod
    def setUpClass(cls):
        env = data_sources.fetch_environment(13.0067, 80.2570, "2026-10-12")
        env["launch_local"] = datetime(2026, 10, 12, 18, 0, tzinfo=IST)
        cls.env = env

        # ---- independent evaluation of every candidate -------------------
        cls.brute = []
        for design in brute_force_candidates():
            full = dict(BASE)
            full.update(design)
            sim = ms.simulate(env, full)
            br = cst.breakdown(full)
            cls.brute.append({
                "design": design,
                "verdict": sim["verdict"],
                "passed": sim["verdict"] == "PASS",
                "cost_inr": br["cost_inr"],
                "mass_kg": br["mass_kg"],
                "margin": sim["energy_margin_ratio"],
                "min_box_c": sim["min_box_c"],
                "max_box_c": sim["max_box_c"],
            })
        cls.feasible = [r for r in cls.brute if r["passed"]]
        cls.infeasible = [r for r in cls.brute if not r["passed"]]

        # ---- runs under test ---------------------------------------------
        cls._patch = mock.patch.multiple(opt, **SMALL)
        cls._patch.start()
        cls.calls = []
        real_simulate = ms.simulate

        def counted(env, design, _real=real_simulate):
            cls.calls.append({k: design[k] for k in
                              ("cells", "insulation_mm", "heater_setpoint_c",
                               "heater_max_w", "panel_m2")})
            return _real(env, design)

        with mock.patch.object(opt.mission, "simulate", side_effect=counted):
            cls.res = opt.optimise(env, BASE, objective="all")
            cls.calls_after_optimise = len(cls.calls)
            cls.first_run = list(cls.calls)
            cls.calls.clear()
            cls.res_again = opt.optimise(env, BASE, objective="all")

    @classmethod
    def tearDownClass(cls):
        cls._patch.stop()

    # ---------------------------------------------------------------- sanity
    def test_the_grid_actually_produced_feasible_designs(self):
        """A brute force that finds nothing would make every later check vacuous."""
        self.assertGreaterEqual(
            len(self.feasible), 2,
            "the small grid produced fewer than 2 feasible designs - the test "
            "would pass trivially; widen the grid")
        self.assertGreaterEqual(len(self.infeasible), 1,
                                "no failing design in the grid: the FAIL path is untested")

    def test_candidate_count_matches_designs_actually_simulated(self):
        """search_limits() must not claim more (or fewer) evaluations than happened."""
        claimed = self.res["search_limits"]["candidates_evaluated"]
        self.assertEqual(claimed, len(brute_force_candidates()),
                         "the reported candidate count is not the size of the grid")
        self.assertEqual(claimed, self.calls_after_optimise,
                         f"optimiser claims {claimed} candidates but called the "
                         f"simulation {self.calls_after_optimise} times")

    def test_every_grid_point_was_simulated_exactly_once(self):
        """No design skipped, none double-counted, none invented."""
        expected = {tuple(sorted(d.items())) for d in brute_force_candidates()}
        actual = {tuple(sorted(d.items())) for d in self.first_run}
        self.assertEqual(actual, expected,
                         "the set of designs simulated differs from the declared grid")
        self.assertEqual(len(self.first_run), len(expected),
                         "a design was simulated more than once without being declared")

    # ------------------------------------------------------- the objectives
    def test_lowest_cost_matches_independent_brute_force(self):
        mine = min(self.feasible, key=lambda r: r["cost_inr"])
        theirs = self.res["picks"]["lowest_cost"]
        self.assertEqual(grid_of(theirs["design"]), mine["design"],
                         f"optimiser chose {grid_of(theirs['design'])} at "
                         f"Rs {theirs['cost_inr']:.0f} but brute force found "
                         f"{mine['design']} at Rs {mine['cost_inr']:.0f}")

    def test_lowest_mass_matches_independent_brute_force(self):
        mine = min(self.feasible, key=lambda r: r["mass_kg"])
        theirs = self.res["picks"]["lowest_mass"]
        self.assertEqual(grid_of(theirs["design"]), mine["design"])
        self.assertAlmostEqual(theirs["mass_kg"], mine["mass_kg"], delta=0.001)

    def test_highest_margin_matches_independent_brute_force(self):
        mine = max(self.feasible, key=lambda r: r["margin"])
        theirs = self.res["picks"]["highest_margin"]
        self.assertEqual(grid_of(theirs["design"]), mine["design"])
        self.assertAlmostEqual(theirs["energy_margin_ratio"], mine["margin"], delta=0.01)

    def test_best_balance_is_feasible_and_declared(self):
        """best_balance uses stated weights, so assert its properties, not its winner."""
        rec = self.res["picks"]["best_balance"]
        self.assertIn(grid_of(rec["design"]), [r["design"] for r in self.feasible],
                      "best_balance returned a design that does not pass")
        self.assertEqual(self.res["balance_weights"], opt.BALANCE_WEIGHTS,
                         "the reported weights are not the weights actually used")
        # weights must sum to 1 or "balance" is unnormalised and the score meaningless
        self.assertAlmostEqual(sum(opt.BALANCE_WEIGHTS.values()), 1.0, delta=1e-9)

    def test_most_robust_requires_screening_and_then_works(self):
        """`most_robust` is meaningless before screening; it must not invent an answer."""
        self.assertIsNone(opt._pick_best(self.res["top_passing"], "most_robust",
                                         -20.0, 60.0),
                          "most_robust returned a winner with no scenario data at all")
        opt.screen_robustness(self.env, self.res, top_n=3, n_scenarios=8)
        robust = self.res["picks"].get("most_robust")
        self.assertIsNotNone(robust, "most_robust still empty after screening")
        self.assertIsNotNone(robust["scenario_pass_fraction"],
                             "the robust pick carries no scenario pass fraction")
        self.assertIsNotNone(self.res["robust_pick"])

    def test_all_five_objectives_are_exposed(self):
        """The task states there are five; a rename must not silently lose one."""
        names = [k for k, _, _ in opt.OBJECTIVES]
        self.assertEqual(len(names), 5, f"expected 5 objectives, found {names}")
        for name in names:
            self.assertIn(name, dict((k, v) for k, v, _ in opt.OBJECTIVES).keys())

    # -------------------------------------------------- no better design missed
    def test_nothing_passing_is_cheaper_than_the_returned_optimum(self):
        """The core optimality property, checked over the whole evaluated grid."""
        chosen = self.res["picks"]["lowest_cost"]
        cheaper = [r for r in self.feasible if r["cost_inr"] < chosen["cost_inr"] - 1e-9]
        self.assertEqual(cheaper, [],
                         f"a PASS design cheaper than the returned one exists: {cheaper}")

    def test_nothing_passing_is_lighter_than_the_returned_optimum(self):
        chosen = self.res["picks"]["lowest_mass"]
        lighter = [r for r in self.feasible if r["mass_kg"] < chosen["mass_kg"] - 1e-9]
        self.assertEqual(lighter, [], f"a PASS design lighter than the returned one: {lighter}")

    def test_feasible_and_infeasible_counts_are_the_truth(self):
        self.assertEqual(self.res["feasible_count"], len(self.feasible))
        self.assertEqual(self.res["infeasible_count"], len(self.infeasible))
        self.assertEqual(self.res["feasible_count"] + self.res["infeasible_count"],
                         self.res["combinations_evaluated"])

    # ------------------------------------------------------------ determinism
    def test_repeated_runs_give_identical_answers(self):
        for name in ("lowest_cost", "lowest_mass", "highest_margin", "best_balance"):
            with self.subTest(objective=name):
                a = grid_of(self.res["picks"][name]["design"])
                b = grid_of(self.res_again["picks"][name]["design"])
                self.assertEqual(a, b, f"{name} is not deterministic across runs")

    def test_ties_break_deterministically_and_by_the_documented_rule(self):
        """Equal cost must resolve on margin, and do so the same way every time."""
        a = {"design": {"cells": 6}, "cost_inr": 2468.0, "energy_margin_ratio": 2.0,
             "mass_kg": 0.7}
        b = {"design": {"cells": 12}, "cost_inr": 2468.0, "energy_margin_ratio": 3.3,
             "mass_kg": 0.7}
        first = opt._pick_best([a, b], "lowest_cost", -20.0, 60.0)
        second = opt._pick_best([a, b], "lowest_cost", -20.0, 60.0)
        self.assertIs(first, second, "tie-break is not stable between calls")
        self.assertEqual(first["design"], b["design"],
                         "on equal cost the larger margin should win")

    def test_objective_order_does_not_change_the_answer(self):
        """Asking for one objective must not differ from asking for all of them."""
        one = opt.optimise(self.env, BASE, objective="lowest_cost")
        self.assertEqual(grid_of(one["picks"]["lowest_cost"]["design"]),
                         grid_of(self.res["picks"]["lowest_cost"]["design"]),
                         "lowest_cost depends on which objectives were requested")

    def test_unknown_objective_is_rejected_not_ignored(self):
        with self.assertRaises(ValueError):
            opt.optimise(self.env, BASE, objective="cheapest_please")


if __name__ == "__main__":
    unittest.main(verbosity=2)
