"""
verification.py -- verification benchmarks for the COLDSTART physics engine.
============================================================================
Answers one question: "how do we know the numbers are right, without a lab?"

EVIDENCE CATEGORIES -- every result produced here carries exactly one.
    A  Analytical verification ..... compared against a closed-form solution
    B  Independent reference ....... compared against an external published source
    C  Numerical / software ........ convergence, invariants, regression
    D  Assumption / exploratory .... chosen, not verified
    E  Physical experiment ......... NOT PERFORMED ANYWHERE IN THIS PROJECT

Category E is never assigned. No result in this file, and none in the app,
comes from a physical bench measurement. That is stated in the output itself so
it cannot be lost when a number is copied into a slide.

WHAT IS AND IS NOT BEING CLAIMED
--------------------------------
A benchmark passing means the CODE solves the EQUATION it says it solves. It
does not mean the equation matches a real payload: the conductivity, the
emissivity and the capacity curve are still assumptions. Those are category D
and they are listed as such below.
"""

import math

from . import atmosphere as atm
from . import params as P
from . import thermal as th

CATEGORIES = {
    "A": "Analytical verification -- compared against a closed-form solution",
    "B": "Independent reference comparison -- external published source",
    "C": "Numerical / software verification -- convergence, invariants, regression",
    "D": "Assumption or exploratory scenario -- chosen, not verified",
    "E": "Physical experiment -- NOT PERFORMED",
}

CATEGORY_E_NOTE = (
    "Category E is deliberately empty. No physical bench test, no flown payload "
    "and no laboratory measurement was performed for this project. Every thermal "
    "and electrical result here is analytical, computational or assumed."
)


def _result(bid, title, category, conditions, reference, items,
            limitations, method):
    return {
        "id": bid,
        "title": title,
        "category": category,
        "category_label": CATEGORIES[category],
        "method": method,
        "conditions": conditions,
        "reference": reference,
        "items": items,
        "limitations": limitations,
    }


# ===========================================================================
# A1 -- EXACT SOLUTION OF THE LUMPED-CAPACITANCE ODE
# ===========================================================================
def exact_lumped_temperature(t0_c, t_amb_c, q_in_w, ua_eff_w_per_k, c_th_j_per_k, t_s):
    """Closed-form solution of  C dT/dt = Q_in - UA_eff (T - T_amb).

        T(t) = T_inf + (T0 - T_inf) * exp(-t / tau)
        T_inf = T_amb + Q_in / UA_eff          tau = C_th / UA_eff

    Valid only while UA_eff is constant and there is no radiation term.
    """
    if q_in_w == 0.0:
        return t_amb_c + (t0_c - t_amb_c) * math.exp(-ua_eff_w_per_k * t_s / c_th_j_per_k)
    t_inf = t_amb_c + q_in_w / ua_eff_w_per_k
    tau = c_th_j_per_k / ua_eff_w_per_k
    return t_inf + (t0_c - t_inf) * math.exp(-t_s / tau)


def series_ua_conduction_convection(insulation_mm, area_m2, k_ins, altitude_km):
    """Hand-derived series conductance used as the analytical reference.

    With radiation switched off, the skin solve reduces to two conductances in
    series and the loss becomes EXACTLY linear in (T_box - T_amb):

        q = UA_cond * (T_box - T_skin),   UA_cond * (T_box - T_skin)
                = h*A * (T_skin - T_amb)
        =>  q = UA_eff * (T_box - T_amb),
            UA_eff = UA_cond * hA / (UA_cond + hA)

    This is derived by hand here rather than read from the engine, so that the
    comparison is genuinely independent of the implementation.
    """
    ua_cond = (k_ins / (max(insulation_mm, 1.0) / 1000.0)) * area_m2
    hA = th.convection_coefficient_w_m2k(altitude_km) * area_m2
    return ua_cond * hA / (ua_cond + hA)


