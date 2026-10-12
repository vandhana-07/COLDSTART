"""
battle.py -- Design Battle mode.
=================================
Puts several contrasting design philosophies through the SAME environment and
the SAME engine, then states which one wins for a chosen objective and why the
others lose.

The four archetypes are deliberately drawn as real engineering instincts, not
strawmen:

  battery_heavy    "just add cells"           -- low insulation, large pack
  thermal_heavy    "just add insulation"      -- thick foam, small pack
  obvious_default  what you would build first -- small foam, small pack
  optimiser_pick   the search result
  custom           supplied by the caller

A winner is only meaningful relative to an objective, so the module always
reports the objective alongside the winner, and always lists the failure
mechanism of the losers. It never declares an overall champion.
"""

from . import mission as ms
from . import uncertainty as unc

ARCHETYPES = {
    "battery_heavy": {
        "label": "Battery-heavy",
        "thesis": "Carry more energy and let the cold take the edges off it.",
        "design": {"cells": 12, "insulation_mm": 10, "heater_setpoint_c": None,
                   "heater_max_w": 5.0, "panel_m2": 0.0},
    },
    "thermal_heavy": {
        "label": "Thermally optimised",
        "thesis": "Stop the heat escaping and the battery stops being the problem.",
        "design": {"cells": 6, "insulation_mm": 75, "heater_setpoint_c": None,
                   "heater_max_w": 5.0, "panel_m2": 0.0},
    },
    "obvious_default": {
        "label": "The obvious first build",
        "thesis": "Small pack, thin foam, keep the heater on. What most teams build.",
        "design": {"cells": 6, "insulation_mm": 10, "heater_setpoint_c": -10,
                   "heater_max_w": 5.0, "panel_m2": 0.0},
    },
}

OBJECTIVE_LABEL = {
    "lowest_cost": "Lowest cost",
    "lowest_mass": "Lowest mass",
    "highest_margin": "Highest energy margin",
    "best_balance": "Best balance of cost, mass and margin",
}


def _measure(env, design, full_design, n_scenarios=32):
    sim = ms.simulate(env, full_design)
    stress = unc.stress_test(env, full_design, n_scenarios=n_scenarios)
    sens = unc.sensitivity_ranking(env, full_design)
    return {
        "sim": sim,
        "stress": stress,
        "sensitivity": sens,
        "survives_any_single_input_failure": not any(
            r["single_input_fails"] for r in sens["ranking"]),
    }


def battle(env, base_design, optimiser_result=None, custom=None,
           objective="best_balance", n_scenarios=32, progress=None):
    """Run every archetype under identical conditions and rank for one objective."""
    entries = []

    specs = []
    for key, spec in ARCHETYPES.items():
        specs.append((key, spec["label"], spec["thesis"], spec["design"]))

    if optimiser_result and optimiser_result.get("best"):
        b = optimiser_result["best"]
        specs.append(("optimiser_pick", "Optimiser pick",
                      "Chosen by searching the declared design space.",
                      b["design"]))

    if custom:
        specs.append(("custom", "Custom", "Supplied by the operator.", custom))

    for i, (key, label, thesis, overrides) in enumerate(specs, start=1):
        full = dict(base_design)
        full.update(overrides)
        measured = _measure(env, full, full, n_scenarios=n_scenarios)
        from . import cost as cst
        mc = cst.breakdown(full)
        entries.append({
            "key": key,
            "label": label,
            "thesis": thesis,
            "design": {k: full.get(k) for k in ("cells", "insulation_mm",
                                                "heater_setpoint_c", "heater_max_w",
                                                "panel_m2")},
            "cost_inr": mc["cost_inr"],
            "mass_kg": mc["mass_kg"],
            "verdict": measured["sim"]["verdict"],
            "failure_reason": measured["sim"]["failure_reason"],
            "failure_time": measured["sim"]["failure_time"],
            "survival_hours": measured["sim"]["survival_hours"],
            "min_box_c": measured["sim"]["min_box_c"],
            "margin_ratio": measured["sim"]["energy_margin_ratio"],
            "stress_pass": measured["stress"]["passed"],
            "stress_total": measured["stress"]["n_scenarios"],
            "survives_any_single_input_failure":
                measured["survives_any_single_input_failure"],
            "failure_mechanism": (measured["sim"]["failure_explanation"] or {}).get("headline"),
            "failure_chronology": (measured["sim"]["failure_explanation"] or {}).get("chronology", []),
            "contributing_factors": (measured["sim"]["failure_explanation"] or {}).get("contributing_factors", []),
            "suggested_changes": (measured["sim"]["failure_explanation"] or {}).get("suggested_changes", []),
            "_sim": measured["sim"],
            "_stress": measured["stress"],
        })
        if progress:
            progress(i, len(specs))

    winner_key = _choose_winner(entries, objective)
    ranked = _rank(entries, objective)

    return {
        "objective": objective,
        "objective_label": OBJECTIVE_LABEL[objective],
        "conditions": {
            "note": "Every design was run through the identical forecast, identical "
                    "mission profile and identical engine. The only difference is "
                    "the design.",
            "night_hours": env.get("night_hours"),
            "launch": env["launch_local"].strftime("%Y-%m-%d %H:%M"),
        },
        "entries": entries,
        "winner": winner_key,
        "ranked_keys": ranked,
        "verdict": _narrate(entries, winner_key, objective),
    }


