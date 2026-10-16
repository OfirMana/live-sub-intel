"""Deterministic FIFA-anchored demo cards; event rates are evidence, not ability."""
from __future__ import annotations

import math
from collections import defaultdict

from .metrics import COMPONENTS
from .physical import PHYSICAL_REFERENCE_BY_ROLE
from .statsbomb import ROLE_BY_POSITION

DIMS = ('threat', 'creation', 'progression', 'retention', 'defense', 'aerial')
GENERAL_CAP = 6.0
RECENT_CAP = 6.0
POSITION_MINUTES = 180.0
POSITION_SHARE = 0.15
FIFA_POSITION = {'GK': 'Goalkeeper', 'CB': 'Center Back', 'LB': 'Left Back',
                 'RB': 'Right Back', 'LWB': 'Left Wing Back', 'RWB': 'Right Wing Back',
                 'CDM': 'Center Defensive Midfield', 'CM': 'Center Midfield',
                 'CAM': 'Center Attacking Midfield', 'LM': 'Left Midfield',
                 'RM': 'Right Midfield', 'LW': 'Left Wing', 'RW': 'Right Wing',
                 'CF': 'Secondary Striker', 'ST': 'Center Forward'}
WEIGHTS = {
    'threat': {'attacking_finishing': .4, 'mentality_positioning': .3, 'power_shot_power': .15, 'power_long_shots': .15},
    'creation': {'mentality_vision': .35, 'attacking_short_passing': .3, 'attacking_crossing': .15, 'skill_curve': .1, 'skill_long_passing': .1},
    'progression': {'skill_dribbling': .25, 'skill_ball_control': .25, 'attacking_short_passing': .2, 'skill_long_passing': .15, 'movement_acceleration': .15},
    'retention': {'skill_ball_control': .35, 'skill_dribbling': .2, 'attacking_short_passing': .3, 'movement_balance': .1, 'power_strength': .05},
    'defense': {'mentality_interceptions': .25, 'defending_marking': .25, 'defending_standing_tackle': .25, 'defending_sliding_tackle': .15, 'power_strength': .1},
    'aerial': {'attacking_heading_accuracy': .4, 'power_jumping': .25, 'power_strength': .2, 'height_rating': .15},
}


def clamp(value, lo=0, hi=100):
    return max(lo, min(hi, value))


def bounded_adjustment(signal, reliability, cap=GENERAL_CAP):
    return cap * clamp(reliability, 0, 1) * math.tanh(signal / 2)


def fifa_prior(fifa):
    if 'GK' in fifa['player_positions'].split(', '):
        return {d: None for d in DIMS}
    f = dict(fifa, height_rating=clamp((fifa['height_cm'] - 150) * 2))
    category = {'threat': 'shooting', 'creation': 'passing', 'progression': 'dribbling',
                'retention': 'dribbling', 'defense': 'defending', 'aerial': 'physic'}
    return {d: sum(w * (f[k] if f.get(k) is not None else f[category[d]]) for k, w in weights.items())
            for d, weights in WEIGHTS.items()}


def aggregate(rows):
    return {k: sum(r.get(k, 0) for r in rows) for k in (*COMPONENTS, 'aerial_attempts', 'aerial_wins', 'headed_shots', 'minutes')}


def observed_rates(rows):
    totals = aggregate(rows)
    mins = totals['minutes']
    if not mins:
        return {d: None for d in DIMS}
    rate = lambda c: totals[c] * 90 / mins
    return dict(threat=rate('npxg') + .05 * rate('box_presence'),
                creation=rate('xa') + .1 * rate('box_passes'),
                progression=rate('prog_passes') + rate('prog_carries'),
                retention=1 - totals['ball_losses'] / totals['ball_actions'] if totals['ball_actions'] else None,
                defense=rate('pressures') + rate('def_actions'),
                aerial=totals['aerial_wins'] / totals['aerial_attempts'] if totals['aerial_attempts'] else None)


def evidence_reliability(totals, recent=False):
    minutes = totals['minutes']
    # Both exposure and opportunities constrain noisy rates. No minutes means no delta.
    base = minutes / (minutes + (180 if recent else 900))
    return {d: min(base, totals['ball_actions'] / (totals['ball_actions'] + 100)) if d == 'retention'
            else min(base, totals['aerial_attempts'] / (totals['aerial_attempts'] + 20)) if d == 'aerial'
            else base for d in DIMS}


def positions(fifa, rows):
    static = [FIFA_POSITION[p.strip()] for p in fifa['player_positions'].split(',')]
    historical = defaultdict(float)
    for row in rows:
        for p, m in row['positions'].items():
            historical[p] += m
    total = sum(historical.values())
    meaningful = [p for p, m in historical.items() if m >= POSITION_MINUTES and m / max(total, 1) >= POSITION_SHARE]
    eligible = sorted({ROLE_BY_POSITION[p].value for p in static + meaningful})
    primary_role = ROLE_BY_POSITION[static[0]].value
    # Most-used meaningful exact position within the static primary role, otherwise static fallback.
    within = [p for p in meaningful if ROLE_BY_POSITION[p].value == primary_role]
    primary = max(within, key=historical.get) if within else static[0]
    secondary = sorted(set(static + meaningful) - {primary})
    return dict(primary=primary, secondary=secondary, primary_role=primary_role,
                broad_roles=eligible, eligibility={r: 1.0 for r in eligible},
                suitability={r: 1.0 if r == primary_role else .85 for r in eligible},
                all_positions_played=sorted(historical), minutes_by_position={p: round(m, 3) for p, m in sorted(historical.items())},
                evidence={p: 'FIFA16_POSITION' if p in static else 'OBSERVED_STATSBOMB_MEANINGFUL_MINUTES' for p in sorted(set(static + meaningful))})


