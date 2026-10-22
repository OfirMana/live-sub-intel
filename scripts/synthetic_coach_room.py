"""Original synthetic events through the same automatic planner and explanation API.

Historical player/roster priors are disclosed separately from generated actions.
Inspection never executes a recommendation or rewrites subsequent events.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from run_synthetic_demo import simulate, DEFAULT_SEED, GENERATOR_VERSION
from subintel.auto_plans import AutoConfig, position_fit, recommend_auto
from subintel.coach_room import FORMATIONS, POSITIONS
from subintel.demo_data import load_demo_profiles
from subintel.demo_live import make_match
from subintel.schema import Event, EventType, Role

ROOT = Path(__file__).resolve().parents[1]
MATCH_ID = 'synthetic-demo'


def create_synthetic_room(seed=DEFAULT_SEED):
    dataset = load_demo_profiles()
    evidence = json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    metadata = json.loads((ROOT/'demo_data/synthetic_roster.json').read_text(encoding='utf-8'))
    roster, teams = metadata['roster'], metadata['teams']
    raw, _ = simulate(dataset, evidence, apply_substitutions=False, collect_snapshots=False, seed=seed)
    events = tuple(Event.model_validate(e) for e in raw)
    key_events = []
    for e in events:
        if e.type not in (EventType.CARD, EventType.SHOT, EventType.PRESSURE, EventType.TACKLE, EventType.RECOVERY, EventType.PERIOD_START, EventType.PERIOD_END):
            continue
        key_events.append(dict(id=e.event_id, kind='goal' if e.goal else e.type.value,
            period=e.period, minute=e.minute, second=e.second, elapsed=e.minute+e.second/60,
            team_id=e.team_id, player_id=e.player_id, player=roster.get(e.player_id,{}).get('name'),
            replacement=None, replacement_id=None, card=e.card, xg=e.xg,
            source='SYNTHETIC_SCRIPTED_POSSESSIONS'))
    key_events.append(dict(id='synthetic-full-time',kind='period_end',period=2,minute=91,
        second=0,elapsed=91,team_id='24',player_id=None,player=None,replacement=None,xg=None))
    fixture = dict(id=MATCH_ID, date='Synthetic scenario', first_half_extra=0,
        home=dict(id='24',name='Liverpool'), away=dict(id='1',name='Arsenal'),
        stat_events=[dict(id=e.event_id,kind='goal' if e.goal else e.type.value,elapsed=e.minute+e.second/60,team_id=e.team_id,player_id=e.player_id,success=e.success,recipient_id=e.recipient_id,key_pass_id=e.key_pass_id,xg=e.xg,on_target=e.on_target,card=e.card) for e in events],
        events=key_events, final_elapsed=91.001, source='SYNTHETIC_SCRIPTED_POSSESSIONS')
    views = [dict(team=t['name'],team_id=tid,match_id=MATCH_ID,
        lineup_timeline=[dict(elapsed=0,formation=t['formation'],lineup=t['lineup'])])
        for tid,t in teams.items()]
    bootstrap = dict(fixtures={MATCH_ID:fixture},views=views,formations=list(FORMATIONS),
        profiles={str(p['player_id']):dict(p,position_suitability={pos:dict(zip(('fit','source'),position_fit(p,pos))) for pos in POSITIONS}) for p in dataset['players']},
        version='coach-room-synthetic-v2',data_mode='synthetic',
        generator=dict(version=GENERATOR_VERSION,seed=seed,scenario='authored-goal-phases-not-outcome-validation'),
        provenance=dict(events='SYNTHETIC_SCRIPTED_POSSESSIONS',
            player_profiles='HISTORICAL_PRIORS_WITH_DISCLOSED_ESTIMATES',
            lineup='HISTORICAL_STARTING_XI_METADATA',execution='INSPECTION_ONLY'))

    @lru_cache(maxsize=64)
    def evaluate(mid,tid,minute,config_json):
        if mid != MATCH_ID or tid not in teams or minute not in range(0,91,5):
            raise ValueError('Unknown synthetic checkpoint')
        ms = make_match(dataset,evidence,MATCH_ID)
        for t in teams.values():
            for p in t['lineup']:
                ms.players[p['player_id']].role=Role(p['role'])
        for e in events:
            if e.minute >= minute:
                break
            ms.feed(e)
        if minute:
            ms.feed(Event(event_id=f'synthetic-checkpoint-{minute}',match_id=MATCH_ID,
                period=1 if minute<=45 else 2,minute=minute,second=0,team_id=tid,type=EventType.PERIOD_END))
        t=teams[tid]
        observed=dict(formation=t['formation'],initial_formation=t['formation'],
            lineup=deepcopy(t['lineup']),shifts=[],source='SYNTHETIC_SCRIPTED_POSSESSIONS',
            lineup_source='HISTORICAL_STARTING_XI_METADATA',coordinate_source='SCHEMATIC_NOT_TRACKING')
        result=recommend_auto(ms,tid,observed,roster,AutoConfig.model_validate_json(config_json))
        result['provenance']['lineup']='HISTORICAL_STARTING_XI_METADATA'
        result['provenance']['generator']=dict(version=GENERATOR_VERSION,seed=seed)
        return result
    return bootstrap,evaluate
