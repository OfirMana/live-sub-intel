import math

import numpy as np
import pandas as pd

from subintel.metrics import DIMENSIONS, VOLUME_COMPONENTS
from subintel.profiles import Scale
from subintel.recent_profiles import (
    aggregate_recent_profile,
    merge_player_attributes,
    select_recent_appearances,
    summarize_positions,
)


def scale() -> Scale:
    components = {c: 0.0 for c in VOLUME_COMPONENTS}
    components["retention_rate"] = 0.0
    std = {c: 1.0 for c in components}
    return Scale(
        mean=components,
        std=std,
        dimension_values={d: [-2.0, -1.0, 0.0, 1.0, 2.0] for d in DIMENSIONS},
    )


def row(match, date, minutes, npxg=0.0, started=True, role="ST"):
    data = {
        "match_id": str(match),
        "match_date": date,
        "team_id": "A",
        "player_id": "p1",
        "name": "Player",
        "role": role,
        "started": started,
        "bucket": 0,
        "minutes": minutes,
        "ball_actions": 10.0,
        "ball_losses": 2.0,
    }
    data.update({c: 0.0 for c in VOLUME_COMPONENTS})
    data["npxg"] = npxg
    return data


def test_recent_selects_last_five_actual_appearances_not_team_matches():
    df = pd.DataFrame(
        [row(i, f"2016-01-{i:02d}", 60) for i in range(1, 8)]
        + [{**row(99, "2016-01-12", 0), "player_id": "p1"}]
    )
    recent = select_recent_appearances(df, "p1", "2016-01-20")
    assert set(recent.match_id) == {"3", "4", "5", "6", "7"}
    assert recent.match_id.nunique() == 5


def test_recent_p90_is_sum_over_total_minutes_not_equal_match_average():
    df = pd.DataFrame(
        [
            row(1, "2016-01-01", 90, npxg=0.9),
            row(2, "2016-01-02", 10, npxg=0.9),
        ]
    )
    result = aggregate_recent_profile(df, scale())
    assert math.isclose(result["recent_npxg_p90"], 1.62, rel_tol=1e-9)
    assert not math.isclose(result["recent_npxg_p90"], 4.5)


def test_before_date_has_no_target_or_future_match():
    df = pd.DataFrame(
        [
            row(1, "2016-01-10", 90),
            row(2, "2016-01-13", 90),
            row(3, "2016-01-14", 90),
        ]
    )
    recent = select_recent_appearances(df, "p1", "2016-01-13")
    assert set(recent.match_id) == {"1"}


def test_primary_position_is_most_minutes():
    summary = summarize_positions({"Left Wing": 210, "Center Forward": 120, "Right Wing": 20})
    assert summary["primary_position"] == "Left Wing"
    assert summary["primary_role"] == "AM_W"


def test_secondary_position_rule():
    summary = summarize_positions({"Left Wing": 300, "Center Forward": 100, "Right Wing": 30})
    assert "Center Forward" in summary["secondary_positions"]
    assert "Right Wing" not in summary["secondary_positions"]


def test_fewer_than_five_appearances_is_valid():
    df = pd.DataFrame([row(1, "2016-01-01", 45), row(2, "2016-01-02", 30)])
    recent = select_recent_appearances(df, "p1", "2016-01-13")
    result = aggregate_recent_profile(recent, scale())
    assert result["recent_appearances"] == 2
    assert result["recent_minutes"] == 75


def test_reliability_increases_with_minutes():
    short = pd.DataFrame([row(1, "2016-01-01", 30)])
    long = pd.DataFrame([row(1, "2016-01-01", 90), row(2, "2016-01-02", 90)])
    a = aggregate_recent_profile(short, scale())["recent_reliability_mean"]
    b = aggregate_recent_profile(long, scale())["recent_reliability_mean"]
    assert b > a


def test_missing_physical_attributes_stay_missing():
    profiles = pd.DataFrame([{"player_id": "p1", "name": "Player"}])
    attrs = pd.DataFrame([{"player_id": "p1", "height_cm": np.nan}])
    merged = merge_player_attributes(profiles, attrs)
    assert pd.isna(merged.loc[0, "height_cm"])
    assert pd.isna(merged.loc[0, "max_speed_kmh"])
    assert pd.isna(merged.loc[0, "physical_source"])
