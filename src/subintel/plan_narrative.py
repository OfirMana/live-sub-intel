"""Grounded explanations of the inspected complete XI for broadcasters, analysts and coaches.

The model selects fact IDs; trusted code renders those facts from fixed sentence
templates. Arbitrary model prose never reaches the UI. This prevents swapped
names, signs or probabilities from passing merely because their numbers occur
somewhere in the input. Each audience has facts it always receives (the
decision, rejection reasons, material trade-offs, and for analysts the match
statistics and benefit), so brevity limits never drop them.
"""
from __future__ import annotations

from collections import namedtuple
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .narrative import foundry_client_from_env
from .foundry_runtime import classify_failure

AUDIENCES = ('broadcaster', 'analyst', 'coach')
AUDIENCE_ALIASES = {'fan': 'broadcaster'}  # Fan merged into Broadcaster (22 October 2026).
DEFAULT_AUDIENCE = 'broadcaster'
LANGUAGES = ('en', 'he')
RTL = ('he', 'ar')
TEMPLATE_VERSION = 'plan-templates-v2'
LOG = logging.getLogger(__name__)
# Canonical reading order; the model chooses which optional facts appear, not their order.
FACT_IDS = ('decision','reason','quality','state','urgency','stats','freshness','gain','shape','moves','tradeoff','discipline','score','components')
MAX_FACTS = dict(broadcaster=2, analyst=5, coach=4)
REQUIRED = dict(broadcaster=('decision','reason','quality','tradeoff'),
                analyst=('decision','reason','quality','stats','score','tradeoff'),
                coach=('decision','reason','quality','state','tradeoff'))
OPTIONAL = dict(broadcaster=('shape','gain','moves'),
                analyst=('gain','freshness','moves','components'),
                coach=('urgency','freshness','discipline','moves','gain'))
GUIDANCE = dict(broadcaster='One or two short sentences for fans and commentators; qualitative, no model scores.',
                analyst='Compact and quantitative: the match statistic, the need the plan addresses, its cost and its benefit against the threshold.',
                coach='Practical: game state and brief, urgency, estimated fatigue, role or shape changes and the downside.')

Term = namedtuple('Term', 'key')  # translatable vocabulary (a dimension, a position), not a literal value
Moves = namedtuple('Moves', 'items')  # ((player name, position term key), ...)


def normalize_audience(audience):
    audience = AUDIENCE_ALIASES.get(audience, audience)
    if audience not in AUDIENCES:
        raise ValueError('unsupported audience')
    return audience


def max_facts(audience):
    return MAX_FACTS[normalize_audience(audience)]


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    # Every ID is still checked against the bank; the per-audience length is
    # applied when rendering, so a long but valid selection is truncated, not rejected.
    fact_ids: list[str] = Field(min_length=1, max_length=len(FACT_IDS))
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


POSITION_HE={'Goalkeeper':'שוער','Right Back':'מגן ימני','Left Back':'מגן שמאלי','Right Center Back':'בלם ימני','Left Center Back':'בלם שמאלי','Center Back':'בלם','Right Wing Back':'מגן כנף ימני','Left Wing Back':'מגן כנף שמאלי','Right Defensive Midfield':'קשר אחורי ימני','Left Defensive Midfield':'קשר אחורי שמאלי','Center Defensive Midfield':'קשר אחורי','Right Center Midfield':'קשר מרכזי ימני','Left Center Midfield':'קשר מרכזי שמאלי','Center Midfield':'קשר מרכזי','Right Midfield':'קשר ימני','Left Midfield':'קשר שמאלי','Right Attacking Midfield':'קשר התקפי ימני','Left Attacking Midfield':'קשר התקפי שמאלי','Center Attacking Midfield':'קשר התקפי','Right Wing':'כנף ימין','Left Wing':'כנף שמאל','Right Center Forward':'חלוץ ימני','Left Center Forward':'חלוץ שמאלי','Center Forward':'חלוץ','Secondary Striker':'חלוץ שני'}
ROLE = {'en':dict(GK='goalkeeper', CB='centre-back', FB='full-back', CM='central midfield', AM_W='wide or attacking midfield', ST='striker'),
        'he':dict(GK='שוער', CB='בלם', FB='מגן', CM='קישור מרכזי', AM_W='כנף או קישור התקפי', ST='חלוץ')}
