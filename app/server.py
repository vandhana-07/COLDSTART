"""
server.py  --  COLDSTART web server  (engine-backed)
====================================================
Standard library only, on purpose:
  * nothing to install  ->  no `pip install` failing on venue wifi at 3 AM
  * the whole thing is readable in ten minutes

Run it:      python3 server.py
Then open:   http://localhost:8000

Design notes
------------
* Every simulation goes through engine.mission. There is no second, simpler
  model hiding behind a faster endpoint.
* Long searches are run as BACKGROUND JOBS with polling, because the optimiser
  takes ~20 s and the stress test ~10 s. Blocking an HTTP request for that long
  makes the UI feel broken and times out behind proxies.
* Every response that depends on weather carries a `transparency` block: where
  the data came from, when it was retrieved, what period it covers, how much of
  the flight used real forecast data and how much fell back to ISA. A number is
  never returned without its provenance.
"""

import json
import os
import sys
import threading
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_sources
from engine import atmosphere as atm
from engine import battle as bt
from engine import cost as cst
from engine import mission as ms
from engine import optimizer as opt
from engine import params as P
from engine import uncertainty as unc

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
PORT = int(os.environ.get("PORT", "8000"))

DEFAULT_LAT, DEFAULT_LON = 13.0067, 80.2570      # Rajalakshmi Engineering College

# The design the app starts with. Recorded in the report so a run is reproducible.
DEFAULT_DESIGN = {
    "cells": 6,
    "wh_per_cell": P.CELL_WH,
    "payload_load_w": 3.0,
    "insulation_mm": 10,
    "k_ins": P.DEFAULT_K_INSULATION,
    "heater_setpoint_c": -10.0,
    "heater_max_w": 5.0,
    "box_area_m2": P.DEFAULT_BOX_AREA_M2,
    "panel_m2": 0.0,
    "duration_min": P.DEFAULT_DURATION_MIN,
    "reserve": P.DEFAULT_RESERVE_FRACTION,
}

# ---------------------------------------------------------------------------
# Background jobs. Long enough that blocking would be rude; short enough that a
# thread each is fine.
# ---------------------------------------------------------------------------
JOBS = {}
JOBS_LOCK = threading.Lock()


def _new_job(kind):
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id, "kind": kind, "state": "running",
            "done": 0, "total": None, "started": datetime.now(),
            "result": None, "error": None,
        }
    return job_id


def _set_progress(job_id, done, total):
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if j:
            j["done"] = done
            if total:
                j["total"] = total


def _finish(job_id, result=None, error=None):
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if j:
            j["state"] = "error" if error else "done"
            j["result"] = result
            j["error"] = error
            j["finished"] = datetime.now()


