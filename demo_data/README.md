# Demo player profiles

Complete pre-match player dataset for Liverpool vs Arsenal (13 Jan 2016).

- General: FIFA16 absolute anchor + small, reliability-weighted StatsBomb season signal.
- Recent 5: actual StatsBomb event data from each team's five league fixtures before the demo.
- Physical: deterministic synthetic values from FIFA16 pace/physical + SkillCorner positional references. Not observed tracking data.
- Positions: FIFA16/curated eligibility only. PROFILE_FIT alone never creates a legal role.

Use `demo_player_profiles.json` in the engine. `demo_player_profiles.csv` is a compact inspection table.

Generated physical fields always carry `is_observed: false`.
