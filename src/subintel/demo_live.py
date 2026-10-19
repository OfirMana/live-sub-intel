"""Live dimension vectors and position-constrained scoring of demo player cards."""
from __future__ import annotations

import math
from collections import defaultdict

from .demo_dataset import DIMS, aggregate, clamp
from .engine import MatchState, RECOMMEND_THRESHOLD, substitution_score, team_needs
from .metrics import DIMENSIONS, VOLUME_COMPONENTS
from .profiles import ProfileBook, Scale, TeamBaseline
from .schema import Event, EventType, Player, Role

TEAM_IDS = {'Liverpool': '24', 'Arsenal': '1', 'Chelsea': '33', 'Tottenham Hotspur': '38'}
# Was 1.5: freshness then carried 72 of 92 recommendations on the 216-point benchmark,
# including 29 with a negative tactical part. At 0.5 its size is comparable to tactical
# gains (6 of 32 recommendations are freshness-led). Not fitted to named swaps.
REFRESH_SCORE_CAP = 0.5
REFRESH_HORIZON_MINUTES = 30.0
# Trailing, a team may take a defender or midfielder off for an attacker and change shape
# (Klopp: Milner off, Benteke on, 4-3-3 to 4-4-2 at 65' against Arsenal). Earliest minute
# per outgoing role; the fit discount stands for the structural cost of the new shape.
CHASING_FORMATION_FROM = {'CM': 60, 'FB': 75, 'CB': 75}
CHASING_ATTACK_ROLES = ('ST', 'AM_W')
CHASING_FORMATION_FIT = .75
LOAD_FREE_SHARE = .5
LOAD_FATIGUE_SPAN = .7


def estimated_match_load(played, stamina, pressures, carries, expected_p90, meters_per_minute):
    """Capability-relative load proxy; inferred movement is not measured distance.

    Sparse on-ball activity never implies that off-ball work did not occur.
    Excess pressures/carries can increase inferred intensity, capped at 1.25.
    """
    def excess(count, rate):
        expected = rate * played / 90
        return clamp(count / max(expected, 1) - 1, 0, 1) if played >= 15 else 0
    intensity = 1 + .15 * excess(pressures, expected_p90['pressures']) + .10 * excess(carries, expected_p90['prog_carries'])
    capacity = clamp(1 + (stamina - 75) / 150, .8, 1.15)
    ratio = max(played, 0) / 90 * intensity / capacity
    fatigue = clamp((ratio - LOAD_FREE_SHARE) / LOAD_FATIGUE_SPAN, 0, 1) ** 1.5
    return dict(fatigue=round(fatigue, 4), load_ratio=round(ratio, 4), intensity=round(intensity, 4),
                stamina_capacity=round(capacity, 4),
                estimated_distance_m=round(meters_per_minute * max(played, 0) * intensity, 1),
                distance_is_observed=False,
                load_source='ESTIMATED:minutes+FIFA stamina+pressure/carry proxy; synthetic distance reference')


def refresh_value(fatigue, incoming, outgoing):
    """Freshness has value even with flat tactical needs; ability losses still cost.

    This is the only fatigue reward in candidate scoring. Card deltas exclude
    fatigue, preventing the same load relief from also entering tactical gains.
    """
    relevant = ('threat', 'progression', 'defense')
    quality = clamp(sum(incoming[d] for d in relevant) / max(sum(outgoing[d] for d in relevant), 1), 0, 1)
    return REFRESH_SCORE_CAP * fatigue * quality


def make_match(dataset, evidence, match_id='synthetic-demo', teams=('Liverpool', 'Arsenal')):
    cards = {str(p['player_id']): p for p in dataset['players']}
    players = [Player(player_id=pid, name=p['name'], team_id=TEAM_IDS[p['team']], role=Role(p['primary_role'])) for pid, p in cards.items() if p['team'] in teams]
    # Use initial target-match positions only; never the later tactical shifts.
    starter_positions = evidence.get('starter_positions', {})
    for p in players:
        if p.player_id in starter_positions:
            p.role = Role(starter_positions[p.player_id])
    book = ProfileBook(players={}, teams={tid: TeamBaseline(team_id=tid, **evidence['team_baselines'][tid]) for tid in TEAM_IDS.values()},
                       scale=Scale(mean={}, std={}, dimension_values={}))
    starters = {p.player_id for p in players if cards[p.player_id]['matchday_status'] == 'Starter'}
    ms = DemoMatchState(match_id, players, starters, book)
    ms.cards, ms.evidence = cards, evidence
    return ms


