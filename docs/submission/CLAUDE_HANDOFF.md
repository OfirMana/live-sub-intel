# Claude handoff — integrate the final demo, then finish explanations

22 October 2026. Current main was f8adf5d at audit. The companion PR uses branch `OfirMana:design/local-options-match-audit` into `TomThomasPrintac/live-sub-intel:main`; exact URL: https://github.com/TomThomasPrintac/live-sub-intel/pull/21. It is a draft PR awaiting integration review.

FIRST: inspect current main and the companion PR. Integrate that PR or merge its branch into your integration branch; preserve any newer LLM work. Do not recreate its features. It contains the selected Broadcast theme, Instant default, evolving synthetic XI, two scripted changes per team with one left late, a visible substitution budget, rejection reasons and the no-substitution tactical alternative. The design comparison toolbar is opt-in (`?preview=1` or `?design=...`), not in the standard demo.

Use `DEMO_DATA_MODE=synthetic` and `DEMO_SCENARIO=lively` (CLI default lively). Update any Azure setting overriding the scenario deliberately; never claim local code is deployed. Main merges trigger the existing deployment workflow.

Remove the standalone 2015/16 provenance banner from the normal match screen; keep detailed provenance in DATA_SOURCES.md and the submission. Do not describe historical profiles as generated. Do not remove a mandatory provider logo/notice to conceal origin; complete the documented attribution/license gate separately.

Acceptance demo: Arsenal, minute 65, attack/win; show a second alternative and its exact explanation; then minute 85 where tactical repositioning can be preferred, and 90 where a below-threshold result is legitimate. Liverpool has fewer useful swaps in this roster; do not alter weights or inflate its ratings to force variety. Scenario decisions are independent of inspected recommendations.

The following detailed requirements remain mandatory. The earlier instruction to preserve all design applies to the selected Broadcast layout now. Use actual passing checks, not promised functionality, in the final submission text.

---

IMPLEMENTATION HANDOFF FOR CLAUDE — FINAL LLM AND PRESENTATION PASS
Project: Live Substitution Intelligence
Requested by Ofir, 22 October 2026

Read this entire prompt and inspect current origin/main before editing. Reference inspected locally: f8adf5d. Do not reset or overwrite newer teammate work. Work on a separate branch and open a PR with test evidence. Do not change the decision engine, thresholds, weights, formations search, player profiles or synthetic match script in this task. Preserve the current design. Do not build alternative designs now.

GOAL
Finish audience-specific explanations and multilingual output, reduce distracting copy, and default playback to Instant. Deploy through the existing reviewed workflow; do not report success from localhost alone. Preserve the real working Foundry connection and validated fact-selection architecture.

1. EXACTLY THREE AUDIENCES IN THE UI
Broadcaster, Analyst, Coach. Remove Fan from the selector: the user considers it redundant with Broadcaster. Broadcaster is the concise accessible explanation for both fans and commentators.
For legacy requests using audience=fan, map to broadcaster before cache lookup, or provide an explicit backwards-compatible migration. Return the normalized audience. Default new requests and UI to broadcaster. Update every audience validator, fallback, translations and request defaults, not only the HTML.

Broadcaster:
- One or two short, natural sentences, normally 25–45 English words, with a reasonable language-aware bound.
- Say who could replace whom, why now, and a material trade-off if needed.
- No raw model scores, component decimals or threshold jargon. A formation or match score is allowed if helpful; do not confuse that with model metrics.
- Clearly distinguish recommended / rejected alternative / wait. Never present an inspected rejected plan as advice.
- Mention a formation change qualitatively when relevant; do not list every repositioned player.

Analyst:
- Approximately 3–5 compact sentences; avoid duplicating the same fact in different words.
- Must include a meaningful current-match statistic when available, and the inspected plan's benefit against its threshold or the actual rejection reason. Choose one or two relevant match metrics instead of dumping all totals.
- Include tactical/freshness components only when useful. Scores are model units, not win probabilities or xG.
- Example structure: team has X shots on target / Y xG so far; the change addresses the identified need; benefit A against threshold B; explain the cost and any shape change.
- If no valid match statistics exist, say they are unavailable or omit that clause. Never generate plausible-looking values.

