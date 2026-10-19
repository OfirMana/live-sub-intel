"""Coach-owned objectives, explicit formation plans and auditable replay decisions.

No LLM and no mutation of the shared engine. Pitch coordinates are schematic.
"""
from __future__ import annotations

import math
from collections import defaultdict
from functools import lru_cache

from pydantic import BaseModel, ConfigDict
from typing import Literal

from .demo_live import (effective_profile, live_performance, make_match,
                        MAX_TACTICAL_LOSS_FOR_FRESHNESS)
from .engine import substitution_score, team_needs, RECOMMEND_THRESHOLD
from .profiles import TeamBaseline
from .schema import Event, EventType, Player, Role, TeamNeeds
from .statsbomb import ROLE_BY_POSITION, convert_event

DIMS = ('threat', 'creation', 'progression', 'retention', 'defense')
POSITIONS = {
    'Goalkeeper': (50, 91), 'Right Back': (83, 72), 'Left Back': (17, 72),
    'Right Center Back': (64, 77), 'Center Back': (50, 77), 'Left Center Back': (36, 77),
    'Right Wing Back': (88, 54), 'Left Wing Back': (12, 54),
    'Right Defensive Midfield': (63, 61), 'Center Defensive Midfield': (50, 63), 'Left Defensive Midfield': (37, 61),
    'Right Center Midfield': (66, 49), 'Center Midfield': (50, 49), 'Left Center Midfield': (34, 49),
    'Right Midfield': (83, 43), 'Left Midfield': (17, 43),
    'Right Attacking Midfield': (69, 33), 'Center Attacking Midfield': (50, 32), 'Left Attacking Midfield': (31, 33),
    'Right Wing': (83, 24), 'Left Wing': (17, 24),
    'Right Center Forward': (63, 17), 'Center Forward': (50, 17), 'Left Center Forward': (37, 17),
    'Secondary Striker': (50, 27),
}
BACK_FOUR = ['Right Back', 'Right Center Back', 'Left Center Back', 'Left Back']
BACK_THREE = ['Right Center Back', 'Center Back', 'Left Center Back']
FORMATIONS = {
    '4-3-3': BACK_FOUR + ['Center Defensive Midfield', 'Right Center Midfield', 'Left Center Midfield', 'Right Wing', 'Center Forward', 'Left Wing'],
    '4-2-3-1': BACK_FOUR + ['Right Defensive Midfield', 'Left Defensive Midfield', 'Right Attacking Midfield', 'Center Attacking Midfield', 'Left Attacking Midfield', 'Center Forward'],
    '4-4-2': BACK_FOUR + ['Right Midfield', 'Right Center Midfield', 'Left Center Midfield', 'Left Midfield', 'Right Center Forward', 'Left Center Forward'],
    '4-1-4-1': BACK_FOUR + ['Center Defensive Midfield', 'Right Midfield', 'Right Center Midfield', 'Left Center Midfield', 'Left Midfield', 'Center Forward'],
    '3-5-2': BACK_THREE + ['Right Wing Back', 'Left Wing Back', 'Center Defensive Midfield', 'Right Center Midfield', 'Left Center Midfield', 'Right Center Forward', 'Left Center Forward'],
    '3-4-3': BACK_THREE + ['Right Wing Back', 'Left Wing Back', 'Right Center Midfield', 'Left Center Midfield', 'Right Wing', 'Center Forward', 'Left Wing'],
}
# Transparent role-exposure heuristics, not fitted or measured event probabilities.
ROLE_EXPOSURE = {
    'CB': (0.6, 0.65, 0.85, 1.0, 1.35), 'FB': (0.8, 0.95, 1.1, 1.0, 1.15),
    'CM': (0.9, 1.05, 1.15, 1.15, 1.0), 'AM_W': (1.2, 1.25, 1.1, 0.95, 0.7),
    'ST': (1.35, 1.0, 0.8, 0.8, 0.55),
}
STANCE = dict(balanced=(1, 1, 1, 1, 1), attack=(1.35, 1.25, 1.15, .95, .85),
              defend=(.8, .9, .95, 1.2, 1.35))


class CoachConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    stance: Literal['balanced', 'attack', 'defend'] = 'balanced'
    objective: Literal['win', 'draw', 'competitive', 'limit_damage'] = 'competitive'
    formation: Literal['observed', '4-3-3', '4-2-3-1', '4-4-2', '4-1-4-1', '3-5-2', '3-4-3'] = 'observed'
    freshness_cap: Literal[0.0, 0.5, 1.0, 1.5] = 1.0


def slot(position, player_id, roster):
    p = roster[player_id]
    x, y = POSITIONS[position]
    return dict(player_id=player_id, name=p['name'], number=p.get('number'),
                position=position, role=ROLE_BY_POSITION[position].value, x=x, y=y)


class CoachReplay:
    def __init__(self, dataset, evidence, raw, lineup, mid, tid):
        self.dataset, self.evidence, self.raw, self.mid, self.tid = dataset, evidence, raw, str(mid), str(tid)
        self.roster = {str(p['player_id']): dict(name=p.get('player_nickname') or p['player_name'],
                       number=p.get('jersey_number'), team_id=str(t['team_id'])) for t in lineup for p in t['lineup']}
        self.starts = [e for e in raw if e['type']['name'] == 'Starting XI' and e['period'] == 1 and e['minute'] == 0]

    def state_at(self, minute):
        if minute not in range(0, 91, 5):
            raise ValueError('Use a five-minute checkpoint from 0 to 90')
        ms = make_match(self.dataset, self.evidence, self.mid)
        players = {pid: Player(player_id=pid, name=p['name'], team_id=p['team_id'],
                   role=Role(ms.cards[pid]['primary_role']) if pid in ms.cards else None) for pid, p in self.roster.items()}
        starters = set()
        shape, formation, initial = [], None, None
        for e in self.starts:
            for p in e['tactics']['lineup']:
                pid = str(p['player']['id'])
                players[pid].role = ROLE_BY_POSITION[p['position']['name']]
                starters.add(pid)
            if str(e['team']['id']) == self.tid:
                initial = formation = '-'.join(str(e['tactics']['formation']))
                shape = [slot(p['position']['name'], str(p['player']['id']), self.roster) for p in e['tactics']['lineup']]
        ms.players, ms.on_pitch, ms.used = players, set(starters), set(starters)
        ms.on_since = dict.fromkeys(starters, 0.)
        ms.team_ids = sorted({p.team_id for p in players.values()})
        ms.window = {tid: defaultdict(float) for tid in ms.team_ids}
        ms.book.teams = {tid: TeamBaseline(team_id=tid, **self.evidence['team_baselines'][tid]) for tid in ms.team_ids}
        shifts = []
        for item in self.raw:
            # First-half stoppage is only included after the 45-minute checkpoint.
            if item['minute'] >= minute and (item['period'] == 2 or minute <= 45):
                break
            if item['type']['name'] == 'Tactical Shift':
                for p in item.get('tactics', {}).get('lineup', []):
                    pid = str(p['player']['id'])
                    if pid in ms.on_pitch:
                        ms.players[pid].role = ROLE_BY_POSITION[p['position']['name']]
                if str(item['team']['id']) == self.tid:
                    formation = '-'.join(str(item['tactics']['formation']))
                    shape = [slot(p['position']['name'], str(p['player']['id']), self.roster) for p in item['tactics']['lineup']]
                    shifts.append(dict(minute=item['minute'], second=item['second'], formation=formation))
            ev = convert_event(item, self.mid)
            if ev is None:
                continue
            if ev.type == EventType.SUBSTITUTION:
                ms.players[ev.replacement_id].role = ms.players[ev.player_id].role
                if ev.team_id == self.tid:
                    shape = [slot(p['position'], ev.replacement_id, self.roster) if p['player_id'] == ev.player_id else p for p in shape]
            ms.feed(ev)
            if ev.type == EventType.CARD and ev.card in ('red', 'second_yellow'):
                shape = [p for p in shape if p['player_id'] != ev.player_id]
        if minute:
            ms.feed(Event(event_id=f'coach-checkpoint-{minute}', match_id=self.mid, period=1 if minute <= 45 else 2,
                          minute=minute, second=0, team_id=self.tid, type=EventType.PERIOD_END))
        return ms, dict(formation=formation, initial_formation=initial, lineup=shape, shifts=shifts,
                        source='OBSERVED_STATSBOMB_TACTICS', coordinate_source='SCHEMATIC_NOT_TRACKING')


