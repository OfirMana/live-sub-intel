# Live Azure acceptance — 24 October 2026

Run by `.github/workflows/live-acceptance.yml` ([run 40084236069](https://github.com/TomThomasPrintac/live-sub-intel/actions/runs/40084236069)) against the production App Service, build `0be9e03`, synthetic `lively` scenario, `gpt-4.1-mini` on Microsoft Foundry. Every request was a fresh call (`cached: false`).

## Run 1 — build 0be9e03

| Check | Result |
|---|---|
| Explanation requests | 22 of 22 answered (HTTP 200) |
| Fact selection by the model | 22 of 22 (`source: llm`); none fell back |
| Model translation | All 8 locales (ar, es, fr, de, it, pt, ja, zh-Hans) accepted by validation |
| Plan identity | No failures: every text names the inspected plan's players |
| Broadcaster digits | None |
| Latency | 2.1–4.7 s per explanation; 9.1–9.4 s for the first two (cold model) |

Covered:
- **Arsenal 65′:** the second alternative for all three audiences, plus Hebrew for broadcaster and coach. Also the selected plan, a rejected plan, and a formation change (4-3-3).
- **Liverpool 65′:** the selected repositioning plan and a rejected swap.
- **Arsenal 85′:** repositioning while trailing, so the late-win policy is active.
- **Arsenal 90′:** wait.
- **Arsenal 85′ with a draw objective:** wait; the late-win policy is off.
- **Liverpool 85′:** leading; wait.
- **The eight other locales:** one analyst request each.

### Defect found by human review (not by validation)

For a **recommended** plan, three translations reversed the decision sentence ("passes the recommendation rules"):

| Locale | Model output | Meaning |
|---|---|---|
| ar | ينتهك قواعد التوصية | violates the recommendation rules |
| de | widerspricht den Empfehlungsregeln | contradicts the recommendation rules |
| pt | ultrapassa as regras de recomendação | exceeds the recommendation rules |

The structural checks passed: placeholders, digits and IDs were intact, and no negation was required for an affirmative sentence. This is exactly the limit the handoff warned about.

The fix is in the PR that adds this report:
- **Wording:** the English is now unambiguous: "meets / does not meet the recommendation criteria".
- **Status check:** status sentences must use the language's "meets" verb, negated only when the English is.
- **Prompt:** the model gets a status glossary and runs at temperature 0.
- **Tests:** the three failing outputs above are regression tests.

Spanish, French, Italian, Japanese and Chinese stated the status correctly in run 1. Run 2 after the fix is recorded below.

## Run 2 — build 4d7469f, after the fix

[Run 40084951802](https://github.com/TomThomasPrintac/live-sub-intel/actions/runs/40084951802), with the same 22 requests, all fresh (`cached: false`). Report: `live_acceptance_20261024_run2.json`.

| Check | Result |
|---|---|
| Explanation requests | 22 of 22 answered; 22 by model fact selection |
| Model translation | All 8 locales accepted |
| Plan identity / broadcaster digits | No failures / none |
| Latency | 2.1–3.9 s (en/he); 4.6–5.4 s with a translation call |

The recommended decision sentence, read by a human reviewer in each locale:

| Locale | Decision sentence (status) |
|---|---|
| ar | … يستوفي معايير التوصية (meets) |
| es | … cumple con los criterios recomendados |
| fr | … respecte les critères de recommandation |
| de | … erfüllt die Empfehlungskriterien |
| it | … soddisfa i criteri di raccomandazione |
| pt | … cumpre os critérios recomendados |
| ja | … 推奨基準を満たしています |
| zh-Hans | … 符合推荐标准 |

Japanese and Chinese now have no spaces between sentences.

## Run 3 — build 4d7469f, plus a rejected plan in every locale

[Run 40085225588](https://github.com/TomThomasPrintac/live-sub-intel/actions/runs/40085225588): 30 requests. Report: `live_acceptance_20261024_run3.json`.

- 22 requests were served from the server cache because they repeat run 2 within 10 minutes. These test the cache, not the model.
- 8 requests were fresh: a **rejected** plan (Paulista for Mertesacker, quality gate failed) for an analyst in each locale.
- All 30 came from the model, and all 8 locales were translated, with no fallback, identity failure or digits in broadcaster text.

| Locale | Rejected decision sentence (negated status) |
|---|---|
| ar | … لا يستوفي معايير التوصية |
| es | … no cumple con los criterios de recomendación |
| fr | … elle ne respecte pas les critères de recommandation |
| de | … sie erfüllt nicht die Empfehlungskriterien |
| it | … non soddisfa i criteri di raccomandazione |
| pt | … não cumpre os critérios de recomendação |
| ja | 推奨基準を満たしていません。 |
| zh-Hans | … 不符合推荐标准 |

Fresh translation calls took 3.8–5.0 s, and one took 15.2 s (French). The 35-second wait limit was not reached.

## What this does and does not show

**Shown, on the deployed build:**
- Fact selection by the model, for all three audiences in English and Hebrew.
- Model translation that passes validation for all eight other locales, for recommended and rejected plans.
- The recommendation status correct in every checked locale.
- Plan identity kept throughout, and no numbers in broadcaster text.

**Not shown:**
- **Fluency:** in the other locales, only the decision sentences were reviewed closely. Minor wording issues remain, for example "xG de Arsenal" instead of "d'Arsenal", and "criterios recomendados".
- **Combinations:** coach and broadcaster were not checked in the eight model-translated locales.
- **Football judgement:** whether the recommendations are good football decisions.
- **Stability:** behaviour after the process restarts with an empty translation catalog. The first request per locale then pays one translation call.
