# RUN_ME — COLDSTART on a laptop with no internet

Everything here has been run and verified. If a step does not work, the file is
wrong and should be fixed — do not work around it.

---

## 1. What you need

| | |
|---|---|
| **Python** | **3.10 or newer.** Verified on 3.13.16. All app modules parse under the 3.10 grammar. |
| **pip installs** | **NONE.** The app is pure Python standard library — no numpy, no Flask, no requests, nothing to download. This is deliberate: venue wifi is unreliable. |
| **Browser** | Any modern browser (Chrome, Edge, Firefox, Safari). |
| **Internet** | **Not required** if you use snapshot mode (section 4). |

Check your Python:

```
python3 --version      # need 3.10 or higher
```

If that prints 3.9 or lower, install a newer Python first. Nothing else is
needed.

---

## 2. Start it

```
cd sedhacks26/app
python3 server.py
```

You will see:

```
  COLDSTART running
  open  ->  http://localhost:8000
  engine->  coldstart-engine-1.0
```

Open **http://localhost:8000** in your browser.

To use a different port (e.g. if 8000 is taken):

```
PORT=8080 python3 server.py
```

Stop it with **Ctrl+C**.

> **Note:** the server binds to `0.0.0.0`, so it also works if you need to reach
> it from a phone or another laptop on the same network — use
> `http://<your-laptop-ip>:8000`. For a solo laptop demo this does not matter.

---

## 3. The 30-second demo path

1. Open the page. Tab **1 Configure & Run** is already showing.
2. Tick **Use pinned snapshot** (see section 4 — do this if wifi is unreliable).
3. Set **Date** to `2026-10-12`, leave the site at Chennai.
4. Click **Run simulation**. You get a **FAIL** verdict with the exact minute the
   battery dies.
5. Tab **2 Inspect** → scroll to the failure panel: the plain-language chronology
   of *why* it failed, plus which changes would fix it.
6. Tab **3 Optimize** → click to search. It returns the cheapest design that
   actually survives, with its ₹ cost and kg mass.
7. Tab **4 Stress-Test** → shows how many of 12 stressed scenarios each design
   survives. These are **scenario pass rates, not survival probabilities** — the
   app says so on the page, and that wording matters.
8. Tab **7 Verification** → the evidence: 6 benchmarks, 46 checks, and an explicit
   statement that **category E (physical experiment) is empty**.

---

## 4. Running with NO internet (snapshot mode)

This is the mode to use on demo day. The app replays a **frozen file of real API
responses** (`data/demo_snapshot.json`, captured 2026-10-12T06:54:17Z) and makes
**no network call at all**.

**In the browser:** tick **Use pinned snapshot** before clicking Run. Every screen
then shows a `SNAPSHOT <timestamp>` badge so nobody can mistake it for live data.

**Verify it yourself:** turn off wifi, start the server, run with the box ticked.
It works. That test was run by blocking outbound sockets at the OS level — the
snapshot path never attempts a connection.

**From the command line:**

```
cd sedhacks26
python app/verify.py --snapshot        # adds the pinned badge to the results
python app/check_deck.py --snapshot    # asserts the slides still reproduce
python -m unittest discover -s tests   # 199 tests
```

### What happens WITHOUT internet, in order

The app never invents data. It degrades in three clearly labelled steps:

| Situation | What you see |
|---|---|
| Online | Source flagged **LIVE**, with retrieval time |
| Offline, cache present (normal case) | Source flagged **CACHED**, with the original retrieval time and a note that it is the last real response saved to disk |
| Offline, no cache, snapshot OFF | **Refuses to run.** The Run tab shows "Simulation could not run… No numbers are shown because none could be computed from real data. The engine does not fall back to invented values." |
| Any mode, snapshot ON | Source flagged **SNAPSHOT**, exact replay, no network |

> If you have never run the app on this laptop before, the `cache/` folder will be
> empty. Run it once **with internet** before the event, or simply use snapshot
> mode, which needs no cache.

---

## 5. Rebuild / re-verify everything

Run these from the repo root (`sedhacks26/`):

```
python -m unittest discover -s tests     # 199 tests, expect OK
python app/verify.py --snapshot          # 6 benchmarks, 46 checks, 0 failures
python app/check_deck.py --snapshot      # every slide number reproduces
```

Expected results on a correct checkout:

```
unittest  : Ran 199 tests ... OK
verify.py : benchmarks 6 | checks: 46 | failed: none
check_deck: All slide claims reproduce from the engine. Forecast provenance: SNAPSHOT
```

### Optional: the headless browser check

Confirms all 7 tabs load with zero JavaScript errors and that the SNAPSHOT badge
appears in the Run, Inspect, Export and Verification tabs. Needs two extra
packages, so **skip this on demo day if you have not already installed them**:

```
pip install playwright
python -m playwright install chromium
python tests/browser_check.py
```

Expected: `21/21 checks passed`.

### Rebuilding the slides (only if you must)

The `.pptx` is generated, not edited by hand:

```
cd ppt
python3 build_ppt.py          # needs: pip install python-pptx Pillow
python3 render_preview.py     # layout check + PNG previews
```

After any change to the engine, re-run `python app/check_deck.py --snapshot`. If
it reports a mismatch, the slide and the engine disagree — fix one of them
deliberately. **Never hand-edit a number into the slides.**

---

## 6. Where things live

```
app/server.py          web server (stdlib only)
app/data_sources.py    real API fetchers + cache + snapshot reader
app/snapshot.py        writes data/demo_snapshot.json  (needs internet, once)
app/static/index.html  the entire UI, one file, no libraries
app/engine/            THE MODEL — one concern per module:
    params.py          every constant, tagged SOURCE or ASSUMPTION
    mission.py         the flight simulation loop
    thermal.py         conduction, convection, radiation, skin temperature
    battery.py         capacity vs temperature, derating
    optimizer.py       searches for the cheapest PASSING design
    uncertainty.py     stress scenarios + sensitivity
    verification.py    the benchmark suite verify.py runs
ppt/                   slide generator + previews (do not hand-edit)
tests/                 test suite
bench/bench_test.py    bench rig calculator — REFUSES to output until you type in real measurements
audit/                 what was audited, found, and left unfixed
```

`app/physics.py` is the **superseded** model. Nothing imports it. Do not add work to it.

---

## 7. Two rules that must not be broken

1. **No fabricated numbers.** If a value is not measured, it stays blank. The
   bench tool refuses to compute anything until real measurements are entered,
   and evidence category **E (physical experiment) is empty** because no bench
   test has been run. Never fill that in with an estimate.
2. **Never call a scenario pass rate a survival probability.** "12 of 12 stressed
   scenarios passed" is not "100 % survival". The UI states this on the page.
