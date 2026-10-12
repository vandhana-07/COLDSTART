# COLDSTART — Audit Final Report

**Date:** 12 October 2026
**Repo:** `/home/user/sedhacks26` (baseline tag `baseline` → commit `88f672b`)
**Scope:** Tasks A–E of the audit, the unknown-objective defect, and demo snapshot mode.
**Rule applied throughout:** smallest change that fixes the issue. No module rewritten, no file
renamed, no feature added beyond those requested. Evidence category **E (physical experiment)
remains EMPTY** — no bench test has been run at any point.

---

## 1. Test / verify / check_deck counts, before and after

"Before" was measured by checking the **baseline commit `88f672b`** out into a separate
`git worktree` and running the three commands there today. That makes the comparison
apples-to-apples: same machine, same network conditions, same live forecast.

| Command | Before (baseline `88f672b`) | After (HEAD `dc085b3`) |
|---|---|---|
| `python -m unittest discover -s tests` | **126 tests, 2 failed** | **199 tests, 2 failed** |
| `python app/verify.py` | 6 benchmarks / 46 checks / **0 failures**; residuals within tolerance; state audit clean; convergence default_fails_energy order 1.43, cheapest_passing order 1.69; ranking **FLIPS ×2** | **identical** to the left |
| `python app/check_deck.py` | **2 mismatches** (`rec_margin`, `lazy_fail_time`) | **2 mismatches** — the same two |

Test files: 3 → 9. New files added: `test_night_dip.py` (13), `test_optimizer_bruteforce.py` (16),
`test_radiation.py` (19), `test_bench_refusal.py` (4), `test_api_validation.py` (7),
`test_snapshot_mode.py` (12); `test_verification.py` grew 41 → 43.

### The 2 failures and 2 mismatches are NOT caused by this audit

This was the single most important thing to establish. The **baseline commit, run today, fails
the same two tests and mismatches the same two deck numbers** as the current code. The cause is
that the live GFS forecast was re-fetched and changed between the moment the deck was rendered
and now:

| claim | deck | engine (today) |
|---|---|---|
| `rec_margin` | 3.33× | 3.35× |
| `lazy_fail_time` | 04:07 | 04:05 |

An A/B test was also run on the current tree: my Task C edits were reverted in place, `check_deck`
re-run, and the same two mismatches appeared; the edits were then restored and verified
byte-identical. Both tests independently confirm the numbers moved because the *data* moved, not
because the *code* moved.

**This is exactly the problem demo snapshot mode (item 4) exists to fix.** The deck numbers remain
editable-only-by-the-team; per instruction, **no slide file was touched**.

---

## 2. Per-task findings

### Task A — independent brute-force verification of `optimizer.py`

**Found.** The rebuild's own unit tests could share its mistakes, so `optimizer.py` was verified
against a full-mission brute force that never calls the optimiser. One real defect surfaced: an
**unknown objective string did not raise**. `optimise()` filtered its objective list *before*
reaching `_pick_best`'s guard, so a typo silently produced results for the default objective — a
confident, wrong answer.

**Changed.** `app/engine/optimizer.py::optimise()` now validates `objective` up front and raises
`ValueError` naming the offender and listing the valid keys. `tests/test_optimizer_bruteforce.py`
(16 tests) added: on an 8-candidate grid it runs the full mission simulation for every candidate
directly and asserts the optimiser returns the same winner for min-cost, min-mass, highest-margin
and all five exposed objectives; that ties break deterministically; that no PASS design cheaper or
lighter than the returned one exists; and that `search_limits()`'s candidate count equals the
number of designs actually simulated.

**Not changed.** The searched design space itself. The optimiser searches a declared grid
(5 cell counts × 5 insulation thicknesses × 5 heater settings × 2 panel areas = 250 candidates),
not a continuous space, so it does **not** prove global optimality. That limitation was already
stated in the UI and the report and remains stated.

### Task B — night length at float altitude

