# Liverpool–Arsenal demo player data

This folder contains the frozen pre-match player layer for the hackathon demo:

- Target match: Liverpool 3–3 Arsenal
- Date: 2016-01-13
- StatsBomb match id: `3754305`
- 36 match-day squad players only

## Files

- `liverpool_arsenal_demo_profiles.json` — canonical nested player dataset.
- `liverpool_arsenal_demo_profiles.csv` — flattened table for quick inspection/UI work.
- `recent5_player_match_metrics.csv` — one row per player per team match in the five-match recent window.
- `fifa16_anchors.json` — compact FIFA 16 sanity/attribute source used by the demo layer.

## General ratings

The six demo ratings are:

- Threat
- Creation
- Progression
- Retention
- Defense
- Aerial

They are **absolute, FIFA-anchored scores on 0–100**, not position percentiles.

The base FIFA anchor uses FIFA 16 attributes:

- Threat: shooting, finishing, attacking position and heading.
- Creation: passing, vision, short passing and crossing.
- Progression: passing, dribbling, pace, ball control and long passing.
- Retention: ball control, dribbling, short passing, strength and reactions.
- Defense: defending, interceptions, standing/sliding tackle and strength.
- Aerial: heading, jumping, strength and height.

StatsBomb season-to-date information before 2016-01-13 applies only a **small capped adjustment**. This prevents position-relative statistical artifacts such as an elite centre-back receiving an implausibly low absolute defensive rating.

FIFA 16 is used as a historical sanity anchor, not as a claim that EA ratings are objective truth.

## Recent form

Recent form uses the team's five Premier League matches immediately before the target game.

The raw event metrics come from actual StatsBomb Open Data events. Players who did not play still have a row with zero minutes, so inactivity is visible rather than silently dropped.

Recent ratings are the General rating plus a small, reliability-weighted form adjustment. The adjustment is deliberately bounded; five matches cannot turn a good player into a bad player or vice versa.

## Positions

`fifa_positions` is the primary playable-position anchor. Historical StatsBomb position spells are retained as supporting evidence.

The engine should use `playable_roles` as the hard compatibility set in the demo. Profile-fit guesses alone must not make a major structural substitution legal.

## Physical data

FIFA fields such as height, weight, pace, acceleration, sprint speed, stamina, strength and jumping are historical source attributes.

Tracking-style fields such as:

- metres per minute
- HSR distance/count
- sprint distance/count
- high accelerations/decelerations
- estimated max speed

are **synthetic**. They are generated deterministically from FIFA physical attributes plus SkillCorner A-League positional reference distributions and are labelled:

`SYNTHETIC_FROM_FIFA16_AND_SKILLCORNER_ROLE_REFERENCE`

Do not present them as measured Liverpool/Arsenal tracking data.

## Known fallback

Brad Smith is not present in the FIFA 16 snapshot used here, so his FIFA-like anchor is a conservative role-based synthetic fallback and is explicitly marked `SYNTHETIC_FIFA_LIKE`.

## Design intent

This is demo-quality, football-realistic synthetic/enriched data for the hackathon. It is built to make substitution reasoning coherent and inspectable, not to be a definitive scouting model.
