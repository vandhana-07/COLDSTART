"""
browser_check.py -- drive the real UI in a headless browser.

WHY THIS EXISTS
---------------
Every other check in this project tests Python. None of them would notice a
JavaScript syntax error, a missing DOM id, a tab that throws on click, or a
badge that never renders. Those failures are invisible to unittest and would
only appear in front of judges, which is the worst possible moment.

This script therefore boots the actual server, opens the actual page in headless
Chromium, clicks every tab, and asserts:

  1. every tab loads with no uncaught JS exception and no console error;
  2. in SNAPSHOT mode the SNAPSHOT badge is visible in the Run, Inspect, Export
     and Verification tabs;
  3. live mode is still the default: a plain run shows real provenance
     (LIVE or CACHED) and must NOT claim to be a snapshot.

NOT a unittest file on purpose - it needs a browser and a server, so
`unittest discover -s tests` must not pick it up.

RUN
    python tests/browser_check.py
"""

import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "app")
PORT = int(os.environ.get("BROWSER_CHECK_PORT", "8731"))
BASE = f"http://127.0.0.1:{PORT}"

TABS = ["run", "inspect", "optimize", "stress", "battle", "export", "verify"]


class Result:
    def __init__(self):
        self.checks, self.errors = [], []

    def check(self, name, ok, detail=""):
        self.checks.append((name, bool(ok), detail))
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f"   {detail}" if detail else ""))
        if not ok:
            self.errors.append(f"{name}: {detail}")
        return ok


def start_server():
    env = dict(os.environ, PORT=str(PORT))
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=APP, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(80):
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=2):
                return proc
        except Exception:
            if proc.poll() is not None:
                print(proc.stdout.read())
                raise RuntimeError("server exited during startup")
            time.sleep(0.25)
    proc.terminate()
    raise RuntimeError("server did not answer /api/health")


def collect(page, bag):
    """Attach listeners BEFORE any navigation so nothing is missed."""
    page.on("console", lambda m: bag.append(f"console.{m.type}: {m.text}")
            if m.type in ("error",) else None)
    page.on("pageerror", lambda e: bag.append(f"pageerror: {e}"))


def run():
    from playwright.sync_api import sync_playwright

    r = Result()
    proc = start_server()
    print(f"\nserver up on {BASE}\n")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1600, "height": 1000})

            # =============== live mode is the DEFAULT ======================
            print("LIVE MODE (default, toggle off)")
            bag = []
            page = ctx.new_page()
            collect(page, bag)
            page.goto(BASE, wait_until="networkidle")
            page.fill("#c-date", "2026-10-12")
            page.click("#b-run")
            page.wait_for_function(
                "() => document.querySelector('#run-trans') && "
                "document.querySelector('#run-trans').innerHTML.length > 50",
                timeout=120_000)
            trans = page.inner_text("#run-trans")
            flags = page.eval_on_selector_all(
                "#run-trans .flag", "els => els.map(e => e.textContent.trim())")
            r.check("live: run completes and shows provenance",
                    any(f in ("LIVE", "CACHED", "ISA_FALLBACK") for f in flags),
                    f"flags={flags}")
            r.check("live: run does NOT claim to be a snapshot",
                    "SNAPSHOT" not in trans.upper(),
                    "no snapshot badge when the toggle is off")
            r.check("live: no JS errors on the Run tab", not bag, "; ".join(bag))
            page.close()

            # =============== SNAPSHOT mode =================================
            print("\nSNAPSHOT MODE (toggle on)")
            bag = []
            page = ctx.new_page()
            collect(page, bag)
            page.goto(BASE, wait_until="networkidle")
            page.fill("#c-date", "2026-10-12")
            page.check("#c-snap")
            r.check("snapshot: toggle exists and is checkable",
                    page.is_checked("#c-snap"))

            page.click("#b-run")
            page.wait_for_function(
                "() => document.querySelector('#run-trans') && "
                "document.querySelector('#run-trans').innerHTML.length > 50",
                timeout=120_000)
            run_txt = page.inner_text("#run-trans")
            r.check("snapshot: badge visible in RUN tab",
                    bool(re.search(r"SNAPSHOT\s+\d{4}-\d{2}-\d{2}", run_txt)),
                    re.search(r"SNAPSHOT\s+\S+", run_txt).group(0)
                    if re.search(r"SNAPSHOT\s+\S+", run_txt) else "badge not found")

            # every tab must open cleanly -> catches broken ids and thrown handlers
            for t in TABS:
                page.click(f'#nav button[data-tab="{t}"]')
                page.wait_for_timeout(400)
                vis = page.is_visible(f"#tab-{t}")
                r.check(f"tab '{t}' opens", vis)
            r.check("no JS errors while visiting all 7 tabs", not bag, "; ".join(bag))

            # INSPECT: charts draw and the transparency panel keeps the badge
            page.click('#nav button[data-tab="inspect"]')
            page.wait_for_timeout(900)
            insp = page.inner_text("#inspect-trans")
            r.check("snapshot: badge visible in INSPECT tab",
                    "SNAPSHOT" in insp.upper(),
                    re.search(r"SNAPSHOT\s+\S+", insp).group(0)
                    if re.search(r"SNAPSHOT\s+\S+", insp) else "badge not found")

            # EXPORT report
            page.click('#nav button[data-tab="export"]')
            page.click("#b-report")
            page.wait_for_function(
                "() => document.querySelector('#report-result') && "
                "document.querySelector('#report-result').innerHTML.length > 500",
                timeout=120_000)
            rep = page.inner_text("#report-result")
            r.check("snapshot: badge visible in EXPORT tab",
                    "SNAPSHOT" in rep.upper(),
                    re.search(r"SNAPSHOT\s+\S+", rep).group(0)
                    if re.search(r"SNAPSHOT\s+\S+", rep) else "badge not found")
            for need in ("assum", "provenance", "retrieved", "limitation"):
                r.check(f"export report mentions '{need}'",
                        need in rep.lower())

            # VERIFICATION tab -> reads verify/results.json
            page.click('#nav button[data-tab="verify"]')
            page.click("#b-verify")
            page.wait_for_function(
                "() => document.querySelector('#verify-result') && "
                "document.querySelector('#verify-result').innerHTML.length > 500",
                timeout=120_000)
            vtxt = page.inner_text("#verify-result") + page.inner_text("#verify-status")
            r.check("snapshot: badge visible in VERIFICATION tab",
                    "SNAPSHOT" in vtxt.upper(),
                    re.search(r"SNAPSHOT\s+\S+", vtxt).group(0)
                    if re.search(r"SNAPSHOT\s+\S+", vtxt) else "badge not found")

            final = []
            collect(page, final)
            r.check("no JS errors across the whole snapshot session",
                    not bag and not final, "; ".join(bag + final))

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print("\n" + "=" * 70)
    passed = sum(1 for _, ok, _ in r.checks if ok)
    print(f"  {passed}/{len(r.checks)} checks passed")
    if r.errors:
        print("  FAILURES:")
        for e in r.errors:
            print("    - " + e)
    else:
        print("  All browser checks passed.")
    print("=" * 70)
    return 0 if not r.errors else 1


if __name__ == "__main__":
    sys.exit(run())
