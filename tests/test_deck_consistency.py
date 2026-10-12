"""
test_deck_consistency.py -- the deck must not drift away from the engine.

WHY THIS FILE EXISTS
--------------------
`ppt/build_ppt.py` deliberately does not import the physics engine: an import
would couple a 6-slide presentation to a numerical model and make both harder
to change. The cost of that decision is that every number on the slides is
hand-typed into a FILL dict, so nothing propagates automatically. When the
physics was corrected during the audit the deck kept printing the old numbers
for over an hour, and one of its slides argued a case that had become false.

These tests convert that failure mode into a test failure. They read the FILL
dict straight out of build_ppt.py and assert:

  1. every key the slides reference is present and non-empty;
  2. none of the superseded numbers survive anywhere in the deck;
  3. the headline cost, mass and margin are what the engine computes NOW;
  4. the claims the slides make about PASS/FAIL are true of the engine.
"""

import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

import data_sources                      # noqa: E402
from engine import cost as cst, mission as ms   # noqa: E402

BUILD = os.path.join(ROOT, "ppt", "build_ppt.py")

# Values that were on the deck before it was rebuilt on the verified engine.
# If one of these reappears, the deck has been reverted to unverified numbers.
SUPERSEDED = ["01:23", "7.4", "2210", "2584", "2130", "1.81x", "1.10x",
              "0.52", "30%", "15%", "8 cells", "25 mm",
              # the interim 9-cell/85 mm panel design, replaced by the optimiser's
              # own robust pick once scenario screening became available
              "4488", "8.12x", "105%", "9 cells", "85 mm"]

# What the engine measures for the four designs the slides name.
# cost / mass are deterministic; margin is asserted to 1%.
DESIGNS = {
    "default": dict(cells=6, insulation_mm=10, heater_setpoint_c=-10,
                    heater_max_w=5.0, pass_=False),
    "lazy": dict(cells=10, insulation_mm=10, heater_setpoint_c=0,
                 heater_max_w=5.0, pass_=False),
    "cheap": dict(cells=6, insulation_mm=75, heater_setpoint_c=None,
                  heater_max_w=5.0, pass_=True),
    "robust": dict(cells=12, insulation_mm=75, heater_setpoint_c=None,
                   heater_max_w=5.0, panel_m2=0.06, pass_=True),
}


def load_fill():
    """Parse the FILL dict out of build_ppt.py without importing pythons-pptx."""
    with open(BUILD, encoding="utf-8") as fh:
        src = fh.read()
    block = re.search(r"FILL = \{(.*?)\n\}", src, re.S)
    if block is None:
        raise AssertionError("could not find the FILL dict in ppt/build_ppt.py")
    raw = block.group(1)
    out = {}
    for m in re.finditer(r'^\s*"([a-z_]+)":\s*([^,\n]+)', raw, re.M):
        key, val = m.group(1), m.group(2).strip()
        out[key] = val.strip('"') if val.startswith('"') else val
    return out, src


