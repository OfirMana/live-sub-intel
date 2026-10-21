import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import logging
import socket
import ssl
import threading
from types import SimpleNamespace

import pytest

from subintel.foundry_runtime import (ENV_NAMES,FoundryConfigError,read_config,configuration_summary,normalize_endpoint,classify_failure)
from subintel.plan_narrative import explain_plan


def sample():
    plan=dict(plan_kind='SUBSTITUTION',out_player=dict(id='off',name='Player Off'),in_player=dict(id='on',name='Player On'),
        formation='4-3-3',recommended=True,quality_gate_passed=True,clears_threshold=True,decision_basis='FRESH_LEGS',
        change_type='LIKE_FOR_LIKE',repositioned=[],proposed_lineup=[dict(player_id=str(i)) for i in range(11)],
        expected_benefit=.2,lineup_changes=dict(threat=2,defense=-1),score_components=dict(tactical_benefit=.1,freshness_benefit=.1))
    return dict(minute=65,state=dict(goal_diff=-1),team_id='24',coach_config=dict(stance='attack'),recommendation='SUBSTITUTION',
        alternatives=[plan],selected=plan,best_no_substitution=None,threshold=.15,provenance={},formation_only={},team_needs=dict(threat=.7))


@pytest.fixture
def config(monkeypatch):
    for name,value in zip(ENV_NAMES,['https://live-sub-intel-resource.openai.azure.com/','private-test-key','gpt-4.1-mini']):monkeypatch.setenv(name,value)


def test_host_name_is_not_mistaken_for_a_path():
    assert normalize_endpoint('https://openai-team.openai.azure.com')=='https://openai-team.openai.azure.com/openai/v1/'
    assert normalize_endpoint('https://team.services.ai.azure.com/api/projects/team')=='https://team.services.ai.azure.com/openai/v1/'


@pytest.mark.parametrize('key',['"private-test-key"','abc\nsecret','abc\u200bsecret','abc secret'])
def test_key_format_failure_is_non_secret(config,monkeypatch,key):
    monkeypatch.setenv('FOUNDRY_API_KEY',key)
    report=configuration_summary()
    assert report['code']=='CONFIG_KEY_FORMAT' and not report['configured']
    assert key not in json.dumps(report)


@pytest.mark.parametrize('endpoint',['"https://team.openai.azure.com"','https://user:secret@team.openai.azure.com','https://team.openai.azure.com/?api-key=secret','http://team.openai.azure.com','https://team.openai.azure.com/unexpected'])
def test_invalid_endpoint_is_rejected_without_echoing_it(config,monkeypatch,endpoint):
    monkeypatch.setenv('FOUNDRY_ENDPOINT',endpoint)
    report=configuration_summary(include_endpoint=True)
    assert not report['configured'] and 'secret' not in json.dumps(report)
    assert endpoint not in json.dumps(report)


def test_whitespace_missing_and_repr_do_not_leak_key(config,monkeypatch):
    monkeypatch.setenv('FOUNDRY_API_KEY',' private-test-key\n')
    assert read_config().api_key=='private-test-key'
    assert 'private-test-key' not in repr(read_config())
    monkeypatch.setenv('FOUNDRY_DEPLOYMENT',' \n')
    assert not configuration_summary()['configured']
    assert configuration_summary()['missing']==['FOUNDRY_DEPLOYMENT']


@pytest.mark.parametrize('status,code',[(400,'PROVIDER_BAD_REQUEST'),(401,'AUTHENTICATION_FAILED'),(403,'RESOURCE_ACCESS_DENIED'),(404,'DEPLOYMENT_OR_ROUTE_NOT_FOUND'),(429,'PROVIDER_RATE_LIMIT_OR_QUOTA'),(503,'PROVIDER_SERVICE_ERROR')])
def test_http_failure_categories(status,code):
    error=RuntimeError('private-test-key raw body');error.status_code=status
    error.code='private-test-key';error.param='private-test-key'
    report=classify_failure(error,'provider_request')
    assert report['code']==code and 'private-test-key' not in json.dumps(report)


@pytest.mark.parametrize('cause,code',[(socket.gaierror(-2,'name or service not known'),'DNS_LOOKUP_FAILED'),(ssl.SSLCertVerificationError('private-test-key'),'TLS_VERIFICATION_FAILED'),(TimeoutError('private-test-key'),'NETWORK_TIMEOUT')])
def test_nested_transport_categories(cause,code):
    error=ConnectionError('private-test-key');error.__cause__=cause
    result=classify_failure(error,'provider_request')
    assert result['code']==code and 'private-test-key' not in json.dumps(result)


