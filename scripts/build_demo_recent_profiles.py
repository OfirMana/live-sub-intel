"""Build recent-form and playable-position profiles for a demo match.

Example:
    python scripts/build_demo_recent_profiles.py
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from subintel.metrics import DIMENSIONS
from subintel.physical import PHYSICAL_REFERENCE_BY_ROLE, PHYSICAL_REFERENCE_SOURCE
from subintel.profiles import build
from subintel.recent_profiles import (
    aggregate_recent_profile,
    attributes_template,
    csv_safe_profile_row,
    merge_player_attributes,
    merge_position_minutes,
    position_minutes_from_lineup,
    select_recent_appearances,
    summarize_positions,
)
from subintel.statsbomb import OPEN_DATA

DEFAULT_MATCH_ID = "3754305"
DEFAULT_DATE = "2016-01-13"


def fetch_json(url: str, path: Path) -> list[dict]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(urllib.request.urlopen(url, timeout=120).read())
        tmp.rename(path)
    return json.loads(path.read_text())


def target_squad(lineup: list[dict]) -> pd.DataFrame:
    rows = []
    for team in lineup:
        for player in team["lineup"]:
            rows.append(
                {
                    "player_id": str(player["player_id"]),
                    "name": player.get("player_nickname") or player["player_name"],
                    "team_id": str(team["team_id"]),
                    "team_name": team["team_name"],
                }
            )
    return pd.DataFrame(rows).drop_duplicates("player_id")


def build_demo_profiles(
    buckets: pd.DataFrame,
    target_lineup: list[dict],
    historical_lineups: list[list[dict]],
    before_date: str,
    attributes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the analysis-ready target-squad table from already-loaded inputs."""
    squad = target_squad(target_lineup)
    target_ids = set(squad["player_id"])

    book = build(buckets, before_date=before_date)

    histories = [
        position_minutes_from_lineup(lineup, target_ids)
        for lineup in historical_lineups
    ]
    positions_by_player = merge_position_minutes(histories)

    out_rows = []
    for player in squad.to_dict("records"):
        pid = player["player_id"]
        recent_rows = select_recent_appearances(buckets, pid, before_date)
        recent = aggregate_recent_profile(recent_rows, book.scale)
        position = summarize_positions(positions_by_player.get(pid, {}))

        general = book.players.get(pid)
        general_dims = (
            book.scale.dimensions(general.p90, general.retention_rate)
            if general is not None
            else {dim: np.nan for dim in DIMENSIONS}
        )

        primary_role = position["primary_role"] or (general.role if general else None)
        physical_ref = PHYSICAL_REFERENCE_BY_ROLE.get(primary_role, {})

        row = {
            **player,
            **position,
            **recent,
            "general_minutes": general.minutes if general else 0.0,
            "general_role": general.role if general else None,
            **{f"general_{dim}_z": general_dims[dim] for dim in DIMENSIONS},
            "physical_reference_role": primary_role if physical_ref else None,
            "physical_reference_source": PHYSICAL_REFERENCE_SOURCE if physical_ref else None,
            **{f"position_ref_{key}": value for key, value in physical_ref.items()},
        }
        out_rows.append(csv_safe_profile_row(row))

    output = pd.DataFrame(out_rows)
    return merge_player_attributes(output, attributes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match-id", default=DEFAULT_MATCH_ID)
    parser.add_argument("--before-date", default=DEFAULT_DATE)
    parser.add_argument("--buckets", type=Path, default=Path("data/player_buckets.csv"))
    parser.add_argument("--cache", type=Path, default=Path("data/raw/recent_profiles"))
    parser.add_argument(
        "--attributes",
        type=Path,
        default=Path("data/player_attributes.csv"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/liverpool_arsenal_recent5_profiles.csv"),
    )
    args = parser.parse_args()

    buckets = pd.read_csv(
        args.buckets,
        dtype={"match_id": str, "player_id": str, "team_id": str},
    )
    target_lineup = fetch_json(
        f"{OPEN_DATA}/lineups/{args.match_id}.json",
        args.cache / "lineups" / f"{args.match_id}.json",
    )
    squad = target_squad(target_lineup)
    target_ids = set(squad["player_id"])

    dates = pd.to_datetime(buckets["match_date"])
    relevant_match_ids = (
        buckets[
            buckets["player_id"].astype(str).isin(target_ids)
            & (dates < pd.Timestamp(args.before_date))
            & (buckets["minutes"] > 0)
        ]["match_id"]
        .astype(str)
        .unique()
    )
    historical_lineups = [
        fetch_json(
            f"{OPEN_DATA}/lineups/{match_id}.json",
            args.cache / "lineups" / f"{match_id}.json",
        )
        for match_id in relevant_match_ids
    ]

    if args.attributes.exists():
        attributes = pd.read_csv(args.attributes, dtype={"player_id": str})
    else:
        attributes = attributes_template(squad)
        args.attributes.parent.mkdir(parents=True, exist_ok=True)
        attributes.to_csv(args.attributes, index=False)
        print(f"Created empty enrichment template: {args.attributes}")

    profiles = build_demo_profiles(
        buckets=buckets,
        target_lineup=target_lineup,
        historical_lineups=historical_lineups,
        before_date=args.before_date,
        attributes=attributes,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    profiles.to_csv(args.out, index=False)

    columns = [
        "name",
        "team_name",
        "primary_position",
        "secondary_positions",
        "recent_appearances",
        "recent_minutes",
        "recent_threat_percentile",
        "recent_creation_percentile",
        "recent_progression_percentile",
        "recent_retention_percentile",
        "recent_defense_percentile",
        "recent_reliability_mean",
    ]
    print(f"{len(profiles)} players -> {args.out}")
    print(profiles[columns].to_string(index=False))


if __name__ == "__main__":
    main()
