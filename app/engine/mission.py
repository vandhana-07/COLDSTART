"""
mission.py -- THE FLIGHT DIGITAL TWIN.
=======================================
A minute-by-minute virtual flight of the payload, integrating the coupled
thermal + electrical system and reporting exactly what happened and why.

WHAT IT SOLVES AT EACH TIMESTEP
-------------------------------
  1. Where is the payload?              -> altitude profile
  2. What is the air temperature there? -> real forecast profile, ISA fallback
  3. Is the heater on?                  -> thermostat with hysteresis
  4. How does the box temperature move? -> lumped capacitance ODE (thermal.py)
  5. How much charge is left?           -> battery.py energy accounting
  6. Can the pack actually supply it?   -> C-rate check
  7. Has anything been violated?        -> first-violation failure detection

TIMESTEP SELECTION
------------------
Forward Euler is stable for `dt < 2 * C_th / UA`. Rather than trusting a fixed
number, the engine DERIVES dt from the acoustic... from the THERMAL time constant
of the specific design being simulated. Slow, highly-insulated designs get a
larger step; fast, poorly-insulated ones get a finer step. Numerical stability is
then a property of the code, not a hope. Convergence is verified in
tests/test_thermal.py by halving dt and comparing survival times.
"""

import math
from datetime import timedelta, timezone

from . import atmosphere as atm
from . import battery as bat
from . import params as P
from . import thermal as th

# ---------------------------------------------------------------------------
# FAILURE REASONS  (audit finding A7: previously only "energy depleted" existed)
# ---------------------------------------------------------------------------
ENERGY_DEPLETED = "ENERGY_DEPLETED"
TEMP_BELOW_OPERATING = "TEMP_BELOW_OPERATING"
TEMP_ABOVE_OPERATING = "TEMP_ABOVE_OPERATING"
POWER_EXCEEDS_CAPABILITY = "POWER_EXCEEDS_CAPABILITY"
NONE = None

FAILURE_TEXT = {
    ENERGY_DEPLETED: "Usable stored energy fell to the reserve floor.",
    TEMP_BELOW_OPERATING: ("Cell temperature fell below the permitted discharge "
                           "limit, so the pack can no longer supply power."),
    TEMP_ABOVE_OPERATING: ("Cell temperature rose above the permitted maximum. "
                           "Insulation that is good for a cold night can trap heat."),
    POWER_EXCEEDS_CAPABILITY: ("Required discharge power exceeded the pack's "
                               "C-rate capability; voltage would collapse."),
}


# ---------------------------------------------------------------------------
# MISSION PROFILE
# ---------------------------------------------------------------------------
def altitude_km(minute, ascent_min=P.ASCENT_MIN, burst_alt_km=P.BURST_ALT_KM,
                float_min=P.FLOAT_MIN, descent_min=P.DESCENT_MIN):
    """Altitude of the payload at a given mission minute.

    ASSUMPTION: constant-rate ascent, level float, constant-rate descent. A real
    latex balloon accelerates early then decelerates as the envelope stretches;
    the linear segment is a documented simplification and does not affect the
    physics under test (which is driven by altitude, not by rate of climb).
    """
    if minute < 0:
        return 0.0
    if minute < ascent_min:
        return burst_alt_km * (minute / ascent_min)
    m = minute - ascent_min
    if m < float_min:
        return burst_alt_km
    m -= float_min
    if m < descent_min:
        return burst_alt_km * (1.0 - m / descent_min)
    return 0.0


def sample_profile(levels, alt_km):
    """Temperature at a given altitude, from the forecast profile.

    Returns (temp_c, wind_ms, used_isa_flag).

    LEVELS ARE THE REAL FORECAST. If altitude sits between two forecast levels we
    interpolate linearly. If it is ABOVE the highest forecast level (the GFS
    ceiling is around 31 km) we fall back to the ISA standard atmosphere and RAISE
    A FLAG, so the report can state exactly how much of the flight relied on
    fallback rather than on real data.
    """
    if not levels:
        return atm.isa_temperature_c(alt_km), 0.0, True

    if alt_km <= levels[0]["alt_km"]:
        lv = levels[0]
        return lv["temp_c"], lv["wind_ms"], False
    if alt_km >= levels[-1]["alt_km"]:
        # Real data has run out at the top. Fall back, and say so.
        return atm.isa_temperature_c(alt_km), levels[-1]["wind_ms"], True

    for a, b in zip(levels, levels[1:]):
        if a["alt_km"] <= alt_km <= b["alt_km"]:
            span = max(b["alt_km"] - a["alt_km"], 1e-9)
            w = (alt_km - a["alt_km"]) / span
            return (a["temp_c"] + w * (b["temp_c"] - a["temp_c"]),
                    a["wind_ms"] + w * (b["wind_ms"] - a["wind_ms"]),
                    False)
    return atm.isa_temperature_c(alt_km), 0.0, True


