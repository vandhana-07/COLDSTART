# SEDHACKS '26 — Domain Pick & Winning Playbook
**Rajalakshmi Engineering College · 12–13 Oct 2026 · registration closes 9 Oct, 18:00 IST**
Prepared 7 Oct 2026. Every data source below was tested live from Chennai while writing this.

---

## 0. The 30-second answer

| Question | Answer |
|---|---|
| **Which domain?** | **Domain 04 — Sustainability & Energy Management** |
| **Build what?** | A **power + thermal autonomy planner for near-space payloads / small satellites** — it ingests the **real weather forecast for your launch date**, real solar irradiance and live satellite orbits, and outputs a *decision*: will this payload survive the night, and what's the cheapest change that makes it survive. |
| **Why this wins** | Thinnest competition of the five tracks, 100% real data available (verified below), matches the track's own wording ("powering long-duration space systems"), demo-able in one screen, and it is a tool **Aeroin SpaceTech could actually use** — they fly stratospheric balloon payloads and build CubeSat electric propulsion. |
| **Backup pick** | Domain 01, a **balloon trajectory + landing-zone + airspace GO/NO-GO tool** (section 4). Higher "wow", more crowded track. |
| **Do not** | Build a satellite-image classifier, a space chatbot, or a generic dashboard. That is what 70% of the room will submit. |

If you only read one line: **judges reward "Demonstrate It" + a hard number. Pick a track with few teams and arrive with data pipelines already proven.**

---

## 1. What this event actually rewards (verified, not guessed)

I pulled the site, its JS bundle (the FAQ answers), and the official deck template. Facts:

**Six scoring criteria (FAQ 23, verbatim):** Problem understanding · Innovation & originality · Technical implementation · Functionality & demonstration · Practicality & feasibility · Presentation & communication.

**Your own PPT template has exactly 6 slides (from the official .pptx):**
1. Title — *Problem Statement Title, Track, Team Name, **Category [hardware/software]**, Team Lead Name*
2. PROPOSED SOLUTION
3. TECHNICAL APPROACH
4. **FEASIBILITY & VIABILITY**
5. IMPACT & BENEFITS
6. **RESEARCH & REFERENCE**

Two conclusions jump out:
- **"Feasibility & Viability" + "Research & Reference" are official slides.** Most teams will fill them with adjectives. Facts, sources, costs and a validation method score here — and this is precisely where a "no synthetic data" build prints marks.
- **The template asks for a Category (hardware/software)** — strongly implying the judges rank hardware and software entries as separate pools. So the software pool is the crowded one; a software core with a *physical validation rig* (section 3.6) lets you compete in software while showing hardware-grade rigour.

**Rules that shape strategy (verbatim from the FAQ):**
- **Q14:** "You may build upon existing research or open-source libraries, but your implementation must demonstrate meaningful originality, improvement, or novel application **developed during the hackathon**." → Prep your *infrastructure* before the sprint; build the *novel core* during it, and say so on stage.
- **Q17:** AI tools (ChatGPT/Claude/Copilot) and standard open-source libraries are **allowed** as development aids, but you "must clearly explain" the tools used. Antigravity/Codex = fine. Declare them on slide 3 like a pro.
- **Q27:** "You may use permitted open-source components and public datasets **(NASA, ISRO, ESA)**… respect licenses, provide attribution." → Your real-data approach is explicitly sanctioned. Attribution is a scoring asset, not a chore.
- **Q26:** **You own 100% of the IP.** Useful line in the pitch.
- **Q30:** "**aerospace industry mentors** will be available throughout the sprint." → Free rubric-alignment. Show a mentor your demo at T+8h and at T+18h.
- **Q18/Q19:** simulation-only and fully software solutions are explicitly allowed.
- **Q20/21:** ₹10,000+ pool "awarded across top performing solutions"; wording elsewhere is "merit grant rewards for winning student teams **across all technical tracks**" → prizes are very likely awarded **per track**. That single fact is the reason track-choice matters at all.

