# Live Substitution Intelligence

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
scripts/         build_player_buckets.py, replay_match.py
docs/            CONTRACT.md, examples/recommendation.json
```

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
