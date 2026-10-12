# COLDSTART — SEDHACKS '26
Flight-day power & thermal autonomy planner for near-space payloads.

## Run it
    cd app
    python3 server.py
    # open http://localhost:8000

## Files
    START_HERE.md              <- READ THIS FIRST (beginner guide + schedule + slides)
    SEDHACKS26_playbook.md     <- the strategy document
    data_layer_verify.py       <- standalone proof that all real data feeds work
    app/server.py              <- web server (stdlib only)
    app/physics.py             <- the model: battery, heat, power
    app/data_sources.py        <- real API fetchers with offline cache
    app/static/index.html      <- one-page UI, no libraries

## Rule to remember
Everything marked `# SOURCE:` is a real published value.
Everything marked `# ASSUMPTION:` is our choice and must be validated.
Never delete those comments.
