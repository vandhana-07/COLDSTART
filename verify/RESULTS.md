# COLDSTART — physics verification results

Generated: **2026-10-12T06:19:50Z**  
Engine: `coldstart-engine-1.0`  
Forecast: LIVE  

Reproduce with:

```
cd app && python3 verify.py
python3 -m unittest discover -s tests -v
```

---

## Evidence categories

| Tag | Meaning | Used here |
|---|---|---|
| **A** | Analytical verification -- compared against a closed-form solution | yes |
| **B** | Independent reference comparison -- external published source | yes |
| **C** | Numerical / software verification -- convergence, invariants, regression | yes |
| **D** | Assumption or exploratory scenario -- chosen, not verified | yes |
| **E** | Physical experiment -- NOT PERFORMED | **no** |

> Category E is deliberately empty. No physical bench test, no flown payload and no laboratory measurement was performed for this project. Every thermal and electrical result here is analytical, computational or assumed.

---

## Task 1 — thermal model verification

### Governing equations as implemented

| Path | Equation | Source of the form |
|---|---|---|
| Conduction | `UA_cond = (k / t) * A, q = UA_cond * (T_box - T_skin)` | Fourier steady conduction through a plane wall. |
| Convection | `h = h0 * sqrt(p(alt)/p(0)), q = h A (T_skin - T_amb)` | Natural convection; h0 an assumed small-enclosure value (category D), scaled by the square root of the pressure ratio. |
| Radiation | `q = eps * sigma * A * (T_skin^4 - T_rad^4), T_rad = T_amb - offset` | Stefan-Boltzmann. The offset collapses Earth/horizon/space view factors into one parameter (category D). |
| Skin closure | `UA_cond (T_box - T_skin) = h A (T_skin - T_amb) + eps sigma A (T_skin^4 - T_rad^4)` | Conduction and surface loss are IN SERIES. Solved each step by bisection. |
| Lumped node | `C_th dT/dt = Q_heater + Q_selfheat - q_loss` | Lumped-capacitance. C_th sums pack, insulation and housing mass x cp. |
| Solar (electrical only) | `P_pv = I_direct(alt, elevation) * A_panel * eta * view` | Beer-Lambert attenuation of extraterrestrial irradiance. Solar HEATING of the box structure is NOT modelled — see limitations. |
| Internal heat generation | `Q_selfheat = PAYLOAD_HEAT_FRACTION * delivered_payload_power` | Assumed fraction (category D), applied to DELIVERED power only. |
| Battery | `usable = charge - nominal*(1 - f(T));  P_max = C_rate * Ah * V` | Capacity curve is an assumption (category D). |

### A1 — Lumped-capacitance decay vs closed-form solution  `[A]`

*Analytical verification -- compared against a closed-form solution*

**Method.** Forward Euler advanced to a fixed final time at four timesteps and compared with the closed-form solution. Error must fall as dt falls.

**Reference.** T(t) = T_inf + (T0 - T_inf) exp(-t/tau), with UA_eff derived by hand as a series combination of conduction and convection.

**Conditions.**

```
{
  "insulation_mm": 50.0,
  "cells": 8,
  "area_m2": 0.0864,
  "k_ins_w_per_mk": 0.03,
  "altitude_km": 26.0,
  "t_initial_c": 20.0,
  "t_ambient_c": -55.0,
  "heat_input_w": 0.0,
  "duration_s": 7200.0,
  "emissivity": 0.0,
  "ua_eff_w_per_k_hand_derived": 0.03336218,
  "c_th_j_per_k": 772.56,
  "tau_s": 23156.761,
  "observed_order_of_convergence": 1.001,
  "expected_order": 1.0,
  "order_note": "Forward Euler is first-order. The observed order is measured against the exact closed form, so unlike the mission-level study in app/verify.py this reference is not itself an approximation."
}
```

| dt (s) | engine (°C) | analytical (°C) | abs error (°C) | rel error (%) |
|---|---|---|---|---|
| 60 | -0.064471 | -0.042300 | -0.022171 | -0.040342 |
| 30 | -0.053377 | -0.042300 | -0.011077 | -0.020156 |
| 10 | -0.045991 | -0.042300 | -0.003691 | -0.006715 |
| 5 | -0.044145 | -0.042300 | -0.001845 | -0.003357 |

