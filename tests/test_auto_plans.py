import itertools
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from subintel.auto_plans import (AutoConfig, DEFAULT_FRESHNESS_CAP, MAX_REFRESH_LOSS_SHARE,
    position_fit, optimize_assignment, recommend_auto, _core)
from subintel.coach_room import CoachReplay, DIMS, ROLE_EXPOSURE, lineup_totals
from subintel.demo_data import load_demo_profiles
from subintel.schema import TeamNeeds

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def replay():
    from collect_demo_evidence import fetch  # downloads the pinned file when data/raw is absent (CI)
    evidence=json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    return CoachReplay(load_demo_profiles(),evidence,
        fetch('events/3754305.json'),fetch('lineups/3754305.json'),'3754305','24')


def test_position_matrix_blocks_kane_at_center_back_and_does_not_invent_lamela_striker():
    cards=load_demo_profiles()['players']
    kane=next(p for p in cards if str(p['player_id'])=='10955')
    lamela=next(p for p in cards if str(p['player_id'])=='3585')
    assert position_fit(kane,'Center Forward')[0]==1
    assert position_fit(kane,'Center Back')[0]==0
    assert position_fit(lamela,'Center Forward')[0]==0  # .017 observed minutes is not ST eligibility
    assert 0<position_fit(lamela,'Center Attacking Midfield')[0]<1


@pytest.mark.parametrize('quality_reference',[None,.01,.15])
@pytest.mark.parametrize('risk',[.75,1.])
def test_exact_solver_matches_exhaustive_small_assignment(quality_reference,risk):
    positions=['Right Center Midfield','Center Midfield','Left Center Midfield']
    ids=['a','b','c']
    cards={pid:dict(primary_role='CM',positions=dict(primary=pos,secondary=[p for p in positions if p!=pos],eligibility={'CM':1},suitability={'CM':1})) for pid,pos in zip(ids,positions)}
    ratings={pid:dict(zip(DIMS,values)) for pid,values in zip(ids,[(90,60,70,75,50),(65,85,80,60,90),(70,80,65,80,75)])}
    roster={pid:dict(name=pid,number=i) for i,pid in enumerate(ids)}
    needs=TeamNeeds(team_id='x',needs=dict(zip(DIMS,[.8,.6,.55,.4,.75])),importance=dict.fromkeys(DIMS,1),deficit_z=dict.fromkeys(DIMS,0))
    old=dict(zip(ids,positions));reference=dict.fromkeys(DIMS,200.)
    gain=[max(needs.needs[d]-.5,0)*2 for d in DIMS];loss=[.5*(risk if d in ('retention','defense') else 1.) for d in DIMS]
    brute=[]
    for perm in itertools.permutations(ids):
        totals=dict.fromkeys(DIMS,0.);fresh=0.;cost=0.
        for pos,pid in zip(positions,perm):
            fit,_=position_fit(cards[pid],pos,old[pid])
            for d,w in zip(DIMS,ROLE_EXPOSURE['CM']):totals[d]+=ratings[pid][d]*w*fit
            if pos!=old[pid]:cost+=.02
            if pid=='c':fresh=.2*fit
        tactical=_core([totals[d]-reference[d] for d in DIMS],gain,loss)-cost
        if quality_reference is None or tactical-quality_reference>=-min(.1,.35*fresh)-1e-10:
            brute.append(tactical+fresh)
    result,stats=optimize_assignment(ids,positions,cards,roster,ratings,reference,needs,old,
        'same','same',freshness_base=.2,incoming_id='c',quality_reference=quality_reference,defensive_downside_multiplier=risk)
    if brute:
        assert result['raw_benefit']==pytest.approx(max(brute))
    else:
        assert result is None
    assert stats['nodes']>0


def test_every_available_pair_and_template_is_considered_with_complete_safe_xis(replay):
    ms,observed=replay.state_at(65)
    rec=recommend_auto(ms,'24',observed,replay.roster,AutoConfig(stance='attack'))
    bench=[pid for pid,p in ms.players.items() if p.team_id=='24' and pid in ms.cards and pid not in ms.used and ms.cards[pid]['primary_role']!='GK']
    assert rec['search']['pairs_considered']==10*len(bench)
    assert rec['search']['formation_trials']>rec['search']['pairs_considered']*6
    assert rec['coach_config']['formation']=='auto'
    for c in rec['alternatives']:
        ids=[p['player_id'] for p in c['proposed_lineup']]
        assert len(ids)==len(set(ids))==11
        assert c['out_player']['id'] not in ids and c['in_player']['id'] in ids
        assert c['in_player']['id'] not in ms.used
        assert all(p['fit']>0 for p in c['proposed_lineup'])
        assert c['expected_benefit']==pytest.approx(c['score_components']['tactical_benefit']+c['score_components']['freshness_benefit'],abs=1e-5)
        if c['recommended']:
            assert c['score_components']['tactical_benefit']>=-min(.1,MAX_REFRESH_LOSS_SHARE*c['score_components']['freshness_benefit'])-1e-9
    # A striker can replace a winger when an incumbent can take the wing.
    chain=next(c for c in rec['alternatives'] if c['out_player']['id']=='3635' and c['in_player']['id']=='3380')
    assert any(p['player_id']=='3535' and p['role']=='AM_W' for p in chain['proposed_lineup'])
    assert any(p['player_id']=='3535' for p in chain['repositioned'])


