"""Model translation of fixed English sentence templates, validated before use.

Only templates and vocabulary are translated, never values: player names, numbers,
plan identity and statuses are inserted by the server afterwards through
placeholders. A translation is accepted only if every placeholder survives exactly
once, no digit or ID is added or lost, and a negated English sentence stays
negated. Structural checks do not prove semantic fidelity; see
tests/fixtures/translations.json for reviewed examples.
"""
import json
import re
import threading
from collections import Counter

TRANSLATION_PROMPT_VERSION = 'template-translation-v3-context'
TRUSTED = ('en', 'he')  # hand-written templates in plan_narrative
LANGUAGE_NAMES = {'ar': 'Arabic', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian',
                  'pt': 'Portuguese', 'ja': 'Japanese', 'zh-Hans': 'Simplified Chinese'}
PLACEHOLDER = re.compile(r'\{(\w+)\}')
ENGLISH_NEGATION = re.compile(r"\b(not|no|never|nothing)\b|n't\b", re.IGNORECASE)
NEGATION = {
    'es': r'\b(no|ni|sin|nunca|ningún|ninguna|ninguno)\b',
    'fr': r"\b(ne|pas|non|aucun|aucune|sans|jamais)\b|\bn['’]",
    'de': r'\b(nicht|kein|keine|keinen|keinem|keiner|keines|ohne|nie)\b',
    'it': r'\b(non|senza|nessun|nessuna|nessuno|mai)\b',
    'pt': r'\b(não|nao|sem|nenhum|nenhuma|nunca)\b',
    'ar': r'(?<!\w)و?(لا|لم|لن|ليس|ليست|غير|دون|بدون)(?!\w)',
    'ja': r'(ない|ません|ず|未|不|無)',
    'zh-Hans': r'(不|未|没|无|非)',
}
# A sentence about the recommendation criteria must say "meets" with the language's ordinary verb:
# the first live run turned "passes the recommendation rules" into "violates", "contradicts" and "exceeds".
STATUS_SOURCE = re.compile(r'recommendation criteria', re.IGNORECASE)
STATUS_VERB = {
    'es': r'\b(cumple|cumplen|satisface|reúne)\b',
    'fr': r'\b(respecte|remplit|satisfait)\b',
    'de': r'\b(erfüllt|erfüllen|entspricht)\b',
    'it': r'\b(soddisfa|rispetta|soddisfano)\b',
    'pt': r'\b(cumpre|atende|satisfaz)\b',
    'ar': r'(يستوفي|تستوفي|يلبي|تلبي|يفي|تفي)',
    'ja': r'(満たし|満たす|適合)',
    'zh-Hans': r'(符合|满足)',
}
RECOMMENDATION_SOURCE = re.compile(r'The recommendation is \{on\} for \{off\}|This change is not recommended',re.IGNORECASE)
RECOMMENDATION_WORD = {
 'es':r'(recomend|recomiend)', 'fr':r'recommand', 'de':r'(empfohl|empfehl|empfiehl)',
 'it':r'(raccomand|consigli|sugger)', 'pt':r'recomend', 'ar':r'(يوصى|توصي|ينصح|الموصى|التوصية|موصى)',
 'ja':r'(推奨|勧め|すすめ|提案)', 'zh-Hans':r'(建议|推荐)',
}
STATUS_OPPOSITE = {
    'es': r'(viola|contradice)', 'fr': r'(viole|contredit)',
    'de': r'(widerspricht|verletzt|verstößt)', 'it': r'(viola|contraddice)',
    'pt': r'(viola|contraria|ultrapassa)', 'ar': r'(ينتهك|يخالف)',
    'ja': r'(違反|反する)', 'zh-Hans': r'(违反|违背)',
}

STATUS_EXAMPLE = {'es': 'cumple / no cumple', 'fr': 'respecte / ne respecte pas', 'de': 'erfüllt / erfüllt nicht',
                  'it': 'soddisfa / non soddisfa', 'pt': 'cumpre / não cumpre', 'ar': 'يستوفي / لا يستوفي',
                  'ja': '満たしています / 満たしていません', 'zh-Hans': '符合 / 不符合'}
SENTENCE_JOIN = {'ja': '', 'zh-Hans': ''}  # these scripts do not put spaces between sentences


class TranslationRejected(ValueError):
    def __init__(self, rule, item=None):
        self.rule, self.item = rule, item
        super().__init__(rule)  # never the model's text


