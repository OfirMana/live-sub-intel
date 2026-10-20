"""Automatic one-substitution + complete XI search, with exact bounded assignment.

All available out/in pairs and supported templates are evaluated. No temporary
position is assigned to the departing player: only the final XI affects utility.
"""
from __future__ import annotations

import math
import time
from collections import Counter
from typing import Literal

from .coach_room import (CoachConfig, DIMS, FORMATIONS, ROLE_EXPOSURE, coach_needs,
                         fit_for, lineup_totals, slot)
from .demo_live import effective_profile, live_performance, MAX_TACTICAL_LOSS_FOR_FRESHNESS
from .engine import RECOMMEND_THRESHOLD
from .statsbomb import ROLE_BY_POSITION

DEFAULT_FRESHNESS_CAP = 1.0
MAX_REFRESH_LOSS_SHARE = .35
ROLE_MOVE_COST = .02
SHAPE_CHANGE_COST = .03


class AutoConfig(CoachConfig):
    objective: Literal['win', 'draw'] = 'win'
    formation: Literal['auto', 'observed', '4-3-3', '4-2-3-1', '4-4-2', '4-1-4-1', '3-5-2', '3-4-3'] = 'auto'
    freshness_cap: Literal[0., .5, 1., 1.5] = DEFAULT_FRESHNESS_CAP


def position_fit(card, position, observed_position=None):
    """Heuristic suitability, never a success probability or team chemistry score."""
    role = ROLE_BY_POSITION[position].value
    if role == 'GK':
        return (1., 'GOALKEEPER') if card['primary_role'] == 'GK' else (0., 'BLOCKED')
    broad = fit_for(card, role)
    if broad is None:
        # Describes an actual incumbent only; cannot introduce this role in a plan.
        return (.7, 'OBSERVED_ONLY') if position == observed_position else (0., 'BLOCKED_ROLE')
    p = card['positions']
    if position == p['primary']:
        return (min(1., broad), 'PRIMARY_POSITION')
    if position in p.get('secondary', []):
        return (min(.85, broad), 'SUPPORTED_SECONDARY')
    if p.get('minutes_by_position', {}).get(position, 0) >= 180:
        return (min(.85, broad), 'OBSERVED_180_MINUTES')
    if position == observed_position:
        return (min(.85, broad), 'OBSERVED_CURRENT_POSITION')
    return (min(.75, broad), 'SUPPORTED_BROAD_ROLE_ONLY')


def _core(delta, gain, loss):
    return sum((gain[i] if v >= 0 else loss[i])*v/20 for i, v in enumerate(delta))


