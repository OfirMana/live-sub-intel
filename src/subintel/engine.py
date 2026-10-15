"""Live engine: events in, team needs and ranked substitutions out. Fully deterministic.

Constants here are first guesses to tune on the demo scenario; the ones marked
"measured" come from the 2015/16 season (docs/CONTRACT.md).
"""

from __future__ import annotations

import math
from collections import defaultdict

from .metrics import DIMENSIONS, VOLUME_COMPONENTS, ComponentTracker
from .profiles import PRIOR_90S, PRIOR_BALL_ACTIONS, ProfileBook
from .schema import Event, EventType, GameState, Player, Recommendation, SubOption, TeamNeeds

HALF_LIFE_MIN = 12.0  # team-need memory: events 12 minutes ago count half
XG_DISPERSION = 0.3  # variance inflation for xG-valued components (E[x^2]/E[x] per shot)
PRESSING_FATIGUE_AT_90 = 0.20  # measured: full-match starters press ~20% less in the last 15'
MAX_SUBS = 3  # 2015/16 rules; the current Premier League allows 5
RECOMMEND_THRESHOLD = 0.15  # minimum expected benefit; tune on the demo scenario
ATTACKING = ("npxg", "box_presence", "xa", "box_passes", "prog_passes", "prog_carries")
# Defensive need is judged by what the opponent achieves against us, not by how many
# defensive actions we make (a team under siege makes lots of them).
CONCEDED = ("npxg", "box_presence", "prog_passes", "prog_carries")

# Game-state importance at full time (blended in as the match goes on).
IMPORTANCE = {
    "chasing": {"threat": 1.5, "creation": 1.3, "progression": 1.2, "retention": 0.8, "defense": 0.8},
    "level": {d: 1.0 for d in DIMENSIONS},
    "protecting": {"threat": 0.7, "creation": 0.8, "progression": 0.8, "retention": 1.3, "defense": 1.4},
}
# Like-for-like, plus the two attacking-midfield neighbours. Our five dimensions do not
# measure what defenders are for (aerials, box defending, positioning), so any swap that
# takes a defender off for a non-defender wins on paper; replaying Tottenham 0-1 Leicester
# recommended Huth -> Inler at 65' until this was restricted. Values are a cost in z units.
ROLE_DISTANCE = {
    frozenset({"CB"}): 0.0, frozenset({"FB"}): 0.0, frozenset({"CM"}): 0.0,
    frozenset({"AM_W"}): 0.0, frozenset({"ST"}): 0.0,
    frozenset({"CM", "AM_W"}): 0.2, frozenset({"AM_W", "ST"}): 0.2,
}
# Chasing late, a defender/midfielder may go off for an attacker (a formation change).
CHASING_SWAP = {("CB", "ST"), ("CB", "AM_W"), ("FB", "ST"), ("CM", "ST"), ("FB", "AM_W")}
CHASING_SWAP_COST = 0.6
CHASING_SWAP_FROM_MINUTE = 70


class MatchState:
    """Consumes the event stream and keeps everything the engine needs."""

    def __init__(self, match_id: str, players: list[Player], starters: set[str], book: ProfileBook) -> None:
        self.match_id = match_id
        self.book = book
        self.players = {p.player_id: p for p in players}
        self.team_ids = sorted({p.team_id for p in players})
        self.on_pitch = set(starters)
        self.used = set(starters)  # anyone who has been on the pitch (cannot come back on)
        self.on_since: dict[str, float] = {pid: 0.0 for pid in starters}
        self.minutes_played: dict[str, float] = defaultdict(float)
        self.goals: dict[str, int] = defaultdict(int)
        self.reds: dict[str, int] = defaultdict(int)
        self.subs_made: dict[str, int] = defaultdict(int)
        self.live: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.window: dict[str, dict[str, float]] = {t: defaultdict(float) for t in self.team_ids}
        self.window_minutes = 0.0
        self.minute = 0
        self._t = 0.0  # playing time in minutes, continuous across half-time
        self._period_offset = 0.0
        self._tracker = ComponentTracker()

    def role(self, pid: str) -> str | None:
        """Starters: their position in this match. Bench: their usual role.

        Never use where a substitute ended up playing; that is only known afterwards.
        """
        if pid in self.on_since:
            return self.players[pid].role.value
        prof = self.book.players.get(pid)
        return prof.role if prof else None

    def _advance(self, ev: Event) -> None:
        if ev.type is EventType.PERIOD_START and ev.period == 2:
            self._period_offset = self._t - ev.clock / 60
        t = ev.clock / 60 + self._period_offset
        dt = max(0.0, t - self._t)
        if dt:
            decay = 0.5 ** (dt / HALF_LIFE_MIN)
            for w in self.window.values():
                for k in w:
                    w[k] *= decay
            self.window_minutes = self.window_minutes * decay + HALF_LIFE_MIN / math.log(2) * (1 - decay)
            for pid in self.on_pitch:
                self.minutes_played[pid] += dt
        self._t = max(self._t, t)
        self.minute = ev.minute

    def feed(self, ev: Event) -> None:
        self._advance(ev)
        if (ev.type is EventType.SHOT and ev.goal) or ev.type is EventType.OWN_GOAL:
            self.goals[ev.team_id] += 1
        elif ev.type is EventType.CARD and ev.card in ("red", "second_yellow"):
            self.reds[ev.team_id] += 1
            self.on_pitch.discard(ev.player_id)
        elif ev.type is EventType.SUBSTITUTION:
            self.on_pitch.discard(ev.player_id)
            self.on_pitch.add(ev.replacement_id)
            self.used.add(ev.replacement_id)
            self.on_since[ev.replacement_id] = self._t
            self.subs_made[ev.team_id] += 1
        for c in self._tracker.feed(ev):
            self.live[c.player_id][c.component] += c.value
            self.window[c.team_id][c.component] += c.value

    def game_state(self, team_id: str) -> GameState:
        opp = next(t for t in self.team_ids if t != team_id)
        return GameState(
            minute=self.minute,
            goal_diff=self.goals[team_id] - self.goals[opp],
            red_card_diff=self.reds[team_id] - self.reds[opp],
            subs_left=MAX_SUBS - self.subs_made[team_id],
        )


