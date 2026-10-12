"""
build_ppt.py -- fills the OFFICIAL SEDHACKS '26 template with COLDSTART content.

We do NOT redesign the deck. We keep the organisers' dark-space theme, their
fonts, their title bar and their 6-slide structure, and add content into the
empty content area. Judges scan for the standard structure -- so we keep it.

Run:  python3 build_ppt.py
Out:  COLDSTART_SEDHACKS26.pptx
"""

import copy
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

SRC = "template_official.pptx"
DST = "COLDSTART_SEDHACKS26.pptx"

# ===========================================================================
#   FILL THIS IN. Everything on all 6 slides comes from here.
#   Leave a bench value as None and the slide shows a blank line to fill by hand.
# ===========================================================================
FILL = {
    # ---- your team (slide 1) ------------------------------------------
    "team_name": "TEAM COLDSTART",        # <- your team name
    "team_lead": "YOUR NAME HERE",        # <- team lead's full name

    # ---- bench results (slide 4). None = prints a blank to fill by hand.
    # Get these from:  cd ../bench && python3 bench_test.py
    "bench_predicted_ua": None,           # W/K, what the model predicts
    "bench_measured_ua":  None,           # W/K, what you measured
    "bench_error_pct":    None,           # e.g. 130  (do not type the % sign)

    # ---- design numbers (slides 2, 4, 5) ------------------------------
    # SOURCE:  cd ../app && python3 frontier.py
    # Forecast: GFS live, Chennai 13.0067N 80.2570E, 12 Oct 2026, launch 18:00 IST,
    # 11.5 h night. Engine coldstart-engine-1.0, box 0.0864 m2, k = 0.030 W/m.K.
    # Re-run frontier.py after any bench calibration and update these numbers.
    #
    # NOTE ON 'tolerance': every value below is the largest multiple of the
    # insulation constant at which that design still passes, minus one. It is a
    # stated error budget, NOT a probability and NOT a measurement.
    "fail_time":      "00:14",            # when the default design dies
    "fail_hours":     "6.2",              # hours it survived
    "fail_reason":    "charge exhausted",
    "default_cost":   2369,               # the default 6/10mm/-10C build, for comparison

    # the recommendation: cheapest design that survives the night
    "rec_margin":     "3.35x",
    "rec_cost":       2468,
    "rec_mass":       "0.75",
    "rec_tolerance":  "50%",
    "rec_cells":      "6",
    "rec_ins":        "75 mm",
    "rec_heater":     "heater OFF",

    # 'just add batteries' - does NOT survive
    "lazy_cost":      3369,
    "lazy_fail_time": "04:05",
    "lazy_deficit":   "1.8x",             # foam would have to be this much better
    "default_deficit": "5.0x",            # foam would have to be this much better

    # the robust alternative: what the search picks when asked for the highest
    # share of STRESSED scenarios survived. Scenario counts, not probabilities.
    "robust_cost":    4688,
    "robust_margin":  "7.40x",
    "robust_cells":   "12",
    "robust_scen":    "12 of 12",
    "rec_scen":       "1 of 12",
    "robust_gap":     2220,               # 4688 - 2468
}


def blank_or(value, unit="", fmt=str):
    """None -> a blank to write on by hand. A real value -> the number."""
    return "  " + "_" * 6 + (f" {unit}" if unit else "") if value is None else fmt(value)

# ---------------------------------------------------------------- palette
CARD      = RGBColor(0x0B, 0x17, 0x30)   # card fill, slightly lighter than the space bg
CARD_LINE = RGBColor(0x1F, 0x3A, 0x6D)   # subtle border
HEAD      = RGBColor(0xCA, 0xE8, 0xFF)   # the template's own light-blue accent
BODY      = RGBColor(0xDC, 0xE6, 0xF5)
DIM       = RGBColor(0x8F, 0xA6, 0xC4)
ACCENT    = RGBColor(0x4D, 0xA3, 0xFF)
GOOD      = RGBColor(0x35, 0xD0, 0x7F)
BAD       = RGBColor(0xFF, 0x5C, 0x6E)
WARN      = RGBColor(0xFF, 0xB0, 0x20)
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)

F_HEAD = "HK Grotesk Bold"     # the template's heading font
F_BODY = "Calibri"             # theme minor font: always installed, safe
F_LABEL = "DM Serif Display"   # the template's label font on slide 1

