# Research evidence

`match_load_audit.json` records the same five real research matches with refresh
score caps 0, .6 and 1.2, while the recommendation threshold remains .15.
It includes candidate score terms, load examples and per-checkpoint decisions.
It was regenerated from the current code for this handoff.

The counts are qualifying snapshots, not distinct substitutions. All three
Liverpool matches still have zero recommendations in all checked states.
This is unresolved model behavior, not proof that no changes were warranted.

Sources and limitations: [MATCH_LOAD.md](../MATCH_LOAD.md),
[VALIDATION.md](../VALIDATION.md), [dataset methodology](../../demo_data/README.md).
These real-match analyses are research only. The final event demo is synthetic.

Reproduce after installing the repository:

```bash
python scripts/audit_match_load.py --out docs/research/match_load_audit.json
```
