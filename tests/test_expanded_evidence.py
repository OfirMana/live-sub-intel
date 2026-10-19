"""Source reconciliation, timing and behavioral checks for the expanded model."""
import copy
import json
from collections import defaultdict
from pathlib import Path

import pytest

from subintel.demo_data import load_demo_profiles
from subintel.demo_dataset import aggregate, observed_rates
from subintel.demo_live import TEAM_IDS, make_match, recommend_demo
from subintel.schema import Event, EventType
from benchmark_demo import replay

ROOT = Path(__file__).resolve().parents[1]


def evidence():
    return json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))


def test_source_goal_assist_and_completion_reconciliation():
    # Independent raw-event totals, not a comparison against the extractor itself.
    e = evidence()
    raw_root = ROOT/'data/raw'
    if not all((raw_root/f'events/{mid}.json').exists() for mid in e['match_ids']):
        pytest.skip('Optional pinned raw cache not (fully) downloaded')
    counts = defaultdict(lambda: defaultdict(int))
    for mid in e['match_ids']:
        for event in json.loads((raw_root/f'events/{mid}.json').read_text(encoding='utf-8')):
            pid = str(event.get('player', {}).get('id', ''))
            kind = event['type']['name']
            if kind == 'Shot' and event['shot']['outcome']['name'] == 'Goal':
                counts[pid]['goals'] += 1
                key = 'penalty_goals' if event['shot'].get('type', {}).get('name') == 'Penalty' else 'non_penalty_goals'
                counts[pid][key] += 1
            if kind == 'Pass':
                counts[pid]['assists'] += bool(event['pass'].get('goal_assist'))
                counts[pid]['pass_attempts'] += 1
                counts[pid]['passes_completed'] += 'outcome' not in event['pass']
            if kind == 'Dribble':
                counts[pid]['dribble_attempts'] += 1
                counts[pid]['dribbles_completed'] += event['dribble']['outcome']['name'] == 'Complete'
    for p in load_demo_profiles()['players']:
        totals = p['season']['totals']
        for key in ('goals','non_penalty_goals','penalty_goals','assists','pass_attempts','passes_completed','dribble_attempts','dribbles_completed'):
            assert totals[key] == counts[str(p['player_id'])][key], (p['name'], key)


def test_outcomes_and_completed_dribbles_change_correct_signals():
    base = dict(minutes=900, ball_actions=100, ball_losses=10, pass_attempts=100, passes_completed=90)
    before = observed_rates([base])
    after = observed_rates([base | dict(non_penalty_goals=5, assists=4, dribbles_completed=20)])
    assert after['threat'] > before['threat']
    assert after['creation'] > before['creation']
    assert after['progression'] > before['progression']
    # Penalties are visible but do not masquerade as open-play scoring ability.
    assert observed_rates([base | dict(goals=5, penalty_goals=5)]) == before
    assert observed_rates([base | dict(passes_completed=95)])['retention'] > before['retention']


def test_match_contains_only_selected_teams_and_source_ids():
    e, data = evidence(), load_demo_profiles()
    ms = make_match(data, e, teams=('Chelsea','Tottenham Hotspur'))
    assert set(ms.team_ids) == {'33','38'}
    assert len(ms.on_pitch) == 22
    for row in e['rows']:
        if row['team'] in TEAM_IDS:
            assert TEAM_IDS[row['team']] == row['team_id']


def controlled_candidate(minute, loss):
    data, e = copy.deepcopy(load_demo_profiles()), evidence()
    liverpool = [p for p in data['players'] if p['team'] == 'Liverpool' and p['primary_role'] != 'GK']
    out = next(p for p in liverpool if p['matchday_status'] == 'Starter')
    bench = next(p for p in liverpool if p['matchday_status'] == 'Bench')
    for p in liverpool:
        p['recent']['ratings'] = dict.fromkeys(p['recent']['ratings'], 75.)
        p['general']['reliability'] = dict.fromkeys(p['general']['reliability'], 1.)
        p['physical']['stamina'] = 75
    bench['recent']['ratings'] = dict.fromkeys(bench['recent']['ratings'], 75.-loss)
    bench['positions']['eligibility'] = {out['primary_role']: 1.}
    bench['positions']['suitability'] = {out['primary_role']: 1.}
    ms = make_match(data, e)
    out_id, in_id = str(out['player_id']), str(bench['player_id'])
    # Flat live evidence and team needs isolate the physical trade-off.
    import subintel.demo_live as live
    from unittest.mock import patch
    from subintel.schema import TeamNeeds
    ms.feed(Event(event_id='clock',match_id=ms.match_id,period=2,minute=minute,second=0,team_id='24',type=EventType.PERIOD_END))
    dims = ('threat','creation','progression','retention','defense')
    flat = TeamNeeds(team_id='24', needs=dict.fromkeys(dims,.5), deficit_z=dict.fromkeys(dims,0), importance=dict.fromkeys(dims,1))
    with patch.object(live,'team_needs',return_value=flat), patch.object(live,'effective_profile',side_effect=lambda state,pid,on: state.cards[pid]['recent']['ratings']):
        options = recommend_demo(ms,'24',top=1000)['alternatives']
    return next(c for c in options if c['out_player']['id']==out_id and c['in_player']['id']==in_id)


def test_freshness_does_not_carry_a_moderate_ability_loss():
    # Under the 1.5 freshness cap this late swap cleared the threshold on freshness alone;
    # a tactically harmful change is now never recommended (see recommend_demo).
    assert controlled_candidate(30, 3)['expected_benefit'] < .15
    assert controlled_candidate(75, 3)['score_components']['tactical_benefit'] < 0
    assert controlled_candidate(75, 25)['expected_benefit'] < .15
    equal = controlled_candidate(75, 0)
    assert equal['score_components']['tactical_benefit'] == 0
    assert equal['decision_basis'] == 'FRESH_LEGS'


def test_five_minute_replay_boundaries_and_legal_recommendations():
    if not (ROOT/'data/raw/events/3754305.json').exists():
        pytest.skip('Optional raw benchmark cache not downloaded')
    data, e = load_demo_profiles(), evidence()
    report = replay('3754305','24',data,e)
    assert [s['minute'] for s in report['snapshots']] == list(range(5,91,5))
    assert len(report['snapshots']) == 18
    assert all(s['state']['subs_left'] >= 0 for s in report['snapshots'])
    for s in report['snapshots']:
        if s['selected']:
            assert s['selected']['expected_benefit'] >= s['threshold']