TERMS = {
    'en': {**{f'dim.{k}':v for k,v in dict(threat='attacking threat', creation='chance creation', progression='ball progression', retention='ball retention', defense='defending').items()},
           **{f'aim.{k}':v for k,v in dict(threat='add attacking threat', creation='create more chances', progression='move the ball forward more effectively', retention='keep the ball more securely', defense='strengthen the defending').items()},
           'stance.attack':'more attacking', 'stance.balanced':'balanced', 'stance.defend':'more defensive', 'objective.win':'seek a win', 'objective.draw':'a draw is enough',
           **{f'position.{k}':k for k in POSITION_HE}, **{f'role.{k}':v for k,v in ROLE['en'].items()}},
    'he': {**{f'dim.{k}':v for k,v in dict(threat='איום לשער', creation='יצירת מצבים', progression='קידום הכדור', retention='שמירת כדור', defense='הגנה').items()},
           **{f'aim.{k}':v for k,v in dict(threat='להוסיף איום לשער', creation='לייצר יותר מצבים', progression='לקדם את הכדור טוב יותר', retention='לשמור על הכדור בבטחה רבה יותר', defense='לחזק את ההגנה').items()},
           'stance.attack':'יותר התקפה', 'stance.balanced':'מאוזן', 'stance.defend':'יותר הגנה', 'objective.win':'לכוון לניצחון', 'objective.draw':'תיקו מספיק',
           **{f'position.{k}':v for k,v in POSITION_HE.items()}, **{f'role.{k}':v for k,v in ROLE['he'].items()}},
}
REASONS = ('OUTSIDE_DECISION_WINDOW','NO_SUBSTITUTIONS_LEFT','QUALITY_LOSS_TOO_LARGE','BELOW_THRESHOLD','NO_FEASIBLE_PLAN','MISSING_PLAYER_PROFILES','UNSUPPORTED_PLAYER_COUNT')
TEMPLATES = {
    'en': {
        'decision.swap.recommended': 'Bringing on {on} for {off} passes the recommendation rules.',
        'decision.swap.rejected': 'The option is {on} for {off}; it does not pass the recommendation rules.',
        'decision.swap.recommended.shape': 'Bringing on {on} for {off}, switching to {formation}, passes the recommendation rules.',
        'decision.swap.rejected.shape': 'The option is {on} for {off}, switching to {formation}; it does not pass the recommendation rules.',
        'decision.swap.recommended.broadcaster': 'The suggested change is {on} for {off}.',
        'decision.swap.recommended.broadcaster.fresh': 'The suggested change is {on} for {off}, bringing fresh legs for a player assessed as tiring.',
        'decision.swap.recommended.broadcaster.aim': 'The suggested change is {on} for {off}, to {aim}.',
        'decision.swap.rejected.broadcaster': '{on} for {off} is being considered, but the change is not justified yet.',
        'decision.tactical.recommended': 'The recommendation is to reposition the players already on the pitch, without a substitution.',
        'decision.tactical.alternative': 'This option repositions the players already on the pitch without a substitution; it is not the current recommendation.',
        'decision.tactical.recommended.shape': 'The recommendation is to reposition the players already on the pitch into {formation}, without a substitution.',
        'decision.tactical.alternative.shape': 'This option repositions the players already on the pitch into {formation} without a substitution; it is not the current recommendation.',
        'decision.tactical.recommended.broadcaster': 'The suggestion is to reshuffle the players already on the pitch rather than make a substitution.',
        'decision.tactical.alternative.broadcaster': 'Reshuffling the current players is being considered, but it is not the suggestion.',
        'decision.wait': 'No change currently passes the recommendation rules.',
        'decision.wait.broadcaster': 'No change is suggested at this point.',
        'reason.OUTSIDE_DECISION_WINDOW': 'The engine is waiting for its decision window.',
        'reason.NO_SUBSTITUTIONS_LEFT': 'All available substitutions have been used.',
        'reason.QUALITY_LOSS_TOO_LARGE': 'The available changes lose too much tactical quality.',
        'reason.BELOW_THRESHOLD': 'The available changes do not add enough beyond the best action without a substitution.',
        'reason.NO_FEASIBLE_PLAN': 'No complete plan fits the supported positions.',
        'reason.MISSING_PLAYER_PROFILES': 'Required player profiles are missing.',
        'reason.UNSUPPORTED_PLAYER_COUNT': 'This lineup size is outside the current search scope.',
        'quality.loss': 'The tactical loss is too large for the freshness gain to justify.',
        'quality.below': 'The extra benefit is insufficient compared with the best action without a substitution.',
        'quality.loss.broadcaster': 'The drop in quality would outweigh the fresh legs.',
        'quality.below.broadcaster': 'It would not add enough over keeping the current players.',
        'quality.loss.broadcaster.dim': 'The weaker {dim} would outweigh the fresh legs.',
        'quality.below.broadcaster.dim': 'It would not add enough over keeping the current players, and {dim} would suffer.',
        'state.lead': '{team} lead {score} at {minute}′; brief: {stance}, {objective}.',
        'state.level': '{team} are level, {score}, at {minute}′; brief: {stance}, {objective}.',
        'state.trail': '{team} trail {score} at {minute}′; brief: {stance}, {objective}.',
        'urgency.late': 'With a win still needed late on, the engine accepts somewhat more defensive risk.',
        'stats.attack': 'Match so far: {team} xG {xg}, shots {shots}, on target {on_target}; {opponent} xG {opp_xg}.',
        'stats.defense': 'Match so far: {opponent} xG {opp_xg}, shots {opp_shots}, on target {opp_on_target}; {team} xG {xg}.',
        'stats.passing': 'Match so far: {team} pass accuracy {accuracy}, estimated possession {possession}.',
        'stats.passing.no_possession': 'Match so far: {team} pass accuracy {accuracy}; possession is unknown.',
        'stats.unavailable': 'No match statistics are available before this checkpoint.',
        'freshness': 'The main driver is fresh legs for a player with estimated fatigue, weighed against the tactical trade-off.',
        'freshness.coach': "{off}'s fatigue is estimated from match load (not a medical measure), so fresh legs are the main reason.",
        'gain': 'The model rates the proposed XI higher for {dim}.',
        'gain.need': 'The model rates the proposed XI higher for {dim}, a current team need.',
        'gain.broadcaster': 'The aim is to {aim}.',
        'shape.broadcaster': 'The plan also changes the team shape.',
        'moves': 'Retained players also change positions: {moves}.',
        'moves.broadcaster': 'Some of the players staying on would also change positions.',
        'tradeoff': 'The modelled trade-off is weaker {dim}.',
        'tradeoff.broadcaster': 'The trade-off would be weaker {dim}.',
        'tradeoff.broadcaster.shape': 'The team shape would also change, at the cost of weaker {dim}.',
        'tradeoff.coach': 'The cost is weaker {dim}.',
        'discipline.yellow': '{off} is already on a yellow card; this is context only and not part of the score.',
        'score': 'Incremental benefit is {benefit} against a threshold of {threshold}; this is a model score, not a probability.',
        'components': 'The tactical component is {tactical} and freshness contributes {freshness}, after comparison with the no-substitution alternative.',
    },
    'he': {
        'decision.swap.recommended': 'הכנסת {on} במקום {off} עוברת את תנאי ההמלצה.',
        'decision.swap.rejected': 'נבדקת הכנסת {on} במקום {off}; החלופה אינה עוברת את תנאי ההמלצה.',
        'decision.swap.recommended.shape': 'הכנסת {on} במקום {off}, במעבר למערך {formation}, עוברת את תנאי ההמלצה.',
        'decision.swap.rejected.shape': 'נבדקת הכנסת {on} במקום {off}, במעבר למערך {formation}; החלופה אינה עוברת את תנאי ההמלצה.',
        'decision.swap.recommended.broadcaster': 'ההצעה היא להכניס את {on} במקום {off}.',
        'decision.swap.recommended.broadcaster.fresh': 'ההצעה היא להכניס את {on} במקום {off}, ולהביא רגליים רעננות במקום שחקן שמוערך כעייף.',
        'decision.swap.recommended.broadcaster.aim': 'ההצעה היא להכניס את {on} במקום {off}, כדי {aim}.',
        'decision.swap.rejected.broadcaster': '{on} במקום {off} זו אפשרות שנבחנת, אבל השינוי עדיין אינו מוצדק.',
        'decision.tactical.recommended': 'ההמלצה היא להציב מחדש את השחקנים שכבר במגרש, ללא חילוף.',
        'decision.tactical.alternative': 'אפשרות זו מציבה מחדש את השחקנים שכבר במגרש ללא חילוף; היא אינה ההמלצה הנוכחית.',
        'decision.tactical.recommended.shape': 'ההמלצה היא להציב מחדש את השחקנים שכבר במגרש במערך {formation}, ללא חילוף.',
        'decision.tactical.alternative.shape': 'אפשרות זו מציבה מחדש את השחקנים שכבר במגרש במערך {formation} ללא חילוף; היא אינה ההמלצה הנוכחית.',
        'decision.tactical.recommended.broadcaster': 'ההצעה היא לסדר מחדש את השחקנים שכבר במגרש במקום לבצע חילוף.',
        'decision.tactical.alternative.broadcaster': 'סידור מחדש של השחקנים הנוכחיים נבחן, אבל זו לא ההצעה.',
        'decision.wait': 'אין שינוי שעובר כעת את תנאי ההמלצה.',
        'decision.wait.broadcaster': 'בשלב הזה לא מוצע שינוי.',
        'reason.OUTSIDE_DECISION_WINDOW': 'המנוע ממתין לחלון ההחלטה שלו.',
        'reason.NO_SUBSTITUTIONS_LEFT': 'כל החילופים הזמינים נוצלו.',
        'reason.QUALITY_LOSS_TOO_LARGE': 'החלופות הזמינות מאבדות יותר מדי איכות טקטית.',
        'reason.BELOW_THRESHOLD': 'החלופות אינן מוסיפות מספיק מעבר לפעולה הטובה ביותר ללא חילוף.',
        'reason.NO_FEASIBLE_PLAN': 'אין תוכנית מלאה שמתאימה לעמדות הנתמכות.',
        'reason.MISSING_PLAYER_PROFILES': 'חסרים כרטיסי שחקנים הנדרשים לחישוב.',
        'reason.UNSUPPORTED_PLAYER_COUNT': 'גודל ההרכב הזה אינו נתמך בחיפוש הנוכחי.',
        'quality.loss': 'הירידה הטקטית גדולה מכדי שהרענון יצדיק אותה.',
        'quality.below': 'התועלת הנוספת אינה מספיקה ביחס לפעולה הטובה ביותר ללא חילוף.',
        'quality.loss.broadcaster': 'הירידה באיכות אינה מצדיקה את הרענון.',
        'quality.below.broadcaster': 'השינוי לא יוסיף מספיק על פני השארת השחקנים הנוכחיים.',
        'quality.loss.broadcaster.dim': 'הירידה ב{dim} אינה מצדיקה את הרענון.',
        'quality.below.broadcaster.dim': 'השינוי לא יוסיף מספיק על פני השארת השחקנים הנוכחיים, ויגרום לירידה ב{dim}.',
        'state.lead': '{team} מובילה {score} בדקה {minute}; ההנחיה: {stance}, {objective}.',
        'state.level': '{team} בשוויון {score} בדקה {minute}; ההנחיה: {stance}, {objective}.',
        'state.trail': '{team} בפיגור {score} בדקה {minute}; ההנחיה: {stance}, {objective}.',
        'urgency.late': 'כשעדיין נדרש ניצחון בשלב מאוחר, המנוע מוכן לקחת מעט יותר סיכון הגנתי.',
        'stats.attack': 'המשחק עד כה: {team} עם xG {xg}, בעיטות {shots}, למסגרת {on_target}; {opponent} עם xG {opp_xg}.',
        'stats.defense': 'המשחק עד כה: {opponent} עם xG {opp_xg}, בעיטות {opp_shots}, למסגרת {opp_on_target}; {team} עם xG {xg}.',
        'stats.passing': 'המשחק עד כה: דיוק המסירות של {team} {accuracy}, החזקה משוערת {possession}.',
        'stats.passing.no_possession': 'המשחק עד כה: דיוק המסירות של {team} {accuracy}; ההחזקה אינה ידועה.',
        'stats.unavailable': 'אין נתוני משחק זמינים לפני נקודת הבדיקה הזאת.',
        'freshness': 'השיקול המרכזי הוא רענון שחקן שעייפותו משוערת, לצד המחיר הטקטי.',
        'freshness.coach': 'העייפות של {off} מוערכת לפי עומס המשחק (לא מדידה רפואית), ולכן רגליים רעננות הן הסיבה העיקרית.',
        'gain': 'לפי המודל, ההרכב המוצע מוסיף {dim}.',
        'gain.need': 'לפי המודל, ההרכב המוצע מוסיף {dim}, בהתאם לצורך שזוהה כעת.',
        'gain.broadcaster': 'המטרה היא {aim}.',
        'shape.broadcaster': 'התוכנית משנה גם את מבנה הקבוצה.',
        'moves': 'גם שחקנים שנשארים במגרש מחליפים תפקידים: {moves}.',
        'moves.broadcaster': 'גם חלק מהשחקנים שנשארים במגרש ישנו עמדה.',
        'tradeoff': 'המחיר לפי המודל הוא ירידה ב{dim}.',
        'tradeoff.broadcaster': 'הוויתור יהיה על {dim}.',
        'tradeoff.broadcaster.shape': 'גם מבנה הקבוצה ישתנה, במחיר ירידה ב{dim}.',
        'tradeoff.coach': 'המחיר הוא ירידה ב{dim}.',
        'discipline.yellow': '{off} כבר עם כרטיס צהוב; זה הקשר בלבד ואינו חלק מהניקוד.',
        'score': 'תוספת התועלת היא {benefit} מול סף {threshold}; זה ציון מודל, לא הסתברות.',
        'components': 'הרכיב הטקטי הוא {tactical} ורכיב הרענון {freshness}, לאחר השוואה לחלופה ללא חילוף.',
    },
}


