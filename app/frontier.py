"""
frontier.py -- cost/fragility frontier on the VERIFIED engine.
==============================================================
Produces the numbers the deck needs, and nothing else. Every figure quoted on a
slide must come from a run of this script, so a claim can always be traced back
to a reproducible computation.

    cd app && python3 frontier.py

WHAT IT MEASURES
----------------
For each candidate design that passes under nominal assumptions, find how far the
insulation constant can be WRONG before that design flips to FAIL. The multiplier
is applied to k_ins: 1.15x means "the foam is 15% worse than we assumed", which
is the single largest modelled uncertainty in the thermal path.

Output per design:
    flip_multiplier    largest k_ins multiplier it survives
    tolerance_pct      (flip_multiplier - 1) * 100, i.e. how much model error it
                       tolerates before the verdict changes

This is the honest version of "how robust is it": not a probability, but a stated
error budget.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_sources                                        # noqa: E402
from engine import cost as cst                             # noqa: E402
from engine import mission as ms                           # noqa: E402
from engine import optimizer as opt                        # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
AREA = 0.0864
BASE = dict(box_area_m2=AREA, payload_load_w=3.0, k_ins=0.030)

# Sweep of k_ins multipliers. 1.0 = the assumed value. Higher = worse insulation.
MULTIPLIERS = [0.50, 0.75, 1.00, 1.10, 1.15, 1.25, 1.50, 2.00, 2.50, 3.00]


def build_env():
    env = data_sources.fetch_environment(13.0067, 80.2570, "2026-10-12")
    env["launch_local"] = datetime(2026, 10, 12, 18, 0, tzinfo=IST)
    return env


def flip_point(env, design, multipliers=MULTIPLIERS):
    """Largest multiplier at which the design still survives."""
    surviving = []
    rows = []
    for m in multipliers:
        d = dict(design)
        d["k_ins"] = BASE["k_ins"] * m
        r = ms.simulate(env, d)
        rows.append({"multiplier": m, "verdict": r["verdict"],
                     "failure_reason": r["failure_reason"],
                     "failure_time": r["failure_time"],
                     "survival_hours": r["survival_hours"],
                     "min_box_c": r["min_box_c"],
                     "energy_margin_ratio": r["energy_margin_ratio"]})
        if r["verdict"] == "PASS":
            surviving.append(m)
    return (max(surviving) if surviving else None), rows


def main():
    env = build_env()
    prov = env.get("sources", {}).get("upper_air", {}).get("source", "UNKNOWN")
    print(f"forecast provenance: {prov}")
    print("\nRunning the design search (this takes ~20 s) ...")
    res = opt.optimise(env, BASE, objective="best_balance")
    print(f"  {res['combinations_evaluated']} candidates, "
          f"{res['feasible_count']} feasible\n")

    # Candidate set: the cheapest feasible designs, plus one from each objective,
    # so the comparison covers the trade-off rather than a single pick.
    picks = {k: v for k, v in (res.get("picks") or {}).items() if v}
    candidates = {}
    for name, rec in picks.items():
        candidates[name] = rec["design"]
    for rec in sorted(res["top_passing"], key=lambda r: r["cost_inr"])[:5]:
        key = f"cheap_{rec['design']['cells']}c_{rec['design']['insulation_mm']}mm"
        candidates.setdefault(key, rec["design"])

    print("=" * 104)
    print(f"{'design':<24} {'cells':>5} {'ins':>4} {'setp':>6} {'Rs':>6} {'kg':>6} "
          f"{'margin':>7} {'flip x':>7} {'tol %':>6}  verdict")
    print("=" * 104)

    out = []
    for name, design in candidates.items():
        d = dict(BASE)
        d.update(design)
        nominal = ms.simulate(env, d)
        mc = cst.breakdown(d)
        flip, rows = flip_point(env, d)
        tol = None if flip is None else round(100.0 * (flip - 1.0), 1)
        out.append({"name": name, "design": d, "cost": mc["cost_inr"],
                    "mass": mc["mass_kg"], "verdict": nominal["verdict"],
                    "margin": nominal["energy_margin_ratio"],
                    "flip_multiplier": flip, "tolerance_pct": tol, "sweep": rows})
        print(f"{name:<24} {d['cells']:>5} {d['insulation_mm']:>4} "
              f"{str(d['heater_setpoint_c']):>6} {mc['cost_inr']:>6.0f} "
              f"{mc['mass_kg']:>6.3f} {str(nominal['energy_margin_ratio']):>7} "
              f"{str(flip):>7} {str(tol):>6}  {nominal['verdict']}"
              f"{' ' + nominal['failure_reason'] if nominal['failure_reason'] else ''}")

    # ---- the headline: cheapest that passes vs the most tolerant -------------
    passing = [o for o in out if o["verdict"] == "PASS" and o["tolerance_pct"] is not None]
    if passing:
        cheapest = min(passing, key=lambda o: o["cost"])
        toughest = max(passing, key=lambda o: (o["tolerance_pct"], -o["cost"]))
        print("\n" + "=" * 104)
        print(f"CHEAPEST PASSING : {cheapest['name']}  Rs {cheapest['cost']:.0f}, "
              f"{cheapest['mass']:.3f} kg, margin {cheapest['margin']}, "
              f"tolerates {cheapest['tolerance_pct']}% insulation error")
        print(f"MOST TOLERANT    : {toughest['name']}  Rs {toughest['cost']:.0f}, "
              f"{toughest['mass']:.3f} kg, margin {toughest['margin']}, "
              f"tolerates {toughest['tolerance_pct']}% insulation error")
        gap = toughest["cost"] - cheapest["cost"]
        print(f"Cost of choosing tolerance: Rs {gap:.0f} "
              f"({100.0 * gap / max(cheapest['cost'], 1):.0f}% more)")

    # ---- designs that look attractive but are NOT robust --------------------
    print("\n" + "-" * 104)
    print("DESIGNS THAT FAIL THE NOMINAL CASE (context for the slides):")
    for o in out:
        if o["verdict"] != "PASS":
            print(f"  {o['name']:<24} Rs {o['cost']:>6.0f}  "
                  f"{o['verdict']} {o['failure_reason']}")

    return out


if __name__ == "__main__":
    main()
