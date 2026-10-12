"""
snapshot.py -- pin the demo data to a file.

WHAT THIS IS FOR
----------------
A live demo has two enemies: a flaky venue network, and irreproducibility. If the
forecast re-fetches between your rehearsal and your pitch, the numbers move and
you cannot explain why. This script captures the exact real responses the engine
uses into `data/demo_snapshot.json`, together with where each one came from and
when it was retrieved. The engine can then replay that file with no network at
all, and every screen shows a SNAPSHOT badge so nobody mistakes it for live.

WHAT THIS IS NOT
----------------
It is not a way to fake a forecast. The snapshot contains only REAL API responses
captured at a known instant. If a feed cannot be reached while writing the
snapshot, this script FAILS LOUDLY rather than substituting anything. And it does
not change the default behaviour: the app still fetches live first and falls back
to the labelled cache only when the network is down.

USAGE
    python app/snapshot.py                 # capture at the default demo site/date
    python app/snapshot.py --date 2026-10-12 --lat 13.0067 --lon 80.2570
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import data_sources as ds                                   # noqa: E402

DEFAULT_LAT = 13.0067        # Rajalakshmi Engineering College, Chennai
DEFAULT_LON = 80.2570
DEFAULT_DATE = "2026-10-12"

# The ECMWF cross-check uses the same pressure levels and site as
# validate_atmosphere.py, so the snapshot holds both models' view of the same
# atmosphere. Two independent agencies, two independent data assimilations.
CROSSCHECK_LEVELS = [925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30, 20]
CROSSCHECK_HOSTS = {
    "crosscheck_gfs": "https://api.open-meteo.com/v1/gfs",
    "crosscheck_ecmwf": "https://api.open-meteo.com/v1/ecmwf",
}


def fetch_live(url, timeout=45):
    """A live-only fetch. There is deliberately no cached fallback here: a
    snapshot labelled LIVE that was actually served from an old cache file would
    be a lie about provenance."""
    req = urllib.request.Request(url, headers={"User-Agent": "COLDSTART-sedhacks26/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def crosscheck_url(host, lat, lon, date_str):
    variables = []
    for p in CROSSCHECK_LEVELS:
        variables += [f"temperature_{p}hPa", f"wind_speed_{p}hPa"]
    return host + "?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "hourly": ",".join(variables),
        "start_date": date_str, "end_date": date_str,
        "wind_speed_unit": "ms", "timezone": "Asia/Kolkata",
    })


def main():
    ap = argparse.ArgumentParser(description="Pin the demo forecast to a file.")
    ap.add_argument("--lat", type=float, default=DEFAULT_LAT)
    ap.add_argument("--lon", type=float, default=DEFAULT_LON)
    ap.add_argument("--date", default=DEFAULT_DATE)
    args = ap.parse_args()

    print("=" * 74)
    print("  PINNING DEMO SNAPSHOT")
    print(f"  site {args.lat}, {args.lon}   date {args.date}")
    print("=" * 74)

    feeds = {}

    # --- the two feeds the engine actually simulates with ------------------
    for name, (url, key) in ds.environment_urls(args.lat, args.lon, args.date).items():
        print(f"\n  fetching {name} (live) ...")
        payload = fetch_live(url)
        feeds[key] = {"model": ("NOAA GFS via Open-Meteo" if name == "upper_air"
                                else "GFS shortwave radiation via Open-Meteo"),
                      "url": url, "payload": payload}
        hours = payload.get("hourly", {}).get("time", [])
        print(f"    OK  {len(hours)} hours, key {key}")

    # --- the ECMWF cross-check, so the offline demo can still show two models
    for name, host in CROSSCHECK_HOSTS.items():
        url = crosscheck_url(host, args.lat, args.lon, args.date)
        label = "NOAA GFS" if name.endswith("gfs") else "ECMWF IFS"
        print(f"\n  fetching {name} ({label}) ...")
        payload = fetch_live(url)
        key = f"{name}_{args.date}.json"
        feeds[key] = {"model": f"{label} via Open-Meteo", "url": url, "payload": payload}
        print(f"    OK  {len(payload.get('hourly', {}).get('time', []))} hours, key {key}")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snapshot = {
        "snapshot_version": 1,
        "retrieved_utc": stamp,
        "site": {"lat": args.lat, "lon": args.lon},
        "date": args.date,
        "note": ("REAL API responses pinned for demo replay. Not synthetic data. "
                 "Every response carries the URL it came from; the capture instant "
                 "is retrieved_utc. The engine reads this file only when snapshot "
                 "mode is explicitly requested."),
        "feeds": feeds,
    }

    os.makedirs(os.path.dirname(ds.SNAPSHOT_PATH), exist_ok=True)
    with open(ds.SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=1)

    size_kb = os.path.getsize(ds.SNAPSHOT_PATH) / 1024.0
    print("\n" + "=" * 74)
    print(f"  WROTE {os.path.relpath(ds.SNAPSHOT_PATH)}")
    print(f"  {len(feeds)} feeds, {size_kb:.0f} KB, captured {stamp}")
    print("=" * 74)


if __name__ == "__main__":
    main()