CONTENT_X, CONTENT_W = 0.9, 18.2
TOP = 1.72
# The template's own title sits at y=0.66 with height 0.62. A title that fits on
# one line ends around y=1.28 and 0.18 in of padding is enough. A title that
# WRAPS - "FEASIBILITY & VIABILITY" does - descends to about y=1.91 and needs
# more room, so the wrapping slides raise this. Measured from the rendered
# preview rather than assumed.
OFFSET_Y = 0.18
OFFSET_WRAPPED = 0.42      # for slides whose template title runs to two lines


# ---------------------------------------------------------------- helpers
def textbox(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP, name="CC_text"):
    y = y + OFFSET_Y
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    return tb, tf


def para(tf, text, size=14, color=BODY, bold=False, font=F_BODY,
         space_before=0, space_after=4, first=False, align=PP_ALIGN.LEFT, italic=False):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(space_before)
    p.space_after = Pt(space_after)
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.name = font
    r.font.color.rgb = color
    return p


def rich_para(tf, chunks, size=14, space_before=0, space_after=4, first=False,
              align=PP_ALIGN.LEFT):
    """chunks = [(text, color, bold), ...] inside one paragraph."""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(space_before)
    p.space_after = Pt(space_after)
    for text, color, bold in chunks:
        r = p.add_run()
        r.text = text
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.name = F_BODY
        r.font.color.rgb = color
    return p


def card(slide, x, y, w, h, fill=CARD, line=CARD_LINE, radius=0.05):
    y = y + OFFSET_Y
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(x), Inches(y), Inches(w), Inches(h))
    sh.adjustments[0] = radius
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = line
    sh.line.width = Pt(1)
    sh.shadow.inherit = False
    sh.text_frame.text = ""
    sh.name = "CC_card"
    return sh


def card_header(slide, x, y, w, text, size=17, color=HEAD):
    tb, tf = textbox(slide, x, y, w, 0.42)
    para(tf, text, size=size, color=color, bold=True, font=F_HEAD, first=True, space_after=0)
    return tb


def bullets(slide, x, y, w, h, items, size=14, color=BODY, gap=6):
    """items = list of strings, or (str, color) tuples."""
    tb, tf = textbox(slide, x, y, w, h)
    for i, item in enumerate(items):
        text, col, sz = (item, color, size) if isinstance(item, str) else \
                        (item[0], item[1] if len(item) > 1 else color,
                         item[2] if len(item) > 2 else size)
        para(tf, text, size=sz, color=col, font=F_BODY, first=(i == 0),
             space_after=gap, space_before=0)
    return tb


def arrow(slide, x, y, w=0.42, h=0.3):
    y = y + OFFSET_Y
    sh = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = ACCENT
    sh.line.fill.background()
    sh.shadow.inherit = False
    sh.name = "CC_arrow"
    return sh


def stat_card(slide, x, y, w, h, big, label, big_color=ACCENT):
    card(slide, x, y, w, h)
    tb, tf = textbox(slide, x + 0.18, y + 0.16, w - 0.36, 0.62)
    para(tf, big, size=32, color=big_color, bold=True, font=F_HEAD, first=True, space_after=0)
    tb2, tf2 = textbox(slide, x + 0.18, y + 0.82, w - 0.36, h - 0.9)
    para(tf2, label, size=13, color=DIM, font=F_BODY, first=True, space_after=0)


def full_width_note(slide, y, h, chunks, size=15, align=PP_ALIGN.LEFT, fill=CARD):
    """chunks = one paragraph (list of (text, colour, bold)).
    A list of such lists makes multiple paragraphs."""
    card(slide, CONTENT_X, y, CONTENT_W, h, fill=fill)
    tb, tf = textbox(slide, CONTENT_X + 0.28, y + 0.16, CONTENT_W - 0.56, h - 0.32,
                     anchor=MSO_ANCHOR.MIDDLE)
    paragraphs = chunks if chunks and isinstance(chunks[0], list) else [chunks]
    for i, para_chunks in enumerate(paragraphs):
        rich_para(tf, para_chunks, size=size, first=(i == 0),
                  space_after=5 if i < len(paragraphs) - 1 else 0, align=align)
    return tf


