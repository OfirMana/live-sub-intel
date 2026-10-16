# Current validation record — 16 October 2026

47 automated tests pass after the separate match-load/freshness revision.
They cover source cutoff, exact offline card reconstruction, bounded modifiers,
pooled rates, position artifacts, load sensitivity, window decay, opposition-based
defense need, specialist scoring, no-sub gates and repeatable synthetic streams.
Passing tests establishes implementation behavior, not football decision quality.

## Current research benchmarks

Refresh-score cap 1.2; recommendation threshold .15 (unchanged). Five checked
states per match; counts describe snapshots, not distinct executed substitutions.

| Match | Date | Team evaluated | Qualifying / checked states | Missing active card coverage |
|---|---|---|---|---|
| Liverpool vs Arsenal (3754305) | 2016-01-13 | Liverpool | **0 / 5** | 0 |
| Liverpool vs Manchester United (3754345) | 2016-01-17 | Liverpool | **0 / 5** | 0 |
| Norwich City vs Liverpool (3754348) | 2016-01-23 | Liverpool | **0 / 5** | 0 |
| Stoke City vs Arsenal (3754202) | 2016-01-17 | Arsenal | 2 / 5 | 0 |
| Arsenal vs Chelsea (3754111) | 2016-01-24 | Arsenal | 3 / 5 | 1 |

**Liverpool receives no recommendation in all 15 checked states, even after
adding freshness. This remains a priority investigation, not a validated
conclusion that no substitutions were warranted.**

Profiles and team baselines remain frozen before 2016-01-13. Later matches are
held-out smoke checks; they do not calibrate the threshold. Only the definitive
36-player squad is scored, with missing active profiles disclosed. No assertion
requires a named historical substitution. See MATCH_LOAD.md for the score
breakdown, load formulas and sensitivity at refresh caps 0, .6 and 1.2.

## Local integration and player-card artifacts

The earlier local HTTP/SSE smoke check produced 91 minute updates and completion.
The synthetic scenario remains repeatable under current tests. The browser preview
and player-card browser were checked without console errors. The card browser's
search, team/role filters, view selection and player detail were exercised.
The workbook contains six sheets with filters and frozen identifying columns and
headers. General and Recent formulas were compared to all supported card ratings;
all sheets were visually reviewed, with no exported Excel error cells found.
The workbook and browser are copied unchanged into docs/player-cards for sharing.

The demo events are original synthetic data. Current explanations are deterministic;
no remote LLM, Azure deployment or GitHub Pages hosting is configured. Physical
tracking remains synthetic, and the FIFA16 snapshot update date is unverified.

## Previous iteration

Before the separate freshness contribution, the 40-test version produced qualifying
snapshot counts [0, 0, 0, 2, 1] for the same five matches. The new cap-0 sensitivity
is a different comparison: it disables the explicit refresh reward after removing
the old fatigue card penalty. Do not conflate these baselines.
