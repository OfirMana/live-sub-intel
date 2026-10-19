"""Loader for the frozen four-team hackathon demo profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEMO_PROFILE_PATH = (
    Path(__file__).resolve().parents[2]
    / "demo_data"
    / "demo_player_profiles.json"
)


def load_demo_profiles(path: str | Path = DEMO_PROFILE_PATH) -> dict[str, Any]:
    """Load the canonical demo player dataset."""
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def demo_players(path: str | Path = DEMO_PROFILE_PATH) -> dict[str, dict[str, Any]]:
    """Return demo players keyed by StatsBomb player id as a string."""
    data = load_demo_profiles(path)
    return {str(player["player_id"]): player for player in data["players"]}