def fact_bundle(snapshot, plan_id):
    plan = chosen_plan(snapshot, plan_id)
    state = snapshot['state']
    match = snapshot.get('match_facts')
    if match:
        # Only the players this plan names; the full table stays in the page's statistics.
        named = {p['id'] for p in (plan or {}).values() if isinstance(p, dict) and 'id' in p} if plan else set()
        match = dict(match, players={k:v for k,v in match['players'].items() if k in named})
    return dict(version='grounded-plan-v2', plan_id=plan_id, minute=snapshot['minute'],
        team_id=snapshot['team_id'], coach=snapshot['coach_config'], goal_diff=state['goal_diff'],
        decision=snapshot['recommendation'], no_substitution_reason=snapshot.get('no_substitution_reason'), threshold=snapshot['threshold'],
        late_game_policy=snapshot.get('late_game_policy'), match=match,
        provenance=snapshot['provenance'], inspected_plan=plan,
        reference=snapshot.get('formation_only'), team_needs=snapshot['team_needs'])


def snapshot_need(bundle, dimension):
    return bundle['team_needs'].get(dimension,0)>=.6


def _stats_fact(bundle, focus):
    match = bundle.get('match')
    if not match or not match['events_observed']:
        return 'stats.unavailable', {}
    t, o = match['team'], match['opponent']
    params = dict(team=t['name'], opponent=o['name'], xg=f"{t['xg']:.2f}", shots=t['shots'], on_target=t['on_target'],
                  opp_xg=f"{o['xg']:.2f}", opp_shots=o['shots'], opp_on_target=o['on_target'])
    if focus in ('progression','retention') and t['pass_accuracy'] is not None:
        params['accuracy'] = f"{t['pass_accuracy']:.1f}%"  # the sign stays inside the number's isolate
        if t['possession'] is None:
            return 'stats.passing.no_possession', params
        params['possession'] = f"{t['possession']:.1f}%"
        return 'stats.passing', params
    return ('stats.defense' if focus=='defense' else 'stats.attack'), params


