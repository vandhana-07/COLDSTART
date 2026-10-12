"""
battery.py -- capacity, energy accounting, and electrical limits.
=================================================================
Fixes audit findings A3 (no C-rate limit), A4 (unimplemented charge constraint)
and A7 (single failure mode).

THE ENERGY MODEL, stated precisely because it is easy to get wrong:

  charge_wh   = energy actually stored in the pack. Starts full, changes only
                by energy flowing in or out. This is the state variable.

  usable_wh   = charge_wh - nominal_wh * (1 - capacity_fraction(T))

                A cold cell does not lose its charge; it loses the ability to
                ACCESS the bottom of it. At -52 C only ~39% is reachable, so
                about 61% of the nominal capacity is frozen and unusable.

  The mission fails when usable_wh falls to the reserve floor.

Two electrical constraints bound what the pack can supply at any instant:

  * C-rate      : current must not exceed C_RATE_MAX * capacity_Ah
  * temperature : cells must not be discharged below the operating limit

Both are first-class failure modes with their own reason codes, so the failure
replay can say WHY a design died instead of blaming cold by default.
"""

from . import params as P


def capacity_fraction(temp_c, curve=None):
    """Usable fraction of nominal capacity at a given cell temperature.

    Piecewise-linear interpolation between published datasheet points.
    Linear interpolation is the honest choice: we do not have a physical model
    for the curve and we do not pretend to. Points outside the table clamp to
    the endpoints.
    """
    curve = curve or P.CAPACITY_VS_TEMP
    if temp_c <= curve[0][0]:
        return curve[0][1]
    if temp_c >= curve[-1][0]:
        return curve[-1][1]
    for (t0, f0), (t1, f1) in zip(curve, curve[1:]):
        if t0 <= temp_c <= t1:
            return f0 + (f1 - f0) * (temp_c - t0) / (t1 - t0)
    return 1.0


def nominal_wh(num_cells, wh_per_cell=P.CELL_WH):
    return num_cells * wh_per_cell


def nominal_ah(num_cells, ah_per_cell=P.CELL_AH):
    return num_cells * ah_per_cell


def usable_wh(charge_wh, nominal, temp_c):
    """Energy the pack can actually deliver right now, given its temperature."""
    frozen = nominal * (1.0 - capacity_fraction(temp_c))
    return max(0.0, charge_wh - frozen)


def max_discharge_power_w(num_cells, temp_c,
                          ah_per_cell=P.CELL_AH, c_rate_max=P.C_RATE_MAX,
                          nominal_voltage=3.6):
    """Instantaneous power ceiling imposed by the C-rate limit.

    I_max = c_rate_max * capacity_Ah ;  P_max = I_max * V_nominal
    """
    if temp_c < P.DEFAULT_MIN_OPERATING_C:
        return 0.0                     # cannot discharge at all below the limit
    return c_rate_max * nominal_ah(num_cells, ah_per_cell) * nominal_voltage


def can_accept_charge(temp_c, charge_min_c=P.CHARGE_MIN_TEMP_C):
    """Li-ion must not be charged below 0 C -- lithium plating permanently damages
    the cell. THIS WAS AUDIT FINDING A4: previously claimed on the slide but never
    enforced in code. Now enforced, and surfaced as a counted event so it shows up
    in the report instead of being silently dropped.
    """
    return temp_c >= charge_min_c


def step_charge(charge_wh, nominal, dt_s, battery_power_out_w, pv_available_w,
                temp_c, charge_efficiency=P.CHARGE_EFFICIENCY,
                charge_min_c=P.CHARGE_MIN_TEMP_C, max_charge_power_w=None):
    """Advance stored charge by dt_s seconds.

    battery_power_out_w : net power the pack must supply (payload + heater - PV bus)
                          expressed as positive = discharging.
    pv_available_w      : panel output available to charge the pack.

    Returns (new_charge_wh, charge_accepted_w, charge_rejected_w).
    charge_rejected_w is non-zero when the pack is cold or full -- reported as a
    data-quality event rather than silently discarded energy.
    """
    dt_h = dt_s / P.SECONDS_PER_HOUR

    accept = can_accept_charge(temp_c, charge_min_c)
    if max_charge_power_w is not None:
        pv_available_w = min(pv_available_w, max_charge_power_w)

    if accept:
        charge_accepted = pv_available_w
        charge_rejected = 0.0
    else:
        charge_accepted = 0.0
        charge_rejected = pv_available_w

    net_out = battery_power_out_w - charge_accepted * charge_efficiency

    new_charge = charge_wh - net_out * dt_h
    if new_charge > nominal:
        charge_rejected += (new_charge - nominal) * P.SECONDS_PER_HOUR / dt_s
        new_charge = nominal
    new_charge = max(0.0, new_charge)

    return new_charge, charge_accepted, charge_rejected
