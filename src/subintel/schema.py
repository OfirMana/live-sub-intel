"""Shared data contract (v0). Every module and the synthetic stream use these types.

Coordinates follow StatsBomb: a 120 x 80 pitch in yards, and every event is
expressed from the acting team's perspective, attacking toward x = 120.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0
BOX_X = 102.0
BOX_Y_MIN = 18.0
BOX_Y_MAX = 62.0
GOAL = (120.0, 40.0)


def in_box(x: float | None, y: float | None) -> bool:
    return x is not None and y is not None and x >= BOX_X and BOX_Y_MIN <= y <= BOX_Y_MAX


class EventType(StrEnum):
    PASS = "pass"
    CARRY = "carry"
    DRIBBLE = "dribble"
    SHOT = "shot"
    PRESSURE = "pressure"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    RECOVERY = "recovery"
    BLOCK = "block"
    CLEARANCE = "clearance"
    MISCONTROL = "miscontrol"
    DISPOSSESSED = "dispossessed"
    CARD = "card"
    SUBSTITUTION = "substitution"
    OWN_GOAL = "own_goal"  # team_id = the team credited with the goal
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"
    AERIAL = "aerial"


class Event(BaseModel):
    """One on-ball or defensive action. Fields after `under_pressure` are type-specific."""

    event_id: str
    match_id: str
    period: int
    minute: int  # match clock as broadcast: the second half starts at 45
    second: int
    team_id: str
    player_id: str | None = None
    type: EventType
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    success: bool | None = None
    possession_id: int | None = None
    under_pressure: bool = False
    aerial_contest: bool = False
    aerial_won: bool | None = None
    cross: bool = False
    transition: bool = False  # explicit provider/scenario label, never inferred from coordinates
    # pass
    recipient_id: str | None = None
    set_piece: bool = False
    # shot
    xg: float | None = None
    penalty: bool = False
    on_target: bool | None = None
    goal: bool = False
    key_pass_id: str | None = None  # event_id of the pass that created this shot
    # card
    card: Literal["yellow", "second_yellow", "red"] | None = None
    # substitution: player_id leaves, replacement_id enters
    replacement_id: str | None = None

    @property
    def clock(self) -> float:
        return self.minute * 60.0 + self.second


class Role(StrEnum):
    GK = "GK"
    CB = "CB"
    FB = "FB"
    CM = "CM"
    AM_W = "AM_W"
    ST = "ST"


class Player(BaseModel):
    player_id: str
    name: str
    team_id: str
    role: Role | None  # None for an unused substitute: take the role from their profile
    shirt: int | None = None


Dimension = Literal["threat", "creation", "progression", "retention", "defense"]


class GameState(BaseModel):
    minute: int
    goal_diff: int  # from the analysed team's point of view
    red_card_diff: int = 0  # our red cards minus theirs
    subs_left: int


class TeamNeeds(BaseModel):
    """0..1 per dimension. 0.5 = performing as usual and the score does not change its importance."""

    team_id: str
    needs: dict[Dimension, float]
    deficit_z: dict[Dimension, float]  # how far below the team's own norm (positive = below)
    importance: dict[Dimension, float]  # game-state weight, 1.0 = neutral


class SubOption(BaseModel):
    out_player_id: str
    out_name: str
    in_player_id: str
    in_name: str
    score: float  # need-weighted improvement, in z units
    expected_benefit: float  # score scaled by the share of the match still to play
    delta_pct: dict[Dimension, float]  # percentile-point change per dimension, for display
    strength: Literal["high", "medium", "low"]  # evidence strength, not a probability
    reasons: list[str]  # machine-generated facts the LLM may cite


class Recommendation(BaseModel):
    """What the engine hands to the LLM/UI. The LLM explains it; it never changes it."""

    match_id: str
    team_id: str
    state: GameState
    needs: TeamNeeds
    recommend: bool
    options: list[SubOption]  # ranked, best first; shown even when recommend is False


class LineupSlot(BaseModel):
    player_id: str
    role: Role | None
    on_from_clock: float | None  # None = did not play
    off_at_clock: float | None = None  # None = played to the final whistle