**Limitations.**

- Exact only because radiation is disabled; the radiative term is not exercised by this benchmark.
- UA_eff is treated as constant, so this does NOT verify the altitude-varying convection or the temperature-dependent terms.
- This verifies the integrator and the conduction/convection network. It says nothing about whether k = 0.030 W/m/K is the real value for the box (category D).

### A2 — Stefan-Boltzmann radiation against the exact expression  `[A]`

*Analytical verification -- compared against a closed-form solution*

**Method.** Direct comparison of the implementation with the closed-form expression.

**Reference.** q = eps * sigma * A * (T_skin^4 - T_radiant^4)

**Conditions.**

```
{
  "area_m2": 0.0864,
  "emissivity": 0.9,
  "sigma_w_m2_k4": 5.670374419e-08
}
```

| T_skin (°C) | T_radiant (°C) | engine (W) | analytical (W) | abs error (W) | direction |
|---|---|---|---|---|---|
| +20.0 | -60.0 | 23.4618141589 | 23.4618141589 | +0.00e+00 | loses heat |
| +0.0 | -60.0 | 15.4441284813 | 15.4441284813 | +0.00e+00 | loses heat |
| -40.0 | -60.0 | 3.9275337274 | 3.9275337274 | +0.00e+00 | loses heat |
| -60.0 | -60.0 | 0.0000000000 | 0.0000000000 | +0.00e+00 | balanced |

**Limitations.**

- Verifies the arithmetic, not the view factors. The real payload sees Earth and horizon as well as space; that is collapsed into a single assumed radiant temperature offset (category D).
- Assumes the skin is isothermal and grey.

### A3 — Equilibrium solver vs an independent root find  `[A]`

*Analytical verification -- compared against a closed-form solution*

**Method.** Engine bisection compared with an independent bisection written in this file, plus the residual at the returned root.

**Reference.** Solve (Q_heater + Q_selfheat) = q_loss(T_eq)

**Conditions.**

```
{
  "altitude_km": 26.0,
  "emissivity": 0.9,
  "radiant_offset_c": 10.0
}
```

| Ambient (°C) | Ins (mm) | Engine (°C) | Independent (°C) | abs error (°C) | residual at root (W) |
|---|---|---|---|---|---|
| -70 | 25 | 16.039560 | 16.039560 | +0.00e+00 | +0.00e+00 |
| -70 | 50 | 81.625979 | 81.625979 | +0.00e+00 | -0.00e+00 |
| -70 | 75 | 147.212399 | 147.212399 | +0.00e+00 | -0.00e+00 |
| -55 | 25 | 27.598924 | 27.598924 | +0.00e+00 | +0.00e+00 |
| -55 | 50 | 93.185344 | 93.185344 | +0.00e+00 | -0.00e+00 |
| -55 | 75 | 158.771764 | 158.771764 | +0.00e+00 | -0.00e+00 |
| -40 | 25 | 39.506756 | 39.506756 | +0.00e+00 | -0.00e+00 |
| -40 | 50 | 105.093176 | 105.093176 | +0.00e+00 | +0.00e+00 |
| -40 | 75 | 170.679595 | 170.679595 | +0.00e+00 | -0.00e+00 |
| -20 | 25 | 55.905271 | 55.905271 | +0.00e+00 | -0.00e+00 |
| -20 | 50 | 121.491690 | 121.491690 | +0.00e+00 | -0.00e+00 |
| -20 | 75 | 187.078110 | 187.078110 | +0.00e+00 | +0.00e+00 |

**Limitations.**

- Both solvers call the same heat_loss_w routine, so this verifies the root-finding, not the loss model itself.
- Equilibrium assumes the ambient is constant, which a real ascent is not. The bench protocol in bench/ measures this quantity, which is why it is the right comparison for a future physical test.
- Several of these configurations equilibrate ABOVE the 60 C maximum operating temperature. That is not a solver error: a well-insulated box with a standing 5 W heater genuinely overheats. It is why the engine has a TEMP_ABOVE_OPERATING failure mode.

### A4 — Limiting cases and heat-flow direction  `[A]`

*Analytical verification -- compared against a closed-form solution*

**Method.** Direct evaluation of limiting cases with asserted expected behaviour.

**Reference.** Second law of thermodynamics and the monotonicity of a series conductance network.

