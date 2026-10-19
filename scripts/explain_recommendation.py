"""Explain a saved engine result; --require-azure makes the live smoke test strict."""
import argparse
import json
from pathlib import Path

from subintel.narrative import NarrativeRequest, NarrativeService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('--minute', type=int)
    parser.add_argument('--team')
    parser.add_argument('--language', choices=('en', 'he'), default='en')
    parser.add_argument('--audience', choices=('analyst', 'coach', 'fan'), default='analyst')
    parser.add_argument('--provider', choices=('deterministic', 'azure'), default='deterministic')
    parser.add_argument('--require-azure', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding='utf-8'))
    if isinstance(payload, list):
        matches = [r for r in payload if (args.minute is None or r['state']['minute'] == args.minute)
                   and (args.team is None or str(r['team_id']) == args.team)]
        if len(matches) != 1:
            parser.error('Choose exactly one checkpoint with --minute and --team')
        payload = matches[0]
    result = NarrativeService.from_env(args.provider).explain(NarrativeRequest(
        recommendation=payload, language=args.language, audience=args.audience))
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding='utf-8')
    else:
        print(text)
    if args.require_azure and result['source'] != 'azure_openai':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
