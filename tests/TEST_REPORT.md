# TEST REPORT — COLDSTART physics engine

**Date:** 12 October 2026
**Command:** `python3 -m unittest discover -s tests -v`
**Result:** **71 tests, 71 passed, 0 failed, 0 skipped** (9.9 s)
**Engine under test:** `app/engine/` (params, atmosphere, thermal, battery, mission, cost)

---

## 0. What this report is, and what it is not

**This is software verification.** Every test below checks the *code* against an
analytical reference, a physical invariant, or a boundary condition that can be
established without hardware.

**This is not physical validation.** No test here proves that the model matches a
real payload in the stratosphere. Three inputs remain **UNVALIDATED** against
measurement:

| Input | Value used | Status |
|---|---|---|
| Box conductance `UA` | computed from `k = 0.030 W/m·K`, 86.4 cm² | **UNVALIDATED** — no bench measurement |
| Cell capacity vs temperature | curve in `params.py` | **UNVALIDATED** — from datasheets, not our cells |
| Package surface conductance | correlation-based | **UNVALIDATED** |

The bench rig in `bench/` exists to reduce the first of these. It was not built.
We are not claiming otherwise, and no test below should be read as a substitute.

What the tests *do* buy us is narrower and worth stating precisely: **they caught
four real defects that would otherwise have shipped**, including one that would
have made every flight prediction wrong by an order of magnitude in pressure, and
one that revealed a failure mode we had not modelled at all.

---

## 1. Coverage by group

| Group | Tests | What it establishes |
|---|---|---|
| T1 Conduction | 4 | `UA = (k/t)·A` matches hand calculation; correct scaling in `k`, `t`, `A` |
| T2 Radiation | 5 | Stefan–Boltzmann `εσA(T⁴−T_rad⁴)` matches hand calculation; 4th-power and emissivity scaling; sign convention |
| T3 Thermal network | 8 | Series-resistance invariant; more insulation → less loss; convection falls with altitude; capacity rises with mass |
| T4 Battery | 13 | Curve endpoints and monotonicity; usable-energy algebra; C-rate scaling; charge inhibition below 0 °C **and reported, not silently lost** |
| T5 Energy accounting | 4 | Charge falls by exactly load × hours against a hand calculation; heater never exceeds rated energy |
| T6 Integrator | 4 | Timestep convergence; time-stepping agrees with the independent equilibrium solver; explicit stability bound |
| T7 Atmosphere | 9 | ISA reference table; irradiance rises with altitude; correct clear-sky magnitude; no output below the horizon |
| T8 Failure taxonomy | 9 | Every reason code reachable and correctly attributed; simulation halts at first failure; suggestions are actionable |
| T9 Data layer | 4 | API failure without cache **raises** rather than inventing data; cache fallback is flagged `CACHED` |
| T10 Determinism | 3 | Repeated runs bit-identical; cost breakdown totals internally consistent |

---

## 2. Defects the tests actually caught

These are the reason the suite exists. All four were found by tests failing, not by
inspection.

### D1 — ISA pressure formula used kilometres where the standard requires metres
**Found by:** T7 `test_isa_pressure_at_26km_matches_reference_table`
**Symptom:** 26 km returned **795 hPa**; the correct value is ≈19 hPa.
**Cause:** the barometric lapse term is `0.0065 K/m`. Passing km made the
tropopause correction negligible, so pressure barely fell with altitude.
**Fix:** convert to metres before applying the standard atmosphere.
**Secondary finding:** the first fix was *also* wrong — the isothermal scale height
`H = R·T/g` needs gravity. Omitting `g` gave 178 hPa at 26 km. Caught because the
test asserted against a published reference table rather than against our own output.
**Impact:** `isa_pressure_hpa` is a reference/cross-check function. The live flight
path uses measured GFS geopotential heights, so **the headline sweep results were
not affected** — but any pressure readout would have been badly wrong.

### D2 — cell temperature was used to evaluate radiation at the surface
**Found by:** T3 `test_effective_ua_is_below_conduction_ua`
**Symptom:** effective conductance came out *above* the wall conductance.
**Cause:** conduction and surface loss were treated as **parallel** paths, and
radiation was evaluated at the *interior* temperature. For an insulated box the
skin sits near ambient, so the radiative driving difference was overstated ~3×.
At 26 km with 10 mm foam this inflated UA from 0.153 to ~0.43 W/K.
**Fix:** two-stage series model. Interior → wall conduction → skin; skin → space by
radiation **and** convection in parallel. `UA_cond·(T_box−T_skin) = h·A·(T_skin−T_amb) + εσA·(T_skin⁴−T_rad⁴)`.
**Impact:** every thermal number in the project changed. This is audit finding **A9**.

