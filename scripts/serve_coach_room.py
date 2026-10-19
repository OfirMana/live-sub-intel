"""Local coach-control research room. No LLM service or teammate demo changes."""
import argparse
import json
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, ValidationError

from collect_demo_evidence import TARGETS, fetch
from export_match_replay import key_events
from subintel.coach_room import CoachConfig, CoachReplay, FORMATIONS, slot
from subintel.demo_data import load_demo_profiles

ROOT = Path(__file__).resolve().parents[1]
TEAM_IDS = {'Liverpool':'24', 'Arsenal':'1', 'Chelsea':'33', 'Tottenham Hotspur':'38'}


class RoomRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    match_id: str
    team_id: str
    minute: int
    config: CoachConfig = CoachConfig()


def create_room():
    from subintel.coach_room import recommend_coach
    dataset = load_demo_profiles()
    evidence = json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    matches = {str(m['match_id']): m for m in fetch('matches/2/27.json')}
    fixtures, replays, views = {}, {}, []
    for team, mid in TARGETS.items():
        tid = TEAM_IDS[team]
        raw, lineup = fetch(f'events/{mid}.json'), fetch(f'lineups/{mid}.json')
        replays[mid, tid] = CoachReplay(dataset, evidence, raw, lineup, mid, tid)
        initial = replays[mid, tid].state_at(0)[1]
        extra = max(e['minute']+e['second']/60 for e in raw if e['period']==1)-45
        shape, formation, timeline = initial['lineup'], initial['formation'], [dict(elapsed=0, **initial)]
        for event in raw:
            if str(event.get('team', {}).get('id')) != tid:
                continue
            kind = event['type']['name']
            if kind == 'Tactical Shift':
                formation = '-'.join(str(event['tactics']['formation']))
                shape = [slot(p['position']['name'], str(p['player']['id']), replays[mid, tid].roster) for p in event['tactics']['lineup']]
            elif kind == 'Substitution':
                old, new = str(event['player']['id']), str(event['substitution']['replacement']['id'])
                shape = [slot(p['position'], new, replays[mid, tid].roster) if p['player_id']==old else p for p in shape]
            elif event.get('bad_behaviour', {}).get('card', {}).get('name') in ('Red Card', 'Second Yellow') or event.get('foul_committed', {}).get('card', {}).get('name') in ('Red Card', 'Second Yellow'):
                shape = [p for p in shape if p['player_id'] != str(event['player']['id'])]
            else:
                continue
            timeline.append(dict(elapsed=event['minute']+event['second']/60+(max(extra,0) if event['period']==2 else 0), formation=formation, lineup=shape))
        views.append(dict(team=team, team_id=tid, match_id=mid, lineup_timeline=timeline))
        if mid not in fixtures:
            match = matches[mid]
            events, extra = key_events(raw, mid)
            fixtures[mid] = dict(id=mid, date=match['match_date'], first_half_extra=extra,
                home=dict(id=str(match['home_team']['home_team_id']), name=match['home_team']['home_team_name']),
                away=dict(id=str(match['away_team']['away_team_id']), name=match['away_team']['away_team_name']),
                events=events, final_elapsed=max(e['minute']+e['second']/60+extra for e in raw if e['period']==2)+.001)
    bootstrap = dict(fixtures=fixtures, views=views, formations=list(FORMATIONS),
                     profiles={str(p['player_id']):p for p in dataset['players']}, version='coach-room-v1')
    @lru_cache(maxsize=64)
    def evaluate(mid, tid, minute, config_json):
        ms, observed = replays[mid, tid].state_at(minute)
        return recommend_coach(ms, tid, observed, replays[mid, tid].roster, CoachConfig.model_validate_json(config_json))
    return bootstrap, evaluate


def make_handler(bootstrap, evaluate):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content_type='application/json; charset=utf-8'):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == '/api/bootstrap':
                return self.reply(200, bootstrap)
            if path == '/health':
                return self.reply(200, dict(status='ok', version='coach-room-v1', llm=False))
            files = {'/':'index.html', '/app.js':'app.js', '/styles.css':'styles.css'}
            if path in files:
                mime = 'text/html' if path == '/' else 'text/javascript' if path.endswith('.js') else 'text/css'
                return self.reply(200, (ROOT/'web/coach-room'/files[path]).read_bytes(), mime+'; charset=utf-8')
            self.reply(404, dict(error='NOT_FOUND'))

        def do_POST(self):
            if urlparse(self.path).path != '/api/evaluate':
                return self.reply(404, dict(error='NOT_FOUND'))
            origin = self.headers.get('Origin')
            if origin and urlparse(origin).netloc != self.headers.get('Host'):
                return self.reply(403, dict(error='CROSS_ORIGIN_DISABLED'))
            try:
                n = int(self.headers.get('Content-Length', '0'))
                if not 0 < n <= 8192:
                    return self.reply(413, dict(error='INVALID_BODY_SIZE'))
                r = RoomRequest.model_validate_json(self.rfile.read(n))
                result = evaluate(r.match_id, r.team_id, r.minute, r.config.model_dump_json())
            except (ValueError, KeyError, TypeError, ValidationError):
                return self.reply(400, dict(error='INVALID_CHECKPOINT_OR_CONFIG'))
            self.reply(200, result)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8774)
    args = parser.parse_args()
    bootstrap, evaluate = create_room()
    print(f'Coach room: http://127.0.0.1:{args.port}/ · historical research, schematic pitch, no LLM', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(bootstrap, evaluate)).serve_forever()


if __name__ == '__main__':
    main()