class DemoMatchState(MatchState):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aerials = defaultdict(lambda: defaultdict(float))
        self.aerial_window = defaultdict(lambda: defaultdict(float))
        self.patterns = defaultdict(lambda: defaultdict(float))

    def _advance(self, ev):
        before = self._t
        super()._advance(ev)
        decay = .5 ** ((self._t - before) / 12)
        for w in (*self.aerial_window.values(), *self.patterns.values()):
            for k in w:
                w[k] *= decay

    def feed(self, ev):
        # Generated approved swaps preserve the active slot, even when the
        # incoming player's supported secondary role differs from his primary.
        if ev.type is EventType.SUBSTITUTION and self.match_id.startswith('synthetic'):
            self.players[ev.replacement_id].role = self.players[ev.player_id].role
        super().feed(ev)
        if ev.player_id and ev.aerial_contest:
            for w in (self.aerials[ev.player_id], self.aerial_window[ev.player_id]):
                w['attempts'] += 1
                w['wins'] += int(bool(ev.aerial_won))
        if ev.cross:
            self.patterns[ev.team_id]['crosses'] += 1
        if ev.transition:
            self.patterns[ev.team_id]['transitions'] += 1

    def role(self, pid):
        if pid in self.on_since:
            return self.players[pid].role.value
        return self.cards[pid]['primary_role']


def expected_rates(ms, pid):
    card = ms.cards[pid]
    role = ms.players[pid].role.value if pid in ms.on_pitch else card['primary_role']
    if role == 'GK':
        return None
    rows = [r for r in ms.evidence['rows'] if r['player_id'] == pid]
    totals = aggregate(rows)
    prior = ms.evidence['role_component_p90'][role]
    n = totals['minutes'] / 90
    p90 = {c: (totals[c] + 5 * prior[c]) / (n + 5) for c in VOLUME_COMPONENTS}
    # Card ability modifies the role/season rate moderately, never equates rating to counts.
    component_dim = {c: d for d, cs in DIMENSIONS.items() for c in cs}
    for c in p90:
        d = component_dim[c]
        p90[c] *= clamp(card['recent']['ratings'][d] / 75, .65, 1.25)
    actions = totals['ball_actions']
    role_ret = 1 - prior['ball_losses'] / max(prior['ball_actions'], 1)
    retention = (actions - totals['ball_losses'] + 100 * role_ret) / (actions + 100)
    return p90, retention


def live_performance(ms, pid):
    card = ms.cards[pid]
    played = ms.minutes_played.get(pid, 0)
    if card['primary_role'] == 'GK':
        return dict(player_id=pid, dimensions=dict.fromkeys(DIMS), cumulative=dict(ms.live[pid]), recent_window=dict(ms.player_window[pid]), fatigue=0, status='UNSUPPORTED_GK')
    rates, retention = expected_rates(ms, pid)
    tid = ms.players[pid].team_id
    opp = next(t for t in ms.team_ids if t != tid)
    own_actions = ms.window[tid]['ball_actions']
    opp_actions = ms.window[opp]['ball_actions']
    # Action share is a possession/opportunity proxy, not tracking possession.
    baseline = ms.book.teams[tid].p90['ball_actions']
    opp_baseline = ms.book.teams[opp].p90['ball_actions']
    expected_share = baseline / (baseline + opp_baseline)
    share = own_actions / (own_actions + opp_actions) if own_actions + opp_actions else expected_share
    attack_context = clamp(share / expected_share, .6, 1.4)
    defense_context = clamp((1 - share) / (1 - expected_share), .6, 1.4)
    exposure = ms.player_window_minutes[pid]
    counts = ms.player_window[pid]
    evidence_strength = exposure / (exposure + 12)
    z = {}
    for c, rate in rates.items():
        context = defense_context if c in ('pressures', 'def_actions') else attack_context
        expected = rate * exposure / 90 * context
        variance = max(expected, .5) * (.3 if c in ('npxg', 'xa') else 1)
        z[c] = (counts.get(c, 0) - expected) / math.sqrt(variance)
    actions = counts.get('ball_actions', 0)
    z['retention_rate'] = ((actions - counts.get('ball_losses', 0)) - actions * retention) / math.sqrt(max(actions * (1-retention), .5))
    vector = {d: round(math.tanh(sum(z[c] for c in cs) / len(cs) / 2) * evidence_strength, 4) for d, cs in DIMENSIONS.items()}
    vector['retention'] *= actions / (actions + 20)
    aerial = ms.aerial_window[pid]
    vector['aerial'] = round((aerial['wins'] / aerial['attempts'] - .5) * 2 * aerial['attempts'] / (aerial['attempts'] + 10), 4) if aerial['attempts'] else None
    load = estimated_match_load(played, card['physical']['stamina'], ms.live[pid].get('pressures', 0),
                                ms.live[pid].get('prog_carries', 0), rates,
                                card['physical']['tracking']['meters_per_minute'])
    return dict(player_id=pid, dimensions=vector, cumulative=dict(ms.live[pid]), recent_window=dict(counts),
                recent_window_minutes=round(exposure, 3), minutes_played=round(played, 3),
                expectation_p90=rates, action_share_proxy=round(share, 3),
                evidence_strength=round(evidence_strength, 3), **load)


