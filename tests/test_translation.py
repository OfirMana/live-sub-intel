"""Ten explanation locales: validated template translation, server-side values, labelled fallback."""
import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from integrated_app import ExplanationCache
from subintel import translation
from subintel.plan_narrative import LANGUAGES, TEMPLATES, explain_plan, source_text
from subintel.translation import LANGUAGE_NAMES, TRUSTED, TranslationCatalog, TranslationRejected, validate

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {k: v for k, v in json.loads((ROOT/'tests/fixtures/translations.json').read_text(encoding='utf-8')).items() if not k.startswith('_')}
LRI, PDI = '⁦', '⁩'


def sample(benefit=.2):
    plan = dict(plan_kind='SUBSTITUTION', out_player=dict(id='off', name='Player Off'), in_player=dict(id='on', name='Player On'),
                formation='4-3-3', recommended=True, quality_gate_passed=True, clears_threshold=True, decision_basis='FRESH_LEGS',
                change_type='LIKE_FOR_LIKE', repositioned=[], proposed_lineup=[dict(player_id=str(i)) for i in range(11)],
                expected_benefit=benefit, lineup_changes=dict(threat=2, defense=-1), score_components=dict(tactical_benefit=.1, freshness_benefit=.1))
    return dict(minute=65, state=dict(goal_diff=-1), team_id='24', coach_config=dict(stance='attack', objective='win'),
                recommendation='SUBSTITUTION', alternatives=[plan], selected=plan, best_no_substitution=None, threshold=.15,
                provenance={}, formation_only={}, team_needs=dict(threat=.7))


