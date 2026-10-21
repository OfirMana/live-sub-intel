"""Explanation layer: turns a `recommend_demo` snapshot into text for fans, analysts or TV.

The engine decides; this module only explains. The LLM sees a small facts object and
nothing else, and its text is rejected if it contains a number that is not in the
facts. A deterministic template produces the same kind of text offline and is the
fallback whenever the LLM is unavailable or fails validation.

Microsoft Foundry is reached through its OpenAI-compatible v1 endpoint with three
environment variables: FOUNDRY_ENDPOINT, FOUNDRY_API_KEY and FOUNDRY_DEPLOYMENT.
"""
from __future__ import annotations

import json
import os
import re
from decimal import Decimal

from .demo_live import TEAM_IDS

AUDIENCES = ('fan', 'analyst', 'broadcaster')
LANGUAGES = {'he': 'Hebrew', 'en': 'English'}
TEAM_NAMES = {tid: name for name, tid in TEAM_IDS.items()}

DIM_LABELS = {
    'he': {'threat': 'איום לשער', 'creation': 'יצירת מצבים', 'progression': 'קידום הכדור',
           'retention': 'שמירת כדור', 'defense': 'הגנה', 'aerial': 'משחק אוויר'},
    'en': {'threat': 'attacking threat', 'creation': 'chance creation', 'progression': 'ball progression',
           'retention': 'ball retention', 'defense': 'defending', 'aerial': 'aerial play'},
}
REASON_LABELS = {
    'he': {'NO_SUBSTITUTIONS_LEFT': 'כל החילופים כבר נוצלו',
           'OUTSIDE_DECISION_WINDOW': 'זה מחוץ לחלון ההחלטה של המנוע (דקות 20–93)',
           'NO_ELIGIBLE_CANDIDATE': 'אין על הספסל שחקן שמתאים לעמדה',
           'BELOW_THRESHOLD': 'אף חילוף לא מספיק טוב כדי לעבור את הסף',
           'QUALITY_LOSS_TOO_LARGE': 'הרענון לא מצדיק מחליף חלש בהרבה'},
    'en': {'NO_SUBSTITUTIONS_LEFT': 'all substitutions have been used',
           'OUTSIDE_DECISION_WINDOW': 'it is outside the engine\'s decision window (minutes 20-93)',
           'NO_ELIGIBLE_CANDIDATE': 'no bench player fits the position',
           'BELOW_THRESHOLD': 'no change is good enough to clear the threshold',
           'QUALITY_LOSS_TOO_LARGE': 'fresh legs do not justify a much weaker substitute'},
}

SYSTEM_PROMPT = """You explain a football substitution decision made by a deterministic engine.
The user message is a JSON object of facts. Rules:
1. The decision is final. Never propose a different substitution and never contradict it.
2. Use only the facts. Every number you write must appear in the JSON exactly as given;
   do not calculate new numbers. Rating changes are card points, needs are percentages.
3. expected_benefit, threshold and evidence_strength are model scores, not probabilities,
   chances or goals. Never describe them as a chance or a prediction of the result.
4. Fatigue is an estimate from minutes and workload, not a measurement.
5. If decision is SUBSTITUTION, name who goes off and who comes on and the main trade-off.
   If decision_basis is FRESH_LEGS, say it is mainly about fresh legs.
   If change_type is FORMATION_CHANGE, say the team changes shape by adding an attacker.
6. If decision is NO_SUBSTITUTION, explain why from no_substitution_reason.
7. Only say the change helps with a team need if that need is listed in addresses_needs.
   If addresses_needs is empty, do not connect the change to the team's needs at all.
8. Describe changes plainly, without intensifiers such as "significantly" or "dramatically".
9. LIKE_FOR_LIKE means the substitute plays the same position as the player going off.
Audience:
- fan: 2-3 short sentences, everyday words, no model scores.
- analyst: 3-5 sentences; may cite team needs, rating changes, benefit vs threshold and evidence strength.
- broadcaster: one punchy on-air sentence, then one supporting sentence.
Write in {language}. Plain text only, no lists, no markdown."""


def _num(x: float, digits: int) -> float | int:
    value = round(float(x), digits)
    return int(value) if digits == 0 else value