def effective_profile(ms, pid, on_pitch):
    card = ms.cards[pid]
    result = dict(card['recent']['ratings'])
    if on_pitch:
        live = live_performance(ms, pid)
        for d, v in live['dimensions'].items():
            if v is not None:
                result[d] = clamp(result[d] + 4 * v)
    return result


def swap_fit(state, out_role, card):
    """(position fit, change type) for a candidate swap, or None when it is not allowed."""
    if out_role in card['positions']['eligibility']:
        return card['positions']['suitability'][out_role], 'LIKE_FOR_LIKE'
    earliest = CHASING_FORMATION_FROM.get(out_role)
    if (state.goal_diff < 0 and earliest is not None and state.minute >= earliest
            and card['primary_role'] in CHASING_ATTACK_ROLES):
        return CHASING_FORMATION_FIT, 'FORMATION_CHANGE'
    return None


def no_substitution_reason(state, options):
    if state.subs_left <= 0:
        return 'NO_SUBSTITUTIONS_LEFT'
    if not 20 <= state.minute < 94:
        return 'OUTSIDE_DECISION_WINDOW'
    if not options:
        return 'NO_ELIGIBLE_CANDIDATE'
    if any(o['expected_benefit'] >= RECOMMEND_THRESHOLD for o in options):
        return 'ONLY_TACTICALLY_HARMFUL_OPTIONS_CLEAR_THRESHOLD'
    return 'BELOW_THRESHOLD'


