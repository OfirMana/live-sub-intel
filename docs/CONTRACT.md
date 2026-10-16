# Data contract and engine spec (v0)

Shared agreement between the three workstreams. Code is the source of truth:
`src/subintel/schema.py` (types), `metrics.py` (what each dimension means),
`profiles.py` (pre-match), `engine.py` (live). Change this file and the code in
the same PR.

Every constant marked **measured** was estimated from StatsBomb Premier League
2015/16 (all 380 matches). Everything else is a first guess to tune on the demo.

## 1. Pipeline and owners

```
events ──► MatchState ──► team needs ──► substitution ranking ──► Recommendation JSON ──► LLM ──► UI
  │            ▲                                   ▲
  │            └──── metrics.ComponentTracker ─────┤ (same code offline and live)
  └─ StatsBomb adapter / synthetic generator       └── ProfileBook (pre-match profiles)
```

| Area | Files | Owner |
|---|---|---|
| Data, profiles | `statsbomb.py`, `metrics.py`, `profiles.py`, `scripts/build_player_buckets.py` | Person 1 |
| Needs, substitutions | `engine.py` | Person 2 |
| Stream, API, LLM, UI | `generator/`, `api/`, `ui/` (to be created) | Person 3 |

Rule: nothing downstream reads StatsBomb JSON. The adapter converts it to `Event`,
and the synthetic generator emits `Event`, so both go through identical code.

## 2. Event schema

Pitch is 120 × 80 (StatsBomb yards). Every event is from the acting team's
perspective, attacking toward x = 120. Penalty box: x ≥ 102, 18 ≤ y ≤ 62.

| Field | Type | Notes |
|---|---|---|
| `event_id`, `match_id` | str | |
| `period`, `minute`, `second` | int | broadcast clock; second half starts at 45:00 |
| `team_id`, `player_id` | str | `player_id` empty for period markers and own goals |
| `type` | enum | `pass carry dribble shot pressure tackle interception recovery block clearance miscontrol dispossessed card substitution own_goal period_start period_end` |
| `x, y, end_x, end_y` | float | end only for pass, carry, shot |
| `success` | bool | pass completed, dribble/tackle/interception won, recovery not failed, shot scored |
| `possession_id` | int | |
| `under_pressure` | bool | |
| `recipient_id`, `set_piece` | pass only | set piece = corner, free kick, throw-in, goal kick, kick-off |
| `xg`, `penalty`, `on_target`, `goal`, `key_pass_id` | shot only | `key_pass_id` = `event_id` of the assisting pass |
| `card` | card only | `yellow`, `second_yellow`, `red` |
| `replacement_id` | substitution only | `player_id` leaves, `replacement_id` enters |

StatsBomb mapping is in `statsbomb.convert_event`. Ball receipts, aerial duels,
fouls without cards, goalkeeper events and 50/50s are dropped in v0.

Optional synthetic-only extension (not in v0 code): a `player_load` message every
60 s with `distance_m`, `hsr_m`, `sprints`. The engine works without it.

## 3. Dimensions

Five dimensions. Each one is the mean of its components after z-scoring the
components against the league (outfield players with ≥ 900 minutes).

| Dimension | Components (per 90 unless stated) | StatsBomb source |
|---|---|---|
| threat | `npxg` non-penalty xG; `box_presence` = passes received in the box + carries into it | `shot.statsbomb_xg`, `shot.type`, `pass.recipient`, `pass.end_location`, `carry.end_location` |
| creation | `xa` = xG of shots from the player's key passes; `box_passes` = completed open-play passes into the box | `shot.key_pass_id`, `pass.end_location`, `pass.type` |
| progression | `prog_passes`: completed open play, ≥ 10 yd forward from x ≥ 48, or into the box; `prog_carries`: ≥ 10 yd forward ending at x ≥ 60, or into the box | `location`, `pass.end_location`, `carry.end_location`, `pass.outcome` |
| retention | rate: 1 − losses / ball actions. Actions = open-play pass attempts, dribbles, miscontrols, dispossessions. Losses = failed passes and dribbles, miscontrols, dispossessions | `pass.outcome`, `dribble.outcome`, `Miscontrol`, `Dispossessed` |
| defense | `pressures`; `def_actions` = won tackles + won interceptions + recoveries + blocks | `Pressure`, `duel.type/outcome`, `interception.outcome`, `ball_recovery.recovery_failure`, `Block` |

