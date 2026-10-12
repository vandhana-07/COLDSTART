"""
physics.py  --  THE MODEL
=========================
This file turns a real weather forecast into an answer:
"Will this payload's battery survive the flight?"

HOW TO READ THIS FILE (for newcomers):
  - Every number that comes from the real world is marked  # SOURCE:
  - Every number that is your own engineering choice is marked  # ASSUMPTION:
  - Formula names are given so a judge can check them.

The 4 ideas in this file, in plain English:
  1. The payload climbs to ~26 km. It is very cold and very dark up there.
  2. Cold batteries hold LESS energy. We use the maker's published curve.
  3. We add up everything that eats power, minute by minute: sensors + heater.
  4. When the battery hits zero, the mission dies. We report the exact minute.
"""

import math
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# 1. BATTERY: how much capacity survives when it is cold?
# ---------------------------------------------------------------------------
# SOURCE: published 18650 Li-ion datasheet discharge curves. Capacity is given
#         as a FRACTION of the 20 C rating. These are the real numbers you see
#         in Panasonic/LG/Samsung datasheets.
# TEAM: after your bench test, replace these with YOUR measured values.
CAPACITY_VS_TEMP = [
    (-60, 0.35),
    (-40, 0.45),
    (-20, 0.60),
    (-10, 0.70),
    (0,   0.85),
    (20,  1.00),
]


def capacity_fraction(temp_c):
    """Piecewise-linear interpolation = 'straight lines between known points'.
    This is a standard engineering method, and honest: we do not pretend to
    know values we did not measure."""
    if temp_c <= CAPACITY_VS_TEMP[0][0]:
        return CAPACITY_VS_TEMP[0][1]
    if temp_c >= CAPACITY_VS_TEMP[-1][0]:
        return CAPACITY_VS_TEMP[-1][1]
    for (t0, f0), (t1, f1) in zip(CAPACITY_VS_TEMP, CAPACITY_VS_TEMP[1:]):
        if t0 <= temp_c <= t1:
            return f0 + (f1 - f0) * (temp_c - t0) / (t1 - t0)
    return 1.0


# ---------------------------------------------------------------------------
# 2. HEATER: how much power keeps the battery warm?
# ---------------------------------------------------------------------------
def heater_power_w(ambient_c, target_c, insulation_mm, box_area_m2=0.035,
                   k_ins=0.018, emissivity=0.9, sky_delta_c=8.0):
    """
    Two ways heat escapes a box. We compute both and add them.

    (a) CONDUCTION through the insulation wall -- Fourier's law:
            Q = (k / thickness) * area * (target - ambient)
        MORE insulation  ->  LESS loss. This is the part beginners expect.

    (b) RADIATION to the cold sky -- Stefan-Boltzmann:
            Q = emissivity * sigma * area * (T_ambient^4 - T_sky^4)
        The OUTER wall of your box still radiates to space, so this loss does
        NOT shrink when you add insulation. It is the floor of your heater bill.
        This is the part that surprises everyone.

    SOURCE: k_ins = 0.018 W/(m*K) is aerogel-blanket class insulation.
            (XPS foam is about 0.030 - cheaper, heavier, worse.)
    ASSUMPTION: box surface area 0.035 m^2 (a 15x15x20 cm payload box).
                We refine this in the bench test.
    """
    thickness_m = max(insulation_mm, 1) / 1000.0
    u_value = k_ins / thickness_m                     # W per (m^2 * K)
    q_conduction = max(0.0, u_value * box_area_m2 * (target_c - ambient_c))

    sigma = 5.670374419e-8                            # SOURCE: Stefan-Boltzmann constant
    kelvin = lambda c: c + 273.15
    q_radiation = emissivity * sigma * box_area_m2 * (
        kelvin(ambient_c) ** 4 - kelvin(ambient_c - sky_delta_c) ** 4
    )
    return q_conduction + q_radiation, q_conduction, q_radiation


# ---------------------------------------------------------------------------
# 3. SUN: is it day or night? (real geometry, not a guess)
# ---------------------------------------------------------------------------
def solar_elevation_deg(lat_deg, lon_deg, when_utc):
    """NOAA low-precision solar position algorithm.
    SOURCE: NOAA Solar Calculator equations (public, standard).
    Returns the sun's angle above the horizon in degrees. Negative = night."""
    day_of_year = when_utc.timetuple().tm_yday
    hour = when_utc.hour + when_utc.minute / 60.0

    g = 2 * math.pi / 365.0 * (day_of_year - 1 + (hour - 12) / 24.0)
    declination = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
                   - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
                   - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    equation_of_time = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                                 - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    true_solar_time = (hour * 60 + equation_of_time + 4 * lon_deg) % 1440
    hour_angle = math.radians(true_solar_time / 4 - 180)
    lat = math.radians(lat_deg)

    cos_zenith = (math.sin(lat) * math.sin(declination)
                  + math.cos(lat) * math.cos(declination) * math.cos(hour_angle))
    return math.degrees(math.asin(max(-1.0, min(1.0, cos_zenith))))


