"""Download pre-cutoff StatsBomb evidence; preserve existing metric definitions."""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from subintel.metrics import COMPONENTS, ComponentTracker
from subintel.statsbomb import OPEN_DATA, ROLE_BY_POSITION, convert_event

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data/raw'
CUTOFF = '2016-01-13'
TARGETS = {'Liverpool': '3754305', 'Arsenal': '3754305',
           'Chelsea': '3754062', 'Tottenham Hotspur': '3754065'}
EXTRA_COUNTS = ('goals', 'non_penalty_goals', 'penalty_goals', 'assists',
                'dribble_attempts', 'dribbles_completed', 'pass_attempts', 'passes_completed')
PINNED_OPEN_DATA = 'https://raw.githubusercontent.com/hudl/open-data/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/data'


def fetch(relative):
    path = CACHE / relative
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    payload = urllib.request.urlopen(f'{PINNED_OPEN_DATA}/{relative}', timeout=120).read()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    except OSError:  # read-only deployment (e.g. run from package): keep it in memory only
        pass
    return json.loads(payload.decode('utf-8'))


def clock(value):
    m, s = value.split(':')
    return int(m) + int(s) / 60


def extract(match):
    mid = str(match['match_id'])
    raw = fetch(f'events/{mid}.json')
    lineup = fetch(f'lineups/{mid}.json')
    first_end = max(e['minute'] + e['second'] / 60 for e in raw if e['period'] == 1)
    end = max(e['minute'] + e['second'] / 60 for e in raw if e['period'] == 2)
    extra = max(0, first_end - 45)
    counts = defaultdict(lambda: defaultdict(float))
    tracker = ComponentTracker()
    for e in raw:
        ev = convert_event(e, mid)
        if ev:
            for c in tracker.feed(ev):
                counts[c.player_id][c.component] += c.value
        pid = str(e.get('player', {}).get('id', ''))
        kind = e['type']['name']
        if kind == 'Shot' and e['shot']['outcome']['name'] == 'Goal':
            penalty = e['shot'].get('type', {}).get('name') == 'Penalty'
            counts[pid]['goals'] += 1
            counts[pid]['penalty_goals' if penalty else 'non_penalty_goals'] += 1
        if kind == 'Pass':
            counts[pid]['assists'] += int(e['pass'].get('goal_assist', False))
            counts[pid]['pass_attempts'] += 1
            counts[pid]['passes_completed'] += int('outcome' not in e['pass'])
        if kind == 'Dribble':
            counts[pid]['dribble_attempts'] += 1
            counts[pid]['dribbles_completed'] += int(e['dribble']['outcome']['name'] == 'Complete')
        # Count annotated aerial wins and lost aerial duels, never pair unrelated events.
        win = any(isinstance(e.get(k), dict) and e[k].get('aerial_won') for k in ('pass', 'shot', 'clearance', 'miscontrol'))
        lost = kind == 'Duel' and e.get('duel', {}).get('type', {}).get('name') == 'Aerial Lost'
        if win or lost:
            counts[pid]['aerial_attempts'] += 1
            counts[pid]['aerial_wins'] += int(win)
        if kind == 'Shot' and e['shot'].get('body_part', {}).get('name') == 'Head':
            counts[pid]['headed_shots'] += 1
    rows = []
    for team in lineup:
        for p in team['lineup']:
            positions = defaultdict(float)
            for spell in p['positions']:
                start = clock(spell['from']) + (extra if spell['from_period'] == 2 else 0)
                stop = clock(spell['to']) + (extra if spell['to_period'] == 2 else 0) if spell['to'] else end + extra
                positions[spell['position']] += max(0, stop - start)
            minutes = sum(positions.values())
            primary = max(positions, key=positions.get) if positions else None
            pid = str(p['player_id'])
            row = dict(player_id=pid, name=p.get('player_nickname') or p['player_name'],
                       team=team['team_name'], team_id=str(team['team_id']),
                       match_id=mid, date=match['match_date'], minutes=minutes,
                       started=bool(p['positions'] and p['positions'][0]['start_reason'] == 'Starting XI'),
                       positions=dict(positions), role=ROLE_BY_POSITION[primary].value if primary else None)
            row.update({c: counts[pid][c] for c in (*COMPONENTS, 'aerial_attempts', 'aerial_wins', 'headed_shots', *EXTRA_COUNTS)})
            rows.append(row)
    return rows


