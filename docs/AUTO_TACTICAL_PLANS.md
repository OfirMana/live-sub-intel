# Automatic tactical plans — coach room v2

Branch: `feature/coach-match-room`, based on main `abbd6ba`. This separate
research scorer does not change the shared engine or teammate LLM implementation.

## Run and inspect

```bash
pip install -e ".[dev]"
python scripts/serve_coach_room.py --port 8775
```

Open http://127.0.0.1:8775/. The existing pinned StatsBomb cache is used; an
uncached first run needs network. Four team perspectives cover the three
matchweek-21 fixtures. Advance five minutes, reveal the decision, and select
alternatives to see the complete proposed XI and its score components.

- [Liverpool 65, attack/win: winger off, striker on, retained players move](http://127.0.0.1:8775/?team=24&minute=65&stance=attack&objective=win&inspect=1).
- [Liverpool 30, balanced/win: examine a tactical adjustment without substitution](http://127.0.0.1:8775/?team=24&minute=30&stance=balanced&objective=win&inspect=1).
- [Tottenham 65, balanced/win](http://127.0.0.1:8775/?team=38&minute=65&stance=balanced&objective=win&inspect=1).

Red marks the outgoing player, yellow the incoming player and blue retained
players changing fine positions. Both boards contain 11 players. Actual shirt
numbers and observed formations come from Starting XI/lineup/Tactical Shift
records consumed only before the checkpoint. Coordinates are schematic, not
tracking. Planning does not execute a substitution or alter subsequent events.
The wide attacking midfield anchors in 4-2-3-1 were widened for readability.

## Coach context and scope

Normal controls are stance (`balanced`, `attack`, `defend`) and objective:
`win` seeks a goal when level or behind; `draw` means a draw is sufficient and
does not ask to surrender a lead. The ambiguous competitive/limit-damage
objectives were removed from this UI/API configuration. Automatic formation
search replaces the manual formation selector. Freshness defaults to 1.0; the
collapsed sensitivity laboratory permits controlled comparisons with 0/.5/1/1.5.

The existing need calculation is retained: sigmoid(deficit signal/1.5 +
2*ln(context weight)). Urgent dimensions cannot have their urgency erased by
a performance surplus. Stance, score, clock and target determine the weights;
the UI exposes weights and raw deficits. See the historical
[v1 formula reference](COACH_ROOM.md) for these unchanged need/exposure formulas.
Its manual formation assignment and experiment results are superseded here.

## Search and position suitability

For every available on-pitch outfield player and every unused outfield bench
player, replace that player in the final XI and optimize all retained players'
positions. No temporary position of the outgoing player is needed. Goalkeeper
substitutions, simultaneous multi-substitution plans and ten-player shapes are
outside the current scope.

Each pair is checked against the exact observed positional slots plus six
templates: 4-3-3, 4-2-3-1, 4-4-2, 4-1-4-1, 3-5-2 and 3-4-3. The observed layout
is deduplicated when exactly identical to a template. Assignment uses exact
branch-and-bound with unique players, most constrained slots first, and a
monotonic upper bound. It has no beam/time cutoff. It optimizes our numerical
utility within this catalog, not every imaginable football shape or real match
outcome. At Liverpool 65 this is 60 pairs and 427 formation trials including
seven no-substitution trials; infeasible trials are recorded too.

Position fit is a transparent ability multiplier, **not measured chemistry or
a success probability**. Every player still has the same five ability dimensions.

| Evidence for a requested fine position | Maximum fit |
| --- | ---: |
| Primary fine position | 1.00 |
| Listed secondary position | .85 |
| At least 180 observed minutes there | .85 |
| Current observed fine position, supported broad role | .85 |
| Supported broad role only | .75 |
| Unsupported broad role | 0 — blocked |

Each permitted value is capped by the existing broad-role suitability. An
unsupported exact incumbent position may be described at .70, but that does
not authorize introducing that role elsewhere. Goalkeepers are restricted to GK.
The same function evaluates the observed XI and proposed XI: no free incumbent
fit advantage. Kane at CB is blocked. Tiny incidental position minutes do not
make Lamela a supported striker. We do not invent absent matchday substitutes.

`demo_data/position_suitability.json` exports all 72 cards × 25 fine positions,
including source categories, blocked roles and a source-card hash. The API
bootstrap includes the same derived matrix without editing the canonical cards.
Foot preference, detailed left/right proficiency, partnerships and off-ball
movement remain unmeasured; the fallback fit values are deliberately explicit.

## Utility and decision policy

Let C[d] = sum(effective ability[d] × role exposure[d] × position fit) over
the outfield XI. Effective ratings reuse the existing card/live-performance
adjustment. For a proposed XI, delta[d] is C[d] minus the observed XI's C[d].
Let gain[d]=2*max(need[d]-.5,0), loss[d]=.5*importance[d].

```
core = sum(delta[d]/20 * (gain[d] if delta[d]>=0 else loss[d]))
disruption = .02 * retained players changing fine position
             + .03 if the formation label changes
evidence = .5 + .5 * min(incoming reliability, outgoing reliability)
tactical = (core - disruption) * evidence * max(94-minute,0)/90
quality_ratio = min(1, sum(incoming threat/progression/defense)
                       / max(sum(outgoing threat/progression/defense),1))
freshness = cap * estimated outgoing fatigue * quality_ratio
            * incoming position fit * evidence * min(max(94-minute,0)/30,1)
```

Reliability is the mean of the card's six general reliability values. For
no-substitution plans evidence=1 and freshness=0. Estimated fatigue is the
existing load model, not measured tracking. The 94-minute horizon, exposure,
movement costs and fit coefficients remain hypotheses requiring calibration.

First optimize every supported shape **without** a substitution. Waiting in
the actual XI remains available with value zero. B is the larger of zero and
the best no-substitution tactical utility. For each substitution:

```
incremental_tactical = tactical - B
incremental_total = tactical + freshness - B
allowed_loss = min(.10, .35 * freshness)
recommend only if incremental_total >= .15
               and incremental_tactical >= -allowed_loss
```

This prevents crediting a substitution for a benefit obtainable just by moving
the existing players. The assignment solver enforces the quality constraint
while searching; an unsafe numerical optimum cannot hide a safe assignment.
If none is safe, the best rejected plan is retained for inspection. For each
pair, retain the best recommended plan if one exists, otherwise its numerical
best. Other tested formations' scores/status remain in `formation_variants`.
The UI lists one complete plan per pair rather than duplicate cards per shape.

Choose the highest eligible substitution. Otherwise, if B >= .15, recommend
a tactical adjustment without a substitution. Otherwise wait. Ties in assignment
prefer fewer position changes. No-substitution adjustment is a first-class
output, not a fabricated player swap.

The 1.0 freshness default is an engineering choice, **not a calibrated optimum**.
It allows some quality loss for freshness while the absolute and proportional
guards restrict it. The paired sensitivity results below motivated retaining
1.0 rather than making the stronger 1.5 cap the default.

## Evidence so far

Run `PYTHONPATH=src python scripts/audit_auto_plans.py`. Cards remain frozen
before the target fixtures. The audit uses 12 team-match replays × 18 five-minute
checkpoints: **216 default cases**. A paired 16-context subset adds the other
three caps, giving 264 evaluations overall. These are repeated decisions along
historical games, not 216 independent games or an accuracy estimate.

Default balanced/win/cap1: **79 substitutions, 27 tactical-only adjustments,
110 waits**. Of the substitutions, 60 include retained-player repositioning,
six change the formation label, 40 are freshness-led, and 11 accept a small
negative incremental tactical value within both guards.

| Freshness cap, same 16 contexts | Substitutions | Tactical-only | Wait | Negative incremental tactics |
| --- | ---: | ---: | ---: | ---: |
| 0 | 2 | 9 | 5 | 0 |
| .5 | 6 | 6 | 4 | 0 |
| 1 | 11 | 3 | 2 | 2 |
| 1.5 | 16 | 0 | 0 | 7 |

Default local CPU scoring: median 172.7 ms, p95 277.69 ms, max 415.8 ms.
Individual UI requests may take longer; these are not service latency promises.
All generated substitution XIs were checked for 11 unique players, outgoing
absence/incoming presence, score threshold and quality guard. Unit tests compare
the exact solver against exhaustive small assignments and exercise role blocks,
chain repositioning, state immutability, availability and no-sub comparisons.
HTTP/bootstrap and browser checks cover the full rendering path.

Machine-readable [summary](research/auto_plans_audit.json) and
[compressed cases](research/auto_plans_cases.json.gz) are committed. The earlier
2,592-case report belongs to v1 and must not be attributed to this new search.

What is **not** established: expert-labelled tactical correctness, calibrated
fit/fatigue/threshold coefficients, causal outcome improvement, or the best
freshness cap. Next review should label the complete proposed XI, retained-player
moves, reasons for waiting and quality tradeoffs across clubs; use held-out
matches before tuning the constants. More recommendations alone are not success.

## Integration contract

`src/subintel/auto_plans.py`: `AutoConfig`, `position_fit`, `recommend_auto`.
`scripts/serve_coach_room.py` exposes POST `/api/evaluate` and GET `/api/bootstrap`.
`AutoConfig.formation` retains observed/explicit templates for research callers;
the normal UI always submits `auto`.

Version is `coach-room-v2`. `recommendation` is `SUBSTITUTION`,
`TACTICAL_ADJUSTMENT` or `NO_SUBSTITUTION`. `selected` remains the chosen player
swap or null. **Use `selected_plan`** to render/explain either a player swap or
tactical-only action. A tactical-only plan has null `out_player`/`in_player`.
Each plan includes complete `proposed_lineup`, fit/source, `repositioned` fine
positions, components and change type. Substitution components are incremental
against `reference_benefit`; `lineup_changes` remain versus the observed XI.

LLM code should consume this deterministic fact bundle, including the reference,
quality gate and heuristic provenance. It may explain uncertainty and tradeoffs;
it must not invent eligibility, replace the optimizer or alter the decision.
No Azure account, key or new LLM service is required to inspect this room.
