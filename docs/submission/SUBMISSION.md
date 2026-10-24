# Live Substitution Intelligence - Hackathon Submission Draft

24 October 2026 · Thomas, Tal and Ofir

English text for the Inside the Game project page, ready to paste once the team signs off. Submission closes 27 October 2026 at 23:59 Pacific (28 October, 08:59 Israel).

## Elevator pitch

Live Substitution Intelligence turns a stream of football match events into a bench decision that a coach, analyst or broadcaster can check. At any five-minute checkpoint it works out what the team needs now, searches substitutions, repositioning and formation changes across the whole XI, and explains the plan for a broadcaster, an analyst or a coach in ten languages. A deterministic engine makes the call; Microsoft Foundry picks which verified facts to tell and translates fixed sentence templates, so the explanation never invents a number or a name.

## Project description

**The problem.** A substitution is one of the few levers a coach can pull mid-match, and it is often decided on instinct and a look at tired legs. Fans and broadcasters see the change but rarely the reasoning behind it. Match statistics show what happened, not what the team needs next or what a change would cost.

**What the app does.**

1. Reads the match as a stream of events (passes, carries, pressures, recoveries, shots) and keeps running measures per player: attacking threat, chance creation, ball progression, ball retention, defending and estimated physical load.
2. Combines the score, the minute and the coach's intent (more attacking, balanced or more defensive; seek a win or avoid defeat) into the team's current needs.
3. Searches every available one-for-one substitution across six supported formations and position assignments, and compares each with the best plan that uses no substitution. Unsupported positions are blocked.
4. Recommends a change only when it beats that no-substitution plan by a set threshold. Fresh legs justify a change only when the tactical loss stays small, so a key player is not removed just because a fresher, weaker player is on the bench.
5. Explains the inspected plan for three audiences: a broadcaster gets two short qualitative sentences, an analyst gets the match statistics so far and the benefit against the threshold, and a coach gets the game state, urgency, estimated fatigue, role changes and the downside. Match statistics in explanations are computed on the server from the same events and rules as the page.
6. Offers the explanation in ten languages (English, Hebrew, Arabic, Spanish, French, German, Italian, Portuguese, Japanese, Simplified Chinese), separately from the page language.

**Why the explanation can be trusted.** The explanation layer cannot change the decision. Microsoft Foundry receives verified facts about the plan and returns only the IDs of the facts worth telling; the app validates them and writes the sentences itself. For languages other than English and Hebrew, Foundry translates only the fixed English sentence templates; names and numbers are inserted afterwards by the server, and a translation is used only if every placeholder, digit and negation survives. If the model is unavailable or its answer fails validation, the app shows a clearly labelled template or English explanation instead.

**Who it is for.** Coaching staff get a ranked shortlist with its trade-offs, analysts get the numbers behind it, and broadcasters get a line they can say on air, in their own language. Inspecting a plan never executes it, and the app says so on screen.

## Architecture

![The engine decides the plan; Foundry only picks which facts to tell](architecture.png)

The engine in App Service makes every decision. Foundry sees only verified facts and returns their IDs, and a labelled template takes over whenever the model is unavailable or its answer is rejected.

## Microsoft and Azure technologies

Three Microsoft services carry the running app: Foundry selects verified facts for the explanation, App Service hosts it, and GitHub Actions tests and deploys every change.

| Technology | What it does in the running app |
| --- | --- |
| Microsoft Foundry, Azure OpenAI deployment of gpt-4.1-mini | Selects which verified facts explain the inspected plan (JSON only, 250 tokens, 12 s, no retries), and translates the fixed sentence templates into eight more languages (strict JSON schema, 15 s, validated before use, cached per language). Explanations cached for 10 minutes, two calls at a time. |
| Azure App Service (Linux, Python 3.12) | Hosts the coach room and its API (`/api/bootstrap`, `/api/evaluate`, `/api/explain`, `/healthz`). The Foundry key lives only in App settings and never reaches the browser. |
| GitHub Actions with Azure OpenID Connect login | Every merge to `main` runs the full Python test suite, then deploys to App Service. A failing test blocks the deploy. |
| GitHub | Public repository; all changes arrive through reviewed pull requests. |

## Data and originality

