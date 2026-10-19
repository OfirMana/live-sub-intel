# Evidence-bound LLM explanations — 19 October 2026

Built from upstream main `7dbadbd`, after the four-team merge. The tactical
engine, scoring, replay UI and synthetic generator are unchanged. The team's
ongoing coach-control and demo work can integrate this module independently.

## What is implemented

```
synthetic events -> existing deterministic engine -> Recommendation JSON
  -> evidence catalog -> Azure OpenAI evidence plan -> local validation
  -> localized factual sentences -> coach / analyst / fan UI
                         failure -> deterministic fallback, explicitly labelled
```

`subintel.narrative` accepts the existing legacy Recommendation JSON and the
rich `recommend_demo` JSON. The model selects and orders fact IDs; it cannot
write arbitrary player names, statistics or new tactical claims. Code renders
those facts in English or Hebrew. This is a constrained LLM editing/planning
layer, not free-form commentary, an autonomous coaching agent or a second
football scoring model. Validating the plan does not validate the underlying
football assumptions.

The plan must preserve the decision and selected player IDs, include the
decision and threshold/availability evidence, disclose dominant freshness, and
retain at least one ability loss when supplied. Source, evidence and model
limitations are always appended. Legacy percentile differences remain
percentile differences; demo rating points are not labelled percentages or
forecast goals. Missing legacy thresholds are not filled with an assumption.

Azure uses the v1 Responses API with strict JSON Schema, `store=False`, one
request, no automatic SDK retries, an 8-second request timeout and an 800-token
output limit. One provider call can run at a time; overlapping requests receive
fallback. A bounded 128-entry memory cache includes the entire input, language,
audience and explicit intent, so different game states cannot share stale
answers. Provider/validation failures are redacted and not cached.

The three audience modes ask the model to prioritize different evidence:
analysts see score detail and needs; coaches see immediate relevance and
trade-offs; fans see shorter context. Required facts cannot be suppressed. The
offline fallback has a simpler selection policy; live audience quality still
needs evaluation.

## Run without Azure

```bash
pip install -e ".[dev,narrative]"
python scripts/serve_narrative.py --port 8772
```

Open http://127.0.0.1:8772/. Select a synthetic engine checkpoint, language and
audience, then press **Explain this decision**. The provider label states that
this is deterministic fallback. This independent integration preview does not
replace the match replay UI or the teammate's final demo.

Explain a saved legacy payload:

```bash
python scripts/explain_recommendation.py docs/examples/recommendation.json --language he
```

Explain one checkpoint from a saved rich list:

```bash
python scripts/explain_recommendation.py data/synthetic_demo/recommendations.json --minute 65 --team 24 --language en --audience coach
```

## Azure setup — not deployed yet

The team reported that it has no Azure account/resource yet. No subscription,
resource, model or paid deployment was created by this change. Remote quality,
latency, quota and regional availability remain unverified.

1. A team member establishes an Azure subscription and signs into Microsoft
   Foundry. Check any available hackathon credits and the actual subscription
   budget; no free quota or model availability is assumed here.
2. Create/select an Azure OpenAI resource and deploy a model that supports both
   the Responses API and structured outputs in the chosen region. Use the
   deployment's actual name, not a guessed public model ID.
3. Copy the resource endpoint, not a Foundry project URL. Configure the SERVER
   environment. `.env.example` is a reference only and is not automatically read.
4. Authenticate with an authorized Entra ID identity (`DefaultAzureCredential`)
   or provide `AZURE_OPENAI_API_KEY` through the local/server secret settings.
   Do not send keys in chat or commit them. No browser variables contain secrets.
5. Run a strict smoke test and inspect that `source` is `azure_openai`, not
   fallback. Do this before claiming the submission uses a live Foundry model.

PowerShell, after installing the optional dependencies and configuring auth:

```powershell
$env:AZURE_OPENAI_ENDPOINT = 'https://YOUR-RESOURCE.openai.azure.com'
$env:AZURE_OPENAI_DEPLOYMENT = 'YOUR-DEPLOYMENT-NAME'
python scripts/explain_recommendation.py docs/examples/recommendation.json --provider azure --require-azure --out data/narrative/live-smoke.json
python scripts/serve_narrative.py --provider azure --port 8772
```

