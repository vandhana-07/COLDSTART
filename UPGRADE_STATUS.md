# COLDSTART — upgrade status

**Date:** 12 October 2026
**Engine:** `coldstart-engine-1.0`
**App:** `cd /home/user/sedhacks26/app && python3 server.py` → `http://localhost:8000`

---

## 1. What was built, in the order the brief required

| Phase | Deliverable | State |
|---|---|---|
| 1 | Physics audit of the existing model | **done** — `audit/PHYSICS_AUDIT.md`, findings A1–A9 |
| 2 | Flight digital twin + automated tests | **done** — `app/engine/`, `tests/`, `tests/TEST_REPORT.md` |
| 3 | Robust optimiser | **done** — `app/engine/optimizer.py` |
| 4 | Timeline + explainable failure replay | **done** — Inspect tab, `engine/mission.py:explain_failure` |
| 5 | Uncertainty / stress engine + Design Battle | **done** — `engine/uncertainty.py`, `engine/battle.py` |
| 6 | Live-data transparency, report export, UI | **done** — transparency block on every response, Export tab |

Everything below is implemented and runs. Nothing is stubbed, and nothing is labelled
"coming soon". Where a feature is narrower than it sounds, that is stated in the code and
in the UI, not hidden.

---

## 2. Verification actually performed

### Automated tests — 71 tests, 71 passed

```
cd /home/user/sedhacks26
python3 -m unittest discover -s tests -v
```

Full detail, including the four real defects the suite caught, in `tests/TEST_REPORT.md`.

### Live-data end-to-end run

Every endpoint exercised against the live GFS forecast for Chennai, 12 Oct 2026:

| Endpoint | Result |
|---|---|
| `/api/health` | GFS **LIVE**, 48 h, ceiling 31.1 km; Celestrak and SWPC also live |
| `/api/plan` | 375 timeline points, provenance recorded, 0 % ISA fallback |
| `/api/stress` | 32 scenarios simulated, 5-parameter sensitivity ranking |
| `/api/job/start` + `/api/job/status` | 250 candidates searched in 22 s with live progress |
| `/api/report` | PASS/FAIL decided from the data actually present; 53 assumptions, 6 limitations |

### UI driven headlessly through jsdom

The page was loaded from the running server, `fetch` was wired to the live API, and every
tab was clicked the way a user would. All six steps render real data:

```
RUN verdict shown : FAIL          RUN transparency : present
INSPECT temp chart: OK 12.7 kB    INSPECT energy   : OK 17.9 kB
STRESS pass rate  : 0 / 32        STRESS disclaimer: present
OPTIMIZE best     : BEST IN SEARCH  OPTIMIZE limits: present
REPORT status     : FAIL          REPORT has limits: yes
JS errors         : 0
```

---

## 3. What a judge can actually do

1. **Configure** — site, date, launch hour, cells, insulation thickness, heater setpoint
   and power limit, payload load, panel area, insulation material, operating limits.
2. **Run** — minute-by-minute integration, timestep derived from the thermal time
   constant, verdict with the exact failure reason and time.
3. **Inspect** — temperature and energy chart with a scrub control, play/pause, and a
   chronological replay of the failure with contributing factors and corrective changes
   you can apply with one button.
4. **Optimize** — 250 candidates through the same engine; best design for each of five
   objectives from a single search; a robustness screen that re-simulates the leaders
   under stress; and the search limits printed underneath, because the search is not
   exhaustive and does not prove global optimality.
5. **Stress-test** — 32 scenarios over five uncertain inputs, a scenario pass rate, a
   ranking of which assumption dominates, and eight named scenarios.
6. **Export** — a full report with methodology, cost/mass breakdown, assumptions and
   limitations; downloadable as JSON or printable to PDF.

---

## 4. Honest results from the new engine

Chennai, 12 Oct 2026, launch 18:00 IST, live GFS, 0 % ISA fallback:

| design | verdict | failure | time | coldest | margin |
|---|---|---|---|---|---|
| 6c 10 mm −10 °C 5 W *(the original default)* | FAIL | ENERGY_DEPLETED | 00:15 | −17.7 °C | 0.99× |
| 6c 25 mm −10 °C 5 W | FAIL | ENERGY_DEPLETED | 03:53 | −11.1 °C | — |
| 6c 75 mm heater off | PASS | — | — | +3.9 °C | 3.33× |
| 9c 85 mm heater off | PASS | — | — | — | 8.12× |

