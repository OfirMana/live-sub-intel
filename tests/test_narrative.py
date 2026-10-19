import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from subintel.narrative import (AzurePlanner, NarrativePlan, NarrativeRequest,
                               NarrativeService, build_evidence, fallback_plan)


@pytest.fixture
def rich():
    option = dict(out_player=dict(id='a', name='Starter'), in_player=dict(id='b', name='Bench'),
                  expected_benefit=.2493, expected_changes=dict(threat=-2, creation=3, progression=1,
                  retention=0, defense=4), position_fit=1, evidence_strength=.7,
                  score_components=dict(tactical_core=.04, tactical_support=0, freshness_relief=1,
                  evidence_multiplier=.8, remaining_time_multiplier=.1, freshness_time_multiplier=.3))
    return dict(match_id='synthetic', team_id='24', minute=85,
                state=dict(minute=85, goal_diff=0, subs_left=1), recommendation='SUBSTITUTION',
                selected=option, alternatives=[option], threshold=.15,
                team_needs=dict(threat=.56, creation=.53, progression=.54, retention=.35, defense=.6),
                event_source='SYNTHETIC_SCRIPTED_POSSESSIONS')


class Planner:
    def __init__(self, transform=lambda plan: plan):
        self.calls = 0
        self.transform = transform

    def plan(self, evidence, request):
        self.calls += 1
        return self.transform(fallback_plan(evidence, request.audience))


def test_no_mutation_and_required_freshness_disclosure(rich):
    before = copy.deepcopy(rich)
    r = NarrativeService(Planner()).explain(NarrativeRequest(recommendation=rich, language='he'))
    assert rich == before
    assert r['source'] == 'azure_openai'
    assert r['decision'] == 'SUBSTITUTION'
    assert 'freshness_dominant' in r['plan']['reason_fact_ids']
    assert r['tradeoffs'] and 'בעיקר מרענון' in r['text']
    assert all(item['text'] in r['text'] for item in r['evidence'])
    assert r['plan']['in_player_id'] == 'b'


@pytest.mark.parametrize('change', ['decision', 'player', 'invented', 'omit_freshness', 'omit_tradeoffs', 'misclassify', 'extra_prose'])
def test_model_cannot_change_decision_or_invent_facts(rich, change):
    def transform(plan):
        d = plan.model_dump()
        if change == 'decision':
            d['decision'] = 'NO_SUBSTITUTION'
        elif change == 'player':
            d['in_player_id'] = 'invented-striker'
        elif change == 'invented':
            d['reason_fact_ids'][-1] = 'scored_50_goals'
        elif change == 'omit_freshness':
            d['reason_fact_ids'].remove('freshness_dominant')
        elif change == 'omit_tradeoffs':
            d['tradeoff_fact_ids'] = []
        elif change == 'misclassify':
            d['tradeoff_fact_ids'] = ['state']
        else:
            d['invented_text'] = 'This guarantees a goal'
        return NarrativePlan.model_validate(d)
    r = NarrativeService(Planner(transform)).explain(NarrativeRequest(recommendation=rich))
    assert r['source'] == 'deterministic_fallback'
    assert r['fallback_reason'] == 'PROVIDER_OR_VALIDATION_ERROR'
    assert r['plan']['in_player_id'] == 'b'
    assert 'scored_50_goals' not in r['text']


def test_no_substitution_and_no_candidates_are_distinct(rich):
    rich['recommendation'], rich['selected'] = 'NO_SUBSTITUTION', None
    rich['alternatives'][0]['expected_benefit'] = .13
    r = NarrativeService(Planner()).explain(NarrativeRequest(recommendation=rich))
    assert r['decision'] == 'NO_SUBSTITUTION'
    assert r['plan']['in_player_id'] is None
    assert 'below' in r['text']
    rich['alternatives'], rich['state']['subs_left'] = [], 0
    r = NarrativeService().explain(NarrativeRequest(recommendation=rich))
    assert 'No substitutions remain' in r['text']
    assert 'threshold' not in r['plan']['reason_fact_ids']


def test_legacy_contract_does_not_invent_threshold_or_rating_units():
    rec = json.loads((Path(__file__).resolve().parents[1] / 'docs/examples/recommendation.json').read_text())
    r = NarrativeService().explain(NarrativeRequest(recommendation=rec))
    assert 'no threshold' in r['text']
    facts = build_evidence(NarrativeRequest(recommendation=rec)).facts
    assert 'percentile points' in facts['delta_creation']['en']
    assert 'rating points' not in facts['delta_creation']['en']


