"""Offline coverage audit: every offered plan, audience and locale; no model calls."""
from collections import Counter
import argparse
import json
from pathlib import Path
import re

from serve_coach_room import create_room
from integrated_app import annotate
from subintel.auto_plans import AutoConfig
from subintel.plan_narrative import fact_bundle, identified, sentences, default_ids


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-mode',choices=('historical','synthetic'),default='historical')
    args=parser.parse_args()
    if args.data_mode=='synthetic':
        from synthetic_coach_room import create_synthetic_room
        bootstrap,evaluate=create_synthetic_room()
    else:bootstrap,evaluate=create_room()
    counts=Counter();decisions=Counter()
    for view in bootstrap['views']:
        for minute in range(5,91,5):
            snapshot=annotate(evaluate(view['match_id'],view['team_id'],minute,AutoConfig().model_dump_json()))
            counts['checkpoints']+=1;decisions[snapshot['recommendation']]+=1
            ids=[p['plan_id'] for p in identified(snapshot)]
            if snapshot['recommendation']=='NO_SUBSTITUTION':ids.append('wait')
            assert len(set(ids))==len(ids)
            for plan_id in ids:
                facts=fact_bundle(snapshot,plan_id);counts['plan_contexts']+=1
                for audience in ('fan','analyst','broadcaster'):
                    for lang in ('en','he'):
                        bank=sentences(facts,audience,lang)
                        chosen=default_ids(bank,audience)
                        text=' '.join(bank[k] for k in chosen)
                        assert text and chosen[0]=='decision'
                        if audience=='broadcaster':assert not re.search(r'\d|%',text)
                        if 'tradeoff' in bank:assert 'tradeoff' in chosen
                        counts['rendered_explanations']+=1
    report=dict(kind='OFFLINE_CONTRACT_COVERAGE_NOT_TACTICAL_ACCURACY',counts=dict(counts),
        decisions=dict(decisions),provider_calls=0,data_mode=args.data_mode,
        scope=f"{len(bootstrap['views'])} team views, 18 checkpoints, every offered pair/tactical/wait plan, 3 audiences and 2 languages")
    filename='synthetic_explanation_audit.json' if args.data_mode=='synthetic' else 'integrated_explanation_audit.json'
    path=Path(__file__).resolve().parents[1]/'docs/research'/filename
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