# ================================================================= SLIDE 1
def slide1(slide, team):
    global OFFSET_Y
    OFFSET_Y = 0.0          # slide 1 values must line up with the template's labels
    # The labels already exist in the template. We add the VALUES next to them,
    # in the same font as the labels so the slide stays consistent.
    values = [
        (" Problem Statement Title: ", 1.12, 6.99, 4.52,
         "Cold-Night Survival - Power & Thermal Autonomy for Near-Space Payloads", 21),
        ("Track: ", 1.21, 7.63, 1.35,
         "04 - Sustainability and Energy Management", 24),
        (" Category[hardware/software]:", 1.12, 8.19, 5.23,
         "Software  (with physical bench validation)", 24),
        ("Team Lead Name:", 1.21, 8.83, 3.06,
         team["lead"], 24),
        (" Team Name:", 1.12, 9.46, 2.26,
         team["name"], 24),
    ]
    for label, lx, ly, lw, value, size in values:
        tb, tf = textbox(slide, lx + lw + 0.12, ly, 18.4 - (lx + lw), 0.48)
        para(tf, value, size=size, color=HEAD, bold=True, font=F_LABEL,
             first=True, space_after=0)

    # one-line project name under the fields
    # (placed below the last label box so it cannot collide if a label wraps)
    tb, tf = textbox(slide, 1.12, 10.42, 17.0, 0.6)
    rich_para(tf, [("COLDSTART", ACCENT, True),
                   ("   |   flight-day power & thermal planner   |   real forecast in, "
                    "PASS/FAIL and the cheapest fix out", DIM, False)],
              size=15, first=True, space_after=0)


# ================================================================= SLIDE 2
def slide2(slide):
    global OFFSET_Y
    OFFSET_Y = 0.18
    full_width_note(slide, TOP, 1.30, [
        ("One question, answered before launch:  ", DIM, False),
        ("will this payload survive the night at -52 C", HEAD, True),
        ("  - and what is the ", DIM, False),
        ("cheapest design", HEAD, True),
        (" that makes it survive?", DIM, False),
    ], size=19)

    y = 3.18
    stat_card(slide, CONTENT_X, y, 5.86, 1.55, "26.4 km", "float altitude - real GFS 20 hPa pressure level")
    stat_card(slide, CONTENT_X + 6.17, y, 5.86, 1.55, "-51.5 C",
              "forecast air temperature on 12 Oct over Chennai", big_color=HEAD)
    stat_card(slide, CONTENT_X + 12.34, y, 5.86, 1.55, "11.5 h",
              "real darkness - from solar geometry, not a guess", big_color=WARN)

    y = 4.90
    card(slide, CONTENT_X, y, 8.95, 2.75)
    card_header(slide, CONTENT_X + 0.24, y + 0.16, 8.4, "THE PROBLEM")
    bullets(slide, CONTENT_X + 0.24, y + 0.66, 8.5, 2.0, [
        "A balloon payload floats where it is -52 C and dark for 11.5 hours.",
        "A cold Li-ion pack cannot give up its bottom 60% of charge - the energy is there but frozen.",
        "Heaters fix the cold, but heaters burn the very energy you are trying to save.",
        "Today this is sized on textbook tables, not on the forecast for the actual launch date.",
    ], size=13.5, gap=7)

    card(slide, CONTENT_X + 9.25, y, 8.95, 2.75)
    card_header(slide, CONTENT_X + 9.49, y + 0.16, 8.4, "WHAT WE BUILT")
    bullets(slide, CONTENT_X + 9.49, y + 0.66, 8.5, 2.0, [
        "A planner that pulls the REAL forecast for your site and date and simulates the whole flight, minute by minute.",
        "It reports the exact minute the battery dies - not a chart to interpret.",
        "It then searches battery size x insulation x heater setting for the CHEAPEST design that still passes.",
        "Validated against a physical bench test we ran during the sprint.",
    ], size=13.5, gap=7)

    y = 7.85
    card(slide, CONTENT_X, y, CONTENT_W, 2.8)
    card_header(slide, CONTENT_X + 0.26, y + 0.16, 17.6,
                "THE OUTPUT IS A DECISION, NOT A DASHBOARD")
    tb, tf = textbox(slide, CONTENT_X + 0.26, y + 0.68, 8.6, 1.9)
    para(tf, "INPUT", size=12, color=DIM, bold=True, font=F_HEAD, first=True, space_after=6)
    para(tf, "6 cells | 10 mm insulation | heater -10 C", size=15, color=BODY, space_after=10)
    para(tf, "VERDICT", size=12, color=DIM, bold=True, font=F_HEAD, space_after=6)
    para(tf, f"FAIL - {FILL['fail_reason']} at {FILL['fail_time']} IST", size=19, color=BAD, bold=True,
         font=F_HEAD, space_after=4)
    para(tf, f"{FILL['fail_hours']} h of the 11.5 h night survived", size=13.5, color=DIM, space_after=0)

    tb, tf = textbox(slide, CONTENT_X + 9.5, y + 0.68, 8.5, 1.9)
    para(tf, "SAME ENGINE, ONE BUTTON LATER", size=12, color=DIM, bold=True,
         font=F_HEAD, first=True, space_after=6)
    para(tf, f"{FILL['rec_cells']} cells | {FILL['rec_ins']} insulation | {FILL['rec_heater']}",
         size=15, color=BODY, space_after=10)
    para(tf, f"PASS - {FILL['rec_margin']} margin, Rs {FILL['rec_cost']}, {FILL['rec_mass']} kg", size=19, color=GOOD, bold=True,
         font=F_HEAD, space_after=4)
    para(tf, "cheapest design that survives the night", size=13.5, color=DIM, space_after=0)


