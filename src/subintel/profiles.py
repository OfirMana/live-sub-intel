"""Pre-match player profiles and team baselines, built from data/player_buckets.csv.

Rates are absolute per-90 values on one league-wide scale (a striker and a
centre-back are compared in the same units). Low-minute players are shrunk
toward the average *fringe* player of their role (under 900 minutes), not the
average regular: in 2015/16 fringe attackers created ~45% less xA per 90 than
regulars, so "unknown" must not mean "average starter". Prior strengths were
measured from the same season (see docs/CONTRACT.md, "Reliability").
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import DIMENSIONS, VOLUME_COMPONENTS

# Prior strength in full matches: how much evidence a player needs before their own
# rate counts as much as their role average. Rounded medians of the 2015/16 estimates.
PRIOR_90S = {
    "npxg": 10.0,
    "box_presence": 4.0,
    "xa": 8.0,
    "box_passes": 5.0,
    "prog_passes": 2.5,
    "prog_carries": 2.0,
    "pressures": 3.0,
    "def_actions": 5.0,
}
PRIOR_BALL_ACTIONS = 100.0  # same idea for the retention rate, counted in ball actions
REFERENCE_MINUTES = 900.0  # players defining the league scale; below this a player is "fringe"


@dataclass
class PlayerProfile:
    player_id: str
    name: str
    team_id: str
    role: str
    minutes: float
    p90: dict[str, float]  # shrunk per-90 rate per volume component
    retention_rate: float
    reliability: dict[str, float]  # n / (n + k) per component, 0..1


@dataclass
class Scale:
    """League reference used to turn component rates into z-scores and dimension percentiles."""

    mean: dict[str, float]
    std: dict[str, float]
    dimension_values: dict[str, list[float]]  # sorted reference values per dimension

    def z(self, component: str, value: float) -> float:
        return (value - self.mean[component]) / self.std[component]

    def dimensions(self, p90: dict[str, float], retention_rate: float) -> dict[str, float]:
        zs = {c: self.z(c, v) for c, v in p90.items()}
        zs["retention_rate"] = self.z("retention_rate", retention_rate)
        return {dim: float(np.mean([zs[c] for c in comps])) for dim, comps in DIMENSIONS.items()}

    def percentile(self, dim: str, value: float) -> float:
        ref = self.dimension_values[dim]
        return 100.0 * np.searchsorted(ref, value) / len(ref)


@dataclass
class TeamBaseline:
    team_id: str
    p90: dict[str, float]  # team total per 90 for attacking volume components
    conceded_p90: dict[str, float]  # what opponents usually produce against this team
    loss_rate: float  # ball_losses / ball_actions


@dataclass
class ProfileBook:
    players: dict[str, PlayerProfile]
    teams: dict[str, TeamBaseline]
    scale: Scale
    role_priors: dict[str, dict[str, float]] = field(default_factory=dict)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self)))

    @classmethod
    def load(cls, path: Path) -> "ProfileBook":
        raw = json.loads(path.read_text())
        return cls(
            players={k: PlayerProfile(**v) for k, v in raw["players"].items()},
            teams={k: TeamBaseline(**v) for k, v in raw["teams"].items()},
            scale=Scale(**raw["scale"]),
            role_priors=raw["role_priors"],
        )


def build(buckets: pd.DataFrame, before_date: str | None = None) -> ProfileBook:
    """Profiles from every match strictly before `before_date` (ISO date), or the whole table."""
    if before_date:
        buckets = buckets[buckets.match_date < before_date]
    sums = ["minutes", *VOLUME_COMPONENTS, "ball_actions", "ball_losses"]
    per_player = buckets.groupby(["player_id", "name", "role", "team_id"], as_index=False)[sums].sum()
    # A player who moved club or role keeps the team/role where they played most.
    per_player = per_player.sort_values("minutes").groupby("player_id").tail(1)
    totals = buckets.groupby(["player_id"])[sums].sum()
    per_player = per_player[["player_id", "name", "role", "team_id"]].join(totals, on="player_id")
    outfield = per_player[per_player.role != "GK"]

    role_priors: dict[str, dict[str, float]] = {}
    for role, g in outfield[outfield.minutes < REFERENCE_MINUTES].groupby("role"):
        n90 = g.minutes.sum() / 90
        role_priors[role] = {c: g[c].sum() / n90 for c in VOLUME_COMPONENTS}
        role_priors[role]["retention_rate"] = 1 - g.ball_losses.sum() / g.ball_actions.sum()

    players: dict[str, PlayerProfile] = {}
    for r in outfield.itertuples(index=False):
        n90 = r.minutes / 90
        prior = role_priors[r.role]
        p90 = {c: (getattr(r, c) + PRIOR_90S[c] * prior[c]) / (n90 + PRIOR_90S[c]) for c in VOLUME_COMPONENTS}
        retained = r.ball_actions - r.ball_losses
        retention = (retained + PRIOR_BALL_ACTIONS * prior["retention_rate"]) / (r.ball_actions + PRIOR_BALL_ACTIONS)
        reliability = {c: n90 / (n90 + PRIOR_90S[c]) for c in VOLUME_COMPONENTS}
        reliability["retention_rate"] = r.ball_actions / (r.ball_actions + PRIOR_BALL_ACTIONS)
        players[str(r.player_id)] = PlayerProfile(
            player_id=str(r.player_id), name=r.name, team_id=str(r.team_id), role=r.role,
            minutes=float(r.minutes), p90=p90, retention_rate=float(retention), reliability=reliability,
        )

    ref = [p for p in players.values() if p.minutes >= REFERENCE_MINUTES]
    comp_values = {c: np.array([p.p90[c] for p in ref]) for c in VOLUME_COMPONENTS}
    comp_values["retention_rate"] = np.array([p.retention_rate for p in ref])
    scale = Scale(
        mean={c: float(v.mean()) for c, v in comp_values.items()},
        std={c: float(v.std()) for c, v in comp_values.items()},
        dimension_values={},
    )
    ref_dims = [scale.dimensions(p.p90, p.retention_rate) for p in ref]
    scale.dimension_values = {d: sorted(x[d] for x in ref_dims) for d in DIMENSIONS}

    return ProfileBook(players=players, teams=_team_baselines(buckets), scale=scale, role_priors=role_priors)


def _team_baselines(buckets: pd.DataFrame) -> dict[str, TeamBaseline]:
    cols = [*VOLUME_COMPONENTS, "ball_actions", "ball_losses"]
    per_match = buckets.groupby(["match_id", "team_id"], as_index=False)[cols].sum()
    opp = per_match[["match_id", "team_id", *VOLUME_COMPONENTS]].rename(
        columns={"team_id": "opp_id", **{c: f"opp_{c}" for c in VOLUME_COMPONENTS}}
    )
    per_match = per_match.merge(opp, on="match_id")
    per_match = per_match[per_match.team_id != per_match.opp_id]
    teams = {}
    for team_id, g in per_match.groupby("team_id"):
        n = len(g)  # matches, i.e. 90s at team level
        teams[str(team_id)] = TeamBaseline(
            team_id=str(team_id),
            p90={c: float(g[c].sum() / n) for c in VOLUME_COMPONENTS},
            conceded_p90={c: float(g[f"opp_{c}"].sum() / n) for c in VOLUME_COMPONENTS},
            loss_rate=float(g.ball_losses.sum() / g.ball_actions.sum()),
        )
    return teams
