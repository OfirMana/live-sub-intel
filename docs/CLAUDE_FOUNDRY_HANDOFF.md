# Claude task: restore Foundry connectivity and preserve the integrated plan contract

Please diagnose and fix the team's actual Azure Foundry connection. Work from
`feature/integrated-coach-explanations` in `OfirMana/live-sub-intel`, incorporating
current `TomThomasPrintac/live-sub-intel/main` as needed. The integration branch
contains the coach planner and the teammate's server/Foundry work. Keep the
existing deterministic scoring; this task is connectivity and explanation QA.

## Observed failure, 20 October 2026

Production URL:
https://live-sub-intel-fcfudheze9b5ewfz.swedencentral-01.azurewebsites.net/

The reviewed production commit was `1ae3c146eb130f78e2c79cb0b0adcd3a246e945a`.
GitHub Actions run 39389731418 completed build and deployment successfully.
`/healthz` returned `status=ok, llm_configured=true`. However, two actual UI
requests (Tottenham, minute 65, fan/Hebrew and analyst/English) returned
`source=template`, `note=LLM unavailable`. A successful deployment or presence
of environment variables is not proof of a successful provider call.

## Diagnose before changing anything

1. Inspect Azure App Service runtime Log stream for the actual failing Foundry
   request. Determine its status/error type and request ID. Do not guess whether
   this is authentication, deployment mismatch, quota, endpoint, DNS or TLS.
2. Verify `FOUNDRY_ENDPOINT`, `FOUNDRY_DEPLOYMENT` and `FOUNDRY_API_KEY` are set
   on the running App Service. Never put the key in source, GitHub issues,
   screenshots, prompts, browser code or this document.
3. The existing deployment guide expects resource
   `https://live-sub-intel-resource.openai.azure.com/` and deployment
   `gpt-4.1-mini`; verify actual resources rather than assuming these are correct.
   The client normalizes its base to `/openai/v1/`.
4. From the actual runtime, make a minimal bounded provider request. Log safe
   diagnostics (exception type, status/code/request ID), not credentials or
   authorization headers. Check the deployed SDK and supported request fields.
5. After a successful provider response, exercise the real UI/API, including a
   second-ranked alternative, a rejected alternative and a tactical-only plan.

## New public app and explanation contract

Start `python scripts/serve_app.py --host 0.0.0.0`; it now delegates to
`scripts/integrated_app.py`. Local example: `--port 8778`. The public root is
the English-default automatic coach room, with Hebrew and RTL support. The
legacy `narrative.explain` free-text path and old App class are retained only
for backwards compatibility; the public integrated room uses `plan_narrative`.

POST `/api/evaluate` with match_id, team_id, minute, config. It returns stable
`plan_id` values for every inspected out/in pair, `selected_plan_id`, complete
`proposed_lineup`, fine-position moves, suitability, score components and
no-substitution reference. Config includes stance, objective, automatic
formation search and freshness cap. Keep the same context for explanation.

POST `/api/explain`:

```json
{
  "match_id": "3754305",
  "team_id": "24",
  "minute": 65,
  "config": {"stance": "attack", "objective": "win", "formation": "auto", "freshness_cap": 1.0},
  "plan_id": "swap:3535:3380",
  "audience": "broadcaster",
  "lang": "en"
}
```

The example is Firmino off / Benteke on, not necessarily the engine's first
choice. Always obtain IDs from the evaluated response; do not construct or
accept arbitrary client-authored facts. `tactical` identifies the best available
repositioning plan, and `wait` is valid when the engine recommends no change.

### Grounding is deliberate, not an error to remove

`src/subintel/plan_narrative.py` creates a bank of verified, localized facts
for the inspected plan. The model selects fact IDs in JSON:

```json
{"fact_ids": ["decision", "freshness"], "style": "direct"}
```

Only offered IDs are accepted. Decision must come first. Code renders the
sentences, preserving names, directions, signs and caveats. Unknown IDs, extra
fields, duplicates or free prose fall back to a verified template. The UI calls
this model-assisted fact selection, rather than claiming the model authored all
sentences. Broadcaster output is qualitative: no rating deltas, percentages,
thresholds or formation digits. Analysts can see model scores with labels.

Do not replace this with numeric-only free-text validation. That older check
accepted reversed players, reversed signs and fatigue misdescribed as scoring
probability. If richer natural phrasing is added, preserve equivalent semantic
guarantees and add regression cases before exposing it publicly.

## Reliability and acceptance

- Client timeout is 12 seconds, SDK automatic retries are disabled, and output
  is bounded to 250 completion tokens. Retain bounded behavior if model API
  compatibility requires adjusting fields.
- The integrated cache coalesces parallel calls for the same full context,
  uses success/failure TTLs, cooldown after provider failure, a per-process
  24-request/minute budget and two concurrent calls. The budget resets on
  restart/scaling; do not claim a lifetime fixed maximum of paid calls.
- `llm_configured` still describes configuration only. Health explicitly reports
  `connectivity_verified=false`; it does not silently perform a paid call.
- Prove an actual `/api/explain` response has `source=llm`, the requested
  `plan_id`, audience and language, and a non-empty correctly rendered text.
- Check all three audiences in English and Hebrew, plus no-change and tactical
  plans. Confirm selecting a different alternative changes the explanation.
- Test a provider failure: the UI remains usable and shows a correctly labelled
  verified template; logs preserve enough safe information to diagnose it.
- Run Python and Node tests. Update the PR with the actual cause, fix, test
  evidence and remaining limits. Deploy the integrated branch via the team's
  normal merge/deploy process, then repeat the real model smoke check.

```bash
pip install -e ".[dev,llm]"
python -m pytest -q
node --test tests/test_coach_room_ui.cjs tests/test_match_replay_ui.cjs tests/test_integrated_ui.cjs
```

No secret is needed in the handoff reply: provide the diagnostic category,
deployed revision, successful source/model/plan IDs and observed timings.