# ================================================================= SLIDE 3
def slide3(slide):
    stages = [
        ("1  REAL DATA", "NOAA GFS upper-air forecast (live), solar irradiance, "
                         "solar geometry, Celestrak TLE, NOAA SWPC space weather."),
        ("2  PHYSICS MODEL", "Fourier conduction Q=(k/t)A(dT), Stefan-Boltzmann "
                             "radiation to cold sky, published 18650 capacity curve."),
        ("3  DESIGN SEARCH", "Sweeps battery cells x insulation thickness x heater "
                             "set-point x panel area. Simulates every combination."),
        ("4  VERDICT + FIX", "PASS or FAIL, the minute of failure, and the cheapest "
                             "passing design with its mass and cost."),
    ]
    x = CONTENT_X
    w = 4.20
    gap = 0.47
    for i, (title, _) in enumerate(stages):
        card(slide, x, TOP, w, 0.72)
        tb, tf = textbox(slide, x + 0.16, TOP + 0.06, w - 0.32, 0.6, anchor=MSO_ANCHOR.MIDDLE)
        para(tf, title, size=15, color=HEAD, bold=True, font=F_HEAD, first=True, space_after=0)
        if i < 3:
            arrow(slide, x + w + 0.03, TOP + 0.24)
        x += w + gap

    y = 2.62
    card(slide, CONTENT_X, y, CONTENT_W, 2.30)
    card_header(slide, CONTENT_X + 0.26, y + 0.16, 17.6,
                "HOW EACH STAGE WORKS - AND WHAT IS REAL")
    x = CONTENT_X + 0.26
    for i, (title, detail) in enumerate(stages):
        tb, tf = textbox(slide, x, y + 0.72, 4.28, 1.45)
        para(tf, detail, size=13, color=BODY, font=F_BODY, first=True, space_after=8)
        if i == 0:
            para(tf, "Every value fetched live at demo time. Cached fallback is "
                     "labelled, never invented.", size=11.5, color=GOOD, italic=True, space_after=0)
        if i == 1:
            para(tf, "Constants are published values; choices are marked "
                     "ASSUMPTION and validated on the bench.", size=11.5, color=GOOD,
                 italic=True, space_after=0)
        if i == 2:
            para(tf, "This search engine is what we built during the hackathon.",
                 size=11.5, color=WARN, italic=True, space_after=0)
        if i == 3:
            para(tf, "Output is a number and a decision, not a graph to interpret.",
                 size=11.5, color=GOOD, italic=True, space_after=0)
        x += 4.60

    y = 5.20
    card(slide, CONTENT_X, y, 8.95, 2.35)
    card_header(slide, CONTENT_X + 0.24, y + 0.16, 8.4, "WHAT IS NOVEL (built during the sprint)")
    bullets(slide, CONTENT_X + 0.24, y + 0.66, 8.5, 1.6, [
        "Existing battery calculators simulate ONE design you already chose. Ours SEARCHES the design space.",
        "The search is coupled: power + thermal + duty cycle are solved together, then ranked by cost.",
        "It answers a question a flight team actually asks the night before launch: 'what is the cheapest thing I can change to make this survive?'",
    ], size=12.5, gap=6)

    card(slide, CONTENT_X + 9.25, y, 8.95, 2.35)
    card_header(slide, CONTENT_X + 9.49, y + 0.16, 8.4, "TOOLS DECLARED (per FAQ 17)")
    bullets(slide, CONTENT_X + 9.49, y + 0.66, 8.5, 1.6, [
        "AI coding assistants used as development aids (disclosed).",
        "All physics implemented, reviewed and validated by the team on a bench rig.",
        "No third-party code copied; all public datasets attributed on slide 6 (FAQ 27).",
    ], size=12.5, gap=6)

    y = 7.80
    card(slide, CONTENT_X, y, CONTENT_W, 1.83)
    tb, tf = textbox(slide, CONTENT_X + 0.26, y + 0.14, CONTENT_W - 0.52, 1.5,
                     anchor=MSO_ANCHOR.MIDDLE)
    para(tf, "CONDUCTION     Q = (k / t) x A x (T_target - T_ambient)",
         size=14, color=HEAD, bold=True, font=F_HEAD, first=True, space_after=6)
    para(tf, "RADIATION      Q = e x s x A x (T_ambient^4 - T_sky^4)      "
             "- this term does NOT shrink when you add insulation",
         size=14, color=HEAD, bold=True, font=F_HEAD, space_after=6)
    para(tf, "BATTERY        capacity = f(temperature), published 18650 datasheet curve; "
             "no charging below 0 C", size=13, color=DIM, space_after=0)