def facts(bundle, audience):
    """Language-independent facts: fact ID -> (template key, params). Audience picks the wording."""
    audience = normalize_audience(audience)
    b, a, c = audience=='broadcaster', audience=='analyst', audience=='coach'
    p = bundle['inspected_plan']
    out = {}
    needs = bundle['team_needs']
    focus = max(needs, key=needs.get) if needs else 'threat'
    if p is None:
        out['decision'] = ('decision.wait.broadcaster' if b else 'decision.wait', {})
        if bundle.get('no_substitution_reason') in REASONS:
            out['reason'] = ('reason.'+bundle['no_substitution_reason'], {})
    else:
        is_swap = p['plan_kind']=='SUBSTITUTION'
        changes = p.get('lineup_changes', {})
        positive = sorted(((d,v) for d,v in changes.items() if v>.01), key=lambda v:-v[1])
        negative = sorted(((d,v) for d,v in changes.items() if v<-.01), key=lambda v:v[1])
        fresh = is_swap and p.get('decision_basis')=='FRESH_LEGS'
        if positive:
            focus = positive[0][0]
        if is_swap:
            names = dict(on=p['in_player']['name'], off=p['out_player']['name'])
            if not p['recommended']:
                out['decision'] = ('decision.swap.rejected'+('.broadcaster' if b else ''), names)
            elif b and fresh:
                out['decision'] = ('decision.swap.recommended.broadcaster.fresh', names)
            elif b and positive:
                out['decision'] = ('decision.swap.recommended.broadcaster.aim', dict(names, aim=Term('aim.'+positive[0][0])))
            else:
                out['decision'] = ('decision.swap.recommended'+('.broadcaster' if b else ''), names)
            gate = 'loss' if not p.get('quality_gate_passed', True) else 'below' if not p.get('clears_threshold', False) else None
            if gate and b and negative:
                # One sentence carries both the rejection reason and its cost.
                out['quality'] = (f'quality.{gate}.broadcaster.dim', dict(dim=Term('dim.'+negative[0][0])))
            elif gate:
                out['quality'] = (f'quality.{gate}'+('.broadcaster' if b else ''), {})
            if fresh and not b:
                out['freshness'] = ('freshness.coach', dict(off=names['off'])) if c else ('freshness', {})
        else:
            out['decision'] = ('decision.tactical.'+('recommended' if p.get('recommended') else 'alternative')+('.broadcaster' if b else ''), {})
        if p.get('change_type')=='FORMATION_CHANGE':
            # Broadcasters receive no formation digits; for the others the decision sentence names the new shape.
            if b:
                out['shape'] = ('shape.broadcaster', {})
            else:
                key, params = out['decision']
                out['decision'] = (key+'.shape', dict(params, formation=p['formation']))
        moves = p.get('repositioned', [])
        if moves:
            out['moves'] = ('moves.broadcaster', {}) if b else ('moves', dict(moves=Moves(tuple(
                (m['name'], 'position.'+m['after_position'] if m['after_position'] in POSITION_HE else 'role.'+m['after']) for m in moves[:3]))))
        # Use whole-XI changes, not the incoming/outgoing raw card difference.
        if positive and not (b and is_swap):
            d = positive[0][0]
            out['gain'] = ('gain.broadcaster', dict(aim=Term('aim.'+d))) if b else (('gain.need' if snapshot_need(bundle,d) else 'gain'), dict(dim=Term('dim.'+d)))
        if negative and not (b and 'quality' in out):
            if b and 'shape' in out:
                out.pop('shape')
                out['tradeoff'] = ('tradeoff.broadcaster.shape', dict(dim=Term('dim.'+negative[0][0])))
            else:
                out['tradeoff'] = ('tradeoff'+('.broadcaster' if b else '.coach' if c else ''), dict(dim=Term('dim.'+negative[0][0])))
        if a:
            out['score'] = ('score', dict(benefit=f"{p['expected_benefit']:.3f}", threshold=f"{bundle['threshold']:.3f}"))
            if is_swap:
                x = p['score_components']
                out['components'] = ('components', dict(tactical=f"{x['tactical_benefit']:.3f}", freshness=f"{x['freshness_benefit']:.3f}"))
        if c and is_swap:
            card = ((bundle.get('match') or {}).get('players') or {}).get(p['out_player']['id'])
            if card and card['yellows'] and not card['red']:
                out['discipline'] = ('discipline.yellow', dict(off=p['out_player']['name']))
    if a:
        out['stats'] = _stats_fact(bundle, focus)
    if c:
        match = bundle.get('match')
        if match:
            gf, ga = match['team']['goals'], match['opponent']['goals']
            out['state'] = ('state.'+('lead' if gf>ga else 'trail' if gf<ga else 'level'), dict(team=match['team']['name'], score=f'{gf}–{ga}',
                minute=bundle['minute'], stance=Term('stance.'+bundle['coach'].get('stance','balanced')), objective=Term('objective.'+bundle['coach'].get('objective','win'))))
        if (bundle.get('late_game_policy') or {}).get('active'):
            out['urgency'] = ('urgency.late', {})
    return {k: out[k] for k in FACT_IDS if k in out}


