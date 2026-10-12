"""
thermal.py -- heat transfer and thermal mass.
=============================================
Fixes audit findings A2 (no thermal mass) and A8 (undocumented radiative constant),
plus a defect found during verification (A9, see audit addendum):

  A9: radiation was evaluated at the BATTERY temperature. For an insulated box
      the outer skin sits close to ambient, not close to the battery, so the
      radiative driving temperature difference was overstated by roughly 3x.

THE MODEL: single thermal node plus an algebraic skin temperature.
-----------------------------------------------------------------
Two stages, which is the minimum needed to get radiation right:

  Stage 1 - the payload interior (battery, electronics, structure) is one lumped
            mass at temperature T_box with heat capacity C_th.

  Stage 2 - the outer skin is treated as massless (its heat capacity is tiny
            compared to the pack) and is solved algebraically at every step.
            Heat reaches the skin by conduction through the insulation, and
            leaves it by radiation to the effective sky and by convection to the
            surrounding air. These are IN SERIES, not in parallel:

                T_box --[conduction k/t]--> T_skin --[radiation + convection]--> environment

  The series arrangement is the physically correct one and it matters a great
  deal: at float altitude with 10 mm of XPS foam it reduces the effective
  conductance from ~0.43 W/K (naive parallel) to ~0.13 W/K. Getting this wrong
  makes every design look 3x worse than it is.

  Skin equation, solved each step:
      UA_cond * (T_box - T_skin) = h_conv*A*(T_skin - T_amb)
                                 + eps*sigma*A*(T_skin^4 - T_rad^4)

CONVECTION AT ALTITUDE
  Sea-level natural-convection coefficients (~5 W/m2K) do not apply at 26 km,
  where air density is ~5% of sea level. We scale by the square root of the
  pressure ratio, giving ~1.1 W/m2K at float. This is a standard first-order
  treatment; it is a documented assumption and a stress-test axis.
"""

import math

from . import atmosphere as atm
from . import params as P


# ---------------------------------------------------------------------------
# CONDUCTION
# ---------------------------------------------------------------------------
def conduction_ua(insulation_mm, area_m2, k_ins):
    """Conductance of the insulation wall, UA = (k/t) * A, in W/K."""
    thickness_m = max(insulation_mm, 1.0) / 1000.0
    return (k_ins / thickness_m) * area_m2


def convection_coefficient_w_m2k(altitude_km, h0=5.0):
    """Natural-convection coefficient at altitude.

    SOURCE for h0 = 5 W/(m2 K): typical sea-level natural convection for a small
    enclosure, standard heat-transfer texts.
    ASSUMPTION: scales with sqrt(pressure ratio). Pressure ratio comes from the
    exponential atmosphere, so this is traceable rather than arbitrary.
    """
    return h0 * math.sqrt(atm.atmospheric_pressure_ratio(altitude_km))


# ---------------------------------------------------------------------------
# RADIATION
# ---------------------------------------------------------------------------
def radiant_temperature_c(t_ambient_c, radiant_offset_c=P.DEFAULT_RADIANT_OFFSET_C):
    """Effective temperature the outer skin radiates to.

    At 26 km the payload sees cold space above, warmer Earth below, and the
    horizon at the sides. Full 3-D view-factor treatment is out of scope, so this
    is a first-order parameterisation: the environment behaves as if it were
    `radiant_offset_c` colder than the air. It is exposed to the user and is a
    named axis of the stress-test engine -- it is the dominant radiative
    uncertainty and we say so rather than hiding it in a constant.
    """
    return min(t_ambient_c - radiant_offset_c, t_ambient_c)


def _radiation_from_skin_w(t_skin_c, t_radiant_c, area_m2, emissivity):
    t_skin_k = P.c_to_k(t_skin_c)
    t_rad_k = max(P.c_to_k(t_radiant_c), P.T_SPACE_K)
    return emissivity * P.STEFAN_BOLTZMANN * area_m2 * (t_skin_k ** 4 - t_rad_k ** 4)


def skin_temperature_c(t_box_c, t_ambient_c, altitude_km, insulation_mm, area_m2,
                       k_ins, emissivity=P.DEFAULT_EMISSIVITY,
                       radiant_offset_c=P.DEFAULT_RADIANT_OFFSET_C):
    """Solve for the outer-skin temperature each step.

    Bounded bisection over a physically sensible interval. Bisection is chosen
    over Newton deliberately: the quartic is monotonic but can be flat, and
    bisection cannot diverge. 40 iterations gives sub-millikelvin precision on a
    ~100 K bracket, and the cost is trivial next to the rest of the step.
    """
    ua_cond = conduction_ua(insulation_mm, area_m2, k_ins)
    if ua_cond <= 0.0:
        return t_box_c

    h_conv = convection_coefficient_w_m2k(altitude_km)
    t_rad = radiant_temperature_c(t_ambient_c, radiant_offset_c)

    def residual(t_skin):
        leaving = ua_cond * (t_box_c - t_skin)
        entering = (h_conv * area_m2 * (t_skin - t_ambient_c)
                    + _radiation_from_skin_w(t_skin, t_rad, area_m2, emissivity))
        return leaving - entering

    lo = min(t_rad, t_ambient_c) - 30.0
    hi = max(t_box_c, t_ambient_c) + 30.0
    f_lo, f_hi = residual(lo), residual(hi)
    if f_lo * f_hi > 0.0:
        # No sign change: the skin is effectively clamped to one bound.
        return max(lo, min(hi, t_box_c))

    for _ in range(45):
        mid = 0.5 * (lo + hi)
        if residual(mid) * f_lo <= 0.0:
            hi = mid
        else:
            lo, f_lo = mid, residual(mid)
    return 0.5 * (lo + hi)