def main():
    matches = fetch('matches/2/27.json')
    before = sorted((m for m in matches if m['match_date'] < CUTOFF), key=lambda m: (m['match_date'], m['match_id']))
    target = [t for mid in sorted(set(TARGETS.values())) for t in fetch(f'lineups/{mid}.json') if TARGETS.get(t['team_name']) == mid]
    wanted = {str(p['player_id']) for t in target for p in t['lineup']}
    with ThreadPoolExecutor(max_workers=8) as pool:
        batches = list(pool.map(extract, before))
    all_rows = [r for batch in batches for r in batch]
    windows = {}
    for team in TARGETS:
        windows[team] = [str(m['match_id']) for m in reversed(before) if team in (m['home_team']['home_team_name'], m['away_team']['away_team_name'])][:5]
    evidence = dict(cutoff=CUTOFF, target_match_id='3754305', target_matches=TARGETS, team_windows=windows,
                    starter_positions={str(p['player_id']): ROLE_BY_POSITION[p['positions'][0]['position']].value
                                       for t in target for p in t['lineup'] if p['positions'] and p['positions'][0]['start_reason'] == 'Starting XI'},
                    match_ids=[str(m['match_id']) for m in before],
                    source=f'{PINNED_OPEN_DATA}/matches/2/27.json',
                    rows=[r for r in all_rows if r['player_id'] in wanted])
    # Whole-league role distributions use pre-cutoff player-season rates, >=450 min.
    import numpy as np
    from subintel.demo_dataset import observed_rates
    grouped = defaultdict(list)
    for r in all_rows:
        if r['minutes'] > 0 and r['role'] != 'GK':
            grouped[r['player_id']].append(r)
    cohorts = defaultdict(list)
    for rows in grouped.values():
        if sum(r['minutes'] for r in rows) < 450:
            continue
        roles = defaultdict(float)
        for r in rows:
            roles[r['role']] += r['minutes']
        cohorts[max(roles, key=roles.get)].append(observed_rates(rows))
    evidence['role_calibration'] = {role: {d: {'mean': float(np.mean([r[d] for r in rates if r[d] is not None])),
                                               'std': max(float(np.std([r[d] for r in rates if r[d] is not None])), 0.02)}
                                            for d in rates[0]} for role, rates in cohorts.items()}
    component_cohorts = defaultdict(list)
    for rows in grouped.values():
        minutes = sum(r['minutes'] for r in rows)
        if minutes < 450:
            continue
        role_minutes = defaultdict(float)
        for r in rows:
            role_minutes[r['role']] += r['minutes']
        role = max(role_minutes, key=role_minutes.get)
        component_cohorts[role].append({c: sum(r[c] for r in rows) / minutes * 90 for c in COMPONENTS})
    evidence['role_component_p90'] = {role: {c: float(np.mean([r[c] for r in rates])) for c in COMPONENTS}
                                        for role, rates in component_cohorts.items()}
    team_games = defaultdict(dict)
    for batch in batches:
        by_team = defaultdict(list)
        for r in batch:
            by_team[r['team_id']].append(r)
        for tid, rows in by_team.items():
            team_games[tid][rows[0]['match_id']] = dict(minutes=max(r['minutes'] for r in rows),
                totals={c: sum(r[c] for r in rows) for c in COMPONENTS})
    evidence['team_baselines'] = {}
    for tid, games in team_games.items():
        minutes = sum(g['minutes'] for g in games.values())
        own = {c: sum(g['totals'][c] for g in games.values()) / minutes * 90 for c in COMPONENTS}
        conceded = {c: sum(other[mid]['totals'][c] for oid, other in team_games.items() if oid != tid for mid in games if mid in other) / minutes * 90 for c in COMPONENTS}
        evidence['team_baselines'][tid] = dict(p90=own, conceded_p90=conceded,
                                               loss_rate=own['ball_losses'] / max(own['ball_actions'], 1))
    used_paths = [CACHE/'matches/2/27.json', *[CACHE/f'lineups/{mid}.json' for mid in sorted(set(TARGETS.values()))]]
    used_paths += [CACHE/f'{kind}/{m["match_id"]}.json' for m in before for kind in ('events', 'lineups')]
    evidence['raw_sha256'] = {str(p.relative_to(CACHE)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(used_paths)}
    out = ROOT / 'demo_data/source_evidence.json'
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'{len(before)} pre-cutoff matches; {len(evidence["rows"])} target-player rows -> {out}')


if __name__ == '__main__':
    main()
