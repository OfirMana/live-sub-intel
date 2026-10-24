"""Contract, grounded semantics and concurrent model-call control for the live app."""
from concurrent.futures import ThreadPoolExecutor
import http.client
from http.server import ThreadingHTTPServer
import json
import re
import threading
from types import SimpleNamespace

import pytest

from integrated_app import IntegratedApp, ExplainRequest, ExplanationCache, annotate, make_handler
from serve_coach_room import create_room, RoomRequest
from subintel.auto_plans import AutoConfig
from subintel.plan_narrative import explain_plan, fact_bundle, sentences


@pytest.fixture(scope='module')
def room():
    return create_room()


@pytest.fixture(scope='module')
def snapshot(room):
    return annotate(room[1]('3754305','24',65,AutoConfig(stance='attack').model_dump_json()))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ('FOUNDRY_ENDPOINT','FOUNDRY_API_KEY','FOUNDRY_DEPLOYMENT'):
        monkeypatch.delenv(key,raising=False)


def client(text):
    calls=[]
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),calls


def test_second_alternative_is_explained_not_the_primary(snapshot):
    first,second=snapshot['alternatives'][:2]
    result=explain_plan(snapshot,second['plan_id'],'analyst','en')
    assert result['plan_id']==second['plan_id']
    assert second['out_player']['name'] in result['text']
    assert second['in_player']['name'] in result['text']
    assert first['out_player']['name'] not in result['text']
    assert result['facts']['inspected_plan']['proposed_lineup']==second['proposed_lineup']
    assert len(result['facts']['inspected_plan']['proposed_lineup'])==11


@pytest.mark.parametrize('lang',['en','he'])
def test_broadcaster_has_qualitative_tradeoffs_no_scores_or_percentages(snapshot,lang):
    for p in snapshot['alternatives'][:5]:
        r=explain_plan(snapshot,p['plan_id'],'broadcaster',lang)
        assert not re.search(r'\d|%',r['text'])
        assert 'score' not in r['text'].lower()
        assert p['in_player']['name'] in r['text']
        bank=sentences(r['facts'],'broadcaster',lang)
        if 'tradeoff' in bank:assert 'tradeoff' in r['fact_ids']


def test_rejected_plan_does_not_sound_recommended(snapshot):
    rejected=next(p for p in snapshot['alternatives'] if not p['recommended'])
    for audience in ('analyst','coach','broadcaster','fan'):
        r=explain_plan(snapshot,rejected['plan_id'],audience,'en')
        assert ('not recommended' in r['text'] or 'not justified' in r['text']) and 'suggested change' not in r['text']
        assert not r['facts']['inspected_plan']['recommended']


def test_tactical_only_plan_is_explained_without_inventing_a_swap(snapshot):
    r=explain_plan(snapshot,'tactical','analyst','en')
    assert 'without a substitution' in r['text']
    assert r['facts']['inspected_plan']['in_player'] is None
    assert r['facts']['inspected_plan']['repositioned']


def test_wait_and_unknown_plan(room,snapshot):
    early=annotate(room[1]('3754305','24',5,AutoConfig().model_dump_json()))
    assert 'decision window' in explain_plan(early,'wait')['text']
    with pytest.raises(ValueError):explain_plan(snapshot,'swap:made:up')


@pytest.mark.parametrize('bad',[
    'Emre Can replaces Joe Allen.',
    'Joe Allen improves defending by 9.1.',
    'A 59% chance of scoring.',
    '{"fact_ids":["decision","invented_probability"],"style":"direct"}',
    '{"fact_ids":["decision"],"style":"direct","text":"wrong names"}',
    '{"fact_ids":["decision","decision"],"style":"direct"}',
])
def test_arbitrary_prose_and_untrusted_claims_cannot_reach_the_ui(snapshot,bad):
    stub,_=client(bad)
    r=explain_plan(snapshot,snapshot['alternatives'][0]['plan_id'],client=stub,deployment='test')
    assert r['source']=='template' and r['note']=='LLM_TEXT_REJECTED'
    assert bad not in r['text']