**Found.** The night length was computed at the **ground horizon** by counting whole hours, giving
13 h. The horizon dip — `dip = arccos(R_earth / (R_earth + h))` — was not applied. Hourly sampling
was also the *larger* of the two errors: it quantises the answer by up to ±1 h, which is bigger
than the dip correction it was hiding.

**Changed.** `app/engine/params.py` gained
`EARTH_RADIUS_KM = 6371.0  # SOURCE: IUGG mean Earth radius 6371.0088 km`.
`app/data_sources.py`'s night block was replaced with a **1-minute-resolution dip-corrected scan**
at threshold `elevation <= -dip`, and a stale `from physics import ...` (the superseded model) was
removed in favour of `engine.atmosphere.solar_elevation_deg` and `engine.params`.
`tests/test_night_dip.py` (13 tests) added.

**Not changed.** The mission-window definition — the engine was already deciding day/night for
itself, per timestep, from the sun's elevation (`app/engine/mission.py:221`).

### Task C — radiation audit

See sections 3(c) and 3(d) below for the exact lines. In summary: the outgoing radiation **does**
use the outer skin temperature; insulation **does** lower the radiative loss but **never** removes
it; and upwelling Earth IR is **not modelled** (reported, not added, per instruction).

**Found.** A documentation defect: `thermal.py::radiant_temperature_c`'s docstring claimed the
radiant offset "is exposed to the user and is a named axis of the stress-test engine". It was in
`verify.py`'s one-at-a-time sweep but **absent from `app/engine/uncertainty.py::UNCERTAIN_INPUTS`** —
so the dominant radiative uncertainty was neither stressed nor ranked by the app.

**Changed.** `uncertainty.py` gained the axis `radiant_offset_c` (lo 0.0 K, hi 20.0 K, Halton base
13) with an `# ASSUMPTION:` comment, **and — critically — `_apply()` now actually writes the factor
into the design.** Without that second edit the axis would have been sampled and silently ignored:
a no-op that leaves every "stressed" scenario identical to the nominal case. This was caught by a
test (`test_the_axis_is_actually_applied_and_not_a_silent_no_op`) after an initial measurement
attempt returned implausible results. `tests/test_radiation.py` (19 tests) added, including the
required proof that doubling insulation lowers radiative loss but never to zero.

**Not changed.** No explicit Earth-IR term was added (item 3c says do not add it now).
`DEFAULT_RADIANT_OFFSET_C` was left at 10.0 K with its original tag; because no second term exists,
there is no double-counting to re-derive.

**Measured impact of the new axis:** the cheap design stays **1 of 12** stressed scenarios passing
(ENERGY_DEPLETED ×11) and the robust design stays **12 of 12**; the five original axes are
bit-identical per index. **No deck number moves.** `verify.py`'s uncertainty section still reports
**FLIPS ×2**.

### Task D — solar-heating wording

