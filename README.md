# Integrated coach room

**Live demo (Azure App Service):** https://live-sub-intel-fcfudheze9b5ewfz.swedencentral-01.azurewebsites.net/
· deployed automatically from `main` by `.github/workflows/main_live-sub-intel.yml`
(tests run before every deployment).

English-default interface with Hebrew/RTL, automatic full-XI tactical plans and
explanations of the alternative you inspect. Run:

```bash
pip install -e ".[dev,llm]"
python scripts/serve_app.py --port 8778
```

Open http://127.0.0.1:8778/. The same startup entry point is used on Azure.
[Integration details and limits](docs/INTEGRATED_ROOM.md) ·
[Prompt for the teammate's Claude to diagnose Foundry](docs/CLAUDE_FOUNDRY_HANDOFF.md).
The model selects verified facts; the app renders the explanation. Without
Foundry configuration the source is explicitly labelled as a verified template.
The older project notes below describe earlier entry points and experiments.

# Live Substitution Intelligence

## Automatic tactical plans — 19 October 2026

The isolated `feature/coach-match-room` branch automatically compares every
available outfield substitution pair, supported formations and complete XI
assignments, including repositioning without a substitution. The coach sets
stance and a win/draw objective; no formation choice is required. Both pitches
show names, shirt numbers and the selected plan's position changes.

Start `python scripts/serve_coach_room.py --port 8775` and open
http://127.0.0.1:8775/. See [current algorithm, evidence and integration](docs/AUTO_TACTICAL_PLANS.md)
or the [Hebrew teammate handoff](docs/COACH_HANDOFF_HE.md).
This remains a separate research scorer with heuristic position suitability;
the shared engine and teammate LLM/demo are unchanged.

Microsoft × Premier League "Inside the Game" hackathon. Team: Thomas, Tal, Ofir.

An explainable live layer that reads a match event stream, works out what the
team needs right now, and shows which substitution would address it, with the
trade-offs, or says that no change is worth making. Deterministic analytics
underneath; the LLM only explains.

The shared spec is [`docs/CONTRACT.md`](docs/CONTRACT.md). Read it first.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Whole 2015/16 Premier League season from StatsBomb Open Data -> data/player_buckets.csv
# (~40 s; --delete-raw keeps only the 5 MB CSV)
python scripts/build_player_buckets.py --delete-raw

# Replay Tottenham 0-1 Leicester (13 Jan 2016) through the live engine
python scripts/replay_match.py --at 55 65 70 80
python scripts/replay_match.py --at 65 --json   # the Recommendation JSON the LLM/UI receive

pytest
```

## Layout

```
src/subintel/
  schema.py      the contract: Event, GameState, TeamNeeds, SubOption, Recommendation
  statsbomb.py   StatsBomb JSON -> Event (the only file that knows StatsBomb)
  metrics.py     Event -> metric components; shared by profiles and the live engine
  profiles.py    pre-match player profiles and team baselines
  engine.py      MatchState, team needs, substitution ranking
  demo_live.py   demo-card scoring, freshness balance, formation changes
  narrative.py   explanation layer: facts -> LLM (Microsoft Foundry) or template
scripts/         build_player_buckets.py, replay_match.py, explain_recommendation.py, ...
docs/            CONTRACT.md, FOUNDRY_HE.md, examples/recommendation.json
```

## Explanation layer

The engine decides; the LLM only explains. `narrative.explain(snapshot, audience, lang)`
sends the model a small facts object and rejects any text containing a number that is
not in it, falling back to a deterministic template (also used offline). Audiences:
`fan`, `analyst`, `broadcaster`; languages: `he`, `en`.

```bash
pip install -e ".[llm]"   # only needed for the LLM; the template works without it
export FOUNDRY_ENDPOINT=... FOUNDRY_DEPLOYMENT=...   # and FOUNDRY_API_KEY, never committed
python scripts/explain_recommendation.py --minute 75 --lang he
```

Microsoft Foundry setup, step by step (Hebrew): [`docs/FOUNDRY_HE.md`](docs/FOUNDRY_HE.md).

## Game room with explanations (web app)

```bash
python scripts/serve_app.py            # http://127.0.0.1:8000
```

Serves the game room plus `/api/explain` and `/healthz`. Explanations are generated
server-side (the key never reaches the browser), only for the checkpoints the game
room shows, and model answers are cached, so a public deployment makes at most
4 views x 18 checkpoints x 3 audiences x 2 languages model calls. Without the
`FOUNDRY_*` variables it serves the deterministic template. On a host:
`python scripts/serve_app.py --host 0.0.0.0 --port $PORT`. The offline bundle in
`docs/match-replay` has no server and hides the explanation panel.

Deploying it to Azure App Service, step by step (Hebrew): [`docs/AZURE_DEPLOY_HE.md`](docs/AZURE_DEPLOY_HE.md).

## Plan to the 27 October deadline

| Days | Person 1: data, profiles | Person 2: needs, substitutions | Person 3: stream, AI, UI |
|---|---|---|---|
| 15–16 Oct | review contract, freeze v0 | review contract, freeze v0 | Foundry model deployment, UI skeleton on `examples/recommendation.json` |
| 17–20 Oct | possession pool for the generator; profile QA | tune constants on 3–4 real matches; pick the demo scenario | narrative prompt (3 audiences, 2 languages); FastAPI + SSE stream |
| 21–23 Oct | synthetic generator with the scenario script | "no change" calibration; ranked alternatives | wire generator → engine → LLM → UI |
| 24–25 Oct | feature freeze; end-to-end rehearsals | | deploy (Azure Container Apps) |
| 26 Oct | demo video, write-up | | |
| 27 Oct | buffer, submit | | |

Out of scope before submission: tracking data, extra dimensions, more agents,
multiple scenarios.

## Data

StatsBomb Open Data (https://github.com/hudl/open-data), Premier League 2015/16
(competition 2, season 27). Raw files are not committed. Their terms ask anyone
publishing analysis based on the data to name StatsBomb as the source and use
their logo.

## Reproducible player cards and synthetic demo

```
PYTHONPATH=src python scripts/build_demo_dataset.py
PYTHONPATH=src python scripts/run_synthetic_demo.py
python -m http.server 8765 --directory data/synthetic_demo
```

Open http://localhost:8765 and select team/minute, or press Play. This is an
interactive playback of deterministic checkpoints from original synthetic events.
Outputs: `events.jsonl`, `recommendations.json`, `index.html`. The explanatory
text is deterministic; a remote LLM/API/Azure service is not required or deployed.
Player source data, formulas, caveats and the complete acceptance table are in
`demo_data/README.md` and `demo_data/player_acceptance_table.md`.

Research validation (requires network for cached real StatsBomb events):

```
PYTHONPATH=src python scripts/benchmark_demo.py
```

Existing team metrics are preserved. Demo recommendations use the new 0..100
cards, supported positions and bounded live adjustments; the older replay CLI
still uses the legacy rate profiles. Neither engine permits generic formation
changes. Recommendation thresholds and physical mappings remain provisional.

For actual event-by-event streaming, run:

```
PYTHONPATH=src python scripts/serve_demo.py --port 8765
```

Open the local URL and press **Stream events**. Each viewer gets a fresh Python
engine; synthetic events feed sequentially over SSE and recommendations recompute
after each simulated minute. **Play checkpoints** also works from the exported
standalone HTML. The server binds only to 127.0.0.1 and is not publicly deployed.

## Current four-team revision — 18 October 2026

72 matchday player cards cover Liverpool, Arsenal, Chelsea and Tottenham. Observed
pre-cutoff goals/assists and technical output now enter capped profile signals.
Freshness uses a separate near-term horizon; threshold stays .15. 54 Python tests and 3 Node tests pass.
The 12 team-match research replays have 216 five-minute checkpoints; Liverpool
now receives recommendations in all three checked fixtures. This is not evidence
that the football decisions are validated: center-back/early-swap biases remain.

- [Hebrew team handoff](docs/TEAM_HANDOFF_HE.md)
- [Calculation details and limitations](docs/MODEL_UPDATE_HE.md)
- [Player browser, workbook and offline ZIP](docs/player-cards/README.md)
- [Interactive five-minute research report](docs/research/README.md)
- [Step-by-step match replay UI and offline download](docs/match-replay/README.md)
- [Validation and sensitivity](docs/VALIDATION.md)

Work is on the fork branch feature/demo-player-dataset. Upstream main is unchanged.
GitHub Pages, remote LLM and Azure are not configured. Download the offline bundles
to view HTML, or serve docs locally. Rich demo JSON still needs UI/API alignment.
