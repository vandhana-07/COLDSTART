# DECK REBUILD — what changed and why

The `.pptx` you had was generated at 03:03. The physics engine was corrected between
04:14 and 04:21 (see `audit/PHYSICS_AUDIT.md`, addenda 1–3). Nothing propagates
automatically: `ppt/build_ppt.py` does not import the engine, so every number on
every slide is typed by hand into a `FILL` dict. That is why the old deck still
quoted numbers the engine no longer produced — and why one of its slides argued a
case that had become **false**.

This rebuild re-ran the decision frontier on the verified engine and rewrote both
the numbers and the argument.

---

## 1. The old slide-5 argument was invalid, not merely stale

The old deck said:

> "the lazy fix passes, but it breaks at 15 % model error. Our design holds to 30 %."

On the corrected engine that is untrue twice over. The "lazy" 10-cell/10 mm design
**fails outright** — `ENERGY_DEPLETED` at 04:07 on the nominal forecast — so it never
had a tolerance to lose. And the old "our answer" 8-cell/25 mm design now passes
with **less** margin (1.27×) than the cheapest passing design (3.33×) while costing
**more** (₹2973 vs ₹2468).

So the story was replaced rather than re-numbered. The new argument is below.

## 2. The new argument

Two things are now true that were not visible before:

- **Adding batteries to a thin box makes it worse.** More cells means more heat
  capacity, more self-heating and more battery to keep warm. Both designs a team
  builds first fail — and they fail *even when we give them better insulation than
  we assumed*:
  - 6 cells / 10 mm / heater −10 °C → fails at **00:14**, needs foam **5.0× better**
  - 10 cells / 10 mm / heater 0 °C → fails at **04:07** (₹3369), needs foam **1.8× better**

- **The cheapest design that survives is a genuinely good one, but only against the
  forecast as issued.** It holds **50 %** of insulation error and costs **₹2468** —
  yet it survives only **1 of 12** stressed scenarios. ₹4688 buys **12 of 12**.

The slide now states that trade-off explicitly and says, in the same breath, that a
scenario pass rate is **not** a survival probability.

## 3. Every number on the slides is now machine-checked

`app/check_deck.py` re-derives all 16 numeric claims from the engine and prints
`OK` or `*** MISMATCH ***` for each. It exits non-zero on any mismatch.

```
cd app && python3 check_deck.py
```

It earned its keep immediately: it refused to accept "the foam would need to be
4.7× better" (the true value is 5.0×), and it caught that an earlier hand-edit to
that same line had silently done nothing.

`tests/test_deck_consistency.py` (14 tests, part of the suite) makes the same
guarantee permanent, plus three rules that must never regress:

- the bench blanks stay blank until a real measurement exists (FAQ 14);
- none of the superseded numbers can reappear in slide prose;
- the deck may not attach the word "probability" to a scenario count.

## 4. A second failure edge, now disclosed

The engine can fail a design from being **too warm** as well as too cold. A 75 mm
box carrying an 8 W load reaches 60.2 °C at 19:36. The recommendation tolerates foam
50 % *worse* than assumed, but if the foam were 2.5× *better* the box would overheat.
Both edges are measured and both are on the slide, in `KNOWN LIMITS`.

## 5. Layout

Slide 4's template title ("FEASIBILITY & VIABILITY") wraps to two lines and its
second line was being covered by the content card. That slide now uses a larger top
padding (`OFFSET_WRAPPED = 0.42`) measured from the rendered preview. No other slide's
title wraps, so nothing else moved.

---

## How to regenerate

```bash
cd ppt   && python3 build_ppt.py        # writes COLDSTART_SEDHACKS26.pptx
cd ppt   && python3 render_preview.py   # writes preview/slide*.png + a layout check
cd ../app && python3 check_deck.py      # asserts every slide claim against the engine
```

**Run `check_deck.py` every time you touch the engine or the deck.** If it reports a
mismatch, the deck is wrong; do not present it.

## Still hand-typed, still yours to fill

Slide 1 team fields and the slide-4 bench row:

```
"team_name", "team_lead"
"bench_predicted_ua", "bench_measured_ua", "bench_error_pct"   # all None
```

The bench values are `None` on purpose. `bench/bench_test.py` refuses to emit
figures until real measurements are entered, and the slide prints a blank line
instead of a number. When you do run the rig, calibrate `k_ins`, re-run
`check_deck.py` and `frontier.py`, and update the `FILL` block if anything moves.