def importance(state: GameState) -> dict[str, float]:
    tau = min(state.minute, 90) / 90
    mode = "chasing" if state.goal_diff < 0 else "protecting" if state.goal_diff > 0 else "level"
    intensity = tau * (1.0 if abs(state.goal_diff) >= 2 else 0.75)
    w = {d: 1 + intensity * (IMPORTANCE[mode][d] - 1) for d in DIMENSIONS}
    if state.red_card_diff > 0:
        w["defense"] += 0.2
        w["retention"] += 0.1
    elif state.red_card_diff < 0:
        w["threat"] += 0.2
        w["creation"] += 0.1
    return w


def team_needs(ms: MatchState, team_id: str) -> TeamNeeds:
    base = ms.book.teams[team_id]
    opp = next(t for t in ms.team_ids if t != team_id)
    win, opp_win = ms.window[team_id], ms.window[opp]
    z: dict[str, float] = {}
    for c in ATTACKING:
        expected = base.p90[c] / 90 * ms.window_minutes
        dispersion = XG_DISPERSION if c in ("npxg", "xa") else 1.0
        z[c] = (expected - win[c]) / math.sqrt(max(expected, 0.5) * dispersion)
    conceded = []
    for c in CONCEDED:
        expected = base.conceded_p90[c] / 90 * ms.window_minutes
        dispersion = XG_DISPERSION if c == "npxg" else 1.0
        conceded.append((opp_win[c] - expected) / math.sqrt(max(expected, 0.5) * dispersion))
    expected_losses = base.loss_rate * win["ball_actions"]
    z["retention_rate"] = (win["ball_losses"] - expected_losses) / math.sqrt(max(expected_losses, 0.5))

    deficit = {d: sum(z[c] for c in comps) / len(comps) for d, comps in DIMENSIONS.items() if d != "defense"}
    deficit["defense"] = sum(conceded) / len(conceded)
    w = importance(ms.game_state(team_id))
    needs = {d: 1 / (1 + math.exp(-(deficit[d] / 1.5 + 2 * math.log(w[d])))) for d in DIMENSIONS}
    return TeamNeeds(
        team_id=team_id,
        needs={d: round(v, 3) for d, v in needs.items()},
        deficit_z={d: round(v, 2) for d, v in deficit.items()},
        importance={d: round(v, 2) for d, v in w.items()},
    )


def live_dimensions(ms: MatchState, pid: str) -> dict[str, float]:
    """Pre-match profile updated with this match's evidence, then pressing fatigue applied."""
    prof = ms.book.players[pid]
    played = ms.minutes_played.get(pid, 0.0)
    n90, live = played / 90, ms.live.get(pid, {})
    p90 = {c: (PRIOR_90S[c] * prof.p90[c] + live.get(c, 0.0)) / (PRIOR_90S[c] + n90) for c in VOLUME_COMPONENTS}
    actions = live.get("ball_actions", 0.0)
    retained = actions - live.get("ball_losses", 0.0)
    retention = (PRIOR_BALL_ACTIONS * prof.retention_rate + retained) / (PRIOR_BALL_ACTIONS + actions)
    p90["pressures"] *= 1 - PRESSING_FATIGUE_AT_90 * min(played, 90) / 90
    return ms.book.scale.dimensions(p90, retention)


