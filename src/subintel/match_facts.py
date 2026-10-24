"""Match-to-date statistics at a checkpoint, computed on the server for explanations.

Mirrors matchStatsAt/possessionAt in web/coach-room/app.js line for line, so the
numbers an explanation quotes are the numbers the page shows (tests/test_match_facts.py
checks parity against the browser code). Only events strictly before the checkpoint
count; unknown values stay None instead of being invented.
"""
import hashlib
import json
import math

FACTS_VERSION = 'match-facts-v1'
CONTROL_GAP_SECONDS = 30
RESET_KINDS = ('period_start', 'period_end', 'goal', 'own_goal', 'shot', 'card', 'miscontrol', 'dispossessed')
CONTROL_KINDS = ('carry', 'dribble', 'recovery', 'interception', 'tackle')
DEFINITIONS = {
    'xg': 'Sum of synthetic xG on shots and goals before the checkpoint.',
    'shots': 'Shots and goals before the checkpoint.',
    'on_target': 'Shots marked on target, plus goals.',
    'pass_accuracy': 'Completed passes / attempted passes, in percent; unknown when no pass was attempted.',
    'possession': 'Share of known control time: a successful pass, carry, dribble, recovery, interception or tackle '
                  'starts control; it expires after 30 seconds without a control event and stops at shots, cards, '
                  'goals, period breaks, miscontrols, dispossessions and failed passes. Unknown when no control time is known.',
}


def checkpoint_elapsed(fixture, minute):
    """The page's timeline position for a checkpoint minute (first-half added time shifts the second half)."""
    return minute + (fixture.get('first_half_extra', 0) if minute > 45 else 0)


def _number(value):
    """JavaScript Number(value)||0."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0.
    return 0. if math.isnan(n) else n


def possession_at(fixture, elapsed):
    seconds = {fixture['home']['id']: 0., fixture['away']['id']: 0.}
    limit = max(0, elapsed*60)
    seen = set()
    owner, last, last_control = None, 0., 0.

    def accrue(to):
        nonlocal last
        if owner:
            seconds[owner] += max(0, min(to, last_control + CONTROL_GAP_SECONDS) - last)
        last = to

    for e in fixture.get('stat_events') or []:
        at = e['elapsed']*60
        if at >= limit:
            break
        if e['id'] in seen:
            continue
        seen.add(e['id'])
        accrue(at)
        if e['kind'] in RESET_KINDS or (e['kind'] == 'pass' and e.get('success') is False):
            owner = None
            continue
        if e.get('team_id') in seconds and e.get('success') is True and (e['kind'] == 'pass' or e['kind'] in CONTROL_KINDS):
            owner, last_control = e['team_id'], at
    accrue(limit)
    known = sum(seconds.values())
    return dict(seconds=seconds, percent={k: 100*v/known if known else None for k, v in seconds.items()},
                known_seconds=known, unknown_seconds=max(0, limit - known),
                coverage=100*known/limit if limit else 0, max_gap_seconds=CONTROL_GAP_SECONDS)


def match_stats_at(fixture, elapsed):
    teams = {tid: dict(shots=0, on_target=0, xg=0., passes=0, completed=0, accuracy=None, possession_proxy=None)
             for tid in (fixture['home']['id'], fixture['away']['id'])}
    players, passes, seen = {}, {}, set()

    def player(pid):
        return players.setdefault(pid, dict(goals=0, assists=0, yellows=0, red=False))

    for e in fixture.get('stat_events') or []:
        if e['elapsed'] >= elapsed or e['id'] in seen:
            continue
        seen.add(e['id'])
        team = teams.get(e.get('team_id'))
        if team is None:
            continue
        if e['kind'] == 'pass':
            team['passes'] += 1
            if e.get('success') is True:
                team['completed'] += 1
            passes[e['id']] = e
        if e['kind'] in ('shot', 'goal'):
            team['shots'] += 1
            team['xg'] += _number(e.get('xg'))
            if e.get('on_target') is True or e['kind'] == 'goal':
                team['on_target'] += 1
        if e['kind'] == 'goal' and e.get('player_id'):
            player(e['player_id'])['goals'] += 1
            key = passes.get(e.get('key_pass_id'))
            if (key and key.get('success') is True and key.get('team_id') == e['team_id'] and key.get('player_id')
                    and key['player_id'] != e['player_id'] and key.get('recipient_id') == e['player_id']):
                player(key['player_id'])['assists'] += 1
        if e['kind'] == 'card' and e.get('player_id'):
            p = player(e['player_id'])
            if e.get('card') in ('yellow', 'second_yellow'):
                p['yellows'] += 1
            if e.get('card') in ('red', 'second_yellow'):
                p['red'] = True
    total = sum(t['passes'] for t in teams.values())
    for t in teams.values():
        t['accuracy'] = 100*t['completed']/t['passes'] if t['passes'] else None
        t['possession_proxy'] = 100*t['passes']/total if total else None
    possession = possession_at(fixture, elapsed)
    for tid, t in teams.items():
        t['possession_time'] = possession['percent'][tid]
    return dict(teams=teams, players=players, possession=possession)


def score_at(fixture, elapsed):
    score = {fixture['home']['id']: 0, fixture['away']['id']: 0}
    for e in fixture.get('events') or []:
        if e['elapsed'] < elapsed and e['kind'] in ('goal', 'own_goal') and e.get('team_id') in score:
            score[e['team_id']] += 1
    return score


def checkpoint_facts(fixture, minute, team_id):
    """Authoritative facts for one team view at a checkpoint, or None when the fixture is unknown."""
    if not fixture or team_id not in (fixture['home']['id'], fixture['away']['id']):
        return None
    elapsed = checkpoint_elapsed(fixture, minute)
    stats = match_stats_at(fixture, elapsed)
    score = score_at(fixture, elapsed)
    opponent_id = fixture['away']['id'] if team_id == fixture['home']['id'] else fixture['home']['id']
    names = {fixture['home']['id']: fixture['home']['name'], fixture['away']['id']: fixture['away']['name']}
    observed = sum(1 for e in fixture.get('stat_events') or [] if e['elapsed'] < elapsed)

    def side(tid):
        t = stats['teams'][tid]
        return dict(id=tid, name=names[tid], goals=score[tid], xg=round(t['xg'], 4), shots=t['shots'],
                    on_target=t['on_target'], passes=t['passes'], completed=t['completed'],
                    pass_accuracy=None if t['accuracy'] is None else round(t['accuracy'], 4),
                    possession=None if t['possession_time'] is None else round(t['possession_time'], 4))

    possession = stats['possession']
    return dict(version=FACTS_VERSION, cutoff=dict(minute=minute, elapsed=elapsed, rule='events strictly before the checkpoint'),
                events_observed=observed, team=side(team_id), opponent=side(opponent_id),
                players={pid: p for pid, p in stats['players'].items()},
                possession_coverage=dict(percent=round(possession['coverage'], 4), unknown_seconds=round(possession['unknown_seconds'], 1),
                                         max_gap_seconds=possession['max_gap_seconds']),
                provenance=fixture.get('source', 'UNSPECIFIED'), definitions=DEFINITIONS)


def fingerprint(facts):
    return hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()[:16]
