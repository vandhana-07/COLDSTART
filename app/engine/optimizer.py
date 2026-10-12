"""
optimiser.py -- search the design space for the best payload configuration.

WHAT THIS DOES
--------------
Every candidate is a dict of design parameters. Every candidate is run through
`mission.simulate()` -- the same engine the single-design view uses, on the same
forecast, with the same timestep. There is no surrogate model and no shortcut:
if the optimiser says a design passes, that design passes when you type the
numbers into the Design tab by hand.

WHAT THIS DOES NOT DO
---------------------
It does not find the global optimum, and its results are never labelled
"optimal". The grid is finite, and a coarse grid can hide a design that lives
between its points. `search_limits` returns a structured description of exactly
what was and was not covered; that description is surfaced in the UI and the
exported report next to any recommendation.

FAILURE IS NOT MONOTONE IN ANY SINGLE KNOB
------------------------------------------
More cells means more heat capacity AND more self-heating AND more battery to
keep warm. Thicker insulation keeps heat in but also traps the payload's own
waste heat. A design can therefore fail from being too cold AND from being too
warm. This module only ever enumerates candidates; it never binary-searches a
scalar direction of improvement, because no such direction is guaranteed.
"""

from __future__ import annotations

from . import cost as cost_mod
from . import mission

try:                                    # stress screening is optional at import time
    from . import uncertainty as unc
except Exception:                       # pragma: no cover
    unc = None


# --------------------------------------------------------------------------
# The design space.
# 4 battery sizes x 4 insulation thicknesses x 3 heater settings x 2 panel
# areas, with the heater rating only enumerated when a heater is actually
# switched on (with no setpoint the power rating does nothing, so enumerating
# it would inflate the candidate count without exploring anything).
# --------------------------------------------------------------------------
_CELLS = [4, 6, 8, 10, 12]
_INSULATION_MM = [10, 20, 30, 50, 75]
_PANEL_M2 = [0.0, 0.06]
_HEATER = [                      # (setpoint_c, max_w)
    (None, 5.0),                 # no heater
    (-10.0, 5.0), (-10.0, 10.0),
    (0.0, 5.0), (0.0, 10.0),
]

OBJECTIVES = [
    ("lowest_cost", "Lowest cost",
     "cheapest design that satisfies every constraint"),
    ("lowest_mass", "Lowest mass",
     "lightest design that satisfies every constraint"),
    ("highest_margin", "Highest margin",
     "most usable energy left at touchdown - the conservative choice"),
    ("best_balance", "Best balance",
     "cost, mass, energy margin and clearance above the cold limit, weighted"),
    ("most_robust", "Most robust",
     "highest share of stressed scenarios survived - requires screening"),
]
OBJECTIVE_TEXT = {k: f"{label} - {desc}" for k, label, desc in OBJECTIVES}

# Weights for best_balance. Ranks are used, not raw values: cost is in
# thousands of rupees and mass is under a kilogram, so adding raw units would
# let cost dominate purely because of the exponent. Stated here, shown in the
# UI, and reported with the result.
BALANCE_WEIGHTS = {"cost": 0.40, "mass": 0.20, "margin": 0.15, "clearance": 0.25}


def _enumerate_space():
    """Every candidate in the declared grid, in a deterministic order."""
    out = []
    for cells in _CELLS:
        for ins in _INSULATION_MM:
            for sp, hw in _HEATER:
                for panel in _PANEL_M2:
                    out.append({"cells": cells, "insulation_mm": ins,
                                "heater_setpoint_c": sp, "heater_max_w": hw,
                                "panel_m2": panel})
    return out


def _record(env, design, base):
    """Run one candidate and flatten everything the UI and the report need."""
    full = dict(base)
    full.update(design)
    sim = mission.simulate(env, full)
    br = cost_mod.breakdown(full)
    design_keys = ("cells", "insulation_mm", "heater_setpoint_c", "heater_max_w",
                   "panel_m2", "box_area_m2", "payload_load_w", "k_ins")
    return {
        "design": {k: full[k] for k in design_keys if k in full},
        "verdict": sim["verdict"],
        "passed": sim["verdict"] == "PASS",
        "failure_time": sim.get("failure_time"),
        "failure_reason": sim.get("failure_reason"),
        "failure_text": sim.get("failure_text"),
        "survival_hours": sim.get("survival_hours"),
        "min_box_c": sim.get("min_box_c"),
        "max_box_c": sim.get("max_box_c"),
        "min_usable_pct": sim.get("min_usable_pct"),
        "energy_margin_ratio": sim.get("energy_margin_ratio"),
        "energy_margin_wh": sim.get("energy_margin_wh"),
        "effective_ua_w_per_k": sim.get("effective_ua_w_per_k"),
        "heater_energy_wh": sim.get("heater_energy_wh"),
        "pv_generated_wh": sim.get("pv_generated_wh"),
        "cost_inr": br["cost_inr"],
        "mass_kg": br["mass_kg"],
        "scenario_pass_fraction": None,     # filled in by screen_robustness
        "scenario_headline": None,
    }