def bench_A1_decay(insulation_mm=50.0, cells=8, dt_list=(60.0, 30.0, 10.0, 5.0),
                   t0_c=20.0, t_amb_c=-55.0, q_in_w=0.0, altitude_km=26.0,
                   duration_s=7200.0):
    """Compare the engine's integrator against the exact closed-form solution.

    Radiation is switched off (emissivity = 0) so a closed form exists. That is
    stated in the conditions, because the benchmark therefore does NOT verify the
    radiative term -- benchmark A2 does that separately, against the exact
    Stefan-Boltzmann expression.
    """
    area = P.DEFAULT_BOX_AREA_M2
    k = P.DEFAULT_K_INSULATION
    ua_eff = series_ua_conduction_convection(insulation_mm, area, k, altitude_km)
    c_th = th.thermal_capacity_j_per_k(cells, insulation_mm, area)

    t_exact = exact_lumped_temperature(t0_c, t_amb_c, q_in_w, ua_eff, c_th, duration_s)

    items = []
    for dt in dt_list:
        t = t0_c
        n = int(round(duration_s / dt))
        for _ in range(n):
            t = th.step_temperature(t, t_amb_c, altitude_km, dt, c_th, q_in_w, 0.0,
                                    insulation_mm, area, k, emissivity=0.0)
        abs_err = t - t_exact
        rel_err = abs_err / abs(t_exact - t_amb_c) if abs(t_exact - t_amb_c) > 1e-9 else 0.0
        items.append({
            "dt_s": dt,
            "engine_c": round(t, 6),
            "analytical_c": round(t_exact, 6),
            "abs_error_c": round(abs_err, 6),
            "rel_error_pct": round(100.0 * rel_err, 6),
        })

    # observed order of convergence from consecutive halvings
    orders = []
    for a, b in zip(items, items[1:]):
        ea, eb = abs(a["abs_error_c"]), abs(b["abs_error_c"])
        if ea > 1e-12 and eb > 1e-12:
            orders.append(math.log(ea / eb) / math.log(a["dt_s"] / b["dt_s"]))
    order_estimate = round(sum(orders) / len(orders), 3) if orders else None

    return _result(
        "A1", "Lumped-capacitance decay vs closed-form solution", "A",
        {
            "insulation_mm": insulation_mm, "cells": cells, "area_m2": area,
            "k_ins_w_per_mk": k, "altitude_km": altitude_km,
            "t_initial_c": t0_c, "t_ambient_c": t_amb_c,
            "heat_input_w": q_in_w, "duration_s": duration_s,
            "emissivity": 0.0,
            "ua_eff_w_per_k_hand_derived": round(ua_eff, 8),
            "c_th_j_per_k": round(c_th, 3),
            "tau_s": round(c_th / ua_eff, 3),
            "observed_order_of_convergence": order_estimate,
            "expected_order": 1.0,
            "order_note": ("Forward Euler is first-order. The observed order is "
                           "measured against the exact closed form, so unlike the "
                           "mission-level study in app/verify.py this reference is "
                           "not itself an approximation."),
        },
        "T(t) = T_inf + (T0 - T_inf) exp(-t/tau), with UA_eff derived by hand as "
        "a series combination of conduction and convection.",
        items,
        [
            "Exact only because radiation is disabled; the radiative term is not "
            "exercised by this benchmark.",
            "UA_eff is treated as constant, so this does NOT verify the "
            "altitude-varying convection or the temperature-dependent terms.",
            "This verifies the integrator and the conduction/convection network. "
            "It says nothing about whether k = 0.030 W/m/K is the real value for "
            "the box (category D).",
        ],
        "Forward Euler advanced to a fixed final time at four timesteps and "
        "compared with the closed-form solution. Error must fall as dt falls.",
    )


