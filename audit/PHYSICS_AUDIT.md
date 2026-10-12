# PHYSICS AUDIT — COLDSTART
**Date:** 12 Oct 2026 · **Scope:** `app/physics.py` as it existed before this upgrade
**Method:** code inspection + numerical checks, run against the live 12 Oct forecast.

---

## Findings

### A1 — CRITICAL: solar model uses surface irradiance at 26 km
**Location:** `simulate_flight()`, PV block
**Evidence:**
```
env["solar_by_index"] <- GFS "shortwave_radiation" = shortwave radiation AT THE SURFACE
Peak forecast for 12 Oct: 868 W/m2
Solar constant above the atmosphere: ~1361 W/m2 (x ~1.03 eccentricity correction)
```
**Impact:** For a payload floating at 26 km — above ~98% of the atmosphere and above all
cloud — the model understates available irradiance by roughly **1.5×–2×**. Any design with
solar generation is therefore evaluated pessimistically, and the error grows with altitude.
**Fix:** implement an altitude-aware irradiance model (extraterrestrial constant + airmass
attenuation scaled by pressure ratio), validated against the real surface forecast.

### A2 — MAJOR: no thermal mass; battery temperature jumps instantly to ambient
**Location:** `simulate_flight()`, `battery_c = setpoint_c` / `battery_c = ambient_c`
**Evidence:** `grep -i "thermal mass|heat capacity|lumped|transient"` in `physics.py` → no match.
**Impact:** A real pack has a lumped heat capacity of order
`C_th = m·c_p ≈ 0.27 kg × 1000 J/kg·K ≈ 300 J/K`. The insulation coefficient at 10 mm is
`UA ≈ 0.14 W/K`, so the time constant is `τ = C_th/UA ≈ 2100 s ≈ 35 min`. The model reports
the pack at ambient immediately after launch — physically impossible, and it makes every
cold-night failure look worse and earlier than reality.
**Fix:** lumped-capacitance transient heat balance integrated at a stable sub-minute timestep.

### A3 — MODERATE: no discharge current (C-rate) limit
**Location:** battery block
**Evidence:** no `current`, `C-rate` or `max_discharge` term anywhere.
**Impact:** A 6-cell pack can be asked to deliver any power the code wants. Real 18650 cells
have a limited continuous discharge current; exceeding it causes voltage collapse, not
graceful extra runtime. A heater sized beyond the pack's capability would be reported as
"surviving".
**Fix:** explicit `I_req = P/V_nominal` check against `C_rate_max × capacity_Ah` as a
first-class failure mode.

### A4 — MODERATE: slide claims a constraint the code never enforces
**Evidence:** slide 3 and `physics.py` docstrings state *"no charging below 0 °C"*.
`grep -i "below|no charge|charging"` → the only hit is a docstring. **Not implemented.**
**Impact:** An unenforced claim on a judge-facing slide is the single worst category of
defect here — it is exactly the kind of thing a technical jury probes.
**Fix:** implement charge inhibition below 0 °C, or remove the claim. (Implementing.)

### A5 — MINOR: heater modelled as ideal / unlimited power
**Location:** `heater_power_w()` result used directly with no cap.
**Impact:** The thermostat is treated as able to always hold setpoint, regardless of heater
rating or pack capability. Real heaters have a fixed rating, and a weak heater on a cold
night is a genuine failure mode that the model cannot currently express.
**Fix:** heater has a rated maximum power; thermostat has hysteresis and a first-order lag.

### A6 — MINOR: payload electronics self-heating not modelled
**Impact:** 3 W of electronics inside an insulated box *is* 3 W of heat. Ignoring it makes
the box look colder than it is. Physically real and easy to include.
**Fix:** add a documented fraction of payload power dissipated as heat inside the box.

### A7 — MODERATE: single failure mode
**Impact:** Failure is reported only as energy depletion. Temperature-limit and
power-capability failures are not distinguished, so the failure explanation cannot say
*why* something died.
**Fix:** failure taxonomy with first-violation detection and contributing factors.

### A8 — MINOR: undocumented radiative parameter
**Location:** `sky_delta_c=8.0` in `heater_power_w()`, never surfaced to the user.
**Impact:** Radiative exchange in the stratosphere is a genuinely 3-D problem (payload sees
space above, Earth below, horizon at the sides). A fixed 8 K depression is a plausible
first-order choice but is *presented as a constant*, not as the uncertain parameter it is.
**Fix:** expose an effective radiant environment parameter with documented default, and put
it in the uncertainty engine as a named stress-test axis.

---

## Assessment