**Found.** The disclosure existed in `verify.py` in a different form ("SOLAR HEATING OF THE
STRUCTURE IS NOT MODELLED…") and was **entirely absent from the Export report**. An existing test
asserted the old string, so a wording change would have failed the suite rather than passed silently.

**Changed.** The exact required sentence now appears in both required places:

> **Solar heating of the enclosure is not modelled; daytime results are biased cold. Night survival results are unaffected.**

- **Export report** — `app/server.py::build_report()`, first entry of the `limitations` list.
- **Verification tab** — `app/verify.py::main()`, the `unresolved` list, which the UI renders at
  `index.html:1491`. `verify/results.json` was regenerated so the tab shows it.

`tests/test_verification.py` gained three tests pinning the sentence in `verify.py`, in
`build_report()`, and in the `results.json` the UI actually reads — so it can neither be softened
into vagueness nor lost when the results file is regenerated.

**Not changed.** No solar heating was added. The model still computes solar **electrical**
generation only.

### Task E — cleanup

**Found.** `README.md` pointed at the superseded `app/physics.py` and listed no test/verify
commands. `app/sensitivity.py:26` still imports the legacy `physics` module.

**Changed.** `README.md` now documents `app/engine/` module by module, lists the current run/test/
verify/check_deck commands, explains that `verify.py` writes `verify/results.json` (which the
Verification tab reads, so a stale file shows stale numbers), and states plainly that
`app/physics.py` is superseded and must not receive new work.

**Bench refusal — confirmed empirically, then pinned.** `bench/bench_test.py` was executed: its
`RUNS` table is empty, it prints `NO MEASUREMENTS YET - nothing to calculate.`, and it returns
**before** computing any figure. No measurement table, no error %, no measured UA is emitted.
`tests/test_bench_refusal.py` (4 tests) now asserts all of this, including that a fabricated row in
`RUNS` would fail the suite. **Evidence category E stays empty.**

**Not changed.** Nothing under `ppt/`. No slide file was read-modify-written in this task or any other.

### Item 3 — unknown-objective defect

**Found.** Fixed at the engine level in Task A, but the **API** still started a background optimise
job and only surfaced the failure later as a generic job error — after paying for a forecast fetch.

**Changed.** `app/server.py`'s `/api/job/start` now validates the objective **before** `build_env()`
and returns `400` with the offending value and the list of valid objectives.
`tests/test_api_validation.py` (7 tests) boots the real stdlib server on an ephemeral port and
asserts over HTTP that `objective=cheapest` gives a 400 with a hint, that `kind=battle` is validated
too, that a rejected request starts no job, and that an unknown job kind is still a 400.

**Not changed.** `_run_job`'s existing exception handling — still the backstop for any other error.

### Item 4 — demo snapshot mode

**a) Pinned.** `app/snapshot.py` (new) captured **4 live feeds** — GFS upper-air, GFS solar, and the
ECMWF **and** GFS cross-check series — into `data/demo_snapshot.json` (77 KB), stamped
`retrieved_utc: 2026-10-12T06:54:17Z`, each feed carrying the URL and model it came from. It is a
live-only fetch: there is deliberately no cached fallback, because a snapshot labelled LIVE that was
served from an old cache would be a lie about provenance.

**b) Flag/toggle.** `fetch_environment(lat, lon, date, snapshot=False)` and `_get_json(..., snapshot=False)`
read only that file and make **no network call at all**. The mode is passed **per request**
(`?snapshot=1`), not held in a module global, so two browser tabs cannot disagree and a stale tab
cannot report pinned data as live. A UI checkbox **"Use pinned snapshot"** drives it.

**c) Badge.** `SNAPSHOT <retrieved_utc>` is rendered from a single `snapBadge()` component in the
**UI** (Run tab banner + flag, Inspect tab), the **Export report** (header and provenance panel),
and the **Verification tab** (status line and a banner at the top of the results).
`verify/results.json` gained a `snapshot` block of the same shape, and `RESULTS.md` carries the
badge too.

**d) Default unchanged.** Live-first with a labelled CACHED fallback remains the default;
`inspect.signature` asserts `snapshot` defaults to `False`. The shipped `verify/results.json` was
regenerated in **LIVE** mode so the committed artefact matches the default behaviour.

**e) Verification in snapshot mode.** `unittest` **199 tests / 2 failed** (same two);
`verify.py --snapshot` → **6 benchmarks / 46 checks / 0 failures**, residuals within tolerance,
state audit clean, convergence orders 1.43 / 1.69, **FLIPS ×2** — identical to live;
`check_deck.py --snapshot` → the same 2 mismatches as live. A `diff` of live vs snapshot
`check_deck` output was **empty**, which is the proof that the snapshot reproduces live bit-for-bit.
Offline was proven by monkeypatching `urllib.request.urlopen` to raise: replay still succeeded and
`hours`, `profiles`, `solar_by_index` and `night_hours` were all identical to the live fetch.

`tests/test_snapshot_mode.py` (12 tests) pins: no network in snapshot mode; a missing feed raises
naming the feed and stating nothing was invented; a missing file names `snapshot.py`; replay is
deterministic; the payloads are real time series, not filler; both cross-check models are present;
and the badge is a greppable string. 3 further tests in `test_api_validation.py` cover the toggle
end to end over HTTP.