def test_valid_model_selection_is_rendered_from_verified_facts(snapshot):
    plan_id=snapshot['alternatives'][0]['plan_id']
    bank=sentences(fact_bundle(snapshot,plan_id),'broadcaster','en')
    stub,calls=client(json.dumps(dict(fact_ids=list(bank),style='direct')))
    r=explain_plan(snapshot,plan_id,'broadcaster','en',client=stub,deployment='test')
    assert r['source']=='llm' and r['rendering']=='VERIFIED_FACT_SENTENCES'
    assert not re.search(r'\d|%',r['text'])
    assert calls[0]['max_completion_tokens']==250


def test_parallel_same_key_calls_provider_once():
    started=threading.Event();release=threading.Event();calls=[]
    def fn(*args):
        calls.append(1);started.set();assert release.wait(3)
        return dict(source='llm',text='verified')
    cache=ExplanationCache(fn)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(cache.get,'same')
        assert started.wait(2)
        second=pool.submit(cache.get,'same')
        release.set()
        assert first.result()['text']==second.result()['text']=='verified'
    assert len(calls)==1


def test_failure_cache_cooldown_and_retry(snapshot):
    now=[0.];calls=[]
    def fn(*args):
        calls.append(1)
        return dict(source='template',text='safe',note='LLM_UNAVAILABLE')
    cache=ExplanationCache(fn,clock=lambda:now[0])
    args=(snapshot,snapshot['alternatives'][0]['plan_id'],'fan','en')
    cache.get('first',*args);assert cache.get('first',*args)['cached']
    assert cache.get('other',*args)['note']=='LLM_COOLDOWN'
    assert len(calls)==1
    now[0]=31.;cache.get('first',*args);assert len(calls)==2


def test_cache_budget_and_bound(snapshot):
    calls=[]
    def fn(*args):calls.append(1);return dict(source='llm',text='safe')
    cache=ExplanationCache(fn,max_entries=2,calls_per_minute=2)
    args=(snapshot,snapshot['alternatives'][0]['plan_id'],'fan','en')
    cache.get('a',*args);cache.get('b',*args)
    assert cache.get('c',*args)['note']=='LLM_COOLDOWN'
    assert len(calls)==len(cache.cache)==2


def test_http_selected_plan_config_locale_and_validation(room):
    seen=[]
    def explain(s,p,a,l):
        seen.append((s['coach_config'],p,a,l))
        return explain_plan(s,p,a,l)
    app=IntegratedApp(*room,explain_fn=explain)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(app))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def request(path,body=None):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
        conn.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,{'Content-Type':'application/json'})
        response=conn.getresponse();data=response.read().decode();conn.close()
        return response.status,data
    try:
        status,html=request('/')
        assert status==200 and '<html lang="en" dir="ltr">' in html
        assert 'src="/statsbomb-logo.png"' in html and 'StatsBomb Open Data' in html
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
        conn.request('GET','/statsbomb-logo.png');image=conn.getresponse()
        assert image.status==200 and image.getheader('Content-Type')=='image/png'
        assert image.read().startswith(b'\x89PNG\r\n\x1a\n');conn.close()
        status,text=request('/api/bootstrap')
        assert status==200 and len(json.loads(text)['profiles'])==72
        assert 'connectivity_verified' in json.loads(request('/healthz')[1])
        context=dict(match_id='3754305',team_id='24',minute=65,config=dict(stance='attack'))
        status,text=request('/api/evaluate',context);snapshot=json.loads(text)
        assert status==200 and snapshot['selected_plan_id'].startswith('swap:')
        second=snapshot['alternatives'][1]
        body=dict(context,plan_id=second['plan_id'],audience='broadcaster',lang='he')
        status,text=request('/api/explain',body);r=json.loads(text)
        assert status==200 and r['plan_id']==second['plan_id'] and r['lang']=='he'
        assert len(r['facts']['inspected_plan']['proposed_lineup'])==11
        assert seen[0][0]['stance']=='attack'
        assert request('/api/explain',dict(body,plan_id='swap:fake:fake'))[0]==400
        assert request('/api/explain',dict(body,lang='unsupported'))[0]==400
        assert len(seen)==1
    finally:server.shutdown();server.server_close()
