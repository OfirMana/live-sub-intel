"""Game-room server: page, health, explanation validation and caching (no network, no model)."""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from serve_app import App, make_handler

OPTION = dict(out_player=dict(id='1', name='Emre Can'), in_player=dict(id='2', name='Joe Allen'),
              expected_changes=dict(threat=-3.8, creation=-1.0, progression=1.1, retention=7.2, defense=-9.1),
              score_components=dict(outgoing_fatigue=.59), decision_basis='FRESH_LEGS', change_type='LIKE_FOR_LIKE',
              evidence_strength=.14, expected_benefit=.153)
PAYLOAD = dict(fixtures={}, profiles={}, cutoff='2016-01-13', source='test', views=[dict(
    team='Liverpool', team_id='24', match_id='3754305',
    snapshots=[dict(minute=75, state=dict(minute=75, goal_diff=-1, subs_left=2), threshold=.15,
                    team_needs=dict(threat=.63, creation=.58, progression=.56, retention=.31, defense=.42),
                    selected=OPTION, no_substitution_reason=None, alternatives=[OPTION])])])


def serve(explain_fn):
    calls = []

    def recording(snapshot, audience, lang):
        calls.append((snapshot['minute'], snapshot['team_id'], snapshot['recommendation'], audience, lang))
        return explain_fn(snapshot, audience, lang)

    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(App(PAYLOAD, recording)))
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def get(path):
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        conn.request('GET', path)
        r = conn.getresponse()
        body = r.read().decode('utf-8')
        return r.status, (json.loads(body) if r.getheader('Content-Type', '').startswith('application/json') else body)

    return get, calls, server


@pytest.fixture
def llm_app():
    get, calls, server = serve(lambda s, a, l: dict(text='Joe Allen on, fresh legs.', source='llm', audience=a, lang=l, facts={}))
    yield get, calls
    server.shutdown()


def test_page_has_the_explanation_panel_enabled(llm_app):
    get, _ = llm_app
    status, html = get('/')
    assert status == 200 and 'window.EXPLAIN_API="/api/explain"' in html and 'id="explain"' in html


def test_health(llm_app):
    get, _ = llm_app
    status, body = get('/healthz')
    assert status == 200 and body['status'] == 'ok' and 'llm_configured' in body


def test_model_answers_are_cached_per_checkpoint(llm_app, monkeypatch):
    monkeypatch.setenv('FOUNDRY_DEPLOYMENT', 'gpt-4.1-mini')
    get, calls = llm_app
    path = '/api/explain?match=3754305&team=24&minute=75&audience=fan&lang=he'
    first, second = get(path), get(path)
    assert first == second and first[0] == 200
    assert first[1]['source'] == 'llm' and first[1]['model'] == 'gpt-4.1-mini'
    assert calls == [(75, '24', 'SUBSTITUTION', 'fan', 'he')]
    get('/api/explain?match=3754305&team=24&minute=75&audience=analyst&lang=en')
    assert len(calls) == 2


@pytest.mark.parametrize('query,status', [
    ('match=3754305&team=24', 400),
    ('match=3754305&team=24&minute=abc', 400),
    ('match=3754305&team=24&minute=70', 404),
    ('match=3754305&team=1&minute=75', 404),
    ('match=3754305&team=24&minute=75&audience=coach', 404),
    ('match=3754305&team=24&minute=75&lang=fr', 404),
])
def test_only_known_checkpoints_reach_the_model(llm_app, query, status):
    get, calls = llm_app
    assert get(f'/api/explain?{query}')[0] == status
    assert calls == []


def test_template_answers_are_not_cached_and_hide_error_details():
    get, calls, server = serve(lambda s, a, l: dict(text='template text', source='template', audience=a, lang=l,
                                                     facts={}, llm_error='APIConnectionError: https://secret-host'))
    try:
        path = '/api/explain?match=3754305&team=24&minute=75'
        status, body = get(path)
        get(path)
        assert status == 200 and body['note'] == 'LLM unavailable' and 'secret-host' not in json.dumps(body)
        assert len(calls) == 2  # a transient failure is retried on the next click
    finally:
        server.shutdown()


def test_unknown_path_is_404(llm_app):
    get, _ = llm_app
    assert get('/etc/passwd')[0] == 404