The **core physics of the existing code is sound**: conduction (Fourier), radiation
(Stefan-Boltzmann), published capacity-vs-temperature interpolation, solar geometry
(NOAA algorithm) and SGP4 are all implemented correctly and are dimensionally consistent.
The defects are **omissions and one mis-scaled input**, not wrong equations.

Severity ranking: **A1 > A2 > A4 > A3 > A7 > A5 > A6 > A8**

All eight are addressed in the upgraded engine. Verification evidence for each fix is in
`tests/` (see `TEST_REPORT.md` for results).

---

# ADDENDUM — A9 (found during engine implementation, not the original audit)

**A9 — Radiation was evaluated at the battery temperature instead of the skin temperature.**
Severity: **HIGH** — it changed every thermal number in the project.

**What the original code did.** It treated the paths from the box to the environment as
parallel: conduction through the wall *plus* radiation from the box surface, both driven
by the difference between the battery temperature and the environment.

**Why that is wrong.** For an insulated box, the outer skin is not at the battery
temperature — it sits close to ambient, because the wall is the bottleneck. Conduction
through the wall and loss from the surface are therefore **in series**, not parallel.
Driving radiation with the interior temperature overstates the radiative loss by roughly
3× at these conditions.

At 26 km with 10 mm of foam this inflated the effective conductance from
**0.153 W/K to about 0.43 W/K**. Every design looked about three times worse than it is,
which is why the prototype concluded the default design freezes early.

**Correct model.**

    UA_cond · (T_box − T_skin) = h_conv·A·(T_skin − T_amb) + ε·σ·A·(T_skin⁴ − T_rad⁴)

The skin temperature is massless and is solved algebraically each step (the engine uses
bisection), so the interior node still carries all the thermal mass. Convection is scaled
by the square root of the pressure ratio to weaken with altitude.

**Consequence for the project narrative.** With the corrected model the default design no
longer dies of cold. It dies of **energy**: the heater drains the pack long before the
cold would have won. Insulation thickness is the dominant lever (thermal time constant
54 → 392 min across 10–75 mm), not heater power. Any statement in the deck that the
payload "freezes" must be re-checked against the current engine before it is repeated.

**How it was caught.** Not by reading the code — by writing the test that asserts an
invariant any correct series network must satisfy: *effective UA must be strictly less
than the wall conductance alone*. The test failed. See `tests/TEST_REPORT.md`, defect D2.

---

# ADDENDUM 2 — A10 to A13 (found during the verification upgrade)

These four were found by auditing the energy accounting and by benchmarks that
asserted physical behaviour rather than merely running. Each was fixed at its
cause and is now guarded by a named regression test.

## A10 — Heater energy was booked at the COMMANDED power, not the delivered power
**Severity: HIGH — the reported energy consumption exceeded what the battery supplied.**

`heater_energy_wh` accumulated `heater_w` (what the thermostat asked for), while
the pack supplied `effective_demand_w = min(demand, p_max)`. Whenever the C-rate
cap engaged, the reported heater consumption was larger than the energy that left
the battery. The electrical balance could not close.

**Fix:** delivered power is split explicitly — payload first, heater from the
remainder — and every accumulator uses the delivered values.
**Regression test:** `test_heater_energy_never_exceeds_delivered_power`.

## A11 — Payload self-heating was computed from the commanded load
**Severity: HIGH — thermal energy was created from nothing.**

`payload_heat_w = payload_load_w * PAYLOAD_HEAT_FRACTION` was evaluated once,
outside the loop, from the design value. A pack that could not meet demand still
warmed the box as if it had.

**Fix:** self-heating is derived each step from `delivered_payload_w`.
**Regression test:** `test_self_heating_uses_delivered_power`.

## A12 — Heat GAIN was clamped to zero and silently discarded
**Severity: MEDIUM — the reported heat loss was not a physical energy flow.**

`_heat_lost_wh` applied `max(0.0, q)` when reconstructing the total from the
1-minute sampled trace. Every interval where the payload was colder than its
environment was dropped, and the reconstruction did not use the same samples the
integrator used.

**Fix:** heat flow is accumulated inside the loop from the same `q` that drove the
step, and split into `heat_lost_wh` and `heat_gained_wh`.
**Regression test:** `test_heat_gain_is_recorded`.

## A13 — The equilibrium solver silently returned a bracket bound
**Severity: MEDIUM — a bound was reported as if it were a solution.**

`equilibrium_temperature_c` searched `[-150, 150] C` and, when no sign change was
found, returned the nearest bound with no indication. For a well-insulated box
with a 5 W heater the true equilibrium lies ABOVE 150 C, so the function returned
"150.0" — which reads like a converged answer.

Found because benchmark A3 compared the solver against an independent root find
and reported an 8.77 C discrepancy that turned out to be the bound, not a root.