def validate(lang, sources, translations):
    """Raise TranslationRejected unless every translation keeps the source's structure and negation."""
    if not isinstance(translations, dict) or set(translations) != set(sources):
        raise TranslationRejected('ids')
    for key, source in sources.items():
        text = translations[key]
        if not isinstance(text, str) or not text.strip():
            raise TranslationRejected('empty', key)
        if len(text) > 4*len(source) + 60:
            raise TranslationRejected('length', key)
        if Counter(PLACEHOLDER.findall(text)) != Counter(PLACEHOLDER.findall(source)):
            raise TranslationRejected('placeholders', key)
        if text.count('{') != text.count('}') or text.count('{') != len(PLACEHOLDER.findall(source)):
            raise TranslationRejected('braces', key)
        if Counter(re.findall(r'\d', text)) != Counter(re.findall(r'\d', source)):
            raise TranslationRejected('digits', key)
        negated = bool(ENGLISH_NEGATION.search(source))
        if negated and not re.search(NEGATION[lang], text, re.IGNORECASE):
            raise TranslationRejected('negation', key)
        if RECOMMENDATION_SOURCE.search(source):
            if (not re.search(RECOMMENDATION_WORD[lang],text,re.IGNORECASE)
                    or re.search(STATUS_OPPOSITE[lang],text,re.IGNORECASE)
                    or (not negated and re.search(NEGATION[lang],text,re.IGNORECASE))):
                raise TranslationRejected('status',key)
        if STATUS_SOURCE.search(source):
            # The recommendation status must keep its polarity: the "meets" verb, negated only when the source is.
            if not re.search(STATUS_VERB[lang], text, re.IGNORECASE) or (not negated and re.search(NEGATION[lang], text, re.IGNORECASE)):
                raise TranslationRejected('status', key)


class TranslationCatalog:
    """Validated translations per (locale, source key); process-local and versioned through its keys."""
    def __init__(self):
        self.lock = threading.Lock()
        self.entries = {}

    def missing(self, lang, keys):
        with self.lock:
            return sorted({k for k in keys if (lang, k) not in self.entries})

    def add(self, lang, mapping):
        with self.lock:
            self.entries.update({(lang, k): v for k, v in mapping.items()})

    def lookup(self, lang, prefix):
        with self.lock:
            return {k[len(prefix):]: v for (l, k), v in self.entries.items() if l == lang and k.startswith(prefix)}

    def counts(self):
        with self.lock:
            return dict(Counter(lang for lang, _ in self.entries))


SCHEMA_SUPPORTED = [True]  # downgraded once if the deployment refuses json_schema


def translate(client, deployment, lang, sources):
    """One bounded call: aliases t0..tn keep property names simple; returns validated translations."""
    keys = sorted(sources)
    alias = {f't{i}': k for i, k in enumerate(keys)}
    items = {a: sources[k] for a, k in alias.items()}
    schema = dict(type='object', additionalProperties=False, required=['translations'], properties=dict(
        translations=dict(type='object', additionalProperties=False, required=list(items), properties={a: dict(type='string') for a in items})))
    response_format = ({'type': 'json_schema', 'json_schema': dict(name='template_translations', strict=True, schema=schema)}
                       if SCHEMA_SUPPORTED[0] else {'type': 'json_object'})
    system = (f'Translate football analysis sentence templates and terms from English into {LANGUAGE_NAMES[lang]}. '
              'Return JSON only: {"translations": {"<id>": "<translation>"}} with exactly the same ids. '
              'Keep every {placeholder} exactly as written, untranslated, once each. Do not add numbers, names, facts or explanations. '
              'Keep negations and uncertainty ("estimated", "not a probability") in meaning. Keep "xG" as is. '
              '"Meets the recommendation criteria" means the plan satisfies the rules and is recommended; translate it with the ordinary '
              f'verb for "meets/satisfies" ({STATUS_EXAMPLE[lang]}), never as violating, contradicting or exceeding the rules. '
              '"Bringing on A for B" means A comes on and B goes off. "Weaker" always means a loss. '
              'A recommendation must remain a recommendation, and a change described as not recommended must stay rejected. Never reverse player movement direction (from/to). Terms are short phrases inserted into the sentences; translate them so they read naturally there. '
              'Use a neutral, professional sports-analysis register.')
    try:
        response = client.chat.completions.create(model=deployment, max_completion_tokens=1500, temperature=0, response_format=response_format,
                                                  messages=[{'role': 'system', 'content': system},
                                                            {'role': 'user', 'content': json.dumps(dict(items=items), ensure_ascii=False)}])
    except Exception as error:
        if getattr(error, 'status_code', None) == 400 and getattr(error, 'param', None) == 'response_format':
            SCHEMA_SUPPORTED[0] = False
        raise
    try:
        data = json.loads(response.choices[0].message.content or '')
    except json.JSONDecodeError:
        raise TranslationRejected('json') from None
    translated = data.get('translations') if isinstance(data, dict) else None
    validate(lang, items, translated)
    return {alias[a]: text for a, text in translated.items()}