def recommend_demo(ms, tid, top=3):
    needs = team_needs(ms, tid)
    state = ms.game_state(tid)
    opp = next(t for t in ms.team_ids if t != tid)
    urgency = max(0, -state.goal_diff) * min(state.minute / 90, 1)
    tactical = dict(aerial=round(clamp(ms.patterns[tid]['crosses'] / 10 * urgency, 0, 1), 3),
                    pace=round(clamp(ms.patterns[tid]['transitions'] / 10, 0, 1), 3),
                    recovery_pace=round(clamp(ms.patterns[opp]['transitions'] / 10, 0, 1), 3))
    options = []
    if state.subs_left > 0 and 20 <= state.minute < 94:
        for out_id in sorted(ms.on_pitch):
            if out_id not in ms.cards or ms.players[out_id].team_id != tid or ms.role(out_id) == 'GK':
                continue
            outgoing = effective_profile(ms, out_id, True)
            for in_id, card in sorted(ms.cards.items()):
                if in_id not in ms.players or in_id in ms.used or ms.players[in_id].team_id != tid:
                    continue
                swap = swap_fit(state, ms.role(out_id), card)
                if swap is None:
                    continue
                fit, change_type = swap
                incoming = effective_profile(ms, in_id, False)
                delta = {d: incoming[d] - outgoing[d] for d in DIMENSIONS}
                core = substitution_score(needs, {d: v / 20 for d, v in delta.items()})
                aerial_delta = (incoming['aerial'] - outgoing['aerial']) / 20
                speed_in = card['physical']['tracking']['max_speed_kmh']
                speed_out = ms.cards[out_id]['physical']['tracking']['max_speed_kmh']
                tactical_gain = .1 * tactical['aerial'] * aerial_delta + .05 * (tactical['pace'] + tactical['recovery_pace']) * (speed_in - speed_out) / 5
                rel = min(sum(card['general']['reliability'].values()) / 6, sum(ms.cards[out_id]['general']['reliability'].values()) / 6)
                fatigue = live_performance(ms, out_id)['fatigue']
                refresh = refresh_value(fatigue, incoming, outgoing)
                score = (core + tactical_gain + refresh) * (.5 + .5 * rel)
                remaining = max(94 - state.minute, 0)
                # Tactical differences accumulate over the remaining match.
                # Refresh addresses the next ~30 minutes, not a second full 90.
                tactical_horizon = remaining / 90
                refresh_horizon = min(remaining / REFRESH_HORIZON_MINUTES, 1)
                tactical_benefit = fit * (.5 + .5 * rel) * (core + tactical_gain) * tactical_horizon
                freshness_benefit = fit * (.5 + .5 * rel) * refresh * refresh_horizon
                benefit = tactical_benefit + freshness_benefit
                reasons = [f'HIGH_{d.upper()}_NEED' for d, v in needs.needs.items() if v >= .65 and delta[d] > 0]
                if change_type == 'FORMATION_CHANGE':
                    reasons.append('CHASING_FORMATION_CHANGE')
                if refresh >= .05:
                    reasons.append('ESTIMATED_FRESHNESS_RELIEF')
                if fatigue >= .6:
                    reasons.append('CURRENT_PLAYER_ESTIMATED_LOAD')
                if tactical['aerial'] > .3 and aerial_delta > 0:
                    reasons.append('BENCH_PLAYER_AERIAL_ADVANTAGE')
                options.append(dict(out_player=dict(id=out_id, name=ms.cards[out_id]['name']),
                                    in_player=dict(id=in_id, name=card['name']), expected_changes={d: round(v, 3) for d, v in delta.items()},
                                    position_fit=fit, change_type=change_type, evidence_strength=round(rel, 3), reason_codes=reasons,
                                    score_components=dict(tactical_core=round(core, 4), tactical_support=round(tactical_gain, 4),
                                                          freshness_relief=round(refresh, 4), outgoing_fatigue=fatigue,
                                                          evidence_multiplier=round(.5+.5*rel, 4), remaining_time_multiplier=round(tactical_horizon, 4),
                                                          freshness_time_multiplier=round(refresh_horizon, 4),
                                                          tactical_benefit=round(tactical_benefit, 4),
                                                          freshness_benefit=round(freshness_benefit, 4)),
                                    decision_basis='TACTICAL' if tactical_benefit >= freshness_benefit else 'FRESH_LEGS',
                                    score=round(score, 4), expected_benefit=round(benefit, 4)))
    options.sort(key=lambda o: (-o['expected_benefit'], o['out_player']['id'], o['in_player']['id']))
    # Fresh legs may tip a change that does not hurt the team tactically, never justify one that does.
    eligible = [o for o in options if o['expected_benefit'] >= RECOMMEND_THRESHOLD
                and o['score_components']['tactical_benefit'] >= 0]
    selected = eligible[0] if eligible else None
    return dict(match_id=ms.match_id, minute=state.minute, team_id=tid,
                recommendation='SUBSTITUTION' if selected else 'NO_SUBSTITUTION',
                no_substitution_reason=None if selected else no_substitution_reason(state, options),
                state=state.model_dump(), team_needs=needs.needs, tactical_needs=tactical,
                threshold=RECOMMEND_THRESHOLD, selected=selected,
                physical_need=dict(freshness=max((live_performance(ms, pid)['fatigue'] for pid in ms.on_pitch
                                                  if pid in ms.cards and ms.players[pid].team_id == tid and ms.role(pid) != 'GK'), default=0),
                                   source='ESTIMATED_MATCH_LOAD', refresh_score_cap=REFRESH_SCORE_CAP),
                alternatives=options[:top], player_live=[live_performance(ms, pid) for pid in sorted(ms.on_pitch) if pid in ms.cards and ms.players[pid].team_id == tid],
                unavailable_profile_ids=[pid for pid in sorted(ms.on_pitch) if ms.players[pid].team_id == tid and pid not in ms.cards],
                provenance='Deterministic demo model; evidence_strength is not probability')
