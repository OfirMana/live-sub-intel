"""The viewer must reveal the same past-only state as the model, including added time."""
import json
from pathlib import Path

import pytest

from export_match_replay import build_payload, key_events

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def payload():
    if not (ROOT/'data/raw/events/3754065.json').exists():
        pytest.skip('Optional pinned raw cache is not downloaded')
    return build_payload()


def test_viewer_covers_same_matchweek_and_all_legal_candidates(payload):
    assert len(payload['fixtures'])==3
    assert len(payload['views'])==4
    assert {f['matchweek'] for f in payload['fixtures'].values()}=={21}
    assert all(len(v['snapshots'])==18 for v in payload['views'])
    assert any(len(s['alternatives'])>3 for v in payload['views'] for s in v['snapshots'])


def test_events_and_checkpoints_show_identical_scores_without_future_goals(payload):
    for view in payload['views']:
        fixture=payload['fixtures'][view['match_id']]
        opponent=fixture['away']['id'] if fixture['home']['id']==view['team_id'] else fixture['home']['id']
        for s in view['snapshots']:
            for c in s['alternatives']:
                active_role=fixture['active_roles'][c['out_player']['id']]
                assert active_role in payload['profiles'][c['in_player']['id']]['positions']['eligibility']
            elapsed=s['minute']+(fixture['first_half_extra'] if s['minute']>45 else 0)
            score={fixture['home']['id']:0,fixture['away']['id']:0}
            for e in fixture['events']:
                if e['elapsed']<elapsed and e['kind'] in ('goal','own_goal'):
                    score[e['team_id']]+=1
            assert score[view['team_id']]-score[opponent]==s['state']['goal_diff']
        raw=json.loads((ROOT/f'data/raw/events/{view["match_id"]}.json').read_text(encoding='utf-8'))
        for period in (1,2):
            assert sum(e['kind']=='period_start' and e['period']==period for e in fixture['events'])==1
            assert sum(e['kind']=='period_end' and e['period']==period for e in fixture['events'])==1
        # End-stage must include added-time substitutions and the last whistle.
        assert all(e['elapsed']<fixture['final_elapsed'] for e in fixture['events'])
        actual_goals=[e for e in raw if e['type']['name']=='Shot' and e['shot']['outcome']['name']=='Goal']
        assert len([e for e in fixture['events'] if e['kind']=='goal'])==len(actual_goals)
