# Judge guide — a one-minute route through the live app

**Live Substitution Intelligence:** an AI-assisted decision workflow that compares the bench with the best tactical use of the current eleven. No login required.

## 1. A substitution, with a cost — Arsenal at 65

[Open Arsenal, 65, more attacking / seek a win](https://live-sub-intel-fcfudheze9b5ewfz.swedencentral-01.azurewebsites.net/?team=1&minute=65&stance=attack&objective=win&inspect=1).

The reviewed build recommends **Campbell → Oxlade-Chamberlain**, incremental benefit about **0.192** against **0.150**. This is a model score, not a goal prediction. Select Analyst and Explain: the output includes actual match-so-far facts from the synthetic stream. Choose the second alternative or a rejected one; both the pitch and explanation follow that exact plan. Rejection can be due to tactical quality even when a rounded score appears near the threshold.

## 2. Personalize the same facts

Choose Broadcaster, Analyst and Coach. Then choose Français or العربية in the separate explanation selector and press Explain. The page language stays unchanged. The source line distinguishes model fact selection, model translation and fallback. Names/numbers are server-inserted; the model does not decide the substitution.

## 3. A tactical action can be preferable — Arsenal at 85

[Open Arsenal, 85, more attacking / seek a win](https://live-sub-intel-fcfudheze9b5ewfz.swedencentral-01.azurewebsites.net/?team=1&minute=85&stance=attack&objective=win&inspect=1).

Arsenal is behind with one substitution remaining. The model prefers repositioning at about **0.217**; its best substitution adds only **0.115** beyond the best action without a swap. Switch the objective to a draw and inspect the changed policy. Waiting or repositioning is a valid result, not an empty demo.

## 4. A different team and game state — Liverpool at 85

[Open Liverpool, 85, balanced / seek a win](https://live-sub-intel-fcfudheze9b5ewfz.swedencentral-01.azurewebsites.net/?team=24&minute=85&stance=balanced&objective=win&inspect=1).

Liverpool leads. The reviewed model offers **Ibe → Lucas Leiva**, moving to **4-1-4-1**, with benefit about **0.168**. Compare More attacking: intent changes which trade-offs pass. This is a concrete contrast, not a claim that more substitutions are always better.

## What to evaluate

- [Methodology](../METHODOLOGY.md): time boundaries, unknown values, estimated possession/load and scoring.
- [Independent decision sanity review](DECISION_REVIEW_20261024.md): five outcomes, with professional limits.
- [Release evidence and remaining gates](RELEASE_REVIEW_20261024.md).
- [Architecture and submission description](SUBMISSION.md).

The fixed synthetic future does not change when you inspect a plan. Historical priors and third-party publication limitations are documented in [DATA_SOURCES.md](DATA_SOURCES.md). Numbers above were checked on deployed baseline `95456a7`; replay or model changes require rechecking the route.