@pytest.mark.parametrize('language', ['en', 'he'])
@pytest.mark.parametrize('audience', ['coach', 'analyst', 'fan'])
def test_modes_and_explicit_coach_intent_preserve_engine(rich, language, audience):
    r = NarrativeService().explain(NarrativeRequest(recommendation=rich, language=language,
        audience=audience, coach_intent='attack'))
    assert 'intent' in r['plan']['reason_fact_ids']
    assert r['plan']['out_player_id'] == 'a'
    assert rich['threshold'] == .15


def test_cache_keys_include_scores_language_audience_and_do_not_leak_mutations(rich):
    planner = Planner()
    service = NarrativeService(planner)
    request = NarrativeRequest(recommendation=rich)
    first = service.explain(request)
    first['reasons'].clear()
    assert service.explain(request)['cached']
    assert service.explain(request)['reasons']
    assert planner.calls == 1
    service.explain(request.model_copy(update=dict(language='he')))
    service.explain(request.model_copy(update=dict(audience='fan')))
    rich['state']['minute'] = 90
    service.explain(NarrativeRequest(recommendation=rich))
    assert planner.calls == 4


def test_provider_failure_is_redacted_and_not_cached(rich):
    class Failing:
        def plan(self, *args):
            raise TimeoutError('secret-token-must-not-appear')
    service = NarrativeService(Failing())
    first = service.explain(NarrativeRequest(recommendation=rich))
    assert 'secret-token' not in json.dumps(first)
    service.planner = Planner()
    assert service.explain(NarrativeRequest(recommendation=rich))['source'] == 'azure_openai'


def test_missing_azure_is_honest(monkeypatch, rich):
    monkeypatch.delenv('AZURE_OPENAI_ENDPOINT', raising=False)
    service = NarrativeService.from_env('azure')
    r = service.explain(NarrativeRequest(recommendation=rich))
    assert r['fallback_reason'] == 'AZURE_NOT_CONFIGURED'
    assert r['source'] == 'deterministic_fallback'


@pytest.mark.parametrize('endpoint', ['http://example.com', 'https://user:password@example.com',
    'https://example.com/project/id', 'https://example.com?key=secret'])
def test_invalid_azure_endpoint_rejected(endpoint):
    with pytest.raises(ValueError):
        AzurePlanner(endpoint, 'deployment', client=object())


def test_real_sdk_serializes_v1_schema_and_parses_response_with_mock_transport(rich):
    httpx = pytest.importorskip('httpx')
    openai = pytest.importorskip('openai')
    request = NarrativeRequest(recommendation=rich)
    evidence = build_evidence(request)
    plan = fallback_plan(evidence, 'analyst')
    def handler(req):
        assert str(req.url) == 'https://unit.openai.azure.com/openai/v1/responses'
        data = json.loads(req.content)
        assert data['store'] is False and data['model'] == 'unit-deployment'
        assert data['text']['format']['strict'] is True
        assert data['text']['format']['schema']['additionalProperties'] is False
        assert 'freshness_dominant' in data['text']['format']['schema']['properties']['reason_fact_ids']['items']['enum']
        return httpx.Response(200, json=dict(id='resp_test', object='response', created_at=0,
            model='unit-deployment', status='completed', output=[dict(id='msg_test', type='message',
            role='assistant', status='completed', content=[dict(type='output_text', annotations=[],
            text=plan.model_dump_json())])]))
    with openai.OpenAI(api_key='unit-placeholder', base_url='https://unit.openai.azure.com/openai/v1/',
                       http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        planner = AzurePlanner('https://unit.openai.azure.com', 'unit-deployment', client=client)
        assert planner.plan(evidence, request) == plan


def test_refused_or_incomplete_azure_response_falls_back(rich):
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs:
                            SimpleNamespace(status='incomplete', output_text='')))
    service = NarrativeService(AzurePlanner('https://unit.openai.azure.com', 'unit', client=client))
    assert service.explain(NarrativeRequest(recommendation=rich))['source'] == 'deterministic_fallback'


@pytest.mark.parametrize('kind', ['nan', 'contradiction', 'unknown_source'])
def test_invalid_engine_payload_is_rejected_not_rewritten(rich, kind):
    if kind == 'nan':
        rich['selected']['expected_benefit'] = float('nan')
    elif kind == 'contradiction':
        rich['recommendation'] = 'NO_SUBSTITUTION'
    else:
        rich['event_source'] = {}
    with pytest.raises(ValueError):
        NarrativeService().explain(NarrativeRequest(recommendation=rich))


@pytest.mark.parametrize('field', ['state', 'team_needs', 'alternatives'])
def test_malformed_nested_payload_is_rejected(rich, field):
    rich[field] = [] if field != 'alternatives' else {}
    with pytest.raises(ValueError):
        NarrativeService().explain(NarrativeRequest(recommendation=rich))