def optimize_assignment(members, positions, cards, roster, ratings, reference, needs,
                        old_positions, formation, observed_formation, evidence_factor=1.,
                        tactical_time=1., freshness_base=0., incoming_id=None, quality_reference=None):
    """Exact branch-and-bound over admissible final-position assignments.

    The upper bound sums independent remaining maxima per dimension, ignores
    uniqueness/costs, and uses the monotonic scoring function. Therefore pruning
    cannot remove a higher-scoring feasible assignment. No beam/time cutoff.
    """
    n = len(positions)
    if len(members) != n or len(set(members)) != n:
        return None, dict(nodes=0, leaves=0, pruned=0)
    gain = [max(needs.needs[d]-.5, 0)*2 for d in DIMS]
    loss = [.5*needs.importance[d] for d in DIMS]
    reference_vec = [reference[d] for d in DIMS]
    candidates = []
    for j, pos in enumerate(positions):
        role = ROLE_BY_POSITION[pos].value
        entries = []
        for i, pid in enumerate(members):
            fit, source = position_fit(cards[pid], pos, old_positions.get(pid))
            if not fit:
                continue
            vector = tuple(ratings[pid][d]*exposure*fit for d,exposure in zip(DIMS,ROLE_EXPOSURE[role]))
            moved = pid in old_positions and old_positions[pid] != pos
            move_cost = ROLE_MOVE_COST if moved else 0.
            fresh = freshness_base*fit if pid == incoming_id else 0.
            value = _core(vector, gain, loss)*evidence_factor*tactical_time + fresh - move_cost*evidence_factor*tactical_time
            entries.append((i,pid,fit,source,vector,move_cost,fresh,value))
        if not entries:
            return None, dict(nodes=0, leaves=0, pruned=0)
        entries.sort(key=lambda e:(-e[-1],e[1]))
        candidates.append((j,pos,entries))
    candidates.sort(key=lambda row:(len(row[2]),row[0]))
    # Safe (possibly loose) upper bound; player reuse in this bound is deliberate.
    tail = [[0.]*5 for _ in range(n+1)]
    for k in range(n-1,-1,-1):
        tail[k] = [tail[k+1][d]+max(e[4][d] for e in candidates[k][2]) for d in range(5)]
    shape_cost = SHAPE_CHANGE_COST if formation != observed_formation else 0.
    best_value = -math.inf
    best = None
    path = []
    stats = dict(nodes=0,leaves=0,pruned=0)
    factor = evidence_factor*tactical_time
    def visit(k, mask, totals, cost, fresh):
        nonlocal best_value, best
        stats['nodes'] += 1
        upper_delta = [totals[d]+tail[k][d]-reference_vec[d] for d in range(5)]
        # Freshness cannot exceed its pre-fit value, and remaining costs >= 0.
        upper = (_core(upper_delta,gain,loss)-cost-shape_cost)*factor + max(fresh,freshness_base)
        if quality_reference is not None:
            tactical_upper=(_core(upper_delta,gain,loss)-cost-shape_cost)*factor
            if tactical_upper < quality_reference-min(MAX_TACTICAL_LOSS_FOR_FRESHNESS,MAX_REFRESH_LOSS_SHARE*freshness_base)-1e-10:
                stats['pruned'] += 1
                return
        if upper < best_value-1e-10:
            stats['pruned'] += 1
            return
        if k == n:
            stats['leaves'] += 1
            delta = [totals[d]-reference_vec[d] for d in range(5)]
            tactical = (_core(delta,gain,loss)-cost-shape_cost)*factor
            if quality_reference is not None and tactical-quality_reference < -min(MAX_TACTICAL_LOSS_FOR_FRESHNESS,MAX_REFRESH_LOSS_SHARE*fresh)-1e-10:
                return
            value = tactical+fresh
            # Prefer fewer changes on score ties, never an arbitrary busy plan.
            tie = (cost,tuple(e[1] for _,_,e in path))
            if value > best_value+1e-10 or (abs(value-best_value)<=1e-10 and (best is None or tie<best['tie'])):
                best_value=value
                best=dict(path=list(path),tactical=tactical,freshness=fresh,raw_benefit=value,
                          core=_core(delta,gain,loss),disruption=cost+shape_cost,
                          delta=dict(zip(DIMS,delta)),tie=tie)
            return
        j,pos,entries=candidates[k]
        for entry in entries:
            i,pid,fit,source,vector,move_cost,fresh_value,_=entry
            if mask & (1<<i):
                continue
            path.append((j,pos,entry))
            visit(k+1,mask|(1<<i),[totals[d]+vector[d] for d in range(5)],cost+move_cost,fresh+fresh_value)
            path.pop()
    visit(0,0,[0.]*5,0.,0.)
    if best is None:
        return None,stats
    best['lineup']=[dict(slot(pos,e[1],roster),fit=e[2],fit_source=e[3]) for _,pos,e in sorted(best.pop('path'))]
    best.pop('tie')
    return best,stats


