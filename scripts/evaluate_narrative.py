"""Offline contract audit across saved research checkpoints; not a live-model eval."""
import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from subintel.narrative import NarrativeRequest, NarrativeService

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=ROOT / 'docs/research/four_team_benchmark.json.gz')
    parser.add_argument('--out', type=Path, default=ROOT / 'data/narrative/offline_audit.json')
    args = parser.parse_args()
    opener = gzip.open if args.input.suffix == '.gz' else open
    with opener(args.input, 'rt', encoding='utf-8') as handle:
        reports = json.load(handle)
    service = NarrativeService()
    counts = Counter()
    examples = {}
    for report in reports:
        for rec in report['snapshots']:
            original = json.dumps(rec, sort_keys=True)
            for language in ('en', 'he'):
                for audience in ('analyst', 'coach', 'fan'):
                    result = service.explain(NarrativeRequest(recommendation=rec, language=language, audience=audience))
                    assert result['decision'] == rec['recommendation']
                    assert result['source'] == 'deterministic_fallback'
                    assert result['plan']['in_player_id'] == (rec['selected']['in_player']['id'] if rec['selected'] else None)
                    assert all(f['text'] in result['text'] for f in result['evidence'])
                    counts[f'{language}_{audience}'] += 1
                    examples.setdefault(f"{rec['recommendation']}_{language}", result)
            assert json.dumps(rec, sort_keys=True) == original
    result = dict(kind='OFFLINE_CONTRACT_AUDIT_NOT_LIVE_LLM_QUALITY',
                  team_match_replays=len(reports), checkpoints=sum(len(r['snapshots']) for r in reports),
                  cases=sum(counts.values()), modes=dict(counts), live_azure_calls=0,
                  decision_preserved=True, inputs_unchanged=True, examples=examples)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'examples'}, indent=2))


if __name__ == '__main__':
    main()
