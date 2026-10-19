"""Recent-form and playable-position profiles.

This module intentionally keeps three concepts separate:

* General profile: long-term pre-match ability from :mod:`subintel.profiles`.
* Recent profile: the player's last N actual appearances before a cutoff date.
* Live profile: current-match evidence, handled by the live engine.

Recent values are descriptive evidence, not a replacement for the long-term
profile. Physical player attributes are also kept separate from positional
physical reference values.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from .metrics import DIMENSIONS, VOLUME_COMPONENTS
from .physical import PLAYER_ATTRIBUTE_COLUMNS
from .profiles import PRIOR_90S, PRIOR_BALL_ACTIONS, Scale
from .statsbomb import ROLE_BY_POSITION

RECENT_APPEARANCES = 5
SECONDARY_POSITION_MINUTES = 90.0
SECONDARY_POSITION_SHARE = 0.15
FALLBACK_MATCH_END_SECONDS = 95 * 60.0


def select_recent_appearances(
    buckets: pd.DataFrame,
    player_id: str,
    before_date: str,
    limit: int = RECENT_APPEARANCES,
) -> pd.DataFrame:
    """Return bucket rows from the player's last ``limit`` actual appearances.

    Matches on or after ``before_date`` are excluded. An appearance is a match
    in which the player has at least one positive-minute bucket.
    """
    if buckets.empty:
        return buckets.copy()

    work = buckets.copy()
    work["_date"] = pd.to_datetime(work["match_date"])
    cutoff = pd.Timestamp(before_date)
    pid_mask = work["player_id"].astype(str) == str(player_id)
    work = work[pid_mask & (work["_date"] < cutoff) & (work["minutes"] > 0)].copy()
    if work.empty:
        return work.drop(columns=["_date"], errors="ignore")

    appearances = (
        work.groupby("match_id", as_index=False)["_date"]
        .max()
        .sort_values(["_date", "match_id"], ascending=[False, False])
        .head(limit)
    )
    selected = set(appearances["match_id"])
    work = work[work["match_id"].isin(selected)].copy()
    return work.sort_values(["_date", "match_id", "bucket"]).drop(columns=["_date"])


def aggregate_recent_profile(rows: pd.DataFrame, scale: Scale) -> dict[str, Any]:
    """Aggregate recent bucket rows into components, dimensions and reliability."""
    result: dict[str, Any] = {
        "recent_appearances": 0,
        "recent_starts": 0,
        "recent_minutes": 0.0,
        "first_recent_match_date": None,
        "last_recent_match_date": None,
        "recent_reliability_by_component": {},
        "recent_reliability_mean": 0.0,
    }
    for component in VOLUME_COMPONENTS:
        result[f"recent_{component}_p90"] = np.nan
    result["recent_retention_rate"] = np.nan
    for dim in DIMENSIONS:
        result[f"recent_{dim}_z"] = np.nan
        result[f"recent_{dim}_percentile"] = np.nan

    if rows.empty:
        return result

    minutes = float(rows["minutes"].sum())
    appearances = int(rows["match_id"].nunique())
    if "started" in rows:
        starts = int(rows.groupby("match_id")["started"].max().astype(bool).sum())
    else:
        starts = 0

    dates = pd.to_datetime(rows["match_date"])
    result.update(
        recent_appearances=appearances,
        recent_starts=starts,
        recent_minutes=minutes,
        first_recent_match_date=dates.min().date().isoformat(),
        last_recent_match_date=dates.max().date().isoformat(),
    )
    if minutes <= 0:
        return result

    p90: dict[str, float] = {}
    for component in VOLUME_COMPONENTS:
        total = float(rows[component].sum())
        p90[component] = total / minutes * 90.0
        result[f"recent_{component}_p90"] = p90[component]

    ball_actions = float(rows["ball_actions"].sum())
    ball_losses = float(rows["ball_losses"].sum())
    retention = 1.0 - ball_losses / ball_actions if ball_actions > 0 else np.nan
    result["recent_retention_rate"] = retention

    roles = set(rows["role"].dropna().astype(str)) if "role" in rows else set()
    is_goalkeeper_only = roles == {"GK"}
    if not is_goalkeeper_only and not np.isnan(retention):
        dims = scale.dimensions(p90, retention)
        for dim, value in dims.items():
            result[f"recent_{dim}_z"] = value
            result[f"recent_{dim}_percentile"] = scale.percentile(dim, value)

    n90 = minutes / 90.0
    reliability = {c: n90 / (n90 + PRIOR_90S[c]) for c in VOLUME_COMPONENTS}
    reliability["retention_rate"] = (
        ball_actions / (ball_actions + PRIOR_BALL_ACTIONS) if ball_actions > 0 else 0.0
    )
    result["recent_reliability_by_component"] = reliability
    result["recent_reliability_mean"] = float(np.mean(list(reliability.values())))
    return result


def _clock(value: str | None) -> float | None:
    if value is None:
        return None
    minute, second = value.split(":")
    return int(minute) * 60.0 + int(second)


def position_minutes_from_lineup(
    lineup: list[dict],
    target_player_ids: set[str] | None = None,
    fallback_end_seconds: float = FALLBACK_MATCH_END_SECONDS,
) -> dict[str, dict[str, float]]:
    """Return exact-position minutes for players in one StatsBomb lineup document."""
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    wanted = {str(x) for x in target_player_ids} if target_player_ids else None

    for team in lineup:
        for player in team.get("lineup", []):
            pid = str(player["player_id"])
            if wanted is not None and pid not in wanted:
                continue
            for spell in player.get("positions", []):
                start = _clock(spell.get("from")) or 0.0
                end = _clock(spell.get("to"))
                if end is None:
                    end = fallback_end_seconds
                minutes = max(0.0, end - start) / 60.0
                if minutes:
                    out[pid][spell["position"]] += minutes

    return {pid: dict(values) for pid, values in out.items()}


def merge_position_minutes(
    histories: Iterable[Mapping[str, Mapping[str, float]]],
) -> dict[str, dict[str, float]]:
    """Sum exact-position minutes across multiple matches."""
    total: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for history in histories:
        for pid, positions in history.items():
            for position, minutes in positions.items():
                total[str(pid)][position] += float(minutes)
    return {pid: dict(values) for pid, values in total.items()}


def summarize_positions(position_minutes: Mapping[str, float]) -> dict[str, Any]:
    """Create FIFA-like primary/secondary position metadata from historical minutes."""
    clean = {p: float(m) for p, m in position_minutes.items() if float(m) > 0}
    if not clean:
        return {
            "primary_position": None,
            "secondary_positions": [],
            "all_positions_played": [],
            "minutes_by_position": {},
            "primary_role": None,
            "roles_played": [],
            "minutes_by_role": {},
        }

    ordered = sorted(clean.items(), key=lambda item: (-item[1], item[0]))
    primary_position = ordered[0][0]
    total_minutes = sum(clean.values())
    secondary_positions = [
        position
        for position, minutes in ordered[1:]
        if minutes >= SECONDARY_POSITION_MINUTES
        or minutes / total_minutes >= SECONDARY_POSITION_SHARE
    ]

    role_minutes: dict[str, float] = defaultdict(float)
    for position, minutes in clean.items():
        role = ROLE_BY_POSITION.get(position)
        if role is not None:
            role_minutes[role.value] += minutes
    ordered_roles = sorted(role_minutes.items(), key=lambda item: (-item[1], item[0]))
    primary_role = ordered_roles[0][0] if ordered_roles else None

    return {
        "primary_position": primary_position,
        "secondary_positions": secondary_positions,
        "all_positions_played": [position for position, _ in ordered],
        "minutes_by_position": dict(ordered),
        "primary_role": primary_role,
        "roles_played": [role for role, _ in ordered_roles],
        "minutes_by_role": dict(ordered_roles),
    }


def attributes_template(players: pd.DataFrame) -> pd.DataFrame:
    """Return one empty player-specific physical/biographical row per player."""
    identity = players[["player_id", "name"]].drop_duplicates("player_id").copy()
    for column in PLAYER_ATTRIBUTE_COLUMNS:
        if column == "physical_is_observed":
            identity[column] = pd.Series([pd.NA] * len(identity), dtype="boolean")
        else:
            identity[column] = pd.NA
    return identity


def merge_player_attributes(profiles: pd.DataFrame, attributes: pd.DataFrame | None) -> pd.DataFrame:
    """Merge observed/enriched attributes without inventing positional defaults."""
    result = profiles.copy()
    if attributes is None:
        attributes = pd.DataFrame(columns=["player_id", *PLAYER_ATTRIBUTE_COLUMNS])
    attrs = attributes.copy()
    if "player_id" not in attrs:
        attrs["player_id"] = pd.Series(dtype=str)
    attrs["player_id"] = attrs["player_id"].astype(str)

    for column in PLAYER_ATTRIBUTE_COLUMNS:
        if column not in attrs:
            attrs[column] = pd.NA

    keep = ["player_id", *PLAYER_ATTRIBUTE_COLUMNS]
    result["player_id"] = result["player_id"].astype(str)
    return result.merge(attrs[keep].drop_duplicates("player_id"), on="player_id", how="left")


def csv_safe_profile_row(row: dict[str, Any]) -> dict[str, Any]:
    """JSON-encode structured fields before writing a flat CSV."""
    structured = {
        "secondary_positions",
        "all_positions_played",
        "minutes_by_position",
        "roles_played",
        "minutes_by_role",
        "recent_reliability_by_component",
    }
    return {
        key: json.dumps(value, sort_keys=True) if key in structured and value is not None else value
        for key, value in row.items()
    }