# ================================================================= SLIDE 4
def slide4(slide):
    global OFFSET_Y
    OFFSET_Y = OFFSET_WRAPPED       # this template title wraps to two lines
    y = TOP
    # This card adapts. Fill the three bench values in FILL and it becomes a
    # measurement report. Leave them None and it becomes an honest statement of
    # what IS validated without a rig - plus the limits.
    have_bench = FILL["bench_predicted_ua"] is not None

    card(slide, CONTENT_X, y, 8.95, 4.25)
    if have_bench:
        card_header(slide, CONTENT_X + 0.24, y + 0.16, 8.4,
                    "BENCH VALIDATION - we measured our own model")
        bullets(slide, CONTENT_X + 0.24, y + 0.58, 8.5, 1.80, [
            "Method: constant-power equilibrium test - a known resistor in the insulated box; at "
            "equilibrium, measured UA = power / temperature difference.",
            "Run warm, not cold: heat loss scales with temperature difference, so a warm box in a "
            "normal room measures the same coefficient as a cold box in the stratosphere.",
            "Scope, stated honestly: this validates CONDUCTION (k*A/t). Radiative loss and the "
            "battery curve are NOT validated - they stay listed as limits.",
        ], size=11.5, gap=6)
        tb, tf = textbox(slide, CONTENT_X + 0.24, y + 2.42, 8.5, 1.75)
        rich_para(tf, [("Model predicted UA:  ", DIM, False),
                       (blank_or(FILL["bench_predicted_ua"], "W/K",
                                 lambda v: f"{v:.4f} W/K"), HEAD, True)],
                  size=14, first=True, space_after=8)
        rich_para(tf, [("We measured UA:      ", DIM, False),
                       (blank_or(FILL["bench_measured_ua"], "W/K",
                                 lambda v: f"{v:.4f} W/K"), HEAD, True),
                       ("   (3 runs)", DIM, False)], size=14, space_after=8)
        rich_para(tf, [("Model error:            ", DIM, False),
                       (blank_or(FILL["bench_error_pct"], "%",
                                 lambda v: f"{v:+.0f}%"), GOOD, True)],
                  size=14, space_after=10)
        para(tf, "UA = heat lost per kelvin of temperature difference (W/K). "
                 "Calibrate k_ins to your measurement, then re-run the optimiser.",
             size=11, color=WARN, italic=True, space_after=0)
    else:
        card_header(slide, CONTENT_X + 0.24, y + 0.16, 8.4,
                    "VALIDATION - what we checked, and what we did not")
        bullets(slide, CONTENT_X + 0.24, y + 0.58, 8.5, 2.10, [
            "ATMOSPHERE (checked): our upper-air profile comes from NOAA GFS. Because one model "
            "can be biased, we cross-checked it against the independent ECMWF model - from the "
            "surface to ~20 km they agree to a mean of 0.3 K.",
            "DECISION (checked): re-run with every uncertain input at its range limit. The "
            f"cheapest survivor holds {FILL['rec_tolerance']} of insulation error but only "
            f"{FILL['rec_scen']} stressed scenarios; {FILL['robust_scen']} costs "
            f"Rs {FILL['robust_gap']} more.",
            "THERMAL COEFFICIENT (NOT checked): this needs a bench measurement we did not run. "
            "It stays an ASSUMPTION in our code and is listed as a limit below.",
            "ABOVE 20 km (NOT checked): only GFS is available, and above 31 km we use the "
            "published ISA standard atmosphere.",
        ], size=11, gap=5)
        tb, tf = textbox(slide, CONTENT_X + 0.24, y + 2.98, 8.5, 1.15)
        rich_para(tf, [("We would rather show you a limit than a number we cannot "
                        "defend.", WARN, True)], size=12, first=True, space_after=0)

    card(slide, CONTENT_X + 9.25, y, 8.95, 4.25)
    card_header(slide, CONTENT_X + 9.49, y + 0.16, 8.4, "DESIGN TRADE - real numbers, real forecast")
    tb, tf = textbox(slide, CONTENT_X + 9.49, y + 0.62, 8.5, 3.4)
    rows = [
        ("6 cells, 10 mm, heater -10 C  -  what teams try first",
         f"FAIL {FILL['fail_time']}  |  foam would need to be {FILL['default_deficit']} better",
         BAD, False),
        ("10 cells, 10 mm, heater 0 C  -  'just add batteries'",
         f"FAIL {FILL['lazy_fail_time']}  |  Rs {FILL['lazy_cost']}  |  needs foam "
         f"{FILL['lazy_deficit']} better. Still fails.", BAD, False),
        ("6 cells, 75 mm, heater off  -  cheapest that survives",
         f"PASS {FILL['rec_margin']} margin  |  Rs {FILL['rec_cost']}  |  holds only "
         f"{FILL['rec_scen']} stressed scenarios", WARN, False),
        ("12 cells, 75 mm + panel  -  the robust choice",
         f"PASS {FILL['robust_margin']} margin  |  Rs {FILL['robust_cost']}  |  holds "
         f"{FILL['robust_scen']} stressed scenarios", GOOD, True),
    ]
    for i, (label, value, color, bold) in enumerate(rows):
        para(tf, label, size=12, color=DIM, first=(i == 0), space_after=2)
        para(tf, value, size=14.5, color=color, bold=bold, font=F_HEAD, space_after=9)
    para(tf, "Search: 4 battery sizes x 4 insulation thicknesses x 3 heater settings x 2 heater "
             "ratings x 2 panel areas, then a local refinement - 250 candidates, each run through "
             "the full flight model. Not an exhaustive search; see the app for its stated limits.",
         size=11, color=DIM, italic=True, space_after=0)

    y = 6.15
    full_width_note(slide, y, 1.62, [[
        ("THE FINDING:  ", HEAD, True),
        ("adding batteries makes it WORSE - more cells means a colder, hungrier box. Both "
         "designs a team builds first fail, and they fail even when we give them better "
         "insulation than we assumed.", DIM, False),
    ], [
        ("WHAT SEPARATES THEM:  ", HEAD, True),
        (f"Rs {FILL['rec_cost']} buys the cheapest design that survives the forecast as "
         "issued - but it holds only ", DIM, False),
        (FILL['rec_scen'], BAD, True),
        (" stressed scenarios. ", DIM, False),
        (f"Rs {FILL['robust_gap']} more", BAD, True),
        (" buys ", DIM, False),
        (FILL['robust_scen'], GOOD, True),
        (". The app tells you which one you are buying, and it never calls a "
         "scenario pass rate a survival probability.", DIM, False),
    ]], size=14)

    y = 7.95
    card(slide, CONTENT_X, y, 8.95, 2.7)
    card_header(slide, CONTENT_X + 0.24, y + 0.16, 8.4, "WHAT IT COSTS TO BUILD")
    bullets(slide, CONTENT_X + 0.24, y + 0.62, 8.5, 2.0, [
        f"Recommended design: Rs {FILL['rec_cost']}, {FILL['rec_mass']} kg - "
        f"{FILL['rec_cells']} x 18650 cells, {FILL['rec_ins']} insulation, no heater "
        "(the box holds itself above the limit).",
        ("Bench rig used for validation: about Rs 300-500 of ESP32 + sensor + foam."
         if FILL["bench_predicted_ua"] is not None else
         "Validation cost: Rs 0 - cross-model check plus sensitivity analysis."),
        "Software: Rs 0. Runs on free public APIs with no licence fees.",
    ], size=12, gap=5)

    card(slide, CONTENT_X + 9.25, y, 8.95, 2.7)
    card_header(slide, CONTENT_X + 9.49, y + 0.16, 8.4, "KNOWN LIMITS - STATED OPENLY")
    bullets(slide, CONTENT_X + 9.49, y + 0.62, 8.5, 2.0, [
        "Above ~31 km GFS has no data - we switch to the published ISA standard "
        "atmosphere, and say so.",
        ("Radiative loss and the battery curve are not covered by the bench test."
         if FILL["bench_predicted_ua"] is not None else
         "The thermal coefficient is an ASSUMPTION, not bench-measured - so results are "
         "reported as a sensitivity band."),
        "Solar generation is a sensitivity band, not a single false number.",
        f"It tolerates foam {FILL['rec_tolerance']} worse than assumed; overheating sets an "
        "upper edge at roughly 2.5x better.",
        "Scenario counts are a pass rate over the ranges we tested - never a survival "
        "probability.",
    ], size=10.5, gap=4)


