import json
from pathlib import Path

import pytest

from subintel.demo_data import load_demo_profiles
from subintel.demo_live import effective_profile, live_performance, make_match, recommend_demo, swap_fit
from subintel.engine import _role_cost, importance, substitution_score, team_needs
from subintel.schema import Event, EventType, GameState, TeamNeeds
from subintel.statsbomb import convert_event
from run_synthetic_demo import simulate


@pytest.fixture
def inputs():
    root = Path(__file__).resolve().parents[1]
    return load_demo_profiles(), json.loads((root / 'demo_data/source_evidence.json').read_text(encoding='utf-8'))


def tick(ms, minute, **kw):
    ms.feed(Event(event_id=f'tick-{minute}', match_id=ms.match_id, period=1, minute=minute, second=0,
                  team_id='24', type=EventType.PERIOD_END, **kw))


def test_state_changes_importance_gradually():
    def state(minute, diff):
        return GameState(minute=minute, goal_diff=diff, subs_left=3)
    assert importance(state(87, -1))['threat'] > importance(state(20, -1))['threat'] > 1
    assert importance(state(87, 1))['defense'] > 1
    assert importance(state(87, 1))['retention'] > 1
    assert importance(state(87, 1))['threat'] < 1


@pytest.mark.parametrize('pair', [('CB', 'ST'), ('CM', 'ST'), ('FB', 'ST'), ('CB', 'AM_W'), ('CM', 'AM_W')])
def test_legacy_engine_disables_unsupported_formation_changes(pair):
    assert _role_cost(*pair, GameState(minute=88, goal_diff=-2, subs_left=3)) is None


def test_window_decay_and_cumulative_separation(inputs):
    ms = make_match(*inputs)
    pid = next(p for p in ms.on_pitch if ms.role(p) == 'ST' and ms.players[p].team_id == '24')
    ms.feed(Event(event_id='shot', match_id=ms.match_id, period=1, minute=10, second=0,
                  team_id='24', player_id=pid, type=EventType.SHOT, xg=.4))
    tick(ms, 22)
    assert ms.live[pid]['npxg'] == .4
    assert ms.player_window[pid]['npxg'] == pytest.approx(.2)
    live = live_performance(ms, pid)
    assert all(v is None or -1 <= v <= 1 for v in live['dimensions'].values())
    assert 0 <= live['fatigue'] <= 1


def test_opponent_threat_increases_defense_need(inputs):
    ms = make_match(*inputs)
    tick(ms, 40)
    before = team_needs(ms, '24').needs['defense']
    ms.window['1']['npxg'] += 2
    assert team_needs(ms, '24').needs['defense'] > before
    before = team_needs(ms, '24').needs['defense']
    ms.window['24']['def_actions'] += 100
    assert team_needs(ms, '24').needs['defense'] == before


def test_no_sub_early_exhausted_and_unknown_aerial(inputs):
    ms = make_match(*inputs)
    tick(ms, 10)
    assert recommend_demo(ms, '24')['recommendation'] == 'NO_SUBSTITUTION'
    tick(ms, 70)
    ms.subs_made['24'] = 3
    assert recommend_demo(ms, '24')['alternatives'] == []
    pid = next(p for p in ms.on_pitch if ms.role(p) != 'GK')
    assert live_performance(ms, pid)['dimensions']['aerial'] is None


def test_fresh_bench_and_bounded_live_correction(inputs):
    ms = make_match(*inputs)
    tick(ms, 80)
    for pid, p in ms.cards.items():
        if p['primary_role'] == 'GK':
            continue
        effective = effective_profile(ms, pid, pid in ms.on_pitch)
        assert all(abs(effective[d] - p['recent']['ratings'][d]) <= 7 for d in effective)
        if pid not in ms.used:
            assert effective == p['recent']['ratings']


def test_specialist_beats_generic_allrounder_for_dominant_need():
    dims = ('threat', 'creation', 'progression', 'retention', 'defense')
    needs = TeamNeeds(team_id='24', needs={d: .95 if d == 'creation' else .5 for d in dims},
                      deficit_z=dict.fromkeys(dims, 0), importance=dict.fromkeys(dims, 1))
    assert substitution_score(needs, dict.fromkeys(dims, .2) | {'creation': 1}) > substitution_score(needs, dict.fromkeys(dims, .3))


def test_synthetic_demo_repeatable_and_all_swaps_eligible(inputs):
    first = simulate(*inputs)
    assert first == simulate(*inputs)
    events, snapshots = first
    cards = {str(p['player_id']): p for p in inputs[0]['players']}
    assert len(events) > 1500
    assert any(e['type'] == 'substitution' for e in events)
    assert {r['recommendation'] for r in snapshots} == {'SUBSTITUTION', 'NO_SUBSTITUTION'}
    ms = make_match(*inputs)
    for e in events:
        ev = Event(**e)
        if ev.type == EventType.SUBSTITUTION:
            assert ev.player_id in ms.on_pitch
            assert ev.replacement_id not in ms.used
            assert swap_fit(ms.game_state(ev.team_id), ms.role(ev.player_id), cards[ev.replacement_id]) is not None
        elif ev.player_id:
            assert ev.player_id in ms.on_pitch
        ms.feed(ev)
    assert ms.goals['24'] == 2 and ms.goals['1'] == 1
    assert all(r['event_source'].startswith('SYNTHETIC') for r in snapshots)


def test_aerial_adapter_preserves_outfield_metrics():
    raw = dict(id='a', period=1, minute=10, second=0, team={'id': 24}, player={'id': 3380},
               type={'name': 'Duel'}, duel={'type': {'name': 'Aerial Lost'}})
    event = convert_event(raw, 'm')
    assert event.type == EventType.AERIAL and event.aerial_contest and event.aerial_won is False