Coach:
- Approximately 2–4 practical sentences focused on current score, time, approach and objective.
- Explain urgency, estimated fatigue, tactical role/shape changes and a meaningful downside.
- If the outgoing player has a current yellow card, it may be mentioned as discipline context. A yellow card is not proof of imminent dismissal and must not be claimed to affect the engine unless it actually does.
- Fitness/fatigue is an estimate, not a medical diagnosis or sensor measurement.
- Exploiting an opposition weakness is allowed ONLY if a specific, implemented, time-bounded opponent statistic supports it. Otherwise omit it. Do not invent weak flanks, tired opponents or matchup advantages. Do not add a new decision model just to enable that sentence.
- Do not imply executing or accepting the plan changes the replay's future. This remains inspection of a fixed synthetic event stream.

2. SERVER-VERIFIED CURRENT MATCH FACTS
Current relevant files:
- src/subintel/plan_narrative.py: AUDIENCES, LANGUAGES, FACT_IDS, fact_bundle(), sentences(), default_ids(), max_facts(), explain_plan().
- scripts/integrated_app.py: request defaults, audience/language allowlists, explanation cache and API boundary.
- web/coach-room/index.html, i18n.js and associated JS: audience selector, match stats, language controls and playback.
- inspect latest bootstrap/stat_events producer and existing browser stats implementation before adding a second calculation path.

Today fact_bundle() contains context, needs and the selected plan, but no current-match totals. Simply changing the system prompt will NOT make real match statistics available.
Compute an authoritative server-side facts snapshot from the same canonical events used by the replay:
- Only events strictly before the displayed checkpoint, using the established timestamp convention. Never use final totals or later events.
- Team and opponent xG, shots, shots on target, passes attempted/completed and accuracy, estimated possession and its coverage; player current yellow/red/goal/assist context where valid.
- Reuse existing deduplication, shot outcome, assist-link validation, control-time expiry/dead-ball rules. Avoid Python/JS divergence; parity tests against shared fixtures are required if both implementations remain.
- No attempts => null/unknown accuracy, not 100% or 0% by invention. Missing xG/possession must remain unknown.
- Include provenance, cutoff, metric definitions and coverage in structured facts, even if not displayed in the main UI.
- Prevent red-card/10-player scenarios from being described as validated 11-player solutions if unsupported.
Add granular verified fact IDs for game state, relevant match metrics, discipline and coaching rationale. Make audience-required facts deterministic; the model cannot omit every statistic for an Analyst just because it prefers other facts.
Preserve mandatory decision identity, rejection reasons and material tactical losses even when applying brevity limits. Combine these compactly rather than silently dropping them.

3. MULTILINGUAL OUTPUT: CONTROLLED TEN-LANGUAGE LAUNCH
Keep the website's base language English; retain the existing Hebrew interface and RTL support. Explanation language must be a separate control from interface language. A French explanation must not accidentally switch every page label or reset the selected plan.
Initial supported explanation locales:
en English; he עברית; ar العربية; es Español; fr Français; de Deutsch; it Italiano; pt Português; ja 日本語; zh-Hans 简体中文.
Use a searchable, accessible selector if needed; show only these supported choices. Do not advertise “all languages the LLM can speak”: there is no reliably validated universal list in this app. Additional languages can be registered later.

Preserve the existing fact-ID selection stage. Do NOT replace it with unconstrained tactical prose.
Recommended implementation:
A. Produce audience-specific verified canonical facts/sentences in English (and retain existing trusted Hebrew rendering where appropriate).
B. For additional languages, use Foundry only to translate a bounded set of identified sentence templates. Return a strict JSON schema with the exact same IDs and controlled placeholders.
C. Protect player names, numeric values, plan identity, metric identity, recommendation/rejection status and negation semantics. Insert immutable values server-side after validating every placeholder occurs exactly as expected; reject extra, missing or duplicate IDs/placeholders. Never accept client-supplied source facts.
D. Structural/numeric validation does not prove semantic fidelity. Add reviewed translation fixtures, especially for rejection, negative deltas, estimated fatigue and no-data statements. Do not claim complete multilingual factual guarantees solely from JSON validation.
E. If generation/translation fails validation or times out, return a clearly labelled verified English fallback (or trusted Hebrew where available). Do not label fallback English as successful translation. Do not hide a Foundry failure behind a fake success.
F. Preserve existing rate/concurrency limits and total latency budget; avoid an unbounded second call. Cache valid translated templates where appropriate. Version the cache schema; include normalized audience, output locale, plan, complete coach context, checkpoint, fixture/data version and facts fingerprint. Changes in statistics or prompts must not reuse stale output.
G. Set lang and direction on the explanation element: Hebrew/Arabic RTL, others LTR. Use bidi isolation for names and numbers. Keep the page direction controlled by interface language.
H. Keep source/status accurate: e.g. model-assisted fact selection + translation versus verified template / English fallback. Keep technical detail in the connection disclosure.
I. Test each listed language against the actual deployed model. If a language is not validated, do not silently advertise it as ready. Do not change Azure credentials or log secrets.

