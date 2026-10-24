# Independent release review — 24 October 2026

**Functional demo: recordable. Submission clearance: not complete.** The live Azure baseline was independently checked at `95456a7d6924a350c8a78821ad6800e65f6e3b07`. This polish branch changes presentation/CI/docs only; no engine weights, thresholds, player priors or scenario rules were changed in this pass.

## Evidence

- Main baseline: 271 Python tests passed, 1 optional historical-cache test skipped; 16 Node tests passed.
- After acceptance-gate changes: **277 Python tests passed, 1 optional historical-cache test skipped; 16 Node tests passed.** Node was explicitly on PATH, so the Python/Node statistics parity check ran. The optional complete historical raw-cache check is distinct from the synthetic/live demo tests.
- [30-case independent Azure acceptance](../research/live_acceptance_20261024_independent.json): 30 new model responses (`cached:false`), zero HTTP errors, identity failures, broadcaster digits or translation fallbacks. All eight translated locales covered. Successful response times 2.44–7.84 seconds.
- [Extra audience run](../research/live_extended_audiences_20261024.json): broadcaster and coach in all eight translated locales, using Arsenal 65 attack/win, second alternative. Fourteen succeeded; coach Spanish and Japanese had connection failures before an HTTP response. The run correctly remains failed in its original evidence file.
- [Two-case retry](../research/live_extended_audiences_20261024_retry.json): only those failed connections retried; both returned new model-selected/model-translated answers, correct identity and requested locale. No original evidence was overwritten. An earlier combined extended attempt also stopped on a connection timeout before reaching the extra cases; it is not counted as a pass.
- Combined completed coverage: **46 distinct scenario/audience/locale cases**, all successful responses model-assisted, including 16 additional audience/locale cases. This is several runs, not one flawless 46-request run. It does not establish network uptime or native-language fluency.
- Browser: second alternative → Analyst → French kept the page English, used French output and preserved the selected players. Switching interface to Hebrew retained explicitly selected French and cleared stale text. Page width did not overflow at 390 or 1280 CSS pixels; both pitches retained 11 displayed players. Desktop/mobile overrides were reset.
- [Five decision sanity checks](DECISION_REVIEW_20261024.md), including Liverpool's leading/defensive shape change and Arsenal's late tactical-only/wait choices. No professional football validation is claimed.

## Polish changes

1. Three decimal places in candidate scores so a rejected 0.146 does not round to the 0.150 threshold; rejection explanation gets its own readable line.
2. The live acceptance command now returns a nonzero exit status on missing expected plans, HTTP/identity/broadcaster failures, or a build change during the run. `--require-model` rejects fallback as a release-gate result while preserving fallback as legitimate product behavior. `--extended-audiences` adds the missing 16 live cases. Transport/JSON failures are recorded instead of silently losing the report.
3. Main deployment explicitly installs Node and runs all three Node suites as well as pytest. The manual live workflow requests strict, extended acceptance.
4. README is a current judge-facing entry point, with a one-minute guide, honest architecture, sources and scope. The old closeout no longer lists deployed audience/language work as pending.
5. SkillCorner's exact MIT notice is retained and linked from THIRD_PARTY_NOTICES.md. This closes that notice gap only, not FIFA/StatsBomb permission questions.
6. Submission copy no longer promises that translations can never invent/alter meaning. The server preserves names/numbers; status/placeholder validation has stated semantic limits.

## Position against judging criteria

The [official criteria](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md) give five equally weighted categories. The table is our positioning analysis, not a predicted score or organizer endorsement.

| Criterion | Evidence to foreground | Limit / next action |
| --- | --- | --- |
| Technological Implementation (20%) | Deterministic search, time-bounded event facts, server/browser parity, CI and live build checks. | Keep the proof linked and the observed skip explicit. |
| Agentic Design & Innovation (20%) | A constrained AI workflow: deterministic planning → required facts → optional fact selection → protected translation → validation/fallback. The actual translation-status defect and regression fix show why the architecture matters. | It is not autonomous multi-agent orchestration. Do not relabel stages as agents or add a fragile agent feature just for the deadline. |
| Real-World Impact & Applicability (20%) | Inspectable bench trade-offs and three audiences consuming the same intelligence, deployed with server-side secrets and fallback. | Synthetic demonstration, not proof of coaching performance or production data rights. |
| User Experience & Presentation (20%) | Broadcast layout, two pitches, cards/goals/assists, explicit rejection reasons, Instant stepping, separate language controls. | A concise English video remains the biggest presentation deliverable. |
| Adherence to Category (20%) | Foundry fact selection/translation with safeguards, synthetic events and explainable match intelligence. | Select a category honestly; Foundry is demonstrated, a multi-agent category claim is not supported. |

## Remaining release gates

- Data-rights/attribution gate in DATA_SOURCES.md. Historical FIFA/StatsBomb-derived profiles remain publicly present. No clearance was obtained, no raw history was erased, and a notice alone cannot grant permission. We cannot certify the entry fully compliant while this remains unresolved.
- Optional native-speaker and human-coach review: particularly translated coaching nuance, lateral-position utility and late waiting.
- Merge/review this polish PR if desired, deploy and run strict acceptance on its exact build. Existing baseline is functionally recordable now; do not mix claims about a PR with deployed behavior.
- Record/upload an under-two-minute English video, add its URL, verify team membership and complete the submission. No video or final submission was created by this review. Maintain the live service through judging.
