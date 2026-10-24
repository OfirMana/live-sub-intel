"""Server-side match facts: parity with the page's JavaScript, cutoffs and unknown values."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from synthetic_coach_room import create_synthetic_room
from subintel.match_facts import checkpoint_elapsed, checkpoint_facts, match_stats_at

ROOT = Path(__file__).resolve().parents[1]
JS = ("const {matchStatsAt}=require(process.argv[1]);let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{"
      "const {fixture,cutoffs}=JSON.parse(s);process.stdout.write(JSON.stringify(cutoffs.map(c=>matchStatsAt(fixture,c))));});")


@pytest.fixture(scope='module')
def fixture():
    return create_synthetic_room(scenario='lively')[0]['fixtures']['synthetic-demo']


def hand_built():
    """Duplicates, missing values, unknown teams, assists and a second yellow."""
    e = lambda i, at, kind, team='h', **kw: dict(id=i, elapsed=at, kind=kind, team_id=team, **kw)
    return dict(home=dict(id='h', name='Home'), away=dict(id='a', name='Away'), first_half_extra=2, events=[
        dict(id='g1', elapsed=10.5, kind='goal', team_id='h')], stat_events=[
        e('p1', 1, 'pass', success=True, player_id='h1', recipient_id='h2'),
        e('p1', 1, 'pass', success=True, player_id='h1', recipient_id='h2'),
        e('c1', 1.2, 'carry', success=True),
        e('p2', 2, 'pass', 'a', success=False, player_id='a1'),
        e('p3', 3, 'pass', 'a', success=None, player_id='a1'),
        e('r1', 4, 'recovery', 'a', success=True),
        e('s1', 5, 'shot', 'a', xg=None, on_target=False),
        e('k1', 10, 'pass', success=True, player_id='h3', recipient_id='h9'),
        e('g1', 10.5, 'goal', xg=0.31, player_id='h9', key_pass_id='k1'),
        e('x1', 11, 'pass', 'neutral', success=True),
        e('y1', 12, 'card', 'a', player_id='a1', card='yellow'),
        e('y2', 13, 'card', 'a', player_id='a1', card='second_yellow'),
        e('d1', 14, 'tackle', success=True)])


def js_stats(data, cutoffs):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    done = subprocess.run([node, '-e', JS, str(ROOT/'web/coach-room/app.js')], input=json.dumps(dict(fixture=data, cutoffs=cutoffs)),
                          capture_output=True, text=True, check=True, timeout=60)
    return json.loads(done.stdout)


def as_js(stats):
    """Python names -> the page's names, so one comparison covers every field."""
    teams = {tid: dict(shots=t['shots'], onTarget=t['on_target'], xg=t['xg'], passes=t['passes'], completed=t['completed'],
                       accuracy=t['accuracy'], possessionProxy=t['possession_proxy'], possessionTime=t['possession_time'])
             for tid, t in stats['teams'].items()}
    p = stats['possession']
    return dict(teams=teams, players=stats['players'], possession=dict(seconds=p['seconds'], percent=p['percent'],
                knownSeconds=p['known_seconds'], unknownSeconds=p['unknown_seconds'], coverage=p['coverage'], maxGapSeconds=p['max_gap_seconds']))


def same(a, b, path='stats'):
    """Exact structure and None-ness; floats within 1e-9."""
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            same(a[k], b[k], f'{path}.{k}')
    elif isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        assert abs(a - b) <= 1e-9, (path, a, b)
    else:
        assert a == b, (path, a, b)


def test_parity_with_the_page_on_the_demo_match(fixture):
    goals = [e['elapsed'] for e in fixture['events'] if e['kind'] == 'goal']
    cutoffs = [0, 0.5, 5, 30, 45, 60, 65, 70, 85, 90, fixture['final_elapsed'], *goals]
    for cutoff, js in zip(cutoffs, js_stats(fixture, cutoffs)):
        same(as_js(match_stats_at(fixture, cutoff)), js, f'cutoff {cutoff}')


def test_parity_on_edge_cases():
    data = hand_built()
    cutoffs = [0, 1, 2.5, 10.5, 10.6, 13.5, 30]
    for cutoff, js in zip(cutoffs, js_stats(data, cutoffs)):
        same(as_js(match_stats_at(data, cutoff)), js, f'cutoff {cutoff}')


def test_unknown_values_stay_unknown():
    data = hand_built()
    empty = match_stats_at(data, 0)
    assert all(t['accuracy'] is None and t['possession_time'] is None for t in empty['teams'].values())
    assert empty['possession']['coverage'] == 0
    early = match_stats_at(data, 3.5)
    assert early['teams']['a']['accuracy'] == 0  # one failed pass; the unknown outcome is still an attempt
    assert early['teams']['a']['passes'] == 2 and early['teams']['h']['passes'] == 1  # duplicate p1 counted once


def test_only_events_strictly_before_the_checkpoint_count():
    data = hand_built()
    at_goal = match_stats_at(data, 10.5)
    assert at_goal['teams']['h']['shots'] == 0 and 'h9' not in at_goal['players']
    after = match_stats_at(data, 10.6)
    assert after['teams']['h']['shots'] == 1 and after['players']['h9']['goals'] == 1 and after['players']['h3']['assists'] == 1
    assert match_stats_at(data, 13.5)['players']['a1'] == dict(goals=0, assists=0, yellows=2, red=True)


def test_checkpoint_facts_follow_the_page_clock(fixture):
    data = hand_built()
    assert checkpoint_elapsed(data, 45) == 45 and checkpoint_elapsed(data, 50) == 52
    facts = checkpoint_facts(fixture, 65, '1')
    assert facts['team']['name'] == 'Arsenal' and facts['opponent']['name'] == 'Liverpool'
    assert (facts['team']['goals'], facts['opponent']['goals']) == (1, 0)
    assert facts['cutoff']['rule'] == 'events strictly before the checkpoint'
    later = checkpoint_facts(fixture, 85, '1')
    assert (later['team']['goals'], later['opponent']['goals']) == (1, 2)
    # Seeking backwards recomputes from the canonical events; nothing leaks from a later checkpoint.
    assert checkpoint_facts(fixture, 65, '1') == facts
    assert checkpoint_facts(fixture, 0, '1')['events_observed'] == 0
    assert checkpoint_facts(fixture, 65, 'unknown') is None and checkpoint_facts(None, 65, '1') is None