**Conditions.**

```
{
  "area_m2": 0.0864,
  "k_ins": 0.03,
  "altitude_km": 26.0
}
```

| Check | Expected | Observed | Result |
|---|---|---|---|
| flow direction | out | out | PASS |
| flow direction | in | in | PASS |
| flow direction | balanced | balanced | PASS |
| skin bounded | -66.0 <= t_skin <= 20.0 | -48.531 | PASS |
| skin bounded | -66.0 <= t_skin <= 0.0 | -51.5688 | PASS |
| skin bounded | -66.0 <= t_skin <= -20.0 | -54.6794 | PASS |
| skin bounded | -66.0 <= t_skin <= -50.0 | -59.4888 | PASS |
| monotonic in insulation | strictly decreasing | decreasing | PASS |
| passive equilibrium matches closed-form skin balance | T settles at -66.190 C, i.e. BELOW ambient, not at it | -66.1902 | PASS |
| colder box gains heat | negative (gaining) | negative | PASS |

**Limitations.**

- These are invariants, not quantitative accuracy checks: they catch a sign error or a broken monotonicity, not a wrong magnitude.
- The 'balanced' tolerance of +/-0.5 W exists because the radiant sink is colder than the air, so a box at air temperature still loses a little.

### B1 — Engine ISA vs published US Standard Atmosphere 1976  `[B]`

*Independent reference comparison -- external published source*

**Method.** Direct value-by-value comparison with the published reference table.

**Reference.** US Standard Atmosphere 1976 / ICAO ISA reference table (15 degC and 1013.25 hPa at sea level, 6.5 K/km to 11 km, 216.65 K isothermal above).

**Conditions.**

```
{
  "engine_model": "linear lapse to 11 km, isothermal above",
  "valid_range_claimed_km": "0-20"
}
```

| Alt (km) | Ref T (°C) | Engine T (°C) | T err (°C) | Ref p (hPa) | Engine p (hPa) | p err (%) |
|---|---|---|---|---|---|---|
| 0 | +15.00 | +15.00 | 0.0000 | 1013.25 | 1013.25 | 0.0000 |
| 1 | +8.50 | +8.50 | 0.0000 | 898.75 | 898.75 | 0.0005 |
| 2 | +2.00 | +2.00 | 0.0000 | 795.01 | 794.95 | 0.0074 |
| 5 | -17.50 | -17.50 | 0.0000 | 540.20 | 540.20 | 0.0004 |
| 10 | -50.00 | -50.00 | 0.0000 | 264.36 | 264.36 | 0.0004 |
| 11 | -56.50 | -56.50 | 0.0000 | 226.32 | 226.32 | 0.0004 |
| 15 | -56.50 | -56.50 | 0.0000 | 120.45 | 120.44 | 0.0049 |
| 20 | -56.50 | -56.50 | 0.0000 | 54.75 | 54.75 | 0.0042 |

**Limitations.**

- The engine is isothermal above 11 km, so it is exact through 20 km and DIVERGES above it: the real atmosphere warms from ~20 km and reaches 228.65 K at 32 km. The engine is not used as a data source above the forecast ceiling except as a declared fallback, and this table shows where that fallback is weakest.
- ISA is a reference atmosphere, not a forecast for any particular night.

### D1 — Parameters that are assumed rather than verified  `[D]`

*Assumption or exploratory scenario -- chosen, not verified*

**Method.** Inventory of constants with their basis and sensitivity.

**Reference.** No external source was measured or tested. Each entry records where the value came from and which part of the result it moves.

**Conditions.**

```
{
  "count": 8
}
```

