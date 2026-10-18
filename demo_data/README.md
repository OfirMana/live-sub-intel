# Reproducible demo player dataset

Canonical: `demo_player_profiles.json` (72 Liverpool/Arsenal/Chelsea/Tottenham matchday players).
`demo_player_profiles.csv` is the inspection table. The older frozen profile and
recent-metrics exports were superseded because their event definitions diverged
from `metrics.py`. Legacy recent-profile helpers remain for compatibility but are
not used by this builder (they select player appearances, not team fixtures).

## Rebuild

```
PYTHONPATH=src python scripts/build_demo_dataset.py
```

This is offline and deterministic. `fifa16_anchors.json` and
`source_evidence.json` contain all inputs. To recompute StatsBomb evidence:

```
PYTHONPATH=src python scripts/collect_demo_evidence.py
PYTHONPATH=src python scripts/build_demo_dataset.py
```

The collector processes all 203 Premier League matches strictly before
2016-01-13. Only target-squad player rows, league calibration distributions,
team baselines and raw SHA256 hashes are committed. Squad membership and starter
status come from matches 3754305, 3754062 and 3754065; no target-match performance or later positions
enter the player cards. Historical minutes include stoppage time in both halves.
The recent window is the five latest TEAM fixtures, including zero-minute rows.
Rates use pooled counts/minutes; retention uses pooled losses/actions.

## Sources and status

- StatsBomb Open Data: https://github.com/hudl/open-data/tree/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
  Counts, minutes and historical positions are OBSERVED annotations. Follow the
  provider's attribution/logo requirements when publishing analyses.
- FIFA16 attribute CSV, republished SoFIFA snapshot:
  https://github.com/kushal-gopal/EA-Sports-Fifa/blob/658e9f96cafcfdb636d6ca96fcc9bfdb1c064868/players_16.csv
  These are observed video-game ratings, not observed real-world capabilities.
  The exact SoFIFA update date is unverified: do not claim January 2016 precision.
  Leading numeric values are parsed from change annotations such as `82-1`.
  70 source records match by SoFIFA id. Brad Smith and Son are absent; Brad uses numeric medians of
  FIFA16 fullbacks rated 60..68 as a generic SYNTHETIC fallback. His left
  foot is a demo assumption. Son uses same-role medians for overall 75..85 and an assumed right foot. Both bands are explicit assumptions, not observed personal ratings. No individual numeric rating is hand tuned.
- SkillCorner reference CSV:
  https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/data/aggregates/aus1league_physicalaggregates_20242025.csv
  Arithmetic means by position_group were verified against `physical.py`.
  A-League 2024/25 references are generation anchors, not observed player data.

The earlier `player_cards.json` and workbooks were not present in local
attachments or this repository; they are not represented as verified sources.
The complete raw pre-match recalculation replaces the need for their derived
scores and league_baselines.csv.

## Formulas

All six dimension weight maps are stored in `demo_dataset.WEIGHTS` and the JSON
metadata. Height contributes only 15% of Aerial; heading, jumping and strength
supply the rest. Missing detailed attributes fall back to the appropriate FIFA
category; the committed source supplies detailed attributes for 70 players.

For each dimension, season signal is the player's observed rate minus the
pre-cutoff league role mean, divided by the role standard deviation (cohort
players >=450 minutes). It is statistical evidence, never an absolute ability.
The role-relative signal can move the absolute FIFA prior by at most
`6 * reliability * tanh(signal / 2)` points. Reliability is minutes/(minutes+900),
constrained further by actions/(actions+100) for retention and aerial
attempts/(attempts+20) for aerial. Low minutes therefore cannot create extremes.

Recent signal is (pooled recent rate - pooled season rate)/role standard
deviation. Its delta is `6 * recent_reliability * tanh(signal / 2)` with
minutes/(minutes+180), and the same opportunity constraints. General, prior,
season adjustment, recent delta and recent rating are separately exposed.
No appearance is missing performance, never zero ability; no minutes => no delta.
Recent evidence overlaps the season; this is a descriptive form modifier, not
an independent validation estimate. Evidence strength is not a probability.

Signals (profile-only; existing engine component meanings are unchanged):
threat = .7*npxG/90 + .3*non_penalty_goals/90 + .05*box_presence/90;
creation = .7*xA/90 + .3*assists/90 + .1*box_passes/90;
progression = progressive_passes/90 + progressive_carries/90 + .5*completed_dribbles/90;
retention = .8*(1-losses/actions) + .2*pass_completion, if passes are observed; otherwise 1-losses/actions; defense = pressures/90 + successful_def_actions/90;
aerial = annotated aerial_wins/annotated aerial_attempts. Lost aerial duels and
explicit aerial_won annotations are counted; unannotated contests are unknown.
The five core metrics are all extracted through the existing ComponentTracker.

## Positions and physical generation

Eligibility comes from FIFA positions or historical positions with BOTH >=180
minutes AND >=15% of historical minutes. Exact primary is the most-used
meaningful position within the first FIFA role, or the static FIFA fallback.
Tiny positional artifacts remain evidence but do not grant eligibility.
Suitability is 1 for the primary broad role and .85 for supported other roles.

Tracking estimates are deterministic and always SYNTHETIC, is_observed=false.
Max speed = clip(24+.12*sprint_speed,25,36). Role-reference workrate scales by
clip(1+(stamina-70)/150,.75,1.2). HSR scales by workrate and
clip(1+(sprint_speed-70)/70,.5,1.45). Sprint volume scales by pace_factor^1.5;
acceleration/deceleration counts scale by clip(1+(acceleration-70)/80,.5,1.4).
HSR is 20..25 km/h; sprint >25 km/h. These are calibration assumptions, not a
validated conversion from FIFA to physical measurements.
GK outfield dimensions and unsupported GK tracking references are null by design;
original FIFA goalkeeper attributes are preserved for future goalkeeper logic.

Season totals and p90 values are exposed under `season`. Goals require Shot outcome Goal; penalties are separate; own goals excluded. Assists use StatsBomb pass.goal_assist. Dribble completion uses outcome Complete. Pass completion means no failure outcome. Completion rates are raw, not pressure/difficulty adjusted; all passes include set pieces. No attempts means null rate. Outcome/process weights are provisional and share the existing capped adjustment, not an extra uncapped bonus. See docs/MODEL_UPDATE_HE.md.