# ===========================================================================
# A2 -- STEFAN-BOLTZMANN EXACT
# ===========================================================================
def bench_A2_radiation():
    """Radiation routine against the exact Stefan-Boltzmann expression."""
    area, eps = P.DEFAULT_BOX_AREA_M2, 0.90
    cases = [(20.0, -60.0), (0.0, -60.0), (-40.0, -60.0), (-60.0, -60.0)]
    items = []
    for t_skin, t_rad in cases:
        expected = (eps * P.STEFAN_BOLTZMANN * area
                    * (P.c_to_k(t_skin) ** 4 - P.c_to_k(t_rad) ** 4))
        got = th._radiation_from_skin_w(t_skin, t_rad, area, eps)
        items.append({
            "t_skin_c": t_skin, "t_radiant_c": t_rad,
            "engine_w": round(got, 10), "analytical_w": round(expected, 10),
            "abs_error_w": round(got - expected, 12),
            "rel_error_pct": round(100.0 * (got - expected) / expected, 10)
            if expected else 0.0,
            "direction": "loses heat" if got > 0 else ("gains heat" if got < 0 else "balanced"),
        })
    return _result(
        "A2", "Stefan-Boltzmann radiation against the exact expression", "A",
        {"area_m2": area, "emissivity": eps,
         "sigma_w_m2_k4": P.STEFAN_BOLTZMANN},
        "q = eps * sigma * A * (T_skin^4 - T_radiant^4)",
        items,
        [
            "Verifies the arithmetic, not the view factors. The real payload sees "
            "Earth and horizon as well as space; that is collapsed into a single "
            "assumed radiant temperature offset (category D).",
            "Assumes the skin is isothermal and grey.",
        ],
        "Direct comparison of the implementation with the closed-form expression.",
    )


# ===========================================================================
# A3 -- EQUILIBRIUM SOLVER vs INDEPENDENT ITERATION
# ===========================================================================
def bench_A3_equilibrium():
    """The engine's bisection equilibrium solver vs an independent secant solve."""
    items = []
    for ambient in (-70.0, -55.0, -40.0, -20.0):
        for insulation in (25.0, 50.0, 75.0):
            heater = 5.0
            self_heat = 1.8
            engine_t, converged, _r = th.equilibrium_diagnostics(
                ambient, 26.0, insulation, P.DEFAULT_BOX_AREA_M2,
                P.DEFAULT_K_INSULATION, heater, self_heat)

            # independent solve: bisect the residual from scratch, different code
            def residual(t):
                return (heater + self_heat
                        - th.heat_loss_w(t, ambient, 26.0, insulation,
                                         P.DEFAULT_BOX_AREA_M2, P.DEFAULT_K_INSULATION))
            lo, hi = -200.0, 400.0
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                if residual(mid) > 0:
                    lo = mid
                else:
                    hi = mid
            indep = 0.5 * (lo + hi)

            items.append({
                "ambient_c": ambient, "insulation_mm": insulation,
                "heater_w": heater, "self_heat_w": self_heat,
                "engine_c": round(engine_t, 6),
                "independent_c": round(indep, 6),
                "abs_error_c": round(engine_t - indep, 9),
                "residual_at_solution_w": round(residual(engine_t), 9),
                "root_bracketed": converged,
                "above_max_operating_c": engine_t > P.DEFAULT_MAX_OPERATING_C,
                "pass": bool(converged and abs(engine_t - indep) < 1e-6),
            })
    return _result(
        "A3", "Equilibrium solver vs an independent root find", "A",
        {"altitude_km": 26.0, "emissivity": P.DEFAULT_EMISSIVITY,
         "radiant_offset_c": P.DEFAULT_RADIANT_OFFSET_C},
        "Solve (Q_heater + Q_selfheat) = q_loss(T_eq)",
        items,
        [
            "Both solvers call the same heat_loss_w routine, so this verifies the "
            "root-finding, not the loss model itself.",
            "Equilibrium assumes the ambient is constant, which a real ascent is not. "
            "The bench protocol in bench/ measures this quantity, which is why it is "
            "the right comparison for a future physical test.",
            "Several of these configurations equilibrate ABOVE the 60 C maximum "
            "operating temperature. That is not a solver error: a well-insulated box "
            "with a standing 5 W heater genuinely overheats. It is why the engine has "
            "a TEMP_ABOVE_OPERATING failure mode.",
        ],
        "Engine bisection compared with an independent bisection written in this "
        "file, plus the residual at the returned root.",
    )