| Parameter | Value | Basis | Impact | Exploratory range |
|---|---|---|---|---|
| Insulation conductivity k | 0.030 W/m/K | Typical published value for XPS foam | Directly scales UA and therefore every thermal time. UNVALIDATED. | 0.018 … 0.045 |
| Box surface area | 0.0864 m2 | 12 x 12 x 12 cm outer envelope | Linear in UA. A different box changes everything. | 0.06 … 0.12 |
| Surface emissivity | 0.90 | Typical for foam / tape / paint | Scales the radiative term, which dominates at 26 km. | 0.8 … 0.95 |
| Radiant temperature offset | 10 K below air | First-order stand-in for Earth + horizon + space view factors | The largest single modelling uncertainty in the loss path. | 5.0 … 20.0 |
| Natural convection coefficient h0 | 5.0 W/m2/K | Typical small-enclosure value from heat-transfer texts | Weak at 26 km where convection is ~1.5% of sea level; matters low down. | 3.0 … 8.0 |
| Cell capacity vs temperature curve | 1.00 at 20 C to 0.35 at -60 C | Shape typical of Li-ion; NOT from a datasheet we hold | Sets how much of the pack is usable when cold. | 0.25 … 0.45 |
| Payload self-heating fraction | 0.60 of electrical load | Engineering estimate of electronics-to-heat | Warms the box; a conservative 0.0 turns cold margins pessimistic. | 0.0 … 0.9 |
| Thermostat hysteresis | 1.5 K | Typical for a simple controller | Small effect on total heater energy. | 0.5 … 3.0 |

**Limitations.**

- The ranges shown are exploratory, chosen to bound engineering plausibility. They are NOT confidence intervals and are NOT derived from measurement.
- Task 6 propagates the three highest-impact parameters and reports how the design ranking responds.

## Task 2 — energy conservation `[C]`

**Sign convention.** Positive = energy LEAVING the battery, or heat ENTERING the payload node. Electrical: storage_drop + pv_into_cells + unmet_energy - payload_delivered - heater_delivered = residual. Thermal: heat_in - heat_lost + heat_gained - stored_change = residual.

**Numerical tolerance.** 1e-06 Wh.

| Design | Verdict | Storage drop | Payload | Heater | PV in | Residual | Pass |
|---|---|---|---|---|---|---|---|
| baseline_default | FAIL | 43.5583 | 18.7250 | 24.8333 | 0.0000 | +0.000e+00 | yes |
| cheapest_passing | PASS | 41.2750 | 41.2750 | 0.0000 | 0.0000 | +0.000e+00 | yes |
| most_robust | PASS | 15.8199 | 41.2750 | 0.0000 | 25.4551 | +0.000e+00 | yes |

### State consistency scan

| Design | Points | Checks | Violations | Clean |
|---|---|---|---|---|
| baseline_default | 375 | 8 | 0 | yes |
| cheapest_passing | 826 | 8 | 0 | yes |
| most_robust | 826 | 8 | 0 | yes |

**Defects found and fixed in this pass.** 3

- **A10** — Heater energy was booked at the COMMANDED power, not the power the pack actually delivered. When the pack hit its C-rate limit the reported heater consumption exceeded the energy the battery supplied.
  - *Cause:* heater_energy_wh accumulated heater_w (the thermostat request) while the pack was only able to supply p_max.
  - *Fix:* Delivered power is now split explicitly: payload first, heater from the remainder; all bookkeeping uses delivered values.
  - *Regression test:* `test_heater_energy_never_exceeds_delivered`
- **A11** — Payload self-heating was computed from the commanded load even when the pack could not supply it, creating thermal energy from nothing.
  - *Cause:* payload_heat_w was computed once, outside the loop, from the design value.
  - *Fix:* payload_heat_w is now derived each step from delivered_payload_w.
  - *Regression test:* `test_self_heating_uses_delivered_power`
- **A12** — Reported heat loss clamped negative flow to zero (max(0, q)), silently discarding every heat-GAIN interval and reconstructing the total from 1-minute samples instead of the integration itself.
  - *Cause:* post-hoc reconstruction in _heat_lost_wh.
  - *Fix:* heat flow is now accumulated in the loop from the same q that drove the step, split into heat_lost and heat_gained.
  - *Regression test:* `test_heat_gain_is_recorded`

**On the thermal residual.** The thermal residual is identically zero for forward Euler: the scheme's own accumulation reproduces it term for term. It is a BOOKKEEPING CONSISTENCY identity, NOT an accuracy measure. Euler truncation error is quantified in Task 1 (analytical) and Task 4 (convergence).

## Task 3 — battery model `[D]`

### Equations as implemented

- `nominal_wh        = N_cells * wh_per_cell * capacity_mult`
- `capacity_fraction = piecewise-linear interpolation of CAPACITY_VS_TEMP, clamped at the endpoints`
- `usable_wh         = charge_wh - nominal_wh * (1 - capacity_fraction(T))`
- `max_discharge_w   = C_rate_max * N_cells * (Ah per cell) * 3.6 V, only for T above the operating floor`
- `step_charge       : new = charge - (P_out - P_pv * eta) * dt_h, clamped to [0, nominal]`
- `can_accept_charge : T >= charge_min_c (0 C)`