---

## 3. The three specific questions

### (b) Night length — Chennai, 12 October 2026, at float altitude

Horizon dip at the 26.0 km float altitude: **5.1675°** (from `EARTH_RADIUS_KM = 6371.0`, dip =
arccos(R/(R+h))).

| | ground horizon (elev ≤ 0°) | **float horizon (elev ≤ −5.168°)** |
|---|---|---|
| night starts (sunset) | 17:49 IST, 12 Oct | **18:11 IST, 12 Oct** |
| night ends (sunrise) | 06:02 IST, 13 Oct | **05:41 IST, 13 Oct** |
| **duration** | 12.22 h | **11.50 h** |

**Correction: +22 minutes of daylight at each end, night shorter by 0.72 h.**

**The old "13 h" definition, stated exactly:** it was the **whole-hour count of ground-level dark
hours within the calendar day** — i.e. the number of hours `h` in 0…23 for which the sun's elevation
at that ground location was ≤ 0°. It is *not* a twilight definition and *not* the mission window.
The old figure decomposes as **13 h → 11.5 h = −0.78 h hourly quantisation + −0.72 h horizon dip**.
The quantisation term is the larger of the two, which is why the scan had to move to 1-minute
resolution for the dip to be visible at all.

**Where `night_hours` is used, and the survival-result question.** It is written at
`data_sources.py:227` and only ever **reported**: `engine/mission.py:380`, `engine/battle.py:130`,
`server.py:149` and `:243`, `sweep.py:93`, and the superseded `physics.py:257`.
**It is not an input to any physics.** The simulation decides day/night for itself, per timestep,
from the sun's elevation (`engine/mission.py:221`). `tests/test_night_dip.py` proves the
independence directly: forcing `night_hours` to 99.0 instead of 11.5 leaves `verdict`,
`failure_time`, `min_box_c` and `survival_hours` **identical**. **No survival result depended on it,
and no survival result moved when it was corrected.** `app/check_deck.py` does not check the night
length at all, so this change could not have failed the checker — which is precisely why it is
reported here rather than caught automatically.

### (c) Upwelling Earth infrared — **not modelled. State plainly: it does not exist.**

`app/engine/thermal.py` contains **no Earth-IR term, no view factor and no albedo term**. A grep for
`earth|albedo|view|solar` across `thermal.py` returns only `emissivity` lines. The exact lines are:

```python
# app/engine/thermal.py:101  (inside radiant_temperature_c)
    return min(t_ambient_c - radiant_offset_c, t_ambient_c)

# app/engine/thermal.py:102
def _radiation_from_skin_w(t_skin_c, t_radiant_c, area_m2, emissivity):
    t_skin_k = P.c_to_k(t_skin_c)
    t_rad_k = max(P.c_to_k(t_radiant_c), P.T_SPACE_K)
    return emissivity * P.STEFAN_BOLTZMANN * area_m2 * (t_skin_k ** 4 - t_rad_k ** 4)
```

**View factor and value used: there is none.** The only view-factor-named constant in the project is
`DEFAULT_PANEL_VIEW_FACTOR = 0.70` (`params.py:132`), and it belongs to the **solar PV** path
(`atmosphere.py:90`), not to the infrared path. It is not read by `thermal.py` at all.

What stands in for Earth IR is a single **lumped effective sky temperature**:

| quantity | value | tag |
|---|---|---|
| effective sink | `ambient − radiant_offset_c`, floored at `T_SPACE_K` | — |
| `DEFAULT_RADIANT_OFFSET_C` | 10.0 K | **ASSUMPTION** (`params.py:99`) |
| `T_SPACE_K` | 3.0 K | floor inside `_radiation_from_skin_w` |
| `DEFAULT_EMISSIVITY` | 0.90 | `params.py:101` |