# ===========================================================================
# B1 -- ISA vs THE PUBLISHED US STANDARD ATMOSPHERE TABLE
# ===========================================================================
# Values from the US Standard Atmosphere 1976 / ICAO ISA, the standard reference
# table. These are published reference values, not measurements taken here.
ISA_REFERENCE_TABLE = [
    (0.0, 288.15, 15.00, 1013.25),
    (1.0, 281.65, 8.50, 898.75),
    (2.0, 275.15, 2.00, 795.01),
    (5.0, 255.65, -17.50, 540.20),
    (10.0, 223.15, -50.00, 264.36),
    (11.0, 216.65, -56.50, 226.32),
    (15.0, 216.65, -56.50, 120.45),
    (20.0, 216.65, -56.50, 54.75),
]


def bench_B1_isa():
    """Engine ISA against the published standard-atmosphere reference table."""
    items = []
    for alt_km, t_k, t_c, p_hpa in ISA_REFERENCE_TABLE:
        engine_t = atm.isa_temperature_c(alt_km)
        engine_p = atm.isa_pressure_hpa(alt_km)
        items.append({
            "altitude_km": alt_km,
            "ref_temperature_c": t_c,
            "engine_temperature_c": round(engine_t, 4),
            "temperature_abs_error_c": round(abs(engine_t - t_c), 4),
            "ref_pressure_hpa": p_hpa,
            "engine_pressure_hpa": round(engine_p, 4),
            "pressure_abs_error_hpa": round(abs(engine_p - p_hpa), 4),
            "pressure_rel_error_pct": round(100.0 * abs(engine_p - p_hpa) / p_hpa, 4),
            "units": "degC, hPa",
        })
    return _result(
        "B1", "Engine ISA vs published US Standard Atmosphere 1976", "B",
        {"engine_model": "linear lapse to 11 km, isothermal above",
         "valid_range_claimed_km": "0-20"},
        "US Standard Atmosphere 1976 / ICAO ISA reference table "
        "(15 degC and 1013.25 hPa at sea level, 6.5 K/km to 11 km, "
        "216.65 K isothermal above).",
        items,
        [
            "The engine is isothermal above 11 km, so it is exact through 20 km and "
            "DIVERGES above it: the real atmosphere warms from ~20 km and reaches "
            "228.65 K at 32 km. The engine is not used as a data source above the "
            "forecast ceiling except as a declared fallback, and this table shows "
            "where that fallback is weakest.",
            "ISA is a reference atmosphere, not a forecast for any particular night.",
        ],
        "Direct value-by-value comparison with the published reference table.",
    )


