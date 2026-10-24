from copy import deepcopy
from live_acceptance import acceptance_failures


def valid_row():
    return dict(team='1',minute=65,audience='coach',lang='fr',http=200,source='llm',output_lang='fr',translation='model',plan_identity_ok=True,broadcaster_has_digits=False)


def test_strict_acceptance_passes_valid_model_response():
    assert acceptance_failures({'requests':[valid_row()]},True)==[]


def test_acceptance_rejects_http_identity_digits_and_empty_report():
    assert acceptance_failures({'requests':[]})
    for change in ({'http':503},{'plan_identity_ok':False},{'broadcaster_has_digits':True}):
        assert acceptance_failures({'requests':[dict(valid_row(),**change)]})


def test_template_is_operational_but_does_not_pass_model_release_gate():
    row=dict(valid_row(),source='template',translation='fallback',output_lang='en')
    assert acceptance_failures({'requests':[row]})==[]
    assert acceptance_failures({'requests':[row]},True)


def test_missing_expected_plan_is_not_silently_accepted():
    assert acceptance_failures({'requests':[dict(skipped='plan not offered here')]})


def test_deployment_change_invalidates_combined_acceptance():
    report=dict(requests=[valid_row()],build_sha='before',build_sha_after='after')
    assert acceptance_failures(report)


def test_live_call_records_timeout_without_losing_the_whole_report(monkeypatch):
    import live_acceptance
    def fail(*args,**kwargs):
        raise TimeoutError('simulated timeout')
    monkeypatch.setattr(live_acceptance.urllib.request,'urlopen',fail)
    status,result,seconds=live_acceptance.call('https://example.invalid','/healthz')
    assert status==0 and result is None and seconds>=0
