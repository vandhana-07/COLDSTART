"""
verify.py -- reproducible verification run for COLDSTART.
==========================================================
Run:  python3 verify.py            (from app/)
Writes:  verify/RESULTS.md
         verify/results.json

Covers the eight tasks of the verification brief:
    Task 1  analytical thermal benchmarks
    Task 2  energy-conservation audit and state consistency
    Task 3  battery-model documentation and consistency
    Task 4  numerical convergence at 60/30/10/5 s
    Task 5  independent reference comparisons
    Task 6  parameter uncertainty and ranking robustness
    Task 7  (tests live in tests/test_verification.py)
    Task 8  (dashboard reads verify/results.json)

Every emitted result carries an evidence category A/B/C/D. Category E -- physical
experiment -- is never assigned because none was performed.
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_sources                                    # noqa: E402
from engine import battery as bat                      # noqa: E402
from engine import cost as cst                         # noqa: E402
from engine import mission as ms                       # noqa: E402
from engine import params as P                         # noqa: E402
from engine import thermal as th                       # noqa: E402
from engine import uncertainty as unc                  # noqa: E402
from engine import verification as V                   # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
SITE = (13.0067, 80.2570)
DATE = "2026-10-12"
LAUNCH_HOUR = 18
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "verify")

AREA = P.DEFAULT_BOX_AREA_M2

# The three designs Task 6 requires us to carry through the uncertainty ranges.
DESIGNS = {
    "baseline_default": dict(cells=6, insulation_mm=10, heater_setpoint_c=-10,
                             heater_max_w=5.0, box_area_m2=AREA, payload_load_w=3.0,
                             k_ins=0.030),
    "cheapest_passing": dict(cells=6, insulation_mm=75, heater_setpoint_c=None,
                             heater_max_w=5.0, box_area_m2=AREA, payload_load_w=3.0,
                             k_ins=0.030),
    "most_robust": dict(cells=9, insulation_mm=85, heater_setpoint_c=None,
                        heater_max_w=5.0, box_area_m2=AREA, payload_load_w=3.0,
                        k_ins=0.030, panel_m2=0.10),
}


def build_env(date=DATE, launch_hour=LAUNCH_HOUR):
    env = data_sources.fetch_environment(SITE[0], SITE[1], date)
    env["launch_local"] = datetime.strptime(
        f"{date} {launch_hour:02d}:00", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    return env


# ===========================================================================
# TASK 2 -- ENERGY CONSERVATION AUDIT
# ===========================================================================
TOL_WH = 1e-6


def audit_states(result):
    """Scan a trace for physically impossible states.

    Every check states the physical law it is testing. A check firing means the
    model produced something that cannot happen, which is a defect, not a
    tolerance issue.
    """
    d = result["design"]
    nominal = result["nominal_wh"]
    htr_max = d.get("heater_max_w", P.DEFAULT_HEATER_MAX_W)
    violations = []
    counts = {}

    def flag(kind, detail):
        counts[kind] = counts.get(kind, 0) + 1
        if counts[kind] <= 3:
            violations.append({"kind": kind, **detail})

    prev = None
    for row in result["timeline"]:
        # stored charge can never be negative or exceed nominal
        if row["charge_pct"] < -1e-9:
            flag("NEGATIVE_CHARGE", {"minute": row["minute"], "charge_pct": row["charge_pct"]})
        if row["charge_pct"] > 100.0 + 1e-6:
            flag("CHARGE_ABOVE_NOMINAL", {"minute": row["minute"], "charge_pct": row["charge_pct"]})

        # usable energy can never exceed what is stored
        if row["usable_pct"] > row["charge_pct"] + 1e-6:
            flag("USABLE_ABOVE_CHARGE", {"minute": row["minute"],
                                         "usable_pct": row["usable_pct"],
                                         "charge_pct": row["charge_pct"]})

        # capacity fraction is a curve output and must stay in [0, 1]
        if not (0.0 <= row["capacity_frac"] <= 1.0):
            flag("CAPACITY_OUT_OF_RANGE", {"minute": row["minute"],
                                           "capacity_frac": row["capacity_frac"]})

        # the heater cannot exceed its rating
        if row["heater_w"] > htr_max + 1e-6:
            flag("HEATER_ABOVE_RATING", {"minute": row["minute"],
                                         "heater_w": row["heater_w"], "rating": htr_max})

        # charging requires either PV or a positive net power; with no PV the
        # charge must never RISE. (This is the "impossible charging" check.)
        if prev is not None:
            if row["charge_pct"] > prev["charge_pct"] + 1e-6 and row["pv_w"] <= 1e-9:
                flag("CHARGE_ROSE_WITHOUT_PV",
                     {"minute": row["minute"], "from": prev["charge_pct"],
                      "to": row["charge_pct"], "pv_w": row["pv_w"]})

            # demand met with an empty pack is impossible
            if row["charge_pct"] <= 1e-9 and row["demand_w"] > 1e-9 and not row["power_limited"]:
                flag("LOAD_ON_EMPTY_PACK", {"minute": row["minute"],
                                            "demand_w": row["demand_w"]})

            # the pack cannot be asked to accept charge below the limit
            if row["pv_w"] > 1e-9 and row["box_c"] < d.get("charge_min_c", 0.0) - 1e-9:
                flag("PV_ACCEPTED_BELOW_CHARGE_LIMIT",
                     {"minute": row["minute"], "box_c": row["box_c"]})
        prev = row

    bal = result["energy_balance"]
    if abs(bal["electrical"]["residual_wh"]) > TOL_WH:
        flag("ELECTRICAL_BALANCE_RESIDUAL",
             {"residual_wh": bal["electrical"]["residual_wh"], "tolerance_wh": TOL_WH})

    return {
        "checks_run": 8,
        "points_scanned": len(result["timeline"]),
        "violations": violations,
        "violation_counts": counts,
        "clean": not counts,
    }


def task2_energy(env):
    rows = []
    for name, design in DESIGNS.items():
        r = ms.simulate(env, design)
        audit = audit_states(r)
        bal = r["energy_balance"]
        rows.append({
            "design": name,
            "verdict": r["verdict"],
            "failure_reason": r["failure_reason"],
            "nominal_wh": bal["electrical"]["nominal_wh"],
            "final_charge_wh": bal["electrical"]["final_charge_wh"],
            "storage_drop_wh": bal["electrical"]["storage_drop_wh"],
            "payload_delivered_wh": bal["electrical"]["payload_delivered_wh"],
            "heater_delivered_wh": bal["electrical"]["heater_delivered_wh"],
            "pv_into_cells_wh": bal["electrical"]["pv_into_cells_wh"],
            "pv_rejected_wh": bal["electrical"]["pv_rejected_wh"],
            "electrical_residual_wh": bal["electrical"]["residual_wh"],
            "electrical_tolerance_wh": TOL_WH,
            "electrical_pass": bal["electrical"]["pass"],
            "thermal_heat_in_wh": bal["thermal"]["heat_in_wh"],
            "thermal_heat_lost_wh": bal["thermal"]["heat_lost_wh"],
            "thermal_heat_gained_wh": bal["thermal"]["heat_gained_wh"],
            "thermal_stored_change_wh": bal["thermal"]["stored_change_wh"],
            "thermal_residual_wh": bal["thermal"]["residual_wh"],
            "thermal_residual_is_identity": True,
            "unmet_demand_wh": r["unmet_demand_wh"],
            "unmet_energy_wh": r["unmet_energy_wh"],
            "clamp_activations": r["clamp_activations"],
            "state_audit": audit,
        })
    return {
        "category": "C",
        "category_label": V.CATEGORIES["C"],
        "sign_convention": (
            "Positive = energy LEAVING the battery, or heat ENTERING the payload "
            "node. Electrical: storage_drop + pv_into_cells + unmet_energy - "
            "payload_delivered - heater_delivered = residual. Thermal: heat_in - "
            "heat_lost + heat_gained - stored_change = residual."
        ),
        "tolerance_wh": TOL_WH,
        "note_thermal": (
            "The thermal residual is identically zero for forward Euler: the "
            "scheme's own accumulation reproduces it term for term. It is a "
            "BOOKKEEPING CONSISTENCY identity, NOT an accuracy measure. Euler "
            "truncation error is quantified in Task 1 (analytical) and Task 4 "
            "(convergence)."
        ),
        "defects_found_and_fixed": [
            {
                "id": "A10",
                "defect": "Heater energy was booked at the COMMANDED power, not the "
                          "power the pack actually delivered. When the pack hit its "
                          "C-rate limit the reported heater consumption exceeded the "
                          "energy the battery supplied.",
                "cause": "heater_energy_wh accumulated heater_w (the thermostat "
                         "request) while the pack was only able to supply p_max.",
                "fix": "Delivered power is now split explicitly: payload first, "
                       "heater from the remainder; all bookkeeping uses delivered "
                       "values.",
                "regression_test": "test_heater_energy_never_exceeds_delivered",
            },
            {
                "id": "A11",
                "defect": "Payload self-heating was computed from the commanded load "
                          "even when the pack could not supply it, creating thermal "
                          "energy from nothing.",
                "cause": "payload_heat_w was computed once, outside the loop, from "
                         "the design value.",
                "fix": "payload_heat_w is now derived each step from "
                       "delivered_payload_w.",
                "regression_test": "test_self_heating_uses_delivered_power",
            },
            {
                "id": "A12",
                "defect": "Reported heat loss clamped negative flow to zero "
                          "(max(0, q)), silently discarding every heat-GAIN interval "
                          "and reconstructing the total from 1-minute samples "
                          "instead of the integration itself.",
                "cause": "post-hoc reconstruction in _heat_lost_wh.",
                "fix": "heat flow is now accumulated in the loop from the same q "
                       "that drove the step, split into heat_lost and heat_gained.",
                "regression_test": "test_heat_gain_is_recorded",
            },
        ],
        "rows": rows,
    }


# ===========================================================================
# TASK 3 -- BATTERY MODEL
# ===========================================================================
def task3_battery():
    curve = P.CAPACITY_VS_TEMP
    checks = []

    nominal = bat.nominal_wh(8)
    checks.append({"check": "nominal energy from cell count",
                   "expected_wh": round(8 * P.CELL_WH, 4),
                   "got_wh": round(nominal, 4),
                   "pass": abs(nominal - 8 * P.CELL_WH) < 1e-9,
                   "units": "Wh"})

    checks.append({"check": "usable at 20 C equals nominal",
                   "expected_wh": round(nominal, 4),
                   "got_wh": round(bat.usable_wh(nominal, nominal, 20.0), 4),
                   "pass": abs(bat.usable_wh(nominal, nominal, 20.0) - nominal) < 1e-6,
                   "units": "Wh"})

    checks.append({"check": "usable at -60 C equals 35 percent of nominal",
                   "expected_wh": round(nominal * 0.35, 4),
                   "got_wh": round(bat.usable_wh(nominal, nominal, -60.0), 4),
                   "pass": abs(bat.usable_wh(nominal, nominal, -60.0) - nominal * 0.35) < 1e-6,
                   "units": "Wh"})

    p8 = bat.max_discharge_power_w(8, 20.0)
    expected_p = P.C_RATE_MAX * 8 * P.CELL_AH * 3.6
    checks.append({"check": "C-rate ceiling = C_rate x amp-hours x volts",
                   "expected_w": round(expected_p, 4), "got_w": round(p8, 4),
                   "pass": abs(p8 - expected_p) < 1e-6, "units": "W"})

    below = bat.max_discharge_power_w(8, P.DEFAULT_MIN_OPERATING_C - 1.0)
    checks.append({"check": "no discharge below the operating floor",
                   "expected_w": 0.0, "got_w": below, "pass": below == 0.0,
                   "units": "W"})

    _, acc, rej = bat.step_charge(nominal, nominal, 60.0, 0.0, 5.0, -10.0)
    checks.append({"check": "charge inhibited below 0 C and reported, not lost",
                   "expected_w": "accepted 0.0 / rejected 5.0",
                   "got_w": f"accepted {acc} / rejected {rej}",
                   "pass": acc == 0.0 and rej == 5.0, "units": "W"})

    return {
        "category": "D",
        "category_label": V.CATEGORIES["D"],
        "equations": [
            "nominal_wh        = N_cells * wh_per_cell * capacity_mult",
            "capacity_fraction = piecewise-linear interpolation of CAPACITY_VS_TEMP, "
            "clamped at the endpoints",
            "usable_wh         = charge_wh - nominal_wh * (1 - capacity_fraction(T))",
            "max_discharge_w   = C_rate_max * N_cells * (Ah per cell) * 3.6 V, "
            "only for T above the operating floor",
            "step_charge       : new = charge - (P_out - P_pv * eta) * dt_h, "
            "clamped to [0, nominal]",
            "can_accept_charge : T >= charge_min_c (0 C)",
        ],
        "curve_points": [{"temp_c": t, "fraction": f} for t, f in curve],
        "consistency_checks": checks,
        "source_status": (
            "The capacity-vs-temperature curve is an ASSUMPTION. It is shaped like "
            "commonly published Li-ion behaviour but is NOT taken from a datasheet "
            "held for the specific cells used, and NO cell was tested at any "
            "temperature. Do not describe it as datasheet-verified."
        ),
        "unmeasured_parameters": [
            "Capacity at each temperature below 20 C",
            "Internal resistance vs temperature (affects the C-rate ceiling in the cold)",
            "Cell-to-cell capacity spread within the pack",
            "Ageing and cycle history of the actual cells",
        ],
        "required_before_any_flight_claim": (
            "A datasheet for the exact cell part number, and ideally a discharge "
            "test at low temperature. Until then the battery model is category D."
        ),
    }


# ===========================================================================
# TASK 4 -- NUMERICAL CONVERGENCE
# ===========================================================================
def task4_convergence(env, dt_list=(60.0, 30.0, 10.0, 5.0)):
    scenarios = {
        "default_fails_energy": DESIGNS["baseline_default"],
        "cheapest_passing": DESIGNS["cheapest_passing"],
    }
    out = []

    for label, design in scenarios.items():
        runs = {}
        for dt in dt_list:
            runs[dt] = ms.simulate(env, design, dt_override=dt)

        base_dt = dt_list[0]
        ref_dt = dt_list[-1]
        ref = runs[ref_dt]

        rows = []
        for dt in dt_list:
            r = runs[dt]
            rows.append({
                "dt_s": dt,
                "verdict": r["verdict"],
                "failure_reason": r["failure_reason"],
                "failure_time": r["failure_time"],
                "failure_minute": r["failure_minute"],
                "min_box_c": r["min_box_c"],
                "min_box_c_raw": r.get("min_box_c_raw"),
                "final_box_c_raw": r.get("final_box_c_raw"),
                "final_charge_wh": r["final_charge_wh"],
                "survival_hours": r["survival_hours"],
                "energy_margin_ratio": r["energy_margin_ratio"],
                "electrical_residual_wh": r["energy_balance"]["electrical"]["residual_wh"],
            })

        # change relative to the FINEST step, which is the best estimate here
        for row in rows:
            row["d_min_box_c_vs_finest"] = round(row["min_box_c"] - ref["min_box_c"], 4)
            row["d_final_charge_wh_vs_finest"] = round(
                row["final_charge_wh"] - ref["final_charge_wh"], 5)
            row["d_failure_min_vs_finest"] = (
                None if (row["failure_minute"] is None or ref["failure_minute"] is None)
                else round(row["failure_minute"] - ref["failure_minute"], 2))

        verdicts = {r["verdict"] for r in rows}
        reasons = {r["failure_reason"] for r in rows}
        times = [r["failure_minute"] for r in rows if r["failure_minute"] is not None]
        temps = [r["min_box_c"] for r in rows]

        max_dt_change = abs(rows[0]["d_min_box_c_vs_finest"])

        # Order of convergence from the UNROUNDED probe. The displayed value is
        # quantised to 0.1 C, which is coarser than the integrator error itself.
        halving = []
        raw_errs = []
        prev_err = None
        for dt in dt_list:
            r = runs[dt]
            err = abs(r.get("min_box_c_raw", r["min_box_c"]) - ref.get("min_box_c_raw", ref["min_box_c"]))
            raw_errs.append(round(err, 9))
            if prev_err is not None and err > 1e-12 and prev_err > 1e-12:
                halving.append(round(math.log2(prev_err / err), 3))
            prev_err = err

        # Failure time can only be detected to within one timestep, so the
        # reported depletion instant carries a +/- dt quantisation.
        failure_time_quantisation_min = max(dt_list) / 60.0

        out.append({
            "scenario": label,
            "design": {k: v for k, v in design.items()},
            "rows": rows,
            "verdict_stable": len(verdicts) == 1,
            "failure_reason_stable": len(reasons) == 1,
            "failure_time_spread_min": round(max(times) - min(times), 2) if times else 0.0,
            "min_temp_spread_c": round(max(temps) - min(temps), 4),
            "worst_min_temp_change_c": round(max_dt_change, 4),
            "raw_min_temp_errors_c": raw_errs,
            "observed_orders": halving,
            "order_estimate": round(sum(halving) / len(halving), 2) if halving else None,
            "failure_time_quantisation_min": failure_time_quantisation_min,
            "failure_time_quantisation_note": (
                "A failure can only be detected at the end of a step, so the reported "
                "depletion instant is quantised by +/- dt. A failure-time shift smaller "
                "than this is not evidence of divergence."),
        })

    return {
        "category": "C",
        "category_label": V.CATEGORIES["C"],
        "reference_step_s": dt_list[-1],
        "comparison_note": (
            "Differences are measured against the FINEST step tested (5 s), which "
            "is the best available estimate, not an exact solution. An exact "
            "solution exists only for benchmark A1."
        ),
        "results": out,
    }


# ===========================================================================
# TASK 6 -- PARAMETER UNCERTAINTY
# ===========================================================================
def task6_uncertainty(env, n_points=7):
    """Sweep the three highest-impact assumed parameters and re-rank the designs.

    NOTE ON WHAT THIS IS: these are EXPLORATORY ranges chosen to bound
    engineering plausibility. They are not confidence intervals and not derived
    from measurement. The output is a SCENARIO PASS RATE, never a probability of
    real-world survival.
    """
    axes = {
        "k_ins_w_per_mk": {"label": "Insulation conductivity", "values": [0.018, 0.024, 0.030, 0.036, 0.045],
                           "baseline": 0.030,
                           "basis": "Published range for XPS/aerogel-type foams. UNVALIDATED for this box."},
        "capacity_mult": {"label": "Battery capacity multiplier", "values": [1.0, 0.9, 0.8, 0.7, 0.6],
                          "baseline": 1.0,
                          "basis": "Exploratory. No cell tested."},
        "radiant_offset_c": {"label": "Radiant temperature offset", "values": [20.0, 15.0, 10.0, 5.0, 0.0],
                             "baseline": 10.0,
                             "basis": "Exploratory bound on view-factor uncertainty."},
    }

    # --- one axis at a time -------------------------------------------------
    oat = []
    for axis, spec in axes.items():
        for val in spec["values"]:
            row = {"axis": axis, "axis_label": spec["label"], "value": val,
                   "designs": {}}
            for name, design in DESIGNS.items():
                d = dict(design)
                d[axis] = val
                r = ms.simulate(env, d)
                row["designs"][name] = {
                    "verdict": r["verdict"],
                    "failure_reason": r["failure_reason"],
                    "failure_time": r["failure_time"],
                    "failure_minute": r["failure_minute"],
                    "min_box_c": r["min_box_c"],
                "min_box_c_raw": r.get("min_box_c_raw"),
                "final_box_c_raw": r.get("final_box_c_raw"),
                    "energy_margin_ratio": r["energy_margin_ratio"],
                    "cost_inr": cst.breakdown(d)["cost_inr"],
                }
            oat.append(row)

    # --- combined worst case ------------------------------------------------
    worst = {}
    for name, design in DESIGNS.items():
        d = dict(design)
        d["k_ins"] = axes["k_ins_w_per_mk"]["values"][-1]
        d["capacity_mult"] = axes["capacity_mult"]["values"][-1]
        d["radiant_offset_c"] = axes["radiant_offset_c"]["values"][0]
        r = ms.simulate(env, d)
        worst[name] = {
            "verdict": r["verdict"], "failure_reason": r["failure_reason"],
            "failure_time": r["failure_time"], "min_box_c": r["min_box_c"],
            "energy_margin_ratio": r["energy_margin_ratio"],
        }

    # --- does the cheapest-passing ranking survive? -------------------------
    ranking_flips = []
    for row in oat:
        passes = {n: d["verdict"] == "PASS" for n, d in row["designs"].items()}
        if not passes.get("cheapest_passing", False) and passes.get("most_robust", False):
            ranking_flips.append({
                "axis": row["axis"], "value": row["value"],
                "change": "cheapest_passing FAILS while most_robust PASSES",
            })

    return {
        "category": "D",
        "category_label": V.CATEGORIES["D"],
        "ranges_are_exploratory": True,
        "axes": {k: {"label": v["label"], "values": v["values"],
                     "baseline": v["baseline"], "basis": v["basis"]}
                 for k, v in axes.items()},
        "one_at_a_time": oat,
        "combined_worst_case": worst,
        "ranking_flips": ranking_flips,
        "ranking_survives": not ranking_flips,
        "disclaimer": (
            "These are SCENARIO PASS RATES over assumed input ranges. They are not "
            "probabilities of real-world survival. The ranges were chosen to bound "
            "engineering plausibility, not measured."
        ),
    }


# ===========================================================================
# REPORT WRITING
# ===========================================================================
def _fmt(v, n=3):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{n}f}"
    return str(v)


def write_markdown(payload, path):
    L = []
    A = L.append
    A("# COLDSTART — physics verification results")
    A("")
    A(f"Generated: **{payload['generated_utc']}**  ")
    A(f"Engine: `{payload['engine_version']}`  ")
    A(f"Forecast: {payload['provenance']}  ")
    A("")
    A("Reproduce with:")
    A("")
    A("```")
    A("cd app && python3 verify.py")
    A("python3 -m unittest discover -s tests -v")
    A("```")
    A("")
    A("---")
    A("")
    A("## Evidence categories")
    A("")
    A("| Tag | Meaning | Used here |")
    A("|---|---|---|")
    for k in ("A", "B", "C", "D", "E"):
        used = "yes" if k in payload["categories_used"] else "**no**"
        A(f"| **{k}** | {V.CATEGORIES[k]} | {used} |")
    A("")
    A(f"> {V.CATEGORY_E_NOTE}")
    A("")
    A("---")
    A("")

    # ---- Task 1 ---------------------------------------------------------
    A("## Task 1 — thermal model verification")
    A("")
    A("### Governing equations as implemented")
    A("")
    A("| Path | Equation | Source of the form |")
    A("|---|---|---|")
    for eq in payload["governing_equations"]:
        A(f"| {eq['path']} | `{eq['equation']}` | {eq['basis']} |")
    A("")
    for bench in payload["benchmarks"]:
        A(f"### {bench['id']} — {bench['title']}  `[{bench['category']}]`")
        A("")
        A(f"*{bench['category_label']}*")
        A("")
        A(f"**Method.** {bench['method']}")
        A("")
        A(f"**Reference.** {bench['reference']}")
        A("")
        A("**Conditions.**")
        A("")
        A("```")
        A(json.dumps(bench["conditions"], indent=2, default=str))
        A("```")
        A("")
        if bench["items"] and "dt_s" in bench["items"][0]:
            A("| dt (s) | engine (°C) | analytical (°C) | abs error (°C) | rel error (%) |")
            A("|---|---|---|---|---|")
            for it in bench["items"]:
                A(f"| {it['dt_s']:.0f} | {it['engine_c']:.6f} | {it['analytical_c']:.6f} "
                  f"| {it['abs_error_c']:+.6f} | {it['rel_error_pct']:+.6f} |")
        elif bench["items"] and "check" in bench["items"][0]:
            A("| Check | Expected | Observed | Result |")
            A("|---|---|---|---|")
            for it in bench["items"]:
                mark = "PASS" if it.get("pass") else "**FAIL**"
                A(f"| {it['check']} | {it.get('expected','')} | {it.get('observed','')} | {mark} |")
        elif bench["items"] and "altitude_km" in bench["items"][0]:
            A("| Alt (km) | Ref T (°C) | Engine T (°C) | T err (°C) | Ref p (hPa) | Engine p (hPa) | p err (%) |")
            A("|---|---|---|---|---|---|---|")
            for it in bench["items"]:
                A(f"| {it['altitude_km']:.0f} | {it['ref_temperature_c']:+.2f} | "
                  f"{it['engine_temperature_c']:+.2f} | {it['temperature_abs_error_c']:.4f} | "
                  f"{it['ref_pressure_hpa']:.2f} | {it['engine_pressure_hpa']:.2f} | "
                  f"{it['pressure_rel_error_pct']:.4f} |")
        elif bench["items"] and "t_skin_c" in bench["items"][0]:
            A("| T_skin (°C) | T_radiant (°C) | engine (W) | analytical (W) | abs error (W) | direction |")
            A("|---|---|---|---|---|---|")
            for it in bench["items"]:
                A(f"| {it['t_skin_c']:+.1f} | {it['t_radiant_c']:+.1f} | {it['engine_w']:.10f} | "
                  f"{it['analytical_w']:.10f} | {it['abs_error_w']:+.2e} | {it['direction']} |")
        elif bench["items"] and "ambient_c" in bench["items"][0]:
            A("| Ambient (°C) | Ins (mm) | Engine (°C) | Independent (°C) | abs error (°C) | residual at root (W) |")
            A("|---|---|---|---|---|---|")
            for it in bench["items"]:
                A(f"| {it['ambient_c']:+.0f} | {it['insulation_mm']:.0f} | {it['engine_c']:.6f} | "
                  f"{it['independent_c']:.6f} | {it['abs_error_c']:+.2e} | "
                  f"{it['residual_at_solution_w']:+.2e} |")
        elif bench["items"] and "parameter" in bench["items"][0]:
            A("| Parameter | Value | Basis | Impact | Exploratory range |")
            A("|---|---|---|---|---|")
            for it in bench["items"]:
                A(f"| {it['parameter']} | {it['value']} | {it['basis']} | {it['impact']} | "
                  f"{it['exploratory_range_low']} … {it['exploratory_range_high']} |")
        A("")
        A("**Limitations.**")
        A("")
        for lim in bench["limitations"]:
            A(f"- {lim}")
        A("")

    # ---- Task 2 ---------------------------------------------------------
    t2 = payload["task2_energy"]
    A("## Task 2 — energy conservation `[C]`")
    A("")
    A(f"**Sign convention.** {t2['sign_convention']}")
    A("")
    A(f"**Numerical tolerance.** {t2['tolerance_wh']:.0e} Wh.")
    A("")
    A("| Design | Verdict | Storage drop | Payload | Heater | PV in | Residual | Pass |")
    A("|---|---|---|---|---|---|---|---|")
    for r in t2["rows"]:
        A(f"| {r['design']} | {r['verdict']} | {r['storage_drop_wh']:.4f} | "
          f"{r['payload_delivered_wh']:.4f} | {r['heater_delivered_wh']:.4f} | "
          f"{r['pv_into_cells_wh']:.4f} | {r['electrical_residual_wh']:+.3e} | "
          f"{'yes' if r['electrical_pass'] else '**NO**'} |")
    A("")
    A("### State consistency scan")
    A("")
    A("| Design | Points | Checks | Violations | Clean |")
    A("|---|---|---|---|---|")
    for r in t2["rows"]:
        a = r["state_audit"]
        A(f"| {r['design']} | {a['points_scanned']} | {a['checks_run']} | "
          f"{len(a['violations'])} | {'yes' if a['clean'] else '**NO**'} |")
    A("")
    A(f"**Defects found and fixed in this pass.** {len(t2['defects_found_and_fixed'])}")
    A("")
    for d in t2["defects_found_and_fixed"]:
        A(f"- **{d['id']}** — {d['defect']}")
        A(f"  - *Cause:* {d['cause']}")
        A(f"  - *Fix:* {d['fix']}")
        A(f"  - *Regression test:* `{d['regression_test']}`")
    A("")
    A(f"**On the thermal residual.** {t2['note_thermal']}")
    A("")

    # ---- Task 3 ---------------------------------------------------------
    t3 = payload["task3_battery"]
    A("## Task 3 — battery model `[D]`")
    A("")
    A("### Equations as implemented")
    A("")
    for eq in t3["equations"]:
        A(f"- `{eq}`")
    A("")
    A("### Reference comparison")
    A("")
    A(f"{t3['source_status']}")
    A("")
    A("| Check | Expected | Got | Result |")
    A("|---|---|---|---|")
    for c in t3["consistency_checks"]:
        exp = c.get("expected_wh", c.get("expected_w"))
        got = c.get("got_wh", c.get("got_w"))
        A(f"| {c['check']} | {exp} | {got} | {'PASS' if c['pass'] else '**FAIL**'} |")
    A("")
    A("### Unmeasured parameters")
    A("")
    for u in t3["unmeasured_parameters"]:
        A(f"- {u}")
    A("")
    A(f"**Required before any flight claim.** {t3['required_before_any_flight_claim']}")
    A("")

    # ---- Task 4 ---------------------------------------------------------
    t4 = payload["task4_convergence"]
    A("## Task 4 — numerical convergence `[C]`")
    A("")
    A(f"*{t4['comparison_note']}*")
    A("")
    for s in t4["results"]:
        A(f"### {s['scenario']}")
        A("")
        A("| dt (s) | Verdict | Failure | ΔT_min vs finest (°C) | Δfinal charge vs finest (Wh) | Δfailure time vs finest (min) |")
        A("|---|---|---|---|---|---|")
        for r in s["rows"]:
            A(f"| {_fmt(r['dt_s'],0)} | {r['verdict']} | {r['failure_time'] or '—'} | "
              f"{r['d_min_box_c_vs_finest']:+.4f} | {r['d_final_charge_wh_vs_finest']:+.5f} | "
              f"{r['d_failure_min_vs_finest'] if r['d_failure_min_vs_finest'] is not None else '—'} |")
        A("")
        A(f"- Verdict stable across all timesteps: **{'yes' if s['verdict_stable'] else 'NO'}**")
        A(f"- Failure reason stable: **{'yes' if s['failure_reason_stable'] else 'NO'}**")
        A(f"- Failure-time spread: **{s['failure_time_spread_min']:.2f} min**")
        A(f"- Min-temperature spread: **{s['min_temp_spread_c']:.4f} °C**")
        A(f"- Worst min-temperature change vs the 5 s reference: **{s['worst_min_temp_change_c']:.4f} °C**")
        A(f"- Observed order of convergence: **{s['order_estimate']}** "
          f"(first-order expected for forward Euler; per-halving values {s['observed_orders']})")
        A("")

    # ---- Task 6 ---------------------------------------------------------
    t6 = payload["task6_uncertainty"]
    A("## Task 6 — parameter uncertainty `[D]`")
    A("")
    A(f"**All ranges are exploratory**, chosen to bound engineering plausibility. They are not "
      f"confidence intervals and not derived from measurement.")
    A("")
    A("| Axis | Baseline | Values swept | Basis |")
    A("|---|---|---|---|")
    for k, v in t6["axes"].items():
        A(f"| {v['label']} | {v['baseline']} | {v['values']} | {v['basis']} |")
    A("")
    A("### One axis at a time — verdict of each design")
    A("")
    A("| Axis | Value | baseline_default | cheapest_passing | most_robust |")
    A("|---|---|---|---|---|")
    for row in t6["one_at_a_time"]:
        cells = []
        for n in ("baseline_default", "cheapest_passing", "most_robust"):
            d = row["designs"][n]
            mark = "PASS" if d["verdict"] == "PASS" else f"FAIL {d['failure_reason'] or ''}".strip()
            cells.append(f"{mark} @ {d['failure_time'] or '—'}")
        A(f"| {row['axis_label']} | {row['value']} | " + " | ".join(cells) + " |")
    A("")
    A("### Combined worst case")
    A("")
    A("| Design | Verdict | Failure | Time | Min T (°C) | Margin |")
    A("|---|---|---|---|---|---|")
    for name, d in t6["combined_worst_case"].items():
        A(f"| {name} | {d['verdict']} | {d['failure_reason'] or '—'} | {d['failure_time'] or '—'} | "
          f"{_fmt(d['min_box_c'],1)} | {_fmt(d['energy_margin_ratio'],2)} |")
    A("")
    if t6["ranking_flips"]:
        A("**Ranking is NOT stable.** The following combinations invert the cost/robustness ordering:")
        A("")
        for f in t6["ranking_flips"]:
            A(f"- {f['axis']} = {f['value']}: {f['change']}")
    else:
        A("**Ranking is stable** across every swept value: the robust design never fails "
          "while the cheapest-passing design survives.")
    A("")
    A(f"> {t6['disclaimer']}")
    A("")
    A("---")
    A("")
    A("## Unresolved defects and limitations")
    A("")
    for item in payload["unresolved"]:
        A(f"- {item}")
    A("")
    return "\n".join(L)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Fetching forecast ...")
    env = build_env()
    prov = env.get("sources", {}).get("upper_air", {}).get("source", "UNKNOWN")
    print(f"  provenance: {prov}")

    print("Task 1/5  benchmarks ...")
    benchmarks = V.run_all_benchmarks()
    bench_summary = V.summary(benchmarks)

    print("Task 2  energy audit ...")
    t2 = task2_energy(env)

    print("Task 3  battery ...")
    t3 = task3_battery()

    print("Task 4  convergence ...")
    t4 = task4_convergence(env)

    print("Task 6  uncertainty ...")
    t6 = task6_uncertainty(env)

    governing = [
        {"path": "Conduction", "equation": "UA_cond = (k / t) * A, q = UA_cond * (T_box - T_skin)",
         "basis": "Fourier steady conduction through a plane wall."},
        {"path": "Convection", "equation": "h = h0 * sqrt(p(alt)/p(0)), q = h A (T_skin - T_amb)",
         "basis": "Natural convection; h0 an assumed small-enclosure value (category D), "
                  "scaled by the square root of the pressure ratio."},
        {"path": "Radiation",
         "equation": "q = eps * sigma * A * (T_skin^4 - T_rad^4), T_rad = T_amb - offset",
         "basis": "Stefan-Boltzmann. The offset collapses Earth/horizon/space view factors "
                  "into one parameter (category D)."},
        {"path": "Skin closure",
         "equation": "UA_cond (T_box - T_skin) = h A (T_skin - T_amb) + eps sigma A (T_skin^4 - T_rad^4)",
         "basis": "Conduction and surface loss are IN SERIES. Solved each step by bisection."},
        {"path": "Lumped node",
         "equation": "C_th dT/dt = Q_heater + Q_selfheat - q_loss",
         "basis": "Lumped-capacitance. C_th sums pack, insulation and housing mass x cp."},
        {"path": "Solar (electrical only)",
         "equation": "P_pv = I_direct(alt, elevation) * A_panel * eta * view",
         "basis": "Beer-Lambert attenuation of extraterrestrial irradiance. Solar HEATING of "
                  "the box structure is NOT modelled — see limitations."},
        {"path": "Internal heat generation",
         "equation": "Q_selfheat = PAYLOAD_HEAT_FRACTION * delivered_payload_power",
         "basis": "Assumed fraction (category D), applied to DELIVERED power only."},
        {"path": "Battery",
         "equation": "usable = charge - nominal*(1 - f(T));  P_max = C_rate * Ah * V",
         "basis": "Capacity curve is an assumption (category D)."},
    ]

    unresolved = [
        "Box thermal conductance UA is UNVALIDATED. It derives from an assumed "
        "conductivity and an assumed geometry; no bench measurement exists.",
        "The battery capacity-vs-temperature curve is an ASSUMPTION. No specific cell "
        "datasheet is attached and no cell was tested.",
        "The radiant temperature offset is a single parameter standing in for full "
        "view-factor geometry. It is the largest uncertainty in the loss path.",
        "SOLAR HEATING OF THE STRUCTURE IS NOT MODELLED. The model computes solar "
        "ELECTRICAL generation only. A sunlit payload is not warmed in this model, so "
        "daytime scenarios are biased cold.",
        "The engine's ISA is isothermal above 11 km and therefore diverges from the "
        "published standard atmosphere above about 20 km (see benchmark B1).",
        "Thermal residual in the energy balance is an identity for forward Euler and is "
        "not an accuracy measure; real truncation error is quantified in Tasks 1 and 4.",
        "Overheating failure mode is modelled but has never been observed in flight.",
        "Uncertainty ranges are exploratory and are not probability distributions, so no "
        "survival probability is reported anywhere in this project.",
        "Category E (physical experiment) is empty. No bench test was conducted.",
    ]

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine_version": getattr(P, "ENGINE_VERSION", "unknown"),
        "provenance": prov,
        "site": {"lat": SITE[0], "lon": SITE[1], "date": DATE,
                 "launch_local": f"{DATE} {LAUNCH_HOUR:02d}:00 IST"},
        "categories_used": ["A", "B", "C", "D"],
        "category_e_note": V.CATEGORY_E_NOTE,
        "governing_equations": governing,
        "benchmarks": benchmarks,
        "benchmark_summary": bench_summary,
        "task2_energy": t2,
        "task3_battery": t3,
        "task4_convergence": t4,
        "task6_uncertainty": t6,
        "unresolved": unresolved,
    }

    json_path = os.path.join(OUT_DIR, "results.json")
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    md_path = os.path.join(OUT_DIR, "RESULTS.md")
    with open(md_path, "w") as f:
        f.write(write_markdown(payload, md_path))

    print("")
    print("benchmarks        :", bench_summary["benchmarks"],
          "| checks:", bench_summary["checks"],
          "| failed:", bench_summary["failed_checks"] or "none")
    print("energy balance    :",
          "all residuals within tolerance" if all(r["electrical_pass"] for r in t2["rows"])
          else "RESIDUAL OUT OF TOLERANCE")
    print("state audit       :",
          "clean" if all(r["state_audit"]["clean"] for r in t2["rows"])
          else "VIOLATIONS FOUND")
    print("convergence       :",
          "; ".join(f"{s['scenario']}: verdict {'stable' if s['verdict_stable'] else 'UNSTABLE'}, "
                    f"T spread {s['min_temp_spread_c']:.4f} C, order {s['order_estimate']}"
                    for s in t4["results"]))
    print("uncertainty       :",
          f"ranking {'stable' if t6['ranking_survives'] else 'FLIPS'} "
          f"({len(t6['ranking_flips'])} flips)")
    print("")
    print("written:", os.path.normpath(json_path))
    print("written:", os.path.normpath(md_path))


if __name__ == "__main__":
    main()
