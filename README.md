# COLDSTART — SEDHACKS '26
Flight-day power & thermal autonomy planner for near-space payloads.

## Run it
    cd app
    python3 server.py
    # open http://localhost:8000

## Test it  (run these from the repo root)
    python -m unittest discover -s tests    # unit + regression tests
    python app/verify.py                    # physics benchmarks, energy balance,
                                            #   convergence, stress analysis
    python app/check_deck.py                # does every number on the slides still
                                            #   reproduce from the engine?

`verify.py` writes `verify/results.json` and `verify/RESULTS.md`; the
Verification tab of the UI reads that file, so re-run it after a physics change
or the tab will show stale numbers.

## Files
    START_HERE.md              <- READ THIS FIRST (beginner guide + schedule + slides)
    SEDHACKS26_playbook.md     <- the strategy document
    data_layer_verify.py       <- standalone proof that all real data feeds work
    app/server.py              <- web server (stdlib only)
    app/data_sources.py        <- real API fetchers with offline cache
    app/static/index.html      <- one-page UI, no libraries

    app/engine/                <- THE MODEL. One concern per module:
        params.py              <- every constant, each tagged SOURCE or ASSUMPTION
        mission.py             <- the flight simulation loop (heat + power together)
        thermal.py             <- conduction, convection, radiation, skin temperature
        battery.py             <- capacity vs temperature, derating, state of charge
        atmosphere.py          <- standard atmosphere + solar geometry
        optimizer.py           <- searches the design space for the cheapest PASS
        uncertainty.py         <- stress scenarios + one-at-a-time sensitivity
        battle.py              <- head-to-head design comparison
        cost.py                <- Rs and kg for a design
        verification.py        <- the benchmark suite that verify.py runs

`app/physics.py` is the SUPERSEDED model. It is kept only as a reference copy;
nothing in `app/` imports it any more. Do not add new work to it.

## Rule to remember
Everything marked `# SOURCE:` is a real published value.
Everything marked `# ASSUMPTION:` is our choice and must be validated.
Never delete those comments.
