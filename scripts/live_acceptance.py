"""Live acceptance against a deployed coach room: a bounded set of fresh explanation requests.

    python scripts/live_acceptance.py https://<app>.azurewebsites.net

Records, per request: build, team/minute/context, plan identity, audience, locale,
source, translation status, cache status, latency and any safe diagnostic. Requests
are spaced to stay under the server's per-minute model budget. Only what is listed
in the report was checked; nothing else is claimed. Standard library only.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import urllib.request

MATCH = 'synthetic-demo'
CONTEXT = dict(stance='attack', objective='win', formation='auto', freshness_cap=1)
EXTRA_LOCALES = ('ar', 'es', 'fr', 'de', 'it', 'pt', 'ja', 'zh-Hans')


def call(base, path, body=None, timeout=60):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base.rstrip('/') + path, data=data, headers={'Content-Type': 'application/json'})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.load(response), round(time.monotonic() - started, 2)
    except urllib.error.HTTPError as error:
        return error.code, None, round(time.monotonic() - started, 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('base')
    parser.add_argument('--spacing', type=float, default=3.0, help='seconds between explanation requests')
    parser.add_argument('--out', default=None)
    args = parser.parse_args()
    _, health, _ = call(args.base, '/healthz')
    _, bootstrap, _ = call(args.base, '/api/bootstrap')
    snapshots = {}

    def evaluate(team, minute, **config):
        key = (team, minute, json.dumps(config, sort_keys=True))
        if key not in snapshots:
            status, body, _ = call(args.base, '/api/evaluate', dict(match_id=MATCH, team_id=team, minute=minute, config=dict(CONTEXT, **config)))
            assert status == 200, (status, key)
            snapshots[key] = body
        return snapshots[key]

    def pick(snap, kind):
        alts = snap['alternatives']
        if kind == 'selected':
            return snap['selected_plan_id']
        if kind == 'second':
            return alts[1]['plan_id'] if len(alts) > 1 else None
        if kind == 'rejected':
            return next((p['plan_id'] for p in alts if not p['recommended']), None)
        if kind == 'formation':
            return next((p['plan_id'] for p in alts if p.get('change_type') == 'FORMATION_CHANGE'), None)
        return kind  # 'tactical' or 'wait'

    cases = [('1', 65, {}, 'second', a, 'en') for a in ('broadcaster', 'analyst', 'coach')]
    cases += [('1', 65, {}, 'second', 'broadcaster', 'he'), ('1', 65, {}, 'second', 'coach', 'he'),
              ('1', 65, {}, 'selected', 'analyst', 'en'), ('1', 65, {}, 'rejected', 'broadcaster', 'en'),
              ('1', 65, {}, 'formation', 'analyst', 'en'), ('24', 65, {}, 'selected', 'analyst', 'en'),
              ('24', 65, {}, 'second', 'coach', 'en'), ('1', 85, {}, 'tactical', 'coach', 'en'),
              ('1', 90, {}, 'wait', 'analyst', 'en'), ('24', 85, {}, 'selected', 'broadcaster', 'en'),
              ('1', 85, dict(objective='draw'), 'selected', 'coach', 'en')]
    cases += [('1', 65, {}, 'second', 'analyst', lang) for lang in EXTRA_LOCALES]
    rows = []
    for team, minute, config, kind, audience, lang in cases:
        snap = evaluate(team, minute, **config)
        plan_id = pick(snap, kind)
        if plan_id is None or (plan_id == 'tactical' and not snap.get('tactical_plan')) or (plan_id == 'wait' and snap['recommendation'] != 'NO_SUBSTITUTION'):
            rows.append(dict(team=team, minute=minute, config=config, kind=kind, audience=audience, lang=lang, skipped='plan not offered here'))
            continue
        body = dict(match_id=MATCH, team_id=team, minute=minute, config=dict(CONTEXT, **config), plan_id=plan_id, audience=audience, lang=lang)
        status, r, seconds = call(args.base, '/api/explain', body)
        row = dict(team=team, minute=minute, config=config, kind=kind, plan_id=plan_id, audience=audience, lang=lang, http=status, seconds=seconds)
        if r:
            plan = next((p for p in snap['alternatives'] if p['plan_id'] == plan_id), None)
            translation = r.get('translation') or {}
            row.update(source=r['source'], note=r.get('note'), model=r.get('model'), cached=r.get('cached'), output_lang=r.get('output_lang'),
                       translation=translation.get('status'), translation_note=translation.get('note'),
                       translation_rule=(translation.get('diagnostic') or {}).get('rule'),
                       diagnostic=(r.get('diagnostic') or {}).get('code'), fact_ids=r['fact_ids'], text=r['text'],
                       plan_identity_ok=r['plan_id'] == plan_id and (plan is None or (plan['in_player']['name'] in r['text'] and plan['out_player']['name'] in r['text'])),
                       broadcaster_has_digits=bool(re.search(r'\d', r['text'])) if audience == 'broadcaster' else None)
        rows.append(row)
        print(f"{team} {minute:>2} {kind:<9} {audience:<11} {lang:<7} http={status} {row.get('source')}/{row.get('translation')} "
              f"cached={row.get('cached')} {seconds}s {row.get('note') or ''} {row.get('translation_note') or ''}", flush=True)
        time.sleep(args.spacing)
    _, after, _ = call(args.base, '/healthz')
    report = dict(kind='LIVE_AZURE_ACCEPTANCE', at=datetime.now(timezone.utc).isoformat(), base=args.base,
                  build_sha=(health or {}).get('build_sha'), data_mode=(health or {}).get('data_mode'),
                  generator=(bootstrap or {}).get('generator'), llm_configuration=(health or {}).get('llm_configuration'),
                  translation_catalog_after=(after or {}).get('translation_catalog'), requests=rows,
                  summary=dict(explanations=sum(1 for r in rows if 'http' in r), llm=sum(1 for r in rows if r.get('source') == 'llm'),
                               translated=sorted({r['lang'] for r in rows if r.get('translation') == 'model'}),
                               translation_fallback=sorted({r['lang'] for r in rows if r.get('translation') == 'fallback'}),
                               identity_failures=[r['plan_id'] for r in rows if r.get('plan_identity_ok') is False],
                               broadcaster_with_digits=[r['plan_id'] for r in rows if r.get('broadcaster_has_digits')]))
    out = Path(args.out or Path(__file__).resolve().parents[1]/'docs/research'/f"live_acceptance_{datetime.now(timezone.utc):%Y%m%d}.json")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], indent=2, ensure_ascii=False))
    print(f'Report: {out}')


if __name__ == '__main__':
    main()
