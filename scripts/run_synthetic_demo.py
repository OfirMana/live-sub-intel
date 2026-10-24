"""Scripted synthetic possessions -> live engine -> grounded JSON and browser demo.

No real match is replayed. All event locations, actions, outcomes and timings are
synthetic; historical player cards serve only as pre-match benchmark priors.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from subintel.demo_data import load_demo_profiles
from subintel.demo_live import make_match, recommend_demo
from subintel.schema import Event, EventType

ROOT = Path(__file__).resolve().parents[1]


DEFAULT_SEED = 20261021
GENERATOR_VERSION = 'seeded-possessions-v4-turnovers'


def simulate(dataset, evidence, *, apply_substitutions=True, collect_snapshots=True, seed=DEFAULT_SEED, scenario="original"):
    """Seeded illustrative possessions; no fitted outcome probabilities.

    The three goal phases are authored scenario beats. Timing, actors, locations
    and shot quality vary independently of recommendations. No future event is
    supplied to the recommendation engine.
    """
    rng = random.Random(seed)
    annotations_rng = random.Random(seed + 31)
    ms = make_match(dataset, evidence)
    events, snapshots = [], []
    sequence = 0
    pending = []

    def emit(minute, second, tid, pid, kind, **fields):
        nonlocal sequence
        sequence += 1
        ev = Event(event_id=f'synthetic-{sequence}', match_id=ms.match_id, period=1 if minute < 45 else 2,
                   minute=minute, second=second, team_id=tid, player_id=pid, type=EventType(kind), **fields)
        pending.append(ev)
        return ev.event_id

    def actors(tid):
        return sorted(p for p in ms.on_pitch if ms.players[p].team_id == tid and ms.role(p) != 'GK')

    def shooter(tid):
        ids = actors(tid)
        weights = {'ST':5, 'AM_W':3.5, 'CM':1.5, 'FB':.5, 'CB':.3}
        return rng.choices(ids, weights=[weights.get(ms.role(p),1) for p in ids])[0]

    # Authored manager decisions, independent of the recommendation ranking.
    # Same-role swaps keep the replay legal without inventing a formation change.
    scripted_swaps = {
        58: ('24', '3535', '3380'), 64: ('1', '3511', '3713'),
        70: ('24', '4090', '10326'), 74: ('1', '5581', '3525'),
    }
    booked = set()
    for minute in range(91):
        if scenario == 'lively' and minute in scripted_swaps:
            tid, outgoing, incoming = scripted_swaps[minute]
            assert outgoing in ms.on_pitch and incoming not in ms.used
            assert ms.players[outgoing].team_id == ms.players[incoming].team_id == tid
            emit(minute, 0, tid, outgoing, 'substitution', replacement_id=incoming)
            # Feed before creating later actions: departed players cannot act again.
            for event in pending:
                events.append(event.model_dump(mode='json'))
                ms.feed(event)
            pending.clear()
        if minute in (0, 45):
            emit(minute, 0, '24', None, 'period_start')
        count = rng.randint(3,4)
        for possession in range(count):
            tid = rng.choice(('24','1'))
            opponent = '1' if tid == '24' else '24'
            a,b = rng.sample(actors(tid),2)
            defender = rng.choice(actors(opponent))
            base = possession*(58//count)+rng.randint(1,2)
            sterile = tid == '24' and 40 <= minute < 75
            x,y = rng.uniform(28,48),rng.uniform(12,68)
            lost=False
            # A failed pass ends this attack. Further actions belong to the
            # recovering side; pressure alone never changes ball ownership.
            for step in range(3):
                end_x = min(110,x+rng.uniform(2,7) if sterile else x+rng.uniform(7,19))
                end_y = max(2,min(78,y+rng.uniform(-12,12)))
                completed=rng.random() < (.85 if sterile else .92)
                emit(minute,base+step,tid,a if step%2==0 else b,'pass',
                     x=round(x,2),y=round(y,2),end_x=round(end_x,2),end_y=round(end_y,2),
                     success=completed,recipient_id=b if step%2==0 else a,
                     possession_id=minute*4+possession,under_pressure=sterile)
                if not completed:
                    emit(minute,base+step+1,opponent,defender,'recovery',success=True)
                    lost=True
                    break
                x,y=end_x,end_y
            if lost:continue
            emit(minute,base+3,opponent,defender,'pressure')
            if rng.random()<.3:
                won=rng.random()<.6
                emit(minute,base+4,opponent,defender,'tackle',success=won)
                if won:
                    emit(minute,base+5,opponent,defender,'recovery',success=True)
                    continue
            if rng.random()<.08:
                emit(minute,base+5,tid,a,'miscontrol',success=False)
                emit(minute,base+6,opponent,defender,'recovery',success=True)
                continue
            if not sterile:
                emit(minute,base+5,tid,a,'carry',x=x,y=y,end_x=min(115,x+rng.uniform(5,17)),end_y=y,
                     success=True,transition=rng.random()<.2)
            elif rng.random()<.5:
                emit(minute,base+5,tid,a,'pass',x=x,y=y,end_x=110,end_y=rng.uniform(20,60),
                     success=False,cross=True)
                emit(minute,base+6,opponent,defender,'recovery',success=True)
                continue
            if rng.random() < (.02 if sterile else .12):
                pid=shooter(tid)
                creator=rng.choice([p for p in actors(tid) if p!=pid])
                assist=emit(minute,base+8,tid,creator,'pass',x=94,y=35,end_x=108,end_y=40,
                            success=True,recipient_id=pid)
                xg=round(rng.uniform(.025,.26),3)
                emit(minute,base+9,tid,pid,'shot',x=round(rng.uniform(96,113),2),
                     y=round(rng.uniform(25,55),2),xg=xg,success=False,goal=False,
                     on_target=rng.random()<.4,key_pass_id=assist)
        first_goal = 27 if scenario == "lively" else 54
        if minute in (first_goal,78,82):
            tid='1' if minute==first_goal else '24'
            pid=shooter(tid)
            second=rng.randint(8,56)
            creator=annotations_rng.choice([p for p in actors(tid) if p!=pid])
            assist=emit(minute,second-1,tid,creator,'pass',x=94,y=35,end_x=108,end_y=40,success=True,recipient_id=pid)
            emit(minute,second,tid,pid,'shot',
                 x=round(rng.uniform(104,114),2),y=round(rng.uniform(30,50),2),
                 xg=round(rng.uniform(.14,.46),3),success=True,goal=True,on_target=True,key_pass_id=assist)
        card_minutes = (18,32,44,61,73) if scenario == "lively" else (32,61)
        if minute in card_minutes:
            tid='24' if minute in (18,32,73) else '1'
            if scenario == 'original':
                emit(minute,annotations_rng.randint(8,56),tid,annotations_rng.choice(actors(tid)),'card',card='yellow')
            else:
                eligible = [pid for pid in actors(tid) if pid not in booked]
                if eligible:
                    booked_player = annotations_rng.choice(eligible)
                    booked.add(booked_player)
                    emit(minute,annotations_rng.randint(8,56),tid,booked_player,'card',card='yellow')
        for ev in sorted(pending,key=lambda e:(e.minute,e.second)):
            events.append(ev.model_dump(mode='json'))
            ms.feed(ev)
        pending.clear()
        if collect_snapshots and minute >= 15 and minute%5==0:
            for tid in ('24','1'):
                snapshot=recommend_demo(ms,tid)
                snapshot['event_source']='SYNTHETIC_SCRIPTED_POSSESSIONS'
                snapshots.append(snapshot)
        if apply_substitutions and scenario != "lively" and 30<=minute<=80 and minute%5==0:
            for tid in ('24','1'):
                rec=recommend_demo(ms,tid)
                if rec['selected']:
                    chosen=rec['selected']
                    emit(minute,59,tid,chosen['out_player']['id'],'substitution',replacement_id=chosen['in_player']['id'])
            for ev in pending:
                events.append(ev.model_dump(mode='json'));ms.feed(ev)
            pending.clear()
    return events,snapshots


def grounded_explanation(rec):
    if rec['recommendation'] == 'NO_SUBSTITUTION':
        return 'No substitution recommended: no eligible candidate clears the deterministic threshold.'
    selected = rec['selected']
    gains = [d for d, v in selected['expected_changes'].items() if v > 0]
    return (f"{selected['in_player']['name']} for {selected['out_player']['name']}. "
            f"The supported role fits; expected improvements: {', '.join(gains)}. "
            'Trade-offs and evidence strength are shown in the JSON. Match load is estimated.')


def write_browser_demo(path, snapshots):
    payload = json.dumps(snapshots, ensure_ascii=False).replace('</', '<\\/')
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Live Substitution Intelligence — Synthetic Demo</title>
<style>body{background:#0e1825;color:#eaf2fc;font:16px system-ui;margin:0;padding:32px}main{max-width:1100px;margin:auto}h1{font-size:30px}small{color:#a9c1da}.label{color:#70e3ac}button,select,input{font:inherit;margin:8px;padding:8px}section{background:#192a3d;padding:22px;margin:20px 0;border-radius:12px}.bars{display:flex;gap:20px;flex-wrap:wrap}.bar{width:160px}progress{width:160px;accent-color:#70e3ac}table{border-collapse:collapse;width:100%}td,th{text-align:left;border-bottom:1px solid #3a4b61;padding:8px}pre{white-space:pre-wrap;max-height:350px;overflow:auto} .warn{color:#ffd18c}</style>
<main><small>MICROSOFT × PREMIER LEAGUE AI HACKATHON · BENCHMARK PROTOTYPE</small><h1>Live Substitution Intelligence</h1>
<p class="warn">SYNTHETIC event stream · Historical FIFA16 / StatsBomb player priors · Estimated match load</p>
<p>Balanced play → sterile possession → trailing → eligible substitution → lead protection.</p>
<button id="play">▶ Play checkpoints</button><button id="live">Stream events</button><span id="status"></span><label>Minute <select id="minute"></select></label><select id="team"><option value="24">Liverpool</option><option value="1">Arsenal</option></select>
<section><h2 id="decision"></h2><p id="reason"></p><p id="score"></p><div class="bars" id="needs"></div></section>
<section><h2>Eligible alternatives</h2><table><thead><tr><th>OUT</th><th>IN</th><th>Benefit</th><th>Position fit</th><th>Evidence strength</th></tr></thead><tbody id="options"></tbody></table></section>
<section><h2>Grounded deterministic output</h2><p>The LLM may explain this JSON; it may not choose a swap or add statistics. This preview uses a deterministic explanation.</p><pre id="json"></pre></section>
<small>Sources, mappings, capped modifiers and limitations: demo_data/README.md. Threshold is provisional; this prototype has not been calibrated across a full season.</small></main>
<script>const data=PAYLOAD; const minutes=[...new Set(data.map(x=>x.minute))];const select=document.getElementById('minute');minutes.forEach(m=>select.add(new Option(m+"′",m)));let timer;
function draw(record){const r=record&&record.team_needs?record:data.find(x=>x.minute==select.value&&x.team_id==document.getElementById('team').value);const s=r.selected;document.getElementById('decision').textContent=s?s.out_player.name+' → '+s.in_player.name:'No substitution recommended';document.getElementById('reason').textContent=r.explanation;document.getElementById('score').textContent='Goal difference: '+r.state.goal_diff+' · Substitutions left: '+r.state.subs_left+' · Threshold: '+r.threshold;document.getElementById('needs').innerHTML=Object.entries(r.team_needs).map(([d,v])=>'<div class="bar"><p>'+d+' '+v.toFixed(2)+'</p><progress value="'+v+'" max="1"></progress></div>').join('');document.getElementById('options').innerHTML=r.alternatives.map(o=>'<tr><td>'+o.out_player.name+'</td><td>'+o.in_player.name+'</td><td>'+o.expected_benefit+'</td><td>'+o.position_fit+'</td><td>'+o.evidence_strength+'</td></tr>').join('');document.getElementById('json').textContent=JSON.stringify(r,null,2)}select.onchange=draw;document.getElementById('team').onchange=draw;document.getElementById('play').onclick=()=>{if(timer){clearInterval(timer);timer=null;return}timer=setInterval(()=>{select.selectedIndex=(select.selectedIndex+1)%minutes.length;draw()},1800)};let stream;document.getElementById('live').onclick=()=>{if(stream)stream.close();document.getElementById('status').textContent='Streaming synthetic events…';stream=new EventSource('/stream?team='+document.getElementById('team').value);stream.onmessage=e=>{const r=JSON.parse(e.data);document.getElementById('status').textContent='Live synthetic minute '+r.minute;draw(r)};stream.addEventListener('complete',()=>{stream.close();document.getElementById('status').textContent='Synthetic match complete'});stream.onerror=()=>{stream.close();document.getElementById('status').textContent='Start scripts/serve_demo.py to stream events; checkpoint playback works offline.'}};draw();</script></html>'''
    path.write_text(html.replace('PAYLOAD', payload), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed',type=int,default=DEFAULT_SEED)
    ap.add_argument('--out', type=Path, default=ROOT / 'data/synthetic_demo')
    args = ap.parse_args()
    evidence = json.loads((ROOT / 'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    events, snapshots = simulate(load_demo_profiles(), evidence, seed=args.seed)
    for snapshot in snapshots:
        snapshot['explanation'] = grounded_explanation(snapshot)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'events.jsonl').write_text('\n'.join(json.dumps(e, ensure_ascii=False) for e in events)+'\n', encoding='utf-8')
    (args.out / 'recommendations.json').write_text(json.dumps(snapshots, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    write_browser_demo(args.out / 'index.html', snapshots)
    print(json.dumps([dict(minute=r['minute'], team=r['team_id'], decision=r['recommendation'], best=r['alternatives'][:1]) for r in snapshots], ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