### Reference comparison

The capacity-vs-temperature curve is an ASSUMPTION. It is shaped like commonly published Li-ion behaviour but is NOT taken from a datasheet held for the specific cells used, and NO cell was tested at any temperature. Do not describe it as datasheet-verified.

| Check | Expected | Got | Result |
|---|---|---|---|
| nominal energy from cell count | 97.92 | 97.92 | PASS |
| usable at 20 C equals nominal | 97.92 | 97.92 | PASS |
| usable at -60 C equals 35 percent of nominal | 34.272 | 34.272 | PASS |
| C-rate ceiling = C_rate x amp-hours x volts | 97.92 | 97.92 | PASS |
| no discharge below the operating floor | 0.0 | 0.0 | PASS |
| charge inhibited below 0 C and reported, not lost | accepted 0.0 / rejected 5.0 | accepted 0.0 / rejected 5.0 | PASS |

### Unmeasured parameters

- Capacity at each temperature below 20 C
- Internal resistance vs temperature (affects the C-rate ceiling in the cold)
- Cell-to-cell capacity spread within the pack
- Ageing and cycle history of the actual cells

**Required before any flight claim.** A datasheet for the exact cell part number, and ideally a discharge test at low temperature. Until then the battery model is category D.

## Task 4 — numerical convergence `[C]`

*Differences are measured against the FINEST step tested (5 s), which is the best available estimate, not an exact solution. An exact solution exists only for benchmark A1.*

### default_fails_energy

| dt (s) | Verdict | Failure | ΔT_min vs finest (°C) | Δfinal charge vs finest (Wh) | Δfailure time vs finest (min) |
|---|---|---|---|---|---|
| 60 | FAIL | 00:14 | -0.2000 | +0.17800 | -1.42 |
| 30 | FAIL | 00:14 | +0.0000 | +0.20300 | -1.42 |
| 10 | FAIL | 00:15 | +0.0000 | +0.07200 | -0.42 |
| 5 | FAIL | 00:15 | +0.0000 | +0.00000 | 0.0 |

- Verdict stable across all timesteps: **yes**
- Failure reason stable: **yes**
- Failure-time spread: **1.42 min**
- Min-temperature spread: **0.2000 °C**
- Worst min-temperature change vs the 5 s reference: **0.2000 °C**
- Observed order of convergence: **1.42** (first-order expected for forward Euler; per-halving values [2.725, 0.123])

### cheapest_passing

| dt (s) | Verdict | Failure | ΔT_min vs finest (°C) | Δfinal charge vs finest (Wh) | Δfailure time vs finest (min) |
|---|---|---|---|---|---|
| 60 | PASS | — | +0.0000 | -0.04600 | — |
| 30 | PASS | — | +0.0000 | -0.02100 | — |
| 10 | PASS | — | +0.0000 | -0.00400 | — |
| 5 | PASS | — | +0.0000 | +0.00000 | — |

- Verdict stable across all timesteps: **yes**
- Failure reason stable: **yes**
- Failure-time spread: **0.00 min**
- Min-temperature spread: **0.0000 °C**
- Worst min-temperature change vs the 5 s reference: **0.0000 °C**
- Observed order of convergence: **1.77** (first-order expected for forward Euler; per-halving values [1.302, 2.245])

## Task 6 — parameter uncertainty `[D]`

**All ranges are exploratory**, chosen to bound engineering plausibility. They are not confidence intervals and not derived from measurement.

| Axis | Baseline | Values swept | Basis |
|---|---|---|---|
| Insulation conductivity | 0.03 | [0.018, 0.024, 0.03, 0.036, 0.045] | Published range for XPS/aerogel-type foams. UNVALIDATED for this box. |
| Battery capacity multiplier | 1.0 | [1.0, 0.9, 0.8, 0.7, 0.6] | Exploratory. No cell tested. |
| Radiant temperature offset | 10.0 | [20.0, 15.0, 10.0, 5.0, 0.0] | Exploratory bound on view-factor uncertainty. |

### One axis at a time — verdict of each design

