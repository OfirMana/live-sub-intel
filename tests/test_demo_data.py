import json
from pathlib import Path

import pytest

from subintel.demo_data import load_demo_profiles
from subintel.demo_dataset import DIMS, GENERAL_CAP, RECENT_CAP, bounded_adjustment, build_player, evidence_reliability, observed_rates, positions

ROOT = Path(__file__).resolve().parents[1]


def test_reproducible_and_no_future_leakage():
    evidence = json.loads((ROOT / 'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    anchors = json.loads((ROOT / 'demo_data/fifa16_anchors.json').read_text(encoding='utf-8'))
    actual = {p['player_id']: p for p in load_demo_profiles()['players']}
    assert len(actual) == 36
    assert all(sum(p['team'] == t for p in actual.values()) == 18 for t in ('Liverpool', 'Arsenal'))
    for a in anchors:
        assert build_player(a, evidence) == actual[a['player_id']]
    assert all(r['date'] < evidence['cutoff'] for r in evidence['rows'])
    assert '3754305' not in evidence['match_ids']


def test_ratings_caps_and_goalkeepers():
    for p in load_demo_profiles()['players']:
        assert len(p['recent']['team_match_window']) == 5
        for d in DIMS:
            if p['primary_role'] == 'GK':
                assert p['general']['ratings'][d] is None
                assert p['recent']['ratings'][d] is None
                continue
            g, r = p['general']['ratings'][d], p['recent']['ratings'][d]
            assert 0 <= g <= 100 and 0 <= r <= 100
            assert abs(p['general']['statsbomb_adjustment'][d]) <= GENERAL_CAP * p['general']['reliability'][d] + 1e-9
            assert abs(p['recent']['form_delta'][d]) <= RECENT_CAP * p['recent']['reliability_by_dimension'][d] + 1e-9
            assert abs(r - g) <= RECENT_CAP + .001
        assert p['physical']['physical_is_observed'] is False


@pytest.mark.parametrize('signal', [-1000, -2, 0, 2, 1000])
def test_low_minutes_cannot_create_large_adjustment(signal):
    rel = evidence_reliability(dict(minutes=10, ball_actions=5, aerial_attempts=1))
    assert all(abs(bounded_adjustment(signal, v)) < .07 for v in rel.values())
    assert bounded_adjustment(signal, 0) == 0


def test_pooled_rates_ignore_inactivity():
    from subintel.metrics import COMPONENTS
    def row(minutes, xg, actions, losses):
        return dict.fromkeys((*COMPONENTS, 'aerial_attempts', 'aerial_wins', 'headed_shots'), 0) | dict(minutes=minutes, npxg=xg, ball_actions=actions, ball_losses=losses)
    rows = [row(10, 1, 10, 2), row(90, 0, 90, 9), row(0, 0, 0, 0)]
    rates = observed_rates(rows)
    assert rates['threat'] == pytest.approx(.9)
    assert rates['retention'] == pytest.approx(.89)
    assert observed_rates([rows[-1]]) == dict.fromkeys(DIMS)


def test_minor_position_annotation_does_not_grant_eligibility():
    pos = positions({'player_positions': 'CB'}, [{'positions': {'Right Wing': 3, 'Center Back': 300}}])
    assert pos['primary'] == 'Center Back'
    assert pos['broad_roles'] == ['CB']
    assert 'Right Wing' in pos['all_positions_played']


def test_football_sanity_and_physical_ordering():
    p = {p['name']: p for p in load_demo_profiles()['players']}
    for name, lower in [('Per Mertesacker', 70), ('Laurent Koscielny', 75), ('Mamadou Sakho', 70)]:
        assert p[name]['general']['ratings']['defense'] > lower
        assert p[name]['general']['ratings']['threat'] < 75
    assert p['Mesut Özil']['general']['ratings']['creation'] > 80
    assert p['Olivier Giroud']['general']['ratings']['threat'] > 70
    assert p['Kolo Touré']['primary_role'] == 'CB'
    slow = p['Per Mertesacker']['physical']['tracking']
    for name in ('Theo Walcott', 'Héctor Bellerín'):
        fast = p[name]['physical']['tracking']
        assert fast['max_speed_kmh'] > slow['max_speed_kmh'] + 5
        assert fast['sprint_distance_90'] > slow['sprint_distance_90'] * 2


def test_inactive_players_have_no_form_adjustment():
    for p in load_demo_profiles()['players']:
        if p['recent']['minutes'] == 0:
            assert p['recent']['reliability'] == 0
            assert all(v in (0, None) for v in p['recent']['form_delta'].values())