def heat_loss_w(t_box_c, t_ambient_c, altitude_km, insulation_mm, area_m2, k_ins,
                emissivity=P.DEFAULT_EMISSIVITY,
                radiant_offset_c=P.DEFAULT_RADIANT_OFFSET_C):
    """Total heat leaving the payload, in watts. Positive = leaving the box.

    Equals conduction through the wall, which equals what the skin then sheds --
    the two must balance, and the skin solve above enforces that.
    """
    t_skin = skin_temperature_c(t_box_c, t_ambient_c, altitude_km, insulation_mm,
                                area_m2, k_ins, emissivity, radiant_offset_c)
    return conduction_ua(insulation_mm, area_m2, k_ins) * (t_box_c - t_skin)


def effective_ua(insulation_mm, area_m2, k_ins, altitude_km=26.0, ambient_c=-52.0,
                 emissivity=P.DEFAULT_EMISSIVITY,
                 radiant_offset_c=P.DEFAULT_RADIANT_OFFSET_C):
    """Linearised effective conductance between payload and environment, in W/K.

    Obtained numerically by perturbing the box temperature by 1 K and measuring
    the change in heat loss. Used for reporting and for choosing a stable
    timestep -- reported to the user because it is the single number that best
    answers 'how fast will my payload cool down?'.
    """
    q1 = heat_loss_w(ambient_c, ambient_c, altitude_km, insulation_mm, area_m2,
                     k_ins, emissivity, radiant_offset_c)
    q2 = heat_loss_w(ambient_c + 1.0, ambient_c, altitude_km, insulation_mm,
                     area_m2, k_ins, emissivity, radiant_offset_c)
    return q2 - q1


# ---------------------------------------------------------------------------
# THERMAL MASS  (audit finding A2)
# ---------------------------------------------------------------------------
def thermal_capacity_j_per_k(num_cells, insulation_mm, area_m2,
                            insulation_density=P.DEFAULT_INSULATION_DENSITY):
    """Lumped heat capacity C_th, in J/K.

    Sum of (mass x specific heat) over the battery pack, the pack hardware, the
    insulation shell and the structure. Without this the model had no thermal
    inertia and the payload snapped instantly to ambient temperature, which made
    every cold-night failure look earlier and more certain than it is.
    """
    cells_mass = num_cells * P.CELL_MASS_KG
    pack_mass = cells_mass * (1.0 + P.PACK_INACTIVE_MASS_FRACTION)

    insul_volume_m3 = (insulation_mm / 1000.0) * area_m2
    insul_mass = insul_volume_m3 * insulation_density

    return (pack_mass * P.CELL_CP_J_PER_KG_K
            + insul_mass * P.INSULATION_CP_J_PER_KG_K
            + P.HOUSING_MASS_KG * P.HOUSING_CP_J_PER_KG_K)


def thermal_time_constant_s(num_cells, insulation_mm, area_m2, k_ins,
                            altitude_km=26.0, ambient_c=-52.0,
                            emissivity=P.DEFAULT_EMISSIVITY,
                            radiant_offset_c=P.DEFAULT_RADIANT_OFFSET_C):
    """tau = C_th / UA_effective, in seconds."""
    c_th = thermal_capacity_j_per_k(num_cells, insulation_mm, area_m2)
    ua = effective_ua(insulation_mm, area_m2, k_ins, altitude_km, ambient_c,
                      emissivity, radiant_offset_c)
    return c_th / ua if ua > 0 else float("inf")