class TestDeckMatchesEngine(unittest.TestCase):
    """Every headline number on the slides is reproducible from the engine."""

    @classmethod
    def setUpClass(cls):
        cls.fill, cls.src = load_fill()
        env = data_sources.fetch_environment(13.0067, 80.2570, "2026-10-12")
        env["launch_local"] = datetime(2026, 10, 12, 18, 0,
                                     tzinfo=timezone(timedelta(hours=5, minutes=30)))
        cls.env = env
        cls.base = dict(box_area_m2=0.0864, payload_load_w=3.0, k_ins=0.030)

    # ------------------------------------------------------------ structure
    def test_every_key_the_slides_use_is_defined(self):
        used = set(re.findall(r"FILL\[['\"]([a-z_]+)['\"]\]", self.src))
        missing = used - set(self.fill)
        self.assertEqual(missing, set(),
                         f"slides reference undefined FILL keys: {sorted(missing)}")

    def test_no_fill_value_is_blank(self):
        for key, val in self.fill.items():
            self.assertNotEqual(str(val).strip(), "",
                                f"FILL[{key!r}] is empty - the slide would print nothing")

    def test_bench_blanks_are_still_blanks(self):
        """FAQ 14: until a real measurement exists these must stay unfilled.

        A number here would be a fabricated measurement, which is the one thing
        the team must never ship.
        """
        for key in ("bench_predicted_ua", "bench_measured_ua", "bench_error_pct"):
            self.assertEqual(self.fill.get(key), "None",
                             f"{key} has been given a value - a bench figure may only be "
                             "entered after an actual bench run")

    # -------------------------------------------------------- anti-regression
    def test_superseded_numbers_are_gone(self):
        """The unrebuilt deck quoted numbers the corrected engine contradicts.

        Only PROSE is searched. Layout arguments such as `CONTENT_W - 0.52` are
        geometry, not claims, and flagging them would train us to ignore this
        test - which is worse than not having it.
        """
        prose = [m.group(0) for m in re.finditer(r'"(?:[^"\\]|\\.){20,}"', self.src)]
        prose += [m.group(1) for m in re.finditer(r"FILL\s*=\s*\{(.*?)\n\}", self.src, re.S)]
        body = "\n".join(prose)
        found = [v for v in SUPERSEDED if re.search(rf"(?<![\d.]){re.escape(v)}(?![\d])", body)]
        self.assertEqual(found, [],
                         f"deck prose still contains superseded values {found}; "
                         "re-run ppt/build_ppt.py against the current engine")

    # ------------------------------------------------------------ the claims
    def _run(self, name):
        d = dict(self.base)
        d.update({k: v for k, v in DESIGNS[name].items() if k != "pass_"})
        sim = ms.simulate(self.env, d)
        return sim, cst.breakdown(d)

    def test_verdicts_on_the_slides_are_true(self):
        for name, spec in DESIGNS.items():
            with self.subTest(design=name):
                sim, _ = self._run(name)
                if spec["pass_"]:
                    self.assertEqual(sim["verdict"], "PASS",
                                     f"slide calls {name} a PASS but the engine says "
                                     f"{sim['verdict']} at {sim.get('failure_time')}")
                else:
                    self.assertNotEqual(sim["verdict"], "PASS",
                                        f"slide calls {name} a FAIL but the engine passes it")

    def test_recommendation_cost_mass_margin(self):
        sim, br = self._run("cheap")
        self.assertAlmostEqual(float(self.fill["rec_cost"]), br["cost_inr"], delta=1.0)
        self.assertAlmostEqual(float(self.fill["rec_mass"]), br["mass_kg"], delta=0.01)
        self.assertAlmostEqual(
            float(self.fill["rec_margin"].rstrip("x")), sim["energy_margin_ratio"], delta=0.02)

    def test_lazy_fix_cost_matches(self):
        _, br = self._run("lazy")
        self.assertAlmostEqual(float(self.fill["lazy_cost"]), br["cost_inr"], delta=1.0)

    def test_robust_alternative_cost_and_margin(self):
        sim, br = self._run("robust")
        self.assertAlmostEqual(float(self.fill["robust_cost"]), br["cost_inr"], delta=1.0)
        self.assertAlmostEqual(
            float(self.fill["robust_margin"].rstrip("x")),
            sim["energy_margin_ratio"], delta=0.02)

    def test_failure_times_are_real_times(self):
        for name, key in (("default", "fail_time"), ("lazy", "lazy_fail_time")):
            with self.subTest(design=name):
                sim, _ = self._run(name)
                self.assertEqual(self.fill[key], sim["failure_time"],
                                 "the deck and the engine disagree about when this dies")

    def test_tolerance_claims_are_the_engine_windows(self):
        """'survives foam 50% worse' must be the measured edge, not a guess.

        The claim only holds if the design also passes at the NOMINAL value;
        a design that passes nowhere would otherwise produce a nonsense edge.
        """
        for name, key in (("cheap", "rec_tolerance"),):
            with self.subTest(design=name):
                spec = dict(self.base)
                spec.update({k: v for k, v in DESIGNS[name].items() if k != "pass_"})
                claim_pct = float(self.fill[key].rstrip("%"))
                k_bad = 0.030 * (1 + claim_pct / 100.0)
                d = dict(spec, k_ins=k_bad * 1.06)      # slightly beyond the claim
                beyond = ms.simulate(self.env, d)["verdict"]
                self.assertNotEqual(
                    beyond, "PASS",
                    f"{key}: slide claims the design survives foam {claim_pct}% worse, "
                    "but it also survives 6% worse than that - the claim understates it")

    def test_the_recommendation_is_cheaper_than_the_failing_design(self):
        """The slide's central argument: the design that survives is the cheap one."""
        cheap = float(self.fill["rec_cost"])
        default = float(self.fill["default_cost"])
        lazy = float(self.fill["lazy_cost"])
        self.assertLess(default, cheap, "the failing default is no longer the cheap option")
        self.assertLess(cheap, lazy, "adding cells is no longer the expensive option")

    def test_scenario_counts_are_the_stress_engine_counts(self):
        """'1 of 12' and '12 of 12' are claims about simulated scenarios.

        They must come from the declared uncertainty ranges, and the deck must
        never present them as a probability of survival.
        """
        from engine import uncertainty as unc
        for name, key in (("cheap", "rec_scen"), ("robust", "robust_scen")):
            with self.subTest(design=name):
                d = dict(self.base)
                d.update({k: v for k, v in DESIGNS[name].items() if k != "pass_"})
                d.setdefault("min_operating_c", -20.0)
                d.setdefault("max_operating_c", 60.0)
                st = unc.stress_test(self.env, d, n_scenarios=12)
                self.assertEqual(self.fill[key], f"{st['passed']} of {st['n_scenarios']}",
                                 f"{key} on the slide disagrees with the stress engine")

    def test_scenario_rates_are_not_called_probabilities(self):
        """The one wording rule that must never slip."""
        self.assertNotRegex(
            self.src.lower(),
            r"\b(probability|probabilit\w*|chance|odds)\b[^.]{0,40}\b(surviv|pass|success)",
            "the deck links a scenario count to a probability of survival; it must not")

    def test_the_overheating_limit_is_stated(self):
        """The recommendation has an UPPER edge too. Hiding it would be dishonest."""
        self.assertRegex(self.src, r"overheat|overheating|upper edge",
                         "the deck no longer discloses that a much better-insulated box "
                         "overheats - that edge was measured and must stay disclosed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
