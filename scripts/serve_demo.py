"""Local HTTP/SSE demo: feed synthetic events into a fresh engine per viewer."""
import argparse
import json
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from itertools import groupby
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from run_synthetic_demo import grounded_explanation, simulate, write_browser_demo
from subintel.demo_data import load_demo_profiles
from subintel.demo_live import make_match, recommend_demo
from subintel.schema import Event

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--seconds-per-minute', type=float, default=.3)
    ap.add_argument('--directory', type=Path, default=ROOT/'data/synthetic_demo')
    args = ap.parse_args()
    dataset = load_demo_profiles()
    evidence = json.loads((ROOT/'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    events, snapshots = simulate(dataset, evidence)
    for snapshot in snapshots:
        snapshot['explanation'] = grounded_explanation(snapshot)
    args.directory.mkdir(parents=True, exist_ok=True)
    write_browser_demo(args.directory/'index.html', snapshots)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(args.directory), **kw)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == '/health':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status":"ok","source":"SYNTHETIC"}')
                return
            if url.path != '/stream':
                return super().do_GET()
            tid = parse_qs(url.query).get('team', ['24'])[0]
            if tid not in ('24', '1'):
                self.send_error(400, 'Unknown demo team')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            ms = make_match(dataset, evidence)
            try:
                for minute, group in groupby(events, key=lambda e: e['minute']):
                    for event in group:
                        ms.feed(Event(**event))
                    rec = recommend_demo(ms, tid)
                    rec['event_source'] = 'SYNTHETIC_SCRIPTED_POSSESSIONS'
                    rec['explanation'] = grounded_explanation(rec)
                    self.wfile.write(('data: '+json.dumps(rec, ensure_ascii=False)+'\n\n').encode('utf-8'))
                    self.wfile.flush()
                    time.sleep(max(args.seconds_per_minute, 0))
                self.wfile.write(b'event: complete\ndata: {}\n\n')
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    print(f'Synthetic event stream demo: http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