def heat_balance_step(t_box_c, t_ambient_c, altitude_km, dt_s, c_th, heater_w,
                     payload_heat_w, insulation_mm, area_m2, k_ins,
                     emissivity=P.DEFAULT_EMISSIVITY,
                     radiant_offset_c=P.DEFAULT_RADIANT_OFFSET_C):
    """Advance the lumped node by dt_s seconds and REPORT the heat flow used.

    Returns (t_new_c, q_loss_w) where q_loss_w is the heat leaving the payload
    at the start of the step, in watts. Positive means the box is losing heat to
    the environment; negative means it is gaining heat from it.

    Reporting q_loss_w is what makes the thermal energy balance auditable: the
    caller can accumulate the SAME number that was used in the integration
    instead of recomputing it later and hoping the two agree. (Audit A12: the
    previous post-hoc reconstruction clamped the loss at zero and silently
    dropped every heat-gain interval.)

    Forward Euler. Stability requires dt < 2*C_th/UA; mission.py derives dt from
    the time constant of the specific design.
    """
    q_in = heater_w + payload_heat_w
    q_out = heat_loss_w(t_box_c, t_ambient_c, altitude_km, insulation_mm,
                        area_m2, k_ins, emissivity, radiant_offset_c)
    return t_box_c + (q_in - q_out) * dt_s / c_th, q_out


def step_temperature(t_box_c, t_ambient_c, altitude_km, dt_s, c_th, heater_w,
                     payload_heat_w, insulation_mm, area_m2, k_ins,
                     emissivity=P.DEFAULT_EMISSIVITY,
                     radiant_offset_c=P.DEFAULT_RADIANT_OFFSET_C):
    """Advance the lumped node by dt_s seconds (forward Euler).

    Thin wrapper over heat_balance_step for callers that only want the new
    temperature. Stability requires dt < 2*C_th/UA.
    """
    t_new, _ = heat_balance_step(t_box_c, t_ambient_c, altitude_km, dt_s, c_th,
                                 heater_w, payload_heat_w, insulation_mm, area_m2,
                                 k_ins, emissivity, radiant_offset_c)
    return t_new


def steady_state_heater_power_w(ambient_c, target_c, altitude_km, insulation_mm,
                                area_m2, k_ins, emissivity=P.DEFAULT_EMISSIVITY,
                                radiant_offset_c=P.DEFAULT_RADIANT_OFFSET_C):
    """Heater power required to HOLD target_c at equilibrium.

    This is precisely the quantity a bench equilibrium test measures, so the
    comparison in bench/ is apples-to-apples. (Comparing a transient cool-down
    against this steady value was the trap identified during bench-test design.)
    """
    return max(0.0, heat_loss_w(target_c, ambient_c, altitude_km, insulation_mm,
                                area_m2, k_ins, emissivity, radiant_offset_c))


def equilibrium_diagnostics(ambient_c, altitude_km, insulation_mm, area_m2,
                            k_ins, heater_w, payload_heat_w,
                            emissivity=P.DEFAULT_EMISSIVITY,
                            radiant_offset_c=P.DEFAULT_RADIANT_OFFSET_C,
                            lo_c=-200.0, hi_c=400.0):
    """Steady-state box temperature, WITH diagnostics.

    Returns (temperature_c, converged, residual_w).

    Audit finding A13: the previous version returned a bracket BOUND silently
    when the true root lay outside the search interval. A caller could not tell a
    genuine 150 C equilibrium from "the search gave up at 150 C". For a
    well-insulated box with a 5 W heater the true equilibrium is above 150 C, so
    the old code reported a bound as if it were a solution.

    `converged` is False only when no sign change was found in the bracket, in
    which case the returned value is the nearest bound and must be treated as
    "at least this hot", never as an equilibrium.
    """
    def residual(t):
        return (heater_w + payload_heat_w
                - heat_loss_w(t, ambient_c, altitude_km, insulation_mm, area_m2,
                              k_ins, emissivity, radiant_offset_c))

    a, b = lo_c, hi_c
    f_a, f_b = residual(a), residual(b)
    if f_a * f_b > 0.0:
        return (a if f_a < 0 else b), False, (f_a if f_a < 0 else f_b)
    for _ in range(200):
        mid = 0.5 * (a + b)
        if residual(mid) * f_a <= 0.0:
            b = mid
        else:
            a, f_a = mid, residual(mid)
    t = 0.5 * (a + b)
    return t, True, residual(t)


def equilibrium_temperature_c(ambient_c, altitude_km, insulation_mm, area_m2,
                              k_ins, heater_w, payload_heat_w,
                              emissivity=P.DEFAULT_EMISSIVITY,
                              radiant_offset_c=P.DEFAULT_RADIANT_OFFSET_C,
                              lo_c=-200.0, hi_c=400.0):
    """Steady-state box temperature with a given standing heat input.

    Solved by bisection on (heat in - heat out). Used by the report to state
    where a design settles, and by tests as an independent check on the
    time-stepping integrator.

    Returns the temperature only. If you need to know whether the root was
    actually bracketed, call equilibrium_diagnostics instead -- a returned value
    equal to a bound may mean no root exists inside the interval.
    """
    t, _converged, _res = equilibrium_diagnostics(
        ambient_c, altitude_km, insulation_mm, area_m2, k_ins, heater_w,
        payload_heat_w, emissivity, radiant_offset_c, lo_c, hi_c)
    return t