**Fix:** bounds widened to `[-200, 400] C`, and `equilibrium_diagnostics()` added,
returning `(temperature, converged, residual)`. Callers that need to know whether
a root was genuinely bracketed can now ask.
**Regression test:** A3 asserts `root_bracketed` and a near-zero residual.

**Engineering consequence:** with a standing 5 W heater and 50–75 mm of
insulation, 8 of the 12 A3 configurations equilibrate between 81 C and 187 C —
above the 60 C maximum operating temperature. Over-insulation is a real failure
mode, not a theoretical one.

---

---

# ADDENDUM 3 — DEFECTS FOUND WHILE REBUILDING THE DECK ON THE VERIFIED ENGINE

These were found *after* A10–A13, while re-deriving every slide number. A14 was
found only because the deck-audit tool (`app/check_deck.py`) refused to accept a
claim it could not reproduce, which is the argument for keeping that tool.

## A14 — The ISA pressure helper was missing the gravitational term

**Defect.** `isa_pressure_hpa()` used the isothermal-layer relation
`p = p11 * exp(-(h - 11000) / (R * T))`. The correct scale height is
`R * T / g`. The `/ g` was absent, so the scale height was inflated by 9.80665
and pressure fell ~9.8x too slowly with altitude. At 26 km the function returned
**177.8 hPa** instead of the correct **~21 hPa**; at 20 km, 54.7 hPa vs the
correct ~5.5 hPa.

**Impact.** *None on any flight result.* This function is a reference/display
helper and is not called anywhere on the simulation path — the mission uses the
forecast pressure profile and `atmospheric_pressure_ratio()` for the float band.
Recorded because a wrong helper is a trap for whoever uses it next.

**Fix.** Divide by `g`. Regression test asserts 0 km, 11 km and 20 km against
published ISA values to 1%.

**Category: C** (numerical/software verification — a coding error with no
physical-consequence path).

## A15 — The simulation did not stop at the first constraint violation

**Defect.** When the pack fell below its minimum operating temperature or ran
out of charge, the integrator kept marching to the end of the flight. The
reported quantities (minimum temperature, worst-case temperature, final charge)
therefore described a state *after failure* — a state the payload would never
reach, because the payload is dead at that point.

**Impact.** Real, and it inverted a headline. The default 6-cell/10 mm design
was previously reported as failing *cold*; with failure detected at the boundary
it fails by **ENERGY_DEPLETED at 00:14**, not by temperature. The old ordering
made the recommended fix ("add insulation") look right when the binding
constraint was electrical energy. The recorded failure reason is now the reason
the design actually died.

**Fix.** The integrator records the failure event at the crossing, stops the
thermal integration, and the reported `min_box_c`/`max_box_c` describe the
flight only up to that point. A `*_raw` probe is exposed for tests that need the
unstopped trajectory.

**Category: C**, with a physical consequence — see A16.

## A16 — Overheating was detected but could never be reported

**Defect.** `TEMP_ABOVE_OPERATING` was evaluated in the integrator, but the
maximum internal temperature was never returned, so a box that overheated could
only be reported as a generic failure with no maximum to display.

**Impact.** It hid a genuine second failure edge. With the self-heating term of
A11, a well-insulated box carrying a load **overheats**: a 75 mm box with an 8 W
payload reaches 60.2 C at 19:36 even at nominal insulation, and every candidate
on the search grid except the thinnest insulations overheats if the insulation
conductivity turns out 2.5x better than the datasheet value. A design can now
fail from being too cold AND from being too warm, and both edges are measured.

**Fix.** `max_box_c` / `max_box_c_raw` added to the result; the deck's limits
panel and the app both disclose the upper edge.

**Category: A** (analytical — the equilibrium balance closes against the
closed-form skin balance) for the physics; **C** for the reporting fix.

## Search-space consequence

The optimiser's declared grid contains designs that violate *both* edges. Any
claim of the form "more insulation is always better" is therefore false on this
model, and the optimiser never binary-searches a single parameter — it only
enumerates. Stated in `optimizer.search_limits()` and repeated in the UI and the
exported report.

---

# EVIDENCE CATEGORIES

Every result in `verify/RESULTS.md` and in the app's Verification tab carries one:

| Tag | Meaning |
|---|---|
| **A** | Analytical verification — compared against a closed-form solution |
| **B** | Independent reference — external published source |
| **C** | Numerical / software verification |
| **D** | Assumption or exploratory scenario |
| **E** | Physical experiment — **NOT PERFORMED** |

**Category E is empty and must stay empty.** No bench test was conducted. Nothing
in this project is experimentally validated.
