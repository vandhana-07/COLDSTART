"""
diagnose.py -- "why won't localhost open?" answered on YOUR machine.

Run this and it will check all five usual causes, actually start the server,
actually fetch a page from it, and then tell you the exact URL to open.

    python3 diagnose.py          (macOS / Linux)
    python server.py  ->  NO.  run:  python diagnose.py    (Windows)

It changes nothing: it starts a temporary server on a spare port, tests it, and
shuts it down again. Nothing is written except a temp log.

Stdlib only, like the rest of this project. No pip installs.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app")
SERVER = os.path.join(APP, "server.py")

PASS, FAIL, WARN, INFO = "  [ OK ]", "[FAIL]", "[WARN]", "  ..  "
problems = []


def say(mark, text):
    print(f"{mark} {text}")


def free_port(preferred=8000):
    """Try the preferred port; if it is taken, find a free one."""
    for port in (preferred, 8080, 8888, 9000, 0):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("0.0.0.0", port))
            got = s.getsockname()[1]
            s.close()
            return got, port == preferred
        except OSError:
            continue
    return 0, False


def main():
    print("=" * 72)
    print("  COLDSTART -- connection diagnosis")
    print("=" * 72)
    print()

    # ---------------------------------------------------------------- 1. Python
    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 10):
        say(PASS, f"1. Python {ver}  (needs 3.10+)")
    else:
        say(FAIL, f"1. Python {ver} is TOO OLD -- this app needs 3.10 or newer.")
        problems.append("Install Python 3.10+ and use that interpreter.")

    # ------------------------------------------------- 2. files / imports work
    if not os.path.exists(SERVER):
        say(FAIL, f"2. Cannot find {SERVER}")
        print("\n  You are running diagnose.py from the wrong place, or the folder is incomplete.")
        print("  diagnose.py must sit in the same folder as the app/ directory.")
        return 1
    say(PASS, "2. Found app/server.py")

    # --------------------------------------------- 3. is the port already busy?
    port, got_preferred = free_port(8000)
    if not port:
        say(FAIL, "3. No usable free port found.")
        return 1
    if got_preferred:
        say(PASS, "3. Port 8000 is free")
    else:
        say(WARN, "3. Port 8000 is ALREADY IN USE (something else has it).")
        # is the thing on 8000 actually our app? if so that is good news
        is_coldstart = False
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=5) as r:
                body = r.read()
                if b"COLDSTART" in body:
                    is_coldstart = True
                    say(INFO, "     ...and it IS a COLDSTART server. It is already running")
                    say(INFO, "     and ready to use! Just open:")
                    say(INFO, "     http://127.0.0.1:8000")
        except Exception:
            pass
        say(INFO, f"     Testing a temporary server on port {port} instead.")
        if not is_coldstart:
            problems.append(f"Port 8000 is busy. Start on another one: see the command at the end.")

    # -------------------------------------------- 4. localhost vs 127.0.0.1 trap
    print()
    say(INFO, "4. Checking how 'localhost' resolves on this machine...")
    v6_only = False
    try:
        infos = socket.getaddrinfo("localhost", port, proto=socket.IPPROTO_TCP)
        families = [i[0].name for i in infos]
        first = families[0] if families else "?"
        print(f"       localhost -> {', '.join(families)}   (tried in this order)")
        if first == "AF_INET6" and "AF_INET" in families:
            v6_only = True
            say(WARN, "     'localhost' prefers IPv6 (::1), but COLDSTART listens on")
            say(WARN, "     IPv4 only. Some browsers then fail on http://localhost")
            say(WARN, "     even though the server is fine.")
            problems.append("Use http://127.0.0.1:PORT instead of http://localhost:PORT")
        else:
            say(PASS, "     No IPv6/IPv4 mismatch detected")
    except Exception as exc:
        say(WARN, f"     Could not resolve localhost: {exc}")

    # -------------------------------- 5. start it for real and fetch a real page
    print()
    say(INFO, f"5. Starting the app on port {port} and fetching a real page...")
    env = dict(os.environ, PORT=str(port))
    log = os.path.join(os.path.dirname(HERE), "diagnose_server.log")
    log_f = open(log, "w")
    try:
        proc = subprocess.Popen([sys.executable, "server.py"], cwd=APP, env=env,
                                stdout=log_f, stderr=subprocess.STDOUT,
                                text=True)
    except Exception as exc:
        log_f.close()
        say(FAIL, f"     Could not launch the server: {exc}")
        return 1

    try:
        up = False
        for _ in range(60):
            if proc.poll() is not None:
                log_f.flush()
                with open(log, "r") as rf:
                    out = rf.read()
                say(FAIL, "     The server EXITED immediately. It printed:")
                for line in out.strip().splitlines()[-8:]:
                    print("        " + line)
                if "Address already in use" in out:
                    problems.append(f"Port {port} got taken. Try another: PORT=8081")
                return 1
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/", timeout=3) as r:
                    r.read()
                up = True
                break
            except Exception:
                time.sleep(0.3)

        if not up:
            say(FAIL, "     Server started but never answered on 127.0.0.1. Firewall?")
            problems.append("A firewall/VPN is likely blocking local connections.")
            return 1

        say(PASS, f"     Server answers on http://127.0.0.1:{port}")

        # the page itself
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=15) as r:
            html = r.read().decode("utf-8", "replace")
        say(PASS, f"     The UI page loads ({len(html)} bytes of HTML)")

        # a real simulation, snapshot mode so it works with no internet
        url = f"http://127.0.0.1:{port}/api/plan?snapshot=1&date=2026-10-12"
        with urllib.request.urlopen(url, timeout=120) as r:
            d = json.loads(r.read())
        verdict, when = d.get("verdict"), d.get("failure_time")
        if verdict == "FAIL" and when == "00:14":
            say(PASS, f"     Simulation ran: {verdict} at {when}  <-- this is the expected result")
        else:
            say(WARN, f"     Simulation ran: {verdict} at {when} (expected FAIL / 00:14)")

        # live mode, only if there is internet
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/health", timeout=20) as r:
                h = json.loads(r.read())
            src = (h.get("open_meteo_gfs") or {}).get("source")
            say(PASS if src == "LIVE" else WARN,
                f"     Forecast feed: {src}   ({'live data OK' if src == 'LIVE' else 'no internet -- snapshot mode still works'})")
        except Exception:
            say(WARN, "     Could not check the live forecast feed")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_f.close()

    # ------------------------------------------------------------------ verdict
    print()
    print("=" * 72)
    if problems:
        print("  WHAT TO DO")
        print("=" * 72)
        for i, p in enumerate(problems, 1):
            print(f"   {i}. {p}")
    else:
        print("  EVERYTHING WORKS ON THIS MACHINE.")
        print("=" * 72)
    print()
    print("  START THE APP:")
    if os.name == "nt":
        print("     cd app")
        print("     python server.py")
    else:
        print("     cd app")
        print("     python3 server.py")
    print()
    print("  OPEN THIS URL  (use 127.0.0.1, not localhost):")
    print(f"     http://127.0.0.1:{port if got_preferred else 8000}")
    print()
    print("  You should see: a FAIL verdict at 00:14 for the default design.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
