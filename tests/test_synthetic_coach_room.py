"""Synthetic actions must share the planner/explanation contract without raw downloads."""
from unittest.mock import patch

import pytest

from integrated_app import IntegratedApp, ExplainRequest
from synthetic_coach_room import create_synthetic_room, MATCH_ID
from subintel.auto_plans import AutoConfig


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
