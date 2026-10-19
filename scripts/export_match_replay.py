"""Build an offline, step-by-step matchweek 21 review UI from frozen model output."""
from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from benchmark_demo import replay
from collect_demo_evidence import TARGETS, fetch
from subintel.demo_data import load_demo_profiles
from subintel.statsbomb import ROLE_BY_POSITION, convert_event
from subintel.schema import EventType

ROOT = Path(__file__).resolve().parents[1]
TEAM_IDS = {'Liverpool':'24','Arsenal':'1','Chelsea':'33','Tottenham Hotspur':'38'}


def key_events(raw, mid):
    """Preserve chronological periods and deduplicate provider half markers."""
    first_end = max(e['minute']+e['second']/60 for e in raw if e['period']==1)
    extra = max(first_end-45,0)
    seen, result = set(), []
    for item in raw:
        ev = convert_event(item,mid)
        if ev is None or ev.period not in (1,2):
            continue
        kind = ev.type.value
        if ev.type not in (EventType.SHOT,EventType.OWN_GOAL,EventType.CARD,
                            EventType.SUBSTITUTION,EventType.PERIOD_START,EventType.PERIOD_END):
            continue
        if ev.type in (EventType.PERIOD_START,EventType.PERIOD_END):
            marker=(kind,ev.period)
            if marker in seen:
                continue
            seen.add(marker)
        if ev.goal:
            kind='goal'
        result.append(dict(id=ev.event_id,kind=kind,period=ev.period,minute=ev.minute,second=ev.second,
                           elapsed=ev.minute+ev.second/60+(extra if ev.period==2 else 0),
                           team_id=ev.team_id,player_id=ev.player_id,
                           player=item.get('player',{}).get('name'),
                           replacement=item.get('substitution',{}).get('replacement',{}).get('name'),
                           replacement_id=ev.replacement_id,card=ev.card,xg=ev.xg,
                           outcome=item.get('shot',{}).get('outcome',{}).get('name')))
    return result,extra


def build_payload():
    data=load_demo_profiles()
    evidence=json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    matches={str(m['match_id']):m for m in fetch('matches/2/27.json')}
    fixtures={}
    views=[]
    for team,mid in TARGETS.items():
        tid=TEAM_IDS[team]
        if mid not in fixtures:
            match=matches[mid]
            raw=fetch(f'events/{mid}.json')
            events,extra=key_events(raw,mid)
            fixtures[mid]=dict(id=mid,date=match['match_date'],matchweek=match['match_week'],
                               home=dict(id=str(match['home_team']['home_team_id']),name=match['home_team']['home_team_name']),
                               away=dict(id=str(match['away_team']['away_team_id']),name=match['away_team']['away_team_name']),
                               first_half_extra=extra,
                               active_roles={str(p['player_id']):ROLE_BY_POSITION[p['positions'][0]['position']].value
                                             for t in fetch(f'lineups/{mid}.json') for p in t['lineup'] if p['positions']},
                               final_elapsed=max(e['minute']+e['second']/60+extra for e in raw if e['period']==2)+.001,
                               events=events)
        report=replay(mid,tid,data,evidence,top_options=1000)
        snapshots=[]
        for s in report['snapshots']:
            live={p['player_id']:{k:p.get(k) for k in ('dimensions','fatigue','minutes_played','evidence_strength')}
                  for p in s['player_live']}
            snapshots.append({k:s[k] for k in ('minute','state','team_needs','threshold','max_tactical_loss_for_freshness','selected','no_substitution_reason','alternatives','unavailable_profile_ids')}|dict(live=live))
        views.append(dict(team=team,team_id=tid,match_id=mid,snapshots=snapshots))
    profiles={str(p['player_id']):{k:p[k] for k in ('player_id','name','team','primary_role','positions','general','recent','season','physical','provenance')}
              for p in data['players']}
    return dict(fixtures=fixtures,views=views,profiles=profiles,cutoff=evidence['cutoff'],
                source='StatsBomb Open Data · historical events, deterministic model recommendations')


def render_html(payload,explain_api=None):
    """One self-contained page. explain_api enables the explanation panel (server only)."""
    web=ROOT/'web/match-replay'
    html=(web/'index.html').read_text(encoding='utf-8')
    html=html.replace('/* STYLES */',(web/'styles.css').read_text(encoding='utf-8'))
    html=html.replace('/* PAYLOAD */',json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('</','<\\/'))
    app=(web/'app.js').read_text(encoding='utf-8')
    if explain_api:
        app=f'window.EXPLAIN_API={json.dumps(explain_api)};\n'+app
    return html.replace('/* APP */',app)


def main():
    payload=build_payload()
    out=ROOT/'docs/match-replay'
    out.mkdir(exist_ok=True)
    (out/'index.html').write_text(render_html(payload),encoding='utf-8',newline='\n')
    with ZipFile(out/'match-replay.zip','w',ZIP_DEFLATED) as z:
        z.write(out/'index.html','index.html')
        z.writestr('READ_ME_FIRST.txt','חלצו ופתחו index.html. בחרו קבוצה, התקדמו חמש דקות ולחצו בדוק חילופים.\nשחזור היסטורי של מחזור 21; המלצות אינן משנות את האירועים.\n'.encode('utf-8'))
    print(f'Exported {len(payload["views"])} team views / {len(payload["fixtures"])} fixtures -> {out}')


if __name__=='__main__':
    main()
