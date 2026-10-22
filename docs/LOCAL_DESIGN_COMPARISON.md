# Local design and match-flow comparison

Branch: `design/local-options-match-audit`. Local experiments only; no deployment or engine/threshold changes.

## Open

- Lively scenario: http://127.0.0.1:8783/?design=studio&minute=30&team=24&inspect=1
- Original scenario: http://127.0.0.1:8784/?design=studio&minute=30&team=24&inspect=1

The top selector changes between Original, Clean studio, Night control room and Match broadcast without resetting the checkpoint or coach context. These are visual directions using the same components and calculations, not three different products. Clean studio is the recommended starting point for readability; Night is an alternative for presenting; Broadcast emphasizes the score.

Run with `PYTHONPATH=src;scripts` and dependencies installed:

```
python scripts/integrated_app.py --port 8783 --scenario lively
python scripts/integrated_app.py --port 8784 --scenario original
python scripts/audit_local_design.py
```

## Scenario experiment

Original remains the default. Its first goal is at minute 54, not after minute 60. Original yellow cards occur at 32 and 61. The lively experiment moves the first goal to 27 and has five yellows at 18, 32, 44, 61 and 73, assigned to distinct players; later goals remain at 78 and 82. This is an authored demonstration, not a forecast or simulated response to a recommended substitution. Moving a goal can also change the seeded downstream event sequence. Both variants use a fixed reproducible seed.

No red card was added: the current automatic XI planner is not a validated ten-player solver. Showing a red card without removing the player and adapting planning would be misleading. More cards are not automatically a more realistic match; this is a pacing option for review.

Instant playback is selected by default, with slower modes still available. All modes remain manually advanced in five-minute steps.

## Verification

- Existing Python suite: 206 passed. Two additional scenario tests passed separately.
- Node UI suite: 13 passed after correcting the preview initializer to remain importable without browser globals.
- `outputs/local_match_walkthrough.json`: 76 team/checkpoint evaluations (two scenarios × two teams × 19 checkpoints), validating score against past events, unique event IDs, valid eleven-player plans, incoming/outgoing identity and recommendation gates. Lively bookings are unique and reproducible.
- Browser: advanced all 18 five-minute segments of the lively variant. Result evolved 0–0, 0–1 at 30, 1–1 at 80, 2–1 at 85; all displayed current XIs had 11 players. Some screenshots of a new checkpoint captured the brief computing state; navigation waits for the previous computation to complete.
- Three themes were selected and screenshots saved. This is initial visual verification, not comprehensive mobile/accessibility testing.

## Known limits before choosing a version

Local Foundry credentials are absent, so model explanations use the labelled fallback; this experiment does not revalidate LLM prose or translations. Live Azure remains the authoritative place to test the configured model. Technical consistency is not proof that football recommendations are optimal. No new deployment was performed. The synthetic replay future remains fixed regardless of inspected plans.

Keep final audience/language work separate from this design experiment. Review which visual direction and scenario to retain before integration. The design comparison toolbar and its fixed localhost links must be removed or made explicitly preview-only before any production merge.