def isolate(text, lang):
    """Left-to-right isolate (LRI…PDI) for names and numbers inside right-to-left text, so 0–1 never shows as 1–0."""
    return f'⁦{text}⁩' if lang in RTL else str(text)


def render(template_key, params, lang, templates=None, terms=None):
    templates, terms = templates or TEMPLATES[lang], terms or TERMS[lang]
    def value(v):
        if isinstance(v, Term):
            return terms[v.key]
        if isinstance(v, Moves):
            return '; '.join(f'{isolate(name, lang)} → {terms[key]}' for name, key in v.items)
        return isolate(v, lang)
    return templates[template_key].format(**{k: value(v) for k, v in params.items()})


def sentences(bundle, audience, lang):
    """Each ID has a single verified meaning, localized from a fixed template."""
    return {fid: render(key, params, lang) for fid, (key, params) in facts(bundle, audience).items()}


def required_ids(bank, audience):
    return [k for k in REQUIRED[normalize_audience(audience)] if k in bank]


def compose(bank, audience, chosen=()):
    """Required facts always; then chosen optional facts up to the audience limit; canonical order."""
    audience = normalize_audience(audience)
    required = required_ids(bank, audience)
    optional = [k for k in chosen if k in bank and k not in required]
    keep = set(required + optional[:max(MAX_FACTS[audience]-len(required), 0)])
    return [k for k in FACT_IDS if k in keep]


