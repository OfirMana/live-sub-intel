# Match-load and freshness revision

The first card scorer subtracted up to three ability points for fatigue. Its
asymmetric tactical scoring gives positive gains credit only when the related
team need exceeds .5. Freshness therefore had little independent value with
flat tactical needs. Early linear fatigue also applied from the first minutes.

## Separate physical need

The five tactical needs keep their existing meanings. `physical_need.freshness`
is a separate 0..1 load estimate, not a sixth ability score. It is the highest
estimated fatigue among supported active outfield players. Individual outgoing
fatigue determines each candidate's freshness score. Unused bench players are
assumed available and fresh; injuries and prior-week recovery are not modeled.

## Deterministic estimate

1. Expected pressures and progressive carries use the existing player/role
   expectation. Positive excess action rates can increase inferred intensity:
   `1 + .15*clip(pressure_ratio-1,0,1) + .10*clip(carry_ratio-1,0,1)`.
   No action evidence means intensity 1, never zero off-ball work. Excess is
   ignored before 15 minutes; intensity is at most 1.25.
2. Stamina capacity = `clip(1+(FIFA_stamina-75)/150,.8,1.15)`.
3. Load ratio = `(minutes_played/90)*intensity/stamina_capacity`.
4. Fatigue = `clip((load_ratio-.5)/.7,0,1)^1.5`.

The .5 onset, .7 span, exponent, capacity scaling and action coefficients are
explicit provisional demo assumptions, not experimentally measured constants.
For stamina 75 and ordinary intensity, the fatigue signal is 0 through minute
45, .116 at 60, .329 at 75 and .604 at 90. At minute 75, stamina 55 yields .535
and stamina 90 yields .223. This is an index, not the percentage of a person's
real physical capability that is exhausted.

Synthetic profile metres/minute times minutes and intensity supplies a labelled
estimated distance for inspection. It is NOT independent evidence for fatigue
and does not separately amplify the load ratio. Pace, height and strength do
not automatically imply greater exhaustion. No real sprint/HSR/tracking stream
is available; halftime recovery and individual physiology are not modeled.

## Candidate score and avoidance of double counting

The tactical profile uses recent card ratings plus bounded live evidence and
no longer subtracts a separate fatigue penalty. All tactical gains and ability
losses still enter the original asymmetric score, divided by 20 card points.

Freshness score = `1.2 * outgoing_fatigue * quality_preservation`, where quality
preservation is the ratio of incoming to outgoing threat+progression+defense,
clipped 0..1. This does not excuse other ability losses: they still cost in the
tactical score. The 1.2 cap is provisional and is exposed in output/config.

Final benefit = `(tactical_core + tactical_support + freshness_score)`
`* evidence_multiplier * position_fit * remaining_minutes/90`.

Output exposes every term under `score_components`, plus physical_need and
reason codes. Position compatibility, available substitutions, the early-game
gate and the unchanged .15 recommendation threshold still apply. A comparable
fresh replacement can now qualify without a tactical deficit. A much weaker
bench player cannot erase a large ability loss just by being fresh.

## Sensitivity and limits

`scripts/audit_match_load.py` replays the same five research matches at refresh
caps 0, .6 and 1.2. Counts of qualifying snapshots (five per match):

| Match | Cap 0 | Cap .6 | Cap 1.2 |
|---|---:|---:|---:|
| Liverpool-Arsenal 3754305 | 0 | 0 | 0 |
| Liverpool-Manchester United 3754345 | 0 | 0 | 0 |
| Norwich-Liverpool 3754348 | 0 | 0 | 0 |
| Stoke-Arsenal 3754202 | 0 | 2 | 2 |
| Arsenal-Chelsea 3754111 | 1 | 1 | 3 |

These are repeated snapshots, not distinct substitutions or proof of quality.
Cap 0 disables the new explicit freshness reward; it is not the original model
with its old fatigue penalty. The prior model produced [0,0,0,2,1]. Do not infer
that fatigue fixes Liverpool's absence of recommendations: it does not in these
checks. Ability trade-offs, low sample strength, broad-role constraints and the
remaining-time multiplier can still keep candidates below threshold.

For example, near minute 65 in the target Liverpool benchmark, the best eligible
candidate has tactical core -.2129, support -.0021 and freshness +.3182. After
evidence multiplier .5759 and remaining-time factor .3333, benefit is .0198,
below .15. This explains a rejected candidate without forcing a historical swap.

47 tests pass, including delayed/monotone load, stamina/intensity sensitivity,
flat-tactical-need freshness benefit, refusal of large quality losses, no-sub
gates, role constraints and repeatable synthetic events. Next calibration must
examine football judgments across more player squads and scenarios, not merely
target a desired number of recommendations.