| Axis | Value | baseline_default | cheapest_passing | most_robust |
|---|---|---|---|---|
| Insulation conductivity | 0.018 | FAIL ENERGY_DEPLETED @ 00:14 | PASS @ — | PASS @ — |
| Insulation conductivity | 0.024 | FAIL ENERGY_DEPLETED @ 00:14 | PASS @ — | PASS @ — |
| Insulation conductivity | 0.03 | FAIL ENERGY_DEPLETED @ 00:14 | PASS @ — | PASS @ — |
| Insulation conductivity | 0.036 | FAIL ENERGY_DEPLETED @ 00:14 | PASS @ — | PASS @ — |
| Insulation conductivity | 0.045 | FAIL ENERGY_DEPLETED @ 00:14 | PASS @ — | PASS @ — |
| Battery capacity multiplier | 1.0 | FAIL ENERGY_DEPLETED @ 00:14 | PASS @ — | PASS @ — |
| Battery capacity multiplier | 0.9 | FAIL ENERGY_DEPLETED @ 23:42 | PASS @ — | PASS @ — |
| Battery capacity multiplier | 0.8 | FAIL ENERGY_DEPLETED @ 23:09 | PASS @ — | PASS @ — |
| Battery capacity multiplier | 0.7 | FAIL ENERGY_DEPLETED @ 22:34 | FAIL ENERGY_DEPLETED @ 07:22 | PASS @ — |
| Battery capacity multiplier | 0.6 | FAIL ENERGY_DEPLETED @ 22:02 | FAIL ENERGY_DEPLETED @ 05:41 | PASS @ — |
| Radiant temperature offset | 20.0 | FAIL ENERGY_DEPLETED @ 23:50 | PASS @ — | PASS @ — |
| Radiant temperature offset | 15.0 | FAIL ENERGY_DEPLETED @ 00:04 | PASS @ — | PASS @ — |
| Radiant temperature offset | 10.0 | FAIL ENERGY_DEPLETED @ 00:14 | PASS @ — | PASS @ — |
| Radiant temperature offset | 5.0 | FAIL ENERGY_DEPLETED @ 00:28 | PASS @ — | PASS @ — |
| Radiant temperature offset | 0.0 | FAIL ENERGY_DEPLETED @ 00:45 | PASS @ — | PASS @ — |

### Combined worst case

| Design | Verdict | Failure | Time | Min T (°C) | Margin |
|---|---|---|---|---|---|
| baseline_default | FAIL | TEMP_BELOW_OPERATING | 19:16 | -20.9 | 4.80 |
| cheapest_passing | FAIL | ENERGY_DEPLETED | 02:24 | -12.8 | 0.99 |
| most_robust | FAIL | ENERGY_DEPLETED | 07:05 | -10.7 | 0.99 |

**Ranking is NOT stable.** The following combinations invert the cost/robustness ordering:

- capacity_mult = 0.7: cheapest_passing FAILS while most_robust PASSES
- capacity_mult = 0.6: cheapest_passing FAILS while most_robust PASSES

> These are SCENARIO PASS RATES over assumed input ranges. They are not probabilities of real-world survival. The ranges were chosen to bound engineering plausibility, not measured.

---

## Unresolved defects and limitations

- Box thermal conductance UA is UNVALIDATED. It derives from an assumed conductivity and an assumed geometry; no bench measurement exists.
- The battery capacity-vs-temperature curve is an ASSUMPTION. No specific cell datasheet is attached and no cell was tested.
- The radiant temperature offset is a single parameter standing in for full view-factor geometry. It is the largest uncertainty in the loss path.
- SOLAR HEATING OF THE STRUCTURE IS NOT MODELLED. The model computes solar ELECTRICAL generation only. A sunlit payload is not warmed in this model, so daytime scenarios are biased cold.
- The engine's ISA is isothermal above 11 km and therefore diverges from the published standard atmosphere above about 20 km (see benchmark B1).
- Thermal residual in the energy balance is an identity for forward Euler and is not an accuracy measure; real truncation error is quantified in Tasks 1 and 4.
- Overheating failure mode is modelled but has never been observed in flight.
- Uncertainty ranges are exploratory and are not probability distributions, so no survival probability is reported anywhere in this project.
- Category E (physical experiment) is empty. No bench test was conducted.
