"""Grounded explanations of the inspected complete XI, in English or Hebrew.

The model selects fact IDs; trusted code renders those facts. Arbitrary model
prose never reaches the UI. This prevents swapped names, signs or probabilities
from passing merely because their numbers occur somewhere in the input.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .narrative import foundry_client_from_env

AUDIENCES = ('fan', 'analyst', 'broadcaster')
LANGUAGES = ('en', 'he')
LOG = logging.getLogger(__name__)


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fact_ids: list[str] = Field(min_length=1, max_length=6)
    style: Literal['direct', 'context'] = 'direct'


def identified(snapshot):
    """Stable IDs are server-derived; never accept client-authored facts."""
    result = []
    for plan in snapshot['alternatives']:
        result.append(dict(plan, plan_id=f"swap:{plan['out_player']['id']}:{plan['in_player']['id']}"))
    tactical = snapshot.get('best_no_substitution')
    if tactical and tactical.get('raw_plan_benefit', 0) > 0:
        result.append(dict(tactical, plan_id='tactical', expected_benefit=tactical['raw_plan_benefit'],
                           recommended=snapshot['recommendation']=='TACTICAL_ADJUSTMENT'))
    return result


def chosen_plan(snapshot, plan_id):
    if plan_id == 'wait':
        if snapshot['recommendation'] != 'NO_SUBSTITUTION':
            raise ValueError('wait is not the current decision')
        return None
    return next((p for p in identified(snapshot) if p['plan_id']==plan_id), None) or _unknown()


def _unknown():
    raise ValueError('unknown plan')


DIM = {
    'en': dict(threat='attacking threat', creation='chance creation', progression='ball progression', retention='ball retention', defense='defending'),
    'he': dict(threat='איום לשער', creation='יצירת מצבים', progression='קידום הכדור', retention='שמירת כדור', defense='הגנה'),
}
ROLE = {'en':dict(GK='goalkeeper', CB='centre-back', FB='full-back', CM='central midfield', AM_W='wide or attacking midfield', ST='striker'),
        'he':dict(GK='שוער', CB='בלם', FB='מגן', CM='קישור מרכזי', AM_W='כנף או קישור התקפי', ST='חלוץ')}
POSITION_HE={'Goalkeeper':'שוער','Right Back':'מגן ימני','Left Back':'מגן שמאלי','Right Center Back':'בלם ימני','Left Center Back':'בלם שמאלי','Center Back':'בלם','Right Wing Back':'מגן כנף ימני','Left Wing Back':'מגן כנף שמאלי','Right Defensive Midfield':'קשר אחורי ימני','Left Defensive Midfield':'קשר אחורי שמאלי','Center Defensive Midfield':'קשר אחורי','Right Center Midfield':'קשר מרכזי ימני','Left Center Midfield':'קשר מרכזי שמאלי','Center Midfield':'קשר מרכזי','Right Midfield':'קשר ימני','Left Midfield':'קשר שמאלי','Right Attacking Midfield':'קשר התקפי ימני','Left Attacking Midfield':'קשר התקפי שמאלי','Center Attacking Midfield':'קשר התקפי','Right Wing':'כנף ימין','Left Wing':'כנף שמאל','Right Center Forward':'חלוץ ימני','Left Center Forward':'חלוץ שמאלי','Center Forward':'חלוץ','Secondary Striker':'חלוץ שני'}


def fact_bundle(snapshot, plan_id):
    plan = chosen_plan(snapshot, plan_id)
    state = snapshot['state']
    bundle = dict(version='grounded-plan-v1', plan_id=plan_id, minute=snapshot['minute'],
        team_id=snapshot['team_id'], coach=snapshot['coach_config'], goal_diff=state['goal_diff'],
        decision=snapshot['recommendation'], no_substitution_reason=snapshot.get('no_substitution_reason'), threshold=snapshot['threshold'],
        provenance=snapshot['provenance'], inspected_plan=plan,
        reference=snapshot.get('formation_only'), team_needs=snapshot['team_needs'])
    return bundle


def sentences(bundle, audience, lang):
    """Each ID has a single verified meaning, localized without numeric broadcaster copy."""
    he = lang=='he'
    p = bundle['inspected_plan']
    if p is None:
        bank={'decision': 'אין שינוי שעובר כעת את תנאי ההמלצה.' if he else 'No change currently passes the recommendation rules.'}
        reasons={
            'OUTSIDE_DECISION_WINDOW':('The engine is waiting for its decision window.','המנוע ממתין לחלון ההחלטה שלו.'),
            'NO_SUBSTITUTIONS_LEFT':('All available substitutions have been used.','כל החילופים הזמינים נוצלו.'),
            'QUALITY_LOSS_TOO_LARGE':('The available changes lose too much tactical quality.','החלופות הזמינות מאבדות יותר מדי איכות טקטית.'),
            'BELOW_THRESHOLD':('The available changes do not add enough beyond the best action without a substitution.','החלופות אינן מוסיפות מספיק מעבר לפעולה הטובה ביותר ללא חילוף.'),
            'NO_FEASIBLE_PLAN':('No complete plan fits the supported positions.','אין תוכנית מלאה שמתאימה לעמדות הנתמכות.'),
            'MISSING_PLAYER_PROFILES':('Required player profiles are missing.','חסרים כרטיסי שחקנים הנדרשים לחישוב.'),
            'UNSUPPORTED_PLAYER_COUNT':('This lineup size is outside the current search scope.','גודל ההרכב הזה אינו נתמך בחיפוש הנוכחי.')}
        reason=reasons.get(bundle.get('no_substitution_reason'))
        if reason:bank['reason']=reason[1 if he else 0]
        return bank
    is_swap = p['plan_kind']=='SUBSTITUTION'
    if is_swap:
        on, off = p['in_player']['name'], p['out_player']['name']
        # A rejected alternative is never phrased as the engine's recommendation.
        if p['recommended']:
            head = f'הכנסת {on} במקום {off} עוברת את תנאי ההמלצה.' if he else f'Bringing on {on} for {off} passes the recommendation rules.'
        else:
            head = f'נבדקת הכנסת {on} במקום {off}; החלופה אינה עוברת את תנאי ההמלצה.' if he else f'The option is {on} for {off}; it does not pass the recommendation rules.'
        if audience=='broadcaster':
            head=(f'ההצעה היא להכניס את {on} במקום {off}.' if he else f'The suggested change is {on} for {off}.') if p['recommended'] else (f'{on} במקום {off} זו אפשרות שנבחנת, אבל השינוי עדיין אינו מוצדק.' if he else f'{on} for {off} is being considered, but the change is not justified yet.')
    else:
        head = 'זו הצבה מחדש של השחקנים שכבר במגרש, ללא חילוף.' if he else 'This repositions the players already on the pitch, without a substitution.'
    result = {'decision': head}
    x = p['score_components']
    if is_swap and p.get('decision_basis')=='FRESH_LEGS':
        result['freshness'] = 'השיקול המרכזי הוא רענון שחקן שעייפותו משוערת, לצד המחיר הטקטי.' if he else 'The main driver is fresh legs for a player with estimated fatigue, weighed against the tactical trade-off.'
        if audience=='broadcaster':result['freshness']='הרעיון הוא להכניס רגליים רעננות במקום שחקן שמוערך כעייף.' if he else 'The idea is to bring on fresh legs for a player assessed as tiring.'
    if is_swap and not p.get('quality_gate_passed', True):
        result['quality'] = 'הירידה הטקטית גדולה מכדי שהרענון יצדיק אותה.' if he else 'The tactical loss is too large for the freshness gain to justify.'
        if audience=='broadcaster':result['quality']='הירידה באיכות אינה מצדיקה את הרענון.' if he else 'The drop in quality would outweigh the fresh legs.'
    elif is_swap and not p.get('clears_threshold', False):
        result['quality'] = 'התועלת הנוספת אינה מספיקה ביחס לפעולה הטובה ביותר ללא חילוף.' if he else 'The extra benefit is insufficient compared with the best action without a substitution.'
    if p.get('change_type')=='FORMATION_CHANGE':
        # Broadcasters receive no formation digits, scores or measured-sounding claims.
        result['shape'] = ('התוכנית משנה גם את מבנה הקבוצה.' if he else 'The plan also changes the team shape.') if audience=='broadcaster' else (f"התוכנית מציבה את הקבוצה במערך {p['formation']}." if he else f"The proposed formation is {p['formation']}.")
    moves = p.get('repositioned', [])
    if moves:
        moves_copy = '; '.join(f"{m['name']} → {POSITION_HE.get(m['after_position'],ROLE[lang][m['after']]) if he else m['after_position']}" for m in moves[:3])
        result['moves'] = ('גם שחקנים שנשארים במגרש מחליפים תפקידים: ' if he else 'Retained players also change positions: ') + moves_copy + '.'
        if audience=='broadcaster':result['moves']='גם חלק מהשחקנים שנשארים במגרש ישנו עמדה.' if he else 'Some of the players staying on would also change positions.'
    # Use whole-XI changes, not the incoming/outgoing raw card difference.
    changes = p.get('lineup_changes', {})
    positive = sorted(((d,v) for d,v in changes.items() if v>.01), key=lambda v:-v[1])
    negative = sorted(((d,v) for d,v in changes.items() if v<-.01), key=lambda v:v[1])
    if positive:
        d = positive[0][0]
        result['gain'] = (f"לפי המודל, ההרכב המוצע מוסיף {DIM[lang][d]}." if he else f"The model rates the proposed XI higher for {DIM[lang][d]}.")
        if audience=='broadcaster':
            aims={'threat':'add attacking threat','creation':'create more chances','progression':'move the ball forward more effectively','retention':'keep the ball more securely','defense':'strengthen the defending'}
            result['gain']=f"המטרה היא להוסיף {DIM[lang][d]}." if he else f"The aim is to {aims[d]}."
        if snapshot_need(bundle, d):
            result['need'] = f"השיפור ב{DIM[lang][d]} מתאים לצורך שזוהה כעת." if he else f"The improvement in {DIM[lang][d]} addresses a current team need."
    if negative:
        d = negative[0][0]
        result['tradeoff'] = f"המחיר לפי המודל הוא ירידה ב{DIM[lang][d]}." if he else f"The modelled trade-off is weaker {DIM[lang][d]}."
        if audience=='broadcaster':result['tradeoff']=f"הוויתור יהיה על {DIM[lang][d]}." if he else f"The trade-off would be weaker {DIM[lang][d]}."
    if audience=='analyst':
        value = p['expected_benefit']
        result['score'] = (f"תוספת התועלת היא {value:.3f} מול סף {bundle['threshold']:.3f}; זה ציון מודל, לא הסתברות." if he else f"Incremental benefit is {value:.3f} against a threshold of {bundle['threshold']:.3f}; this is a model score, not a probability.")
        if is_swap:
            result['components'] = (f"הרכיב הטקטי הוא {x['tactical_benefit']:.3f} ורכיב הרענון {x['freshness_benefit']:.3f}, לאחר השוואה לחלופה ללא חילוף." if he else f"The tactical component is {x['tactical_benefit']:.3f} and freshness contributes {x['freshness_benefit']:.3f}, after comparison with the no-substitution alternative.")
    return result


def snapshot_need(bundle, dimension):
    return bundle['team_needs'].get(dimension,0)>=.6


def default_ids(bank, audience):
    priority = ['decision','reason','freshness','quality','shape','moves','gain','tradeoff','need','score','components']
    if audience=='broadcaster':
        priority = ['decision','reason','quality','freshness','shape','tradeoff','gain','moves']
    limit = 3 if audience=='broadcaster' else 6 if audience=='analyst' else 4
    ids=[k for k in priority if k in bank][:limit]
    # Preserve an important tradeoff when there is one.
    if 'tradeoff' in bank and 'tradeoff' not in ids:
        ids[-1]='tradeoff'
    return ids


def explain_plan(snapshot, plan_id, audience='fan', lang='en', client=None, deployment=None):
    if audience not in AUDIENCES or lang not in LANGUAGES:
        raise ValueError('unsupported audience or language')
    bundle = fact_bundle(snapshot, plan_id)
    bank = sentences(bundle,audience,lang)
    ids = default_ids(bank,audience)
    source, note = 'template', 'LLM_NOT_CONFIGURED'
    try:
        if client is None:
            configured=foundry_client_from_env()
            if configured:
                client,deployment=configured
                client=client.with_options(timeout=12,max_retries=0)
        if client is not None:
            response=client.chat.completions.create(model=deployment, max_completion_tokens=250,
                response_format={'type':'json_object'}, messages=[
                    {'role':'system','content':'Select relevant fact IDs for a football explanation. Return JSON only: {"fact_ids":[...],"style":"direct"}. Use only supplied IDs, include decision first. Never return prose. Respect the audience; broadcaster is qualitative. The deterministic engine owns the decision.'},
                    {'role':'user','content':json.dumps(dict(audience=audience,language=lang,available_facts=bank,context=bundle),ensure_ascii=False)}])
            selection=Selection.model_validate_json(response.choices[0].message.content or '')
            if selection.fact_ids[0]!='decision' or len(set(selection.fact_ids))!=len(selection.fact_ids) or any(k not in bank for k in selection.fact_ids):
                raise ValueError('invalid fact selection')
            required=[k for k in ('reason','quality','tradeoff','shape') if k in bank]
            if audience=='analyst' and 'moves' in bank:required.append('moves')
            # Required caveats cannot be truncated by a long model selection.
            optional=[k for k in selection.fact_ids if k not in ['decision',*required]]
            limit=3 if audience=='broadcaster' else 6
            limit=max(limit,1+len(required))
            ids=list(dict.fromkeys(['decision',*required,*optional]))[:limit]
            source,note='llm',None
    except Exception as error:
        # No keys, response bodies or arbitrary model text in public diagnostics.
        cause=error.__cause__ or error.__context__
        LOG.warning('Explanation failed: type=%s status=%s code=%s cause=%s',type(error).__name__,getattr(error,'status_code',None),
                    getattr(error,'code',None),f'{type(cause).__name__}: {str(cause)[:200]}' if cause else None)
        note='LLM_TEXT_REJECTED' if isinstance(error,(ValueError,KeyError,TypeError)) else 'LLM_UNAVAILABLE'
    return dict(text=' '.join(bank[k] for k in ids), source=source,note=note,
                audience=audience,lang=lang,plan_id=plan_id,facts=bundle,fact_ids=ids,
                rendering='VERIFIED_FACT_SENTENCES',model=deployment if source=='llm' else None)
