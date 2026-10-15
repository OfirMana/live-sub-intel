"""Event -> metric components. The single source of truth for what each dimension means.

Used both offline (season profiles) and live (team needs), so a player's profile
and the team's needs are always measured in the same units.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .schema import Event, EventType, in_box

# Components counted per 90 minutes.
VOLUME_COMPONENTS = (
    "npxg",
    "box_presence",
    "xa",
    "box_passes",
    "prog_passes",
    "prog_carries",
    "pressures",
    "def_actions",
)
# Retention is a rate: 1 - ball_losses / ball_actions.
RATE_COMPONENTS = ("ball_actions", "ball_losses")
COMPONENTS = VOLUME_COMPONENTS + RATE_COMPONENTS

# Each MVP dimension is the mean of its standardized components.
DIMENSIONS: dict[str, tuple[str, ...]] = {
    "threat": ("npxg", "box_presence"),
    "creation": ("xa", "box_passes"),
    "progression": ("prog_passes", "prog_carries"),
    "retention": ("retention_rate",),
    "defense": ("pressures", "def_actions"),
}

PROGRESSIVE_YARDS = 10.0
DEFENDING_40_PCT_X = 48.0  # passes starting here or deeper are not counted as progressive
CARRY_END_MIN_X = 60.0  # carries ending in the own half are not counted as progressive


@dataclass(frozen=True)
class Contribution:
    player_id: str
    team_id: str
    component: str
    value: float
    minute: int


def _enters_box(ev: Event) -> bool:
    return in_box(ev.end_x, ev.end_y) and not in_box(ev.x, ev.y)


def _is_progressive_pass(ev: Event) -> bool:
    if ev.end_x is None or ev.x is None:
        return False
    return _enters_box(ev) or (ev.end_x - ev.x >= PROGRESSIVE_YARDS and ev.x >= DEFENDING_40_PCT_X)


def _is_progressive_carry(ev: Event) -> bool:
    if ev.end_x is None or ev.x is None:
        return False
    return _enters_box(ev) or (ev.end_x - ev.x >= PROGRESSIVE_YARDS and ev.end_x >= CARRY_END_MIN_X)


class ComponentTracker:
    """Feed events in match order; yields the metric contributions each event causes.

    Stateful only because expected assists are credited to the passer when the shot arrives.
    """

    def __init__(self) -> None:
        self._passer_by_event: dict[str, tuple[str, str]] = {}

    def feed(self, ev: Event) -> Iterator[Contribution]:
        pid, team = ev.player_id, ev.team_id
        if pid is None:
            return

        def c(component: str, value: float = 1.0, player: str = pid) -> Contribution:
            return Contribution(player, team, component, value, ev.minute)

        t = ev.type
        if t is EventType.PASS:
            self._passer_by_event[ev.event_id] = (pid, team)
            if ev.set_piece:
                return
            yield c("ball_actions")
            if not ev.success:
                yield c("ball_losses")
                return
            if _enters_box(ev):
                yield c("box_passes")
            if _is_progressive_pass(ev):
                yield c("prog_passes")
            if ev.recipient_id and in_box(ev.end_x, ev.end_y):
                yield c("box_presence", player=ev.recipient_id)
        elif t is EventType.CARRY:
            if _is_progressive_carry(ev):
                yield c("prog_carries")
            if _enters_box(ev):
                yield c("box_presence")
        elif t is EventType.DRIBBLE:
            yield c("ball_actions")
            if not ev.success:
                yield c("ball_losses")
        elif t in (EventType.MISCONTROL, EventType.DISPOSSESSED):
            yield c("ball_actions")
            yield c("ball_losses")
        elif t is EventType.SHOT:
            if ev.penalty:
                return
            yield c("npxg", ev.xg or 0.0)
            passer = self._passer_by_event.get(ev.key_pass_id or "")
            if passer:
                yield Contribution(passer[0], passer[1], "xa", ev.xg or 0.0, ev.minute)
        elif t is EventType.PRESSURE:
            yield c("pressures")
        elif t in (EventType.TACKLE, EventType.INTERCEPTION, EventType.RECOVERY, EventType.BLOCK):
            if ev.success:
                yield c("def_actions")