def facts(snapshot: dict) -> dict:
    """The only material the explanation may use, with numbers already in display form."""
    state = snapshot['state']
    needs_pct = {d: _num(v * 100, 0) for d, v in snapshot['team_needs'].items()}
    out = dict(
        minute=state['minute'],
        team=TEAM_NAMES.get(snapshot['team_id'], snapshot['team_id']),
        score_situation='level' if state['goal_diff'] == 0 else ('trailing' if state['goal_diff'] < 0 else 'leading'),
        goal_margin=abs(state['goal_diff']),
        subs_left=state['subs_left'],
        team_needs_pct=needs_pct,
        top_needs=[d for d, v in sorted(needs_pct.items(), key=lambda kv: -kv[1]) if v >= 60],
        decision=snapshot['recommendation'],
        threshold=_num(snapshot['threshold'], 3),
    )
    option = snapshot['selected']
    if option is None:
        out['no_substitution_reason'] = snapshot.get('no_substitution_reason')
        option = snapshot['alternatives'][0] if snapshot['alternatives'] else None
        key = 'best_rejected_option'
    else:
        key = 'substitution'
    if option is not None:
        changes = {d: _num(v, 1) for d, v in option['expected_changes'].items()}
        gains = [d for d, v in sorted(changes.items(), key=lambda kv: -kv[1]) if v > 0][:2]
        losses = [d for d, v in sorted(changes.items(), key=lambda kv: kv[1]) if v < 0][:1]
        out[key] = dict(
            player_off=option['out_player']['name'],
            player_on=option['in_player']['name'],
            decision_basis=option.get('decision_basis'),
            change_type=option.get('change_type', 'LIKE_FOR_LIKE'),
            rating_gains={d: changes[d] for d in gains},
            addresses_needs=[d for d in out['top_needs'] if changes.get(d, 0) > 0],
            rating_tradeoff={d: changes[d] for d in losses},
            player_off_estimated_fatigue_pct=_num(option['score_components']['outgoing_fatigue'] * 100, 0),
            expected_benefit=_num(option['expected_benefit'], 3),
            evidence_strength=_num(option['evidence_strength'], 2),
        )
    return out


