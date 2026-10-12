"""
validate_atmosphere.py -- VALIDATION WITHOUT ANY HARDWARE
=========================================================
The bench rig validated ONE number: how much heat leaks out of an insulated box.
If you are not building the rig, you still need an answer to "how do we know
your numbers are right?" This script gives you a real, defensible answer.

WHAT IT DOES
------------
Our app's atmosphere comes from ONE source: the NOAA GFS forecast.
If that model had a bias over Chennai, our temperature - and therefore our whole
verdict - would be wrong, and we would never know.

So we check it against a SECOND, INDEPENDENT source: the ECMWF IFS model
(European Centre for Medium-Range Weather Forecasts). GFS is American; IFS is
European. Separate agencies, separate physics, separate data assimilation.
Where two independent models agree, that is evidence the input is sound.

This is called INTERCOMPARISON - standard practice in meteorology. It is NOT a
substitute for measuring your own box, but it does cover the part you cannot
measure from a hostel room: the atmosphere at 26 km.

IMPORTANT SCOPE LIMIT (the script detects this for you)
-------------------------------------------------------
The ECMWF model stops around 50 hPa (~20 km). Our payload floats at ~26 km.
So the float band CANNOT be cross-validated with a second model - the script
says so explicitly rather than implying agreement that does not exist.

  VALIDATED     : upper-air profile, surface to ~20 km (two independent models)
  NOT VALIDATED : the 26 km float band (only GFS available there)
  NOT VALIDATED : the box heat-loss coefficient (needs the bench rig)
  NOT VALIDATED : the battery capacity curve (needs a cold discharge test)

Say all four sentences on stage. The honest scope is the point.

Run:  python3 validate_atmosphere.py
"""

import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "..", "cache")
os.makedirs(CACHE, exist_ok=True)

SITE = {"name": "REC Chennai", "lat": 13.0067, "lon": 80.2570}
DATE = "2026-10-12"        # flight day
HOUR = 12                  # 12:00 IST, near the float phase

# Pressure levels with altitude from the ISA standard atmosphere.
# NOTE: 20 hPa is ~26 km - exactly where our payload floats, so it matters most.
LEVELS = [(1000, 0.1), (925, 0.8), (850, 1.5), (700, 3.0), (600, 4.4),
          (500, 5.9), (400, 7.2), (300, 9.2), (250, 10.4), (200, 11.8),
          (150, 14.1), (100, 16.2), (70, 18.5), (50, 20.6), (30, 23.8), (20, 26.4)]

FLOAT_LOW, FLOAT_HIGH = 20.0, 28.0


def fetch(tag, host, date_str):
    variables = []
    for p, _ in LEVELS:
        variables += ["temperature_" + str(p) + "hPa", "wind_speed_" + str(p) + "hPa"]
    query = urllib.parse.urlencode({
        "latitude": SITE["lat"], "longitude": SITE["lon"],
        "hourly": ",".join(variables),
        "start_date": date_str, "end_date": date_str,
        "wind_speed_unit": "ms", "timezone": "Asia/Kolkata",
    })
    url = host + "?" + query
    path = os.path.join(CACHE, tag + "_" + date_str + ".json")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "COLDSTART-validation/1.0"})
        with urllib.request.urlopen(req, timeout=35) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        open(path, "w").write(raw)
        return json.loads(raw), "LIVE"
    except Exception as exc:
        if os.path.exists(path):
            return json.loads(open(path).read()), "CACHED (" + exc.__class__.__name__ + ")"
        raise


def profile(data, hour_index):
    hourly = data["hourly"]
    out = {}
    for p, alt in LEVELS:
        key = "temperature_" + str(p) + "hPa"
        series = hourly.get(key) or []
        if hour_index < len(series) and series[hour_index] is not None:
            out[p] = series[hour_index]
    return out


