"""Research-only real-match replay; never the final synthetic demo stream."""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from collect_demo_evidence import fetch
from subintel.demo_data import load_demo_profiles
from subintel.demo_live import make_match, recommend_demo
from subintel.profiles import TeamBaseline
from subintel.schema import Event, EventType, Player, Role
from subintel.statsbomb import ROLE_BY_POSITION, convert_event

ROOT = Path(__file__).resolve().parents[1]


def replay(mid, target_tid, dataset, evidence, top_options=3):
    raw = fetch(f'events/{mid}.json')
    lineup = fetch(f'lineups/{mid}.json')
    ms = make_match(dataset, evidence, str(mid))
    players, starters = {}, set()
    for team in lineup:
        for p in team['lineup']:
            pid = str(p['player_id'])
            spells = p['positions']
            role = ROLE_BY_POSITION[spells[0]['position']] if spells else None
            players[pid] = Player(player_id=pid, name=p.get('player_nickname') or p['player_name'], team_id=str(team['team_id']), role=role)
            if spells and spells[0]['start_reason'] == 'Starting XI':
                starters.add(pid)
    ms.players, ms.on_pitch, ms.used = players, set(starters), set(starters)
    ms.on_since = dict.fromkeys(starters, 0.)
    ms.team_ids = sorted({p.team_id for p in players.values()})
    ms.window = {tid: defaultdict(float) for tid in ms.team_ids}
    ms.book.teams = {tid: TeamBaseline(team_id=tid, **evidence['team_baselines'][tid]) for tid in ms.team_ids}
    result = []
    checkpoints = iter(range(5, 91, 5))
    checkpoint = next(checkpoints, None)
    for item in raw:
        ev = convert_event(item, str(mid))
        if ev is None:
            continue
        while checkpoint is not None and ev.minute >= checkpoint and (ev.period == 2 or checkpoint <= 45):
            # Evaluate at the exact boundary, with only events before it.
            ms.feed(Event(event_id=f'checkpoint-{checkpoint}', match_id=str(mid),
                          period=1 if checkpoint <= 45 else 2, minute=checkpoint, second=0,
                          team_id=target_tid, type=EventType.PERIOD_END))
            snapshot = recommend_demo(ms, target_tid, top=1000)
            snapshot['checkpoint_minute'] = checkpoint
            result.append(snapshot)
            checkpoint = next(checkpoints, None)
        ms.feed(ev)
    historical = []
    for item in raw:
        if item['type']['name'] != 'Substitution' or str(item['team']['id']) != target_tid:
            continue
        minute = item['minute']
        prior = next((s for s in reversed(result) if s['checkpoint_minute'] <= minute), None)
        out_id, in_id = str(item['player']['id']), str(item['substitution']['replacement']['id'])
        ranked = prior['alternatives'] if prior else []
        candidate = next((c for c in ranked if c['out_player']['id'] == out_id and c['in_player']['id'] == in_id), None)
        historical.append(dict(minute=minute, out_id=out_id, in_id=in_id,
                               out_name=item['player']['name'], in_name=item['substitution']['replacement']['name'],
                               preceding_checkpoint=prior['checkpoint_minute'] if prior else None,
                               candidate_rank=ranked.index(candidate)+1 if candidate else None,
                               candidate=candidate,
                               comparison='CANDIDATE_AT_PRECEDING_CHECKPOINT' if candidate else 'NOT_AVAILABLE_OR_ROLE_UNSUPPORTED_AT_PRECEDING_CHECKPOINT'))
    for snapshot in result:
        snapshot['alternatives'] = snapshot['alternatives'][:top_options]
    return dict(match_id=mid, team_id=target_tid, research_only=True,
                evidence_cutoff=evidence['cutoff'], profiles_frozen=True,
                historical_substitutions=historical, snapshots=result)


def select_matches(matches, cutoff):
    selected = []
    for team, tid in [('Liverpool','24'), ('Arsenal','1'), ('Chelsea','33'), ('Tottenham Hotspur','38')]:
        future = sorted((m for m in matches if m['match_date'] >= cutoff and team in
                         (m['home_team']['home_team_name'], m['away_team']['away_team_name'])), key=lambda m: (m['match_date'], m['match_id']))
        selected.extend((str(m['match_id']), tid) for m in future[:3])
    return selected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT/'data/benchmark_report.json')
    args = ap.parse_args()
    evidence = json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    matches = fetch('matches/2/27.json')
    selected = select_matches(matches, evidence['cutoff'])
    reports = [replay(mid, tid, load_demo_profiles(), evidence) for mid, tid in selected]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(reports, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps([dict(match_id=r['match_id'], team=r['team_id'], decisions=[s['recommendation'] for s in r['snapshots']],
                           unavailable_profiles=max(len(s['unavailable_profile_ids']) for s in r['snapshots'])) for r in reports]))


if __name__ == '__main__':
    main()