def _choose_winner(entries, objective):
    feasible = [e for e in entries if e["verdict"] == "PASS"]
    pool = feasible or entries

    if objective == "lowest_cost":
        return min(pool, key=lambda e: e["cost_inr"])["key"]
    if objective == "lowest_mass":
        return min(pool, key=lambda e: e["mass_kg"])["key"]
    if objective == "highest_margin":
        return max(pool, key=lambda e: e["margin_ratio"] or 0.0)["key"]
    if objective == "best_balance":
        # cost and mass low is good; margin, scenario pass rate and single-input
        # survival high is good. Ranks, not invented exchange rates.
        def score(e):
            return (0 if e["verdict"] == "PASS" else 1,
                    -(e["stress_pass"] / max(1, e["stress_total"])),
                    0 if e["survives_any_single_input_failure"] else 1,
                    e["cost_inr"])
        return min(pool, key=score)["key"]
    raise ValueError(f"unknown objective {objective!r}")


def _rank(entries, objective):
    order = {
        "lowest_cost": lambda e: (e["verdict"] != "PASS", e["cost_inr"]),
        "lowest_mass": lambda e: (e["verdict"] != "PASS", e["mass_kg"]),
        "highest_margin": lambda e: (e["verdict"] != "PASS", -(e["margin_ratio"] or 0.0)),
        "best_balance": lambda e: (e["verdict"] != "PASS",
                                   -(e["stress_pass"] / max(1, e["stress_total"])),
                                   e["cost_inr"]),
    }[objective]
    return [e["key"] for e in sorted(entries, key=order)]


def _narrate(entries, winner_key, objective):
    """Plain-language why-the-winner-won. Generated so it cannot drift."""
    winner = next(e for e in entries if e["key"] == winner_key)
    losers = [e for e in entries if e["key"] != winner_key]
    failed = [e for e in losers if e["verdict"] != "PASS"]

    lines = [
        f"Judged on {OBJECTIVE_LABEL[objective].lower()}, "
        f"{winner['label']} wins ({winner['design']['cells']} cells, "
        f"{winner['design']['insulation_mm']} mm insulation, Rs {winner['cost_inr']:.0f})."
    ]

    if winner["verdict"] == "PASS":
        lines.append(
            f"It survived the full night with an energy margin of "
            f"{winner['margin_ratio']:.2f}x the reserve floor and "
            f"{winner['stress_pass']} of {winner['stress_total']} stressed scenarios.")
        if winner["survives_any_single_input_failure"]:
            lines.append(
                "No single stressed input, pushed to its worst assumed value, was "
                "enough to fail it on its own.")
        else:
            lines.append(
                "Some single stressed inputs are enough to fail it, so its margin "
                "is thinner than the headline number suggests.")

    for e in failed:
        mech = e["failure_mechanism"] or e["failure_reason"]
        lines.append(
            f"{e['label']} lost: it failed at {e['failure_time']} "
            f"({e['failure_reason']}). {mech}")

    if not failed:
        cheapest = min(losers, key=lambda e: e["cost_inr"])
        lines.append(
            f"No design failed outright, so the decision comes down to cost and "
            f"robustness: {cheapest['label']} is cheaper at Rs {cheapest['cost_inr']:.0f} "
            f"but passed {cheapest['stress_pass']} of {cheapest['stress_total']} "
            f"stressed scenarios against the winner's "
            f"{winner['stress_pass']} of {winner['stress_total']}.")

    return " ".join(lines)