# ================================================================= SLIDE 5
def slide5(slide):
    global OFFSET_Y
    OFFSET_Y = 0.18                 # slide 4 raised it; this title is one line
    y = TOP
    w, gap = 4.20, 0.47
    x = CONTENT_X
    cards = [
        ("PREVENTS LOSS", f"A payload that brownouts at {FILL['fail_time']} is a dead mission. This catches it before launch, not after.", ACCENT),
        ("SAVES MASS", "Right-sized batteries instead of guessed ones. Less mass on every flight means cheaper launch.", HEAD),
        ("REUSABLE", "Same engine plans balloon nights and CubeSat eclipses - different mission, same physics.", WARN),
        ("OPEN DATA", "Runs entirely on free public APIs, so any student team anywhere can use it.", GOOD),
    ]
    for title, text, col in cards:
        card(slide, x, y, w, 3.25)
        tb, tf = textbox(slide, x + 0.22, y + 0.22, w - 0.44, 0.5)
        para(tf, title, size=16, color=col, bold=True, font=F_HEAD, first=True, space_after=0)
        tb2, tf2 = textbox(slide, x + 0.22, y + 0.85, w - 0.44, 2.2)
        para(tf2, text, size=13.5, color=BODY, font=F_BODY, first=True, space_after=0)
        x += w + gap

    y = 5.22
    card(slide, CONTENT_X, y, CONTENT_W, 2.05, fill=RGBColor(0x0A, 0x1F, 0x18),
         line=RGBColor(0x1E, 0x5C, 0x40))
    tb, tf = textbox(slide, CONTENT_X + 0.3, y + 0.2, CONTENT_W - 0.6, 1.65,
                     anchor=MSO_ANCHOR.MIDDLE)
    rich_para(tf, [("THE NUMBER THAT MATTERS:   ", HEAD, True),
                   (f"{FILL['rec_cost'] - FILL['default_cost']}", GOOD, True),
                   ("   rupees.  That is the entire gap between the design that survives the "
                    "night and the design that does not (", DIM, False),
                   (f"Rs {FILL['rec_cost']}", GOOD, True),
                   ("  versus  ", DIM, False),
                   (f"Rs {FILL['default_cost']}", BAD, True),
                   (").  Everything else on this slide is a consequence of that number.", DIM, False)],
              size=16, first=True, space_after=0)

    y = 7.50
    card(slide, CONTENT_X, y, 8.95, 3.15)
    card_header(slide, CONTENT_X + 0.24, y + 0.16, 8.4, "WHO USES IT")
    bullets(slide, CONTENT_X + 0.24, y + 0.68, 8.5, 2.3, [
        "Student high-altitude balloon teams - SEDS REC flies these missions.",
        "Near-space payload operators - the same cold-night problem, with rupees at stake.",
        "CubeSat teams sizing a power budget for an electric-propulsion duty cycle.",
        "Any team that needs a go/no-go answer the night before a launch.",
    ], size=13, gap=7)

    card(slide, CONTENT_X + 9.25, y, 8.95, 3.15)
    card_header(slide, CONTENT_X + 9.49, y + 0.16, 8.4, "WHERE IT GOES NEXT")
    bullets(slide, CONTENT_X + 9.49, y + 0.68, 8.5, 2.3, [
        "Run the same planner for a real flight date and hand the operator a report.",
        "Add the radiosonde archive to validate against real Chennai soundings (WMO 43279).",
        "Extend from a single payload box to a whole mission power budget.",
        "Calibrate the thermal model against more bench measurements, then publish the error.",
    ], size=13, gap=7)


