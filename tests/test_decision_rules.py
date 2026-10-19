"""Decision rules: urgency in team needs, the freshness gate and chasing formation changes."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import subintel.demo_live as live
from subintel.demo_data import load_demo_profiles
from subintel.demo_live import CHASING_FORMATION_FIT, make_match, recommend_demo, swap_fit
from subintel.engine import importance, team_needs
from subintel.schema import Event, EventType, GameState, TeamNeeds

ROOT = Path(__file__).resolve().parents[1]
DIMS = ('threat', 'creation', 'progression', 'retention', 'defense')


def evidence():
    return json.loads((ROOT / 'demo_data/source_evidence.json').read_text(encoding='utf-8'))


def tick(ms, minute):
    ms.feed(Event(event_id=f'tick-{minute}', match_id=ms.match_id, period=2, minute=minute, second=0,
                  team_id='24', type=EventType.PERIOD_END))


def test_trailing_team_attacking_above_its_norm_still_needs_threat():
    ms = make_match(load_demo_profiles(), evidence())
    tick(ms, 80)
    for c in ('npxg', 'box_presence'):
        ms.window['24'][c] += 20  # far more than Liverpool usually produce
    ms.goals['1'] = 1
    w = importance(ms.game_state('24'))['threat']
    assert w > 1
    # The surplus cannot cancel the urgency: need = sigmoid(2 ln w) = w^2 / (1 + w^2).
    assert team_needs(ms, '24').needs['threat'] == pytest.approx(w ** 2 / (1 + w ** 2), abs=1e-3)
    ms.goals['1'] = 0
    assert team_needs(ms, '24').needs['threat'] < .5  # level score: the surplus lowers the need


def gated_recommendation(loss):
    """Liverpool at 70' with flat needs and a freshness term large enough to clear the threshold."""
    data = copy.deepcopy(load_demo_profiles())
    liverpool = [p for p in data['players'] if p['team'] == 'Liverpool' and p['primary_role'] != 'GK']
    out = next(p for p in liverpool if p['matchday_status'] == 'Starter')
    bench = next(p for p in liverpool if p['matchday_status'] == 'Bench')
    for p in liverpool:
        p['recent']['ratings'] = dict.fromkeys(p['recent']['ratings'], 75.)
        p['general']['reliability'] = dict.fromkeys(p['general']['reliability'], 1.)
    bench['recent']['ratings'] = dict.fromkeys(bench['recent']['ratings'], 75. - loss)
    for p in liverpool:
        if p is not bench and p['matchday_status'] == 'Bench':
            p['positions']['eligibility'] = {}
    bench['positions']['eligibility'] = {out['primary_role']: 1.}
    bench['positions']['suitability'] = {out['primary_role']: 1.}
    ms = make_match(data, evidence())
    tick(ms, 70)
    flat = TeamNeeds(team_id='24', needs=dict.fromkeys(DIMS, .5), deficit_z=dict.fromkeys(DIMS, 0),
                     importance=dict.fromkeys(DIMS, 1))
    with patch.object(live, 'team_needs', return_value=flat), \
            patch.object(live, 'effective_profile', side_effect=lambda state, pid, on: state.cards[pid]['recent']['ratings']), \
            patch.object(live, 'refresh_value', return_value=3.0):
        return recommend_demo(ms, '24', top=1000), str(out['player_id']), str(bench['player_id'])


def test_freshness_never_justifies_a_tactically_harmful_change():
    rec, out_id, in_id = gated_recommendation(loss=3)
    option = next(o for o in rec['alternatives'] if o['out_player']['id'] == out_id and o['in_player']['id'] == in_id)
    assert option['expected_benefit'] >= rec['threshold']
    assert option['score_components']['tactical_benefit'] < 0
    assert rec['selected'] is None
    assert rec['no_substitution_reason'] == 'ONLY_TACTICALLY_HARMFUL_OPTIONS_CLEAR_THRESHOLD'


def test_fresh_legs_for_an_equal_player_is_recommended_and_labelled():
    rec, out_id, in_id = gated_recommendation(loss=0)
    assert rec['selected']['in_player']['id'] == in_id
    assert rec['selected']['decision_basis'] == 'FRESH_LEGS'
    assert rec['no_substitution_reason'] is None


def card(role):
    return {'primary_role': role, 'positions': {'eligibility': {role: 1.}, 'suitability': {role: 1.}}}


@pytest.mark.parametrize('minute,diff,out_role,allowed', [
    (65, -1, 'CM', True),    # Klopp's Milner -> Benteke
    (55, -1, 'CM', False),   # too early
    (80, 0, 'CM', False),    # not trailing
    (80, 1, 'CB', False),
    (70, -1, 'CB', False),   # defenders only from 75'
    (76, -1, 'CB', True),
    (85, -2, 'GK', False),
])
def test_formation_change_only_when_trailing_and_late_enough(minute, diff, out_role, allowed):
    result = swap_fit(GameState(minute=minute, goal_diff=diff, subs_left=3), out_role, card('ST'))
    assert (result == (CHASING_FORMATION_FIT, 'FORMATION_CHANGE')) if allowed else result is None


def test_like_for_like_is_unchanged():
    assert swap_fit(GameState(minute=30, goal_diff=0, subs_left=3), 'ST', card('ST')) == (1., 'LIKE_FOR_LIKE')


def test_no_substitution_reason_when_all_subs_used():
    ms = make_match(load_demo_profiles(), evidence())
    tick(ms, 70)
    ms.subs_made['24'] = 3
    rec = recommend_demo(ms, '24')
    assert rec['selected'] is None and rec['no_substitution_reason'] == 'NO_SUBSTITUTIONS_LEFT'
