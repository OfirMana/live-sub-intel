"""Automatic-XI coverage, performance and paired freshness review; not accuracy."""
import gzip
import json
from collections import Counter
from pathlib import Path

from benchmark_demo import select_matches
from collect_demo_evidence import fetch, TARGETS
from subintel.auto_plans import AutoConfig, recommend_auto
from subintel.coach_room import CoachReplay
from subintel.demo_data import load_demo_profiles

ROOT=Path(__file__).resolve().parents[1]


def summarize(rows):
    c=Counter(cases=len(rows))
    times=[]
    for r in rows:
        c[r['decision']]+=1
        if r['selected']:
            c['negative_incremental_tactics']+=r['selected']['tactical']<0
            c['with_repositioning']+=r['selected']['moved']>0
            c['formation_changes']+=r['selected']['change_type']=='FORMATION_CHANGE'
            c['freshness_led']+=r['selected']['basis']=='FRESH_LEGS'
        times.append(r['search']['elapsed_ms'])
    times.sort()
    return dict(c,latency_ms=dict(median=times[len(times)//2],p95=times[min(len(times)-1,int(.95*len(times)))],max=max(times)))


def main():
    data=load_demo_profiles()
    evidence=json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    rows=[]
    for mid,tid in select_matches(fetch('matches/2/27.json'),evidence['cutoff']):
        replay=CoachReplay(data,evidence,fetch(f'events/{mid}.json'),fetch(f'lineups/{mid}.json'),mid,tid)
        target=mid in TARGETS.values()
        for minute in range(5,91,5):
            ms,observed=replay.state_at(minute)
            caps=(0.,.5,1.,1.5) if target and minute in (60,65,75,85) else (1.,)
            for cap in caps:
                result=recommend_auto(ms,tid,observed,replay.roster,AutoConfig(freshness_cap=cap))
                selected=result['selected']
                if selected:
                    x=selected['score_components']
                    assert x['tactical_benefit']>=-selected['allowed_tactical_loss']-1e-9
                    assert selected['expected_benefit']>=.15
                for option in result['alternatives']:
                    ids=[p['player_id'] for p in option['proposed_lineup']]
                    assert len(ids)==len(set(ids))==11
                    assert option['out_player']['id'] not in ids
                    assert option['in_player']['id'] in ids
                rows.append(dict(match_id=mid,team_id=tid,minute=minute,cap=cap,paired=target and minute in (60,65,75,85),
                    decision=result['recommendation'],search=result['search'],
                    selected=None if not selected else dict(out=selected['out_player']['id'],incoming=selected['in_player']['id'],
                    formation=selected['formation'],benefit=selected['expected_benefit'],tactical=selected['score_components']['tactical_benefit'],
                    freshness=selected['score_components']['freshness_benefit'],moved=len(selected['repositioned']),
                    change_type=selected['change_type'],basis=selected['decision_basis'])))
        print(f'Checked automatic plans {mid}/{tid}',flush=True)
    default=[r for r in rows if r['cap']==1.]
    paired={str(cap):summarize([r for r in rows if r['paired'] and r['cap']==cap]) for cap in (0.,.5,1.,1.5)}
    result=dict(version='coach-room-v2',kind='RESEARCH_COVERAGE_AND_SENSITIVITY_NOT_ACCURACY',
        default_policy=dict(freshness_cap=1.,max_absolute_tactical_loss=.1,max_loss_fraction_of_freshness=.35),
        default=summarize(default),paired=paired,total_evaluations=len(rows),
        limitations=['No expert-labelled accuracy, no causal result prediction.','Timing is local CPU scoring, not network latency.',
                      'The search is exact within the supported position/template catalog, not every imaginable football shape.'])
    out=ROOT/'docs/research'
    (out/'auto_plans_audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    with gzip.open(out/'auto_plans_cases.json.gz','wt',encoding='utf-8') as f:json.dump(rows,f)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
