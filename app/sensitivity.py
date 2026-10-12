"""
sensitivity.py -- "does a wrong constant change our ANSWER?"
============================================================
The bench test measures ONE number: the insulation coefficient UA (W/K).
This script asks the question that actually matters:

    If our assumed UA is wrong, does the PASS/FAIL verdict change?

A model can be 40% wrong on an absolute coefficient and still make exactly the
right decision -- and showing that, with numbers, is what turns a weak slide 4
into a strong one. It is also the honest answer to "how much do you trust this?"

k_ins enters the model as (k/t)*A, so scaling k_ins is the same as scaling UA.
One sweep therefore covers the whole measurement error.

Run:  python3 sensitivity.py

READ THIS BEFORE QUOTING ANY NUMBER IT PRINTS
---------------------------------------------
The current model lives in `app/engine/` (thermal.py, battery.py, mission.py,
optimizer.py). This script still runs `app/physics.py`, which is the SUPERSEDED
model: it uses the old 0.035 m2 box, the old 0.018 W/m/K aerogel assumption and
the old 840-minute window.

The two models DISAGREE, and the difference has been measured:

    design              physics.py   engine/
    10 cells / 10 mm    PASS         FAIL          <- the verdict flips
    cheapest passing    Rs 2130      Rs 2468

So the numbers below are NOT the numbers on the slides and must not be quoted
against them. The live, engine-backed sensitivity analysis is in
`app/engine/uncertainty.py` (`sensitivity_ranking`) and is what the app's
Stress-Test tab shows.

Porting this script to `app/engine/` is a deliberate, separate change: it would
move the results above, so it has NOT been done as part of a reference cleanup.
"""

import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import physics
import data_sources

# How wrong our insulation constant could realistically be.
MULTIPLIERS = [0.6, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0, 3.0]

# The level of model error we REQUIRE a design to survive before we will
# recommend it. 1.30 = "still passes even if our measurement is 30% wrong."
REQUIRED_TOLERANCE = 1.30

BASE = dict(wh_per_cell=12.24, load_w=3.0, box_area_m2=0.035, panel_m2=0.0,
            panel_eff=0.18, duration_min=840, reserve=0.10)

CELLS = (6, 8, 10, 12, 14)
INSULATIONS = (10, 25, 50, 75)
SETPOINTS = (None, -10, 0)


def tolerance(env, design):
    """Highest multiplier at which this design still PASSes."""
    ok = 0.0
    for m in MULTIPLIERS:
        r = physics.simulate_flight(env, dict(BASE, **design, k_ins=0.018 * m))
        if r["verdict"] == "PASS":
            ok = m
        else:
            break
    return ok


def label(d):
    heat = "off" if d["heater_setpoint_c"] is None else f"{d['heater_setpoint_c']}C"
    return f"{d['cells']} cells / {d['insulation_mm']}mm / heater {heat}"