# ===========================================================================
# A4 -- LIMITING CASES AND FLOW DIRECTION
# ===========================================================================
def bench_A4_limits():
    """Heat must flow from hot to cold, and the skin must sit between them."""
    area, k = P.DEFAULT_BOX_AREA_M2, P.DEFAULT_K_INSULATION
    items = []

    # 1. flow direction
    for t_box, t_amb, expected in ((-10.0, -55.0, "out"), (-55.0, -10.0, "in"),
                                   (-55.0, -55.0, "balanced")):
        q = th.heat_loss_w(t_box, t_amb, 26.0, 50.0, area, k)
        got = "out" if q > 0.5 else ("in" if q < -0.5 else "balanced")
        items.append({
            "check": "flow direction",
            "t_box_c": t_box, "t_ambient_c": t_amb,
            "heat_flow_w": round(q, 6), "expected": expected, "observed": got,
            "pass": got == expected,
        })

    # 2. skin bounded by box and environment (allowing for the radiant offset)
    for t_box in (20.0, 0.0, -20.0, -50.0):
        t_amb = -55.0
        t_skin = th.skin_temperature_c(t_box, t_amb, 26.0, 50.0, area, k)
        t_rad = th.radiant_temperature_c(t_amb)
        lo = min(t_rad, t_amb) - 1.0
        items.append({
            "check": "skin bounded",
            "t_box_c": t_box, "t_ambient_c": t_amb,
            "t_skin_c": round(t_skin, 4), "t_radiant_c": round(t_rad, 3),
            "expected": f"{lo:.1f} <= t_skin <= {t_box}",
            "observed": round(t_skin, 4),
            "pass": lo <= t_skin <= t_box + 1e-6,
        })

    # 3. more insulation must not increase loss
    uas = [th.effective_ua(mm, area, k, 26.0, -52.0) for mm in (5, 25, 50, 75, 100)]
    mono = all(a >= b - 1e-12 for a, b in zip(uas, uas[1:]))
    items.append({
        "check": "monotonic in insulation",
        "ua_by_thickness_w_per_k": [round(u, 6) for u in uas],
        "expected": "strictly decreasing",
        "observed": "decreasing" if mono else "NOT monotonic",
        "pass": mono,
    })

    # 4. PASSIVE EQUILIBRIUM: the box must settle where the skin balances.
    #
    # This is NOT the ambient temperature. At 26 km the payload radiates to a
    # sink colder than the air, so a box with no heat input settles BELOW
    # ambient. The first version of this check asserted a band around the
    # ambient value and failed -- the assertion was wrong, not the model.
    #
    # The correct reference is the closed-form balance at the skin:
    #     h*A*(T_skin - T_amb) + eps*sigma*A*(T_skin^4 - T_rad^4) = 0
    # and at equilibrium T_box == T_skin. Solved here independently.
    t = 0.0
    c_th = th.thermal_capacity_j_per_k(8, 50, area)
    for _ in range(200000):
        t = th.step_temperature(t, -60.0, 26.0, 5.0, c_th, 0.0, 0.0, 50.0, area, k)

    t_amb, t_rad = -60.0, th.radiant_temperature_c(-60.0)
    hA = th.convection_coefficient_w_m2k(26.0) * area

    def skin_balance(ts):
        return (hA * (ts - t_amb)
                + th._radiation_from_skin_w(ts, t_rad, area, P.DEFAULT_EMISSIVITY))

    lo, hi = -120.0, t_amb
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if skin_balance(mid) < 0:
            lo = mid
        else:
            hi = mid
    t_ref = 0.5 * (lo + hi)

    items.append({
        "check": "passive equilibrium matches closed-form skin balance",
        "t_ambient_c": t_amb, "t_radiant_c": round(t_rad, 3),
        "t_final_c": round(t, 6), "analytical_c": round(t_ref, 6),
        "abs_error_c": round(abs(t - t_ref), 6),
        "expected": f"T settles at {t_ref:.3f} C, i.e. BELOW ambient, not at it",
        "observed": round(t, 4),
        "pass": abs(t - t_ref) < 0.05,
        "note": ("Radiative cooling to a sink colder than the air drives the box "
                 "below ambient. Settling above ambient with zero heat input would "
                 "violate the second law."),
    })

    # 5. no heater, box starts cold: heat must flow IN
    q_cold = th.heat_loss_w(-70.0, -55.0, 26.0, 50.0, area, k)
    items.append({
        "check": "colder box gains heat",
        "t_box_c": -70.0, "t_ambient_c": -55.0,
        "heat_flow_w": round(q_cold, 6),
        "expected": "negative (gaining)", "observed": "negative" if q_cold < 0 else "positive",
        "pass": q_cold < 0,
    })

    return _result(
        "A4", "Limiting cases and heat-flow direction", "A",
        {"area_m2": area, "k_ins": k, "altitude_km": 26.0},
        "Second law of thermodynamics and the monotonicity of a series "
        "conductance network.",
        items,
        [
            "These are invariants, not quantitative accuracy checks: they catch a "
            "sign error or a broken monotonicity, not a wrong magnitude.",
            "The 'balanced' tolerance of +/-0.5 W exists because the radiant sink is "
            "colder than the air, so a box at air temperature still loses a little.",
        ],
        "Direct evaluation of limiting cases with asserted expected behaviour.",
    )


