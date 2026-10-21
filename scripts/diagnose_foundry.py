"""Run INSIDE App Service to locate the failing layer, without printing keys.

Default: config/SDK preflight only, zero provider calls.
--live: one small bounded request. --full: also try one real game-plan request
if the small request succeeds. No key argument, raw error body or secret output.
"""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from subintel.foundry_runtime import configuration_summary, classify_failure
from subintel.narrative import foundry_client_from_env
from subintel.plan_narrative import Selection


def version(name):
    try:return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:return None


def diagnose(live=False,full=False):
    report=dict(versions={name:version(name) for name in ('openai','httpx','httpx2','pydantic')},
                configuration=configuration_summary(include_endpoint=True),checks=[],provider_calls=0)
    if not report['configuration']['configured']:
        report['outcome']='CONFIGURATION_FAILED';return report
    stage='client_setup';client=None
    try:
        client,deployment=foundry_client_from_env()
        report['checks'].append(dict(stage='client_setup',ok=True))
        if not live:
            report['outcome']='PREFLIGHT_ONLY_NOT_CONNECTIVITY';return report
        stage='minimal_provider_request';started=time.monotonic();report['provider_calls']+=1
        response=client.chat.completions.create(model=deployment,max_completion_tokens=150,
            response_format={'type':'json_object'},messages=[
                {'role':'system','content':'Return JSON only, exactly {"fact_ids":["decision"],"style":"direct"}.'},
                {'role':'user','content':'This is a connection smoke test. Return the requested JSON.'}])
        report['checks'].append(dict(stage=stage,ok=True,elapsed_ms=round((time.monotonic()-started)*1000)))
        stage='output_validation'
        selected=Selection.model_validate_json(response.choices[0].message.content or '')
        if selected.fact_ids!=['decision']:raise ValueError('unexpected fact IDs')
        report['checks'].append(dict(stage=stage,ok=True))
        report['outcome']='MINIMAL_MODEL_SUCCESS'
        if full:
            stage='full_plan_setup'
            from serve_coach_room import create_room
            from integrated_app import annotate
            from subintel.auto_plans import AutoConfig
            from subintel.plan_narrative import explain_plan
            _,evaluate=create_room()
            snapshot=annotate(evaluate('3754305','24',65,AutoConfig(stance='attack').model_dump_json()))
            plan_id=snapshot['alternatives'][1]['plan_id']
            started=time.monotonic();report['provider_calls']+=1
            result=explain_plan(snapshot,plan_id,'broadcaster','en',client=client,deployment=deployment)
            report['checks'].append(dict(stage='full_plan_explanation',ok=result['source']=='llm',
                plan_id=plan_id,source=result['source'],note=result['note'],diagnostic=result.get('diagnostic'),
                elapsed_ms=round((time.monotonic()-started)*1000)))
            report['outcome']='FULL_MODEL_SUCCESS' if result['source']=='llm' else 'FULL_PLAN_FAILED'
    except Exception as error:
        diag_stage='provider_request' if stage=='minimal_provider_request' else stage
        report['checks'].append(dict(stage=stage,ok=False,diagnostic=classify_failure(error,diag_stage)))
        report['outcome']='FAILED'
    finally:
        if client is not None:client.close()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Make one bounded provider request using existing server environment')
    parser.add_argument('--full',action='store_true',help='After the minimal check, test the actual second-choice game plan (implies --live)')
    args=parser.parse_args()
    report=diagnose(live=args.live or args.full,full=args.full)
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return 0 if report['outcome'] in ('PREFLIGHT_ONLY_NOT_CONNECTIVITY','MINIMAL_MODEL_SUCCESS','FULL_MODEL_SUCCESS') else 2


if __name__=='__main__':sys.exit(main())
