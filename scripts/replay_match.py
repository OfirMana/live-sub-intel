"""Replays a StatsBomb match through the live engine and prints recommendations.

    python scripts/replay_match.py --match 3754065 --at 55 60 65 70 75
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from subintel import profiles
from subintel.engine import MatchState, recommend
from subintel.schema import EventType
from subintel.statsbomb import OPEN_DATA, PREMIER_LEAGUE, SEASON_2015_16, load_events, load_lineups

from build_player_buckets import fetch


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", default="3754065")  # Tottenham 0-1 Leicester, 13 Jan 2016
    ap.add_argument("--at", type=int, nargs="+", default=[55, 60, 65, 70, 75])
    ap.add_argument("--buckets", type=Path, default=Path("data/player_buckets.csv"))
    ap.add_argument("--cache", type=Path, default=Path("data/raw"))
    ap.add_argument("--json", action="store_true", help="print the full Recommendation JSON")
    args = ap.parse_args()

    matches = json.loads(fetch(f"{OPEN_DATA}/matches/{PREMIER_LEAGUE}/{SEASON_2015_16}.json",
                               args.cache / "matches" / f"{PREMIER_LEAGUE}_{SEASON_2015_16}.json").read_text())
    match = next(m for m in matches if str(m["match_id"]) == args.match)
    # Pre-match profiles: only matches played before this one, so nothing leaks from the future.
    book = profiles.build(pd.read_csv(args.buckets), before_date=match["match_date"])

    events = load_events(fetch(f"{OPEN_DATA}/events/{args.match}.json", args.cache / "events" / f"{args.match}.json"), args.match)
    players, slots = load_lineups(fetch(f"{OPEN_DATA}/lineups/{args.match}.json", args.cache / "lineups" / f"{args.match}.json"))
    starters = {s.player_id for s in slots if s.on_from_clock == 0}
    ms = MatchState(args.match, players, starters, book)
    names = {match["home_team"]["home_team_id"]: match["home_team"]["home_team_name"],
             match["away_team"]["away_team_id"]: match["away_team"]["away_team_name"]}

    checkpoints = sorted(args.at)
    for ev in events:
        while checkpoints and ev.period == 2 and ev.minute >= checkpoints[0]:
            report(ms, checkpoints.pop(0), names, args.json)
        if ev.type is EventType.SUBSTITUTION:
            print(f"  >> actual sub {ev.minute}': {ms.players[ev.player_id].name} -> {ms.players[ev.replacement_id].name}")
        if (ev.type is EventType.SHOT and ev.goal) or ev.type is EventType.OWN_GOAL:
            print(f"  >> GOAL {ev.minute}': {names[int(ev.team_id)]}")
        ms.feed(ev)


def report(ms: MatchState, minute: int, names: dict, as_json: bool) -> None:
    print(f"\n===== {minute}' =====")
    for team_id in ms.team_ids:
        rec = recommend(ms, team_id)
        if as_json:
            print(rec.model_dump_json(indent=2))
            continue
        n = rec.needs
        print(f"{names[int(team_id)]}  (goal diff {rec.state.goal_diff:+d}, subs left {rec.state.subs_left})")
        print("   needs  " + "  ".join(f"{d} {v:.2f}" for d, v in n.needs.items()))
        print("   z      " + "  ".join(f"{d} {v:+.1f}" for d, v in n.deficit_z.items()))
        print(f"   recommend: {rec.recommend}")
        for o in rec.options:
            delta = " ".join(f"{d[:4]} {v:+.0f}" for d, v in o.delta_pct.items())
            print(f"     OUT {o.out_name:22s} IN {o.in_name:20s} score {o.score:+.2f} benefit {o.expected_benefit:+.2f} [{o.strength}]  {delta}")


if __name__ == "__main__":
    main()
