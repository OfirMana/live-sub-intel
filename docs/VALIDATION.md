# Validation record

40 automated tests passed on Python 3.12. Tests cover source cutoff, exact offline card reconstruction, role artifacts, bounded modifiers, pooled rates, fatigue, window decay, opposition-based defense need, specialist scoring, no-sub decisions and repeatable synthetic streams.

Local HTTP/SSE smoke test: 91 minute updates, both decision types, and complete event. Browser preview rendered and changed team/checkpoint successfully; no browser console errors were reported.

## Research benchmarks

| Match | Date | Team evaluated | Sub / no-sub checkpoints | Missing active card coverage |
|---|---|---|---|---|
| Liverpool vs Arsenal (3754305) | 2016-01-13 | Liverpool | 0 / 5 | 0 |
| Liverpool vs Manchester United (3754345) | 2016-01-17 | Liverpool | 0 / 5 | 0 |
| Norwich City vs Liverpool (3754348) | 2016-01-23 | Liverpool | 0 / 5 | 0 |
| Stoke City vs Arsenal (3754202) | 2016-01-17 | Arsenal | 2 / 3 | 0 |
| Arsenal vs Chelsea (3754111) | 2016-01-24 | Arsenal | 1 / 4 | 1 |

Profiles and team baselines are frozen strictly before 2016-01-13. Later matches are held-out smoke checks, not evidence that the provisional threshold is calibrated. Only the definitive 36-player squad is scored; missing players are disclosed. Match 3754305 does not have to reproduce any historical substitution. No assertion checks for Benteke.

The final event demo is original synthetic data. It automatically applies only deterministic engine-approved swaps. The local preview includes a deterministic explanation; no remote LLM or cloud deployment has been configured. Physical tracking fields remain synthetic, and the FIFA16 snapshot update date is unverified.