def main():
    line = "=" * 82
    print(line)
    print("  ATMOSPHERE CROSS-VALIDATION  --  no hardware required")
    print("  site: " + SITE["name"] + "   date: " + DATE + " " + str(HOUR).zfill(2) + ":00 IST")
    print(line)

    try:
        gfs_data, gfs_src = fetch("gfs", "https://api.open-meteo.com/v1/gfs", DATE)
    except Exception as exc:
        print("  Could not reach GFS: " + str(exc))
        return
    try:
        ec_data, ec_src = fetch("ecmwf", "https://api.open-meteo.com/v1/ecmwf", DATE)
    except Exception as exc:
        print("  Could not reach ECMWF: " + str(exc))
        return

    print("")
    print("  source A: NOAA GFS   (American)   status: " + gfs_src)
    print("  source B: ECMWF IFS  (European)   status: " + ec_src)
    print("")
    print("  Two independent operational models - separate agencies, separate physics.")
    print("  Agreement between them is evidence the profile we simulate is sound.")
    print("")

    a_all = profile(gfs_data, HOUR)
    b_all = profile(ec_data, HOUR)

    # What is the highest level the second model actually publishes?
    ec_levels = [p for p, _ in LEVELS if p in b_all]
    ec_max_p = min(ec_levels) if ec_levels else None
    ec_ceiling = next((alt for p, alt in LEVELS if p == ec_max_p), None)

    print("  " + "{:>9} {:>10} {:>10} {:>11} {:>10}   {:<22}".format(
        "alt (km)", "level", "GFS (C)", "ECMWF (C)", "diff (K)", "region"))
    print("  " + "-" * 78)

    lower_diffs, float_diffs = [], []
    for p, alt in sorted(LEVELS, key=lambda item: -item[1]):
        in_float = FLOAT_LOW <= alt <= FLOAT_HIGH
        region = "FLOAT BAND" if in_float else ("lower atmosphere" if alt < FLOAT_LOW else "above float")
        a = a_all.get(p)
        b = b_all.get(p)
        if a is None:
            print("  " + "{:>9.2f} {:>7} hPa {:>10} {:>10} {:>10}   {:<22}".format(
                alt, str(p), "--", "--", "--", region) + " (no GFS)")
            continue
        if b is None:
            print("  " + "{:>9.2f} {:>7} hPa {:>10.1f} {:>10} {:>10}   {:<22}".format(
                alt, str(p), a, "--", "--", region) + " (no 2nd source)")
            continue
        d = a - b
        if in_float:
            float_diffs.append(abs(d))
        else:
            lower_diffs.append(abs(d))
        print("  " + "{:>9.2f} {:>7} hPa {:>10.1f} {:>10.1f} {:>+10.2f}   {:<22}".format(
            alt, str(p), a, b, d, region))

    print("  " + "-" * 78)

    print("")
    print(line)
    print("  RESULT")
    print(line)

    if lower_diffs:
        print("")
        print("  LOWER ATMOSPHERE (surface to ~20 km) - " + str(len(lower_diffs)) + " levels compared:")
        print("      mean difference between the two models : {:.2f} K".format(
            sum(lower_diffs) / len(lower_diffs)))
        print("      worst-case difference                  : {:.2f} K".format(max(lower_diffs)))

    print("")
    if float_diffs:
        print("  FLOAT BAND (20-28 km) - " + str(len(float_diffs)) + " levels compared:")
        print("      mean difference : {:.2f} K".format(sum(float_diffs) / len(float_diffs)))
    else:
        p_txt = str(ec_max_p) + " hPa" if ec_max_p else "an unknown level"
        c_txt = "~{:.0f} km".format(ec_ceiling) if ec_ceiling else "an unknown height"
        print("  FLOAT BAND (20-28 km):  NO SECOND SOURCE AVAILABLE.")
        print("      The European model stops at " + p_txt + " (" + c_txt + "),")
        print("      which is BELOW our 26 km float altitude.")

    print("")
    print(line)
    print("  HONEST SCOPE - put this on slide 4 in these words. It is what earns marks.")
    print(line)
    ceiling_txt = ("~{:.0f} km".format(ec_ceiling)) if ec_ceiling else "about 20 km"
    print("""
  1. The upper-air profile IS cross-validated against a second independent
     model, from the surface up to """ + ceiling_txt + """.""")

    print("""  2. ABOVE that, the profile rests on the GFS model ALONE - we have no second
     source. Above ~31 km no model data exists at all, and we switch to the
     published ISA standard atmosphere.

  3. The box heat-loss coefficient is NOT validated unless you build the bench
     rig. We say so plainly rather than implying otherwise.

  4. The battery capacity curve is NOT validated. It comes from published 18650
     datasheets and is listed as a limit.

  """)
    print(line)
    print("  THE THREE SENTENCES FOR THE JURY")
    print(line)
    print("""
  1. "Our atmosphere input is the NOAA GFS forecast. Because a single model can
     be biased, we cross-checked it against the independent ECMWF model: from
     the surface to ~20 km they agree to within X K. Above 20 km only GFS is
     available, and above 31 km we use the ISA standard atmosphere - both
     stated as limits."

  2. "We did not build the bench rig, so the thermal coefficient is UNVALIDATED.
     We are not claiming otherwise."

  3. "Instead we validated the DECISION, not the number. sensitivity.py shows
     which designs still pass when the thermal constant is 2-3x wrong. Our
     recommendation survives that; the obvious alternatives do not."

  Saying sentence 2 out loud is what makes 1 and 3 believable.
  """)


if __name__ == "__main__":
    main()
