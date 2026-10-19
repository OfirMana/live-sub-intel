"""Run the isolated explanation UI/API against the existing synthetic engine."""
import argparse
import json
from http.server import ThreadingHTTPServer
from pathlib import Path

from run_synthetic_demo import simulate
from subintel.demo_data import load_demo_profiles
from subintel.narrative import NarrativeService
from subintel.narrative_http import make_handler

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8772)
    parser.add_argument('--provider', choices=('deterministic', 'azure'), default='deterministic')
    args = parser.parse_args()
    service = NarrativeService.from_env(args.provider)
    evidence = json.loads((ROOT / 'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    _, examples = simulate(load_demo_profiles(), evidence)
    handler = make_handler(service, examples, ROOT / 'web/narrative/index.html')
    print(f'Narrative demo: http://127.0.0.1:{args.port} · provider requested: {args.provider}', flush=True)
    if service.unavailable_reason:
        print('Azure is not configured; responses are explicitly labelled deterministic fallback.', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), handler).serve_forever()


if __name__ == '__main__':
    main()