def _clearance(rec, min_operating_c):
    """Degrees between the coldest the box got and the limit it must not cross."""
    if rec.get("max_box_c") is None or rec.get("min_box_c") is None:
        return float("-inf")
    # clearance is the smaller of the two distances: how far above the cold
    # limit it stayed, and how far below the hot limit it stayed.
    cold = rec["min_box_c"] - min_operating_c
    hot = rec.get("_max_operating_c", 60.0) - rec["max_box_c"]
    return min(cold, hot)


def _rank_score(recs, key, reverse):
    n = len(recs)
    if n == 1:
        return {0: 0.0}
    order = sorted(range(n), key=lambda i: recs[i][key], reverse=reverse)
    return {idx: pos / (n - 1) for pos, idx in enumerate(order)}


def _balance_scores(recs, min_operating_c, max_operating_c):
    for r in recs:
        r["_max_operating_c"] = max_operating_c
        r["_clearance_c"] = _clearance(r, min_operating_c)
    n = len(recs)
    if n == 1:
        return {0: 0.0}
    r_cost = _rank_score(recs, "cost_inr", False)
    r_mass = _rank_score(recs, "mass_kg", False)
    r_marg = _rank_score(recs, "energy_margin_ratio", True)
    r_clear = _rank_score(recs, "_clearance_c", True)
    w = BALANCE_WEIGHTS
    return {i: (w["cost"] * r_cost[i] + w["mass"] * r_mass[i]
                + w["margin"] * r_marg[i] + w["clearance"] * r_clear[i])
            for i in range(n)}


def _pick_best(recs, objective, min_operating_c, max_operating_c):
    """Best record for one objective. Returns None if the objective is not met."""
    if not recs:
        return None
    if objective == "lowest_cost":
        return min(recs, key=lambda r: (r["cost_inr"], -r["energy_margin_ratio"]))
    if objective == "lowest_mass":
        return min(recs, key=lambda r: (r["mass_kg"], -r["energy_margin_ratio"]))
    if objective == "highest_margin":
        return max(recs, key=lambda r: (r["energy_margin_ratio"], -r["cost_inr"]))
    if objective == "best_balance":
        score = _balance_scores(recs, min_operating_c, max_operating_c)
        return recs[min(range(len(recs)), key=lambda i: score[i])]
    if objective == "most_robust":
        # only meaningful once screen_robustness() has run
        screened = [r for r in recs if r.get("scenario_pass_fraction") is not None]
        if not screened:
            return None
        return max(screened, key=lambda r: (r["scenario_pass_fraction"],
                                            r["energy_margin_ratio"],
                                            -r["cost_inr"]))
    raise ValueError(f"unknown objective {objective!r}")


def search_limits(n_candidates, feasible, infeasible):
    """Structured, honest description of the search. Surfaced in UI + report."""
    return {
        "candidates_evaluated": n_candidates,
        "feasible": feasible,
        "infeasible": infeasible,
        "axes_searched": {
            "cells": _CELLS,
            "insulation_mm": _INSULATION_MM,
            "heater_setting": ["off", "-10 C @ 5 W", "-10 C @ 10 W",
                               "0 C @ 5 W", "0 C @ 10 W"],
            "solar_panel_m2": _PANEL_M2,
        },
        "held_fixed": [
            "box internal free area 0.0864 m2 (the kit enclosure)",
            "payload electrical load 3.0 W (given by the mission profile)",
            "insulation conductivity 0.030 W/m/K (datasheet value, NOT bench-measured)",
            "launch date and site: the single forecast that is loaded",
        ],
        "not_searched": [
            "box shapes other than the kit enclosure",
            "active cooling or venting as a remedy for overheating",
            "phase-change material",
            "multi-layer or vacuum insulation",
            "other launch dates or sites",
        ],
        "resolution_note": (
            f"Insulation is sampled every 10-25 mm across {len(_INSULATION_MM)} thicknesses. "
            "A design that survives only in a narrower window than that could be missed."
        ),
        "convergence_claim": (
            "NONE. This is an enumerated finite grid, not a search that converges to a "
            "global optimum, and no result is labelled optimal."
        ),
    }