def substitution_score(needs: TeamNeeds, delta: dict[str, float]) -> float:
    """Gains count only where the team has a problem; losses always cost.

    A plain sum of need x delta turns into a generic overall rating whenever needs are
    flat (around 0.5), and then recommends replacing specialists (it took Kane off at 65'
    of Tottenham 0-1 Leicester for a midfielder). Here a dimension at its usual level
    (need 0.5) gives no credit for improving it, but losing it still costs.
    """
    score = 0.0
    for d, change in delta.items():
        if change >= 0:
            score += max(needs.needs[d] - 0.5, 0.0) * 2 * change
        else:
            score += 0.5 * needs.importance[d] * change
    return score


def _role_cost(out_role: str, in_role: str, state: GameState) -> float | None:
    """None = not a sensible swap."""
    cost = ROLE_DISTANCE.get(frozenset({out_role, in_role}))
    if cost is not None:
        return cost
    if state.goal_diff < 0 and state.minute >= CHASING_SWAP_FROM_MINUTE and (out_role, in_role) in CHASING_SWAP:
        return CHASING_SWAP_COST
    return None


def recommend(ms: MatchState, team_id: str, top: int = 3) -> Recommendation:
    state = ms.game_state(team_id)
    needs = team_needs(ms, team_id)
    remaining = max(90 - state.minute, 0) + 4  # typical stoppage time
    on = [p for p in ms.on_pitch if ms.players[p].team_id == team_id and p in ms.book.players]
    bench = [
        p for p, pl in ms.players.items()
        if pl.team_id == team_id and p not in ms.used and p in ms.book.players
    ]
    options: list[SubOption] = []
    if state.subs_left > 0:
        for out_id in on:
            out_dims = live_dimensions(ms, out_id)
            for in_id in bench:
                cost = _role_cost(ms.role(out_id), ms.role(in_id), state)
                if cost is None:
                    continue
                in_dims = ms.book.scale.dimensions(ms.book.players[in_id].p90, ms.book.players[in_id].retention_rate)
                delta = {d: in_dims[d] - out_dims[d] for d in DIMENSIONS}
                score = substitution_score(needs, delta) - cost
                options.append(_option(ms, out_id, in_id, out_dims, in_dims, delta, score, remaining, needs))
    options.sort(key=lambda o: o.score, reverse=True)
    best = options[:top]
    return Recommendation(
        match_id=ms.match_id,
        team_id=team_id,
        state=state,
        needs=needs,
        recommend=bool(best) and best[0].expected_benefit >= RECOMMEND_THRESHOLD,
        options=best,
    )


def _option(ms, out_id, in_id, out_dims, in_dims, delta, score, remaining, needs) -> SubOption:
    scale, book = ms.book.scale, ms.book
    delta_pct = {d: round(scale.percentile(d, in_dims[d]) - scale.percentile(d, out_dims[d])) for d in DIMENSIONS}
    reliability = min(
        min(book.players[in_id].reliability.values()),
        min(book.players[out_id].reliability.values()),
    )
    strength = "high" if reliability >= 0.6 else "medium" if reliability >= 0.3 else "low"
    out_name, in_name = book.players[out_id].name, book.players[in_id].name
    played = ms.minutes_played.get(out_id, 0.0)
    reasons = [
        f"Team need {d}: {v:.2f} ({needs.deficit_z[d]:+.1f} sd vs the team's usual level, importance x{needs.importance[d]:.2f})"
        for d, v in sorted(needs.needs.items(), key=lambda kv: -kv[1]) if v >= 0.6
    ]
    gains = sorted((d for d in delta_pct if delta_pct[d] > 0), key=lambda d: -delta_pct[d])[:2]
    reasons += [f"{in_name} vs {out_name}: {d} {delta_pct[d]:+.0f} percentile points" for d in gains]
    worst = min(delta_pct, key=delta_pct.get)
    if delta_pct[worst] < 0:
        reasons.append(f"Trade-off: {worst} {delta_pct[worst]:+.0f} percentile points")
    reasons.append(
        f"{out_name} has played {played:.0f} minutes; estimated pressing output "
        f"-{PRESSING_FATIGUE_AT_90 * min(played, 90) / 90:.0%} from fatigue"
    )
    reasons.append(f"Evidence: {in_name} {book.players[in_id].minutes:.0f} minutes before this match")
    return SubOption(
        out_player_id=out_id, out_name=book.players[out_id].name,
        in_player_id=in_id, in_name=book.players[in_id].name,
        score=round(score, 3), expected_benefit=round(score * remaining / 90, 3),
        delta_pct=delta_pct, strength=strength, reasons=reasons,
    )