**The sky is therefore NOT treated as ≈ 0 K, and radiative loss is not automatically
overestimated.** At a −52.5 °C float ambient the effective sink is **−62.5 °C ≈ 210.6 K** — a warm
sink implying only ~11 % of the black-body flux to deep space. That is the honest reading of the
model. Whether it is high or low is genuinely unknown, because the real environment is a mix of
~200–260 W/m² upwelling longwave from the Earth (which fills roughly 55 % of the view at a 5.17°
horizon dip) and near-0 K space in the remaining ~45 %. A first-order view-weighted estimate puts
the sink at **209–225 K**, i.e. between roughly **−3 K and +12 K** relative to that air temperature.

Two consequences, stated honestly:
1. The default **+10 K** sits at the **cold, loss-overestimating end** of that estimate — the
   conservative direction for a cold-survival question.
2. That estimate reaches **below the axis floor of 0 K**. The declared range 0.0–20.0 K therefore
   does not cover the full plausible envelope at its warm end. **This is a known open question, not
   an oversight** — it is documented in `uncertainty.py` and below in section 5.

Per instruction, **no explicit Earth-IR term was added.** If one is ever added, the parameterisation
must be removed or re-derived rather than kept alongside it, or the design would be credited twice.

### (d) Radiation uses the skin temperature, not the air temperature

Exact line, `app/engine/thermal.py:102`:

```python
return emissivity * P.STEFAN_BOLTZMANN * area_m2 * (t_skin_k ** 4 - t_rad_k ** 4)
```

with, on line 100, `t_skin_k = P.c_to_k(t_skin_c)`. The radiating node is the **outer skin**, not
`t_box` and not `t_ambient`. The skin temperature itself is solved by bisection in
`skin_temperature_c()` on the series chain **conduction → skin → (radiation + convection)**.
`tests/test_radiation.py` pins this three ways: that skin ≠ box and skin ≠ ambient, that radiating
at `t_box` would overstate the loss by >20 % at 10 mm, and a source-level assertion that
`skin_temperature_c` still calls `_radiation_from_skin_w(t_skin, …)`.

Insulation lowers the skin temperature — so it lowers the radiative loss — but **never removes the
term**: `conduction_ua` floors thickness at `max(insulation_mm, 1.0)`, so as UA → 0 the skin floats
to its own radiative/convective equilibrium rather than collapsing to ambient. The tests assert
positive radiative loss at 5, 10, 20, 50, 75, 150, 300 and 1000 mm, and monotonic decrease with
thickness.

---

## 4. Every number the slides quote, in snapshot mode

`check_deck.py --snapshot` was the source. **No slide was edited.**

| # | claim on the slide | slide value | engine (snapshot mode) | matches? |
|---|---|---|---|---|
| 1 | default 6c/10 mm FAIL time | `00:14` | 00:14 | ✅ |
| 2 | default FAIL at hours | 6.2 | 6.23 | ✅ |
| 3 | default design cost | ₹2369 | 2369.0 | ✅ |
| 4 | cheapest-passing cost | ₹2468 | 2468.0 | ✅ |
| 5 | cheapest-passing mass | 0.75 kg | 0.748 | ✅ |
| 6 | cheapest-passing energy margin | **3.33×** | **3.35** | ❌ **mismatch** |
| 7 | "lazy" 10c cost | ₹3369 | 3369.0 | ✅ |
| 8 | "lazy" 10c FAIL time | **04:07** | **04:05** | ❌ **mismatch** |
| 9 | "lazy" foam deficit | 1.8× | 1.8 | ✅ |
| 10 | default foam deficit | 5.0× | 5.0 | ✅ |
| 11 | robust design cost | ₹4688 | 4688.0 | ✅ |
| 12 | robust energy margin | 7.40× | 7.41 | ✅ |
| 13 | robust cells | 12 | 12 | ✅ |
| 14 | cheapest stressed scenarios | 1 of 12 | 1 of 12 | ✅ |
| 15 | robust stressed scenarios | 12 of 12 | 12 of 12 | ✅ |
| 16 | insulation-error tolerance | 50 % | 50.0 | ✅ |
| 17 | ₹ premium of the robust pick | ₹2220 | 4688 − 2468 = 2220 | ✅ (arithmetic on two ✅ costs) |
| 18 | overheat upper edge | "roughly 2.5× better" | passes 0.40×–1.50×; overheats below 0.40× → 2.5× | ✅ |
| 19 | search size | "250 candidates" | 250 evaluated, 123 feasible | ✅ |
| 20 | float altitude | **26.5 km** | GFS 20 hPa level today at **26.40 km** | ⚠️ 0.1 km high |
| 21 | air temperature | **−52.5 C** | **−51.5 °C** at 20 hPa/26.40 km; −52.5 °C is at 200 hPa/11.80 km | ❌ **wrong level** |
| 22 | night length | **13 h** | **11.5 h** | ❌ **not updated** |
| 23 | ECMWF agreement | "mean of **0.2 K**" | **0.32 K** mean over 12 levels; worst 1.90 K; float band 1 level, 1.00 K | ❌ **not reproducible** |
| — | bench UA (predicted/measured/error) | blank | `None` → rendered blank | ✅ intentionally blank |

