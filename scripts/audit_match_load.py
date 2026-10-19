"""Compare refresh weights without tuning the recommendation threshold."""
import argparse
import json
from pathlib import Path

from benchmark_demo import replay, select_matches
from collect_demo_evidence import fetch
from subintel.demo_data import load_demo_profiles
from subintel import demo_live

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT/'data/match_load_audit.json')
    args = ap.parse_args()
    evidence = json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    saved = demo_live.REFRESH_SCORE_CAP, demo_live.REFRESH_HORIZON_MINUTES
    result = dict(threshold=.15, calibration_status='PROVISIONAL_HEURISTIC', sensitivity=[])
    try:
        for cap, horizon in ((0.,90.), (1.2,90.), (1.2,30.), (1.5,30.), (1.8,30.)):
            demo_live.REFRESH_SCORE_CAP = cap
            demo_live.REFRESH_HORIZON_MINUTES = horizon
            reports = [replay(mid, tid, load_demo_profiles(), evidence) for mid, tid in select_matches(fetch('matches/2/27.json'), evidence['cutoff'])]
            result['sensitivity'].append(dict(refresh_score_cap=cap, refresh_horizon_minutes=horizon, matches=[dict(
                match_id=r['match_id'], team_id=r['team_id'],
                recommendations=sum(s['recommendation']=='SUBSTITUTION' for s in r['snapshots']),
                snapshots=[dict(minute=s['minute'], recommendation=s['recommendation'], physical_need=s['physical_need'],
                                best=s['alternatives'][:1]) for s in r['snapshots']]) for r in reports]))
    finally:
        demo_live.REFRESH_SCORE_CAP, demo_live.REFRESH_HORIZON_MINUTES = saved
    result['examples'] = [dict(minutes=m, stamina=st, pressure_actions=p,
        **demo_live.estimated_match_load(m, st, p, 4*m/90, {'pressures':15,'prog_carries':4},115))
        for m, st, p in [(30,75,5),(60,75,10),(75,75,12.5),(90,75,15),(75,55,12.5),(75,90,12.5),(75,75,30)]]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps([dict(cap=r['refresh_score_cap'], counts=[m['recommendations'] for m in r['matches']]) for r in result['sensitivity']]))


if __name__ == '__main__':
    main()
