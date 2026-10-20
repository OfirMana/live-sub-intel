> **Archived v1 design and experiment.** The current room uses automatic tactical
> search, two objectives and a revised freshness guard. See
> [Automatic tactical plans](AUTO_TACTICAL_PLANS.md). Numbers and manual controls
> below describe the earlier implementation, not the current UI.

# Coach room — isolated research branch, 19 October 2026

Base: upstream main `abbd6ba`, including balanced freshness at cap 1.0 and a
maximum tactical loss of 0.1. This branch adds coach controls and explicit XI
plans without modifying the shared engine, teammate LLM code, old replay or
synthetic generator. The coach scorer is a separate, provisional decision model.

## Run

```bash
pip install -e ".[dev]"
python scripts/serve_coach_room.py --port 8774
```

Open http://127.0.0.1:8774/. The server loads pinned StatsBomb research fixtures
through the existing raw cache/downloader. First run needs network if the cache
is absent. It serves four team perspectives across the three matchweek-21 games.
No LLM, Azure account or API key is needed. Existing demo services are untouched.

Select stance, objective, target formation and freshness cap. Advance in
five-minute stages, then reveal substitutions when wanted. Select any candidate
to see its complete proposed XI, shirts, names, numbers, role changes, card
comparisons, tactical/freshness contributions and quality gate. Yellow marks the
incoming player and blue marks retained players changing broad roles. Planning
does not execute the change or change the historical result.

The direct-link control preserves match perspective, minute and coach settings.
Examples (local server must be running):

