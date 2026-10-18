# Validation record — 18 October 2026

52 automated tests pass. This establishes software behavior, not football decision quality.
Tests cover deterministic rebuilding, pre-cutoff filtering, all 72 players' goal/assist/
pass/dribble totals independently reconciled against 203 raw match files, bounded
ratings, pooled rates, monotone load, role eligibility, clock boundaries, match isolation,
and repeatable synthetic substitutions. A controlled flat-need case allows a three-point
ability loss for late freshness, refuses it early, and refuses a 25-point loss late.

## Five-minute research replay

12 team-match replays across 10 distinct fixtures; 18 checkpoints each (5,10,...,90),
216 total. Decisions use only events before the exact checkpoint boundary. No
recommendation before minute 20 is allowed. First-half minute 45 is checked once;
added time is consumed before second-half checks. The historical timeline and actual
substitutions continue: model recommendations are NOT executed in this replay.

| קבוצה | משחק | נקודות שעברו את הסף / 18 | מרב כרטיסים פעילים חסרים |
|---|---|---:|---:|
| Liverpool | Liverpool / Arsenal (2016-01-13) | 5 / 18 | 0 |
| Liverpool | Liverpool / Manchester United (2016-01-17) | 5 / 18 | 0 |
| Liverpool | Norwich City / Liverpool (2016-01-23) | 9 / 18 | 0 |
| Arsenal | Liverpool / Arsenal (2016-01-13) | 12 / 18 | 0 |
| Arsenal | Stoke City / Arsenal (2016-01-17) | 12 / 18 | 0 |
| Arsenal | Arsenal / Chelsea (2016-01-24) | 10 / 18 | 1 |
| Chelsea | Chelsea / West Bromwich Albion (2016-01-13) | 7 / 18 | 0 |
| Chelsea | Chelsea / Everton (2016-01-16) | 6 / 18 | 0 |
| Chelsea | Arsenal / Chelsea (2016-01-24) | 7 / 18 | 1 |
| Tottenham Hotspur | Tottenham Hotspur / Leicester City (2016-01-13) | 9 / 18 | 0 |
| Tottenham Hotspur | Tottenham Hotspur / Sunderland (2016-01-16) | 5 / 18 | 0 |
| Tottenham Hotspur | Crystal Palace / Tottenham Hotspur (2016-01-23) | 4 / 18 | 2 |

91 positive checkpoints are repeated decisions, not 91 swaps. The original three
Liverpool replays now have 5,5,9 positive checkpoints. Can -> Allen ranks first at
minute 80 against Arsenal (.2182); it actually happened at minute 81. Ibe -> Lallana
ranks first at minute 55 against Norwich (.1793); it happened at minute 58. These are
qualitative comparisons, not causal validation or a fitted target.

## Sensitivity

All variants below use the NEW outcome-aware cards and exact five-minute replay.
Thus the 1.2/90 row isolates the old refresh scoring, not the complete old model.

| Refresh cap / horizon | Liverpool v Arsenal | Liverpool v Man Utd | Liverpool v Norwich | Positive / 216 |
|---|---:|---:|---:|---:|
| 0 / 90 | 0 | 0 | 2 | 17 |
| 1.2 / 90 | 0 | 0 | 2 | 32 |
| 1.2 / 30 | 4 | 1 | 5 | 75 |
| **1.5 / 30 (current)** | **5** | **5** | **9** | **91** |
| 1.8 / 30 | 6 | 5 | 10 | 96 |

Raw results: [four_team_sensitivity.json](research/four_team_sensitivity.json).
Threshold stays .15. Parameters remain provisional design choices, not an empirical optimum.
Son sensitivity: omitting his synthetic card yields Tottenham counts [9,4,4], versus
[9,5,4] baseline; minus/plus five recent rating points yields [9,4,5] / [9,6,4].
The existence of Tottenham recommendations does not rely on that one synthetic prior;
individual timing and choices can still change. See research/son_assumption_sensitivity.json.

## What is still unresolved

- Repeated center-back refresh recommendations and early Arsenal recommendations need
  football review. The scorer has no disruption cost for changing a defensive partnership,
  and broad FB roles do not enforce left/right side. More recommendations alone is not success.
- Historical substitutions involving formation changes remain unsupported. Missing profiles
  for players outside the Jan 13 matchday squads are disclosed, never invented silently.
- All cards and baselines stay frozen before Jan 13, including later matches. This is a
  frozen-prior research comparison, not a rolling up-to-date season backtest.
- Outcome/process weights, FIFA mappings, fatigue and threshold have not been validated
  against independent expert labels or counterfactual outcomes. No measured live tracking,
  injury model, halftime recovery, or recovery between fixtures is available.
- No remote LLM or Azure deployment. This revision's local HTTP/SSE smoke check delivered
  91 minute updates, completion, and a valid three-substitution budget; refreshed standalone
  browser artifacts and the deterministic pipeline were also verified.
- Rich demo JSON still needs alignment with the original Recommendation schema and team UI/API.

Old match_load_audit.json records the Oct 16 five-checkpoint experiment; it is historical,
not the current 216-checkpoint result.