Fatigue is not a dimension. It is a modifier on the player going off (section 6).

Sanity check, league top 5 by dimension (≥ 900 minutes): threat Agüero, Benteke,
Costa, Ighalo, Vardy; creation Özil, Sánchez, Tadić, Deulofeu, De Bruyne;
progression Cazorla, Fàbregas, Hazard, Silva, Ramsey; defense Kanté, Gueye,
Lucas, Dembélé, Behrami.

### Why absolute (league-wide) values, not position-relative

Team needs are absolute: a team that needs goals needs xG, whoever produces it.
Position-relative scores would rate a 90th-percentile centre-back's finishing
like a 90th-percentile striker's. Position is handled by restricting which swaps
are allowed (section 8). For like-for-like swaps both normalizations give the
same ranking, so the debate only matters for cross-role swaps, where absolute is
right.

## 4. Pre-match profile

Per-90 rate per component, shrunk toward a role prior:

```
rate = (player_total + k · prior_p90) / (player_90s + k)
```

- **Prior = the average fringe player of the role (< 900 minutes), not the average
  regular. Measured:** fringe attacking midfielders/wingers produce 0.10 xA/90 vs
  0.19 for those with 1,800+ minutes, and 0.95 vs 1.47 box passes/90. Shrinking a rarely used bench
  player toward the average regular made him look like a starter.
- **k (prior strength, in full matches), measured** by comparing match-to-match
  noise with real between-player differences within each role:

| component | AM_W | CB | CM | FB | ST | v0 value |
|---|---|---|---|---|---|---|
| npxg | 11.6 | 134 | 5.2 | 19.4 | 16.4 | 10 |
| box_presence | 3.4 | 44 | 2.4 | 6.5 | 5.7 | 4 |
| xa | 9.3 | ∞ | 4.2 | 118 | 25.7 | 8 |
| box_passes | 3.5 | 25.6 | 3.8 | 10.8 | 9.8 | 5 |
| prog_passes | 1.3 | 3.3 | 2.3 | 4.2 | 2.5 | 2.5 |
| prog_carries | 1.5 | 5.3 | 1.9 | 2.6 | 1.2 | 2 |
| pressures | 2.4 | 3.7 | 3.7 | 3.6 | 1.8 | 3 |
| def_actions | 7.3 | 7.0 | 3.7 | 10.2 | 4.2 | 5 |

Retention uses k = 100 ball actions.

No separate "recent form" term in v0. With these k values, five matches of
xG or xA are almost entirely noise, so a 0.6 × season + 0.4 × last-5 blend would
add variance and not information. If wanted later: exponentially weighted
season with a half-life of ~10 matches, still shrunk.

Profiles for a demo match are built only from matches before it
(`profiles.build(before_date=...)`), so nothing leaks from the future.

## 5. Live profile and confidence

The same shrinkage, with the pre-match profile as the prior:

```
live_rate = (k · prematch_p90 + live_count) / (k + minutes_played / 90)
confidence = n / (n + k)        n = minutes_played / 90
```

Weight given to today's evidence after 60 minutes:

| npxg | xa | box_passes | def_actions | box_presence | pressures | prog_passes | prog_carries |
|---|---|---|---|---|---|---|---|
| 6% | 8% | 12% | 12% | 14% | 18% | 21% | 25% |

Consequence for the product: a player's live profile barely moves in one match
(and should not). What changes during a match is the **team's needs, the score,
the clock and fatigue**. Present it that way; don't claim to detect that a
player "is having a bad game" from 20 minutes of events.

## 6. Fatigue

**Measured:** full-match starters make 15.1 pressures/90 in minutes 0–15 and
12.0 in minutes 75–90 (−20%). In minutes 60–90, fresh substitutes press more
than the starters still on in the same role: AM_W 17.3 vs 14.5, ST 14.4 vs 11.3,
FB 14.3 vs 12.1, CB 10.0 vs 7.8, CM 17.8 vs 17.1. Other components show no clear
decline. v0 applies

