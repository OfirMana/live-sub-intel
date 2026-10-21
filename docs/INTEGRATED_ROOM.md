# Integrated coach room — 20 October 2026

> Current startup and submission-demo scope: see the root README and
> [21 October readiness](DEMO_READINESS_HE.md). The default server now uses
> synthetic actions; use `--data-mode historical` for the research examples
> below. This document records the earlier integration design, not deployment status.

Branch: `feature/integrated-coach-explanations`. This merges shared main
`1ae3c14` and automatic planner `4205a36`, then adds per-plan grounded
explanations and an English-default bilingual interface. Shared main is not
modified by preparing this branch; merging main triggers its Azure workflow.

## Run

```bash
pip install -e ".[dev,llm]"
python scripts/serve_app.py --port 8778
```

Open http://127.0.0.1:8778/. Existing `FOUNDRY_*` variables enable the model;
without them the same verified sentences work as labelled templates. No keys
are required to inspect tactics, compare alternatives or test both languages.
`serve_app.py` is also the existing Azure startup entry point, so integration
does not require a new deployment command. The older coach-room entry point
delegates to the same app. Legacy classes remain for existing offline callers.

- [English, Liverpool 65, attack/win](http://127.0.0.1:8778/?team=24&minute=65&stance=attack&objective=win&inspect=1).
- [Hebrew, same state](http://127.0.0.1:8778/?team=24&minute=65&stance=attack&objective=win&inspect=1&lang=he).
- [Tactical-only example, Liverpool 30](http://127.0.0.1:8778/?team=24&minute=30&inspect=1).

## What changed

The root now presents the automatic complete-XI search from
[AUTO_TACTICAL_PLANS.md](AUTO_TACTICAL_PLANS.md). The engine evaluates all
available outfield pairs over six supported shapes plus observed slots, with
role suitability, retained-player moves and a no-substitution reference.
Scoring constants and the freshness default are unchanged by this integration.
Both pitches show real shirt numbers; the proposed pitch follows the inspected
alternative rather than remaining tied to the first recommendation.

Selecting a candidate binds its `plan_id` to the explanation. A nonrecommended
alternative is explicitly described as rejected. A tactical-only action and
the no-change decision also have explanation paths. The heading names the
inspected plan; the primary recommendation remains visible separately.

English is the base locale. The language control changes all interface labels,
dynamic messages, positions and explanations to Hebrew with RTL. Player names
and machine-readable debug facts retain source values. New locale dictionaries
can be added in `web/coach-room/i18n.js`; missing keys fall back to English.
Links preserve language and coach context. Changing candidate, minute, team,
context, audience or language clears/aborts stale explanations. Browser request
identity also guards against responses arriving after an abort.

The live API uses `src/subintel/plan_narrative.py`. It offers verified fact IDs
to Foundry, accepts a strict selection schema, then renders trusted sentences.
This is intentionally model-assisted selection rather than unvalidated prose.
It closes the reviewed swapped-name, sign and probability loopholes. Whole-XI
effects and incremental score references are distinguished. Broadcasters get
qualitative, on-air wording without scores, percentages or numeric formations;
analysts may receive score components with the model-score caveat.

`scripts/integrated_app.py` validates context and plan against server-owned
snapshots. It coalesces concurrent same-key calls and caches results (600s for
model success, 30s for fallback), bounds the cache at 256 entries, limits model
attempts to 24/minute per process and two at a time, and applies a 15s global
cooldown after provider failure. No secrets or raw model prose are returned.
The SDK has a 12s timeout, zero automatic retries and 250 completion tokens.
Cache/budget are process-local, not a promise about total costs across replicas.

Health reports configuration and explicitly says connectivity is not verified.
The deployment workflow now runs Python tests before uploading the artifact.
It still needs a real post-deployment model smoke check from the owning team.

## Verification and limits

New tests cover second-choice identity, rejected alternatives, tactical/no-change
plans, broadcaster qualitative output in both languages, malicious or malformed
model responses, grounded selection, concurrent coalescing, cooldown/retry,
cache bounds/budget and the real HTTP bootstrap/evaluate/explain contract.
Node tests cover complete locale parity and stale-response identity, alongside
the existing replay checks. Manual browser review checks the two pitches,
candidate switching, English/Hebrew layout and explanation content.

The current machine has no Foundry configuration; local explanations therefore
truthfully show verified-template provenance. The teammate's deployed main
returned LLM unavailable during the earlier live review. This branch does not
claim to fix Azure credentials, quota, model deployment or network access.
Give [CLAUDE_FOUNDRY_HANDOFF.md](CLAUDE_FOUNDRY_HANDOFF.md) to the teammate's Claude.

Remaining football limitations are unchanged: suitability/exposure and load are
heuristic, supported shapes are a bounded catalog, one substitution at a time,
no goalkeeper swaps or ten-player search, and no causal prediction of outcomes.
Historical playback does not execute a proposed plan. Expert tactical review
and synthetic-demo integration are still needed before calling the product final.

Final checks: **153 Python tests and 8 Node tests passed**. The offline coverage
script checked **72 checkpoints, 2,070 offered plan contexts and 12,420 rendered
explanations**, with zero provider calls. Broadcaster text passed qualitative
output checks across all offered plans in both locales. These counts describe
contract coverage, not football accuracy or actual successful Foundry calls.
The report is `docs/research/integrated_explanation_audit.json`; reproduce with
`PYTHONPATH=src python scripts/audit_integrated_explanations.py`.
