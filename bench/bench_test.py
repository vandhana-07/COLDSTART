"""
bench_test.py -- turns YOUR bench measurement into the number for slide 4.
================================================================================
This is the tool that fills the blanks. It contains NO inventable numbers:
it refuses to calculate until you type in real measurements.

--------------------------------------------------------------------------------
READ THIS FIRST: THE TRAP THAT WOULD HAVE RUINED YOUR ERROR PERCENTAGE
--------------------------------------------------------------------------------
Our model predicts STEADY-STATE hold power:
        Q = (k/t) * A * (T_inside - T_outside)

So the bench test must measure the SAME thing: how much power it takes to HOLD a
temperature difference at equilibrium.

If you instead logged a cool-down curve (temperature falling over time) and
compared it to this prediction, you would be comparing two different physical
quantities and the "error %" would be meaningless. Judges who know physics will
spot that instantly.

--------------------------------------------------------------------------------
THE MEASUREMENT: equilibrium heater power (takes about 40 minutes)
--------------------------------------------------------------------------------
  1. Put a known resistor inside your insulated box. Power it from a 5 V USB
     power bank. Measure the ACTUAL voltage across the resistor with a multimeter.
  2. Let it run until the inside temperature stops rising (30-40 min).
  3. Record the inside temperature and the room temperature.
  4. Measured UA = power / (T_inside - T_outside)     [W per K]

Good news: you do NOT need ice or a freezer. Heat loss scales with the
temperature difference, so a warm box in a normal Chennai room measures the SAME
insulation coefficient as a cold box in the stratosphere. This makes the test
fast, safe to run indoors at the venue, and repeatable.

--------------------------------------------------------------------------------
WHAT THIS TEST DOES AND DOES NOT VALIDATE (say this on stage)
--------------------------------------------------------------------------------
  VALIDATES : the conduction coefficient through the insulation, UA = k*A/t
  DOES NOT  : the radiation term (indoors, walls are at room temperature, so
              there is no cold-sky radiative loss to measure)
  DOES NOT  : the battery's capacity-vs-temperature curve (that needs a cold
              discharge test - list it as a limit instead)
Saying this clearly is worth more marks than pretending you validated everything.

Run:  python3 bench_test.py
"""

import os
import sys

# ------------------------------------------------------------------ INPUTS
# EDIT THESE with your real measured values. Leave as None until you measure.
# ------------------------------------------------------------------
RUNS = [
    # {"volts": None, "ohms": None, "t_inside": None, "t_outside": None},
]

# Your physical test box, outside dimensions in metres.
BOX_L = 0.12
BOX_W = 0.12
BOX_H = 0.12

# The insulation you actually put on the box
INSULATION_MM = 25.0
K_INS = 0.018            # aerogel blanket class. XPS foam ~0.030. Use what you used.

# The app currently assumes a payload surface area of 0.035 m^2. Your bench box
# is bigger. Both must use the SAME area or the comparison is meaningless, so
# this script tells you what to change in the app (see the output).

MODEL_AREA_M2 = 0.035    # what physics.py uses today (design["box_area_m2"])

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))


def box_surface_area(l, w, h):
    """Outer surface area of a rectangular box = 2*(lw + lh + wh)."""
    return 2 * (l * w + l * h + w * h)