**Deadline reality:** registration closes **9 Oct 18:00 IST** — that's ~2 days from now. Register today even if the idea shifts later (Q31 permits refinement/pivoting during the sprint).

---

## 2. Track crowding — where the field is thin

This is an informed estimate from how intra-college Indian hackathons distribute, not official data. **Verify it on Day 1** (section 6).

| Track | Who piles in | Crowding | Real-data depth | Aeroin fit | Verdict |
|---|---|---|---|---|---|
| **01 Space Apps & Defence** | Everyone with a laptop: satellite images, "AI for ISRO", defence dashboards | **Highest** | High | Medium | Only enter with a non-generic idea (section 4) |
| **02 Medical/Food/Agri in Space** | Biotech + a few CSE; hardware plant experiments | Medium | **Low** | Low | Weak for a software team: sparse real data, bench-science bias |
| **03 Space Instrumentation** | ECE/Mech with sensors, spectrometers, telescopes | Medium-high | Medium | **High** | Software team looks thin next to real hardware |
| **04 Sustainability & Energy** | Under-picked: students read "sustainability" as a boring green checkbox | **Lowest–low** | **Highest** | **High** | ✅ **Pick this** |
| **05 Open Innovation** | The undecided + strongest wildcards | High, high variance | Varies | Varies | Gamble; tends to be judged as "didn't fit anywhere" |

Why 04 is the value pick: it's the only track where (a) real, hourly, forecast-grade data exists for free on a public API, (b) the physics is standard textbook engineering you can defend under questioning, (c) the track text literally asks for "powering long-duration space systems… energy management… battery storage", and (d) the incumbent jury (Aeroin) has a direct commercial interest in the answer.

**Your likely software rivals in 04:** "solar panel soiling detection", "smart grid for space" hand-waving, "energy dashboard" with charts and no decision. Beat them with a **verdict and a number**.

---

## 3. THE PICK — Domain 04

### 3.1 Project name (pick one, put it on the title slide)
**COLDSTART** · or **NightSurvive** · or **STRATOBAT** — *"Flight-day power & thermal autonomy planner for near-space payloads and small satellites."*

### 3.2 The problem statement (say it in one sentence, twice)
> "A high-altitude balloon payload floating at 26 km sits in −52 °C air for a 12-hour night. Li-ion packs lose half their capacity when cold, heaters eat the energy you're trying to save, and flight teams plan this on guesswork. We built the tool that gives you the verdict and the fix — using the real weather forecast for your actual launch date."

That is a *real*, checkable, local problem: SEDS REC flies high-altitude balloon missions; Aeroin's flagship is a stratospheric balloon rocket launcher whose payloads face exactly this.

### 3.3 What it does

| Module | Function | Output (the money shot) |
|---|---|---|
| **1. Environment ingest** | Pull real GFS upper-air profile for the chosen site + launch date (temperature, wind, geopotential height, up to ~31 km), real solar irradiance forecast, real solar geometry | A real atmosphere for the flight, not a table from a textbook |
| **2. Energy + thermal model** | Battery pack model (cells, chemistry, published capacity-vs-temperature curves), insulation conduction (Fourier), radiative loss to cold sky, heater duty cycle, PV generation from the real forecast, night duration from real solar geometry | State-of-charge curve across the entire flight; **time of first brownout** |
| **3. Decision engine** *(this is the innovation)* | Searches the design space: cells · insulation thickness · heater set-point · duty-cycled load scheduling (sleep the camera, batch the downlink) | **A verdict + the cheapest fix**: "6 cells fails at T+9h29m. Add 2 cells + 50 mm aerogel + heat to −10 °C → 18h23m = 1.53× margin. Cost: ₹1,240, 310 g." |
| **4. Verification view** | Backtest the model against real historical solar/weather (ERA5 archive) and against real orbital data (live TLE + SGP4) for the CubeSat variant | "The model reproduces real conditions; here's the eclipse geometry of a real spacecraft, computed from its real orbit today" |

