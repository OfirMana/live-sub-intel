> Research archive. Generated ZIP/Excel/preview artifacts are no longer bundled. Use the live Azure app for the submission; existing HTML is a historical research snapshot, not the current product.

# Synthetic match demo

Download `synthetic-demo.zip` (local generated export; not bundled), extract it and open `index.html`
in a browser for offline checkpoint playback. The package also includes the
original synthetic `events.jsonl` and deterministic `recommendations.json`.
All three were regenerated after the separate freshness-score revision.

**All match events are synthetic.** Historical player cards are benchmark priors;
this is not a replay of a real match or licensed live Premier League data.

The **Stream events** button needs the local Python SSE server; offline HTML
supports **Play checkpoints**. From an installed repository checkout:

```bash
python scripts/serve_demo.py --port 8765
```

Open `http://127.0.0.1:8765` on that same computer. The server creates a fresh
engine per viewer and feeds events sequentially. No hosted backend or remote
LLM is deployed. Checkpoints and an explanation template are not proof of
football decision quality; see [the handoff](../TEAM_HANDOFF_HE.md).
