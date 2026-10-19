"""The game room and its explanation API in one small web app, locally or on Azure.

    python scripts/serve_app.py                                # http://127.0.0.1:8000
    python scripts/serve_app.py --host 0.0.0.0 --port $PORT    # container / App Service

The Foundry key stays on the server (FOUNDRY_* environment variables, see
docs/FOUNDRY_HE.md). /api/explain only answers for the precomputed checkpoints the
game room shows, and caches every model answer per (match, team, minute, audience,
language), so even a public deployment makes at most a few hundred model calls.
"""
import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Runs without PYTHONPATH or an installed package, e.g. on Azure App Service.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from export_match_replay import build_payload, render_html  # noqa: E402
from subintel.narrative import AUDIENCES, LANGUAGES, explain  # noqa: E402


class App:
    def __init__(self, payload, explain_fn=explain):
        self.html = render_html(payload, explain_api='/api/explain').encode('utf-8')
        self.snapshots = {}
        for view in payload['views']:
            for s in view['snapshots']:
                self.snapshots[(view['match_id'], view['team_id'], s['minute'])] = dict(
                    s, team_id=view['team_id'], recommendation='SUBSTITUTION' if s['selected'] else 'NO_SUBSTITUTION')
        self.explain_fn = explain_fn
        self.cache, self.lock = {}, threading.Lock()

    def explanation(self, query: str) -> tuple[int, dict]:
        q = {k: v[0] for k, v in parse_qs(query).items()}
        try:
            key = (q['match'], q['team'], int(q['minute']))
        except (KeyError, ValueError):
            return 400, {'error': 'match, team and minute are required'}
        audience, lang = q.get('audience', 'fan'), q.get('lang', 'he')
        if key not in self.snapshots or audience not in AUDIENCES or lang not in LANGUAGES:
            return 404, {'error': 'unknown checkpoint, audience or language'}
        cache_key = (*key, audience, lang)
        with self.lock:
            if cache_key in self.cache:
                return 200, self.cache[cache_key]
        result = self.explain_fn(self.snapshots[key], audience, lang)
        body = {k: result[k] for k in ('text', 'source', 'audience', 'lang', 'facts')}
        if result['source'] == 'llm':
            body['model'] = os.environ.get('FOUNDRY_DEPLOYMENT')
            with self.lock:
                self.cache[cache_key] = body
        else:
            # Details (endpoint, error text) go to the server log, not to the public.
            if 'llm_error' in result:
                print(f"LLM error for {cache_key}: {result['llm_error']}", file=sys.stderr)
            body['note'] = ('LLM unavailable' if 'llm_error' in result else
                            'LLM text failed the number check' if 'invented_numbers' in result else
                            'LLM not configured')
        return 200, body


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, content_type, data: bytes):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status, body):
            self._send(status, 'application/json; charset=utf-8', json.dumps(body, ensure_ascii=False).encode('utf-8'))

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ('/', '/index.html'):
                self._send(200, 'text/html; charset=utf-8', app.html)
            elif url.path == '/api/explain':
                self._json(*app.explanation(url.query))
            elif url.path == '/healthz':
                configured = all(os.environ.get(k) for k in ('FOUNDRY_ENDPOINT', 'FOUNDRY_API_KEY', 'FOUNDRY_DEPLOYMENT'))
                self._json(200, {'status': 'ok', 'llm_configured': configured})
            else:
                self._json(404, {'error': 'not found'})

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8000)))
    args = ap.parse_args()
    print('Preparing the game room (replays three matches)...', flush=True)
    app = App(build_payload())
    llm = 'on' if all(os.environ.get(k) for k in ('FOUNDRY_ENDPOINT', 'FOUNDRY_API_KEY', 'FOUNDRY_DEPLOYMENT')) else 'off (template only)'
    print(f'Game room: http://{args.host}:{args.port}  ·  LLM explanations: {llm}', flush=True)
    ThreadingHTTPServer((args.host, args.port), make_handler(app)).serve_forever()


if __name__ == '__main__':
    main()
