"""Three audiences on the synthetic demo: identity, required facts, brevity and truthful match facts."""
import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

import integrated_app
from integrated_app import ExplainRequest, IntegratedApp
from synthetic_coach_room import create_synthetic_room
from subintel.plan_narrative import AUDIENCES, DEFAULT_AUDIENCE, MAX_FACTS, explain_plan, normalize_audience

ROOT = Path(__file__).resolve().parents[1]
CONFIG = dict(stance='attack', objective='win', formation='auto', freshness_cap=1)
LRI, PDI = '⁦', '⁩'


@pytest.fixture(scope='module')
def app():
    return IntegratedApp(*create_synthetic_room(scenario='lively'), explain_fn=explain_plan)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ('FOUNDRY_ENDPOINT', 'FOUNDRY_API_KEY', 'FOUNDRY_DEPLOYMENT'):
        monkeypatch.delenv(key, raising=False)


def ask(app, team, minute, plan_id='wait', audience=DEFAULT_AUDIENCE, lang='en', **config):
    return app.explanation(ExplainRequest(match_id='synthetic-demo', team_id=team, minute=minute,
                                          config=dict(CONFIG, **config), plan_id=plan_id, audience=audience, lang=lang))


def snapshot(app, team, minute, **config):
    return app.snapshot(ExplainRequest(match_id='synthetic-demo', team_id=team, minute=minute, config=dict(CONFIG, **config), plan_id='wait'))


def plans(snap):
    ids = [p['plan_id'] for p in snap['alternatives']]
    if snap.get('tactical_plan'):
        ids.append('tactical')
    if snap['recommendation'] == 'NO_SUBSTITUTION':
        ids.append('wait')
    return ids


def sentences(text):
    return [s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s]


def test_fan_is_an_alias_for_broadcaster(app):
    assert normalize_audience('fan') == 'broadcaster' and AUDIENCES == ('broadcaster', 'analyst', 'coach')
    with pytest.raises(ValueError):
        normalize_audience('commentator')
    plan = snapshot(app, '1', 65)['selected_plan_id']
    fan, broadcaster = ask(app, '1', 65, plan, 'fan'), ask(app, '1', 65, plan, 'broadcaster')
    assert fan['audience'] == broadcaster['audience'] == 'broadcaster' and fan['text'] == broadcaster['text']
    assert broadcaster['cached']  # the alias is normalized before the cache lookup
    assert ExplainRequest(match_id='m', team_id='t', minute=0, plan_id='wait').audience == 'broadcaster'


def test_server_and_page_offer_the_same_three_audiences():
    html = (ROOT/'web/coach-room/index.html').read_text(encoding='utf-8')
    select = re.search(r'<select id="audience"[^>]*>(.*?)</select>', html).group(1)
    assert tuple(re.findall(r'<option value="(\w+)"', select)) == AUDIENCES
    assert re.search(r'<option value="broadcaster" selected', select)
    i18n = (ROOT/'web/coach-room/i18n.js').read_text(encoding='utf-8')
    for key in ('broadcaster', 'analyst', 'coachAudience'):
        assert i18n.count(f'{key}:') == 2  # English and Hebrew labels


@pytest.mark.parametrize('lang', ['en', 'he'])
def test_every_plan_keeps_its_identity_and_audience_limits(app, lang):
    for team in ('1', '24'):
        for minute in (30, 65, 85, 90):
            snap = snapshot(app, team, minute)
            for plan_id in plans(snap):
                plan = next((p for p in snap['alternatives'] if p['plan_id'] == plan_id), None)
                for audience in AUDIENCES:
                    r = ask(app, team, minute, plan_id, audience, lang)
                    assert r['plan_id'] == plan_id and r['audience'] == audience and r['fact_ids'][0] == 'decision'
                    assert len(r['fact_ids']) <= MAX_FACTS[audience] or audience != 'broadcaster'
                    if plan:
                        assert plan['in_player']['name'] in r['text'] and plan['out_player']['name'] in r['text']
                        if not plan['recommended']:
                            assert 'quality' in r['fact_ids']  # the rejection reason is never dropped
                    if audience == 'broadcaster':
                        assert len(sentences(r['text'])) <= 2 and not re.search(r'\d|%', r['text'])
                        if lang == 'en':
                            assert len(r['text'].split()) <= 45


def test_rejected_and_tactical_plans_never_sound_recommended(app):
    snap = snapshot(app, '1', 65)
    rejected = next(p['plan_id'] for p in snap['alternatives'] if not p['recommended'])
    assert 'not justified' in ask(app, '1', 65, rejected, 'broadcaster')['text']
    for audience in ('analyst', 'coach'):
        assert 'does not pass' in ask(app, '1', 65, rejected, audience)['text']
    assert 'not the current recommendation' in ask(app, '1', 65, 'tactical', 'analyst')['text']
    later = snapshot(app, '1', 85)
    assert later['recommendation'] == 'TACTICAL_ADJUSTMENT'
    assert 'The recommendation is to reposition' in ask(app, '1', 85, 'tactical', 'coach')['text']