```
pressures_live × (1 − 0.20 × min(minutes_played, 90) / 90)
```

to players on the pitch; substitutes enter at full value. Call it "estimated
fatigue / match load", never fitness.

## 7. Team needs

For each team, components are summed over an exponentially weighted window
(half-life 12 minutes) and compared with the team's own pre-match norm:

```
z_c = (expected_c − observed_c) / sqrt(expected_c · dispersion_c)    (attacking components)
z_retention = (observed_losses − expected_losses) / sqrt(expected_losses)
z_defense   = mean over {npxg, box_presence, prog_passes, prog_carries} of
              (opponent_observed − what this team usually concedes) / sqrt(expected)
deficit_dim = mean of its components' z      (positive = worse than usual)
```

`dispersion` is 0.3 for xG-valued components and 1 for counts. Defensive need is
judged by what the opponent achieves against us, not by our defensive action
count: a team under siege makes many defensive actions.

Game state sets an importance weight per dimension, blended in as the match goes
on (τ = minute / 90; intensity τ × 0.75 at a one-goal margin, τ × 1.0 at two or
more):

| | threat | creation | progression | retention | defense |
|---|---|---|---|---|---|
| chasing | 1.5 | 1.3 | 1.2 | 0.8 | 0.8 |
| level | 1 | 1 | 1 | 1 | 1 |
| protecting | 0.7 | 0.8 | 0.8 | 1.3 | 1.4 |

A red card for us adds 0.2 to defense and 0.1 to retention; for them, 0.2 to
threat and 0.1 to creation. Then

```
need_dim = sigmoid(deficit_dim / 1.5 + 2 · ln(importance_dim))      0..1, 0.5 = normal
```

Game state enters only here. The substitution score has no extra game-state
multiplier (that would count it twice).

## 8. Substitution score