# ===========================================================================
# D1 -- PARAMETERS THAT ARE ASSUMED, NOT VERIFIED
# ===========================================================================
ASSUMED_PARAMETERS = [
    {"parameter": "Insulation conductivity k", "value": "0.030 W/m/K",
     "category": "D", "basis": "Typical published value for XPS foam",
     "impact": "Directly scales UA and therefore every thermal time. UNVALIDATED.",
     "range_low": 0.018, "range_high": 0.045},
    {"parameter": "Box surface area", "value": "0.0864 m2",
     "category": "D", "basis": "12 x 12 x 12 cm outer envelope",
     "impact": "Linear in UA. A different box changes everything.",
     "range_low": 0.06, "range_high": 0.12},
    {"parameter": "Surface emissivity", "value": "0.90",
     "category": "D", "basis": "Typical for foam / tape / paint",
     "impact": "Scales the radiative term, which dominates at 26 km.",
     "range_low": 0.80, "range_high": 0.95},
    {"parameter": "Radiant temperature offset", "value": "10 K below air",
     "category": "D", "basis": "First-order stand-in for Earth + horizon + space view factors",
     "impact": "The largest single modelling uncertainty in the loss path.",
     "range_low": 5.0, "range_high": 20.0},
    {"parameter": "Natural convection coefficient h0", "value": "5.0 W/m2/K",
     "category": "D", "basis": "Typical small-enclosure value from heat-transfer texts",
     "impact": "Weak at 26 km where convection is ~1.5% of sea level; matters low down.",
     "range_low": 3.0, "range_high": 8.0},
    {"parameter": "Cell capacity vs temperature curve", "value": "1.00 at 20 C to 0.35 at -60 C",
     "category": "D", "basis": "Shape typical of Li-ion; NOT from a datasheet we hold",
     "impact": "Sets how much of the pack is usable when cold.",
     "range_low": 0.25, "range_high": 0.45},
    {"parameter": "Payload self-heating fraction", "value": "0.60 of electrical load",
     "category": "D", "basis": "Engineering estimate of electronics-to-heat",
     "impact": "Warms the box; a conservative 0.0 turns cold margins pessimistic.",
     "range_low": 0.0, "range_high": 0.9},
    {"parameter": "Thermostat hysteresis", "value": "1.5 K",
     "category": "D", "basis": "Typical for a simple controller",
     "impact": "Small effect on total heater energy.",
     "range_low": 0.5, "range_high": 3.0},
]


def assumed_parameters():
    return [dict(p) for p in ASSUMED_PARAMETERS]


def assumptions_result():
    return _result(
        "D1", "Parameters that are assumed rather than verified", "D",
        {"count": len(ASSUMED_PARAMETERS)},
        "No external source was measured or tested. Each entry records where the "
        "value came from and which part of the result it moves.",
        [{"parameter": p["parameter"], "value": p["value"],
          "basis": p["basis"], "impact": p["impact"],
          "exploratory_range_low": p["range_low"],
          "exploratory_range_high": p["range_high"]}
         for p in ASSUMED_PARAMETERS],
        [
            "The ranges shown are exploratory, chosen to bound engineering "
            "plausibility. They are NOT confidence intervals and are NOT derived "
            "from measurement.",
            "Task 6 propagates the three highest-impact parameters and reports how "
            "the design ranking responds.",
        ],
        "Inventory of constants with their basis and sensitivity.",
    )


# ===========================================================================
def run_all_benchmarks():
    return [
        bench_A1_decay(),
        bench_A2_radiation(),
        bench_A3_equilibrium(),
        bench_A4_limits(),
        bench_B1_isa(),
        assumptions_result(),
    ]


def summary(results):
    a_pass = sum(1 for r in results if r["category"] == "A")
    b_pass = sum(1 for r in results if r["category"] == "B")
    n_items = sum(len(r["items"]) for r in results)
    fails = []
    for r in results:
        for it in r["items"]:
            if isinstance(it.get("pass"), bool) and not it["pass"]:
                fails.append((r["id"], it.get("check", "")))
    return {
        "benchmarks": len(results),
        "analytical": a_pass,
        "reference": b_pass,
        "checks": n_items,
        "failed_checks": fails,
        "category_e_count": 0,
        "note": CATEGORY_E_NOTE,
    }
