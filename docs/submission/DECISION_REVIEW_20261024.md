# Five football decision sanity checks — 24 October 2026

Source: independent calls to the live Azure `/api/evaluate`, deployed baseline `95456a7`. These are reasonableness and consistency checks, not expert sign-off, match-outcome validation or causal evidence. Threshold 0.150 and model weights were not tuned for this review.

| Context | Returned action | Assessment |
| --- | --- | --- |
| Arsenal 65, leading, attack/win; 2 subs left | Campbell → Oxlade-Chamberlain, 4-2-3-1, benefit 0.19201 | A supported attacking swap with freshness benefit 0.20221 offsetting tactical loss 0.01019. The outgoing player is booked, but the decision engine is not claimed to predict a second yellow. Plausible refresh; exact utility uncalibrated. |
| Arsenal 85, behind, attack/win; 1 sub left | Reposition the current XI, 4-2-3-1, 0.21695 | Swap Ramsey/Flamini's midfield sides. Best substitution is Koscielny → Paulista at 0.11498 beyond this baseline, so it does not clear 0.150. The benefit assigned to a lateral position change is a heuristic sensitivity, not measured real-world impact. |
| Arsenal 90, behind, attack/win; 1 sub left | Wait, BELOW_THRESHOLD | Best swap adds about 0.06715; tactical-only adjustment is about 0.11337, both below threshold. Technically consistent; football staff might still gamble late. This is a documented model limitation, not proof that waiting is correct. |
| Liverpool 65, behind, attack/win; 2 subs left | Reposition the current XI, 4-3-3, 0.50528 | Benteke has already entered. Reassign Henderson/Can/Milner. The top swap Ibe → Lucas adds 0.06725 and fails quality. Consistent with comparison against no-sub action; exact positional-fit utility needs future calibration. |
| Liverpool 85, leading, balanced/win; 1 sub left | Ibe → Lucas Leiva, 4-1-4-1, 0.16817 | Trades attacking threat for defending/retention and estimated freshness. Directionally plausible for protecting a lead. Switching to attacking can change the result; not a prediction of match outcome. |

## Limits

- The current replay never executes inspected tactical adjustments. A repeated positional recommendation may therefore recur until the scripted lineup changes.
- Capability profiles and role fit constrain bench options. A stronger bench sensitivity experiment changes some Liverpool outcomes but not all Arsenal late outcomes; it is not permission to inflate historical ratings.
- No opponent-specific weak-side analysis, tracking measurement or ten-player planner is claimed.
- A human coach's judgement on these exact five choices remains valuable, especially the large benefit attributed to moving midfielders between supported positions and late waiting. Do not call this independent expert validation in the video.