def physical(fifa, role):
    source = 'SYNTHETIC:FIFA16+SkillCorner-role-reference'
    base = dict(height_cm=fifa['height_cm'], preferred_foot=fifa['preferred_foot'],
                pace=fifa.get('pace'), stamina=fifa['power_stamina'], strength=fifa['power_strength'],
                physical_source=source, physical_is_observed=False)
    if role == 'GK':
        # No goalkeeper tracking reference exists in this release: do not invent it.
        return dict(base, tracking=None, tracking_status='UNSUPPORTED_GK_REFERENCE')
    ref = PHYSICAL_REFERENCE_BY_ROLE[role]
    speed = fifa['movement_sprint_speed']
    acceleration = fifa['movement_acceleration']
    stamina = fifa['power_stamina']
    pace_factor = clamp(1 + (speed - 70) / 70, .5, 1.45)
    intensity = clamp(1 + (stamina - 70) / 150, .75, 1.2)
    tracking = dict(max_speed_kmh=round(clamp(24 + .12 * speed, 25, 36), 2),
                    meters_per_minute=round(ref['meters_per_minute'] * intensity, 2),
                    hsr_distance_90=round(ref['hsr_distance_90'] * pace_factor * intensity, 2),
                    hsr_count_90=round(ref['hsr_count_90'] * pace_factor * intensity, 2),
                    sprint_distance_90=round(ref['sprint_distance_90'] * pace_factor ** 1.5, 2),
                    sprint_count_90=round(ref['sprint_count_90'] * pace_factor ** 1.5, 2),
                    high_accel_90=round(ref['high_accel_90'] * clamp(1 + (acceleration - 70) / 80, .5, 1.4), 2),
                    high_decel_90=round(ref['high_decel_90'] * clamp(1 + (acceleration - 70) / 80, .5, 1.4), 2))
    return dict(base, tracking=tracking)


def build_player(anchor, evidence):
    pid = str(anchor['player_id'])
    fifa = anchor['fifa']
    rows = [r for r in evidence['rows'] if r['player_id'] == pid]
    recent_rows = [r for r in rows if r['team'] == anchor['team'] and r['match_id'] in evidence['team_windows'][anchor['team']]]
    pos = positions(fifa, rows)
    prior = fifa_prior(fifa)
    rates, totals = observed_rates(rows), aggregate(rows)
    recent_rates, recent_totals = observed_rates(recent_rows), aggregate(recent_rows)
    rel = evidence_reliability(totals)
    recent_rel = evidence_reliability(recent_totals, recent=True)
    calibration = evidence['role_calibration'].get(pos['primary_role'], {})
    adjustment, delta = {}, {}
    for d in DIMS:
        cal = calibration.get(d)
        signal = (rates[d] - cal['mean']) / cal['std'] if cal and rates[d] is not None else 0
        adjustment[d] = bounded_adjustment(signal, rel[d]) if prior[d] is not None else None
        signal_recent = (recent_rates[d] - rates[d]) / cal['std'] if cal and recent_rates[d] is not None and rates[d] is not None else 0
        delta[d] = bounded_adjustment(signal_recent, recent_rel[d], RECENT_CAP) if prior[d] is not None else None
    general = {d: round(clamp(prior[d] + adjustment[d]), 3) if prior[d] is not None else None for d in DIMS}
    recent = {d: round(clamp(general[d] + delta[d]), 3) if general[d] is not None else None for d in DIMS}
    return dict(player_id=anchor['player_id'], name=anchor['name'], team=anchor['team'],
                matchday_status=anchor['matchday_status'], primary_role=pos['primary_role'], positions=pos,
                identity=dict(height_cm=fifa['height_cm'], preferred_foot=fifa['preferred_foot'], source=fifa['source_status']),
                fifa16=fifa,
                general=dict(ratings=general, fifa_prior=prior, statsbomb_adjustment=adjustment,
                             reliability=rel, minutes=round(totals['minutes'], 3), observed_rates=rates),
                recent=dict(ratings=recent, form_delta=delta, reliability=round(sum(recent_rel.values()) / len(DIMS), 4),
                            reliability_by_dimension=recent_rel, minutes=round(recent_totals['minutes'], 3),
                            appearances=sum(r['minutes'] > 0 for r in recent_rows), starts=sum(r['started'] for r in recent_rows),
                            appearance_rate=sum(r['minutes'] > 0 for r in recent_rows) / 5,
                            team_match_window=evidence['team_windows'][anchor['team']], observed_rates=recent_rates, totals=recent_totals),
                physical=physical(fifa, pos['primary_role']),
                provenance=dict(general='SYNTHETIC:FIFA16 prior + capped observed StatsBomb signal',
                                recent='ESTIMATED:bounded change from observed last five team matches',
                                events='OBSERVED:StatsBomb Open Data; strictly before 2016-01-13',
                                fifa=fifa['source_status'], physical='SYNTHETIC',
                                goalkeeper_outfield_dimensions='UNSUPPORTED' if pos['primary_role'] == 'GK' else 'SUPPORTED'))