def _numbers(value) -> set[str]:
    if isinstance(value, dict):
        return set().union(*map(_numbers, value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*map(_numbers, value)) if value else set()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return set()
    return {_canonical(str(abs(value)))}


def _canonical(token: str) -> str:
    """Exact decimal form without trailing zeros: '7.20' == '7.2', but '0.1526' != '0.153'."""
    return format(Decimal(token.replace(',', '.')).normalize(), 'f')


NUMBER = re.compile(r'\d+(?:[.,]\d+)?')


def invented_numbers(text: str, fact_sheet: dict) -> list[str]:
    """Numbers in the text that do not appear in the facts (signs and % are ignored)."""
    allowed = _numbers(fact_sheet) | {'20', '93'}  # the decision window, quoted by the templates
    return [t for t in NUMBER.findall(text) if _canonical(t) not in allowed]


def template(fact_sheet: dict, audience: str, lang: str) -> str:
    """Deterministic explanation built only from the facts."""
    L, R = DIM_LABELS[lang], REASON_LABELS[lang]
    f, he = fact_sheet, lang == 'he'
    sub = f.get('substitution')
    if sub is None:
        reason = R.get(f.get('no_substitution_reason') or 'BELOW_THRESHOLD', '')
        best = f.get('best_rejected_option')
        text = (f"דקה {f['minute']}: אין המלצת חילוף, כי {reason}." if he
                else f"Minute {f['minute']}: no substitution recommended, because {reason}.")
        if best and audience == 'analyst':
            text += (f" האפשרות המובילה, הכנסת {best['player_on']} במקום {best['player_off']}, קיבלה {best['expected_benefit']} מול סף {f['threshold']}." if he
                     else f" The best option, {best['player_on']} for {best['player_off']}, scored {best['expected_benefit']} against a threshold of {f['threshold']}.")
        return text

    gains = ', '.join(f"{L[d]} +{v}" for d, v in sub['rating_gains'].items())
    trade = ', '.join(f"{L[d]} {v}" for d, v in sub['rating_tradeoff'].items())
    fresh = sub['decision_basis'] == 'FRESH_LEGS'
    shape = sub['change_type'] == 'FORMATION_CHANGE'
    need = L[sub['addresses_needs'][0]] if sub['addresses_needs'] else None
    if he:
        head = f"דקה {f['minute']}: {sub['player_on']} נכנס במקום {sub['player_off']}."
        why = (f" בעיקר רגליים רעננות: העייפות המשוערת של {sub['player_off']} היא {sub['player_off_estimated_fatigue_pct']}%." if fresh
               else f" הקבוצה צריכה יותר {need}." if need else "")
        if shape:
            why += " זה גם שינוי מערך: עוד שחקן התקפה."
        cost = f" המחיר: {trade}." if trade else ""
        gain = f" רווח: {gains}." if gains else ""
        if audience == 'fan':
            return head + why
        if audience == 'broadcaster':
            return f"{sub['player_on']} על הדשא במקום {sub['player_off']}!" + why + cost
        return (head + why + gain + cost +
                f" תועלת {sub['expected_benefit']} מול סף {f['threshold']}, חוזק ראיות {sub['evidence_strength']}.")
    head = f"Minute {f['minute']}: {sub['player_on']} on for {sub['player_off']}."
    why = (f" Mainly fresh legs: {sub['player_off']}'s estimated fatigue is {sub['player_off_estimated_fatigue_pct']}%." if fresh
           else f" The team needs more {need}." if need else "")
    if shape:
        why += " It also changes the shape: one more attacker."
    cost = f" The cost: {trade}." if trade else ""
    gain = f" Gains: {gains}." if gains else ""
    if audience == 'fan':
        return head + why
    if audience == 'broadcaster':
        return f"{sub['player_on']} is coming on for {sub['player_off']}!" + why + cost
    return (head + why + gain + cost +
            f" Benefit {sub['expected_benefit']} against a threshold of {f['threshold']}, evidence strength {sub['evidence_strength']}.")


def foundry_client_from_env():
    """(client, deployment) for Microsoft Foundry, or None when not configured."""
    # strip(): values pasted into a portal often carry a stray space or newline, which
    # makes the key an invalid header and fails every call as a "connection error".
    from .foundry_runtime import read_config
    config=read_config()
    if config is None:
        return None
    from openai import OpenAI  # optional dependency: pip install -e ".[llm]"
    return OpenAI(base_url=config.base_url, api_key=config.api_key, timeout=12, max_retries=0), config.deployment


def v1_base_url(endpoint: str) -> str:
    """Resource endpoint (or a project endpoint) -> the OpenAI-compatible v1 base URL."""
    from .foundry_runtime import normalize_endpoint
    return normalize_endpoint(endpoint)


def _describe(error: Exception) -> str:
    """Error type, message and underlying cause (e.g. DNS or TLS), without request headers."""
    text = f'{type(error).__name__}: {error}'
    cause = error.__cause__ or error.__context__
    if cause is not None:
        text += f' <- {type(cause).__name__}: {cause}'
    return text[:300]


def explain(snapshot: dict, audience: str = 'fan', lang: str = 'he', client=None, deployment: str | None = None) -> dict:
    """Explanation text plus where it came from. Falls back to the template, never to silence."""
    if audience not in AUDIENCES or lang not in LANGUAGES:
        raise ValueError(f'audience must be one of {AUDIENCES}, lang one of {tuple(LANGUAGES)}')
    fact_sheet = facts(snapshot)
    result = dict(facts=fact_sheet, audience=audience, lang=lang)
    if client is None:
        configured = foundry_client_from_env()
        if configured:
            client, deployment = configured
    if client is not None:
        try:
            response = client.chat.completions.create(
                model=deployment,
                messages=[{'role': 'system', 'content': SYSTEM_PROMPT.format(language=LANGUAGES[lang])},
                          {'role': 'user', 'content': json.dumps(dict(audience=audience, **fact_sheet), ensure_ascii=False)}],
            )
            text = (response.choices[0].message.content or '').strip()
        except Exception as error:  # network, auth, quota: the demo must keep explaining
            return dict(result, text=template(fact_sheet, audience, lang), source='template', llm_error=_describe(error))
        invented = invented_numbers(text, fact_sheet)
        if text and not invented:
            return dict(result, text=text, source='llm')
        return dict(result, text=template(fact_sheet, audience, lang), source='template',
                    rejected_llm_text=text, invented_numbers=invented)
    return dict(result, text=template(fact_sheet, audience, lang), source='template')