def choose_timestep_s(design):
    """Pick a stable, accurate integration step for THIS design.

    Rule: resolve the thermal time constant with at least 30 steps, and never
    exceed 30 s (so the thermostat's on/off behaviour is also well resolved).
    Floor of 1 s guards against a pathological near-zero thermal mass.
    """
    tau = th.thermal_time_constant_s(
        design["cells"], design["insulation_mm"], design["box_area_m2"],
        design["k_ins"], altitude_km=design.get("burst_alt_km", P.BURST_ALT_KM),
        ambient_c=-52.0,
        emissivity=design.get("emissivity", P.DEFAULT_EMISSIVITY),
        radiant_offset_c=design.get("radiant_offset_c", P.DEFAULT_RADIANT_OFFSET_C))
    return max(1.0, min(30.0, tau / 30.0))


# ---------------------------------------------------------------------------
# THE SIMULATION
# ---------------------------------------------------------------------------
def simulate(env, design, dt_override=None):
    """Run the full flight. Returns a result dict with a timeline and a verdict.

    dt_override forces a specific timestep in seconds. This exists so the
    convergence study (app/verify.py, Task 4) can compare the SAME scenario at
    60/30/10/5 s. It is not used by the app, which always lets the engine derive
    a stable step from the design's own time constant.
    """
    d = _with_defaults(design)
    # `is not None`, not truthiness: dt_override=0.0 must be rejected, not
    # silently replaced by the automatic step.
    dt = float(dt_override) if dt_override is not None else choose_timestep_s(d)
    if dt <= 0:
        raise ValueError("dt_override must be positive")

    # capacity_mult models the possibility that the real cells store less than the
    # datasheet figure (ageing, cold-soak history, cell-to-cell spread). It is a
    # STRESS-TEST input, not a claim about our cells.
    nominal = bat.nominal_wh(d["cells"], d["wh_per_cell"]) * d.get("capacity_mult", 1.0)
    reserve_wh = d["reserve"] * nominal

    c_th = th.thermal_capacity_j_per_k(d["cells"], d["insulation_mm"], d["box_area_m2"])
    # NOTE: self-heating is computed INSIDE the loop from the power actually
    # delivered to the payload, never from the commanded load. See audit A11.

    duration_min = d["duration_min"]
    total_s = duration_min * 60.0
    n_steps = int(math.ceil(total_s / dt))

    launch_local = env["launch_local"]
    lat, lon = env["site"]["lat"], env["site"]["lon"]
    profile_start = env["profile_start_local"]

    # --- initial condition: the payload sits on the ground before launch -----
    t_box = env["profiles"][0][0]["temp_c"] if env["profiles"][0] else 30.0
    t0_c = t_box
    charge = nominal
    heater_on = False

    timeline = []
    events = []
    failure_reason = None
    failure_minute = None
    failure_detail = {}
    isa_minutes = 0
    charge_rejected_wh = 0.0
    pv_generated_wh = 0.0
    heater_energy_wh = 0.0
    # Energy-accounting accumulators (audit A10-A12). Accumulated in the loop
    # from the SAME quantities used in the integration, so the balance closes by
    # construction rather than by a later reconstruction.
    payload_energy_wh = 0.0        # electrical energy delivered to the payload
    heat_lost_j = 0.0              # payload -> environment, always >= 0
    heat_gained_j = 0.0            # environment -> payload, always >= 0
    thermal_in_j = 0.0             # heater + payload self-heating, in joules
    unmet_demand_wh = 0.0          # demand the pack could not supply (C-rate cap)
    unmet_energy_wh = 0.0          # demand the pack could not supply (empty pack)
    clamp_activations = 0          # times the -120/+80 C sanity clamp engaged
    min_box_c = t_box
    max_box_c = t_box
    min_usable_pct = 100.0
    next_record_s = 0.0

    for step in range(n_steps + 1):
        elapsed_s = step * dt
        minute = elapsed_s / 60.0
        now_local = launch_local + timedelta(seconds=elapsed_s)
        alt = altitude_km(minute, d["ascent_min"], d["burst_alt_km"],
                          d["float_min"], d["descent_min"])

        # ---- environment at this time and height --------------------------
        hour_index = int((now_local - profile_start).total_seconds() // 3600)
        hour_index = max(0, min(hour_index, len(env["profiles"]) - 1))
        t_amb, wind_ms, used_isa = sample_profile(env["profiles"][hour_index], alt)
        if used_isa:
            isa_minutes += dt / 60.0

        # ---- thermostat (hysteresis, and a RATED heater) ------------------
        setpoint = d["heater_setpoint_c"]
        if setpoint is None:
            heater_w = 0.0
            heater_on = False
        else:
            if heater_on and t_box >= setpoint:
                heater_on = False
            elif (not heater_on) and t_box < setpoint - P.THERMOSTAT_HYSTERESIS_C:
                heater_on = True
            heater_w = d["heater_max_w"] if heater_on else 0.0

        # ---- solar generation --------------------------------------------
        now_utc = now_local.astimezone(timezone.utc)
        elevation = atm.solar_elevation_deg(lat, lon, now_utc)
        # Clear-sky physical model (audit A1: never surface GHI at altitude).
        # solar_derate then removes a fraction for cloud, dirt, panel angle and
        # shading -- a STRESS input, defaulting to 1.0 = ideal.
        pv_w = atm.panel_power_w(alt, elevation, now_utc.timetuple().tm_yday,
                                 d["panel_m2"], d["panel_efficiency"],
                                 d["panel_view_factor"]) * d.get("solar_derate", 1.0)

        # ---- electrical demand -------------------------------------------
        demand_w = d["payload_load_w"] + heater_w

        # C-rate capability check (audit finding A3)
        p_max = bat.max_discharge_power_w(d["cells"], t_box, c_rate_max=d["c_rate_max"])
        power_limited = demand_w > p_max and charge > 0.0
        effective_demand_w = min(demand_w, p_max) if power_limited else demand_w

        # ---- what the pack ACTUALLY delivers ------------------------------
        # The pack cannot exceed its C-rate capability. The payload has
        # priority; the heater receives whatever is left. Booking energy at the
        # COMMANDED value would count energy the pack never supplied and would
        # generate self-heating from nothing (audit findings A10 and A11).
        delivered_payload_w = min(d["payload_load_w"], effective_demand_w)
        delivered_heater_w = max(0.0, effective_demand_w - delivered_payload_w)
        payload_heat_w = delivered_payload_w * P.PAYLOAD_HEAT_FRACTION
        unmet_demand_wh += (demand_w - effective_demand_w) * dt / P.SECONDS_PER_HOUR

        # ---- usable energy (audit finding A4: charge inhibited when cold) --
        usable = bat.usable_wh(charge, nominal, t_box)
        below_operating = t_box < d["min_operating_c"]
        above_operating = t_box > d["max_operating_c"]

        # ---- failure detection: FIRST violation wins ----------------------
        if failure_reason is None:
            if below_operating:
                failure_reason = TEMP_BELOW_OPERATING
                failure_minute = minute
                failure_detail = {
                    "temperature_c": round(t_box, 1),
                    "limit_c": d["min_operating_c"],
                    "ambient_c": round(t_amb, 1),
                    "altitude_km": round(alt, 2),
                    "heater_was_on": heater_on,
                }
            elif above_operating:
                failure_reason = TEMP_ABOVE_OPERATING
                failure_minute = minute
                failure_detail = {
                    "temperature_c": round(t_box, 1),
                    "limit_c": d["max_operating_c"],
                    "ambient_c": round(t_amb, 1),
                    "altitude_km": round(alt, 2),
                    "heater_was_on": heater_on,
                    "self_heat_w": round(payload_heat_w, 2),
                }
            elif usable <= reserve_wh:
                failure_reason = ENERGY_DEPLETED
                failure_minute = minute
                failure_detail = {
                    "usable_wh": round(usable, 2),
                    "reserve_wh": round(reserve_wh, 2),
                    "charge_rejected_wh": round(charge_rejected_wh, 2),
                    "heater_energy_wh": round(heater_energy_wh, 2),
                }
            elif power_limited and demand_w > p_max * 1.0:
                failure_reason = POWER_EXCEEDS_CAPABILITY
                failure_minute = minute
                failure_detail = {
                    "demanded_w": round(demand_w, 2),
                    "capability_w": round(p_max, 2),
                    "temperature_c": round(t_box, 1),
                }

        # ---- integrate thermal node --------------------------------------
        t_box, q_loss_w = th.heat_balance_step(
            t_box, t_amb, alt, dt, c_th, delivered_heater_w, payload_heat_w,
            d["insulation_mm"], d["box_area_m2"], d["k_ins"],
            d["emissivity"], d["radiant_offset_c"])
        t_unclamped = t_box
        t_box = max(-120.0, min(80.0, t_box))       # physical sanity clamp
        if t_box != t_unclamped:
            clamp_activations += 1

        # Thermal bookkeeping uses the SAME q that drove the step above, so the
        # balance cannot drift from the physics.
        if q_loss_w >= 0.0:
            heat_lost_j += q_loss_w * dt
        else:
            heat_gained_j += -q_loss_w * dt
        thermal_in_j += (delivered_heater_w + payload_heat_w) * dt

        # ---- integrate charge --------------------------------------------
        battery_out_w = effective_demand_w
        charge_before = charge
        charge, accepted_w, rejected_w = bat.step_charge(
            charge, nominal, dt, battery_out_w, pv_w, t_box,
            charge_efficiency=d["charge_efficiency"],
            charge_min_c=d["charge_min_c"],
            max_charge_power_w=d["max_charge_power_w"])
        # If the pack was clamped at empty, the demand it could not meet is a
        # real energy shortfall and must be counted, not silently absorbed.
        expected_drop = (battery_out_w - accepted_w * d["charge_efficiency"]) \
            * dt / P.SECONDS_PER_HOUR
        if charge <= 0.0 and expected_drop > charge_before:
            unmet_energy_wh += expected_drop - charge_before
        charge_rejected_wh += rejected_w * dt / P.SECONDS_PER_HOUR
        pv_generated_wh += accepted_w * dt / P.SECONDS_PER_HOUR
        # A10: the heater is booked at the power it was DELIVERED, not at the
        # power the thermostat asked for.
        heater_energy_wh += delivered_heater_w * dt / P.SECONDS_PER_HOUR
        payload_energy_wh += delivered_payload_w * dt / P.SECONDS_PER_HOUR

        usable = bat.usable_wh(charge, nominal, t_box)
        min_box_c = min(min_box_c, t_box)
        max_box_c = max(max_box_c, t_box)
        min_usable_pct = min(min_usable_pct, 100.0 * usable / nominal)

        # ---- record the timeline at 1-minute resolution -------------------
        if elapsed_s >= next_record_s:
            timeline.append({
                "minute": round(minute, 2),
                "time": now_local.strftime("%H:%M"),
                "alt_km": round(alt, 2),
                "ambient_c": round(t_amb, 1),
                "box_c": round(t_box, 1),
                "usable_pct": round(max(0.0, 100.0 * usable / nominal), 2),
                "charge_pct": round(max(0.0, 100.0 * charge / nominal), 2),
                "capacity_frac": round(bat.capacity_fraction(t_box), 3),
                "heater_w": round(delivered_heater_w, 2),
                "heater_commanded_w": round(heater_w, 2),
                "pv_w": round(pv_w, 2),
                "demand_w": round(demand_w, 2),
                "power_limited": power_limited,
                "isa_fallback": used_isa,
            })
            next_record_s += 60.0

        # ---- the mission ENDS at first failure --------------------------
        # Continuing past the violation would model a dead payload still drawing
        # power and self-heating, which is unphysical. Freeze at the failure.
        if failure_reason is not None:
            break

        if elapsed_s >= total_s:
            break

    survived = failure_reason is None
    survival_hours = (failure_minute if failure_minute is not None else duration_min) / 60.0
    end_minute = failure_minute if failure_minute is not None else duration_min
    end_state = _state_at(timeline, end_minute)

    result = {
        "verdict": "PASS" if survived else "FAIL",
        "failure_reason": failure_reason,
        "failure_text": FAILURE_TEXT.get(failure_reason),
        "failure_minute": failure_minute,
        "failure_time": (launch_local + timedelta(minutes=failure_minute)).strftime("%H:%M")
                         if failure_minute is not None else None,
        "failure_detail": failure_detail,
        "survival_hours": round(survival_hours, 2),
        "night_hours": env.get("night_hours"),
        "nominal_wh": round(nominal, 2),
        "min_box_c": round(min_box_c, 1),
        "max_box_c": round(max_box_c, 1),
        # Unrounded, for the timestep-convergence study: the displayed value is
        # quantised to 0.1 C, which is coarser than the integrator's own error and
        # would mask the order of convergence (app/verify.py, Task 4).
        "min_box_c_raw": min_box_c,
        "max_box_c_raw": max_box_c,
        "final_box_c_raw": t_box,
        "min_usable_pct": round(min_usable_pct, 2),
        "reserve_wh": round(reserve_wh, 2),
        "energy_margin_wh": round((end_state.get("usable_pct", 0) / 100.0) * nominal - reserve_wh, 2),
        "energy_margin_ratio": round(max(0.0, end_state.get("usable_pct", 0) / 100.0 * nominal) / reserve_wh, 2)
                               if reserve_wh > 0 else None,
        "heater_energy_wh": round(heater_energy_wh, 2),
        "pv_generated_wh": round(pv_generated_wh, 2),
        "charge_rejected_wh": round(charge_rejected_wh, 2),
        "heat_lost_wh": round(heat_lost_j / P.SECONDS_PER_HOUR, 3),
        "heat_gained_wh": round(heat_gained_j / P.SECONDS_PER_HOUR, 3),
        "payload_energy_wh": round(payload_energy_wh, 3),
        "unmet_demand_wh": round(unmet_demand_wh, 3),
        "unmet_energy_wh": round(unmet_energy_wh, 3),
        "clamp_activations": clamp_activations,
        "energy_balance": _energy_balance(
            nominal, charge, pv_generated_wh, charge_rejected_wh,
            payload_energy_wh, heater_energy_wh, unmet_energy_wh,
            d["charge_efficiency"], c_th, t0_c, t_box,
            thermal_in_j, heat_lost_j, heat_gained_j),
        "final_charge_wh": round(charge, 3),
        "isa_fallback_minutes": round(isa_minutes, 1),
        "isa_fallback_pct": round(100.0 * isa_minutes / max(duration_min, 1e-9), 1),
        "timestep_s": dt,
        "timeline": timeline,
        "thermal_time_constant_min": round(
            th.thermal_time_constant_s(d["cells"], d["insulation_mm"], d["box_area_m2"],
                                       d["k_ins"], altitude_km=d["burst_alt_km"],
                                       ambient_c=min_box_c,
                                       emissivity=d["emissivity"],
                                       radiant_offset_c=d["radiant_offset_c"]) / 60.0, 1),
        "effective_ua_w_per_k": round(
            th.effective_ua(d["insulation_mm"], d["box_area_m2"], d["k_ins"],
                            altitude_km=d["burst_alt_km"], ambient_c=min_box_c,
                            emissivity=d["emissivity"],
                            radiant_offset_c=d["radiant_offset_c"]), 4),
        "design": d,
        "events": events,
    }
    result["failure_explanation"] = explain_failure(result, env)
    return result


def _with_defaults(design):
    """Fill every optional field with the documented default from params.py."""
    d = dict(design)
    d.setdefault("wh_per_cell", P.CELL_WH)
    d.setdefault("k_ins", P.DEFAULT_K_INSULATION)
    d.setdefault("insulation_material", "xps")
    d.setdefault("box_area_m2", P.DEFAULT_BOX_AREA_M2)
    d.setdefault("heater_max_w", P.DEFAULT_HEATER_MAX_W)
    d.setdefault("payload_load_w", 3.0)
    d.setdefault("panel_m2", 0.0)
    d.setdefault("panel_efficiency", P.PANEL_EFFICIENCY)
    d.setdefault("panel_view_factor", P.DEFAULT_PANEL_VIEW_FACTOR)
    d.setdefault("reserve", P.DEFAULT_RESERVE_FRACTION)
    d.setdefault("capacity_mult", 1.0)
    d.setdefault("solar_derate", 1.0)
    d.setdefault("min_operating_c", P.DEFAULT_MIN_OPERATING_C)
    d.setdefault("max_operating_c", P.DEFAULT_MAX_OPERATING_C)
    d.setdefault("charge_min_c", P.CHARGE_MIN_TEMP_C)
    d.setdefault("charge_efficiency", P.CHARGE_EFFICIENCY)
    d.setdefault("max_charge_power_w", None)
    d.setdefault("emissivity", P.DEFAULT_EMISSIVITY)
    d.setdefault("radiant_offset_c", P.DEFAULT_RADIANT_OFFSET_C)
    d.setdefault("duration_min", P.DEFAULT_DURATION_MIN)
    d.setdefault("ascent_min", P.ASCENT_MIN)
    d.setdefault("burst_alt_km", P.BURST_ALT_KM)
    d.setdefault("float_min", P.FLOAT_MIN)
    d.setdefault("descent_min", P.DESCENT_MIN)
    d.setdefault("c_rate_max", P.C_RATE_MAX)
    return d


def _state_at(timeline, minute):
    best = timeline[0] if timeline else {}
    for row in timeline:
        if row["minute"] <= minute:
            best = row
        else:
            break
    return best


def _energy_balance(nominal_wh, final_charge_wh, pv_accepted_wh, rejected_wh,
                    payload_wh, heater_wh, unmet_energy_wh, charge_eff,
                    c_th, t0_c, t_final_c, thermal_in_j, heat_lost_j,
                    heat_gained_j):
    """Explicit energy-balance residuals, in Wh. Sign convention below.

    ELECTRICAL
        storage(t)   : nominal at t=0, final_charge at the end
        storage(t)   : nominal at t=0, final_charge at the end
        flows IN     : + pv_accepted_wh * charge_eff      (PV that reached the cells)
        flows OUT    : - payload_wh - heater_wh           (delivered to loads)
        shortfall    : + unmet_energy_wh                  (demand never supplied)
        residual     : (nominal - final) + pv_in - out + shortfall

    A well-posed integrator gives residual -> 0. A non-zero residual means energy
    has been created, destroyed or double-counted somewhere.

    THERMAL   (sign: positive = energy entering the payload node)
        in           : + thermal_in_j  (heater + payload self-heating)
        out          : - heat_lost_j   (payload -> environment)
        in           : + heat_gained_j (environment -> payload)
        stored       : + C_th * (T_final - T_0)
        residual     : thermal_in_j - heat_lost_j + heat_gained_j
                       - C_th * (T_final - T_0)

    READ THIS BEFORE QUOTING THE THERMAL RESIDUAL.
    It is IDENTICALLY ZERO for forward Euler, because the scheme is
        C_th * (T_{n+1} - T_n) = (q_in - q_out(T_n)) * dt
    and summing that over the flight reproduces the accumulation term for term.
    It is therefore a BOOKKEEPING CONSISTENCY IDENTITY, not a measure of physical
    accuracy: it proves no term was dropped or double-counted between the
    integration and the accounting, and nothing more. It would catch a future
    edit that accumulates a different heat flow from the one used to step the
    temperature. It does NOT catch truncation error.

    Forward-Euler truncation error is real and is evaluated where it belongs:
    against the closed-form analytical solution in app/engine/verification.py
    (Task 1) and the timestep convergence study in app/verify.py (Task 4).
    """
    sec_h = P.SECONDS_PER_HOUR
    storage_drop_wh = nominal_wh - final_charge_wh
    pv_in_wh = pv_accepted_wh * charge_eff

    elec_residual = (storage_drop_wh + pv_in_wh + unmet_energy_wh
                     - payload_wh - heater_wh)

    thermal_in_wh = thermal_in_j / sec_h
    lost_wh = heat_lost_j / sec_h
    gained_wh = heat_gained_j / sec_h
    stored_wh = c_th * (t_final_c - t0_c) / sec_h

    thermal_residual = thermal_in_wh - lost_wh + gained_wh - stored_wh

    scale = max(abs(payload_wh) + abs(heater_wh) + abs(pv_in_wh), 1e-9)
    return {
        "electrical": {
            "nominal_wh": round(nominal_wh, 4),
            "final_charge_wh": round(final_charge_wh, 4),
            "storage_drop_wh": round(storage_drop_wh, 4),
            "pv_accepted_wh": round(pv_accepted_wh, 4),
            "pv_into_cells_wh": round(pv_in_wh, 4),
            "pv_rejected_wh": round(rejected_wh, 4),
            "payload_delivered_wh": round(payload_wh, 4),
            "heater_delivered_wh": round(heater_wh, 4),
            "unmet_energy_wh": round(unmet_energy_wh, 6),
            "residual_wh": round(elec_residual, 6),
            "residual_relative": round(elec_residual / scale, 9),
            "tolerance_wh": 1e-6,
            "pass": abs(elec_residual) <= 1e-6,
        },
        "thermal": {
            "heat_in_wh": round(thermal_in_wh, 4),
            "heat_lost_wh": round(lost_wh, 4),
            "heat_gained_wh": round(gained_wh, 4),
            "stored_change_wh": round(stored_wh, 4),
            "residual_wh": round(thermal_residual, 6),
            "identically_zero": True,
            "note": ("Bookkeeping consistency identity for forward Euler -- zero "
                     "by construction. It proves no term was dropped or "
                     "double-counted. It is NOT an accuracy measure; truncation "
                     "error is quantified separately in verification.py and "
                     "app/verify.py."),
        },
    }


def _heat_lost_wh(timeline, d, dt):
    """Total heat lost through the insulation over the flight (informational)."""
    total_j = 0.0
    for row in timeline:
        q = th.heat_loss_w(row["box_c"], row["ambient_c"], row["alt_km"],
                           d["insulation_mm"], d["box_area_m2"], d["k_ins"],
                           d["emissivity"], d["radiant_offset_c"])
        total_j += max(0.0, q) * 60.0
    return total_j / P.SECONDS_PER_HOUR


# ---------------------------------------------------------------------------
# EXPLAINABLE FAILURE REPLAY  (spec section 6)
# ---------------------------------------------------------------------------
def explain_failure(result, env=None):
    """Chronological explanation of WHY the design failed, derived from the trace.

    Deliberately does not assume cold is the cause -- it reads the timeline and
    the recorded violation, exactly as the spec requires.
    """
    if result["verdict"] == "PASS":
        return {"mechanism": None, "chronology": [],
                "headline": "No constraint was violated during the flight."}

    reason = result["failure_reason"]
    detail = result["failure_detail"] or {}
    tl = result["timeline"]
    fm = result["failure_minute"] or 0.0

    chronology = []
    window = [r for r in tl if fm - 25 <= r["minute"] <= fm + 1]

    if window:
        first = window[0]
        chronology.append(
            f"T+{first['minute']:.0f} min ({first['time']}) — payload at "
            f"{first['alt_km']:.1f} km. Box {first['box_c']:.1f} C, ambient "
            f"{first['ambient_c']:.1f} C, usable energy {first['usable_pct']:.1f}%.")

        coldest = min(window, key=lambda r: r["box_c"])
        chronology.append(
            f"T+{coldest['minute']:.0f} min — coldest point in the window: "
            f"{coldest['box_c']:.1f} C. Available capacity at that temperature is "
            f"{coldest['capacity_frac'] * 100:.0f}% of nominal.")

        heating = [r for r in window if r["heater_w"] > 0]
        if heating:
            avg_heater = sum(r["heater_w"] for r in heating) / len(heating)
            chronology.append(
                f"Heater drew an average of {avg_heater:.2f} W across {len(heating)} of "
                f"{len(window)} sampled minutes in this window.")
        else:
            chronology.append("Heater did not run in this window "
                              "(setpoint off, or the box stayed above setpoint).")

        if result["charge_rejected_wh"] > 0.5:
            chronology.append(
                f"{result['charge_rejected_wh']:.2f} Wh of solar generation was "
                f"REJECTED because the pack was below the 0 C charge limit. "
                f"Energy was available and could not be stored.")
    else:
        chronology.append("Timeline window unavailable for this failure.")

    chronology.append(
        f"T+{fm:.0f} min ({result['failure_time']}) — {FAILURE_TEXT[reason]}")

    # ---- contributing factors, read from the trace ----------------------
    factors = []
    if reason == ENERGY_DEPLETED:
        if result["heater_energy_wh"] > 0:
            share = result["heater_energy_wh"] / max(result["nominal_wh"], 1e-9) * 100
            factors.append(f"Heater consumed {result['heater_energy_wh']:.1f} Wh "
                           f"({share:.0f}% of nominal pack energy).")
        if result["min_box_c"] < -20:
            factors.append(f"Pack reached {result['min_box_c']:.1f} C, so only "
                           f"{bat.capacity_fraction(result['min_box_c']) * 100:.0f}% of "
                           f"capacity was ever accessible.")
        if result["charge_rejected_wh"] > 0.5:
            factors.append("Cold charge inhibition discarded solar energy that could "
                           "otherwise have extended runtime.")
        if detail.get("usable_wh") is not None:
            factors.append(f"Usable energy at failure: {detail['usable_wh']:.1f} Wh "
                           f"against a reserve of {detail['reserve_wh']:.1f} Wh.")

    elif reason == TEMP_BELOW_OPERATING:
        factors.append(f"Cell temperature {detail.get('temperature_c')} C fell below the "
                       f"limit of {detail.get('limit_c')} C.")
        if detail.get("heater_was_on") is False:
            factors.append("The heater was NOT running at the moment of failure — "
                           "the thermostat never brought it on.")
        elif detail.get("heater_was_on") is True:
            factors.append("The heater WAS running and was still insufficient to hold "
                           "temperature, so the heater rating is the binding constraint.")
        factors.append(f"Insulation thickness is {result['design']['insulation_mm']:.0f} mm; "
                       f"thermal time constant {result['thermal_time_constant_min']:.0f} min.")

    elif reason == TEMP_ABOVE_OPERATING:
        factors.append(f"Cell temperature {detail.get('temperature_c')} C rose above the "
                       f"limit of {detail.get('limit_c')} C.")
        if detail.get("self_heat_w"):
            factors.append(f"Payload electronics dissipate {detail['self_heat_w']} W as heat "
                           f"inside the box. At {result['design']['insulation_mm']:.0f} mm of "
                           f"insulation that heat cannot escape.")
        factors.append(f"Effective conductance is only "
                       f"{result['effective_ua_w_per_k']:.3f} W/K, so the box sheds heat "
                       f"very slowly.")

    elif reason == POWER_EXCEEDS_CAPABILITY:
        factors.append(f"Demand {detail.get('demanded_w')} W exceeded pack capability "
                       f"{detail.get('capability_w')} W at {detail.get('temperature_c')} C.")

    # ---- corrective suggestions, tied to the actual mechanism -----------
    suggestions = []
    if reason == TEMP_BELOW_OPERATING:
        if not detail.get("heater_was_on", False):
            suggestions.append({"change": "heater_setpoint_c", "to": -5,
                                "why": "Bring the thermostat on earlier so the heater "
                                       "acts before the cells drop past their limit."})
        suggestions.append({"change": "insulation_mm",
                            "to": min(75, result["design"]["insulation_mm"] + 25),
                            "why": "Thicker insulation raises the box temperature without "
                                   "spending any electrical energy."})
        suggestions.append({"change": "heater_max_w", "to": 10,
                            "why": "A stronger heater can hold setpoint when the "
                                   "temperature difference is at its worst."})
    elif reason == ENERGY_DEPLETED:
        suggestions.append({"change": "insulation_mm",
                            "to": min(75, result["design"]["insulation_mm"] + 25),
                            "why": "Reduces the standing heat load, which is the dominant "
                                   "drain over a long night."})
        suggestions.append({"change": "cells", "to": result["design"]["cells"] + 2,
                            "why": "More stored energy directly extends runtime."})
        if result["design"]["heater_setpoint_c"] is not None:
            suggestions.append({"change": "heater_setpoint_c", "to": -15,
                                "why": "A lower setpoint runs the heater less often, "
                                       "trading a little capacity for a lot of energy."})
    elif reason == TEMP_ABOVE_OPERATING:
        suggestions.append({"change": "insulation_mm",
                            "to": max(10, result["design"]["insulation_mm"] - 25),
                            "why": "Thinner insulation lets the self-generated heat escape. "
                                   "At cold ambient this is a real trade, not a mistake."})
        suggestions.append({"change": "payload_load_w",
                            "to": max(0.5, result["design"]["payload_load_w"] * 0.7),
                            "why": "Less electrical load means less heat dumped inside the box."})

    elif reason == POWER_EXCEEDS_CAPABILITY:
        suggestions.append({"change": "cells", "to": result["design"]["cells"] + 2,
                            "why": "More cells in parallel raise the current capability."})
        suggestions.append({"change": "heater_max_w", "to": 3,
                            "why": "Reduce peak heater demand so it fits inside the "
                                   "pack's capability."})

    return {
        "mechanism": reason,
        "headline": FAILURE_TEXT[reason],
        "chronology": chronology,
        "contributing_factors": factors,
        "suggested_changes": suggestions,
    }
