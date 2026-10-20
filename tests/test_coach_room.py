import copy
import json
from pathlib import Path

import pytest

from subintel.coach_room import CoachConfig, CoachReplay, coach_needs, fit_for, recommend_coach, assign_formation, lineup_totals
from subintel.demo_data import load_demo_profiles
from subintel.demo_live import effective_profile

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def replay():
    if not (ROOT/'data/raw/events/3754305.json').exists():
        pytest.skip('Optional pinned historical cache is not downloaded')
    def read(p):
        return json.loads((ROOT/p).read_text(encoding='utf-8'))
    return CoachReplay(load_demo_profiles(), read('demo_data/source_evidence.json'),
        read('data/raw/events/3754305.json'), read('data/raw/lineups/3754305.json'), '3754305', '24')


def test_historical_lineup_has_real_numbers_and_no_future_tactical_shift(replay):
    _, initial = replay.state_at(0)
    _, before = replay.state_at(65)
    ms, after = replay.state_at(70)
    assert initial['initial_formation'] == before['formation'] == '4-3-3'
    assert before['shifts'] == []
    assert after['formation'] == '4-4-2' and after['shifts'][0]['minute'] == 66
    assert all(len(x['lineup']) == 11 and len({p['player_id'] for p in x['lineup']}) == 11 for x in [initial,before,after])
    benteke = next(p for p in after['lineup'] if p['player_id']=='3380')
    assert benteke['number'] == 9 and benteke['role'] == 'ST'
    assert ms.role('3380') == 'ST'
    assert '3380' not in {p['player_id'] for p in before['lineup']}
    assert all(p['number'] is not None for p in initial['lineup'])


def test_coach_intent_changes_needs_at_same_state_without_mutating_history(replay):
    ms, _ = replay.state_at(60)
    original = dict(ms.goals)
    attack = coach_needs(ms, '24', CoachConfig(stance='attack', objective='win'))
    defend = coach_needs(ms, '24', CoachConfig(stance='defend', objective='draw'))
    assert attack.needs['threat'] > defend.needs['threat']
    assert defend.needs['defense'] > attack.needs['defense']
    assert dict(ms.goals) == original
    ms.goals['24'] = ms.goals['1']
    assert coach_needs(ms,'24',CoachConfig(objective='win')).needs['threat'] > coach_needs(ms,'24',CoachConfig(objective='draw')).needs['threat']


def test_freshness_ablation_preserves_tactical_part_and_scales_only_refresh(replay):
    ms, observed = replay.state_at(80)
    before = copy.deepcopy(observed)
    results = [recommend_coach(ms,'24',observed,replay.roster,CoachConfig(freshness_cap=cap)) for cap in (0.,.5,1.,1.5)]
    indexed = [{(o['out_player']['id'],o['in_player']['id']):o for o in r['alternatives']} for r in results]
    assert observed == before
    assert all(set(indexed[0]) == set(m) for m in indexed)
    for key, first in indexed[0].items():
        assert first['score_components']['freshness_benefit'] == 0
        for i, cap in enumerate((0.,.5,1.,1.5)):
            c = indexed[i][key]['score_components']
            assert c['tactical_benefit'] == first['score_components']['tactical_benefit']
            assert c['freshness_benefit'] == pytest.approx(indexed[2][key]['score_components']['freshness_benefit']*cap, abs=2e-5)


@pytest.mark.parametrize('formation', ['4-4-2','4-3-3','4-2-3-1','3-5-2','3-4-3'])
def test_every_formation_candidate_is_complete_unique_and_supported(replay, formation):
    ms, observed = replay.state_at(65)
    r = recommend_coach(ms,'24',observed,replay.roster,CoachConfig(stance='attack', objective='win', formation=formation))
    for c in r['alternatives']:
        lineup = c['proposed_lineup']
        ids = {p['player_id'] for p in lineup}
        assert len(lineup) == len(ids) == 11
        assert c['in_player']['id'] in ids and c['out_player']['id'] not in ids
        assert c['in_player']['id'] not in ms.used
        assert sum(p['role']=='GK' for p in lineup) == 1
        assert all(fit_for(ms.cards[p['player_id']],p['role']) is not None for p in lineup)
        assert c['expected_benefit'] == pytest.approx(c['score_components']['tactical_benefit']+c['score_components']['freshness_benefit'],abs=2e-5)
        assert c['recommended'] == (c['clears_threshold'] and c['quality_gate_passed'])


def test_formation_only_reference_and_no_forced_swap(replay):
    ms, observed = replay.state_at(70)
    r = recommend_coach(ms,'24',observed,replay.roster,CoachConfig(formation='4-4-2'))
    assert r['formation_only']['feasible']
    assert all(c['comparison_reference']=='FORMATION_ONLY_WITHOUT_SUB' for c in r['alternatives'])
    ms.subs_made['24']=3
    no = recommend_coach(ms,'24',observed,replay.roster,CoachConfig(formation='4-4-2'))
    assert no['selected'] is None and not no['alternatives']
    assert no['no_substitution_reason'] == 'NO_SUBSTITUTIONS_LEFT'


def test_coach_payload_has_llm_contract_but_no_llm(replay):
    ms, observed = replay.state_at(65)
    rec = recommend_coach(ms,'24',observed,replay.roster,CoachConfig(stance='attack',objective='win'))
    assert rec['explanation_context']['llm_may_change_decision'] is False
    assert rec['provenance']['coordinates']=='SCHEMATIC_NOT_TRACKING'
    assert rec['coach_config']['objective']=='win'
    assert observed['lineup'] == rec['observed']['lineup']


def test_selecting_the_same_shape_does_not_penalize_unchanged_incumbent_roles(replay):
    ms, observed = replay.state_at(65)
    ratings = {p['player_id']: effective_profile(ms,p['player_id'],True) for p in observed['lineup']}
    assigned = assign_formation(observed['lineup'],observed['formation'],ms.cards,replay.roster,ratings)
    assert assigned is not None
    assert lineup_totals(assigned,ratings) == pytest.approx(lineup_totals(observed['lineup'],ratings))


def test_missing_player_or_red_card_never_fakes_eleven_players(replay):
    ms, observed = replay.state_at(65)
    observed['lineup'] = observed['lineup'][:-1]
    r = recommend_coach(ms,'24',observed,replay.roster,CoachConfig(formation='4-4-2'))
    assert not r['alternatives'] and r['no_substitution_reason']=='UNSUPPORTED_PLAYER_COUNT'