def coach_needs(ms, tid, config):
    base = team_needs(ms, tid)
    state = ms.game_state(tid)
    tau = min(state.minute, 90) / 90
    w = dict(zip(DIMS, STANCE[config.stance]))
    chase = (config.objective == 'win' and state.goal_diff <= 0) or (config.objective == 'draw' and state.goal_diff < 0)
    if chase:
        factor = (1 + .55 * tau, 1 + .4 * tau, 1 + .25 * tau, 1, 1)
    elif config.objective == 'limit_damage':
        factor = (.85, .9, 1, 1 + .25 * tau, 1 + .4 * tau)
    elif state.goal_diff > 0 or (config.objective in ('draw', 'competitive') and state.goal_diff == 0):
        factor = (1, 1, 1, 1 + .12 * tau, 1 + .18 * tau)
    elif config.objective == 'competitive' and state.goal_diff < 0:
        factor = (1 + .2 * tau, 1 + .15 * tau, 1 + .1 * tau, 1, 1)
    else:
        factor = (1, 1, 1, 1, 1)
    w = {d: w[d] * factor[i] for i, d in enumerate(DIMS)}
    signals = {d: max(base.deficit_z[d], 0) if w[d] > 1 else base.deficit_z[d] for d in DIMS}
    needs = {d: 1 / (1 + math.exp(-max(-30, min(30, signals[d] / 1.5 + 2 * math.log(w[d]))))) for d in DIMS}
    return TeamNeeds(team_id=tid, needs=needs, deficit_z=base.deficit_z, importance=w)


def fit_for(card, role):
    if role == 'GK':
        return 1. if card['primary_role'] == 'GK' else None
    if role not in card['positions']['eligibility']:
        return None
    return float(card['positions']['suitability'][role])


def assign_formation(lineup, formation, cards, roster, ratings):
    """Exact maximum-fit assignment, then ability, then minimum positional movement.

    Ten outfield slots use bitmask dynamic programming. Unsupported roles are
    rejected, not silently invented; left/right preference is schematic only.
    """
    if len(lineup) != 11 or len({p['player_id'] for p in lineup}) != 11 or any(p['player_id'] not in cards for p in lineup):
        return None
    keepers = [p for p in lineup if p['role'] == 'GK']
    if len(keepers) != 1:
        return None
    field = sorted((p for p in lineup if p['role'] != 'GK'), key=lambda p: p['player_id'])
    positions = FORMATIONS[formation]
    def assignment_fit(p, role):
        supported = fit_for(cards[p['player_id']], role)
        # Keep the observed incumbent-role baseline consistent across shapes.
        # Merely choosing a template must not penalize an unchanged player/role.
        return 1. if supported is not None and p['role'] == role and not p.get('is_new') else supported
    costs = []
    for position in positions:
        role = ROLE_BY_POSITION[position].value
        x, y = POSITIONS[position]
        row = []
        for p in field:
            pid = p['player_id']
            fit = assignment_fit(p, role)
            ability = sum(ratings[pid][d] * v for d, v in zip(DIMS, ROLE_EXPOSURE[role])) / 5
            movement = (abs(p['x']-x) + abs(p['y']-y)) / 200
            row.append(None if fit is None else fit * 1000 + ability * .1 - movement)
        costs.append(row)
    @lru_cache(None)
    def solve(mask):
        i = mask.bit_count()
        if i == 10:
            return 0., ()
        best = None
        for j, value in enumerate(costs[i]):
            if mask & (1 << j) or value is None:
                continue
            tail = solve(mask | (1 << j))
            if tail is not None and (best is None or value + tail[0] > best[0]):
                best = value + tail[0], (j,) + tail[1]
        return best
    result = solve(0)
    if result is None:
        return None
    return [slot('Goalkeeper', keepers[0]['player_id'], roster)] + [
        dict(slot(pos, field[j]['player_id'], roster), fit=assignment_fit(field[j], ROLE_BY_POSITION[pos].value))
        for pos, j in zip(positions, result[1])]