**All numbers labelled ✅ in rows 1–19 also reproduced from the baseline commit**, so the audit did
not move any of them. Rows 20–23 are *not* covered by `check_deck.py` and were found by hand; they
are reported here rather than silently fixed, per instruction.

Notes on the four that do not match:
- **Rows 6 and 8** are the forecast-drift pair proven in section 1. Fixing them requires re-rendering
  the deck from the current (or pinned) forecast — a slide edit, which was out of scope here.
- **Rows 20–21** are a labelling issue, not a broken computation. The card pairs "26.5 km float
  altitude (real GFS 20 hPa level)" with "−52.5 C forecast air temperature on 12 Oct over Chennai".
  The −52.5 °C figure is a real forecast value — but for the **200 hPa / 11.8 km** level, not the
  float band. Side by side, the two cards read as one statement about float altitude.
- **Row 22** uses the superseded whole-hour ground definition (detail in section 3(b)).
- **Row 23** is a live-value that moved with the forecast; it is also outside `check_deck.py`.

---

## 5. New ASSUMPTIONs introduced, and problems found but not fixed

### New ASSUMPTIONs introduced (2)

1. **`radiant_offset_c` uncertainty range: lo 0.0 K, hi 20.0 K** — `app/engine/uncertainty.py`,
   tagged `# ASSUMPTION` with the rationale inline. **This range was not invented**: it is reused
   verbatim from the sweep that already existed in `verify.py` Task 6, so a new range was not
   fabricated for the app while an older one was in use elsewhere. The accompanying comment states
   openly that a first-order view-factor estimate reaches *below* the 0 K floor, so the range is a
   deliberate, documented choice rather than a claim of completeness.
2. **`EARTH_RADIUS_KM = 6371.0` is tagged `# SOURCE:` (IUGG mean radius 6371.0088 km), not
   ASSUMPTION** — recorded here so the distinction is explicit. It is the only new physical constant
   added since the baseline; `git diff 88f672b -- app/engine/params.py` shows exactly one added
   assignment.

No other constants were introduced. Snapshot mode, the ISA correction and the API validation added
no physical values.

### Problems found but NOT fixed

