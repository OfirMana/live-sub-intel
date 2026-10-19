# Match load, freshness and score horizons — 18 October 2026

The earlier scorer used freshness cap 1.2 and discounted the whole candidate by
remaining_minutes/90. At ordinary intensity and stamina 75, even perfect equal-quality
refresh peaked near .083 before evidence penalties, below the .15 decision threshold.
That explained a structural suppression of ordinary refresh substitutions.

## Load proxy (unchanged)

For played minutes >=15, excess(count,rate) = clip(count/max(rate*minutes/90,1)-1,0,1);
before 15 it is zero. Intensity = 1 + .15 excess(pressures) + .10 excess(progressive carries),
bounded 1..1.25. Low observed on-ball activity never implies zero off-ball work.
Capacity = clip(1+(FIFA stamina-75)/150,.8,1.15).
Load ratio = minutes/90 * intensity/capacity.
Fatigue = clip((load_ratio-.5)/.7,0,1)^1.5.

For stamina 75/ordinary intensity, fatigue is 0 through 45, .116 at 60, .329 at 75,
.604 at 90. This is a model index, not measured exhaustion. Synthetic metres/minute
times played time/intensity is displayed as an estimated distance and supplies no extra
evidence to the score. No measured tracking, physiology or recovery is inferred.

## Candidate calculation

Core dimensions are Threat, Creation, Progression, Retention, Defense. Recent ratings
plus 4 times bounded live dimension evidence form outgoing ability. Incoming ability is
Recent. There is no extra fatigue subtraction from these cards.

For each dimension, delta = (incoming-outgoing)/20.
Positive delta earns 2*max(need-.5,0)*delta; negative delta costs
.5*game-state importance*abs(delta). Sum gives tactical_core.
Tactical support = .1*aerial_need*(aerial difference/20)
+ .05*(pace_need+recovery_need)*(estimated speed difference/5).

Quality preservation = clip(sum incoming Threat+Progression+Defense /
sum outgoing Threat+Progression+Defense,0,1).
Freshness relief = **0.5 * outgoing fatigue * quality preservation** (1.5 until 19 Oct 2026; see CONTRACT.md, "Decision rules revision").
All ability-loss penalties still enter core. Freshness is counted once.

Evidence multiplier = .5 + .5*min(mean incoming general reliability,
mean outgoing general reliability). This is not a probability.
Position fit = 1 primary broad role, .85 verified secondary broad role.
Remaining = max(94-minute,0).
Tactical horizon = remaining/90.
Freshness horizon = min(remaining/30,1).

**Benefit = position_fit * evidence_multiplier *
((tactical_core+tactical_support)*tactical_horizon + freshness_relief*freshness_horizon).**

The shorter freshness horizon treats relief as a near-term contribution; it avoids
discounting a newly tired player as if the relief needed another 90 minutes to matter.
Both terms vanish near the end. Thirty minutes and cap 1.5 are explicit heuristic
assumptions. The prior 1.2/90, 1.2/30 and nearby 1.8/30 are published for comparison.
No parameter names a player, team, historical swap or desired substitution count.

The output's score is the pre-horizon sum times evidence; expected_benefit is the
decision quantity with the separate horizons above. score_components exposes both
horizons, core, support, relief, fatigue and evidence. The .15 threshold, same-role
eligibility, available bench, minute>=20 and three-substitution historical rule remain.

The controlled test allows a slightly worse fresh player late with flat tactical needs,
refuses the same swap early, and refuses a much worse player late. It does not claim all
three-point losses are worthwhile under all evidence or positions. See VALIDATION.md
for observed sensitivity and remaining football limitations, particularly center-back bias.
