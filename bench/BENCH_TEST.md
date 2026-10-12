# BENCH TEST — the 40-minute experiment that turns 7.5 into 9

You are validating **one number**: how much heat leaks out of your insulated box.
That number (`UA`, in W/K) is what `physics.py` uses to decide how much heater power
you need. If it is wrong, every verdict is wrong. So you measure it.

**Total time:** ~30 min to build, ~40 min to measure, ×3 runs.
**Cost:** ₹300–500. **Skills needed:** none beyond plugging in a USB cable.

---

## ⚠️ Read this first: the trap that would have ruined your error percentage

Our model predicts **steady-state** heat loss:

```
Q = (k / t) * A * (T_inside - T_outside)
```

So the bench test must measure the **same quantity** — how much power it takes to *hold*
a temperature difference once things have settled.

If you instead logged a **cool-down curve** (temperature falling over time) and compared it
to this formula, you would be comparing two different physical quantities. The "error %"
would be meaningless, and any judge who knows heat transfer will spot it instantly.

**We measure equilibrium heater power. Not a cool-down curve.** It's also easier.

---

## Why you can run this test WARM (no ice, no freezer)

Heat loss is proportional to the **temperature difference**, not to absolute temperature:

```
lose 5.6 W for a 30 K difference   ==  lose 5.6 W for a 30 K difference
whether the box is at +30 °C in a room, or at −22 °C in the stratosphere
```

So a warm box in a normal Chennai room measures exactly the same insulation coefficient as
a cold box up there. This makes the test:

- **safe** — no ice, no dry ice, nothing to burn yourself on
- **fast** — it stabilises in ~30 minutes instead of overnight
- **repeatable** — you can do three runs before midnight
- **venue-friendly** — it runs off a USB power bank at your table

Say this out loud during the pitch. Understanding *why* you can run warm is a strong signal.

---

## What to buy

| Item | Notes | Cost |
|---|---|---|
| ESP32 or Arduino | any board you can read a temperature from | ₹250 |
| DS18B20 temperature sensor | waterproof probe version, ±0.5 °C | ₹80 |
| Power resistor, 10 Ω **10 W** wirewound | this is your heater | ₹25 |
| USB power bank | 5 V, powers the resistor | borrow one |
| Multimeter | you must measure the **actual** voltage | borrow one |
| XPS foam sheet (~2 cm) + aerogel scraps | insulation, cut to fit | ₹100 |
| Aluminium foil tape | optional, reduces radiative loss | ₹50 |
| Cardboard box ~12 × 12 × 12 cm | the payload box | free |

**Total: ≈ ₹450.** Order it by 9 October.

---

## Build it (~30 minutes)

1. Cut foam panels for all **six** faces of the box and tape them on, leaving one face
   removable. Measure the **outer** dimensions with a ruler — you need them for the maths.
2. Poke a small hole for the sensor wire and the resistor wires.
3. Tape the DS18B20 probe inside, suspended in the middle of the air space — **not touching
   the resistor** (you want air temperature, not heater temperature).
4. Solder or screw the resistor to the power bank leads. Keep the resistor away from the
   sensor by a few cm.
5. Log temperature to Serial every 5 seconds.

> **Optional upgrade (worth it):** put a second DS18B20 on the *outside* of the box. Then
> you measure the real temperature difference instead of assuming it equals room temperature.
> Two sensors, one data line, same code. Costs ₹80 and removes your biggest error source.

---

## Measure it (~40 minutes per run)

1. Record the **room temperature** (from a second sensor, or any thermometer in the room).
2. Measure the **actual voltage** across the resistor with the multimeter while it is
   powered. Do **not** assume 5.00 V — a power bank often gives 4.8 V, and that is a
   ~8% error in power straight away.
3. Measure the **resistor's real resistance** with the multimeter (a "10 Ω" resistor is
   often 9.6 Ω or 10.4 Ω).
4. Switch on the heater. Watch the temperature.
5. Wait until the inside temperature **stops rising** — that is a plateau, and it usually
   takes 25–40 minutes. Wait a further 5 minutes on the plateau to be sure.
6. Record: inside temperature, outside temperature, volts, ohms.
7. **Switch off and let it cool back to room temperature, then repeat. Three runs total.**

Power and the coefficient:

```
P      = volts² / ohms              (watts)
ΔT     = T_inside − T_outside       (kelvin)
UA     = P / ΔT                     (W/K)   ← the number your model predicts
```

---

## Put your numbers in and get the slide-4 figure

Open `bench_test.py`, edit these two blocks at the top, and run it:

```python
BOX_L, BOX_W, BOX_H = 0.12, 0.12, 0.12     # your OUTER dimensions, in metres
INSULATION_MM = 25.0                        # the thickness you actually used
K_INS = 0.030                               # USE THE MATERIAL YOU REALLY USED:
                                            # 0.030 = XPS foam (what you will buy)
                                            # 0.035 = thermocol / styrofoam
                                            # 0.018 = ideal aerogel (if you got scraps)

RUNS = [
    # type YOUR measured numbers in here - the ones below are only a format example
    {"volts": 4.83, "ohms": 9.7, "t_inside": 52.1, "t_outside": 29.4},
    {"volts": 4.81, "ohms": 9.7, "t_inside": 51.6, "t_outside": 29.1},
    {"volts": 4.85, "ohms": 9.7, "t_inside": 52.8, "t_outside": 29.6},
]
```

> **Set `K_INS` to the material you actually used.** If you compare a box made of XPS foam
> against an aerogel constant, you are measuring the *difference between two materials*, not
> the error in your model — and a judge may notice. XPS foam is what you will realistically
> buy, so start there.