def lineup_totals(lineup, ratings):
    totals = dict.fromkeys(DIMS, 0.)
    for p in lineup:
        if p['role'] == 'GK':
            continue
        for d, exposure in zip(DIMS, ROLE_EXPOSURE[p['role']]):
            totals[d] += ratings[p['player_id']][d] * exposure * p.get('fit', 1.)
    return totals


def recommend_coach(ms, tid, observed, roster, config: CoachConfig):
    state = ms.game_state(tid)
    needs = coach_needs(ms, tid, config)
    active = observed['lineup']
    cards = ms.cards
    available = sorted(pid for pid, p in ms.players.items() if p.team_id == tid and pid in cards)
    ratings = {pid: effective_profile(ms, pid, pid in ms.on_pitch) for pid in available}
    missing = [p['player_id'] for p in active if p['player_id'] not in ratings]
    formation = observed['formation'] if config.formation == 'observed' else config.formation
    current = active if not missing else []
    no_sub_plan = current if config.formation == 'observed' else assign_formation(active, formation, cards, roster, ratings) if not missing else None
    reference = no_sub_plan or current
    options = []
    live = {p['player_id']: live_performance(ms, p['player_id']) for p in active if p['player_id'] in ratings}
    if state.subs_left > 0 and 20 <= state.minute < 94 and not missing and len(active) == 11:
        reference_totals = lineup_totals(reference, ratings)
        for outgoing in active:
            out_id = outgoing['player_id']
            if outgoing['role'] == 'GK':
                continue
            for in_id in available:
                if in_id in ms.used or cards[in_id]['primary_role'] == 'GK':
                    continue
                if config.formation == 'observed':
                    fit = fit_for(cards[in_id], outgoing['role'])
                    if fit is None:
                        continue
                    after = [dict(slot(p['position'], in_id, roster), fit=fit) if p['player_id'] == out_id else dict(p) for p in active]
                else:
                    replacement = dict(outgoing, player_id=in_id, is_new=True)
                    trial = [replacement if p['player_id'] == out_id else p for p in active]
                    after = assign_formation(trial, formation, cards, roster, ratings)
                    if after is None:
                        continue
                    fit = next(p.get('fit', 1.) for p in after if p['player_id'] == in_id)
                after_totals = lineup_totals(after, ratings)
                delta = {d: after_totals[d]-reference_totals[d] for d in DIMS}
                core = substitution_score(needs, {d: v/20 for d, v in delta.items()})
                # A small explicit disruption cost for retained players changing broad role.
                old_roles = {p['player_id']: p['role'] for p in active}
                moved = [dict(player_id=p['player_id'], name=p['name'], before=old_roles[p['player_id']], after=p['role'])
                         for p in after if p['player_id'] in old_roles and p['role'] != old_roles[p['player_id']]]
                reference_roles = {p['player_id']: p['role'] for p in reference}
                disruption = .02 * sum(p['player_id'] in reference_roles and p['role'] != reference_roles[p['player_id']] for p in after)
                rel = min(sum(cards[in_id]['general']['reliability'].values())/6, sum(cards[out_id]['general']['reliability'].values())/6)
                evidence_factor = .5 + .5 * rel
                remaining = max(94-state.minute, 0)
                tactical_time, refresh_time = remaining/90, min(remaining/30, 1)
                quality = min(1, sum(ratings[in_id][d] for d in ('threat','progression','defense')) /
                              max(sum(ratings[out_id][d] for d in ('threat','progression','defense')), 1))
                refresh = config.freshness_cap * live[out_id]['fatigue'] * quality
                tactical_benefit = evidence_factor * (core-disruption) * tactical_time
                fresh_benefit = evidence_factor * refresh * refresh_time
                benefit = tactical_benefit + fresh_benefit
                allowed = tactical_benefit >= -MAX_TACTICAL_LOSS_FOR_FRESHNESS
                basis = 'FRESH_LEGS' if fresh_benefit > max(tactical_benefit, 0) else 'TACTICAL'
                options.append(dict(out_player=dict(id=out_id, name=roster[out_id]['name']), in_player=dict(id=in_id, name=roster[in_id]['name']),
                    expected_changes={d: round(ratings[in_id][d]-ratings[out_id][d], 3) for d in DIMS},
                    lineup_changes={d: round(v, 3) for d, v in delta.items()}, position_fit=fit,
                    score_components=dict(tactical_core=round(core, 5), tactical_support=-disruption, freshness_relief=round(refresh, 5),
                    outgoing_fatigue=live[out_id]['fatigue'], evidence_multiplier=evidence_factor, remaining_time_multiplier=tactical_time,
                    freshness_time_multiplier=refresh_time, tactical_benefit=round(tactical_benefit, 5), freshness_benefit=round(fresh_benefit, 5)),
                    expected_benefit=round(benefit, 5), score=round(core-disruption+refresh, 5), evidence_strength=rel,
                    decision_basis=basis, quality_gate_passed=allowed, clears_threshold=benefit >= RECOMMEND_THRESHOLD,
                    recommended=allowed and benefit >= RECOMMEND_THRESHOLD,
                    change_type='FORMATION_CHANGE' if formation != observed['formation'] else 'REPOSITIONING' if moved else 'LIKE_FOR_LIKE',
                    formation=formation, proposed_lineup=after, repositioned=moved,
                    comparison_reference='FORMATION_ONLY_WITHOUT_SUB' if no_sub_plan and config.formation != 'observed' else 'CURRENT_OBSERVED_XI',
                    reason_codes=[basis, 'COACH_OBJECTIVE_'+config.objective.upper(), 'COACH_STANCE_'+config.stance.upper()]))
    options.sort(key=lambda c: (-c['expected_benefit'], c['out_player']['id'], c['in_player']['id']))
    selected = next((o for o in options if o['recommended']), None)
    reason = None if selected else 'NO_SUBSTITUTIONS_LEFT' if state.subs_left == 0 else 'OUTSIDE_DECISION_WINDOW' if state.minute < 20 else 'MISSING_PLAYER_PROFILES' if missing else 'UNSUPPORTED_PLAYER_COUNT' if len(active) != 11 else 'NO_FEASIBLE_FORMATION_WITH_ONE_SUB' if not options else 'QUALITY_LOSS_TOO_LARGE' if any(o['clears_threshold'] for o in options) else 'BELOW_THRESHOLD'
    return dict(version='coach-room-v1', match_id=ms.match_id, team_id=tid, minute=state.minute, state=state.model_dump(),
                coach_config=config.model_dump(), team_needs={d: round(v, 4) for d, v in needs.needs.items()},
                importance={d: round(v, 4) for d, v in needs.importance.items()}, performance_deficit_z=needs.deficit_z,
                recommendation='SUBSTITUTION' if selected else 'NO_SUBSTITUTION', selected=selected,
                no_substitution_reason=reason, alternatives=options, threshold=RECOMMEND_THRESHOLD,
                max_tactical_loss_for_freshness=MAX_TACTICAL_LOSS_FOR_FRESHNESS,
                observed=observed, formation_only=dict(feasible=no_sub_plan is not None, lineup=no_sub_plan, formation=formation,
                explanation='When feasible, substitutions are scored relative to the target formation without a substitution.'),
                player_live=live, unavailable_profile_ids=missing,
                provenance=dict(events=observed.get('source', 'UNSPECIFIED_CALLER_SOURCE'), coordinates='SCHEMATIC_NOT_TRACKING',
                                load='ESTIMATED', role_exposure='HEURISTIC_NOT_CALIBRATED', outcome='HISTORICAL_NOT_COUNTERFACTUAL'),
                explanation_context=dict(owner='deterministic_engine', llm_may_change_decision=False,
                    facts=['coach_config','importance','team_needs','observed','formation_only','selected','alternatives','no_substitution_reason']))