def test_analyst_quotes_server_statistics_and_the_benefit(app):
    snap = snapshot(app, '1', 65)
    plan = snap['alternatives'][1]
    r = ask(app, '1', 65, plan['plan_id'], 'analyst')
    match = r['facts']['match']
    assert {'stats', 'score'} <= set(r['fact_ids'])
    assert match['cutoff']['minute'] == 65 and match['team']['name'] == 'Arsenal'
    stats_sentence = next(s for s in sentences(r['text']) if s.startswith('Match so far'))
    numbers = re.findall(r'\d+(?:\.\d+)?', stats_sentence)
    allowed = {f"{match[side]['xg']:.2f}" for side in ('team', 'opponent')} | {str(match[side][k]) for side in ('team', 'opponent') for k in ('shots', 'on_target')}
    allowed |= {f"{match['team'][k]:.1f}" for k in ('pass_accuracy', 'possession') if match['team'][k] is not None}
    assert numbers and set(numbers) <= allowed
    assert f"{plan['expected_benefit']:.3f}" in r['text'] and f"{snap['threshold']:.3f}" in r['text']
    wait = ask(app, '1', 90, 'wait', 'analyst')
    assert {'reason', 'stats'} <= set(wait['fact_ids'])


def test_missing_statistics_are_said_not_invented(app):
    snap = snapshot(app, '1', 65)
    plan_id = snap['alternatives'][0]['plan_id']
    r = explain_plan(dict(snap, match_facts=None), plan_id, 'analyst', 'en')
    assert 'No match statistics are available' in r['text'] and 'Match so far' not in r['text']
    early = explain_plan(dict(snap, match_facts=dict(r['facts']['match'] or {}, events_observed=0) if r['facts']['match'] else None), plan_id, 'analyst', 'en')
    assert 'No match statistics are available' in early['text']


def test_coach_gets_game_state_urgency_and_discipline_only_when_true(app):
    snap = snapshot(app, '1', 65)
    plan = snap['alternatives'][0]
    r = ask(app, '1', 65, plan['plan_id'], 'coach')
    assert 'Arsenal lead 1–0 at 65′; brief: more attacking, seek a win.' in r['text']
    assert 'urgency' not in r['fact_ids']  # the late win policy is not active while leading
    booked = r['facts']['match']['players'].get(plan['out_player']['id'], {}).get('yellows', 0)
    from subintel.plan_narrative import facts
    bank = facts(dict(r['facts']), 'coach')
    assert ('discipline' in bank) == bool(booked)
    if 'discipline' in r['fact_ids']:
        assert 'not part of the score' in r['text']
    late = ask(app, '1', 85, 'tactical', 'coach')
    assert 'Arsenal trail 1–2 at 85′' in late['text'] and 'urgency' in late['fact_ids']
    assert 'urgency' not in ask(app, '1', 85, 'tactical', 'coach', objective='draw')['fact_ids']


def test_formation_change_is_numeric_for_analysts_and_qualitative_for_broadcasters(app):
    for team, minute in (('1', 65), ('1', 85), ('24', 65), ('24', 85), ('1', 30), ('24', 30)):
        snap = snapshot(app, team, minute)
        plan = next((p for p in snap['alternatives'] if p.get('change_type') == 'FORMATION_CHANGE'), None)
        if plan:
            assert plan['formation'] in ask(app, team, minute, plan['plan_id'], 'analyst')['text']
            assert plan['formation'] not in ask(app, team, minute, plan['plan_id'], 'broadcaster')['text']
            return
    pytest.skip('no formation-changing alternative in the sampled checkpoints')


def test_hebrew_isolates_names_and_scores(app):
    plan = snapshot(app, '24', 65)['alternatives'][0]
    he = ask(app, '24', 65, plan['plan_id'], 'coach', 'he')['text']
    assert f'{LRI}0–1{PDI}' in he and f"{LRI}{plan['in_player']['name']}{PDI}" in he
    assert LRI not in ask(app, '24', 65, plan['plan_id'], 'coach', 'en')['text']


def test_cache_key_separates_audience_language_facts_and_schema(app, monkeypatch):
    calls = []
    def fn(snapshot, plan_id, audience, lang):
        calls.append((audience, lang))
        return dict(source='llm', text='verified', note=None)
    local = IntegratedApp(app.bootstrap, app.evaluate, explain_fn=fn)
    plan = snapshot(app, '1', 65)['selected_plan_id']
    for audience, lang in (('broadcaster', 'en'), ('fan', 'en'), ('analyst', 'en'), ('analyst', 'he'), ('coach', 'en')):
        ask(local, '1', 65, plan, audience, lang)
    assert calls == [('broadcaster', 'en'), ('analyst', 'en'), ('analyst', 'he'), ('coach', 'en')]
    real = integrated_app.checkpoint_facts
    monkeypatch.setattr(integrated_app, 'checkpoint_facts', lambda *a: dict(real(*a), events_observed=-1))
    ask(local, '1', 65, plan, 'coach', 'en')
    monkeypatch.setattr(integrated_app, 'checkpoint_facts', real)
    monkeypatch.setattr(integrated_app, 'CACHE_SCHEMA', 'next-version')
    ask(local, '1', 65, plan, 'coach', 'en')
    assert len(calls) == 6


def test_model_cannot_drop_required_facts(app):
    plan = snapshot(app, '1', 65)['alternatives'][0]['plan_id']
    stub = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"fact_ids":["decision"],"style":"direct"}'))]))))
    snap = dict(snapshot(app, '1', 65), match_facts=app.bootstrap and integrated_app.checkpoint_facts(app.bootstrap['fixtures']['synthetic-demo'], 65, '1'))
    r = explain_plan(snap, plan, 'analyst', 'en', client=stub, deployment='test')
    assert r['source'] == 'llm' and {'decision', 'stats', 'score'} <= set(r['fact_ids'])
    assert json.dumps(r['facts']['match']['cutoff']) == json.dumps(dict(minute=65, elapsed=65, rule='events strictly before the checkpoint'))