# ================================================================= SLIDE 6
def slide6(slide):
    sources = [
        ("NOAA GFS upper-air forecast", "via Open-Meteo - real temperature, wind and "
         "geopotential height profiles to about 31 km. Public API, no key.", HEAD),
        ("Open-Meteo historical archive (ERA5)", "real measured solar irradiance used to "
         "backtest the model against past conditions.", HEAD),
        ("NASA POWER", "satellite-derived solar resource and temperature, used as the "
         "long-term baseline. Open, attribution required.", HEAD),
        ("Celestrak orbital catalogue (TLE)", "live orbital elements of real satellites; "
         "propagated with SGP4 for eclipse planning. Open data.", HEAD),
        ("NOAA SWPC space weather", "real X-ray flare class and planetary K index feeds.", HEAD),
        ("University of Wyoming radiosonde archive", "real upper-air soundings for Chennai / "
         "Minambakkam, station WMO 43279 - used for validation.", HEAD),
        ("18650 cell manufacturer datasheets", "published capacity-versus-temperature "
         "discharge curves, quoted directly rather than invented.", HEAD),
        ("NOAA solar position algorithm and ISA standard atmosphere", "standard published "
         "methods for sun geometry and the upper atmosphere.", HEAD),
    ]
    x, y = CONTENT_X, TOP
    col_w = 8.95
    for i, (name, desc, col) in enumerate(sources):
        cy = y + (i // 2) * 1.62
        cx = x + (i % 2) * 9.25
        card(slide, cx, cy, col_w, 1.48)
        tb, tf = textbox(slide, cx + 0.22, cy + 0.12, col_w - 0.44, 1.24)
        para(tf, name, size=14, color=col, bold=True, font=F_HEAD, first=True, space_after=3)
        para(tf, desc, size=12, color=BODY, space_after=0)

    y = 8.25
    card(slide, CONTENT_X, y, CONTENT_W, 2.4, fill=RGBColor(0x1A, 0x14, 0x06),
         line=RGBColor(0x5C, 0x45, 0x1E))
    tb, tf = textbox(slide, CONTENT_X + 0.3, y + 0.2, CONTENT_W - 0.6, 2.0,
                     anchor=MSO_ANCHOR.MIDDLE)
    para(tf, "ATTRIBUTION AND LICENCES", size=15, color=WARN, bold=True,
         font=F_HEAD, first=True, space_after=8)
    para(tf, "Every dataset used is public and is credited above by name. No dataset is "
             "redistributed with this submission; we query the sources live at demonstration "
             "time and cache the response only so the demo survives a network failure, "
             "clearly labelled as CACHED (per FAQ 27).", size=13, color=BODY, space_after=6)
    para(tf, "Assumptions made by the team (box geometry, payload load, insulation "
             "properties beyond datasheet values) are marked ASSUMPTION in our source code "
             "and are listed on slide 4 as limits to be validated.", size=13, color=BODY,
         space_after=0)


# ---------------------------------------------------------------- build
def main():
    # Team details come from the FILL block at the top of this file.
    team = {"name": FILL["team_name"], "lead": FILL["team_lead"]}

    prs = Presentation(SRC)
    slides = list(prs.slides)
    print(f"template has {len(slides)} slides")

    slide1(slides[0], team)
    slide2(slides[1])
    slide3(slides[2])
    slide4(slides[3])
    slide5(slides[4])
    slide6(slides[5])

    prs.save(DST)
    print(f"saved -> {DST}")


if __name__ == "__main__":
    main()
