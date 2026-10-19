"""Explanation layer: facts, number validation, templates and the LLM fallback path."""
from types import SimpleNamespace

import pytest

from subintel.narrative import AUDIENCES, LANGUAGES, explain, facts, invented_numbers, template, v1_base_url


def option(out='Emre Can', inn='Joe Allen', basis='FRESH_LEGS', change='LIKE_FOR_LIKE'):
    return dict(out_player=dict(id='1', name=out), in_player=dict(id='2', name=inn),
                expected_changes=dict(threat=-3.8, creation=-1.0, progression=1.1, retention=7.2, defense=-9.1),
                score_components=dict(outgoing_fatigue=.5891, tactical_benefit=-.0467, freshness_benefit=.1992),
                decision_basis=basis, change_type=change, evidence_strength=.5682, expected_benefit=.1526)


def snapshot(selected=True, reason=None, **kw):
    opt = option(**kw)
    return dict(team_id='24', recommendation='SUBSTITUTION' if selected else 'NO_SUBSTITUTION',
                state=dict(minute=75, goal_diff=-1, subs_left=2, red_card_diff=0),
                team_needs=dict(threat=.633, creation=.585, progression=.559, retention=.307, defense=.424),
                threshold=.15, selected=opt if selected else None, no_substitution_reason=reason,
                alternatives=[opt])


def test_facts_carry_display_numbers_and_the_decision():
    f = facts(snapshot())
    assert f['team'] == 'Liverpool' and f['score_situation'] == 'trailing' and f['goal_margin'] == 1
    assert f['team_needs_pct']['threat'] == 63 and f['top_needs'] == ['threat']
    sub = f['substitution']
    assert sub['player_off'] == 'Emre Can' and sub['player_on'] == 'Joe Allen'
    assert sub['rating_gains'] == {'retention': 7.2, 'progression': 1.1}
    assert sub['rating_tradeoff'] == {'defense': -9.1}
    assert sub['player_off_estimated_fatigue_pct'] == 59


def test_no_substitution_keeps_the_reason_and_the_best_rejected_option():
    f = facts(snapshot(selected=False, reason='BELOW_THRESHOLD'))
    assert f['decision'] == 'NO_SUBSTITUTION' and f['no_substitution_reason'] == 'BELOW_THRESHOLD'
    assert 'substitution' not in f and f['best_rejected_option']['player_on'] == 'Joe Allen'


def test_invented_numbers_are_caught():
    f = facts(snapshot())
    assert invented_numbers("Minute 75: Allen on, retention +7.2, defending -9.1, fatigue 59%.", f) == []
    assert invented_numbers("Allen gives a 73% chance of a goal.", f) == ['73']
    assert invented_numbers("Benefit 0.1526.", f) == ['0.1526']  # facts carry 0.153, not more digits


@pytest.mark.parametrize('lang', LANGUAGES)
@pytest.mark.parametrize('audience', AUDIENCES)
@pytest.mark.parametrize('case', ['fresh', 'tactical', 'formation', 'none'])
def test_templates_only_use_fact_numbers(case, audience, lang):
    snap = {'fresh': snapshot(), 'tactical': snapshot(basis='TACTICAL'),
            'formation': snapshot(basis='TACTICAL', change='FORMATION_CHANGE'),
            'none': snapshot(selected=False, reason='QUALITY_LOSS_TOO_LARGE')}[case]
    f = facts(snap)
    text = template(f, audience, lang)
    assert text and invented_numbers(text, f) == []
    if case != 'none':
        assert 'Joe Allen' in text and 'Emre Can' in text


def stub(text=None, error=None):
    def create(**kwargs):
        stub.calls.append(kwargs)
        if error:
            raise error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    stub.calls = []
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_llm_text_is_used_when_every_number_is_grounded():
    client = stub("Joe Allen replaces a tiring Emre Can (estimated fatigue 59%) at minute 75; the cost is defending -9.1.")
    result = explain(snapshot(), 'analyst', 'en', client=client, deployment='my-deployment')
    assert result['source'] == 'llm' and 'Joe Allen' in result['text']
    call = stub.calls[0]
    assert call['model'] == 'my-deployment' and 'English' in call['messages'][0]['content']
    assert '"player_on": "Joe Allen"' in call['messages'][1]['content']


def test_llm_text_with_an_invented_number_falls_back_to_the_template():
    result = explain(snapshot(), 'fan', 'he', client=stub("לאלן יש 80% סיכוי לכבוש."), deployment='d')
    assert result['source'] == 'template' and result['invented_numbers'] == ['80']
    assert 'Joe Allen' in result['text']


def test_llm_failure_falls_back_to_the_template():
    result = explain(snapshot(), 'fan', 'en', client=stub(error=TimeoutError()), deployment='d')
    assert result['source'] == 'template' and result['llm_error'] == 'TimeoutError'


def test_without_configuration_the_template_is_used(monkeypatch):
    for k in ('FOUNDRY_ENDPOINT', 'FOUNDRY_API_KEY', 'FOUNDRY_DEPLOYMENT'):
        monkeypatch.delenv(k, raising=False)
    assert explain(snapshot(), 'broadcaster', 'he')['source'] == 'template'


@pytest.mark.parametrize('endpoint', [
    'https://my-res.openai.azure.com', 'https://my-res.openai.azure.com/',
    'https://my-res.openai.azure.com/openai/v1/',
])
def test_v1_base_url_from_resource_endpoint(endpoint):
    assert v1_base_url(endpoint) == 'https://my-res.openai.azure.com/openai/v1/'


def test_v1_base_url_from_project_endpoint():
    assert v1_base_url('https://my-res.services.ai.azure.com/api/projects/live-sub-intel') == \
        'https://my-res.services.ai.azure.com/openai/v1/'