def recommend_auto(ms, tid, observed, roster, config:AutoConfig):
    started=time.perf_counter()
    state=ms.game_state(tid)
    needs=coach_needs(ms,tid,config)
    cards=ms.cards
    available=sorted(pid for pid,p in ms.players.items() if p.team_id==tid and pid in cards)
    ratings={pid:effective_profile(ms,pid,pid in ms.on_pitch) for pid in available}
    active=observed['lineup']
    missing=[p['player_id'] for p in active if p['player_id'] not in ratings]
    current=[]
    for p in active:
        fit,source=position_fit(cards[p['player_id']],p['position'],p['position']) if p['player_id'] in cards else (0.,'MISSING_CARD')
        current.append(dict(p,fit=fit,fit_source=source))
    old_positions={p['player_id']:p['position'] for p in active}
    reference=lineup_totals(current,ratings) if not missing else dict.fromkeys(DIMS,0.)
    keepers=[p for p in current if p['role']=='GK']
    field=[p['player_id'] for p in active if p['role']!='GK']
    live={p['player_id']:live_performance(ms,p['player_id']) for p in active if p['player_id'] in ratings}
    shapes=[(observed['formation'],[p['position'] for p in active if p['role']!='GK'])]
    if config.formation=='auto':
        shapes += [(f,positions) for f,positions in FORMATIONS.items() if positions!=shapes[0][1]]
    elif config.formation!='observed':
        shapes=[(config.formation,FORMATIONS[config.formation])]
    horizon=max(94-state.minute,0)/90
    fresh_horizon=min(max(94-state.minute,0)/30,1)
    stats=Counter(pairs_considered=0,formation_trials=0,feasible_plans=0,nodes=0,leaves=0,pruned=0)
    no_sub_plans=[]
    valid=not missing and len(current)==11 and len(keepers)==1 and len(set(field))==10
    baseline=0.
    def plan_for(members,formation,positions,out_id=None,in_id=None):
        stats['formation_trials']+=1
        rel=min(sum(cards[in_id]['general']['reliability'].values())/6,sum(cards[out_id]['general']['reliability'].values())/6) if in_id else 1.
        evidence=.5+.5*rel if in_id else 1.
        quality=min(1.,sum(ratings[in_id][d] for d in ('threat','progression','defense'))/max(sum(ratings[out_id][d] for d in ('threat','progression','defense')),1)) if in_id else 0.
        raw_refresh=config.freshness_cap*live[out_id]['fatigue']*quality if out_id else 0.
        result, counts=optimize_assignment(members,positions,cards,roster,ratings,reference,needs,old_positions,
            formation,observed['formation'],evidence,horizon,evidence*raw_refresh*fresh_horizon,in_id,
            baseline if in_id else None)
        stats.update(counts)
        if result is None and in_id:
            # Retain the best rejected plan for inspection. An unsafe numerical
            # optimum never hides a lower-scoring assignment that passes safety.
            result, counts=optimize_assignment(members,positions,cards,roster,ratings,reference,needs,old_positions,
                formation,observed['formation'],evidence,horizon,evidence*raw_refresh*fresh_horizon,in_id)
            stats.update(counts)
        if result is None:
            return None
        stats['feasible_plans']+=1
        lineup=[dict(keepers[0])]+result['lineup']
        moved=[dict(player_id=p['player_id'],name=p['name'],before=next(o['role'] for o in active if o['player_id']==p['player_id']),
               after=p['role'],before_position=old_positions[p['player_id']],after_position=p['position'])
               for p in lineup if p['player_id'] in old_positions and p['position']!=old_positions[p['player_id']]]
        incoming=next((p for p in lineup if p['player_id']==in_id),None)
        return dict(plan_kind='SUBSTITUTION' if in_id else 'FORMATION_ONLY',
            out_player=dict(id=out_id,name=roster[out_id]['name']) if out_id else None,
            in_player=dict(id=in_id,name=roster[in_id]['name']) if in_id else None,
            formation=formation,proposed_lineup=lineup,repositioned=moved,
            change_type='FORMATION_CHANGE' if formation!=observed['formation'] else 'REPOSITIONING' if moved else 'LIKE_FOR_LIKE',
            raw_plan_benefit=result['raw_benefit'],raw_tactical_benefit=result['tactical'],
            position_fit=incoming['fit'] if incoming else None,evidence_strength=rel,
            expected_changes={d:round(ratings[in_id][d]-ratings[out_id][d],3) for d in DIMS} if in_id else dict.fromkeys(DIMS,0.),
            lineup_changes={d:round(v,4) for d,v in result['delta'].items()},
            score_components=dict(tactical_core=result['core'],tactical_support=-result['disruption'],
                evidence_multiplier=evidence,remaining_time_multiplier=horizon,freshness_time_multiplier=fresh_horizon,
                freshness_relief=raw_refresh,outgoing_fatigue=live[out_id]['fatigue'] if out_id else 0.,
                freshness_benefit=result['freshness'],tactical_benefit=result['tactical']))
    if valid and 20<=state.minute<94:
        for formation,positions in shapes:
            plan=plan_for(field,formation,positions)
            if plan is not None:
                no_sub_plans.append(plan)
    # Waiting in the actual XI always remains an alternative with utility zero.
    best_no_sub=max(no_sub_plans,key=lambda p:p['raw_plan_benefit'],default=None)
    baseline=max(0.,best_no_sub['raw_plan_benefit'] if best_no_sub else 0.)
    all_plans=[]
    if valid and state.subs_left>0 and 20<=state.minute<94:
        bench=[pid for pid in available if pid not in ms.used and cards[pid]['primary_role']!='GK']
        for out_id in field:
            for in_id in bench:
                stats['pairs_considered']+=1
                members=[in_id if pid==out_id else pid for pid in field]
                for formation,positions in shapes:
                    plan=plan_for(members,formation,positions,out_id,in_id)
                    if plan is None:
                        continue
                    x=plan['score_components']
                    incremental_tactical=plan['raw_tactical_benefit']-baseline
                    allowed_loss=min(MAX_TACTICAL_LOSS_FOR_FRESHNESS,MAX_REFRESH_LOSS_SHARE*x['freshness_benefit'])
                    plan.update(expected_benefit=round(plan['raw_plan_benefit']-baseline,5),
                        comparison_reference='BEST_NO_SUBSTITUTION_ACTION',reference_benefit=baseline,
                        quality_gate_passed=incremental_tactical>=-allowed_loss-1e-10,
                        clears_threshold=plan['raw_plan_benefit']-baseline>=RECOMMEND_THRESHOLD,
                        decision_basis='FRESH_LEGS' if x['freshness_benefit']>max(incremental_tactical,0) else 'TACTICAL',
                        score=round(plan['raw_plan_benefit'],5),allowed_tactical_loss=allowed_loss)
                    x['tactical_benefit']=incremental_tactical
                    plan['recommended']=plan['quality_gate_passed'] and plan['clears_threshold']
                    plan['reason_codes']=['AUTOMATIC_XI_SEARCH','COACH_GOAL_'+config.objective.upper(),plan['change_type']]
                    all_plans.append(plan)
    # Keep the best safe and best numerical plan per pair, so a failed quality
    # gate in one formation cannot hide a valid alternative for that same pair.
    by_pair={}
    for p in all_plans:
        key=(p['out_player']['id'],p['in_player']['id'])
        by_pair.setdefault(key,[]).append(p)
    alternatives=[]
    for plans in by_pair.values():
        eligible=[p for p in plans if p['recommended']]
        best=max(eligible or plans,key=lambda p:p['expected_benefit'])
        best['formation_variants']=[dict(formation=p['formation'],benefit=p['expected_benefit'],recommended=p['recommended']) for p in sorted(plans,key=lambda p:-p['expected_benefit'])]
        alternatives.append(best)
    alternatives.sort(key=lambda p:(-p['expected_benefit'],p['out_player']['id'],p['in_player']['id']))
    selected=next((p for p in alternatives if p['recommended']),None)
    adjustment=best_no_sub if best_no_sub and baseline>=RECOMMEND_THRESHOLD else None
    if adjustment:
        adjustment.update(expected_benefit=round(baseline,5),recommended=True,decision_basis='TACTICAL',
            comparison_reference='CURRENT_OBSERVED_XI',quality_gate_passed=True,clears_threshold=True)
    decision='SUBSTITUTION' if selected else 'TACTICAL_ADJUSTMENT' if adjustment else 'NO_SUBSTITUTION'
    reason=None if selected else 'FORMATION_ONLY_SUFFICIENT' if adjustment else 'OUTSIDE_DECISION_WINDOW' if state.minute<20 else 'MISSING_PLAYER_PROFILES' if missing else 'UNSUPPORTED_PLAYER_COUNT' if not valid else 'NO_SUBSTITUTIONS_LEFT' if state.subs_left<=0 else 'NO_FEASIBLE_PLAN' if not alternatives else 'QUALITY_LOSS_TOO_LARGE' if any(p['clears_threshold'] for p in alternatives) else 'BELOW_THRESHOLD'
    stats['elapsed_ms']=round((time.perf_counter()-started)*1000,2)
    return dict(version='coach-room-v2',match_id=ms.match_id,team_id=tid,minute=state.minute,state=state.model_dump(),
        coach_config=config.model_dump(),recommendation=decision,selected=selected,selected_plan=selected or adjustment,
        no_substitution_reason=reason,alternatives=alternatives,threshold=RECOMMEND_THRESHOLD,
        max_tactical_loss_for_freshness=MAX_TACTICAL_LOSS_FOR_FRESHNESS,refresh_loss_share=MAX_REFRESH_LOSS_SHARE,
        team_needs={d:round(v,4) for d,v in needs.needs.items()},importance=needs.importance,performance_deficit_z=needs.deficit_z,
        observed=dict(observed,lineup=current),formation_only=dict(feasible=valid,lineup=best_no_sub['proposed_lineup'] if best_no_sub else current,
            formation=best_no_sub['formation'] if best_no_sub else observed['formation'],benefit=baseline),
        best_no_substitution=best_no_sub,search=dict(stats),player_live=live,unavailable_profile_ids=missing,
        provenance=dict(events=observed.get('source','UNSPECIFIED'),coordinates='SCHEMATIC_NOT_TRACKING',
                        position_fit='HEURISTIC_FROM_PROFILE_EVIDENCE',role_exposure='HEURISTIC_NOT_CALIBRATED',load='ESTIMATED'),
        explanation_context=dict(owner='deterministic_engine',llm_may_change_decision=False,
            facts=['coach_config','selected_plan','search','best_no_substitution','reference_benefit','score_components','proposed_lineup','repositioned']))
