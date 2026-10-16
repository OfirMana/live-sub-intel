import json
from pathlib import Path


DATA = Path(__file__).resolve().parents[1] / "demo_data" / "liverpool_arsenal_demo_profiles.json"


def _players():
    return json.loads(DATA.read_text(encoding="utf-8"))["players"]


def _by_name():
    return {p["name"]: p for p in _players()}


def test_demo_has_only_target_squads_and_36_players():
    players = _players()
    assert len(players) == 36
    assert {p["team"] for p in players} == {"Liverpool", "Arsenal"}
    assert sum(p["team"] == "Liverpool" for p in players) == 18
    assert sum(p["team"] == "Arsenal" for p in players) == 18


def test_all_ratings_are_bounded_and_recent_window_is_five_matches():
    for player in _players():
        assert len(player["recent"]["team_match_window"]) == 5
        for block in ("general",):
            for value in player[block]["ratings"].values():
                assert 0 <= value <= 100
        for value in player["recent"]["ratings"].values():
            assert 0 <= value <= 100
        for dim, value in player["recent"]["ratings"].items():
            assert abs(value - player["general"]["ratings"][dim]) <= 6


def test_fifa_sanity_anchors_prevent_position_percentile_artifacts():
    p = _by_name()
    assert p["Per Mertesacker"]["general"]["ratings"]["defense"] >= 80
    assert p["Laurent Koscielny"]["general"]["ratings"]["defense"] >= 80
    assert p["Mamadou Sakho"]["general"]["ratings"]["defense"] >= 80
    assert p["Mesut Özil"]["general"]["ratings"]["creation"] >= 85
    assert p["Olivier Giroud"]["general"]["ratings"]["threat"] >= 80


def test_position_sanity_comes_from_verified_fifa_roles():
    p = _by_name()
    assert p["Kolo Touré"]["primary_role"] == "CB"
    assert p["Kieran Gibbs"]["primary_role"] == "FB"
    assert p["Danny Ward"]["primary_role"] == "GK"


def test_physical_tracking_is_explicitly_synthetic_and_speed_is_plausible():
    p = _by_name()
    for player in p.values():
        assert player["physical"]["tracking"]["source"].startswith("SYNTHETIC_")
    assert p["Theo Walcott"]["physical"]["tracking"]["estimated_max_speed_kmh"] > 34
    assert p["Per Mertesacker"]["physical"]["tracking"]["estimated_max_speed_kmh"] < 30
