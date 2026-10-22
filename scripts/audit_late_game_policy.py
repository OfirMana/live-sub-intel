"""Compare the same historical checkpoints with late-win policy on/off."""
from collections import Counter
import json
from pathlib import Path
from collect_demo_evidence import TARGETS, fetch
from serve_coach_room import TEAM_IDS
from subintel.coach_room import CoachReplay
from subintel.auto_plans import AutoConfig, recommend_auto
from subintel.demo_data import load_demo_profiles

ROOT=Path(__file__).resolve().parents[1]

def main():
    dataset=load_demo_profiles()
    evidence=json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    rows=[]
    for team,mid in TARGETS.items():
        tid=TEAM_IDS[team]
        replay=CoachReplay(dataset,evidence,fetch(f'events/{mid}.json'),fetch(f'lineups/{mid}.json'),mid,tid)
        for minute in (75,80,85,90):
            for objective in ('win','draw'):
                ms,observed=replay.state_at(minute)
                config=AutoConfig(objective=objective)
                before=recommend_auto(ms,tid,observed,replay.roster,config,late_policy_enabled=False)
                after=recommend_auto(ms,tid,observed,replay.roster,config)
                if not after['late_game_policy']['active']:
                    assert [(p['out_player']['id'],p['in_player']['id'],p['expected_benefit']) for p in before['alternatives']]==[(p['out_player']['id'],p['in_player']['id'],p['expected_benefit']) for p in after['alternatives']]
                def summarize(r):
                    p=r['selected']
                    return dict(decision=r['recommendation'],recommended_pairs=sum(x['recommended'] for x in r['alternatives']),
                        selected=(p['out_player']['name']+' -> '+p['in_player']['name']) if p else None,
                        selected_benefit=p['expected_benefit'] if p else None,
                        top_benefit=r['alternatives'][0]['expected_benefit'] if r['alternatives'] else None)
                rows.append(dict(team=team,minute=minute,objective=objective,goal_diff=after['state']['goal_diff'],
                    policy=after['late_game_policy'],before=summarize(before),after=summarize(after)))
    summary=dict(checkpoints=len(rows),active=sum(r['policy']['active'] for r in rows),
        decisions_before=dict(Counter(r['before']['decision'] for r in rows)),decisions_after=dict(Counter(r['after']['decision'] for r in rows)),
        changed_decisions=sum(r['before']['decision']!=r['after']['decision'] for r in rows),
        unchanged_inactive=True)
    report=dict(kind='SENSITIVITY_NOT_TACTICAL_ACCURACY',summary=summary,rows=rows)
    (ROOT/'docs/research/late_game_policy_audit.json').write_text(json.dumps(report,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
    print(json.dumps(summary))

if __name__=='__main__':main()
