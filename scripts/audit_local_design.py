import json
from pathlib import Path
from synthetic_coach_room import create_synthetic_room
from subintel.auto_plans import AutoConfig
report=[]
for scenario in ('original','lively'):
 b,evaluate=create_synthetic_room(scenario=scenario); f=b['fixtures']['synthetic-demo'];events=f['stat_events'];rows=[]
 assert len({x['id'] for x in events})==len(events)
 cards={}
 for ev in events:
  if ev.get('card')=='yellow':cards[ev['player_id']]=cards.get(ev['player_id'],0)+1
 if scenario=='lively':assert max(cards.values())==1
 for minute in range(0,91,5):
  visible=[e for e in events if e['elapsed']<minute];segment=[e for e in f['events'] if max(0,minute-5)<=e['elapsed']<minute]
  goals={t:sum(e['kind']=='goal' and e['team_id']==t for e in visible) for t in ('24','1')}
  row={'minute':minute,'score':[goals['24'],goals['1']],'segment_highlights':[{k:x.get(k) for k in ('kind','elapsed','player','card')} for x in segment if x['kind'] in ('goal','card','shot')],'decisions':{}}
  for t in ('24','1'):
   r=evaluate('synthetic-demo',t,minute,AutoConfig().model_dump_json());assert r['state']['goal_diff']==goals[t]-goals['1' if t=='24' else '24'];assert len(r['observed']['lineup'])==11
   for p in r['alternatives']:
    ids=[x['player_id'] for x in p['proposed_lineup']];assert len(ids)==len(set(ids))==11
    assert p['out_player']['id'] not in ids and p['in_player']['id'] in ids
    if p['recommended']:assert p['quality_gate_passed'] and p['clears_threshold']
   row['decisions'][t]=r['recommendation']
  rows.append(row)
 report.append({'scenario':scenario,'goals':[{'minute':e['elapsed'],'team':e['team_id'],'player':e['player_id']} for e in events if e['kind']=='goal'],'yellow_players':cards,'checkpoints':rows})
Path('outputs/local_match_walkthrough.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('PASS: 76 team/checkpoint evaluations; both scenarios; score, XI, gates, unique events; lively cards all unique')
