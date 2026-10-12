"""
sweep.py -- canonical design sweep against LIVE forecast data.
==============================================================
Runs a fixed set of designs through the same engine the app uses, so the
numbers quoted in the deck, the report and the UI all come from one place.

    python3 sweep.py                 # the 7 headline designs
    python3 sweep.py --grid          # full design grid, incl. overheat check

Every run prints the data provenance (LIVE / CACHED / ISA fallback) so that a
number can never be quoted without knowing where its weather came from.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import mission as ms          # noqa: E402
import data_sources                        # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
SITE = (13.0067, 80.2570)                  # Rajalakshmi Engineering College
DATE = "2026-10-12"
LAUNCH_HOUR = 18

BASE = dict(box_area_m2=0.0864, payload_load_w=3.0, panel_m2=0.0,
            k_ins=0.030, heater_max_w=5.0)

HEADLINE = [
    ("6c 10mm sp-10 5W", dict(cells=6,  insulation_mm=10, heater_setpoint_c=-10)),
    ("6c 25mm sp-10 5W", dict(cells=6,  insulation_mm=25, heater_setpoint_c=-10)),
    ("6c 50mm sp-10 5W", dict(cells=6,  insulation_mm=50, heater_setpoint_c=-10)),
    ("6c 75mm sp-10 5W", dict(cells=6,  insulation_mm=75, heater_setpoint_c=-10)),
    ("8c 25mm sp-10 10W", dict(cells=8,  insulation_mm=25, heater_setpoint_c=-10,
                               heater_max_w=10.0)),
    ("8c 50mm sp0  10W", dict(cells=8,  insulation_mm=50, heater_setpoint_c=0,
                               heater_max_w=10.0)),
    ("10c 25mm sp-10 5W", dict(cells=10, insulation_mm=25, heater_setpoint_c=-10)),
]


def provenance(env):
    """Report where every input actually came from. Never guess."""
    out = {}
    for key, meta in (env.get("sources") or {}).items():
        out[key] = meta.get("source", "UNKNOWN")
    return out


def run(env, name, overrides):
    d = dict(BASE)
    d.update(overrides)
    r = ms.simulate(env, d)
    return r


def fmt(r):
    ex = r.get("failure_explanation") or {}
    return "{:<19} {:<5} {:<24} T-{:>19} minT={:>7.1f} htr={:>6.2f}Wh ua={:>5.3f}".format(
        r["label"] if "label" in r else "",
        r["verdict"],
        r["failure_reason"] or "-",
        (r["failure_time"] or "-"),
        r["min_box_c"],
        r["heater_energy_wh"],
        r["effective_ua_w_per_k"],
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--date", default=DATE)
    args = ap.parse_args()

    print(f"Fetching forecast for {args.date} at {SITE[0]:.4f}N {SITE[1]:.4f}E ...")
    env = data_sources.fetch_environment(SITE[0], SITE[1], args.date)

    # The mission engine needs an explicit launch instant. The app sets this in
    # server.py; the sweep sets it here so results are comparable.
    env["launch_local"] = datetime.strptime(
        f"{args.date} {LAUNCH_HOUR:02d}:00", "%Y-%m-%d %H:%M").replace(tzinfo=IST)

    print(f"  provenance : {provenance(env)}")
    print(f"  hours      : {len(env['hours'])}")
    if env["profiles"]:
        lv = env["profiles"][0]
        print(f"  levels     : {len(lv)}  top={lv[-1]['alt_km']:.2f} km "
              f"({lv[-1]['temp_c']:.1f} C)")
    print(f"  launch     : {env['launch_local']:%Y-%m-%d %H:%M %Z}")
    print(f"  night      : {env['night_hours']:.1f} h")
    print()

    cases = HEADLINE
    if args.grid:
        cases = []
        for cells in (4, 6, 8, 10, 12):
            for ins in (10, 25, 50, 75):
                for sp in (-10, 0):
                    cases.append((f"{cells}c {ins}mm sp{sp}",
                                  dict(cells=cells, insulation_mm=ins,
                                       heater_setpoint_c=sp, heater_max_w=10.0)))

    hdr = "{:<19} {:<5} {:<24} {:<21} {:>7} {:>10} {:>7}".format(
        "design", "v", "failure", "when", "minT", "htrWh", "UA")
    print(hdr)
    print("-" * len(hdr))

    fails = {}
    over = 0
    for name, ov in cases:
        r = run(env, name, ov)
        ex = r.get("failure_explanation") or {}
        print("{:<19} {:<5} {:<24} {:<21} {:>7.1f} {:>10.2f} {:>7.3f}".format(
            name, r["verdict"], r["failure_reason"] or "-",
            (r["failure_time"] or "-"), r["min_box_c"],
            r["heater_energy_wh"], r["effective_ua_w_per_k"]))
        fails[r["failure_reason"] or "PASS"] = fails.get(r["failure_reason"] or "PASS", 0) + 1
        if r["failure_reason"] == ms.TEMP_ABOVE_OPERATING:
            over += 1

    print()
    print("summary:", ", ".join(f"{k}={v}" for k, v in sorted(fails.items())))
    if over:
        print(f"*** {over} designs failed by OVERHEATING -- insulation can trap "
              f"self-generated heat. This is a real design trade, not a bug. ***")


if __name__ == "__main__":
    main()
