"""Scripted synthetic possessions -> live engine -> grounded JSON and browser demo.

No real match is replayed. All event locations, actions, outcomes and timings are
synthetic; historical player cards serve only as pre-match benchmark priors.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from subintel.demo_data import load_demo_profiles
from subintel.demo_live import make_match, recommend_demo
from subintel.schema import Event, EventType

ROOT = Path(__file__).resolve().parents[1]


def simulate(dataset, evidence):
    ms = make_match(dataset, evidence)
    events, snapshots = [], []
    sequence = 0

    def emit(minute, second, tid, pid, kind, **fields):
        nonlocal sequence
        sequence += 1
        ev = Event(event_id=f'synthetic-{sequence}', match_id=ms.match_id, period=1 if minute < 45 else 2,
                   minute=minute, second=second, team_id=tid, player_id=pid, type=EventType(kind), **fields)
        events.append(ev.model_dump(mode='json'))
        ms.feed(ev)
        return ev.event_id

    def actors(tid):
        return sorted((p for p in ms.on_pitch if ms.players[p].team_id == tid and ms.role(p) != 'GK'),
                      key=lambda p: (ms.role(p), p))

    def attacker(tid):
        return next((p for p in actors(tid) if ms.role(p) == 'ST'), actors(tid)[0])

    for minute in range(91):
        if minute in (0, 45):
            emit(minute, 0, '24', None, 'period_start')
        for possession in range(4):
            tid = '24' if possession % 2 == 0 else '1'
            ids = actors(tid)
            a, b = ids[(minute + possession) % len(ids)], ids[(minute + possession + 1) % len(ids)]
            base_second = 1 + possession * 14
            sterile = tid == '24' and 40 <= minute < 75
            for step in range(3):
                x = 38 + step * (3 if sterile else 15)
                emit(minute, base_second + step * 2, tid, a if step % 2 == 0 else b, 'pass',
                     x=x, y=30 + 5 * step, end_x=x+8, end_y=35, success=True,
                     recipient_id=b if step % 2 == 0 else a, possession_id=minute*4+possession,
                     under_pressure=sterile)
            if not sterile:
                emit(minute, base_second+7, tid, a, 'carry', x=65, y=35, end_x=80, end_y=35, success=True,
                     transition=minute % 5 == 0)
            else:
                emit(minute, base_second+7, tid, a, 'pass', x=90, y=5, end_x=109, end_y=40,
                     success=False, cross=True)
            emit(minute, base_second+8, tid, b, 'pressure')
            if minute % 3 == 0:
                emit(minute, base_second+9, tid, b, 'recovery', success=True)
            if minute % 5 == 0:
                emit(minute, base_second+10, tid, a, 'miscontrol', success=False)
            shot_frequency = 9 if tid == '24' else 7
            if not sterile and minute % shot_frequency == 0 and possession < 2:
                shooter = attacker(tid)
                assist = emit(minute, base_second+11, tid, b, 'pass', x=94, y=35, end_x=109, end_y=40,
                              success=True, recipient_id=shooter)
                emit(minute, base_second+12, tid, shooter, 'shot', x=109, y=40, xg=.12,
                     success=False, goal=False, on_target=minute % 2 == 0, key_pass_id=assist)
        if minute in (54, 78, 82):
            tid = '1' if minute == 54 else '24'
            emit(minute, 58, tid, attacker(tid), 'shot', x=111, y=40, xg=.32,
                 success=True, goal=True, on_target=True)
        if minute in (15, 35, 55, 65, 75, 85, 90):
            for tid in ('24', '1'):
                snapshot = recommend_demo(ms, tid)
                snapshot['event_source'] = 'SYNTHETIC_SCRIPTED_POSSESSIONS'
                snapshots.append(snapshot)
        # Apply only an engine-approved change, never force a named historical swap.
        if minute in (35, 65):
            for tid in ('24', '1'):
                rec = recommend_demo(ms, tid)
                if rec['selected']:
                    chosen = rec['selected']
                    emit(minute, 59, tid, chosen['out_player']['id'], 'substitution', replacement_id=chosen['in_player']['id'])
    return events, snapshots


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
    ap.add_argument('--out', type=Path, default=ROOT / 'data/synthetic_demo')
    args = ap.parse_args()
    evidence = json.loads((ROOT / 'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    events, snapshots = simulate(load_demo_profiles(), evidence)
    for snapshot in snapshots:
        snapshot['explanation'] = grounded_explanation(snapshot)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'events.jsonl').write_text('\n'.join(json.dumps(e, ensure_ascii=False) for e in events)+'\n', encoding='utf-8')
    (args.out / 'recommendations.json').write_text(json.dumps(snapshots, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    write_browser_demo(args.out / 'index.html', snapshots)
    print(json.dumps([dict(minute=r['minute'], team=r['team_id'], decision=r['recommendation'], best=r['alternatives'][:1]) for r in snapshots], ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