def test_config_error_does_not_get_mislabelled_as_bad_model_output(config,monkeypatch,caplog):
    monkeypatch.setenv('FOUNDRY_API_KEY','"private-test-key"')
    with caplog.at_level(logging.WARNING):r=explain_plan(sample(),'swap:off:on')
    assert r['note']=='LLM_CONFIGURATION_INVALID'
    assert r['diagnostic']['code']=='CONFIG_KEY_FORMAT'
    assert 'private-test-key' not in json.dumps(r) and 'private-test-key' not in caplog.text


@pytest.mark.parametrize('mode',['preflight','success','authentication','malformed_output'])
def test_operator_doctor_is_bounded_and_never_echoes_errors(config,monkeypatch,mode):
    import diagnose_foundry as doctor
    calls=[];closed=[]
    def create(**kwargs):
        calls.append(kwargs)
        if mode=='authentication':
            error=RuntimeError('private-test-key provider body');error.status_code=401;raise error
        text='private-test-key' if mode=='malformed_output' else '{"fact_ids":["decision"],"style":"direct"}'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),close=lambda:closed.append(1))
    monkeypatch.setattr(doctor,'foundry_client_from_env',lambda:(client,'gpt-4.1-mini'))
    report=doctor.diagnose(live=mode!='preflight')
    assert 'private-test-key' not in json.dumps(report) and closed==[1]
    assert len(calls)==report['provider_calls']==(0 if mode=='preflight' else 1)
    if mode=='preflight':assert report['outcome']=='PREFLIGHT_ONLY_NOT_CONNECTIVITY'
    elif mode=='success':assert report['outcome']=='MINIMAL_MODEL_SUCCESS'
    else:assert report['checks'][-1]['diagnostic']['code']==('AUTHENTICATION_FAILED' if mode=='authentication' else 'MODEL_RESPONSE_REJECTED')


def test_health_distinguishes_configuration_success_failure_and_cooldown(config):
    import http.client
    from integrated_app import IntegratedApp,ExplainRequest,make_handler
    calls=[]
    def fn(snapshot,plan_id,audience,lang):
        calls.append(1)
        return dict(source='llm',text='safe') if len(calls)==1 else dict(source='template',text='safe',note='LLM_UNAVAILABLE',diagnostic={'code':'AUTHENTICATION_FAILED'})
    app=IntegratedApp({},lambda *args:sample(),explain_fn=fn)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(app));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def health():
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3);conn.request('GET','/healthz');response=conn.getresponse();body=json.loads(response.read());conn.close();return body
    try:
        assert health()['llm_configured'] and not health()['connectivity_verified']
        ctx=dict(match_id='m',team_id='t',minute=65,plan_id='swap:off:on')
        app.explanation(ExplainRequest(**ctx,audience='fan'))
        assert health()['connectivity_verified']
        app.explanation(ExplainRequest(**ctx,audience='analyst'))
        assert not health()['connectivity_verified']
        app.explanation(ExplainRequest(**ctx,audience='broadcaster'))
        report=health()
        assert report['last_explanation']['diagnostic']['code']=='AUTHENTICATION_FAILED'
        assert len(calls)==2 and 'private-test-key' not in json.dumps(report)
        assert 'openai' in report['llm_runtime_versions']
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


@pytest.mark.parametrize('status',[200,400,401,403,404,429,503])
def test_real_sdk_wire_request_and_error_mapping(status,caplog):
    """Actual installed SDK and HTTP transport; only the provider is a local server."""
    openai=pytest.importorskip('openai');seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            seen.append(dict(path=self.path,body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            if status==200:
                body=dict(id='chat-test',object='chat.completion',created=1,model='gpt-4.1-mini',choices=[dict(index=0,finish_reason='stop',message=dict(role='assistant',content='{"fact_ids":["decision","freshness"],"style":"direct"}'))])
            else:body=dict(error=dict(code='test',message='secret-should-not-appear'))
            raw=json.dumps(body).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    client=openai.OpenAI(base_url=f'http://127.0.0.1:{server.server_port}/openai/v1/',api_key='dummy-not-a-secret',timeout=2,max_retries=0)
    try:
        with caplog.at_level(logging.WARNING):r=explain_plan(sample(),'swap:off:on','broadcaster','en',client=client,deployment='gpt-4.1-mini')
        assert len(seen)==1 and seen[0]['path']=='/openai/v1/chat/completions'
        body=seen[0]['body'];assert body['max_completion_tokens']==250 and body['response_format']=={'type':'json_object'}
        assert body['model']=='gpt-4.1-mini'
        assert r['source']==('llm' if status==200 else 'template')
        if status!=200:assert r['diagnostic']['status']==status and r['diagnostic']['stage']=='provider_request'
        assert 'secret-should-not-appear' not in json.dumps(r) and 'secret-should-not-appear' not in caplog.text
    finally:client.close();server.shutdown();server.server_close();thread.join(timeout=2)
