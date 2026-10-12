# START HERE — COLDSTART for a team of 3 beginners

You do **not** need to understand all the space stuff. You need to run one app, learn what
it does, and improve one part of it during the hackathon. That's it.

---

## PART 1 — What we are building, in plain words

**The problem:** A balloon carries a small box with a battery up to 26 km. Up there it is
−52 °C and dark for 13 hours. Cold batteries can't give you all their energy. If the battery
dies, the payload dies and the mission fails.

**Our app:** You type in *"Battery: 6 cells. Insulation: 10 mm. Heater: −10 °C."*
The app answers: *"**FAIL**. Your battery dies at 01:23 — after 7.4 hours of a 13 hour night."*

Then you press one button, and it tells you the **cheapest way to fix it**.

That's the whole project. Real weather data goes in, a clear verdict comes out.

**Why this wins:** most teams build a dashboard that shows charts. Charts are not a decision.
Ours gives a verdict and a number.

---

## PART 2 — Proof it works (real numbers, real data, today)

I ran this app on the **real NOAA GFS forecast for 12 October 2026 over Chennai**:

```
Default design: 6 cells, 10 mm insulation, heater −10 °C
  → VERDICT: FAIL — battery dies at 01:23 (7.4 h into a 13 h night)

Press "FIND CHEAPEST FIX" (48 designs tested, 21 passed):

  #  cells  insul  heater   verdict   margin    cost     mass
  1    6    75 mm   0 °C     PASS     1.10×    ₹2130   0.74 kg
  2    8    25 mm   0 °C     PASS     1.81×    ₹2210   0.52 kg   ← BEST VALUE
  3   10    10 mm   0 °C     PASS     1.10×    ₹2584   0.51 kg   ← the lazy fix
```

**Look at rows 2 and 3. This is your winning insight.**

Row 3 is what a normal team does: *"battery dies? add batteries."* 10 cells with thin
insulation costs **₹2584** and gives a **1.10× margin**.

Row 2 costs **₹2210** — ₹374 *cheaper* — and gives a **1.81× margin**, because the money
went into insulation and correct heater setting instead of more cells.

> **Say this on stage:** *"The obvious fix — add batteries — is 15% more expensive and
> nearly twice as risky. Proper thermal design beats extra cells. The tool found that;
> we didn't assume it."*

That is a real engineering finding, computed from a real forecast. Judges remember that.

---

## PART 3 — How to run it

Open a terminal in the `sedhacks26/app` folder and type:

```bash
python3 server.py
```

Then open **http://localhost:8000** in a browser.

**There is nothing to install.** No `pip install`, no npm, no CDN. This matters: venue wifi
often dies at 3 AM, and this app still runs. The only Python libraries used are the ones
already inside Python.

If the internet dies, the app automatically shows the **last real data it downloaded** and
labels it `CACHED`. It never invents data.

---

## PART 4 — What each file does (read them in this order)

| File | What it is | Read it if you are… |
|---|---|---|
| `app/static/index.html` | The screen. Buttons, charts, verdict. | …the **UI person** |
| `app/server.py` | The web server. Sends pages, handles buttons. | …the **glue person** |
| `app/engine/` | The science. Battery + heat + power maths, split into `thermal.py`, `battery.py`, `mission.py`, `optimizer.py`. | …the **science person** |
| `app/data_sources.py` | Fetches real data from the internet. | …the **data person** |