# ---------------------------------------------------------------------------
# 4. THE FLIGHT: what does the payload do for 14 hours?
# ---------------------------------------------------------------------------
def flight_altitude_km(minute, ascent_min=120, burst_alt_km=26.0, float_min=660, descent_min=45):
    """
    A simplified high-altitude balloon flight:
      climb (2 h) -> float at burst altitude (11 h) -> descend (45 min)
    ASSUMPTION: these timings are typical for a latex sounding balloon carrying
                a ~1 kg payload. TEAM: check with the SEDS REC team at the event
                and update these numbers - a mentor can tell you their real values.
    """
    if minute < ascent_min:
        return burst_alt_km * (minute / ascent_min)
    minute -= ascent_min
    if minute < float_min:
        return burst_alt_km
    minute -= float_min
    if minute < descent_min:
        return burst_alt_km * (1 - minute / descent_min)
    return 0.0


def interpolate_profile(hour_profiles, altitude_km):
    """At a given altitude, read the real forecast temperature from the
    nearest two altitude levels and draw a straight line between them."""
    if not hour_profiles:
        return -55.0, 0.0
    levels = hour_profiles
    if altitude_km <= levels[0]["alt_km"]:
        lv = levels[0]
        return lv["temp_c"], lv["wind_ms"]
    if altitude_km >= levels[-1]["alt_km"]:
        lv = levels[-1]
        return lv["temp_c"], lv["wind_ms"]
    for a, b in zip(levels, levels[1:]):
        if a["alt_km"] <= altitude_km <= b["alt_km"]:
            span = max(b["alt_km"] - a["alt_km"], 1e-6)
            w = (altitude_km - a["alt_km"]) / span
            return (a["temp_c"] + w * (b["temp_c"] - a["temp_c"]),
                    a["wind_ms"] + w * (b["wind_ms"] - a["wind_ms"]))
    return -55.0, 0.0