def client(lang, mutate=None, fail=None):
    """Selection returns decision + freshness; translation answers from the reviewed fixtures."""
    calls = []
    by_source = {source_text(k): v for k, v in FIXTURES.get(lang, {}).items()}
    def create(**kwargs):
        calls.append(kwargs)
        if kwargs['response_format']['type'] == 'json_object' and 'fact_ids' in kwargs['messages'][0]['content']:
            content = '{"fact_ids":["decision","freshness"],"style":"direct"}'
        else:
            if fail:
                raise fail
            items = json.loads(kwargs['messages'][1]['content'])['items']
            out = {alias: by_source[english] for alias, english in items.items()}
            content = json.dumps(dict(translations=mutate(out) if mutate else out), ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), calls


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ('FOUNDRY_ENDPOINT', 'FOUNDRY_API_KEY', 'FOUNDRY_DEPLOYMENT'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(translation, 'SCHEMA_SUPPORTED', [True])


def test_the_page_offers_exactly_the_supported_locales():
    html = (ROOT/'web/coach-room/index.html').read_text(encoding='utf-8')
    select = re.search(r'<select id="explainLang"[^>]*>(.*?)</select>', html).group(1)
    assert tuple(re.findall(r'<option value="([\w-]+)"', select)) == LANGUAGES
    assert set(LANGUAGE_NAMES) == set(LANGUAGES) - set(TRUSTED) and len(LANGUAGES) == 10


@pytest.mark.parametrize('lang', sorted(FIXTURES))
def test_reviewed_fixtures_pass_validation(lang):
    validate(lang, {k: source_text(k) for k in FIXTURES[lang]}, FIXTURES[lang])
    covered = set(FIXTURES[lang])
    assert {'tpl:decision.swap.rejected', 'tpl:tradeoff', 'tpl:freshness.coach', 'tpl:stats.unavailable', 'tpl:score'} <= covered


@pytest.mark.parametrize('change,rule', [
    (lambda t: t.replace('{on}', 'X'), 'placeholders'),
    (lambda t: t + ' {minute}', 'placeholders'),
    (lambda t: t.replace('{off}', '{off} {off}'), 'placeholders'),
    (lambda t: t.replace('{on}', '{player}'), 'placeholders'),
    (lambda t: t.replace('{on}', '{{on}}'), 'braces'),
    (lambda t: t + ' 9', 'digits'),
    (lambda t: '', 'empty'),
])
def test_tampered_translations_are_rejected(change, rule):
    key = 'tpl:decision.swap.rejected'
    with pytest.raises(TranslationRejected) as error:
        validate('fr', {key: source_text(key)}, {key: change(FIXTURES['fr'][key])})
    assert error.value.rule == rule


def test_lost_negation_missing_and_extra_ids_are_rejected():
    key = 'tpl:decision.swap.rejected'
    with pytest.raises(TranslationRejected, match='negation'):
        validate('fr', {key: source_text(key)}, {key: "L'option est {on} à la place de {off} ; elle respecte les règles de recommandation."})
    with pytest.raises(TranslationRejected, match='negation'):
        validate('zh-Hans', {key: source_text(key)}, {key: '该选项是用 {on} 换下 {off}；它符合推荐规则。'})
    with pytest.raises(TranslationRejected, match='ids'):
        validate('fr', {key: source_text(key), 'tpl:score': source_text('tpl:score')}, {key: FIXTURES['fr'][key]})
    with pytest.raises(TranslationRejected, match='ids'):
        validate('fr', {key: source_text(key)}, {key: FIXTURES['fr'][key], 'extra': 'x'})


@pytest.mark.parametrize('lang', sorted(FIXTURES))
def test_translated_explanation_keeps_server_values_and_identity(lang):
    stub, calls = client(lang)
    catalog = TranslationCatalog()
    r = explain_plan(sample(), 'swap:off:on', 'analyst', lang, client=stub, deployment='gpt-4.1-mini', catalog=catalog)
    assert r['source'] == 'llm' and r['translation'] == dict(status='model', model='gpt-4.1-mini', cached=False)
    assert r['output_lang'] == lang and r['plan_id'] == 'swap:off:on'
    for value in ('Player On', 'Player Off', '0.200', '0.150', FIXTURES[lang]['term:dim.defense']):
        assert value in r['text']
    assert 'Bringing on' not in r['text']
    assert (LRI + 'Player On' + PDI in r['text']) == (lang == 'ar')
    request = calls[1]
    assert request['response_format']['type'] == 'json_schema' and request['response_format']['json_schema']['strict']
    assert 'Player On' not in request['messages'][1]['content'] and '0.200' not in request['messages'][1]['content']
    again = explain_plan(sample(), 'swap:off:on', 'analyst', lang, client=stub, deployment='gpt-4.1-mini', catalog=catalog)
    assert again['translation']['cached'] and len(calls) == 3 and again['text'] == r['text']


def test_negative_scores_are_inserted_verbatim():
    stub, _ = client('ar')
    r = explain_plan(sample(-.056), 'swap:off:on', 'analyst', 'ar', client=stub, deployment='d', catalog=TranslationCatalog())
    assert f'{LRI}-0.056{PDI}' in r['text']
    stub, _ = client('de')
    assert '-0.056' in explain_plan(sample(-.056), 'swap:off:on', 'analyst', 'de', client=stub, deployment='d', catalog=TranslationCatalog())['text']


def test_rejected_translation_falls_back_to_labelled_english():
    stub, _ = client('fr', mutate=lambda out: {k: v.replace('{on}', '') for k, v in out.items()})
    catalog = TranslationCatalog()
    r = explain_plan(sample(), 'swap:off:on', 'analyst', 'fr', client=stub, deployment='d', catalog=catalog)
    assert r['output_lang'] == 'en' and r['text'].startswith('Bringing on Player On for Player Off')
    assert r['translation']['status'] == 'fallback' and r['translation']['note'] == 'TRANSLATION_REJECTED'
    assert r['translation']['diagnostic']['code'] == 'TRANSLATION_REJECTED' and r['translation']['diagnostic']['rule'] == 'placeholders'
    assert r['source'] == 'llm' and catalog.counts() == {}


@pytest.mark.parametrize('error,code', [(TimeoutError('slow'), 'NETWORK_TIMEOUT'), (ValueError('not json'), 'UNEXPECTED_CLIENT_ERROR')])
def test_translation_failures_fall_back_to_english(error, code):
    stub, _ = client('ja', fail=error)
    r = explain_plan(sample(), 'swap:off:on', 'coach', 'ja', client=stub, deployment='d', catalog=TranslationCatalog())
    assert r['output_lang'] == 'en' and r['translation']['note'] == 'TRANSLATION_UNAVAILABLE'
    assert r['translation']['diagnostic']['code'] == code


def test_no_model_means_no_translation_but_trusted_languages_still_work():
    r = explain_plan(sample(), 'swap:off:on', 'broadcaster', 'es', catalog=TranslationCatalog())
    assert r['output_lang'] == 'en' and r['translation'] == dict(status='fallback', note='TRANSLATION_NOT_CONFIGURED', diagnostic=None)
    he = explain_plan(sample(), 'swap:off:on', 'broadcaster', 'he', catalog=TranslationCatalog())
    assert he['output_lang'] == 'he' and he['translation'] == dict(status='trusted')
    with pytest.raises(ValueError):
        explain_plan(sample(), 'swap:off:on', 'broadcaster', 'xx')


def test_a_failed_selection_call_does_not_trigger_a_second_slow_call():
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        raise TimeoutError('provider down')
    stub = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    r = explain_plan(sample(), 'swap:off:on', 'analyst', 'it', client=stub, deployment='d', catalog=TranslationCatalog())
    assert len(calls) == 1 and r['translation']['note'] == 'TRANSLATION_UNAVAILABLE' and r['note'] == 'LLM_UNAVAILABLE'


def test_schema_refusal_downgrades_to_json_object_once():
    error = RuntimeError('bad request'); error.status_code = 400; error.param = 'response_format'
    stub, calls = client('pt', fail=error)
    explain_plan(sample(), 'swap:off:on', 'analyst', 'pt', client=stub, deployment='d', catalog=TranslationCatalog())
    assert translation.SCHEMA_SUPPORTED == [False]
    stub, calls = client('pt')
    r = explain_plan(sample(), 'swap:off:on', 'analyst', 'pt', client=stub, deployment='d', catalog=TranslationCatalog())
    assert calls[1]['response_format'] == {'type': 'json_object'} and r['translation']['status'] == 'model'


def test_fallback_translations_are_not_cached_for_long():
    now = [0.]; calls = []
    def fn(*args):
        calls.append(1)
        return dict(source='llm', text='english', translation=dict(status='fallback'))
    cache = ExplanationCache(fn, clock=lambda: now[0])
    cache.get('k', None, None, None, None); now[0] = 31.; cache.get('k', None, None, None, None)
    assert len(calls) == 2


def test_hebrew_is_hand_written_with_the_same_placeholders():
    from subintel.plan_narrative import TERMS
    assert set(TEMPLATES['he']) == set(TEMPLATES['en']) and set(TERMS['he']) == set(TERMS['en'])
    for key, english in TEMPLATES['en'].items():
        assert sorted(re.findall(r'\{(\w+)\}', english)) == sorted(re.findall(r'\{(\w+)\}', TEMPLATES['he'][key])), key


def test_rejected_plan_stays_negated_after_translation():
    snap = sample()
    snap['alternatives'][0].update(recommended=False, quality_gate_passed=False)
    snap['recommendation'] = 'NO_SUBSTITUTION'
    stub, _ = client('fr')
    r = explain_plan(snap, 'swap:off:on', 'analyst', 'fr', client=stub, deployment='d', catalog=TranslationCatalog())
    assert r['translation']['status'] == 'model' and 'ne respecte pas' in r['text'] and FIXTURES['fr']['tpl:quality.loss'] in r['text']
