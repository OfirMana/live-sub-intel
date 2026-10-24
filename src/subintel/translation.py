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

TRANSLATION_PROMPT_VERSION = 'template-translation-v1'
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
        if ENGLISH_NEGATION.search(source) and not re.search(NEGATION[lang], text, re.IGNORECASE):
            raise TranslationRejected('negation', key)


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
              'Terms are short phrases inserted into the sentences; translate them so they read naturally there. '
              'Use a neutral, professional sports-analysis register.')
    try:
        response = client.chat.completions.create(model=deployment, max_completion_tokens=1500, response_format=response_format,
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