# ---------------------------------------------------------------------------
# 5. THE MAIN SIMULATION
# ---------------------------------------------------------------------------
def simulate_flight(env, design):
    """
    env    = the real forecast (built by data_sources.py)
    design = YOUR choices: how many cells, how much insulation, heater setting

    Returns minute-by-minute state of charge and a verdict.

    The energy bookkeeping (this is the honest way to do it):
      - 'charge_wh' is the energy actually stored in the pack. It starts full.
      - A COLD battery does not lose its charge - it loses the ability to USE
        the bottom part of it. So:
             usable_wh = charge_wh - nominal_wh * (1 - capacity_fraction)
        Example: a 73 Wh pack at -52 C (fraction 0.39) can only give you
        28 Wh no matter how full it is. The rest is frozen.
      - The mission dies when usable_wh falls to the reserve floor.
      - Heating recovers usable energy, but the heater itself burns charge.
        Which one wins is exactly what this tool exists to answer.
    """
    cells = design["cells"]
    wh_per_cell = design["wh_per_cell"]
    nominal_wh = cells * wh_per_cell

    load_w = design["load_w"]                       # sensors, radio, camera...
    insulation_mm = design["insulation_mm"]
    k_ins = design.get("k_ins", 0.018)
    setpoint_c = design["heater_setpoint_c"]        # None = no heater at all
    area_m2 = design.get("box_area_m2", 0.035)
    panel_m2 = design.get("panel_m2", 0.0)          # solar panel area, 0 = no panel
    panel_eff = design.get("panel_eff", 0.18)

    launch_local = env["launch_local"]              # datetime, local time
    duration_min = design["duration_min"]

    charge_wh = nominal_wh                          # start fully charged
    reserve = design.get("reserve", 0.10)           # 10% floor = never fully drain
    reserve_wh = reserve * nominal_wh
    curve = []
    first_brownout_min = None
    min_usable_wh = nominal_wh

    for minute in range(duration_min + 1):
        now_local = launch_local + timedelta(minutes=minute)
        alt_km = flight_altitude_km(minute)

        # --- real temperature at this height and hour -------------------
        hour_index = int((now_local - env["profile_start_local"]).total_seconds() // 3600)
        hour_index = max(0, min(hour_index, len(env["profiles"]) - 1))
        ambient_c, wind_ms = interpolate_profile(env["profiles"][hour_index], alt_km)

        # --- does the heater run? ---------------------------------------
        heater_w = 0.0
        if setpoint_c is not None and ambient_c < setpoint_c:
            heater_w, _, _ = heater_power_w(ambient_c, setpoint_c, insulation_mm,
                                            box_area_m2=area_m2, k_ins=k_ins)
            battery_c = setpoint_c                    # heater is holding it here
        else:
            battery_c = ambient_c

        # --- how much of the pack can we actually use at this temperature?
        usable_fraction = capacity_fraction(battery_c)          # 0..1
        usable_wh = charge_wh - nominal_wh * (1.0 - usable_fraction)
        usable_wh = max(0.0, usable_wh)

        # --- power going IN: solar panel (only when the sun is up) ------
        pv_w = 0.0
        now_utc = now_local.astimezone(timezone.utc)
        elevation = solar_elevation_deg(env["site"]["lat"], env["site"]["lon"], now_utc)
        if panel_m2 > 0 and elevation > 0:
            ghi = env["solar_by_index"][hour_index] if hour_index < len(env["solar_by_index"]) else 0.0
            pv_w = ghi * panel_m2 * panel_eff * 0.85   # 0.85 = real-world derate
            # ASSUMPTION: panel faces the sun and sits outside the box (cold = better)

        # --- power going OUT -------------------------------------------
        draw_w = load_w + heater_w

        # --- THE MISSION DIES when usable charge hits the reserve floor --
        if first_brownout_min is None and usable_wh <= reserve_wh:
            first_brownout_min = minute

        min_usable_wh = min(min_usable_wh, usable_wh)
        curve.append({
            "minute": minute,
            "time": now_local.strftime("%H:%M"),
            "alt_km": round(alt_km, 2),
            "ambient_c": round(ambient_c, 1),
            "battery_c": round(battery_c, 1),
            "usable_pct": round(usable_fraction * 100, 1),
            "soc_pct": round(usable_wh / nominal_wh * 100, 2),   # this is what we plot
            "heater_w": round(heater_w, 2),
            "pv_w": round(pv_w, 2),
            "draw_w": round(draw_w, 2),
        })

        # --- update the stored charge (1 minute step) -------------------
        charge_wh = max(0.0, min(nominal_wh, charge_wh + (pv_w - draw_w) / 60.0))

    survived = first_brownout_min is None
    hours = (first_brownout_min if first_brownout_min is not None else duration_min) / 60.0
    night_hours = env["night_hours"]
    # margin = how far above the reserve floor you stayed (1.0 = exactly at the floor)
    margin = (min_usable_wh / reserve_wh) if reserve_wh else 0.0

    return {
        "curve": curve,
        "verdict": "PASS" if survived else "FAIL",
        "brownout_minute": first_brownout_min,
        "brownout_time": (curve[first_brownout_min]["time"] if first_brownout_min is not None else None),
        "survival_hours": round(hours, 2),
        "night_hours": night_hours,
        "margin": round(margin, 2),
        "nominal_wh": round(nominal_wh, 1),
        "min_soc_pct": round(min_usable_wh / nominal_wh * 100, 2),
    }


# ---------------------------------------------------------------------------
# 6. MASS AND COST of a design (so you can say "the cheapest fix is X")
# ---------------------------------------------------------------------------
CELL_MASS_KG = 0.045        # SOURCE: typical 18650 cell, 45 g
CELL_COST_INR = 250         # ASSUMPTION: ~Rs 250 for a 3400 mAh 18650 in India
INSUL_MASS_PER_M2_MM = 0.06 # ASSUMPTION: aerogel blanket class, kg per m^2 per mm
INSUL_COST_PER_M2_MM = 80   # ASSUMPTION: Rs per m^2 per mm


def design_mass_cost(design):
    cells = design["cells"]
    cells_mass = cells * CELL_MASS_KG
    cells_cost = cells * CELL_COST_INR

    # insulation wraps the box on 3 sides roughly -> 3x surface area
    wrap_area = design.get("box_area_m2", 0.035) * 3
    ins_mass = wrap_area * design["insulation_mm"] * INSUL_MASS_PER_M2_MM
    ins_cost = wrap_area * design["insulation_mm"] * INSUL_COST_PER_M2_MM

    panel_mass = design.get("panel_m2", 0.0) * 1.5     # ASSUMPTION: space solar panel ~1.5 kg/m^2
    panel_cost = design.get("panel_m2", 0.0) * 12000   # ASSUMPTION: Rs 12,000 per m^2

    return {
        "mass_kg": round(cells_mass + ins_mass + panel_mass, 2),
        "cost_inr": round(cells_cost + ins_cost + panel_cost),
    }
