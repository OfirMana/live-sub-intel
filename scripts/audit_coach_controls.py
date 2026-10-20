"""Paired coach/freshness experiments on identical past-only research states."""
import argparse
import json
import gzip
from collections import Counter
from pathlib import Path

from benchmark_demo import select_matches
from collect_demo_evidence import fetch
from subintel.coach_room import CoachConfig, CoachReplay, recommend_coach
from subintel.demo_data import load_demo_profiles

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=ROOT/'docs/research/coach_controls_audit.json')
    args = p.parse_args()
    data = load_demo_profiles()
    evidence = json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    matches = select_matches(fetch('matches/2/27.json'), evidence['cutoff'])
    totals, rows = {}, []
    for stance, objective in [('balanced','competitive'), ('attack','win'), ('defend','draw')]:
        for cap in (0., .5, 1., 1.5):
            totals[f'{stance}/{objective}/{cap}'] = Counter()
    for mid, tid in matches:
        replay = CoachReplay(data, evidence, fetch(f'events/{mid}.json'), fetch(f'lineups/{mid}.json'), mid, tid)
        for minute in range(5, 91, 5):
            ms, observed = replay.state_at(minute)
            for stance, objective in [('balanced','competitive'), ('attack','win'), ('defend','draw')]:
                for cap in (0., .5, 1., 1.5):
                    config = CoachConfig(stance=stance, objective=objective, freshness_cap=cap)
                    rec = recommend_coach(ms, tid, observed, replay.roster, config)
                    selected = rec['selected']
                    key = f'{stance}/{objective}/{cap}'
                    counter = totals[key]
                    counter['checkpoints'] += 1
                    if selected:
                        counter['recommendations'] += 1
                        counter[selected['decision_basis']] += 1
                        counter['negative_tactical'] += selected['score_components']['tactical_benefit'] < 0
                        role = next(p['role'] for p in observed['lineup'] if p['player_id']==selected['out_player']['id'])
                        counter['CB_out'] += role == 'CB'
                        counter['before_60'] += minute < 60
                    rows.append(dict(match_id=mid, team_id=tid, minute=minute, setting=key,
                        selected=None if not selected else dict(out=selected['out_player'], incoming=selected['in_player'],
                        benefit=selected['expected_benefit'], tactical=selected['score_components']['tactical_benefit'],
                        freshness=selected['score_components']['freshness_benefit']),
                        need=rec['team_needs'], reason=rec['no_substitution_reason']))
        print(f'Checked {mid}/{tid}', flush=True)
    result = dict(kind='PAIRED_RESEARCH_SENSITIVITY_NOT_FOOTBALL_ACCURACY',
                  checkpoints=len(matches)*18, cases=len(rows), profiles_frozen=True,
                  formation='observed', summary={k:dict(v) for k,v in totals.items()}, rows=rows,
                  limitations=['Counts are repeated checkpoints, not distinct swaps.',
                    'The coach model adds role exposure and observed tactical shifts; this is not a controlled comparison to the old engine.',
                    'Within each coach setting only freshness cap changes. No named historical substitution is a target.'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cases_path=args.out.with_name('coach_controls_cases.json.gz')
    with gzip.open(cases_path,'wt',encoding='utf-8') as handle:
        json.dump(rows, handle, ensure_ascii=False)
    result.pop('rows')
    result['cases_file']=cases_path.name
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result['summary'], indent=2))


if __name__=='__main__':
    main()
