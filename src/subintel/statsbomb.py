"""Converts StatsBomb open-data JSON into the shared contract (schema.py).

Everything downstream reads only `Event`, so historical data and the synthetic
stream go through exactly the same metric code.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import Event, EventType, LineupSlot, Player, Role

OPEN_DATA = "https://raw.githubusercontent.com/hudl/open-data/master/data"
PREMIER_LEAGUE = 2
SEASON_2015_16 = 27

ROLE_BY_POSITION = {
    "Goalkeeper": Role.GK,
    "Center Back": Role.CB,
    "Left Center Back": Role.CB,
    "Right Center Back": Role.CB,
    "Left Back": Role.FB,
    "Right Back": Role.FB,
    "Left Wing Back": Role.FB,
    "Right Wing Back": Role.FB,
    "Center Defensive Midfield": Role.CM,
    "Left Defensive Midfield": Role.CM,
    "Right Defensive Midfield": Role.CM,
    "Center Midfield": Role.CM,
    "Left Center Midfield": Role.CM,
    "Right Center Midfield": Role.CM,
    "Center Attacking Midfield": Role.AM_W,
    "Left Attacking Midfield": Role.AM_W,
    "Right Attacking Midfield": Role.AM_W,
    "Left Midfield": Role.AM_W,
    "Right Midfield": Role.AM_W,
    "Left Wing": Role.AM_W,
    "Right Wing": Role.AM_W,
    "Center Forward": Role.ST,
    "Left Center Forward": Role.ST,
    "Right Center Forward": Role.ST,
    "Secondary Striker": Role.ST,
}

SET_PIECE_PASSES = {"Corner", "Free Kick", "Goal Kick", "Kick Off", "Throw-in"}
TACKLE_WON = {"Won", "Success In Play", "Success Out"}
INTERCEPTION_WON = {"Won", "Success In Play", "Success Out"}
ON_TARGET = {"Goal", "Saved", "Saved to Post"}
CARDS = {"Yellow Card": "yellow", "Second Yellow": "second_yellow", "Red Card": "red"}


def _id(obj: dict | None) -> str | None:
    return None if obj is None else str(obj["id"])


def _xy(loc: list | None) -> tuple[float | None, float | None]:
    return (loc[0], loc[1]) if loc else (None, None)


def convert_event(e: dict, match_id: str) -> Event | None:
    """Returns None for StatsBomb events the contract does not need (receipts, aerials, ...)."""
    kind = e["type"]["name"]
    x, y = _xy(e.get("location"))
    base = dict(
        event_id=e["id"],
        match_id=match_id,
        period=e["period"],
        minute=e["minute"],
        second=e["second"],
        team_id=_id(e["team"]),
        player_id=_id(e.get("player")),
        x=x,
        y=y,
        possession_id=e.get("possession"),
        under_pressure=bool(e.get("under_pressure")),
    )
    if kind == "Pass":
        p = e["pass"]
        outcome = p.get("outcome", {}).get("name")
        if outcome == "Injury Clearance":
            return None
        ex, ey = _xy(p.get("end_location"))
        return Event(
            **base, type=EventType.PASS, end_x=ex, end_y=ey, success=outcome is None,
            recipient_id=_id(p.get("recipient")),
            set_piece=p.get("type", {}).get("name") in SET_PIECE_PASSES,
        )
    if kind == "Carry":
        ex, ey = _xy(e["carry"].get("end_location"))
        return Event(**base, type=EventType.CARRY, end_x=ex, end_y=ey, success=True)
    if kind == "Dribble":
        return Event(**base, type=EventType.DRIBBLE, success=e["dribble"]["outcome"]["name"] == "Complete")
    if kind == "Shot":
        s = e["shot"]
        ex, ey = _xy((s.get("end_location") or [None, None])[:2])
        outcome = s["outcome"]["name"]
        return Event(
            **base, type=EventType.SHOT, end_x=ex, end_y=ey, success=outcome == "Goal",
            xg=s.get("statsbomb_xg", 0.0), penalty=s["type"]["name"] == "Penalty",
            on_target=outcome in ON_TARGET, goal=outcome == "Goal", key_pass_id=s.get("key_pass_id"),
        )
    if kind == "Pressure":
        return Event(**base, type=EventType.PRESSURE)
    if kind == "Duel" and e["duel"]["type"]["name"] == "Tackle":
        return Event(**base, type=EventType.TACKLE, success=e["duel"].get("outcome", {}).get("name") in TACKLE_WON)
    if kind == "Interception":
        return Event(**base, type=EventType.INTERCEPTION, success=e["interception"]["outcome"]["name"] in INTERCEPTION_WON)
    if kind == "Ball Recovery":
        return Event(**base, type=EventType.RECOVERY, success=not e.get("ball_recovery", {}).get("recovery_failure", False))
    if kind == "Block":
        return Event(**base, type=EventType.BLOCK, success=True)
    if kind == "Clearance":
        return Event(**base, type=EventType.CLEARANCE, success=True)
    if kind == "Miscontrol":
        return Event(**base, type=EventType.MISCONTROL, success=False)
    if kind == "Dispossessed":
        return Event(**base, type=EventType.DISPOSSESSED, success=False)
    if kind in ("Foul Committed", "Bad Behaviour"):
        card = e.get("foul_committed", e.get("bad_behaviour", {})).get("card", {}).get("name")
        return Event(**base, type=EventType.CARD, card=CARDS[card]) if card in CARDS else None
    if kind == "Substitution":
        return Event(**base, type=EventType.SUBSTITUTION, replacement_id=_id(e["substitution"]["replacement"]))
    if kind == "Own Goal For":
        return Event(**{**base, "player_id": None}, type=EventType.OWN_GOAL)
    if kind == "Half Start":
        return Event(**base, type=EventType.PERIOD_START)
    if kind == "Half End":
        return Event(**base, type=EventType.PERIOD_END)
    return None


def load_events(path: Path, match_id: str) -> list[Event]:
    raw = json.loads(path.read_text())
    return [ev for e in raw if (ev := convert_event(e, match_id)) is not None]


def _clock(mmss: str | None) -> float | None:
    if mmss is None:
        return None
    m, s = mmss.split(":")
    return int(m) * 60.0 + int(s)


def load_lineups(path: Path) -> tuple[list[Player], list[LineupSlot]]:
    """Players of both teams, plus one slot per player with when they were on the pitch.

    A player's role is the position where they spent the most time in this match.
    """
    players, slots = [], []
    for team in json.loads(path.read_text()):
        for p in team["lineup"]:
            spells = p["positions"]
            if spells:
                role = max(
                    ((ROLE_BY_POSITION[s["position"]], (_clock(s["to"]) or 95 * 60) - _clock(s["from"])) for s in spells),
                    key=lambda r: r[1],
                )[0]
            else:
                role = None
            pid = str(p["player_id"])
            name = p.get("player_nickname") or p["player_name"]
            players.append(Player(player_id=pid, name=name, team_id=str(team["team_id"]), role=role, shirt=p.get("jersey_number")))
            ends = [s["end_reason"] for s in spells]
            slots.append(
                LineupSlot(
                    player_id=pid,
                    role=role,
                    on_from_clock=_clock(spells[0]["from"]) if spells else None,
                    off_at_clock=None if not spells or ends[-1] == "Final Whistle" else _clock(spells[-1]["to"]),
                )
            )
    return players, slots