Every match action in the demo is synthetic; only the player priors and line-ups draw on historical sources, and the app labels each one.

- **Match events:** original synthetic events from our own scripted-possession generator, in the same event format the engine reads live. They are not a real fixture, a prediction or licensed Premier League data.
- **Player profiles:** historical priors. Each card starts from FIFA 16 ratings and is adjusted, by at most 6 points, using [StatsBomb Open Data](https://github.com/statsbomb/open-data) evidence from before the match date. Starting line-ups and shirt numbers use historical metadata.
- **Estimates:** physical load and position suitability are heuristics, shown as estimates on screen.
- **Research mode:** a separate mode replays four team views across three Premier League 2015/16 fixtures from StatsBomb Open Data to benchmark the engine. It is not the submission demo.
- **Original work:** the code was written for this hackathon; the first commit is dated 15 October 2026. Open-source libraries: NumPy, pandas, pydantic and the OpenAI Python SDK.

## Testing instructions for judges

The app is live with no login at [live-sub-intel on Azure](https://live-sub-intel-fcfudheze9b5ewfz.swedencentral-01.azurewebsites.net/) and stays up through the end of judging (11 November 2026 in Israel; maintain a safety buffer). The first load can take up to 30 seconds while the server starts.

**Two-minute walkthrough**

1. Open [this checkpoint](https://live-sub-intel-fcfudheze9b5ewfz.swedencentral-01.azurewebsites.net/?team=1&minute=65&stance=attack&objective=win&freshness_cap=1&lang=en&inspect=1): Arsenal at minute 65, More attacking, Seek a win, plans open.
2. Read the bench decision: the recommended plan, its benefit against the 0.15 threshold, and the ranked alternatives that pass the rules.
3. Click the second alternative. The proposed pitch and the explanation both switch to that plan.
4. Keep Audience on Broadcaster and click **Explain this plan**. The line under the text reads "Model-assisted fact selection (gpt-4.1-mini)" when Foundry selected the facts, or "Verified template" with the reason when it did not.
5. Switch Audience to Analyst for match statistics and the benefit against the threshold, or Coach for the game state and the downside. Pick another explanation language, for example Français or العربية, next to the audience: the page itself stays in English, and the note says whether Foundry translated the templates or the text is shown in English.
6. Step forward or back five minutes, or change the approach and result objective; the analysis recalculates from the events up to that minute.

`/healthz` reports the deployed build, the data mode and whether Foundry is configured, without exposing settings or keys. How every number is computed: [Methodology](../METHODOLOGY.md).

**Run it locally** (Python 3.12):

```bash
git clone https://github.com/TomThomasPrintac/live-sub-intel.git
cd live-sub-intel
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,llm]"
python scripts/serve_app.py --port 8779
```

Then open `http://127.0.0.1:8779/?team=1&minute=65&stance=attack&objective=win&inspect=1`. Without Foundry settings the decisions are identical and explanations are labelled templates; set `FOUNDRY_ENDPOINT`, `FOUNDRY_API_KEY` and `FOUNDRY_DEPLOYMENT` to use the model. Tests: `python -m pytest -q`.

## Finalization status

This is a candidate description, not proof of submission.

- **Done and deployed:**
  - The Broadcast design and the evolving synthetic match (#21).
  - The three audiences with server-computed match statistics (#22).
  - The ten explanation languages with validated template translation (#23).
  - The build SHA and the live acceptance script and workflow (#24, #25).
  - The translation status-polarity fix (#26).
- **Verified offline:** 271 Python tests and 16 Node tests, plus the synthetic and historical explanation audits.
- **Verified live on Azure, 24 October** ([report](../research/LIVE_ACCEPTANCE_20261024.md)):
  - Model fact selection for all three audiences in English and Hebrew.
  - Model translation for all eight other languages, for recommended and rejected plans.
  - The recommendation status correct in every checked language.
  - The first run found a reversed status in Arabic, German and Portuguese. It was fixed and re-checked the same day.
- **Not verified:** native-speaker fluency, and coach and broadcaster wording in the eight model-translated languages.
- **Remaining release gates:**
  - Finish the data-license and attribution review (see DATA_SOURCES.md).
  - Record and upload the English video, under two minutes.
  - Add the public video URL and complete the submission.