```bash
cd bench
python3 bench_test.py
```

It prints your measured `UA`, the model's predicted `UA`, your **error %**, your run-to-run
spread, and the exact sentence to put on slide 4.

**It will not run without real numbers.** That is deliberate — an invented number on slide 4
is the one thing that can turn a 7.5 into a disqualification.

> ⚠️ **The box size must match.** `bench_test.py` will tell you the surface area of *your*
> bench box and compare it to the `0.035 m²` the app assumes. They must agree, or the
> comparison is meaningless. The script prints the one-line fix (`DEFAULT_DESIGN["box_area_m2"]`
> in `app/server.py`). Do it.

---

## Expect your error to be LARGE — that is normal, and it is a strength

Your first measurement will almost certainly come out **worse** than the ideal formula, often
by **50% to 150%**. That is not a failure. It is what happens to everyone, because:

- **Real foam is worse than the model assumes.** XPS foam is k ≈ 0.030 W/(m·K), roughly
  1.7× worse than the ideal aerogel value of 0.018 the formula starts from.
- **Corners leak.** Heat bypasses insulation at every edge, tape seam and wire hole. A
  neatly-cut student box still has thermal bridges the formula has no term for.
- **Your model is 1-D; your box is 3-D.** The formula treats heat as flowing straight through
  a flat wall. Real boxes leak along the seams and through the base.

So a measured `UA` that is **1.5× to 3× the prediction is a realistic, believable result**.
Reporting it honestly is far stronger than reporting a suspiciously perfect match — nobody
believes a first-time bench measurement that lands within 3%.

**Do two things with the result, and they are not the same:**

1. **Report the discrepancy** — that is your slide-4 evidence. `bench_test.py` prints the sentence.
2. **Calibrate, then re-run** — set `DEFAULT_DESIGN["k_ins"]` and `["box_area_m2"]` in
   `app/server.py` to your measured values, then re-run the optimiser. Your recommendation
   may change, and *"the bench test changed our recommendation, and here is by how much"* is
   a genuinely strong thing to say on stage.

Step 2 is **not** hiding the error. Hiding is quietly changing a number and never mentioning
the measurement. Reporting *and* calibrating is what a professional instrumented test does.

---

## The 3 sentences for slide 4

After your run, put these up — with **your** numbers:

1. *"We measured the insulation coefficient of our rig: **X** W/K. Our model predicted
   **Y** W/K — a **Z%** error over three runs."*
2. *"This test validates **conduction only**. The radiative term and the battery
   capacity-vs-temperature curve are not covered by it, and we list them as limits."* ← honest, and it
   protects you from the obvious question
3. *"We then asked whether that error would change any of our recommendations — that's
   `sensitivity.py`."* (see below)

And if your error is large, say the fourth sentence — it turns a weakness into the best
moment in your pitch:

4. *"Yes, our first box measured 1.6× worse than the ideal formula — because real foam has
   thermal bridges at the seams the model does not capture. So we calibrated against the
   measurement and re-ran the optimiser. Our recommendation moved from X to Y. That is the
   tool doing its job."*

---

## The part that actually raises the score: does the error change the answer?

A model can be 40% wrong on a coefficient and still make the right **decision**. That is the
question a real validation asks, and you can answer it with numbers you already have:

```bash
cd ../app
python3 sensitivity.py
```

It re-runs the model with the insulation constant scaled from 0.6× to 3.0× and reports
whether each design's verdict flips. Results computed from the real 12 October forecast:

| Design | Verdict | Flips to FAIL if the constant is wrong by |
|---|---|---|
| Default 6 cells / 10 mm / −10 °C | **FAIL — robust** at every level | never (it fails anyway) |
| "Just add batteries" 10 / 10 mm / 0 °C | PASS — fragile | **15%** |
| Cheapest passing 6 / 75 mm / 0 °C | PASS — fragile | **15%** |
| **8 cells / 25 mm / 0 °C (our answer)** | **PASS — holds to 30%** | 50% |

**This is the strongest sentence in your whole deck:**

> *"Two designs that look attractive on paper — the cheapest one, and simply adding more
> batteries — flip to FAIL if our measured insulation constant is off by just 15%. We chose
> a design that still passes if that measurement is 30% wrong. It costs ₹80 more than the
> fragile one. That ₹80 is the price of not being wrong."*

Validation isn't proving your number is right. It's proving your **decision** survives being
wrong. That is the difference between a 7.5 and a 9.

---

## Rehearse, then measure again at the venue

Do the whole procedure once at home so it's boring and reliable. Then run the **timed test
during the sprint** and put those numbers on the slide, for two reasons:

1. **Rule (FAQ 14):** your implementation must show work developed *during* the hackathon.
   An in-sprint measurement answers that cleanly and can't be questioned.
2. **Credibility:** *"we measured this at 2 AM in this building"* beats *"we measured it at
   home last week"* — and you can hold the rig up while you say it.

---

## If it goes wrong

| Problem | What to do |
|---|---|
| Temperature never plateaus | Insulation is too thin / box too big. Wait 60 min. OR report the rate of rise and extrapolate — say you extrapolated. |
| Sensor reads wild values | Wire length or a bad joint. Shorten it. Mention it on stage as a known issue. |
| The rig dies mid-sprint | **Say so, and show the model-only result clearly labelled as unvalidated.** Then explain what you'd fix. The FAQ explicitly rewards this honesty (it asks how you'd troubleshoot a failed demo). |
| Your error is 60%+ | **Report it.** A measured 60% error beats an unmeasured 5% claim. Then explain that `sensitivity.py` shows your *decision* still holds — that's the answer that matters. |