| # | Problem | Why not fixed |
|---|---|---|
| 1 | Deck `rec_margin` 3.33× and `lazy_fail_time` 04:07 do not reproduce (engine 3.35× / 04:05) | Cause is the re-fetched live forecast, proven by the baseline and A/B runs. Fixing means editing slides — explicitly out of scope. Snapshot mode now prevents recurrence. |
| 2 | Deck says "**13 h**" night in three places | Task B–E forbade slide edits. Reported; the engine value is 11.5 h. |
| 3 | Deck "**0.2 K**" ECMWF agreement vs 0.32 K today | Not covered by `check_deck.py`; a slide edit. Also drifts with the forecast. |
| 4 | Deck "**−52.5 C**" card is the 200 hPa (11.8 km) temperature, adjacent to the 26.5 km card | Slide edit; the value is real but the altitude is unstated and misleading in context. |
| 5 | Deck "**26.5 km**" vs today's 26.40 km | Slide edit. 0.1 km, and it moves with the forecast. |
| 6 | Deck's search description "**4 × 4 × 3 × 2 × 2**" multiplies to 192, but the deck also says 250 candidates | The **total is correct** (250 = 5 cells × 5 insulation × 5 heater settings × 2 panels); the factorisation is wrong. Slide edit. |
| 7 | **No explicit Earth-IR term and no view factor** | Item 3c says do not add it now. Reported in full in section 3(c). |
| 8 | `radiant_offset_c` range floor (0 K) is **warmer than** a first-order view-factor estimate (−3 K) | Deliberately not widened: changing it would move the stress-test numbers and is a modelling decision for the team, not an audit fix. Documented in the code comment. |
| 9 | **`tests/TEST_REPORT.md` header says "71 tests"** | Stale: the baseline suite was actually **126** tests (71 in `test_engine.py` alone, plus 41 + 14). It now describes a suite that is 199 tests. Doc-only; left for the team. |
| 10 | **`app/sensitivity.py:26` still imports the legacy `physics` module** | It imports and runs, but it is a second, parallel implementation of the sensitivity analysis using the superseded model. Task E scoped only the README and the bench check. It is a live inconsistency: the app UI uses `engine/uncertainty.py`, this script uses `physics.py`. |
| 11 | `START_HERE.md` and `SEDHACKS26_playbook.md` still reference `app/physics.py` | Task E scoped `README.md` only. |
| 12 | The thermal energy-balance residual is **identically zero by construction** for forward Euler | Not a defect but a labelling risk: it validates *bookkeeping* (nothing double-counted, no clamp fired) and is **not** an accuracy measure. `verify.py` already says so in its unresolved list; flagged so it is never quoted as a physics validation. |
| 13 | **ISA diverges from the published standard atmosphere above ~20 km** | Pre-existing and already documented in the benchmark suite (B1). Not a regression. |
| 14 | Contract/convection coefficient `h0` and box UA remain **UNVALIDATED** | No bench test has been run. Evidence category **E stays empty** by instruction. `bench/bench_test.py` refuses to emit figures until real measurements are entered, and now cannot regress. |

---

## 6. `git log --oneline`

```
dc085b3 Demo snapshot mode: pinned real-forecast replay with SNAPSHOT badge in UI, report and verification tab
72c7555 Reject unknown optimise objective with a 400 at the API, not a late job error
2442a21 Task E: README points at app/engine/, current commands, bench refusal pinned by tests
cdfb5d8 Task D: solar-heating disclosure in Export report and Verification tab, pinned by tests
c52839d Task C: radiation audit - declare radiant sink as a stress axis, pin skin-temperature behaviour with tests
0bc7f0b Task B: horizon dip at float altitude for night duration
2ae9c09 Task A: optimizer brute-force verification
125d9d8 Add git safety net: restore_git.sh (tested) and working rules
88f672b baseline before audit
```

Annotated tag **`baseline`** → `88f672b`. Working tree clean. A transient `git worktree` at
`/tmp/baseline88` was used to measure the pre-audit counts and has been removed and pruned.

**Commits in this session:** `72c7555` (unknown objective), `dc085b3` (snapshot mode).
`2442a21` was Task E, `cdfb5d8` Task D, `c52839d` Task C.

---

## 7. One-line summary

The audit's four fixes (night horizon dip, radiation axis, solar-heating disclosure, README/bench
integrity) plus the objective-validation and snapshot-mode additions left **every number on the
slides that the engine could reproduce still reproducing** — the two exceptions were already broken
at the baseline commit because the live forecast moved under them, which is now preventable via the
pinned snapshot. Four further slide numbers that `check_deck.py` does not cover (night length,
ECMWF agreement, float altitude, and the −52.5 °C card's altitude) do not reproduce today and are
listed above rather than edited.