Optimiser output, one search: cheapest pass **₹2468**, best balance **₹2788**,
most robust **₹4488** (passed 16/16 stressed scenarios against the cheapest pass's 1/16).

**The failure mechanism is ENERGY, not cold.** The heater drains the pack long before the
cold would. Insulation thickness is the dominant lever — it moves the thermal time
constant from 54 to 392 minutes across the 10–75 mm range.

---

## 5. Limitations that must stay attached to any claim

1. **Box conductance is UNVALIDATED.** `UA` is derived from an assumed foam conductivity.
   Absolute survival times are indicative; the *comparison between designs* is the
   reliable output. The bench rig to fix this was not built.
2. **The battery capacity curve is UNVALIDATED** — datasheet values, not these cells.
3. **Stress percentages are scenario pass rates**, not probabilities of real-world
   survival. The wording is generated by `engine/uncertainty.py` so it cannot drift.
4. **The optimiser is not exhaustive** (250 of a 192-point grid plus local refinement).
   It does not prove global optimality, and says so in its own output.
5. **Above 31.1 km only ISA applies**, and the simulation reports how many minutes did so.
6. **Overheating is modelled but unvalidated** — added in this upgrade after tests
   revealed it was reachable and being mislabelled as a cold failure.
7. **The failure replay is an explanation of the model**, not a record of a real flight.

---

## 6. OUTSTANDING — the deck no longer matches the engine

**This needs a decision before the presentation.**

`ppt/build_ppt.py` still carries numbers from the legacy `app/physics.py` model:

| Deck value | Legacy model | Current engine |
|---|---|---|
| Failure time of the default design | 01:23 | **00:15** |
| Hours survived | 7.4 | **6.25** |
| Recommended design cost | ₹2210 | **₹2788** (best balance) / ₹2468 (cheapest pass) |
| "Lazy fix" cost | ₹2584 | — |

The *narrative* is still right — the deck already says "charge exhausted", and the engine
confirms energy is the mechanism. The *numbers* are stale, and they come from a model with
the A9 radiation defect and a box area 2.5× smaller than the real one.

Two options:

- **(a) Re-derive the deck from the engine.** Re-run the sensitivity frontier on the new
  engine, update the `FILL` block, rebuild the deck. Numbers then match what the demo
  shows. The headline "₹80 more" comparison will change.
- **(b) Keep the deck as-is** and accept that the slide and the live demo disagree by
  about an hour and a few hundred rupees, with a stale sentence explaining why.

Option (a) is the only one consistent with "never present numbers you cannot defend".

> **RESOLVED — option (a) was chosen and executed.** The deck was rebuilt on the
> verified engine; both the numbers and the slide-5 argument were replaced. See
> `ppt/REBUILD_NOTES.md` for what changed and `audit/PHYSICS_AUDIT.md` ADDENDUM 3
> for the defects found while doing it. Nothing below this line is still open.


---

## Session: deck rebuilt on the verified engine (2026-10-12)

**Engine defects fixed and audited** (`audit/PHYSICS_AUDIT.md`, ADDENDUM 3):

- **A14** — `isa_pressure_hpa()` was missing the `/g` in the isothermal scale height,
  returning 177.8 hPa at 26 km instead of ~21 hPa. Display-only helper, not on the
  simulation path; fixed and regression-tested against published ISA to 1 %.
- **A15** — the integrator did not stop at the first constraint violation, so
  post-failure temperatures were reported as flight data and the failure mechanism
  could be misordered. The default design now correctly reads `ENERGY_DEPLETED at
  00:14` rather than failing cold.
- **A16** — `max_box_c` was never returned, so an overheating box could not be
  reported. Over-insulation is a real second failure edge; both edges are now
  measured and disclosed.

**Tooling added**

- `app/frontier.py` — maps the insulation-error axis for each candidate design and
  reports BOTH edges (too cold / too hot). Never a single flip point.
- `app/check_deck.py` — re-derives all 16 slide claims from the engine; non-zero exit
  on any mismatch. `ppt/build_ppt.py` does not import the engine, so without this the
  deck drifts silently. It caught two real errors on first run.
- `tests/test_deck_consistency.py` — 14 tests making that guarantee permanent.

**Restored** — `app/engine/optimizer.py` was overwritten during this session and has
been rebuilt to the interface `server.py`, `frontier.py` and `battle.py` require
(`objective_text`, `picks`, `robust_pick`, `violation_counts`, `search_limits`,
`top_passing`, `screened`, `screen_robustness`), keeping the improved search limits
and the honest "not optimal" labelling.

**Verified state**

- `python3 -m unittest discover -s tests` → **126 tests, OK**
- `python3 verify.py` → 6 benchmarks / 46 checks / 0 failures / 9 unresolved
- `python3 check_deck.py` → all 16 slide claims reproduce, forecast LIVE
- headless UI run → 14 verification panels, report includes verification evidence,
  category E declared NOT PERFORMED, **0 JS errors**
- `ppt/COLDSTART_SEDHACKS26.pptx` + `ppt/preview/slide*.png` rebuilt; layout check clean

**Deck narrative replaced** — see `ppt/REBUILD_NOTES.md`. The old slide-5 argument
("lazy fix breaks at 15 %, ours holds to 30 %") was false on the verified engine and
has been removed, not re-numbered.

**No new bench test was run. Category E remains empty.**