def main():
    print("=" * 74)
    print("  BENCH VALIDATION CALCULATOR")
    print("=" * 74)

    measured_area = box_surface_area(BOX_L, BOX_W, BOX_H)
    predicted_ua = (K_INS / (INSULATION_MM / 1000.0)) * measured_area

    print(f"\nYOUR RIG")
    print(f"  box outer dimensions : {BOX_L*100:.1f} x {BOX_W*100:.1f} x {BOX_H*100:.1f} cm")
    print(f"  outer surface area A : {measured_area:.4f} m^2")
    print(f"  insulation           : {INSULATION_MM:.0f} mm, k = {K_INS} W/(m*K)")
    print(f"  PREDICTED UA         : {predicted_ua:.4f} W/K   <- what our model claims")

    finished = [r for r in RUNS if all(r.get(k) is not None
                for k in ("volts", "ohms", "t_inside", "t_outside"))]

    if not finished:
        print("\n" + "-" * 74)
        print("  NO MEASUREMENTS YET - nothing to calculate.")
        print("-" * 74)
        print("""
  This is deliberate. This tool will not invent a number for you, because an
  invented number on slide 4 is worse than a blank one: it is the one thing
  that can turn a 7.5 into a disqualification.

  DO THIS, IN ORDER:
    1. Build the rig (see BENCH_TEST.md). ~30 minutes.
    2. Run the equilibrium test. ~40 minutes. Record volts, ohms, T_inside, T_outside.
    3. Do it THREE times (warm up, let it cool, repeat). Three runs let you
       report a spread instead of a single lucky number.
    4. Paste your numbers into the RUNS list at the top of this file.
    5. Run this script again.

  IMPORTANT - DO THE TIMED RUN AT THE VENUE DURING THE SPRINT.
  Rehearse the whole procedure at home so it is boring and reliable, then take
  the numbers you actually report during the hackathon. Two reasons:
    (a) FAQ 14 wants your hackathon implementation to be developed during the
        sprint - an in-sprint measurement answers that cleanly;
    (b) "we measured this at 2 AM in this building" is a far stronger sentence
        than "we measured this at home last week".
""")
        return

    print(f"\nYOUR MEASUREMENTS  ({len(finished)} run(s))")
    print(f"  {'run':>3} {'volts':>7} {'ohms':>7} {'P (W)':>8} "
          f"{'T_in':>7} {'T_out':>7} {'dT (K)':>7} {'UA meas':>9} {'error':>8}")
    print("  " + "-" * 76)

    errors, uas = [], []
    for i, r in enumerate(finished, 1):
        p = r["volts"] ** 2 / r["ohms"]                  # P = V^2 / R
        dt = r["t_inside"] - r["t_outside"]
        if dt <= 0:
            print(f"  {i:>3}  --- rejected: inside temp is not above outside temp")
            continue
        ua = p / dt
        err = (ua - predicted_ua) / predicted_ua * 100.0
        uas.append(ua)
        errors.append(err)
        print(f"  {i:>3} {r['volts']:>7.2f} {r['ohms']:>7.1f} {p:>8.3f} "
              f"{r['t_inside']:>7.1f} {r['t_outside']:>7.1f} {dt:>7.1f} "
              f"{ua:>9.4f} {err:>7.1f}%")

    if not uas:
        print("\n  No usable runs. Check that the box actually heated above the room.")
        return

    mean_ua = sum(uas) / len(uas)
    mean_err = sum(errors) / len(errors)
    spread = (max(errors) - min(errors)) if len(errors) > 1 else 0.0

    print("  " + "-" * 76)
    print(f"  mean measured UA  : {mean_ua:.4f} W/K")
    print(f"  predicted UA      : {predicted_ua:.4f} W/K")
    print(f"  MEAN ERROR        : {mean_err:+.1f}%")
    if len(errors) > 1:
        print(f"  run-to-run spread : {spread:.1f} percentage points")

    # --- TWO things to do with the result, and they are different ----------
    fitted_k = mean_ua * (INSULATION_MM / 1000.0) / measured_area
    print("")
    print("  " + "=" * 70)
    print("  DO BOTH OF THESE - THEY ARE NOT THE SAME THING")
    print("  " + "=" * 70)
    print(f"""
  1) REPORT the discrepancy  (this is your slide-4 evidence)
       model predicted {predicted_ua:.4f} W/K, we measured {mean_ua:.4f} W/K
       -> error {mean_err:+.0f}%.

  2) CALIBRATE the model, then re-run the optimiser  (this is good engineering)
       Update k_ins to your measured value so the planner's advice is based on
       your real box rather than on an idealised constant:

         in  app/server.py  ->  DEFAULT_DESIGN["k_ins"] = {fitted_k:.5f}

       and while you are there, make the area honest:

         in  app/server.py  ->  DEFAULT_DESIGN["box_area_m2"] = {measured_area:.4f}

       Then re-run the optimiser. Your recommended design may change - and if it
       does, that is a GREAT thing to show: "the bench test changed our
       recommendation, and here is by how much."

  Doing (2) is not "hiding the error". Hiding is when you quietly change a number
  and never mention the measurement. Reporting AND calibrating is exactly what a
  professional instrumented test does.""")

    if abs(mean_err) > 50:
        print(f"""
  NOTE ON YOUR LARGE ERROR ({mean_err:+.0f}%):
    This is NORMAL for a first bench box, and it is worth understanding why:
      - Real foam is k ~ 0.030, not the 0.018 of ideal aerogel.
      - Edges, gaps and screw holes bypass the insulation. A real box leaks
        along its corners no matter how neatly you cut the foam.
      - Your model has no term for the wooden/frame thermal bridge.
    So a measured UA that is 1.5x to 3x the ideal prediction is a realistic,
    believable result - and reporting it honestly is far stronger than reporting
    a suspiciously perfect match.

    Because of that, ALSO run:
        cd ../app && python3 sensitivity.py
    It shows which designs survive a constant that is 2-3x off, and which fall
    apart. That is the analysis that protects your headline claim.""")
    else:
        print("""
  Your error is small. Good - but say on stage that the test validates
  CONDUCTION only. Radiative loss and the battery capacity curve are still
  unvalidated, and claiming otherwise is the one thing that can hurt you.""")

    # --- does the size assumption match the app? ---------------------------
    print("\n" + "=" * 74)
    print("  CONSISTENCY FIX - DO THIS OR YOUR ERROR % IS MEANINGLESS")
    print("=" * 74)
    ratio = measured_area / MODEL_AREA_M2
    print(f"""
  The app currently assumes the payload box has a surface area of {MODEL_AREA_M2} m^2.
  Your bench box has an area of {measured_area:.4f} m^2  ({ratio:.1f}x bigger).

  Because heat loss is proportional to area, these two must agree. Choose one:

    OPTION A (recommended, 2 minutes): rebuild nothing - just tell the app the
      truth. In app/server.py, set DEFAULT_DESIGN["box_area_m2"] to
      {measured_area:.4f}
      Then the app models the same box you actually measured.

    OPTION B: build a box whose outer surface area is {MODEL_AREA_M2} m^2
      (that is a cube about 7.6 cm on each side - fiddly to insulate).

  Pick A. Then re-run the app and re-check your designs, because the numbers on
  slide 4 will shift slightly once the area is honest.
""")

    # --- the headline sentence for slide 4 ---------------------------------
    print("=" * 74)
    print("  FOR SLIDE 4 (fill in your own numbers)")
    print("=" * 74)
    print(f"""
  "We measured the insulation coefficient of our rig: {mean_ua:.4f} W/K.
   Our model predicted {predicted_ua:.4f} W/K - a {abs(mean_err):.0f}% error over
   {len(uas)} run(s). The test validates conduction only; the radiative term and the
   battery curve remain listed as limits." """)

    # --- the part that actually matters: does the verdict survive the error? ----
    print("=" * 74)
    print("  DOES YOUR VERDICT SURVIVE A WRONG INSULATION CONSTANT?")
    print("=" * 74)
    print("""
  A % error in UA is only interesting if it can change the ANSWER. Re-run the
  model with the constant scaled by your measured error and see whether the
  PASS/FAIL verdict moves. Run this:

      cd ../app && python3 sensitivity.py

  (That script already does this sweep. The results computed from the real
   12 Oct forecast are in the printed table.)
""")


if __name__ == "__main__":
    main()
