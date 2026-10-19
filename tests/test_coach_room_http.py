import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from serve_coach_room import create_room, make_handler


def test_coach_room_http_and_live_lineups_match_past_only_engine():
    bootstrap, evaluate = create_room()
    assert len(bootstrap['profiles'])==72
    assert bootstrap['profiles']['10955']['position_suitability']['Center Back']['fit']==0
    assert bootstrap['version']=='coach-room-v2'
    server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(bootstrap,evaluate))
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    def request(minute, **config):
        body=dict(match_id='3754305',team_id='24',minute=minute,config=config)
        req=Request(base+'/api/evaluate',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(req) as response:
                return response.status,json.load(response)
        except HTTPError as error:
            return error.code,json.load(error)
    try:
        status,rec=request(65,stance='attack',objective='win',formation='4-4-2')
        assert status==200 and rec['coach_config']['objective']=='win'
        assert rec['observed']['formation']=='4-3-3'
        view=next(v for v in bootstrap['views'] if v['team_id']=='24')
        f=bootstrap['fixtures']['3754305']
        elapsed=65+f['first_half_extra']
        timeline=[v for v in view['lineup_timeline'] if v['elapsed']<elapsed]
        assert {p['player_id'] for p in timeline[-1]['lineup']}=={p['player_id'] for p in rec['observed']['lineup']}
        assert request(70)[1]['observed']['formation']=='4-4-2'
        assert request(65,freshness_cap=999)[0]==400
        assert request(67)[0]==400
        with urlopen(base+'/') as response:
            assert 'חדר המאמן' in response.read().decode('utf-8')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