### D3 — the simulation continued running after the payload was dead
**Found by:** T8 `test_simulation_stops_at_first_failure`
**Symptom:** a pack that failed at T+105 min was still being drawn down and still
self-heating at T+840 min, reaching +80 °C and drawing 8 W from a dead battery.
**Cause:** the loop recorded the first failure but kept integrating.
**Fix:** break at first failure.
**Impact:** reported min/max temperatures and heater energy for failed designs were
nonsense. It also **hid a real failure mode** — see D4.

### D4 — overheating was a reachable failure that the model could not report
**Found by:** T8, while diagnosing D3
**Symptom:** a 3-cell, 75 mm, 8 W-payload design reached +80 °C and the engine called
it `TEMP_BELOW_OPERATING`.
**Cause:** only a lower temperature limit existed. The 8 W payload dissipates ~4.8 W
*inside* a box whose conductance is 0.032 W/K — at 50 K of ΔT that is only 1.6 W of
loss, so heat accumulates.
**Fix:** added `DEFAULT_MAX_OPERATING_C = 60 °C` and a `TEMP_ABOVE_OPERATING`
failure code with its own explanation and corrective suggestions.
**Impact:** this is a genuine design trade, not an edge case. **More insulation is
not monotonically better.** A whole design grid test (`sweep.py --grid`) confirms it
is not reachable at the modelled 3 W payload load, but it is reachable at 8 W — and
it is now detected rather than mislabelled.

---

## 3. Results of the canonical sweep (post-fix)

`python3 app/sweep.py` — live GFS forecast, Chennai, launch 18:00 IST,
**provenance reported as `LIVE` for both upper-air and solar** (0 % ISA fallback).

| design | verdict | failure | time | min T | heater Wh | UA (W/K) |
|---|---|---|---|---|---|---|
| 6c 10 mm −10 °C 5 W | FAIL | ENERGY_DEPLETED | 00:14 | −17.7 | 24.8 | 0.153 |
| 6c 25 mm −10 °C 5 W | FAIL | ENERGY_DEPLETED | 03:53 | −11.1 | 14.1 | 0.082 |
| 6c 50 mm −10 °C 5 W | PASS | — | — | −11.0 | 1.8 | 0.046 |
| 6c 75 mm −10 °C 5 W | PASS | — | — | +3.9 | 0.0 | 0.032 |
| 8c 25 mm −10 °C 10 W | FAIL | ENERGY_DEPLETED | 07:01 | −11.1 | 19.0 | 0.082 |
| 8c 50 mm 0 °C 10 W | PASS | — | — | −1.1 | 6.1 | 0.046 |
| 10c 25 mm −10 °C 5 W | PASS | — | — | −11.1 | 19.5 | 0.082 |

Grid scan (40 combinations, 4–12 cells × 10/25/50/75 mm × setpoint −10/0 °C):
**21 PASS, 19 FAIL — every failure `ENERGY_DEPLETED`, none cold-driven.**

**This is a change to the story the earlier prototype told.** The old model called
the default design a *cold* failure at 01:23. With thermal mass and an honest
heater-energy balance, the default now dies of **energy**: the heater drains the
pack before the cold can. Insulation thickness moves the time constant from 54 min
to 392 min and is the dominant lever, not heater power. Quoting the old cause on a
slide would be describing a model we no longer use.

---

## 4. Known limitations

Stated because a test report that lists only successes is not a test report.

1. **No bench measurement.** `UA`, the battery curve and the surface conductance are
   unvalidated. Sensitivity analysis (`app/sensitivity.py`) shows the *recommendation*
   survives 2–3× error in the insulation constant; that is a statement about
   robustness of a decision, **not** a validation of a number.
2. **No independent second model in the float band.** ECMWF publishes nothing above
   50 hPa (~20.6 km). Below that, GFS and ECMWF agree to 0.22 K mean. Above 31 km only
   ISA applies, and this is declared in the UI for every run.
3. **Overheating is verified only against the model**, not against a flown payload.
4. **Charts are not tested.** The suite covers the engine. Rendering, layout and
   colour-independence of the PASS/FAIL display are checked by inspection only.
5. **`app/physics.py` is still the module the running application imports.** The
   fixes above are in `app/engine/`. Until the app is repointed, the live UI does
   **not** show these results.
6. **Convergence is asserted, not proven.** T6 checks that halving the timestep moves
   the answer by less than 0.5 K on a flat profile. It does not prove the scheme is
   second-order or that it converges on every possible trajectory.

---

## 5. How to reproduce

```bash
cd /home/user/sedhacks26
python3 -m unittest discover -s tests -v      # 71 tests
python3 app/sweep.py                          # canonical sweep, live data
python3 app/sweep.py --grid                   # 40-combination grid scan
python3 app/validate_atmosphere.py            # GFS vs ECMWF cross-check
```

Tests T9 and the sweep require network access; they fail loudly rather than falling
back to invented data, which is the intended behaviour.