**Two targets from one engine** — say this on stage, it widens your impact slide:
- **Near-space / balloon payload** (SEDS REC + Aeroin's actual use case)
- **CubeSat** — same engine, eclipses instead of night, using the live TLE (this is what Aeroin's **electric-propulsion CubeSat** work needs; EP thrusters are power hungry and their duty cycle must be planned)

### 3.4 Real data layer — every endpoint live-tested today

| Source | What's real about it | Endpoint | Status 7 Oct 2026 |
|---|---|---|---|
| **Open-Meteo GFS** | NOAA GFS **forecast** — upper-air temperature, wind, geopotential at 1000→10 hPa | `api.open-meteo.com/v1/gfs` | ✅ 408 profile points; ceiling **31.13 km**; T @ 20 hPa = **−52.5 °C** for 12 Oct |
| **Open-Meteo ERA5 archive** | **Measured/reanalysis** past solar irradiance (backtesting) | `archive-api.open-meteo.com/v1/archive` | ✅ 25 Sep 2026: peak GHI **829 W/m²** |
| **Open-Meteo forecast (solar)** | Real forecast irradiance for flight day | `api.open-meteo.com/v1/forecast` | ✅ 12 Oct 2026: peak GHI forecast **858 W/m²** |
| **NASA POWER** | Satellite-derived solar + met, long-term baseline | `power.larc.nasa.gov/api/temporal/daily/point` | ✅ 1 Oct 2026: **5.99 kWh/m²/day** (⚠️ the *hourly* endpoint lags weeks — use **daily**; get hourly from Open-Meteo) |
| **Celestrak GP/TLE** | **Live orbital elements** of real satellites | `celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle` | ✅ ISS epoch 26279.98; SGP4 propagation verified |
| **NOAA SWPC** | Live space weather (X-ray flare class, Kp) | `services.swpc.noaa.gov/json/goes/primary/xray-flares-latest.json` | ✅ latest flare **C7.9 @ 13:17Z**, Kp 0.67 |
| **Cell datasheets** | Published capacity-vs-temperature curves (Panasonic/LG/Samsung 18650) | vendor PDFs | Real specs — cite them on slide 6 |
| **NASA/ESA/ISRO reports** | Long-duration balloon, ULDB, ECLSS, Loon thermal papers | — | Cite on slide 6 |

⚠️ **Dead ends I already hit, so you don't waste sprint hours:** NASA **DONKI API is retired** (301 → CCMC notice page) — use **NOAA SWPC** instead. **SatNOGS telemetry frames require auth** (401); the satellite DB is open but decoded telemetry is not. NASA POWER **hourly** returns `-999` fill values for recent dates.

### 3.5 Model layer — physics, not invention

The credibility rule for your pitch: **"inputs are measured/forecast data; the model is published physics; the two are separated and labelled."** That is the difference between a simulation and a fabrication.

- Conduction: `Q = (k/t)·A·ΔT` (aerogel k≈0.018, XPS k≈0.030 W/m·K)
- Radiation to cold sky: `Q = εσA(T_amb⁴ − T_sky⁴)` — surface-based, **not** reducible by more insulation (so it sets the floor of your heater budget — a nice engineering nuance to say out loud)
- Battery: published capacity-retention curves vs temperature; no charging below 0 °C (lithium plating) — a real constraint judges will respect
- Solar geometry: NOAA solar-position algorithm (deterministic, verifiable)
- Orbit: SGP4/SDP4 via the `sgp4` Python library on **live** TLEs (verified working)
- Above the GFS ceiling (~31 km): ISA / NRLMSISE-00 **published standard atmospheres** — and say the word "standard atmosphere" aloud, because that's not fake data either

### 3.6 The free credibility multiplier: a bench test rig
You're a software team in a software category — so bring **one physical artifact**. Build it during the sprint, at the venue, in an hour:

> **Rig:** a 6-cell 18650 pack or a resistor substitute in an insulated box (XPS + aerogel offcuts) → a DS18B20 thermocouple → ESP32 → serial plot. Cool it with ice/salt (or the hostel freezer) and log the cool-down curve. Compare measured heat-loss to your model's prediction.

Then say: *"Here is our model's prediction; here is the measurement we made at 02:00 in this building; here's our error percentage."* That single sentence beats every dashboard in the room on **Technical implementation**, **Functionality**, and **Feasibility**, and it's honest — the model is validated, not asserted. It also gives you a physical prop for the judges' walk-around. (Bring ESP32 + thermocouple + resistors in your kit per FAQ 29; costs ~₹300.)

### 3.7 The demo — exact 3-minute pitch
| Time | Do this |
|---|---|
| 0:00–0:25 | "At 26 km over Chennai in October, the air is −52 °C for a 12-hour night. Half your battery's capacity disappears. We planned a real flight for **Monday, 12 October**." |
| 0:25–0:55 | Live: pick **REC Chennai** + **12 Oct**. Real GFS layer paints the atmospheric profile on screen. (Not a mock-up — this forecast was fetched minutes ago.) |
| 0:55–1:35 | Press **PLAN**. SoC curve draws across the flight. It crosses your red minimum at **T+9h29m**. Verdict: **FAIL**. Let that sit for a beat. |
| 1:35–2:10 | Press **OPTIMISE**. Watch it sweep cells × insulation × heater. It stops at the cheapest passing design, prints the mass and cost. Show the **1.53× margin**. |
| 2:10–2:35 | Toggle to the **CubeSat** tab: real ISS TLE, real eclipse geometry, power budget for an EP-thrust duty cycle. "Same engine, different mission." |
| 2:35–3:00 | Hold up the bench rig. "We didn't trust our own thermal model — we measured it at 02:00 tonight. Model error: X%. Slide 6 lists every dataset and paper." |

### 3.8 The hard number — computed live today (this is your evidence)

Real forecast inputs, real geometry, published-curve battery model — run before the sprint to prove the pipeline:

```
Float altitude (GFS 20 hPa): 26.47 km | real forecast ambient T: -52.5 C
Pack: 6 x 18650 = 73.4 Wh nominal | payload load 3.0 W | real night = 12 h

A) UNHEATED      : capacity 39% -> 28.5 Wh ->  9.49 h   (FAIL vs 12 h night)
B) HEAT + 25 mm  : heater 1.65 W (cond 1.07 + rad 0.58) | capacity 70%
                   -> net 31.6 Wh -> 10.53 h             (FAIL)   <-- the counter-intuitive bit
C) HEAT + 50 mm  : heater 1.12 W (cond 0.54 + rad 0.58)
                   -> net 38.0 Wh -> 12.67 h             (PASS, thin margin)
D) 10 cells, cold: 47.4 Wh -> 15.81 h                   (PASS, no heater at all)
E) 8 cells + C   : net 55.1 Wh -> 18.38 h = 1.53x margin  <-- the tool's recommendation
```

**Case B is your storytelling gold.** Heater on a poorly insulated box *makes things worse* — the heater eats more energy than the capacity it recovers. Every judge who has actually built a cold-environment payload has learned that the hard way. You'll have the number.

### 3.9 Originality statement (write this on slide 3, unprompted — it answers FAQ 14)
> "The physics is textbook; the datasets are public. What's new (built during the sprint): a forecast-driven co-design solver that searches **power × thermal × duty-cycle** jointly for a near-space mission, and reports the *cheapest passing design* rather than only simulating one. Existing EPS calculators take a fixed design and environment; ours takes the real forecast for a real launch date and returns a design decision with a mass/cost penalty attached."

### 3.10 24-hour build plan (4 people)

**Roles:** A = data/pipeline engineer · B = physics/model engineer · C = front-end/visualisation · D = integration + pitch + bench rig + documentation.

| Clock | A (data) | B (model) | C (UI) | D (rig + pitch) |
|---|---|---|---|---|
| **Pre-sprint (before 12 Oct)** | Prove all 6 endpoints, cache JSON, error handling | Port `data_layer_verify.py` physics into clean functions + unit tests | UI shell + map/chart components with fake-free sample payloads from cache | Bench rig assembled; slide skeleton in the official template |
| **T+0 → T+4** | Live fetch → normalised profile objects | Environment → temp/PV/SoC curves | Wire charts to model output | Bench test #1: measure heat loss; get a mentor's read on the framing |
| **T+4 → T+10** | ERA5 backtest harness | Optimiser sweep (cells × insulation × heater × duty cycle) | Verdict panel + red "FAIL at T+…" moment | Draft slides 2–4 |
| **T+10 → T+16** | CubeSat/eclipse branch (SGP4 on live TLE) | Model-vs-bench error report | CubeSat tab, margin indicator | Bench test #2 (validated), slides 5–6 with real citations |
| **T+16 → T+20** | Freeze data, offline cache fallback | Freeze model, write assumptions list | Polish, dark "mission ops" theme | **Record a 3-min video of the full demo** |
| **T+20 → T+24** | Rehearse ×3, kill the network dependency (cached real data), sleep in shifts | | | Jury walk-around script; bench rig reset |

### 3.11 Cut list (when you're behind at 3 AM)
Cut in this order: (1) ERA5 backtest view, (2) CubeSat tab, (3) 3D globe → replace with a 2D map/eclipse strip, (4) the optimiser's fancy search → downgrade to a 15-point grid sweep. **Never cut:** the verdict, the hard number, the bench rig, slide 6 citations.

---

## 4. Runner-up — Domain 01: **"FLIGHTLINE"** — balloon trajectory & recovery assurance

Register under **Domain 01** ("mission support systems · navigation · space situational awareness" — it fits verbatim).

**What it does:** takes launch site + date/time, pulls the **real GFS wind profile** (tested: 408 points, 31 km ceiling) and the **real radiosonde archive** for Chennai/Minambakkam (WMO **43279**) from the University of Wyoming upper-air archive, runs a balloon physics model (ascent rate, burst altitude, parachute descent), integrates the wind field to predict the **landing zone with a Monte-Carlo uncertainty ellipse**, and produces a **GO/NO-GO** verdict with drift-into-sea / populated-area / controlled-airspace warnings.

**Why it's strong:** it is the single most Aeroin-relevant thing you can build (their flagship **is** a stratospheric balloon launcher — recovery and airspace clearance are their operational pain), the live demo is beautiful (animated flight on a map with the uncertainty cone), and it has a genuinely fatal-sounding failure mode it catches (payload landing in the Bay of Bengal).

**Why it's #2, not #1:** Domain 01 is the most crowded track, and "map + trajectory" reads as generic to a judge who has seen 12 maps that day — you must make the *uncertainty ellipse and the safety verdict* the hero, not the map.

---

## 5. Do not build these

| Idea | Why it loses |
|---|---|
| Satellite-image land-use/water classifier | Every track-01 team does this. Zero novelty, and your "model accuracy 94%" is meaningless to a space jury. |
| "AI space chatbot / RAG over ISRO PDFs" | No engineering. Fails "Technical implementation" and "Functionality". |
| Space-debris "visualiser" with static data | Looks pretty, has no output. Judges ask "what decision does it make?" and it's over. |
| Mars/rover path-planning sim | Not connected to any real mission or operator, and outside the declared track scopes. |
| Solar-panel soiling/energy dashboard with no decision | Dashboard ≠ solution. Add a verdict and a number or don't build it. |
| Anything with invented telemetry you can't attribute | FAQ 27 requires attribution; and "Practicality & feasibility" collapses the moment they ask where the data came from. |

---

## 6. Rules leverage & risk management

**Hedge your track choice on Day 1 (10 minutes, high ROI).** FAQ 31 explicitly allows refinement/pivoting early. Ask the organisers/mentors:
1. *"How many teams registered in each track?"* → if Domain 04 is unexpectedly crowded, pivot your framing to Domain 01 (both projects above share 80% of the code).
2. *"Are prizes awarded per track, or across all teams?"* → determines whether track choice or absolute quality is the dominant factor.
3. *"Are hardware and software entries judged in separate categories?"* (the template's Category field suggests yes).
4. *"Can a mentor review our demo at T+8h?"* → book it in writing.

Where to ask: **Sruthi Nisha J.S (Student Coordinator) +91 98844 64389**, **Arun Kumar S (Club President) +91 81221 50038**.

**Other leverage:**
- **AI-tool disclosure (Q17):** put a line on slide 3 — "Built with Antigravity/Codex as development aids; all data real, all physics implemented and validated by the team." Disclosing it *proactively* converts a potential attack into a competence signal.
- **Attribution page:** keep a live `CREDITS.md` in your repo as you build — every dataset, paper, datasheet, license. Paste it into slide 6 the night before. Ten minutes, guaranteed marks.
- **Live-demo failure (FAQ 25):** the FAQ literally grades your composure. So: (a) record a 3-min video backup, (b) cache today's real API responses for offline replay (cached *real* data is not synthetic data — label it "cached 12 Oct 09:14 IST"), (c) keep a "module fallback" button that demos the optimiser on the cached case.
- **Don't overclaim:** say "validated against a bench measurement with X% error", not "flight-proven". A SEDS/aerospace jury punishes overclaiming instantly and rewards calibrated language.
- **IP (Q26):** you keep 100% — mention it if a judge asks whether the college or Aeroin owns it.
- **Internship play:** Aeroin's internships are the real prize. In the last 30 seconds say: *"This runs on the real forecast for any launch date. We'd like to run it on your next flight's date and hand you the report."* That is a concrete, low-risk offer to a 28-person startup whose core product is launched from a balloon.

---

## 7. Pre-sprint checklist (today → 11 Oct)

- [ ] **Today:** register the 4-member team (deadline 9 Oct 18:00 IST) — you can refine the idea later.
- [ ] **Today:** run `data_layer_verify.py` on your own laptop; confirm all 6 sources work on your network.
- [ ] **9 Oct:** ask the organisers the 4 questions in section 6.
- [ ] **9–10 Oct:** port the model into clean functions with unit tests; build the UI shell against cached real JSON.
- [ ] **10 Oct:** buy/borrow bench rig parts (ESP32, DS18B20 or thermocouple, resistors, aerogel/XPS offcuts, ice-salt cooler) and 6×18650 cells if available.
- [ ] **11 Oct:** fill slides 1, 2, 5, 6 in the **official template** (don't restyle it — judges scan for the standard structure); write `CREDITS.md`; set up the repo; sleep.
- [ ] **Carry:** laptops + chargers, extension board, 2 phones as hotspot backups, REC ID cards, the rig, a pen drive with the offline cache and the template. (FAQ 29 explicitly tells you to bring your own hardware.)

---

## Appendix A — copy-paste endpoints (all verified live)

```
# Real upper-air forecast (temp/wind/geopotential to ~31 km) — flight day
https://api.open-meteo.com/v1/gfs?latitude=13.0067&longitude=80.2570&hourly=temperature_500hPa,wind_speed_500hPa,wind_direction_500hPa,geopotential_height_500hPa&start_date=2026-10-12&end_date=2026-10-12&wind_speed_unit=ms&timezone=Asia/Kolkata
# (swap 500 for 1000/925/850/700/600/400/300/250/200/150/70/50/30/20/10 hPa)

# Real measured/reanalysis solar history (backtesting)
https://archive-api.open-meteo.com/v1/archive?latitude=13.0067&longitude=80.2570&start_date=2026-09-25&end_date=2026-09-25&hourly=shortwave_radiation,direct_normal_irradiance,temperature_2m&timezone=Asia/Kolkata

# Real solar forecast for flight day
https://api.open-meteo.com/v1/forecast?latitude=13.0067&longitude=80.2570&start_date=2026-10-12&end_date=2026-10-12&hourly=shortwave_radiation,direct_normal_irradiance&timezone=Asia/Kolkata

# NASA POWER daily resource (use DAILY; hourly lags weeks)
https://power.larc.nasa.gov/api/temporal/daily/point?parameters=ALLSKY_SFC_SW_DWN,T2M&community=RE&longitude=80.257&latitude=13.0067&start=20261001&end=20261001&format=JSON

# Live satellite catalogue (real orbital elements, no key)
https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle

# Live space weather
https://services.swpc.noaa.gov/json/goes/primary/xray-flares-latest.json
https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json

# Upper-air radiosonde archive (real soundings, Chennai/Minambakkam WMO 43279)
https://weather.uwyo.edu/upperair/sounding.html
```

Python: `pip install sgp4` (verified working, v2.27 — use `Satrec.twoline2rv(l1, l2, WGS72)`).
Workspace script: `sedhacks26/data_layer_verify.py` → writes `out/upper_air_2026-10-12.csv`, `out/solar_era5_*.csv`, `out/tle_stations.txt`, `out/space_weather.json`, `out/verification_summary.json`.

## Appendix B — prompt pack for Antigravity / Codex

Give it the **contract first**, not the vibe:

> "Build a Python FastAPI service with two endpoints: `/environment?lat&lon&date` returning a normalised flight environment `{altitude_profile: [{z_m, temp_C, wind_ms, wind_dir_deg}], solar: [{t, ghi, dni}], night_hours}` sourced from Open-Meteo GFS + archive (per Appendix A URLs, no mock data, no random numbers, raise on upstream failure), and `/plan` accepting `{cells, wh_per_cell, insulation_mm, k_ins, heater_setpoint_C, load_profile_W, area_m2}` returning a state-of-charge time series + `first_brownout_utc` + `survival_hours`. Physics: conduction Q=(k/t)AΔT, radiation Q=εσA(T_amb⁴−T_sky⁴), capacity-vs-temperature as a piecewise-linear interpolation table supplied as a constant. All constants must be named with a source comment. Then a single-page React front-end: site+date picker → chart of SoC vs time with a red minimum line → PASS/FAIL verdict → 'Optimise' button running a grid sweep over cells ∈ {6,8,10,12}, insulation ∈ {10,25,50,75} mm, setpoint ∈ {−20,−10,0} °C, reporting the cheapest passing design with mass and cost."

Then iterate with: *"Add the Eclipse/CubeSat mode using Celestrak TLE + sgp4, computing eclipse entry/exit and a panel-generation model."*
**Rule for your team:** every constant the AI writes must be traceable to a datasheet or paper, or it goes in the "assumptions to validate" list — that list is slide 4 and it will *earn* you points, not cost you.

## Appendix C — slide skeleton mapped to the official template

1. **Title:** *COLDSTART — Flight-Day Power & Thermal Autonomy Planner for Near-Space Payloads and Small Satellites.* Track: 04. Category: Software (with bench validation). Team name + lead.
2. **Proposed Solution:** problem in one sentence → what we built in one sentence → the verdict screenshot.
3. **Technical Approach:** architecture diagram (data → model → solver → UI) · physics equations · AI tools used (Q17 disclosure) · what's novel (section 3.9).
4. **Feasibility & Viability:** model-vs-bench error % · BOM + cost + mass of the recommended design · who uses it (SEDS REC flights, Aeroin near-space payloads, CubeSat teams) · limits we know about.
5. **Impact & Benefits:** avoids failed flights and lost payloads · right-sizing packs saves mass on every mission · reusable across near-space and orbital platforms · cost/power savings number.
6. **Research & Reference:** GFS/Open-Meteo, NASA POWER, Celestrak, NOAA SWPC, Wyoming radiosonde archive, ISA/NRLMSISE-00, 18650 datasheets, long-duration balloon thermal papers. Licenses + attribution.

---

### Honest caveats (know these before a judge finds them)
- **Track crowding is an estimate**, not published data — confirm on Day 1.
- **Above ~31 km**, GFS has no data; you switch to standard-atmosphere models. Say so before you're asked.
- The battery curve is a **datasheet approximation** until your bench test refines it. Publish your error bar; that is what engineers do.
- The near-space solar-generation model at altitude is the weakest link (irradiance at 26 km above cloud, panel temperature, cosine losses). Use it as a *sensitivity band*, and say the band out loud. A calibrated range beats a false point value.