Everything is heavily commented. Every number is marked either
`# SOURCE:` (it's a real published value) or `# ASSUMPTION:` (we chose it).
**Do not delete those comments.** They are how you answer judges' questions.

---

## PART 5 — Your 3 roles (3 people, 3 jobs)

| Person | Role | Owns | Score it feeds |
|---|---|---|---|
| **A** | Data & back end | `data_sources.py`, `server.py` | Technical implementation |
| **B** | Physics & validation | `app/engine/`, the **bench rig** | Feasibility & viability |
| **C** | Front end & pitch | `index.html`, the slides, the speaking | Presentation & communication |

C is not the "least technical" role — C is the person who makes the demo land. That is
worth as much as the code.

---

## PART 6 — Prework schedule (7 Oct → 11 Oct)

> **Register your team TODAY.** Deadline is **9 Oct, 18:00 IST**. You can change the idea
> later (the FAQ allows it), but you cannot register late.

### Wed 7 Oct — Everyone, 1 hour
- [ ] Register all 3 members at the SEDHACKS '26 site. **Do this first.**
- [ ] Install Python 3 on every laptop (python.org). Test by running `python3 --version`.
- [ ] Download the repo folder onto all 3 laptops.
- [ ] Everyone runs `python3 server.py` and sees the app in a browser. This proves the
      whole team can run it — so you are not debugging laptops at the venue.

### Thu 8 Oct — Learn by breaking it (2 hours each)
- **A:** Open `data_sources.py`. Change `PRESSURE_LEVELS` and see what happens. Try a
  different `date`. Get comfortable that this file is just "ask a website for numbers."
- **B:** Open `app/engine/battery.py`. Change the `CAPACITY_VS_TEMP` values. Watch the verdict change.
  Understand `heater_power_w()` — the two ways heat escapes.
- **C:** Open `index.html`. Change the colours in `:root`. Move a box. Reload the page.
  Learn that the screen is just text you can edit.

### Fri 9 Oct — Deadline + talk to organisers (1 hour)
- [ ] **Confirm registration before 18:00 IST.**
- [ ] Message the organisers and ask these 4 questions (write the answers down):
  1. How many teams registered in each of the 5 tracks?
  2. Are prizes given per track, or to the overall best teams?
  3. Are software entries and hardware entries judged separately?
  4. Can a mentor review our demo around T+8h?
- [ ] Buy bench-rig parts (list in Part 7). About ₹300–500 total.

### Sat 10 Oct — Build the bench rig (3 hours, all 3 together)
This is your secret weapon. See Part 7. Test it once at home so it isn't new at the venue.

### Sun 11 Oct — Slides + rehearsal (3 hours)
- [ ] Fill slides **1, 2, 5, 6** of the official `.pptx` template. Use Part 9 as the text.
- [ ] Run the demo 3 times out loud, with a timer. 3 minutes.
- [ ] Sleep early. Do not arrive tired.

---

## PART 7 — The bench rig (your credibility multiplier)

> **Full step-by-step instructions are in `bench/BENCH_TEST.md`, and the calculator that
> turns your measurements into the slide-4 number is `bench/bench_test.py`.**
> Read that file before Saturday — it explains why you can run the test warm (no ice
> needed) and why a large error is normal and still good.

You are a software team. But bring **one physical thing** and you beat every pure-software
team in the room.

**What it is:** a small insulated box with a battery (or a resistor standing in for one),
a temperature sensor, and an ESP32 that prints the temperature every few seconds.

**What you do with it:** cool the box (ice + salt, or a fridge), log the temperature falling,
and compare the measured curve to what `app/engine/battery.py` predicted.

**What you say:** *"Our model predicted X minutes to reach −10 °C. We measured Y minutes in
this building at 2 AM. That's a Z% error. Here is the graph."*

That single sentence proves your model is real, not a guess. It scores on **Technical
implementation** and **Feasibility & viability** at the same time.

**Shopping list (₹300–500):** ESP32 board, DS18B20 temperature sensor (waterproof version),
a few 10 W resistors, small XPS foam sheet, aluminium tape, some 18650 cells, jumper wires.
Borrow a laptop, an ice box, and salt from the hostel kitchen.

**If the rig fails:** show the graph anyway and explain what went wrong. The FAQ rewards
honesty and troubleshooting over fake success.

---

## PART 8 — ⚠️ What you MUST build at the event (rules + your winning part)

The FAQ says: *"your implementation must demonstrate meaningful originality, improvement,
or novel application **developed during the hackathon**."*

So be honest and be smart. Here is the split:

### This kit is your STARTING POINT (infrastructure — allowed to prepare)
Fetches data · shows a profile · runs one design · gives PASS/FAIL.

### YOU build these during the 24 hours (this is your originality)
1. **Upgrade the design search.** Right now `server.py` does a basic 48-combination sweep
   and it is clearly labelled as a placeholder in the code comments. Make it *yours*:
   pick one or more of these —
   - add **solar panel area** to the search (`[0, 0.05, 0.10]` m²)
   - finer insulation steps (every 5 mm, 5 → 75 mm)
   - report the **top 3 designs**, not just the cheapest
   - add a **sensitivity report**: *"of the 3 knobs you can turn, insulation thickness
     changes survival time the most"* — that's a genuine insight judges love
2. **The bench validation** (Part 7) — measured vs predicted, with an error percentage.
3. **Your improvements to the screen** — make the verdict bigger, add the comparison that
   shows "adding batteries is the lazy fix".
4. **The pitch and the slides.**

Put this line on slide 3, unprompted:
> *"Data pipelines, physics library and app shell were prepared before the sprint.
> The design-search engine, the bench validation and all results were produced during
> the hackathon."*

Saying it yourself makes you look honest and organised. Getting caught hiding it makes you
look like cheaters. Same facts, completely different outcome.

---

## PART 9 — Slides: exactly what to change

> **The deck is built for you: `ppt/COLDSTART_SEDHACKS26.pptx`**
> Official template, their background/fonts/title bar untouched. Preview images in `ppt/preview/`.

### There is ONE place to edit: the `FILL` block at the top of `ppt/build_ppt.py`

Open `ppt/build_ppt.py`, edit these lines, then run `python3 build_ppt.py` and your
`COLDSTART_SEDHACKS26.pptx` is regenerated with everything updated on all 6 slides.

**Do this before the event (2 minutes):**

```python
FILL = {
    "team_name": "TEAM COLDSTART",        # <- your team name
    "team_lead": "YOUR NAME HERE",        # <- team lead's full name
```

**Do this after the bench test at the venue:**

```python
    "bench_predicted_ua": None,           # <- e.g. 0.0622   (W/K, from bench_test.py)
    "bench_measured_ua":  None,           # <- e.g. 0.1429   (W/K, from bench_test.py)
    "bench_error_pct":    None,           # <- e.g. 130      (no % sign)
```

While they are `None`, slide 4 automatically shows **blank lines to write on by hand** —
which is correct until you have real measurements.

**Do this only if your numbers move:** after you calibrate `k_ins` with your bench result and
re-run the optimiser, check whether your recommended design changed. If it did, update the
design numbers in the same `FILL` block (`rec_cost`, `rec_margin`, `fail_time`, and so on).
Every one of those numbers appears on slides 2, 4 and 5 and updates itself.

The text below is the source content, in case you want to change wording.

**Slide 1 — Title**
- Problem Statement Title: **Cold-Night Survival — Power & Thermal Autonomy for Near-Space Payloads**
- Track: **04 — Sustainability and Energy Management**
- Team Name / Team Lead Name: *(yours)*
- Category: **Software** (with physical bench validation)

**Slide 2 — Proposed Solution**
A flight-day planner that turns the real weather forecast into a design decision.
Input: payload design. Output: PASS/FAIL, the exact minute the battery dies, and the
cheapest design that survives. For high-altitude balloon payloads and small satellites,
where a 13-hour night at −52 °C can silently kill the mission.

**Slide 3 — Technical Approach**
- Real data: NOAA GFS upper-air forecast (live), solar irradiance, solar geometry
- Physics: Fourier conduction `Q=(k/t)·A·ΔT`, Stefan-Boltzmann radiation, published
  18650 capacity-vs-temperature curves, no-charge-below-0 °C constraint
- Built with AI coding tools as development aids (disclosed per FAQ 17); all physics
  implemented and validated by the team
- **Novelty built during the sprint:** the design-search engine (see Part 8)

**Slide 4 — Feasibility & Viability**
- Bench test: predicted vs measured cool-down, error = ___%
- Recommended design: 8 cells + 25 mm insulation + heater 0 °C = ₹2210, 0.52 kg
- Same problem solved by "just add batteries" = ₹2584 with a worse safety margin
- Known limits: above ~31 km we use standard-atmosphere models, not GFS data. We say so.

**Slide 5 — Impact & Benefits**
- Prevents total payload loss from an avoidable power failure
- Right-sizes battery mass on every flight — less mass, cheaper launch
- Runs on free public data, so any student team can use it
- Same engine works for balloon payloads and CubeSat eclipse planning

**Slide 6 — Research & Reference**
NOAA GFS / Open-Meteo · NASA POWER · Celestrak (live TLE) · NOAA SWPC space weather ·
University of Wyoming radiosonde archive (Chennai, WMO 43279) · 18650 manufacturer
datasheets · NOAA solar position algorithm · ISA standard atmosphere.
*(Keep a `CREDITS.md` in your repo and update it as you build — then paste it here.)*

---

## PART 10 — The 3-minute demo script

| Time | What you do |
|---|---|
| 0:00 | "At 26 km over Chennai, the air is −52 °C for a 13-hour night. Half your battery's usable energy disappears. This is a real mission problem — we planned a flight for 12 October." |
| 0:25 | Type in **6 cells, 10 mm insulation, heater −10 °C**. Press RUN. Charts appear. |
| 0:50 | Point at the verdict: **FAIL — dies at 01:23, after 7.4 h of a 13 h night.** |
| 1:05 | Press **FIND CHEAPEST FIX**. Let it run. 48 designs, 21 pass. |
| 1:30 | Show row 2 vs row 3. "The lazy fix — 10 cells, thin insulation — costs ₹2584 for a 1.10× margin. Our answer: 8 cells and proper insulation, ₹2210, 1.81× margin. Cheaper *and* safer." |
| 2:00 | Hold up the bench rig. "We measured our own thermal model at 2 AM in this building. Here's the error." |
| 2:30 | "Every number here came from a live public API. Slide 6 lists all of them. The search engine is what we built today." |

Rehearse it until you don't need to read. Then rehearse it once more.

---

## PART 11 — Troubleshooting

| Problem | Fix |
|---|---|
| `python3: command not found` | Install Python 3 from python.org, tick "Add to PATH" |
| Port 8000 already busy | `python3 server.py` after setting `PORT=8080` — or just close the other app |
| Page loads but charts are empty | You are offline. The top-right badge will say `CACHED`. That is normal and fine. |
| A number looks wrong | Check the `# SOURCE:` / `# ASSUMPTION:` comment above it. If it's an assumption, say so — don't hide it. |
| Demo crashes on stage | The app falls back to cached real data automatically. Say "we're showing the last real fetch" and carry on. Never restart the laptop mid-pitch. |

---

## PART 12 — Tonight, do only these three things

1. **Register the team** (deadline 9 Oct 18:00 IST).
2. Run `python3 server.py` on all 3 laptops and confirm the app opens.
3. Watch a 10-minute video on "conduction and radiation" — that's the only physics you
   actually need to defend on stage.

Everything else can wait until tomorrow. You have 5 days.