def default_ids(bank, audience):
    return compose(bank, audience, OPTIONAL[normalize_audience(audience)])


def explain_plan(snapshot, plan_id, audience=DEFAULT_AUDIENCE, lang='en', client=None, deployment=None):
    audience = normalize_audience(audience)
    if lang not in LANGUAGES:
        raise ValueError('unsupported language')
    bundle = fact_bundle(snapshot, plan_id)
    bank = sentences(bundle,audience,lang)
    ids = default_ids(bank,audience)
    source, note = 'template', 'LLM_NOT_CONFIGURED'
    diagnostic=None;stage='configuration'
    try:
        if client is None:
            configured=foundry_client_from_env()
            if configured:
                client,deployment=configured
                stage='client_setup'
                client=client.with_options(timeout=12,max_retries=0)
        if client is not None:
            stage='provider_request'
            response=client.chat.completions.create(model=deployment, max_completion_tokens=250,
                response_format={'type':'json_object'}, messages=[
                    {'role':'system','content':'Select relevant fact IDs for a football explanation. Return JSON only, exactly {"fact_ids":[...],"style":"direct"}. '
                        'fact_ids: between 1 and max_facts unique keys of available_facts, copied exactly and never translated, with "decision" first. '
                        'required_facts are always shown; choose the optional facts that best serve the audience guidance. '
                        'style: "direct" or "context". No other keys and no prose. The deterministic engine owns the decision.'},
                    {'role':'user','content':json.dumps(dict(audience=audience,guidance=GUIDANCE[audience],language=lang,max_facts=MAX_FACTS[audience],
                        required_facts=required_ids(bank,audience),available_facts=bank,context=bundle),ensure_ascii=False)}])
            stage='output_validation'
            selection=Selection.model_validate_json(response.choices[0].message.content or '')
            if selection.fact_ids[0]!='decision' or len(set(selection.fact_ids))!=len(selection.fact_ids) or any(k not in bank for k in selection.fact_ids):
                raise ValueError('invalid fact selection')
            # Required caveats cannot be truncated by a long model selection.
            ids=compose(bank,audience,selection.fact_ids)
            source,note='llm',None
    except Exception as error:
        # No keys, response bodies or arbitrary model text in public diagnostics.
        diagnostic=dict(classify_failure(error,stage),reference=uuid.uuid4().hex[:12],
                        at=datetime.now(timezone.utc).isoformat())
        LOG.warning('Explanation failed: reference=%s code=%s stage=%s status=%s provider_code=%s param=%s type=%s causes=%s validation=%s',
            diagnostic['reference'],diagnostic['code'],stage,diagnostic['status'],diagnostic['provider_code'],diagnostic['provider_param'],diagnostic['exception_type'],diagnostic['cause_types'],diagnostic['validation_errors'])
        note='LLM_TEXT_REJECTED' if stage=='output_validation' else 'LLM_CONFIGURATION_INVALID' if stage=='configuration' else 'LLM_UNAVAILABLE'
    return dict(text=' '.join(bank[k] for k in ids), source=source,note=note,
                audience=audience,lang=lang,plan_id=plan_id,facts=bundle,fact_ids=ids,template_version=TEMPLATE_VERSION,
                rendering='VERIFIED_FACT_SENTENCES',model=deployment if source=='llm' else None,diagnostic=diagnostic)
