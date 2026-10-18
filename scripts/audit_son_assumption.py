"""Expose Tottenham sensitivity to the missing Son FIFA record."""
import copy
import json
from pathlib import Path

from benchmark_demo import replay, select_matches
from collect_demo_evidence import fetch
from subintel.demo_data import load_demo_profiles

ROOT = Path(__file__).resolve().parents[1]


def main():
    data = load_demo_profiles()
    evidence = json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    matches = [(m,t) for m,t in select_matches(fetch('matches/2/27.json'),evidence['cutoff']) if t=='38']
    scenarios = []
    for label, delta in [('omit_synthetic_son',None),('son_ratings_minus_5',-5),('baseline',0),('son_ratings_plus_5',5)]:
        sample = copy.deepcopy(data)
        if delta is None:
            sample['players'] = [p for p in sample['players'] if str(p['player_id'])!='3083']
        else:
            p = next(p for p in sample['players'] if str(p['player_id'])=='3083')
            for d in p['recent']['ratings']:
                p['recent']['ratings'][d] = max(0,min(100,p['recent']['ratings'][d]+delta))
        results = [replay(m,t,sample,evidence) for m,t in matches]
        scenarios.append(dict(scenario=label,matches=[dict(match_id=r['match_id'],
            snapshots=[dict(minute=s['minute'],decision=s['recommendation'],selected=s['selected']) for s in r['snapshots']]) for r in results]))
    out=ROOT/'docs/research/son_assumption_sensitivity.json'
    out.write_text(json.dumps(dict(warning='Sensitivity to a synthetic prior, not a confidence interval',scenarios=scenarios),ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps([dict(scenario=r['scenario'],positive_checkpoints=[sum(s['selected'] is not None for s in m['snapshots']) for m in r['matches']]) for r in scenarios]))


if __name__ == '__main__':
    main()