- [Liverpool at 65, attack and seek a win, 4-3-3](http://127.0.0.1:8774/?team=24&minute=65&stance=attack&objective=win&formation=4-3-3&inspect=1).
- [Same state, test 4-4-2](http://127.0.0.1:8774/?team=24&minute=65&stance=attack&objective=win&formation=4-4-2&inspect=1).
- [Chelsea at 85, attack and seek a win](http://127.0.0.1:8774/?team=33&minute=85&stance=attack&objective=win&inspect=1).

## Historical formation evidence

StatsBomb Starting XI events contain formation, positional lineup and jersey
numbers. Tactical Shift supplies updated lineup/formation when recorded. In the
pinned Liverpool–Arsenal events, Liverpool starts 4-3-3 and changes to 4-4-2 at
66:13. Chelsea and Tottenham start 4-2-3-1. Leicester changes from 4-4-2 to
4-2-3-1 at 76:08. See [source match events](https://github.com/hudl/open-data/blob/master/data/events/3754305.json)
and [StatsBomb specification](https://github.com/hudl/open-data/blob/master/doc/StatsBomb%20Open%20Data%20Specification%20v1.1.pdf).

Replay state only consumes events before the selected boundary. A substitution
inherits the outgoing position until a subsequent observed Tactical Shift
changes it. This avoids using a substitute's future lineup spell as if it were
known in advance. Actual shirt numbers come from the match lineup roster.
Pitch x/y values are schematic position anchors, not measured tracking data.
Live pitch/score/event rendering applies the same strict before-boundary rule,
including after seeking backwards and through first-half stoppage time.

## Explicit coach context

`CoachConfig` has four independent controls:

| Field | Values | Meaning |
| --- | --- | --- |
| stance | balanced, attack, defend | Present tactical preference |
| objective | win, draw, competitive, limit_damage | Desired result / risk posture |
| formation | observed, 4-3-3, 4-2-3-1, 4-4-2, 4-1-4-1, 3-5-2, 3-4-3 | Shape to test |
| freshness_cap | 0, 0.5, 1.0, 1.5 | Isolated sensitivity experiment |

`win` seeks another goal when level or behind. `draw` means a draw is sufficient,
not that an existing lead should be surrendered. `competitive` is a lower-risk
attempt to avoid defeat. `limit_damage` emphasizes retention/defense even while
behind; it does not instruct the team to concede. These are preferences, not
win/draw/loss probabilities or guarantees.

Dimension order below: threat, creation, progression, retention, defense.
Stance multipliers are balanced (1,1,1,1,1), attack (1.35,1.25,1.15,.95,.85),
defend (.8,.9,.95,1.2,1.35). With tau=minute/90 capped at 1:

- Chasing the coach's target: multiply by (1+.55tau,1+.4tau,1+.25tau,1,1).
- Limit damage: (.85,.9,1,1+.25tau,1+.4tau).
- Ahead, or level with draw/competitive target: (1,1,1,1+.12tau,1+.18tau).
- Behind with competitive target: (1+.2tau,1+.15tau,1+.1tau,1,1).

The model reuses the shared engine's raw performance deficit z values. For an
urgent dimension (combined weight > 1), a surplus cannot erase that urgency.
Need=sigmoid(signal/1.5 + 2*ln(weight)); signal=max(deficit_z,0) when urgent,
otherwise deficit_z. The actual weights and deficits are visible in the UI/JSON.
All coefficients are provisional; changing posture is not empirically validated.

## Complete formation feasibility and scoring

With `observed`, candidates preserve the current positional slot. Explicit
templates instead place all ten outfield players plus the unchanged goalkeeper.
A bitmask assignment maximizes supported position fit, then role-weighted
ability and minimum schematic movement. It is an exact fit assignment under
that heuristic, not optimization of football outcomes. Unsupported broad roles
are rejected. Sidedness, foot preference and off-ball movement are not modelled.

Each candidate uses one unused, available bench player. All retained players
receive explicit positions. An incumbent remaining in the same observed broad
role keeps the same baseline fit; choosing a template must not retroactively
penalize them for an unchanged role. A new player's suitability comes from their
profile. There are no goalkeeper substitutions or multi-substitution plans.

Role exposure heuristics in the dimension order above:

| Role | Threat | Creation | Progression | Retention | Defense |
| --- | ---: | ---: | ---: | ---: | ---: |
| CB | .60 | .65 | .85 | 1.00 | 1.35 |
| FB | .80 | .95 | 1.10 | 1.00 | 1.15 |
| CM | .90 | 1.05 | 1.15 | 1.15 | 1.00 |
| AM/W | 1.20 | 1.25 | 1.10 | .95 | .70 |
| ST | 1.35 | 1.00 | .80 | .80 | .55 |

Team contribution per dimension is the sum of effective card rating × exposure
× fit across outfield players. If the current XI can occupy the target formation
without a substitution, it becomes the reference. Otherwise the observed XI is
the reference, and a candidate represents the combined shape/substitution plan.
This prevents crediting a substitution for a formation-only gain.

The five total contribution deltas /20 feed the shared asymmetric
`substitution_score` with the coach's needs. A .02 disruption cost is charged
for each retained player changing broad role relative to that reference.
Tactical benefit=evidence_multiplier*(core-disruption)*(94-minute)/90.

Freshness=cap*outgoing_fatigue*min(incoming/outgoing quality ratio,1), where the
quality ratio uses threat+progression+defense. Benefit from freshness is scaled
by the evidence multiplier and min((94-minute)/30,1). Fit is already applied
inside team contribution, not multiplied over the final score a second time.
The tactical-support component carries the negative disruption cost; the old
cross/speed bonus is not additionally added in this separate coach model.

A candidate passes only when total benefit >= .15 and tactical benefit >= -.1,
matching main's bounded willingness to lose quality for fresh legs. The selected
candidate is the highest-scoring one passing BOTH conditions; it need not be
the first numerical alternative. The UI distinguishes score and quality gates.
The 94-minute horizon remains an assumption that needs separate calibration.

## Freshness experiment

`python scripts/audit_coach_controls.py` evaluates 216 past-only checkpoints in
12 team-match replays, three coach contexts and four caps: **2,592 cases**.
Cards stay frozen before 13 January. Within each coach context only the cap
changes. All rows are in the compressed cases file beside the JSON summary.

| Coach context | Cap 0 | Cap .5 | Cap 1 | Cap 1.5 |
| --- | ---: | ---: | ---: | ---: |
| Balanced / competitive | 13 | 27 | 55 | 78 |
| Attack / win | 64 | 82 | 102 | 112 |
| Defend / draw sufficient | 35 | 61 | 77 | 95 |

These are repeated checkpoints, not distinct substitutions or accuracy scores.
In balanced/competitive mode, cap 1 selects a negative tactical contribution at
8 points, versus 21 at cap 1.5; all stay inside the -.1 quality limit. The number
of CB exits also rises with cap. Attack/win produces many early suggestions:
54 of its 64 positive no-freshness checkpoints occur before minute 60. This is
an open calibration concern, not a demonstrated coaching success.

This coach model also changes needs, role exposure and observed role updates.
Its counts are NOT a freshness-only comparison against the old engine.
Use the UI sensitivity button for a strictly paired comparison at one state.
No cap is declared correct merely because it produces more/fewer suggestions.

## Teammate integration / LLM contract

```python
from subintel.coach_room import CoachConfig, recommend_coach

rec = recommend_coach(ms, team_id, observed, roster,
    CoachConfig(stance='attack', objective='win', formation='4-4-2'))
```

`observed` contains formation, initial_formation, current lineup, shifts and a
source label. Each lineup row contains player_id/name/number/position/role/x/y;
`roster` maps player ID to name/number/team_id. Synthetic callers supply their
own correctly labelled current lineup; CoachReplay is only the historical
adapter. Provenance follows the caller's observed source.

HTTP: `POST /api/evaluate` with match_id, team_id, minute and config. The separate
local server has no secrets or model provider. For an existing async backend,
call the deterministic scorer in a worker as appropriate; it must receive the
same past-only match state as the rest of the demo.

Output version is `coach-room-v1`. Important fields for the friend's LLM:
coach_config, state, importance, team_needs, observed, formation_only, selected,
no_substitution_reason and candidate score_components, lineup_changes,
expected_changes, proposed_lineup, repositioned, comparison_reference,
quality_gate_passed, clears_threshold and decision_basis.

Do not assume the first alternative is recommended. Do not treat crossing the
threshold as sufficient. Do not describe a formation-only plan as requiring a
substitution. expected_changes are pairwise card differences; lineup_changes
are role-adjusted XI contribution differences. Neither is a percentage chance
of scoring. explanation_context explicitly leaves decision ownership with the
deterministic engine; no LLM implementation is added here.

## Limits and validation

The earlier main/old replay remains available for comparison. This branch is
not a replacement for the teammate's synthetic presentation demo. Cards,
freshness, role-exposure multipliers, needs and thresholds remain provisional.
Plans for ten-player teams, unsupported templates, multiple simultaneous swaps,
manual drag/drop and actually applying a counterfactual change are not included.

Tests cover past-only tactics and shirt numbers, observed lineup replacement,
consistent unchanged-role fit, complete unique feasible XIs, substitution
availability, role changes, coach effects, isolated freshness scaling, HTTP
validation and asynchronous UI context keys. The complete Python suite passed
**80 tests**; both Node suites passed **6 tests**. The final coach/API subset
also passed all 13 tests after the starting-lineup guard. These checks establish
code/data consistency, not football recommendation quality.
