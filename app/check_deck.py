"""
check_deck.py -- assert that every number printed on the slides is reproducible.

    cd app && python3 check_deck.py

Exit code 0 = the deck and the engine agree. Any mismatch is printed with both
values so the slide can be corrected deliberately rather than by hand-editing.

This exists because build_ppt.py does NOT import the engine: its numbers are
typed into a FILL dict. Without a check, the deck silently drifts away from the
code the moment the physics changes - which is exactly what happened once.
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_sources
from engine import cost as cst, mission as ms

IST = timezone(timedelta(hours=5, minutes=30))
AREA, K = 0.0864, 0.030
BASE = dict(box_area_m2=AREA, payload_load_w=3.0)

DECK = {
    "default":  dict(cells=6,  insulation_mm=10, heater_setpoint_c=-10, heater_max_w=5.0),
    "lazy":     dict(cells=10, insulation_mm=10, heater_setpoint_c=0,   heater_max_w=5.0),
    "cheap":    dict(cells=6,  insulation_mm=75, heater_setpoint_c=None, heater_max_w=5.0),
    "robust":   dict(cells=12, insulation_mm=75, heater_setpoint_c=None, heater_max_w=5.0,
                     panel_m2=0.06),
}


def load_fill():
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "ppt", "build_ppt.py")).read()
    block = re.search(r"FILL = \{(.*?)\n\}", src, re.S).group(1)
    out = {}
    for m in re.finditer(r'^\s*"([a-z_]+)":\s*(.+?),\s*(?:#.*)?$', block, re.M):
        raw = m.group(2).strip()
        try:
            out[m.group(1)] = eval(raw, {"__builtins__": {}}, {})
        except Exception:
            out[m.group(1)] = raw.strip('"')
    return out


SNAPSHOT_MODE = "--snapshot" in sys.argv


def main():
    env = data_sources.fetch_environment(13.0067, 80.2570, "2026-10-12",
                                         snapshot=SNAPSHOT_MODE)
    env["launch_local"] = datetime(2026, 10, 12, 18, 0, tzinfo=IST)
    fill = load_fill()

    r = {}
    for name, ov in DECK.items():
        d = dict(BASE); d.update(ov)
        sim = ms.simulate(env, d)
        r[name] = {"sim": sim, "cost": cst.breakdown(d)["cost_inr"],
                   "mass": cst.breakdown(d)["mass_kg"], "k": K, "design": d}

    def verdict_at(design, m):
        dd = dict(design); dd["k_ins"] = K * m
        return ms.simulate(env, dd)["verdict"]

    def pass_window(design, lo=0.05, hi=4.00, step=0.05):
        """Map the whole insulation-error axis and return the contiguous range
        of multipliers at which the design still passes.

        A design can fail at BOTH ends. At low k the box is nearly adiabatic and
        the payload's own 3 W self-heats it past its limit; at high k it loses
        more heat than the battery can replace. A single 'flip point' assumes
        one monotone edge and would silently report the wrong side, so the whole
        axis is scanned instead.
        """
        m, passing = round(lo, 6), []
        vals = []
        while m <= hi + 1e-9:
            vals.append((m, verdict_at(design, m) == "PASS"))
            m = round(m + step, 6)
        if not any(p for _, p in vals):
            return None
        first = next(i for i, (_, p) in enumerate(vals) if p)
        last = len(vals) - 1 - next(i for i, (_, p) in enumerate(reversed(vals)) if p)
        return {"low": vals[first][0], "high": vals[last][0],
                "all": [v for v, p in vals if p],
                "holes": any(not p for _, p in vals[first:last + 1])}

    checks = []

    def eq(label, deck_val, engine_val, tol=0.01):
        try:
            ok = abs(float(str(deck_val).rstrip("%x")) - float(engine_val)) <= tol
        except Exception:
            ok = str(deck_val) == str(engine_val)
        checks.append((label, deck_val, engine_val, ok))

    # default design
    eq("fail_time", fill["fail_time"], r["default"]["sim"]["failure_time"])
    eq("fail_hours", fill["fail_hours"], r["default"]["sim"]["survival_hours"], tol=0.15)
    eq("default_cost", fill["default_cost"], r["default"]["cost"], tol=1.0)

    # recommendation
    eq("rec_cost", fill["rec_cost"], r["cheap"]["cost"], tol=1.0)
    eq("rec_margin", fill["rec_margin"], r["cheap"]["sim"]["energy_margin_ratio"], tol=0.02)
    eq("rec_mass", fill["rec_mass"], r["cheap"]["mass"], tol=0.01)

    # lazy fix
    eq("lazy_cost", fill["lazy_cost"], r["lazy"]["cost"], tol=1.0)
    eq("lazy_fail_time", fill["lazy_fail_time"], r["lazy"]["sim"]["failure_time"])

    # robust alternative
    eq("robust_cost", fill["robust_cost"], r["robust"]["cost"], tol=1.0)
    eq("robust_margin", fill["robust_margin"],
       r["robust"]["sim"]["energy_margin_ratio"], tol=0.02)

    windows = {}
    print("Insulation-error window for each design (k x multiplier, 0.05 .. 4.0):")
    for name in DECK:
        w = pass_window(r[name]["design"])
        windows[name] = w
        if w is None:
            print(f"  {name:<9} never passes anywhere on the axis")
        else:
            print(f"  {name:<9} passes {w['low']:.2f}x .. {w['high']:.2f}x"
                  + ("   (with gaps - not a single band)" if w["holes"] else ""))
    print()

    # tolerance = how much WORSE than assumed the foam can be
    for key, name in (("rec_tolerance", "cheap"),):
        w = windows[name]
        if w is None:
            checks.append((key, fill[key], "never passes", False))
        else:
            eq(key, str(fill[key]).rstrip("%"), round(100 * (w["high"] - 1), 0), tol=2.0)

    # the two failing designs: how much BETTER the foam would have to be
    for key, name in (("default_deficit", "default"), ("lazy_deficit", "lazy")):
        w = windows[name]
        if w is None:
            checks.append((key, fill[key], "never passes", False))
        else:
            eq(key, str(fill[key]).rstrip("x"), round(1 / w["high"], 1), tol=0.1)

    # the scenario counts are claims too: they must come from the stress engine
    try:
        from engine import uncertainty as unc
        print("Stressed-scenario screening (declared uncertainty ranges):")
        for key, name in (("rec_scen", "cheap"), ("robust_scen", "robust")):
            full = dict(BASE); full.update(DECK[name])
            st = unc.stress_test(env, full, n_scenarios=12)
            got = f"{st['passed']} of {st['n_scenarios']}"
            claimed = str(fill[key]).replace(" ", " ")
            print(f"  {key:<12} deck {claimed!r:>12}   engine {got!r}")
            checks.append((key, claimed, got, claimed == got))
        print()
    except Exception as exc:                       # never hide a failed check
        checks.append(("scenario_screening", "ran", f"error: {exc}", False))

    width = max(len(c[0]) for c in checks)
    print(f"{'claim':<{width}}  {'deck':>10}  {'engine':>10}  result")
    print("-" * (width + 36))
    bad = 0
    for label, dv, ev, ok in checks:
        print(f"{label:<{width}}  {str(dv):>10}  {str(ev):>10}  {'OK' if ok else '*** MISMATCH ***'}")
        bad += 0 if ok else 1
    print()
    if bad:
        print(f"{bad} mismatch(es). Do NOT present the deck until these are reconciled.")
        return 1
    src = env["sources"]["upper_air"]
    line = f"Forecast provenance: {src['source']}"
    if SNAPSHOT_MODE:
        line += f"  [SNAPSHOT {src.get('snapshot_utc')}]"
    print("All slide claims reproduce from the engine.", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
