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


def scenario(out_ratings, in_ratings, minute, fatigue):
    """Liverpool, level score, flat needs: one starter, one eligible bench player, fixed fatigue."""
    data = copy.deepcopy(load_demo_profiles())
    liverpool = [p for p in data['players'] if p['team'] == 'Liverpool' and p['primary_role'] != 'GK']
    out = next(p for p in liverpool if p['matchday_status'] == 'Starter')
    bench = next(p for p in liverpool if p['matchday_status'] == 'Bench')
    for p in liverpool:
        p['recent']['ratings'] = dict.fromkeys(p['recent']['ratings'], 75.)
        p['general']['reliability'] = dict.fromkeys(p['general']['reliability'], 1.)
        if p['matchday_status'] == 'Bench':
            p['positions']['eligibility'] = {}
    out['recent']['ratings'].update(out_ratings)
    bench['recent']['ratings'].update(in_ratings)
    bench['positions']['eligibility'] = {out['primary_role']: 1.}
    bench['positions']['suitability'] = {out['primary_role']: 1.}
    ms = make_match(data, evidence())
    tick(ms, minute)
    flat = TeamNeeds(team_id='24', needs=dict.fromkeys(DIMS, .5), deficit_z=dict.fromkeys(DIMS, 0),
                     importance=dict.fromkeys(DIMS, 1))
    with patch.object(live, 'team_needs', return_value=flat), \
            patch.object(live, 'effective_profile', side_effect=lambda state, pid, on: state.cards[pid]['recent']['ratings']), \
            patch.object(live, 'live_performance', side_effect=lambda state, pid: {'player_id': pid, 'fatigue': fatigue}):
        rec = recommend_demo(ms, '24', top=1000)
    option = next(o for o in rec['alternatives'] if o['out_player']['id'] == str(out['player_id'])
                  and o['in_player']['id'] == str(bench['player_id']))
    return rec, option


STAR = dict(threat=92., creation=90., progression=93., retention=88., defense=35.)
GOOD_SUB = dict(threat=80., creation=80., progression=82., retention=80., defense=40.)


def test_a_tired_star_is_not_taken_off_for_a_clearly_weaker_player():
    rec, option = scenario(STAR, GOOD_SUB, minute=75, fatigue=1.)
    assert option['expected_benefit'] >= rec['threshold']  # freshness alone would clear it
    assert option['score_components']['tactical_benefit'] < -live.MAX_TACTICAL_LOSS_FOR_FRESHNESS
    assert rec['selected'] is None
    assert rec['no_substitution_reason'] == 'QUALITY_LOSS_TOO_LARGE'


def test_fresh_legs_can_bring_on_a_slightly_weaker_player_late():
    rec, option = scenario({}, dict.fromkeys(DIMS, 72.), minute=75, fatigue=1.)
    assert option['score_components']['tactical_benefit'] < 0  # the substitute is weaker...
    # ...and still recommended (another tired starter in the same role may tie for the slot).
    assert rec['selected']['in_player'] == option['in_player']
    assert rec['selected']['score_components']['tactical_benefit'] < 0
    assert rec['selected']['decision_basis'] == 'FRESH_LEGS'


def test_the_same_weaker_player_costs_too_much_early():
    rec, option = scenario({}, dict.fromkeys(DIMS, 72.), minute=40, fatigue=1.)
    assert option['score_components']['tactical_benefit'] < -live.MAX_TACTICAL_LOSS_FOR_FRESHNESS
    assert rec['selected'] is None


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
