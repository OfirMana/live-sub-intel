"""Explain the engine's decision at one checkpoint of a replayed match.

    python scripts/explain_recommendation.py --match 3754305 --team Liverpool --minute 75
    python scripts/explain_recommendation.py --minute 75 --audience all --lang en

Uses Microsoft Foundry when FOUNDRY_ENDPOINT, FOUNDRY_API_KEY and FOUNDRY_DEPLOYMENT are
set (pip install -e ".[llm]"); otherwise prints the deterministic template.
"""
import argparse
import json
from pathlib import Path

from benchmark_demo import replay
from subintel.demo_data import load_demo_profiles
from subintel.demo_live import TEAM_IDS
import os

from subintel.narrative import AUDIENCES, LANGUAGES, explain, v1_base_url

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--match', default='3754305', help='StatsBomb match id (default: Liverpool 3-3 Arsenal)')
    ap.add_argument('--team', default='Liverpool', choices=sorted(TEAM_IDS))
    ap.add_argument('--minute', type=int, default=75, help='checkpoint minute, a multiple of 5')
    ap.add_argument('--audience', default='all', choices=('all', *AUDIENCES))
    ap.add_argument('--lang', default='he', choices=tuple(LANGUAGES))
    ap.add_argument('--facts', action='store_true', help='also print the facts sent to the model')
    args = ap.parse_args()

    evidence = json.loads((ROOT / 'demo_data/source_evidence.json').read_text(encoding='utf-8'))
    report = replay(args.match, TEAM_IDS[args.team], load_demo_profiles(), evidence)
    snapshot = next((s for s in report['snapshots'] if s['checkpoint_minute'] == args.minute), None)
    if snapshot is None:
        raise SystemExit(f'No checkpoint at minute {args.minute}; use a multiple of 5 between 5 and 90.')
    if os.environ.get('FOUNDRY_ENDPOINT'):
        print(f"Foundry: {v1_base_url(os.environ['FOUNDRY_ENDPOINT'])} · deployment "
              f"{os.environ.get('FOUNDRY_DEPLOYMENT', '(missing)')} · key {'set' if os.environ.get('FOUNDRY_API_KEY') else 'MISSING'}\n")
    audiences = AUDIENCES if args.audience == 'all' else (args.audience,)
    for i, audience in enumerate(audiences):
        result = explain(snapshot, audience, args.lang)
        if args.facts and i == 0:
            print(json.dumps(result['facts'], ensure_ascii=False, indent=2))
        note = ''
        if result['source'] == 'template':
            note = (f" (LLM error: {result['llm_error']})" if 'llm_error' in result else
                    f" (LLM text rejected, invented numbers: {result['invented_numbers']})" if 'invented_numbers' in result else
                    ' (set FOUNDRY_* to use the LLM)')
        print(f'[{audience} · {result["source"]}{note}]\n{result["text"]}\n')


if __name__ == '__main__':
    main()
