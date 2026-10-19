import copy

import pytest

from subintel.demo_live import REFRESH_HORIZON_MINUTES, estimated_match_load, refresh_value
from subintel.engine import substitution_score
from subintel.schema import TeamNeeds

RATES = {'pressures': 15, 'prog_carries': 4}


def load(minutes, stamina=75, pressures=0, carries=0):
    return estimated_match_load(minutes, stamina, pressures, carries, RATES, 115)


def test_load_is_delayed_monotone_and_stamina_sensitive():
    values = [load(m)['fatigue'] for m in (0, 20, 40, 60, 75, 90)]
    assert values == sorted(values)
    assert values[:3] == [0, 0, 0]
    assert load(80, stamina=55)['fatigue'] > load(80, stamina=90)['fatigue']
    assert load(80, pressures=40, carries=15)['fatigue'] > load(80)['fatigue']
    assert load(80)['intensity'] == 1  # no on-ball evidence cannot imply no running
    assert load(80)['distance_is_observed'] is False


def test_freshness_can_justify_like_for_like_change_with_flat_tactical_needs():
    dims = ('threat', 'creation', 'progression', 'retention', 'defense')
    needs = TeamNeeds(team_id='A', needs=dict.fromkeys(dims, .5),
                      deficit_z=dict.fromkeys(dims, 0), importance=dict.fromkeys(dims, 1))
    equal = dict.fromkeys(dims, 75)
    tactical = substitution_score(needs, dict.fromkeys(dims, 0))
    assert tactical == 0
    tired = load(72, stamina=45, pressures=30, carries=12)['fatigue']
    remaining = 94 - 72
    assert tactical * remaining / 90 + refresh_value(tired, equal, equal) * min(remaining / REFRESH_HORIZON_MINUTES, 1) > .15
    assert refresh_value(load(20)['fatigue'], equal, equal) == 0


def test_freshness_does_not_hide_large_ability_loss():
    dims = ('threat', 'creation', 'progression', 'retention', 'defense')
    needs = TeamNeeds(team_id='A', needs=dict.fromkeys(dims, .5),
                      deficit_z=dict.fromkeys(dims, 0), importance=dict.fromkeys(dims, 1))
    outgoing = dict.fromkeys(dims, 85)
    incoming = dict.fromkeys(dims, 55)
    tactical = substitution_score(needs, {d: (incoming[d]-outgoing[d])/20 for d in dims})
    assert tactical + refresh_value(1, incoming, outgoing) < 0


@pytest.mark.parametrize('minutes,stamina', [(0,0), (90,100), (130,0), (45,70)])
def test_load_bounds(minutes, stamina):
    result = load(minutes, stamina, pressures=100, carries=100)
    assert 0 <= result['fatigue'] <= 1
    assert 1 <= result['intensity'] <= 1.25
