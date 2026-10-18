"""Export an offline, inspectable four-team checkpoint report and CSV."""
import argparse
import csv
import copy
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'24':'Liverpool','1':'Arsenal','33':'Chelsea','38':'Tottenham Hotspur'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()
    reports = json.loads(args.report.read_text(encoding='utf-8'))
    matches = json.loads((ROOT/'data/raw/matches/2/27.json').read_text(encoding='utf-8'))
    by_id = {str(m['match_id']): m for m in matches}
    rows = []
    for report in reports:
        m = by_id[report['match_id']]
        report['team_name'] = NAMES[report['team_id']]
        report['fixture'] = f"{m['home_team']['home_team_name']} / {m['away_team']['away_team_name']} ({m['match_date']})"
        for s in report['snapshots']:
            best = s['alternatives'][0] if s['alternatives'] else {}
            rows.append(dict(team=report['team_name'], fixture=report['fixture'], minute=s['minute'],
                             decision=s['recommendation'], out=best.get('out_player',{}).get('name'),
                             incoming=best.get('in_player',{}).get('name'), benefit=best.get('expected_benefit'),
                             threshold=s['threshold'], missing_profiles=len(s['unavailable_profile_ids']),
                             **best.get('score_components', {})))
    out = ROOT/'docs/research'
    out.mkdir(exist_ok=True)
    (out/'four_team_benchmark.json.gz').write_bytes(gzip.compress(json.dumps(reports, ensure_ascii=False).encode('utf-8'),mtime=0))
    with (out/'five_minute_decisions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for row in rows for k in row)),lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    html = '''<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>בדיקות חילופים — ארבע קבוצות</title>
<style>body{font:16px Arial;background:#f3f6fa;color:#17304b;margin:0}main{max-width:1250px;margin:auto;padding:24px}section{background:white;padding:20px;margin:18px 0;border-radius:10px}p{line-height:1.7}select{padding:10px;max-width:100%;font:inherit}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:11px;border-bottom:1px solid #dce4ee;text-align:right}th{background:#17365d;color:white}tr{cursor:pointer}tr:hover{background:#e6f0fa}.scroll{overflow:auto}pre{direction:ltr;text-align:left;max-height:420px;overflow:auto;white-space:pre-wrap}.note{background:#fff1ce;padding:15px;border-radius:8px}.grid{display:flex;gap:20px;flex-wrap:wrap}</style>
<main><h1>בדיקת המלצות כל חמש דקות</h1><p>ארבע קבוצות · 12 הרצות של קבוצה במשחק · דקות 5–90 · כרטיסים קפואים מלפני 13.01.2016.</p>
<p class="note">אלה נקודות בדיקה חוזרות בשחזור האירועים ההיסטורי. המלצות המודל אינן מבוצעות בשחזור; המשחק ממשיך עם חילופי המאמן המקוריים. הציון אינו הסתברות או אומדן תוספת שערים. נתוני העייפות הם אומדן. בחלק מהמשחקים המאוחרים חסרים כרטיסים לשחקנים שלא היו בסגל המקורי.</p>
<section><label>קבוצה <select id="team"></select></label> <label>משחק <select id="match"></select></label><p id="summary"></p><div class="scroll"><table><thead><tr><th>דקה</th><th>החלטה</th><th>מועמד יוצא</th><th>מועמד נכנס</th><th>תועלת</th><th>עייפות יוצא</th><th>כרטיסים חסרים</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section><h2 id="title">פירוט נקודת בדיקה</h2><div id="detail"></div><details><summary>כל הנתונים והחישובים בנקודה הזאת</summary><pre id="raw"></pre></details></section>
<section><h2>החילופים ההיסטוריים לצורך השוואה</h2><p>מוצג דירוג החילוף בנקודת הבדיקה שקדמה לו. חוסר התאמה יכול לנבוע ממגבלת עמדה, כרטיס חסר או זמינות; אינו מסומן אוטומטית כטעות של המודל.</p><div class="scroll" id="history"></div></section>
<p><a href="five_minute_decisions.csv">טבלת כל נקודות הבדיקה CSV</a> · <a href="four_team_benchmark.json.gz">נתונים מלאים JSON דחוס</a> · <a href="../player-cards/index.html">כרטיסי השחקנים</a></p></main>
<script>const reports=PAYLOAD;const team=document.getElementById('team'),match=document.getElementById('match');const fmt=x=>x===undefined||x===null?'—':typeof x==='number'?x.toFixed(3):x;let current;
for(const n of [...new Set(reports.map(r=>r.team_name))])team.add(new Option(n,n));
function show(s){document.getElementById('title').textContent='דקה '+s.minute;const best=s.alternatives[0];document.getElementById('detail').innerHTML=best?'<p dir="ltr">'+best.out_player.name+' → '+best.in_player.name+'</p><div class="scroll"><table><tr><th>רכיב</th><th>ערך</th></tr>'+Object.entries(best.score_components).map(([k,v])=>'<tr><td>'+k+'</td><td>'+fmt(v)+'</td></tr>').join('')+'</table></div><p>תועלת: '+best.expected_benefit+' · סף: '+s.threshold+'</p>':'אין מועמד חוקי בנקודה הזאת.';document.getElementById('raw').textContent=JSON.stringify(s,null,2);}
function draw(){current=reports.find(r=>r.team_name===team.value&&r.match_id===match.value);document.getElementById('summary').textContent=current.snapshots.filter(s=>s.selected).length+' מתוך '+current.snapshots.length+' נקודות עברו את הסף — אין פירוש הדבר שזה מספר החילופים.';document.getElementById('rows').innerHTML=current.snapshots.map((s,i)=>{const b=s.alternatives[0]||{};return '<tr data-i="'+i+'"><td>'+s.minute+'</td><td>'+(s.selected?'חילוף':'ללא חילוף')+'</td><td dir="ltr">'+(b.out_player?.name||'—')+'</td><td dir="ltr">'+(b.in_player?.name||'—')+'</td><td>'+fmt(b.expected_benefit)+'</td><td>'+fmt(b.score_components?.outgoing_fatigue)+'</td><td>'+s.unavailable_profile_ids.length+'</td></tr>'}).join('');document.getElementById('history').innerHTML='<table><tr><th>דקה</th><th>יוצא</th><th>נכנס</th><th>דירוג בנקודה קודמת</th><th>תועלת</th></tr>'+current.historical_substitutions.map(h=>'<tr><td>'+h.minute+'</td><td dir="ltr">'+h.out_name+'</td><td dir="ltr">'+h.in_name+'</td><td>'+(h.candidate_rank??'לא זמין / לא נתמך')+'</td><td>'+fmt(h.candidate?.expected_benefit)+'</td></tr>').join('')+'</table>';show(current.snapshots.find(s=>s.selected)||current.snapshots[0]);}
function selectTeam(){match.innerHTML='';for(const r of reports.filter(r=>r.team_name===team.value))match.add(new Option(r.fixture,r.match_id));draw();}team.onchange=selectTeam;match.onchange=draw;document.getElementById('rows').onclick=e=>{const tr=e.target.closest('tr[data-i]');if(tr)show(current.snapshots[Number(tr.dataset.i)]);};selectTeam();</script></html>'''
    browser_reports = copy.deepcopy(reports)
    for report in browser_reports:
        for s in report['snapshots']:
            # Full player windows remain in the compressed downloadable JSON.
            s.pop('player_live',None)
    (out/'index.html').write_text(html.replace('PAYLOAD',json.dumps(browser_reports,ensure_ascii=False).replace('</','<\\/')),encoding='utf-8',newline='\n')
    print(f'{len(reports)} team replays; {len(rows)} checkpoints; {sum(s["decision"]=="SUBSTITUTION" for s in rows)} positive checkpoints')


if __name__ == '__main__':
    main()