Candidates: every outfield player on the pitch × every unused squad player, if
subs remain (3 in 2015/16; 5 in today's Premier League). Bench roles come from
the player's profile, never from where he actually played after coming on.

Allowed swaps (cost in z units): same role 0; CM ↔ AM_W 0.2; AM_W ↔ ST 0.2.
When chasing from 70', CB/FB/CM → ST and CB/FB → AM_W are allowed at 0.6. GK
only for GK. Without this restriction, replaying Tottenham 0–1 Leicester
recommended taking off Robert Huth for Gökhan İnler: our five dimensions do not
measure what defenders are for (aerials, box defending, positioning), so any
defender loses on paper.

```
delta_dim = in_dim (pre-match, fresh) − out_dim (live, fatigued)
score = Σ_dim [ 2 · max(need_dim − 0.5, 0) · max(delta_dim, 0)
              + 0.5 · importance_dim · min(delta_dim, 0) ]  − role_cost
expected_benefit = score × (90 − minute + 4) / 90
recommend = best expected_benefit ≥ 0.15
```

Gains count only where the team has a problem; losses always cost. The first
version (Σ need × delta) turned into a generic overall rating when needs were
flat, and recommended taking Harry Kane off at 65' for a midfielder.

Each option carries `delta_pct` (percentile-point change per dimension, for
display), `strength` (`high`/`medium`/`low` from the lower profile reliability of
the two players; evidence strength, not a probability) and `reasons` (facts the
LLM may cite).

Result on Tottenham 0–1 Leicester (13 Jan 2016), profiles from earlier matches
only: Tottenham, dominant, get no recommendation through 80'. Leicester at 65'
show retention need 0.71 and progression 0.70 and get Okazaki → Dyer (low
strength), with Okazaki → Ulloa second. Ranieri took Vardy off for Ulloa at 70'
and Okazaki off for King at 76'.

## 9. Recommendation JSON (engine → LLM → UI)

`schema.Recommendation`. A real example is in
[`examples/recommendation.json`](examples/recommendation.json). The UI and the
narrative prompt are built against this file; the engine never returns anything
else.

## 10. What the LLM may do

| Deterministic Python | LLM |
|---|---|
| metrics, profiles, needs, scores, ranking, threshold, "no change" | explain the ranked options and their trade-offs |
| percentile changes, confidence, fatigue | adapt tone: fan, analyst, broadcaster |
| all numbers shown in the UI | translate (Hebrew, English, ...) |
| | answer follow-ups by calling the engine ("why not Ulloa?") |

The prompt passes the Recommendation JSON and forbids numbers that are not in
it. Validate the output: every number in the text must appear in the JSON.

## 11. Synthetic stream (proposal)

Possession resampling, not event-by-event simulation:

1. Convert all 2015/16 possessions to `Event` sequences and tag each with its
   outcome (reached final third, entered box, shot, xG, where it was lost).
2. Build a match timeline of alternating possessions with a target possession
   share and tempo.
3. For each possession, sample from the pool with weights set by a scenario
   script per time segment, e.g. 45'–70': home possessions reach the final third
   often but rarely enter the box.
4. Remap the original players to the demo squads by role slot; re-time; insert
   scripted goals, cards and substitutions.
5. Seeded, so the demo is reproducible.

Realistic sequences and coordinates for free, scenario fully controllable.

## 12. Known limitations (say them in the demo)

- Team needs are signals, not causes: low progression can be the opponent's press.
- Live player evidence is weak (section 5); profiles of rarely used players are
  low strength.
- No measure of aerial or box defending, so defenders are compared only with
  defenders.
- Minutes ignore first-half stoppage time (~1% error).
- Data: StatsBomb Open Data. Their terms ask anyone publishing analysis based on
  it to name StatsBomb as the source and use their logo.

### Recent profile, playable positions and physical enrichment

The long-term `PlayerProfile` remains the engine's **GeneralProfile**. A separate
**RecentProfile** is descriptive evidence from the player's five most recent
actual appearances strictly before the analysed match. Volume rates are computed
as `SUM(component) / SUM(minutes) * 90`; appearance-level per-90 values are never
averaged equally. Recent retention uses the existing
`1 - ball_losses / ball_actions` definition, and recent dimensions reuse the
same league `Scale` as the GeneralProfile.

Recent evidence exposes sample size and reliability. Reliability uses the same
prior strengths as the main profile (`n / (n + k)`, with `n = minutes / 90`;
retention uses ball actions) and means **evidence strength**, not probability of
correctness. GeneralProfile and RecentProfile stay separate in v0; there is no
hard-coded `60/40` or other blend yet. The current-match **LiveProfile** remains a
third, separate concept.

Playable positions are built only from lineup/position spells before the cutoff
date. The exact position with the most historical minutes is primary. A
secondary position is exposed when it has at least 90 historical minutes or at
least 15% of the player's known position minutes. Exact positions also map to
the existing broad `GK / CB / FB / CM / AM_W / ST` roles using
`statsbomb.ROLE_BY_POSITION`. The target match may identify the squad and team,
but its later position assignments are never used to infer pre-match versatility.

Player-specific physical/biographical enrichment is separate again. The
supported template includes height, preferred foot, top speed, metres/minute,
HSR, sprint and acceleration/deceleration fields plus source/provenance flags.
Unknown values remain missing. Position-group means from SkillCorner A-League
2024/25 are stored only as **synthetic-generation/reference distributions** and
must never silently populate a Liverpool/Arsenal player's observed physical
attributes.

Aerial ability remains a TODO. StatsBomb raw data contains useful clues such as
aerial-duel annotations and shot body part, but v0 drops aerial duels in the
adapter and does not define a reliable aerial-win-rate pairing. Height alone is
not aerial ability.


## Demo dataset revision (supersedes sections 4 and the earlier recent enrichment for demo cards)

The definitive demo dataset and formulas are documented in `demo_data/README.md`.
Use `demo_data/demo_player_profiles.json` and `demo_data.load_demo_profiles`.
General is FIFA16 anchored plus a capped season signal; Recent is General plus
an explicit capped form delta from the last five TEAM matches. Both reuse
`metrics.ComponentTracker` for observed event components. Outfield dimensions
are null for GK. Physical tracking is explicitly synthetic. Source inputs and
SHA256 evidence are committed; `scripts/build_demo_dataset.py` rebuilds offline.
The old appearance-based recent helpers remain legacy utilities only.
The final demo event stream must be synthetic and labelled as such.
