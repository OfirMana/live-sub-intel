"""Synthetic actions must share the planner/explanation contract without raw downloads."""
from unittest.mock import patch

import pytest

from integrated_app import IntegratedApp, ExplainRequest
from synthetic_coach_room import create_synthetic_room, MATCH_ID
from subintel.auto_plans import AutoConfig
from run_synthetic_demo import simulate, DEFAULT_SEED
from subintel.demo_data import load_demo_profiles
import json
from pathlib import Path


@pytest.fixture(scope='module')
def room():
    with patch('collect_demo_evidence.fetch',side_effect=AssertionError('Synthetic mode must work offline')):
        return create_synthetic_room()


def test_synthetic_fixture_provenance_and_goal_boundaries(room):
    b,e=room
    assert b['data_mode']=='synthetic'
    assert len(b['views'])==2
    assert all(x['source']=='SYNTHETIC_SCRIPTED_POSSESSIONS' for x in b['fixtures'][MATCH_ID]['events'] if x['kind']=='goal')
    for minute,diff in [(50,0),(55,-1),(80,0),(85,1)]:
        r=e(MATCH_ID,'24',minute,AutoConfig().model_dump_json())
        assert r['state']['goal_diff']==diff
        assert r['provenance']['events']=='SYNTHETIC_SCRIPTED_POSSESSIONS'
        assert r['provenance']['lineup']=='HISTORICAL_STARTING_XI_METADATA'
    with pytest.raises(ValueError):e('3754305','24',65,AutoConfig().model_dump_json())
    with pytest.raises(ValueError):e(MATCH_ID,'38',65,AutoConfig().model_dump_json())


def test_synthetic_plans_use_same_selected_alternative_and_bilingual_explanation(room,monkeypatch):
    for name in ('FOUNDRY_ENDPOINT','FOUNDRY_API_KEY','FOUNDRY_DEPLOYMENT'):
        monkeypatch.delenv(name,raising=False)
    app=IntegratedApp(*room)
    req=ExplainRequest(match_id=MATCH_ID,team_id='24',minute=65,config=AutoConfig(stance='attack'),plan_id='wait')
    r=app.snapshot(req)
    second=r['alternatives'][1]
    for p in r['alternatives']:
        assert len({x['player_id'] for x in p['proposed_lineup']})==11
        assert p['out_player']['id'] not in {x['player_id'] for x in p['proposed_lineup']}
        assert all(x['fit']>0 for x in p['proposed_lineup'])
    for lang in ('en','he'):
        explanation=app.explanation(req.model_copy(update=dict(plan_id=second['plan_id'],lang=lang)))
        assert explanation['plan_id']==second['plan_id']
        assert second['in_player']['name'] in explanation['text']
        assert explanation['facts']['provenance']['events']=='SYNTHETIC_SCRIPTED_POSSESSIONS'
    # Inspecting a suggestion does not change the scenario's lineup or use a sub.
    after=app.snapshot(req)
    assert after['state']['subs_left']==3
    assert after['observed']['lineup']==r['observed']['lineup']
    assert after['selected_plan_id']==r['selected_plan_id']


def test_seeded_generator_is_repeatable_varied_and_chronological():
    evidence=json.loads((Path(__file__).resolve().parents[1]/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    def generate(seed):
        return simulate(load_demo_profiles(),evidence,apply_substitutions=False,collect_snapshots=False,seed=seed)[0]
    raw=generate(DEFAULT_SEED)
    assert raw==generate(DEFAULT_SEED)
    assert raw!=generate(DEFAULT_SEED+1)
    assert [(e['minute'],e['second']) for e in raw]==sorted((e['minute'],e['second']) for e in raw)
    shots=[e for e in raw if e['type']=='shot']
    assert len({e['player_id'] for e in shots})>=4
    assert len({e['xg'] for e in shots})>=5
    assert len({e['second'] for e in shots})>=5
    assert all(0<e['xg']<1 for e in shots)
    assert not any(e['type']=='substitution' for e in raw)


def test_visible_actions_and_seed_provenance_and_no_future_leakage(room):
    bootstrap,evaluate=room
    fixture=bootstrap['fixtures'][MATCH_ID]
    assert {'pressure','tackle','recovery'} <= {e['kind'] for e in fixture['events']}
    assert bootstrap['generator']['seed']==DEFAULT_SEED
    r=evaluate(MATCH_ID,'24',65,AutoConfig().model_dump_json())
    # Alter the generated future, then rebuild: no effect on an earlier decision.
    original=simulate
    def changed_future(*args,**kwargs):
        raw,snapshots=original(*args,**kwargs)
        for e in raw:
            if e['minute']>=65 and e['type']=='shot':e.update(goal=True,xg=.99)
        return raw,snapshots
    with patch('synthetic_coach_room.simulate',side_effect=changed_future):
        _,other=create_synthetic_room()
        altered=other(MATCH_ID,'24',65,AutoConfig().model_dump_json())
    assert altered['state']==r['state']
    assert altered['team_needs']==r['team_needs']
    assert altered['selected']==r['selected']
    assert altered['alternatives']==r['alternatives']


def test_match_stat_stream_preserves_pass_links_cards_and_visible_goal_totals(room):
    bootstrap,_=room
    fixture=bootstrap['fixtures'][MATCH_ID]
    stats=fixture['stat_events']
    assert len({e['id'] for e in stats})==len(stats)
    passes={e['id']:e for e in stats if e['kind']=='pass'}
    goals=[e for e in stats if e['kind']=='goal']
    assert len(goals)==3
    for goal in goals:
        assist=passes[goal['key_pass_id']]
        assert assist['elapsed']<goal['elapsed']
        assert assist['team_id']==goal['team_id']
        assert assist['recipient_id']==goal['player_id']
        assert assist['player_id']!=goal['player_id']
        assert assist['success'] is True
    cards=[e for e in stats if e['kind']=='card']
    assert len(cards)==2 and all(e['card']=='yellow' for e in cards)
    assert {e['id'] for e in goals}=={e['id'] for e in fixture['events'] if e['kind']=='goal'}


def test_both_teams_have_failed_passes_and_turnovers_end_each_generated_attack(room):
    bootstrap,_=room
    events=bootstrap['fixtures'][MATCH_ID]['stat_events']
    for tid in ('24','1'):
        passes=[e for e in events if e['kind']=='pass' and e['team_id']==tid and e['elapsed']<65]
        rate=sum(e['success'] is True for e in passes)/len(passes)
        assert .7<rate<.98  # scenario QA, not a claim of statistical calibration
    groups={}
    evidence=json.loads((Path(__file__).resolve().parents[1]/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    raw,_=simulate(load_demo_profiles(),evidence,apply_substitutions=False,collect_snapshots=False)
    for i,e in enumerate(raw[:-1]):
        if e['type']=='pass' and e['success'] is False:
            after=raw[i+1]
            assert after['type']=='recovery'
            assert after['team_id']!=e['team_id']
            assert after['minute']==e['minute'] and after['second']==e['second']+1