The strict CLI exits 2 on fallback. Authentication must be configured in the
same server process environment. A configured SDK client is not proof of a
successful call: `/health` deliberately reports `live_provider_verified=false`.
The server is a local integration preview, bound to loopback. Public Azure
hosting requires the teammate's production HTTP app, access/rate controls and
normal deployment configuration; this patch does not publicly expose the API.

## Integration for Thomas / Tal

Python (reuse one service per server process):

```python
from subintel.narrative import NarrativeRequest, NarrativeService

service = NarrativeService.from_env('azure')

# In an existing request handler, after the engine produced rec:
explanation = service.explain(NarrativeRequest(
    recommendation=rec, language='en', audience='coach',
    coach_intent='unspecified',
))
# Keep rec unchanged; attach explanation as a separate response field.
```

Async servers should run the synchronous SDK call in a worker thread. Do not
await it in the event ingestion loop; request explanations on demand or at
selected checkpoints so the live stream continues during inference.

HTTP (the separate local server exposes this too):

```js
const response = await fetch('/api/explain', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({recommendation: rec, language: 'he', audience: 'coach'})
});
const explanation = await response.json();
// Render headline/reasons/tradeoffs/caveats using textContent, never innerHTML.
// Preserve the source label; do not present fallback as a live AI answer.
// Discard the response if match/team/minute or selected UI context changed.
```

`POST /api/explain` accepts at most 256 KiB. It returns `context_id`,
`match_id`, `team_id`, `minute`, unchanged `decision`, `headline`, `reasons`,
`tradeoffs`, `caveats`, `evidence`, `plan`, `source`, `fallback_reason`,
`language`, `audience`, `latency_ms` and `cached`. Malformed or inconsistent
engine payloads return 400; they are not silently re-scored. Cross-origin
browser requests are disabled on this local adapter. Credentials/endpoints are
never accepted from the browser.

Coach controls stay owned by the teammate. Optional `coach_intent` accepts
`unspecified`, `attack`, `balanced`, `defend`, but only discloses the supplied
intent; it DOES NOT alter scoring. When the new engine has explicit tactical
objectives, formation changes or additional decision gates, extend the adapter
with those structured facts and tests. Do not let prose in the LLM invent the
missing state or resolve a disagreement with the deterministic decision.

## Validation and remaining work

- Offline tests cover decision/player preservation, fabricated IDs, missing
  trade-offs/freshness disclosure, schema refusal, timeout, cache recovery,
  no-substitution cases, both contracts/languages/audiences and HTTP errors.
- An actual OpenAI SDK request/response is checked using a mock HTTP transport.
  This checks serialization, not Azure credentials or live model quality.
- `python scripts/evaluate_narrative.py` audits all saved research checkpoints
  in six language/audience combinations without remote calls. This is an
  integration audit, not a model quality or football accuracy score.
- Before submission: real Azure smoke test, representative explanation plans
  in all modes, latency/fallback-rate measurements, teammate UI integration and
  a synthetic end-to-end demo. Independent football calibration remains open.

Validation on 19 October: the existing 54 Python tests and 29 initial narrative
tests passed together (83). After extending nested-input checks, all 32 narrative
tests passed; the unchanged replay JavaScript suite passed all three tests.
The saved-checkpoint audit covered 216 checkpoints in six modes (1,296 cases),
preserved all decisions/inputs, and made zero remote calls. Its machine-readable
result is [narrative_offline_audit.json](research/narrative_offline_audit.json).

## Documentation and inspiration reviewed

- [Microsoft: Azure OpenAI Responses API](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses).
- [OpenAI: Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
- [Microsoft's structured Responses sample](https://github.com/Azure-Samples/azure-openai-responses-api-samples/blob/main/python/responses-structured-aoai-v1.py).
- [PitchLens](https://github.com/enniob/pitchlens): reviewed its README and
  `src/server/analyst.ts`; useful patterns are bounded evidence, audience
  selection, failure transparency and separating facts from interpretation.
  Its README describes Foundry and Azure hosting; those deployments were not
  independently tested. Our smaller planner does not reproduce its multi-step
  analyst/verifier workflow.
- [Inside the Game by bikilath](https://github.com/bikilath/inside-the-game):
  the README describes a synthetic generator and analysis layer with narrative
  and personalization still on its roadmap; do not cite it as a verified live
  Azure integration.

No participant code was copied. These are architectural references, not a
claim about competitors' current submission status or eligibility.