def optimise(env, base_design, objective="best_balance", progress=None):
    """Enumerate the design space and return the best candidate per objective.

    Parameters
    ----------
    env          : environment dict from data_sources.fetch_environment
    base_design  : parameters held fixed (box area, payload load, k_ins, limits)
    objective    : one of OBJECTIVES' keys, or "all" for every objective
    progress     : optional callable(done, total) for a live progress bar

    Never raises for an empty feasible set: it returns best=None and a message,
    so the UI can say "nothing in this grid works" rather than failing.
    """
    min_op = base_design.get("min_operating_c", -20.0)
    max_op = base_design.get("max_operating_c", 60.0)

    combos = _enumerate_space()
    records, infeasible = [], []
    total = len(combos)
    for i, design in enumerate(combos):
        rec = _record(env, design, base_design)
        (records if rec["passed"] else infeasible).append(rec)
        if progress and (i % 5 == 0 or i == total - 1):
            progress(i + 1, total)

    violation_counts = {}
    for r in infeasible:
        key = r["failure_reason"] or "UNKNOWN"
        violation_counts[key] = violation_counts.get(key, 0) + 1

    limits = search_limits(total, len(records), len(infeasible))

    if not records:
        return {
            "objective": objective,
            "objective_text": OBJECTIVE_TEXT.get(objective, objective),
            "best": None, "picks": {}, "robust_pick": None, "runner_up": None,
            "feasible_count": 0, "infeasible_count": len(infeasible),
            "combinations_evaluated": total,
            "violation_counts": violation_counts,
            "search_limits": limits,
            "top_passing": [], "screened": [],
            "message": ("No design in the searched grid satisfies every constraint on "
                        "this forecast. The failure reasons are listed so the binding "
                        "constraint is visible."),
        }

    wanted = [o[0] for o in OBJECTIVES] if objective == "all" else \
        [o[0] for o in OBJECTIVES if o[0] == objective]
    picks = {}
    for key in wanted:
        best = _pick_best(records, key, min_op, max_op)
        if best is not None:
            picks[key] = best
    # always publish the cheap ones even when only one objective was asked for
    for key in ("lowest_cost", "lowest_mass", "highest_margin", "best_balance"):
        if key not in picks:
            b = _pick_best(records, key, min_op, max_op)
            if b is not None:
                picks[key] = b
    if "most_robust" in picks:
        picks["most_robust"] = _pick_best(records, "most_robust", min_op, max_op)

    primary = picks.get(objective) or picks.get("best_balance") or records[0]

    ordered = sorted(records, key=lambda r: (r["cost_inr"], -r["energy_margin_ratio"]))
    runner = None
    if len(ordered) > 1:
        runner = ordered[1]

    return {
        "objective": objective,
        "objective_text": OBJECTIVE_TEXT.get(objective, objective),
        "best": primary,
        "picks": picks,
        "robust_pick": None,
        "runner_up": runner,
        "feasible_count": len(records),
        "infeasible_count": len(infeasible),
        "combinations_evaluated": total,
        "violation_counts": violation_counts,
        "search_limits": limits,
        "balance_weights": BALANCE_WEIGHTS,
        "top_passing": ordered[:40],
        "screened": [],
    }


def screen_robustness(env, res, top_n=8, n_scenarios=16, progress=None):
    """Stress-test the most promising candidates and record how they hold up.

    Screening is run on the cheapest feasible designs, because that is the set
    a student team would actually consider building; a design nobody can afford
    is not a recommendation.

    The pass fraction written back is a SCENARIO PASS RATE over declared input
    ranges, never a probability. The wording comes from
    uncertainty.stress_test so it cannot drift into a survival-probability claim.

    Mutates `res` in place and returns it.
    """
    if unc is None:
        return res
    feasible = res.get("top_passing") or []
    if not feasible:
        return res

    picks = res.get("picks") or {}
    seeds = []
    seen = set()

    def add(rec):
        if rec is None:
            return
        key = repr(sorted(rec["design"].items()))
        if key not in seen:
            seen.add(key)
            seeds.append(rec)

    # seed with each objective's pick, then fill the rest with the cheapest
    for key in ("lowest_cost", "lowest_mass", "best_balance", "highest_margin"):
        add(picks.get(key))
    for rec in feasible:
        if len(seeds) >= top_n:
            break
        add(rec)
    seeds = seeds[:top_n]

    screened = []
    per = n_scenarios
    for i, rec in enumerate(seeds):
        full = dict(res.get("_base_design") or {})
        full.update(rec["design"])
        st = unc.stress_test(env, full, n_scenarios=per,
                             progress=None)
        rec["scenario_pass_fraction"] = st["pass_fraction"]
        rec["scenario_passed"] = st["passed"]
        rec["scenario_n"] = st["n_scenarios"]
        rec["scenario_headline"] = st["headline"]
        rec["worst_scenario"] = st["worst"]
        screened.append(rec)
        if progress:
            progress((i + 1) * per, len(seeds) * per)

    screened.sort(key=lambda r: (-r["scenario_pass_fraction"],
                                 r["cost_inr"]))
    res["screened"] = screened
    res["robust_pick"] = screened[0] if screened else None
    if screened:
        res["picks"]["most_robust"] = screened[0]
    res["scenario_screening"] = {
        "top_n": len(seeds),
        "scenarios_each": per,
        "note": ("Each candidate was run through the declared uncertain ranges. "
                 "The pass fraction is a scenario pass rate, not a probability of "
                 "real-world survival."),
    }
    return res


def compare(records, key, reverse=False, limit=6):
    """Small helper used by the UI: the top few records on one metric."""
    return sorted(records, key=lambda r: r[key], reverse=reverse)[:limit]