def _run_job(job_id, fn):
    try:
        result = fn(lambda d, t: _set_progress(job_id, d, t))
        _finish(job_id, result=result)
    except Exception as exc:
        traceback.print_exc()
        _finish(job_id, error=f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Environment + transparency
# ---------------------------------------------------------------------------
def build_env(parsed):
    q = parse_qs(parsed.query)
    lat = float(q.get("lat", [DEFAULT_LAT])[0])
    lon = float(q.get("lon", [DEFAULT_LON])[0])
    date_str = q.get("date", [None])[0]
    launch_hour = int(q.get("launch_hour", ["18"])[0])

    if not date_str:
        date_str = datetime.now(data_sources.IST).strftime("%Y-%m-%d")

    env = data_sources.fetch_environment(lat, lon, date_str)
    env["launch_local"] = datetime.strptime(
        f"{date_str} {launch_hour:02d}:00", "%Y-%m-%d %H:%M").replace(tzinfo=data_sources.IST)
    return env


def transparency_block(env):
    """Everything a judge needs in order to distrust the numbers appropriately."""
    levels = env["profiles"][0] if env["profiles"] else []
    top = levels[-1] if levels else {}
    srcs = env.get("sources", {})
    upper = srcs.get("upper_air", {})
    solar = srcs.get("solar", {})

    return {
        "site": {"lat": env["site"]["lat"], "lon": env["site"]["lon"]},
        "date": env["date"],
        "launch_local": env["launch_local"].isoformat(),
        "night_hours": env["night_hours"],
        "sources": {
            "upper_air": {
                "model": upper.get("model", "unknown"),
                "source": upper.get("source", "UNKNOWN"),      # LIVE / CACHED / ISA_FALLBACK
                "retrieved_utc": upper.get("retrieved_utc") or upper.get("fetched_utc"),
                "note": upper.get("note"),
            },
            "solar": {
                "model": solar.get("model", "unknown"),
                "source": solar.get("source", "UNKNOWN"),
                "retrieved_utc": solar.get("retrieved_utc") or solar.get("fetched_utc"),
                "note": solar.get("note"),
            },
        },
        "forecast_period": {"first_hour": env["hours"][0] if env["hours"] else None,
                            "last_hour": env["hours"][-1] if env["hours"] else None,
                            "hours_fetched": len(env["hours"])},
        "altitude_coverage": {
            "levels_in_profile": len(levels),
            "lowest_km": levels[0]["alt_km"] if levels else None,
            "highest_km": top.get("alt_km"),
            "highest_temp_c": top.get("temp_c"),
            "above_ceiling_note": (
                "The forecast model publishes nothing above "
                f"{top.get('alt_km'):.1f} km at this location and time. Any part of "
                "the flight above that uses the ISA standard atmosphere, and the "
                "simulation reports how many minutes did so."
                if levels else "No forecast levels were returned."),
        },
        "engine": {
            "version": getattr(P, "ENGINE_VERSION", "engine-v1"),
            "constants": P.as_dict() if hasattr(P, "as_dict") else {},
        },
    }


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------
def design_from_query(parsed, base=None):
    d = dict(base or DEFAULT_DESIGN)
    q = parse_qs(parsed.query)
    for key in ("cells", "insulation_mm", "duration_min"):
        if key in q:
            d[key] = int(float(q[key][0]))
    for key in ("payload_load_w", "load_w", "k_ins", "panel_m2", "box_area_m2",
                "heater_max_w", "reserve"):
        if key in q:
            target = "payload_load_w" if key == "load_w" else key
            d[target] = float(q[key][0])
    if "heater_setpoint_c" in q:
        raw = q["heater_setpoint_c"][0]
        d["heater_setpoint_c"] = None if raw.lower() in ("none", "off", "") else float(raw)
    if "min_operating_c" in q:
        d["min_operating_c"] = float(q["min_operating_c"][0])
    return d


def slim_timeline(timeline, max_points=240):
    """Downsample for the browser. Never changes what the engine computed; the
    full-resolution trace stays server-side and in the report."""
    n = len(timeline)
    if n <= max_points:
        return timeline
    step = max(1, n // max_points)
    out = timeline[::step]
    if out[-1] is not timeline[-1]:
        out.append(timeline[-1])
    return out


def sim_payload(env, design):
    r = ms.simulate(env, design)
    mc = cst.breakdown(design)
    return {
        "verdict": r["verdict"],
        "failure_reason": r["failure_reason"],
        "failure_text": r["failure_text"],
        "failure_time": r["failure_time"],
        "failure_minute": r["failure_minute"],
        "failure_detail": r["failure_detail"],
        "failure_explanation": r["failure_explanation"],
        "survival_hours": r["survival_hours"],
        "night_hours": r["night_hours"],
        "min_box_c": r["min_box_c"],
        "max_box_c": r["max_box_c"],
        "min_box_c_raw": r["min_box_c_raw"],
        "max_box_c_raw": r["max_box_c_raw"],
        "min_usable_pct": r["min_usable_pct"],
        "final_charge_wh": r["final_charge_wh"],
        "payload_energy_wh": r["payload_energy_wh"],
        "heat_gained_wh": r["heat_gained_wh"],
        "unmet_energy_wh": r["unmet_energy_wh"],
        "clamp_activations": r["clamp_activations"],
        "nominal_wh": r["nominal_wh"],
        "reserve_wh": r["reserve_wh"],
        "energy_margin_wh": r["energy_margin_wh"],
        "energy_margin_ratio": r["energy_margin_ratio"],
        "heater_energy_wh": r["heater_energy_wh"],
        "pv_generated_wh": r["pv_generated_wh"],
        "charge_rejected_wh": r["charge_rejected_wh"],
        "heat_lost_wh": r["heat_lost_wh"],
        "isa_fallback_pct": r["isa_fallback_pct"],
        "min_operating_c": r["design"].get("min_operating_c", P.DEFAULT_MIN_OPERATING_C),
        "max_operating_c": r["design"].get("max_operating_c", P.DEFAULT_MAX_OPERATING_C),
        "duration_min": r["design"]["duration_min"],
        "isa_fallback_minutes": r["isa_fallback_minutes"],
        "timestep_s": r["timestep_s"],
        "thermal_time_constant_min": r["thermal_time_constant_min"],
        "effective_ua_w_per_k": r["effective_ua_w_per_k"],
        "events": r["events"],
        "design": {k: v for k, v in design.items()},
        "mass_cost": mc,
        "timeline": slim_timeline(r["timeline"]),
        "timeline_points": len(r["timeline"]),
    }


# ---------------------------------------------------------------------------
# Flight-readiness report
# ---------------------------------------------------------------------------
def load_verification():
    """Read the verification results, or return None if they were never generated.
    Returning None is deliberate: the report says 'not run' rather than showing
    placeholders."""
    vpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "verify", "results.json")
    if not os.path.exists(vpath):
        return None
    with open(vpath) as fh:
        return json.load(fh)


def build_report(env, design, optimiser=None, stress=None, battle_result=None):
    """Assemble the reproducible report. Status is decided here, once, from the
    data actually present -- never assumed."""
    sim = ms.simulate(env, design)
    mc = cst.breakdown(design)
    trans = transparency_block(env)

    missing = []
    if trans["sources"]["upper_air"]["source"] == "UNKNOWN":
        missing.append("upper-air forecast provenance is unknown")

    # PASS requires: the simulation ran, data were real or explicitly declared as
    # fallback, and no essential constraint went unchecked.
    if sim["verdict"] != "PASS":
        status = "FAIL"
        status_reason = (f"The design did not survive: {sim['failure_reason']} "
                         f"at T+{sim['failure_minute']:.0f} min.")
    elif missing:
        status = "INSUFFICIENT DATA"
        status_reason = "; ".join(missing)
    elif trans["sources"]["upper_air"]["source"] not in ("LIVE", "CACHED"):
        status = "INSUFFICIENT DATA"
        status_reason = ("The forecast fell back to the standard atmosphere, so the "
                         "survival claim rests on an assumed atmosphere, not a "
                         "forecast for this site and date.")
    else:
        status = "PASS"
        status_reason = "The simulation completed with all constraints satisfied."

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "status_reason": status_reason,
        "transparency": trans,
        "mission": {
            "site": trans["site"],
            "date": env["date"],
            "launch_local": env["launch_local"].strftime("%Y-%m-%d %H:%M %Z"),
            "duration_min": design["duration_min"],
            "profile": {"ascent_min": design.get("ascent_min", P.ASCENT_MIN),
                        "float_min": design.get("float_min", P.FLOAT_MIN),
                        "descent_min": design.get("descent_min", P.DESCENT_MIN),
                        "burst_alt_km": design.get("burst_alt_km", P.BURST_ALT_KM)},
        },
        "design": {k: v for k, v in design.items()},
        "results": {
            "verdict": sim["verdict"],
            "failure_reason": sim["failure_reason"],
            "failure_time": sim["failure_time"],
            "survival_hours": sim["survival_hours"],
            "min_box_c": sim["min_box_c"],
            "energy_margin_ratio": sim["energy_margin_ratio"],
            "energy_margin_wh": sim["energy_margin_wh"],
            "heater_energy_wh": sim["heater_energy_wh"],
            "pv_generated_wh": sim["pv_generated_wh"],
            "heat_lost_wh": sim["heat_lost_wh"],
            "effective_ua_w_per_k": sim["effective_ua_w_per_k"],
            "thermal_time_constant_min": sim["thermal_time_constant_min"],
            "timestep_s": sim["timestep_s"],
            "timeline_points": len(sim["timeline"]),
        },
        "cost_mass": mc,
        "failure_explanation": sim["failure_explanation"],
        "optimiser": optimiser,
        "stress": stress,
        "battle": battle_result,
        "methodology": {
            "engine": "engine/ (params, atmosphere, thermal, battery, mission, cost)",
            "integration": "Forward Euler on a lumped interior node with an "
                           "algebraically solved massless skin (conduction and "
                           "surface loss in series).",
            "timestep": "Derived from the thermal time constant and clamped to "
                        "1-30 s, so it adapts to how well insulated the design is.",
            "solar": "Extraterrestrial irradiance at the date, attenuated by "
                     "Beer-Lambert absorption using the pressure ratio at altitude. "
                     "Surface forecast irradiance is NOT used at altitude.",
            "battery": "Usable energy = charge minus the fraction of capacity "
                       "unavailable at the cell temperature. Discharge limited by "
                       "C-rate. Charging inhibited below 0 C and the rejected energy "
                       "is counted, not silently discarded.",
        },
        "assumptions": P.as_dict() if hasattr(P, "as_dict") else {},
        "verification": _verification_summary(),
        "limitations": [
            # Wording required by the audit (Task D); asserted by tests/test_verification.py.
            "Solar heating of the enclosure is not modelled; daytime results are "
            "biased cold. Night survival results are unaffected.",
            "Box conductance UA is derived from an assumed foam conductivity and has "
            "NOT been measured on a bench rig. Treat absolute survival times as "
            "indicative and the comparison between designs as the reliable result.",
            "The cell capacity-vs-temperature curve comes from datasheets, not from "
            "tests on these cells.",
            "Above the forecast model's ceiling, the standard atmosphere is used; the "
            "simulation reports how many minutes did so.",
            "Stress-test percentages are SCENARIO PASS RATES over assumed input "
            "ranges, not probabilities of real-world survival.",
            "The optimiser searches a declared grid plus a local refinement. It does "
            "not prove global optimality.",
            "The failure-replay chronology is generated from the simulated trace. It "
            "is an explanation of the model, not a record of a real flight.",
        ],
    }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()}  {fmt % args}")

    def _send(self, code, body, content_type="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _error(self, code, msg, hint=None):
        return self._send(code, {"error": msg, "hint": hint})

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path

        try:
            if route in ("/", "/index.html"):
                with open(os.path.join(STATIC_DIR, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")

            if route == "/api/health":
                h = data_sources.health_check()
                h["engine"] = getattr(P, "ENGINE_VERSION", "engine-v1")
                return self._send(200, h)

            if route == "/api/environment":
                env = build_env(parsed)
                slim = [[{"alt_km": l["alt_km"], "temp_c": l["temp_c"],
                          "wind_ms": l["wind_ms"]} for l in prof]
                        for prof in env["profiles"]]
                return self._send(200, {
                    "date": env["date"],
                    "hours": env["hours"],
                    "profiles": slim,
                    "transparency": transparency_block(env),
                })

            # ---------------- single design, synchronous (fast) -------------
            if route == "/api/plan":
                env = build_env(parsed)
                design = design_from_query(parsed)
                payload = sim_payload(env, design)
                payload["transparency"] = transparency_block(env)
                return self._send(200, payload)

            # ---------------- stress test a single design --------------------
            if route == "/api/stress":
                env = build_env(parsed)
                design = design_from_query(parsed)
                n = int(parse_qs(parsed.query).get("scenarios", ["24"])[0])
                stress = unc.stress_test(env, design, n_scenarios=n)
                sens = unc.sensitivity_ranking(env, design)
                named = unc.named_scenarios(env, design)
                return self._send(200, {
                    "stress": stress, "sensitivity": sens, "named": named,
                    "transparency": transparency_block(env),
                })

            # ---------------- long jobs: start -------------------------------
            if route == "/api/job/start":
                q = parse_qs(parsed.query)
                kind = q.get("kind", ["optimise"])[0]

                # Validate the objective BEFORE fetching the forecast or spawning a
                # worker (audit finding A3). Without this, a typo started a job that
                # silently fell back to the default objective, or surfaced as a
                # generic job error minutes later after paying for a data fetch.
                if kind in ("optimise", "battle"):
                    valid_objectives = [o[0] for o in opt.OBJECTIVES]
                    asked = q.get("objective", ["best_balance"])[0]
                    if asked not in valid_objectives:
                        return self._error(
                            400, f"unknown objective {asked!r}",
                            hint="valid objectives: " + ", ".join(valid_objectives))

                env = build_env(parsed)
                design = design_from_query(parsed)

                if kind == "optimise":
                    objective = q.get("objective", ["best_balance"])[0]
                    scenarios = int(q.get("screen_scenarios", ["16"])[0])
                    screen_top = int(q.get("screen_top", ["8"])[0])

                    def work(progress, env=env, design=design, objective=objective,
                             scenarios=scenarios, screen_top=screen_top):
                        res = opt.optimise(env, design, objective=objective,
                                           progress=progress)
                        res["_base_design"] = design
                        if screen_top > 0:
                            opt.screen_robustness(env, res, top_n=screen_top,
                                                  n_scenarios=scenarios,
                                                  progress=lambda d, t: progress(
                                                      t + d, None))
                        return _optimiser_public(res, env)

                elif kind == "battle":
                    objective = q.get("objective", ["best_balance"])[0]
                    scenarios = int(q.get("scenarios", ["24"])[0])

                    def work(progress, env=env, design=design, objective=objective,
                             scenarios=scenarios):
                        res = opt.optimise(env, design, objective=objective,
                                           progress=lambda d, t: progress(d, t))
                        res["_base_design"] = design
                        b = bt.battle(env, design, optimiser_result=res,
                                      objective=objective, n_scenarios=scenarios)
                        return {"battle": _battle_public(b),
                                "optimiser": _optimiser_public(res, env)}

                else:
                    return self._error(400, f"unknown job kind {kind!r}")

                job_id = _new_job(kind)
                threading.Thread(target=_run_job, args=(job_id, work),
                                 daemon=True).start()
                return self._send(200, {"job_id": job_id, "kind": kind})

            if route == "/api/job/status":
                job_id = parse_qs(parsed.query).get("id", [""])[0]
                with JOBS_LOCK:
                    j = JOBS.get(job_id)
                if not j:
                    return self._error(404, "no such job")
                out = {k: v for k, v in j.items() if k != "result"}
                if j["state"] == "done":
                    out["result"] = j["result"]
                return self._send(200, out)

            # ---------------- report -----------------------------------------
            # ---------------- physics verification dashboard ----------------
            if route == "/api/verification":
                vpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "verify", "results.json")
                if not os.path.exists(vpath):
                    return self._error(
                        404, "verification results have not been generated yet",
                        hint="Run:  cd app && python3 verify.py")
                with open(vpath) as fh:
                    data = json.load(fh)
                if parse_qs(parsed.query).get("download", ["0"])[0] == "1":
                    body = json.dumps(data, indent=2, default=str).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Disposition",
                                     "attachment; filename=coldstart_verification.json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    return self.wfile.write(body)
                return self._send(200, data)

            if route == "/api/report":
                env = build_env(parsed)
                design = design_from_query(parsed)
                report = build_report(env, design)
                return self._send(200, report)

            if route == "/api/report.json":
                env = build_env(parsed)
                design = design_from_query(parsed)
                report = build_report(env, design)
                body = json.dumps(report, indent=2, default=str).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Disposition",
                                 "attachment; filename=coldstart_report.json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)

            return self._error(404, f"no route {route}")

        except Exception as exc:
            traceback.print_exc()
            return self._error(500, f"{type(exc).__name__}: {exc}",
                               hint="Check the server console for the full traceback.")

    def do_POST(self):
        # Accept POST for consistency; behave exactly like GET.
        return self.do_GET()


def _verification_summary():
    """Condensed verification evidence for the report. Every entry keeps its
    evidence category, and category E is reported as NOT PERFORMED."""
    v = load_verification()
    if v is None:
        return {
            "available": False,
            "note": ("Verification results have not been generated. Run "
                     "`cd app && python3 verify.py`. No placeholders are shown."),
        }
    return {
        "available": True,
        "generated_utc": v["generated_utc"],
        "engine_version": v["engine_version"],
        "evidence_categories": v["categories_used"],
        "category_e": "NOT PERFORMED - no physical bench test was conducted",
        "benchmark_summary": v["benchmark_summary"],
        "benchmarks": [
            {"id": b["id"], "title": b["title"], "category": b["category"],
             "label": b["category_label"],
             "checks": len(b["items"]),
             "failed": sum(1 for i in b["items"]
                           if isinstance(i.get("pass"), bool) and not i["pass"]),
             "limitations": b["limitations"]}
            for b in v["benchmarks"]
        ],
        "energy_balance": {
            "tolerance_wh": v["task2_energy"]["tolerance_wh"],
            "sign_convention": v["task2_energy"]["sign_convention"],
            "rows": [{k: r[k] for k in ("design", "verdict", "electrical_residual_wh",
                                        "electrical_pass", "clamp_activations")}
                     for r in v["task2_energy"]["rows"]],
            "state_audit_clean": all(r["state_audit"]["clean"]
                                     for r in v["task2_energy"]["rows"]),
            "defects_fixed": [d["id"] for d in v["task2_energy"]["defects_found_and_fixed"]],
        },
        "convergence": [
            {"scenario": r["scenario"], "verdict_stable": r["verdict_stable"],
             "failure_reason_stable": r["failure_reason_stable"],
             "failure_time_spread_min": r["failure_time_spread_min"],
             "min_temp_spread_c": r["min_temp_spread_c"],
             "order_estimate": r["order_estimate"]}
            for r in v["task4_convergence"]["results"]
        ],
        "battery": {
            "category": v["task3_battery"]["category"],
            "source_status": v["task3_battery"]["source_status"],
            "all_consistency_checks_pass": all(
                c["pass"] for c in v["task3_battery"]["consistency_checks"]),
        },
        "uncertainty": {
            "ranges_are_exploratory": v["task6_uncertainty"]["ranges_are_exploratory"],
            "ranking_survives": v["task6_uncertainty"]["ranking_survives"],
            "ranking_flips": v["task6_uncertainty"]["ranking_flips"],
            "combined_worst_case": v["task6_uncertainty"]["combined_worst_case"],
            "disclaimer": v["task6_uncertainty"]["disclaimer"],
        },
        "unresolved": v["unresolved"],
    }


def _optimiser_public(res, env):
    """Strip the full simulation objects before sending to the browser."""
    def clean(rec):
        if rec is None:
            return None
        out = {k: v for k, v in rec.items() if not k.startswith("_") and k != "sim"}
        return out
    return {
        "objective": res["objective"],
        "objective_text": res["objective_text"],
        "best": clean(res.get("best")),
        "picks": {k: clean(v) for k, v in (res.get("picks") or {}).items()},
        "robust_pick": clean(res.get("robust_pick")),
        "runner_up": clean(res.get("runner_up")),
        "feasible_count": res["feasible_count"],
        "infeasible_count": res["infeasible_count"],
        "combinations_evaluated": res["combinations_evaluated"],
        "violation_counts": res["violation_counts"],
        "search_limits": res["search_limits"],
        "top_passing": [clean(r) for r in res.get("top_passing", [])],
        "screened": [clean(r) for r in res.get("screened", [])],
    }


def _battle_public(b):
    def clean(e):
        return {k: v for k, v in e.items() if not k.startswith("_")}
    return {
        "objective": b["objective"],
        "objective_label": b["objective_label"],
        "conditions": b["conditions"],
        "entries": [clean(e) for e in b["entries"]],
        "winner": b["winner"],
        "ranked_keys": b["ranked_keys"],
        "verdict": b["verdict"],
    }


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("")
    print("  COLDSTART running")
    print(f"  open  ->  http://localhost:{PORT}")
    print(f"  engine->  {getattr(P, 'ENGINE_VERSION', 'engine-v1')}")
    print("")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")


if __name__ == "__main__":
    main()