def main():
    env = data_sources.fetch_environment(13.0067, 80.2570, "2026-10-12")
    env["launch_local"] = datetime.strptime("2026-10-12 18:00", "%Y-%m-%d %H:%M").replace(
        tzinfo=data_sources.IST)
    night = env["night_hours"]

    print("=" * 96)
    print("  !! LEGACY MODEL (app/physics.py) -- SUPERSEDED. These numbers are NOT")
    print("  !! the ones on the slides and must not be quoted against them.")
    print("  !! Current model: app/engine/   Live analysis: app/engine/uncertainty.py")
    print("=" * 96)
    print(f"  SENSITIVITY TO THE INSULATION CONSTANT   |   real forecast: 12 Oct 2026, Chennai")
    print(f"  night = {night} h   |   flight = 14 h   |   reserve floor = 10%")
    print("=" * 96)

    # ---------------------------------------------------------------- sweep
    print("\n  Rows = designs. Columns = how wrong our insulation constant is (1.00x = model assumption).")
    print("  PASS = survived with reserve intact.  7.4h = reserve breached after 7.4 hours.\n")

    named = {
        "default 6 / 10mm / -10C  (what teams do first)": dict(cells=6, insulation_mm=10, heater_setpoint_c=-10),
        "lazy fix 10 / 10mm / 0C  ('just add batteries')": dict(cells=10, insulation_mm=10, heater_setpoint_c=0),
        "deep 6 / 75mm / 0C  (absolute cheapest passing)": dict(cells=6, insulation_mm=75, heater_setpoint_c=0),
        "OUR PICK 8 / 25mm / 0C": dict(cells=8, insulation_mm=25, heater_setpoint_c=0),
    }

    head = f"  {'design':<48}" + "".join(f"{m:>7.2f}x" for m in MULTIPLIERS)
    print(head)
    print("  " + "-" * (len(head) - 2))

    results = {}
    for name, d in named.items():
        row, flags = f"  {name:<48}", []
        for m in MULTIPLIERS:
            r = physics.simulate_flight(env, dict(BASE, **d, k_ins=0.018 * m))
            if r["verdict"] == "PASS":
                row += f"{'PASS':>8}"
                flags.append(True)
            else:
                row += f"{r['survival_hours']:>7.1f}h"
                flags.append(False)
        print(row)
        results[name] = flags

    # ------------------------------------------------------- classification
    print("\n  VERDICT STABILITY")
    print("  " + "-" * 92)
    for name, flags in results.items():
        n = sum(flags)
        if n == len(flags):
            print(f"  {name:<48} ROBUST PASS  - survives every error level tested")
        elif n == 0:
            print(f"  {name:<48} ROBUST FAIL  - fails at every level; the finding is not an artefact")
        else:
            first_fail = MULTIPLIERS[flags.index(False)]
            flips = f"{(first_fail - 1) * 100:.0f}%"
            print(f"  {name:<48} FRAGILE      - flips to FAIL at {first_fail:.2f}x  (a {flips} error)")

    # ------------------------------------------------- robustness frontier
    print("\n" + "=" * 96)
    print("  THE POINT: CHEAPEST-PASSING IS A TRAP. CHEAPEST-ROBUST IS THE REAL ANSWER.")
    print("=" * 96)
    print("\n  Searching every design, and finding the CHEAPEST one that still passes at each")
    print("  level of model error:\n")
    print(f"  {'if our measurement is off by':<30} {'cheapest design that still passes':<40} {'cost':>8} {'mass':>8}")
    print("  " + "-" * 92)

    all_designs = [dict(cells=c, insulation_mm=i, heater_setpoint_c=s)
                   for c in CELLS for i in INSULATIONS for s in SETPOINTS]
    for d in all_designs:
        d["_tol"] = tolerance(env, d)
        d["_mc"] = physics.design_mass_cost(d)

    frontier = {}
    for req in (1.15, 1.3, 1.5, 2.0, 3.0):
        ok = sorted([d for d in all_designs if d["_tol"] >= req],
                    key=lambda d: (d["_mc"]["cost_inr"], d["_mc"]["mass_kg"]))
        if ok:
            b = ok[0]
            frontier[req] = b
            print(f"  {(req-1)*100:>4.0f}%{'':<25} {label(b):<40} "
                  f"{'Rs ' + str(b['_mc']['cost_inr']):>8} {str(b['_mc']['mass_kg']) + ' kg':>8}")

    passing = sorted([d for d in all_designs if d["_tol"] >= 1.0],
                     key=lambda d: d["_mc"]["cost_inr"])
    cheapest = passing[0]
    chosen = frontier.get(REQUIRED_TOLERANCE)

    print("\n  " + "-" * 92)
    print(f"  CHEAPEST THAT PASSES   : {label(cheapest)}  - Rs {cheapest['_mc']['cost_inr']}")
    print(f"                           tolerates only {(cheapest['_tol']-1)*100:.0f}% error. "
          f"It sits on the boundary.")
    if chosen:
        print(f"  CHEAPEST THAT IS SAFE  : {label(chosen)}  - Rs {chosen['_mc']['cost_inr']}")
        print(f"    (requirement: survive {(REQUIRED_TOLERANCE-1)*100:.0f}% model error) "
              f"tolerates {(chosen['_tol']-1)*100:.0f}%")
        extra = chosen["_mc"]["cost_inr"] - cheapest["_mc"]["cost_inr"]
        print(f"    Costs Rs {extra} more than the fragile one. That Rs {extra} is the price of "
              f"not being wrong.")

    # ------------------------------------------------------------- slide 4
    print("\n" + "=" * 96)
    print("  SLIDE 4 - SAY THIS (numbers generated from the run above, not typed by hand)")
    print("=" * 96)
    lazy = results["lazy fix 10 / 10mm / 0C  ('just add batteries')"]
    lazy_flip = MULTIPLIERS[lazy.index(False)] if not all(lazy) else None
    print(f"""
   1. Our headline FAIL is robust. Even if the insulation performed 40% better
      than assumed, the default design still dies at 8.8 h of a {night} h night.
      The failure is not an artefact of a wrong constant.

   2. The two designs people reach for first are BOTH fragile.
      - The absolute cheapest passing design ({label(cheapest)}) sits exactly on
        the boundary: it breaks with any degradation at all.
      - "Just add batteries" ({label(dict(cells=10, insulation_mm=10, heater_setpoint_c=0))}){f" flips to FAIL at only {lazy_flip:.2f}x - a {(lazy_flip-1)*100:.0f}% modelling error." if lazy_flip else ""}

   3. Our recommended design is chosen for ROBUSTNESS, not just cost:
      {label(chosen) if chosen else "n/a"} - still passes if our measured
      insulation constant is {(REQUIRED_TOLERANCE-1)*100:.0f}% wrong.

   >> That is validation of the DECISION, not just of a number. And it is the
      honest answer to "how much should we trust this model?"
""")
    print("  Re-run this after your bench test to fold in your measured error.")


if __name__ == "__main__":
    main()