def test_no_substitution_actions_are_competitors_and_search_does_not_mutate_state(replay):
    ms,observed=replay.state_at(70)
    before=json.dumps(observed,sort_keys=True)
    rec=recommend_auto(ms,'24',observed,replay.roster,AutoConfig(stance='attack'))
    assert json.dumps(observed,sort_keys=True)==before
    baseline=rec['formation_only']['benefit']
    for c in rec['alternatives']:
        assert c['comparison_reference']=='BEST_NO_SUBSTITUTION_ACTION'
        assert c['expected_benefit']==pytest.approx(c['raw_plan_benefit']-baseline,abs=1e-5)
    ms.subs_made['24']=3
    no=recommend_auto(ms,'24',observed,replay.roster,AutoConfig(stance='attack'))
    assert no['selected'] is None and not no['alternatives']
    assert no['recommendation'] in ('TACTICAL_ADJUSTMENT','NO_SUBSTITUTION')


def test_default_freshness_policy_is_fixed_and_can_accept_small_but_not_large_quality_loss(replay):
    assert DEFAULT_FRESHNESS_CAP==AutoConfig().freshness_cap==1.
    ms,observed=replay.state_at(75)
    # The policy itself caps both absolute loss and fraction bought by freshness.
    rec=recommend_auto(ms,'24',observed,replay.roster,AutoConfig())
    for c in rec['alternatives']:
        fresh=c['score_components']['freshness_benefit']
        assert c['allowed_tactical_loss']==pytest.approx(min(.1,.35*fresh))
    with pytest.raises(ValueError): AutoConfig(objective='limit_damage')


def test_zero_freshness_never_recommends_negative_incremental_tactics(replay):
    ms,observed=replay.state_at(80)
    rec=recommend_auto(ms,'24',observed,replay.roster,AutoConfig(freshness_cap=0.))
    assert all(c['score_components']['freshness_benefit']==0 for c in rec['alternatives'])
    assert all(c['score_components']['tactical_benefit']>=-1e-10 for c in rec['alternatives'] if c['recommended'])


def test_late_win_policy_is_contextual_bounded_and_still_expires():
    from subintel.auto_plans import late_game_weights
    from subintel.schema import GameState
    def policy(m,diff=0,objective='win',enabled=True):
        return late_game_weights(GameState(minute=m,goal_diff=diff,subs_left=3),AutoConfig(objective=objective),enabled)
    for p in [policy(65),policy(90,1),policy(90,0,'draw'),policy(90,0,enabled=False)]:
        assert p['urgency']==0
        assert p['tactical_time']==p['baseline_tactical_time']
        assert p['defensive_downside_multiplier']==1
    p80,p90=policy(80),policy(90,-1)
    assert p80['urgency']<p90['urgency']==1
    assert p90['baseline_tactical_time']<p90['tactical_time']<=3*p90['baseline_tactical_time']
    assert p90['defensive_downside_multiplier']==.75
    assert policy(94)['tactical_time']==0


def test_late_win_policy_does_not_force_changes_or_bypass_the_no_sub_reference(replay):
    ms,observed=replay.state_at(90)
    r=recommend_auto(ms,'24',observed,replay.roster,AutoConfig(stance='attack'))
    assert r['late_game_policy']['active']
    for p in r['alternatives']:
        assert p['expected_benefit']==pytest.approx(p['raw_plan_benefit']-r['formation_only']['benefit'],abs=1e-5)
        if p['recommended']:
            assert p['quality_gate_passed'] and p['clears_threshold']
            assert p['score_components']['tactical_benefit']>=-p['allowed_tactical_loss']-1e-9
    ms.subs_made['24']=3
    exhausted=recommend_auto(ms,'24',observed,replay.roster,AutoConfig(stance='attack'))
    assert exhausted['selected'] is None and not exhausted['alternatives']
