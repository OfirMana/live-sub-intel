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
