import json
from pathlib import Path

from subintel.demo_profiles import load_demo_profiles

DATA = Path("demo_data/demo_player_profiles.json")


def test_demo_dataset_has_only_target_squads_and_36_players():
    data = load_demo_profiles(DATA)
    assert len(data["players"]) == 36
    assert {p["team"] for p in data["players"]} == {"Liverpool", "Arsenal"}


def test_demo_general_scores_pass_core_sanity_checks():
    data = load_demo_profiles(DATA)
    by_name = {p["name"]: p for p in data["players"]}
    assert by_name["Per Mertesacker"]["general"]["defense"] >= 75
    assert by_name["Laurent Koscielny"]["general"]["defense"] >= 78
    assert by_name["Mesut Özil"]["general"]["creation"] >= 85
    assert by_name["Olivier Giroud"]["general"]["threat"] >= 75


def test_outfield_capabilities_are_bounded():
    data = load_demo_profiles(DATA)
    dims = ("threat", "creation", "progression", "retention", "defense", "aerial")
    for p in data["players"]:
        if p["positions"]["primary_role"] == "GK":
            continue
        for dim in dims:
            assert 0 <= p["general"][dim] <= 95


def test_recent_window_is_five_team_matches():
    data = load_demo_profiles(DATA)
    for p in data["players"]:
        assert len(p["recent_5"]["team_match_ids"]) == 5
        assert 0 <= p["recent_5"]["appearances"] <= 5


def test_synthetic_physical_data_is_never_marked_observed():
    data = load_demo_profiles(DATA)
    for p in data["players"]:
        assert p["physical"]["is_observed"] is False
        assert p["physical"]["source"].startswith("SYNTHETIC:")


def test_position_sanity_examples():
    data = load_demo_profiles(DATA)
    by_name = {p["name"]: p for p in data["players"]}
    assert by_name["Kolo Touré"]["positions"]["eligible_roles"] == ["CB"]
    assert "FB" in by_name["Kieran Gibbs"]["positions"]["eligible_roles"]
    assert "ST" in by_name["Roberto Firmino"]["positions"]["eligible_roles"]
