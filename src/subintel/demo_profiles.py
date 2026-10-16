"""Loader for the complete Liverpool-Arsenal hackathon demo profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_DEMO_PROFILES = Path("demo_data/demo_player_profiles.json")


def load_demo_profiles(path: Path = DEFAULT_DEMO_PROFILES) -> dict[str, Any]:
    """Load the complete demo dataset and index players by string player_id."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["players_by_id"] = {str(p["player_id"]): p for p in raw["players"]}
    return raw


def player_profile(player_id: str, path: Path = DEFAULT_DEMO_PROFILES) -> dict[str, Any]:
    """Return one demo profile or raise KeyError for a player outside the demo squads."""
    return load_demo_profiles(path)["players_by_id"][str(player_id)]