4. LESS COPY IN THE MAIN UI, SAME DATA IN DOCUMENTATION
Use short labels: “Possession”, “Pass accuracy”, “xG”, “Shots on target”. Remove repetitive inline methodology prose, including “Possession — time estimate”, from the main statistical presentation.
Do not replace it with an invented “checked” / “verified” badge: these values are estimates from synthetic events, not official tracking measurements.
Move full methodology into a clean English document linked from About / Methodology, with Hebrew summary if practical. Include possession estimation/coverage, unknown intervals, fatigue assumptions, synthetic data and fixed-seed behavior, score units and threshold, fact selection/translation/fallback, and known limitations.
Keep essential truth visible in a compact form: synthetic scenario identity and whether the explanation is model-assisted or fallback. A short info icon/link can point to estimation details without repeating paragraphs.
Avoid deleting provenance from API/JSON or changing any calculations as a copy cleanup. Preserve accessible labels and keyboard access.

5. INSTANT PLAYBACK DEFAULT
In web/coach-room/index.html, #speed currently starts with Normal (4000), then Fast (1500), then Instant (0). Make Instant explicitly selected on a clean initial load; verify JS initialization/reset does not overwrite it.
Keep Normal/Fast available for slower playback. A user's explicit selection during the session should persist across team/checkpoint changes and Restart; document any persistent preference policy. Old settings must not prevent a clean first visit from defaulting to Instant.
No automatic full-match autoplay: advancing remains under user control.

6. REQUIRED TESTS AND ACCEPTANCE
Inspect current suites before changing tests. Existing baseline on reviewed main: 206 pytest tests and 13 Node tests passed. Do not weaken grounding assertions to make new outputs pass.
Add meaningful tests for:
- audience fan alias, three visible audiences, defaults and server/client allowlist consistency;
- short Broadcaster, numeric/statistical Analyst when data exist, context-aware Coach, truthful missing-data behavior;
- exact selected plan identity, second alternative, rejected alternative, wait and formation-changing plan;
- no future events, backward seeking, no stale explanation after context/locale/audience changes;
- parity of current-match totals, null denominators and incomplete possession coverage;
- every supported locale, RTL/LTR isolation, placeholder tampering, negative numbers, rejected-plan negation, unknown locale, invalid response and timeout fallback;
- clean-load Instant default and slower playback remaining usable;
- cache invalidation across new facts, locale, prompt/schema version and audience.
Run the relevant complete Python and Node suites. Update the explanation audit for the new audience/locale matrix. Separate deterministic/mock tests from real model acceptance results.
After PR checks and deployment, run live Azure acceptance with a bounded number of fresh requests:
Liverpool and Arsenal at 65; winning/drawing/losing examples at 85/90; alternate plan; formation-changing plan; rejected plan; all three audiences; en/he and at least one fresh response per additional locale. Record actual source, latency, locale, plan identity, cache status, failure/fallback and build SHA. Do not claim unchecked combinations passed.

7. DELIVERABLES
- Small PR on a separate branch; no unrelated redesign or engine retuning.
- Updated tests, accurate English methodology and submission description.
- Live acceptance results with failures honestly listed.
- Short Hebrew handoff: what changed, what was verified in Azure, what still needs review.
- Do not record the final submission video before this acceptance pass.

FUTURE DESIGN EXPLORATION — OUT OF THIS PR
The user likes the current design. Later create a separate static prototype/route or isolated worktree for 2–3 visual alternatives, using identical frozen sample data and no production changes. Do not replace, merge or deploy an alternative without a separate request.
